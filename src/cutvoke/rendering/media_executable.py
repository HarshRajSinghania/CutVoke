"""Resolve default media binaries without trusting the first PATH placeholder.

Explicit RenderService paths bypass discovery. Validation is cached by candidate
file identity, so repeated requests do not spawn version checks and replacing or
repairing a binary invalidates both successful and failed discovery.
"""
from collections import OrderedDict
import logging
import os
from pathlib import Path
import subprocess
import threading
import time

_cache = OrderedDict()
_lock = threading.Lock()


def _candidates(name):
    filename = name + '.exe' if os.name == 'nt' else name
    directories = (directory.strip('"') if os.name == 'nt' else directory
                   for directory in os.get_exec_path())
    paths = dict.fromkeys(os.path.abspath(os.path.join(directory, filename))
                          for directory in directories)
    result = []
    for path in paths:
        try:
            stat = Path(path).stat()
            result.append((path, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns,
                           stat.st_mode, stat.st_dev, stat.st_ino))
        except FileNotFoundError:
            continue
        except OSError as error:
            result.append((path, str(error)))
    return tuple(result)


def _discover(name, candidates):
    rejected = []
    for identity in candidates:
        path = identity[0]
        try:
            if len(identity) == 2:
                raise OSError(identity[1])
            if identity[1] == 0:
                raise OSError('empty executable')
            completed = subprocess.run([path, '-version'], capture_output=True,
                                       text=True, errors='replace', timeout=3)
            lines = (completed.stdout or completed.stderr).splitlines()
            if completed.returncode != 0:
                raise OSError(f'version check exited {completed.returncode}: '
                              f'{(completed.stderr or completed.stdout)[:300]}')
            if not lines or not lines[0].startswith(name + ' version '):
                raise OSError(f'unexpected {name} version output: '
                              f'{lines[0][:200] if lines else "<empty>"}')
        except (OSError, subprocess.TimeoutExpired) as error:
            rejected.append({'path': path, 'message': str(error)[:500]})
            continue
        for item in rejected:
            logging.getLogger(__name__).warning('Skipping unusable %s at %s: %s',
                                               name, item['path'], item['message'])
        return path, lines[0], tuple((item['path'], item['message']) for item in rejected)
    return None, None, tuple((item['path'], item['message']) for item in rejected)


def media_tool_status(name):
    if name not in ('ffmpeg', 'ffprobe'):
        raise ValueError(f'unsupported media executable: {name}')
    key = (name, _candidates(name))
    with _lock:
        cached = _cache.get(key)
        # Retry transient start failures/timeouts, including a first candidate
        # that recovers without a file replacement. Healthy results need no TTL.
        if cached is None or ((cached[1][0] is None or cached[1][2]) and
                              time.monotonic() - cached[0] >= 3):
            discovered = _discover(*key)
            cached = (time.monotonic(), discovered)
            _cache[key] = cached
        _cache.move_to_end(key)
        while len(_cache) > 32:
            _cache.popitem(last=False)
        path, version, rejected = cached[1]
    return {'path': path, 'version': version,
            'rejectedCandidates': [{'path': p, 'message': m} for p, m in rejected]}


def resolve_media_tool(name):
    status = media_tool_status(name)
    if status['path']:
        return status['path']
    detail = '; '.join(f"{item['path']}: {item['message']}"
                       for item in status['rejectedCandidates']) or 'no candidate on PATH'
    raise OSError(f'No usable {name}: {detail}. Install a working binary and correct PATH; '
                  'run cutvoke doctor --json for diagnostics.')
