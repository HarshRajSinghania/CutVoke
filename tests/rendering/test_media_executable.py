"""Default discovery, explicit paths and recovery use disposable candidates."""
import errno
import os
from pathlib import Path
import shutil
import subprocess
from unittest.mock import patch

import pytest

from cutvoke.rendering import media_executable as tools
from cutvoke.rendering.render import RenderError, RenderService


def candidate(root, name='ffprobe', content=b'candidate'):
    root.mkdir(exist_ok=True)
    path = root / (name + '.exe' if os.name == 'nt' else name)
    path.write_bytes(content)
    path.chmod(0o755)
    return path


@pytest.mark.parametrize('name', ['ffmpeg', 'ffprobe'])
@pytest.mark.parametrize('failure', ['empty', 'format', 'permission', 'missing',
                                    'windows193', 'timeout', 'nonzero', 'wrong-tool'])
def test_skips_unusable_path_candidate_and_keeps_diagnostic(tmp_path, monkeypatch, failure, name):
    bad = candidate(tmp_path / 'bad', name=name, content=b'' if failure == 'empty' else b'bad')
    good = candidate(tmp_path / 'good', name=name)
    monkeypatch.setenv('PATH', os.pathsep.join([str(bad.parent), str(good.parent)]))
    started = []

    def run(command, **kwargs):
        started.append(command[0])
        assert command[1:] == ['-version']
        if command[0] == str(bad):
            if failure == 'windows193':
                error = OSError(errno.ENOEXEC, 'not a valid Win32 application')
                error.winerror = 193
                raise error
            if failure == 'format':
                raise OSError(errno.ENOEXEC, 'Exec format error')
            if failure == 'permission':
                raise PermissionError(errno.EACCES, 'Permission denied')
            if failure == 'missing':
                raise FileNotFoundError(errno.ENOENT, 'Removed before start')
            if failure == 'timeout':
                raise subprocess.TimeoutExpired(command, kwargs['timeout'])
            return subprocess.CompletedProcess(command, 1 if failure == 'nonzero' else 0, 'other version 1', '')
        return subprocess.CompletedProcess(command, 0, name + ' version fixture\n', '')

    with patch.object(tools.subprocess, 'run', side_effect=run):
        status = tools.media_tool_status(name)
        assert status['path'] == str(good)
        assert len(status['rejectedCandidates']) == 1
        assert status['rejectedCandidates'][0]['path'] == str(bad)
        for _ in range(20):
            assert tools.resolve_media_tool(name) == str(good)
    assert started == ([str(good)] if failure == 'empty' else [str(bad), str(good)])


def test_no_candidates_is_actionable_and_install_is_detected(tmp_path, monkeypatch):
    monkeypatch.setenv('PATH', str(tmp_path))
    with pytest.raises(OSError, match='No usable ffprobe.*PATH'):
        tools.resolve_media_tool('ffprobe')
    path = candidate(tmp_path)
    with patch.object(tools.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'ffprobe version fixture', '')):
        assert tools.resolve_media_tool('ffprobe') == str(path)


def test_transient_failure_recovers_without_file_change(tmp_path, monkeypatch):
    path = candidate(tmp_path)
    monkeypatch.setenv('PATH', str(tmp_path))
    with patch.object(tools.time, 'monotonic', return_value=10), patch.object(
            tools.subprocess, 'run', side_effect=PermissionError('temporarily unavailable')):
        assert tools.media_tool_status('ffprobe')['path'] is None
    with patch.object(tools.time, 'monotonic', return_value=14), patch.object(
            tools.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'ffprobe version fixture', '')):
        assert tools.resolve_media_tool('ffprobe') == str(path)


def test_replaced_selected_executable_invalidates_cache(tmp_path, monkeypatch):
    first = candidate(tmp_path / 'first')
    second = candidate(tmp_path / 'second')
    monkeypatch.setenv('PATH', os.pathsep.join([str(first.parent), str(second.parent)]))
    with patch.object(tools.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'ffprobe version fixture', '')) as run:
        assert tools.resolve_media_tool('ffprobe') == str(first)
        first.write_bytes(b'')
        assert tools.resolve_media_tool('ffprobe') == str(second)
        assert run.call_count == 2


