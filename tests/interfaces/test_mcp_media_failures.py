"""Project discovery must survive unavailable optional media tools."""
import errno
from unittest.mock import patch

import pytest

from cutvoke.editing.service import EditService
from cutvoke.interfaces.mcp_server import MCPServer
from cutvoke.rendering.render import RenderError, RenderService
from cutvoke.storage.store import ProjectStore


def bad_windows_executable():
    error = OSError(errno.ENOEXEC, '%1 is not a valid Win32 application')
    error.winerror = 193
    return error


def test_project_list_does_not_initialize_optional_media(tmp_path):
    store = ProjectStore(str(tmp_path / 'projects.sqlite'))
    service = EditService(store)
    service.create_project('saved')
    server = MCPServer(service, media_dir=str(tmp_path / 'media'))
    try:
        with patch.object(RenderService, 'probe_media', side_effect=bad_windows_executable()) as probe:
            for _ in range(2):
                result = server.call_tool('project_list', {})
                assert result['ok'], result
                assert result['projects'][0]['id'] == 'saved'
                assert result['total'] == 1
            probe.assert_not_called()
            assert server._agent_api is None
    finally:
        server.close()
        store.close()


def test_probe_converts_process_start_failure_to_render_error(tmp_path):
    source = tmp_path / 'source.wav'
    source.write_bytes(b'RIFF')
    renderer = RenderService(ffprobe_path=str(tmp_path / 'explicit-ffprobe'))
    with patch('cutvoke.rendering.render.subprocess.run', side_effect=bad_windows_executable()):
        with pytest.raises(RenderError, match='ffprobe.*193|ffprobe.*Win32'):
            renderer.probe_media(str(source))


def test_discovery_remains_usable_after_a_real_media_error(tmp_path, monkeypatch):
    monkeypatch.setenv('PATH', str(tmp_path / 'missing-tools'))
    store = ProjectStore(str(tmp_path / 'projects.sqlite'))
    service = EditService(store)
    server = MCPServer(service, media_dir=str(tmp_path / 'media'))
    source = tmp_path / 'source.wav'
    source.write_bytes(b'RIFF')
    try:
        assert server.call_tool('create_project', {'projectId': 'kept'})['ok']
        failure = server.call_tool('media_inspect', {'path': str(source)})
        assert not failure['ok']
        assert failure['error']['code'] == 'EXECUTION_FAILED'
        assert 'ffprobe' in failure['error']['message']
        for name in ('runtime', 'editor_help', 'project_list'):
            assert server.call_tool(name, {})['ok']
        result = server.call_tool('project_list', {'query': 'kept', 'limit': 1})
        assert result['total'] == 1 and result['projects'][0]['id'] == 'kept'
    finally:
        server.close()
        store.close()


def test_mcp_listing_preserves_shared_pagination_and_query(tmp_path):
    store = ProjectStore(str(tmp_path / 'projects.sqlite'))
    service = EditService(store)
    server = MCPServer(service, media_dir=str(tmp_path / 'media'))
    try:
        for index in range(3):
            service.create_project(f'project-{index}')
        arguments = {'query': 'PROJECT', 'offset': 1, 'limit': 1}
        result = server.call_tool('project_list', arguments)
        assert result['ok']
        assert result['total'] == 3 and result['nextOffset'] == 2
        assert len(result['projects']) == 1
        empty = server.call_tool('project_list', {'query': 'absent'})
        assert empty['projects'] == [] and empty['total'] == 0 and empty['nextOffset'] is None
    finally:
        server.close()
        store.close()