def test_explicit_path_does_not_fall_back_or_probe_versions(tmp_path):
    source = tmp_path / 'source.wav'
    source.write_bytes(b'RIFF')
    explicit = str(tmp_path / 'specific-ffprobe')
    renderer = RenderService(ffmpeg_path='fixed-ffmpeg', ffprobe_path=explicit)
    with patch.object(tools, 'resolve_media_tool', side_effect=AssertionError('must not search PATH')):
        assert renderer.ffmpeg == 'fixed-ffmpeg'
        assert renderer.ffprobe == explicit
        with patch('cutvoke.rendering.render.subprocess.run', side_effect=PermissionError('denied')) as run:
            with pytest.raises(RenderError, match='ffprobe could not start.*specific-ffprobe.*denied'):
                renderer.probe_media(str(source))
            assert run.call_count == 1
            assert run.call_args.args[0][0] == explicit


@pytest.mark.skipif(os.name == 'nt', reason='POSIX executable fixtures; Windows errors tested above')
@pytest.mark.parametrize('content', [b'', b'not an executable binary'])
def test_real_shadow_file_is_skipped_and_real_probe_decodes(tmp_path, monkeypatch, content):
    import wave
    real_probe = shutil.which('ffprobe')
    if not real_probe:
        pytest.skip('ffprobe required')
    bad = candidate(tmp_path / 'shadow', content=content)
    good_dir = tmp_path / 'real'
    good_dir.mkdir()
    (good_dir / 'ffprobe').symlink_to(real_probe)
    monkeypatch.setenv('PATH', os.pathsep.join([str(bad.parent), str(good_dir)]))
    source = tmp_path / 'tone.wav'
    with wave.open(str(source), 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(b'\0\0' * 800)
    info = RenderService().probe_media(str(source))
    assert info['has_audio'] and info['duration'] == pytest.approx(.1)
    assert tools.media_tool_status('ffprobe')['path'] == str(good_dir / 'ffprobe')


@pytest.mark.skipif(os.name == 'nt', reason='POSIX executable fixture')
def test_real_ffmpeg_after_empty_shadow_produces_audio(tmp_path, monkeypatch):
    real_tools = {name: shutil.which(name) for name in ('ffmpeg', 'ffprobe')}
    if not all(real_tools.values()):
        pytest.skip('FFmpeg required')
    shadow = tmp_path / 'shadow'
    good = tmp_path / 'good'
    good.mkdir()
    for name, real in real_tools.items():
        candidate(shadow, name=name, content=b'')
        (good / name).symlink_to(real)
    monkeypatch.setenv('PATH', os.pathsep.join([str(shadow), str(good)]))
    renderer = RenderService()
    output = tmp_path / 'generated.wav'
    subprocess.run([renderer.ffmpeg, '-v', 'error', '-f', 'lavfi', '-i',
                    'sine=frequency=440:duration=0.2', str(output)],
                   check=True, capture_output=True, timeout=10)
    info = renderer.probe_media(str(output))
    assert info['has_audio'] and info['duration'] == pytest.approx(.2)


@pytest.mark.skipif(os.name != 'nt', reason='requires real Windows CreateProcess')
@pytest.mark.parametrize('content', [b'', b'not a Windows executable'])
def test_real_windows_invalid_exes_and_explicit_failure(tmp_path, monkeypatch, content):
    import wave
    real = {name: shutil.which(name) for name in ('ffmpeg', 'ffprobe')}
    assert all(real.values()), 'native acceptance must provide FFmpeg and ffprobe'
    shadow = tmp_path / 'shadow'
    bad = {name: candidate(shadow, name=name, content=content) for name in real}
    monkeypatch.setenv('PATH', str(shadow) + os.pathsep + os.environ['PATH'])
    for name in real:
        status = tools.media_tool_status(name)
        assert os.path.normcase(status['path']) == os.path.normcase(real[name])
        assert status['rejectedCandidates'][0]['path'] == str(bad[name])
        message = status['rejectedCandidates'][0]['message']
        # Windows versions classify malformed images as bad format (193) or
        # machine mismatch (216). Both must preserve later valid candidates;
        # the exact 193 branch also has deterministic coverage above.
        assert (any(code in message for code in ('WinError 193', 'WinError 216'))
                if content else message == 'empty executable'), message
    source = tmp_path / 'source.wav'
    with wave.open(str(source), 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(b'\0\0' * 800)
    assert RenderService().probe_media(str(source))['duration'] == pytest.approx(.1)
    if content:
        with pytest.raises(RenderError, match=r'ffprobe could not start.*WinError (193|216)'):
            RenderService(ffprobe_path=str(bad['ffprobe'])).probe_media(str(source))
