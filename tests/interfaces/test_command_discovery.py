"""Opt-in compact command discovery keeps detailed discovery compatible."""
import json
from unittest.mock import patch

import pytest

from cutvoke.editing.service import EditService
from cutvoke.interfaces.agent_tools import AgentTools
from cutvoke.interfaces.httpapi import HttpApi
from cutvoke.interfaces.mcp_server import MCPServer


@pytest.fixture
def discovery(tmp_path):
    service = EditService()
    api = HttpApi(service, media_dir=str(tmp_path / "http-media"))
    server = MCPServer(service, media_dir=str(tmp_path / "mcp-media"))
    yield service, api, server
    server.close()
    api.close()


def compact(entry):
    return {key: value for key, value in entry.items()
            if key not in ("params", "inputSchema")}


def test_default_and_explicit_full_discovery_match_existing_catalog(discovery):
    service, api, server = discovery
    catalog = service.command_catalog()
    expected = {"ok": True, "commands": catalog[:20], "total": len(catalog), "nextOffset": 20}
    for arguments in ({}, {"includeSchemas": True}):
        assert server.call_tool("commands_list", arguments) == expected
        assert api.handle("POST", "/api/v1/agent/commands_list", arguments) == (200, expected)
    assert all("inputSchema" in entry and "params" in entry for entry in catalog)
    # Existing HTTP callers retain their complete response and count contract.
    assert api.handle("GET", "/api/v1/commands", {}) == (200, {"commands": catalog, "count": len(catalog)})


@pytest.mark.parametrize("arguments", [
    {}, {"query": "CLIP."}, {"query": "字幕"}, {"type": "edit.batch"},
    {"type": "clip.insert", "query": "CLIP"}, {"type": "clip.insert", "query": "export"},
    {"query": "no-such-command"}, {"offset": 4, "limit": 3},
    {"offset": 10000, "limit": 1},
])
def test_compact_mcp_and_http_preserve_filters_order_and_pagination(discovery, arguments):
    _, api, server = discovery
    full = server.call_tool("commands_list", arguments)
    expected = {**full, "commands": [compact(entry) for entry in full["commands"]]}
    lightweight = {**arguments, "includeSchemas": False}
    assert server.call_tool("commands_list", lightweight) == expected
    assert api.handle("POST", "/api/v1/agent/commands_list", lightweight) == (200, expected)
    # Exercise the actual MCP JSON-RPC result serialization too.
    wire = server._handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": "commands_list", "arguments": lightweight}})["result"]
    assert not wire["isError"]
    assert json.loads(wire["content"][0]["text"]) == expected


def test_compact_catalog_skips_schema_building_and_keeps_preview_metadata(discovery):
    service, _, server = discovery
    full = service.command_catalog()
    with patch("cutvoke.editing.command_schema.payload_schema", side_effect=AssertionError("schema built")), \
            patch.object(service._effects, "get", side_effect=AssertionError("effect loaded")):
        light = service.command_catalog(include_schemas=False)
        assert light == [compact(entry) for entry in full]
        assert server.call_tool("commands_list", {"includeSchemas": False})["ok"]
    entries = {entry["type"]: entry for entry in light}
    for command in ("audio.record", "audio.export", "caption.transcribe", "export.enqueue"):
        assert entries[command]["previewSupported"] is False
    assert entries["clip.insert"]["previewSupported"] is True
    assert entries["edit.batch"]["allowedCommands"]
    assert entries["edit.batch"]["maxCommands"] == 32
    # Compact discovery must not alter later detailed help or effect parameters.
    detailed = server.call_tool("editor_help", {"topic": "command", "command": "effect.add",
                                               "effectId": "cutvoke.transform"})["help"]
    assert detailed["params"]
    assert "opacity" in detailed["inputSchema"]["properties"]["params"]["properties"]
    assert service.command_catalog() == full


@pytest.mark.parametrize("invalid", [None, 0, 1, 0.0, "false", "true", [], {}])
def test_include_schemas_requires_a_boolean_in_protocols_and_direct_adapters(discovery, invalid):
    service, api, server = discovery
    arguments = {"includeSchemas": invalid}
    schema = next(tool for tool in server.list_tools() if tool["name"] == "commands_list")["inputSchema"]
    assert schema["properties"]["includeSchemas"] == {"type": "boolean", "default": True}
    with pytest.raises(ValueError, match="includeSchemas.*boolean"):
        server._validate_arguments(arguments, schema)
    result = server.call_tool("commands_list", arguments)
    assert result["ok"] is False and result["error"]["code"] == "INVALID_ARGUMENT"
    status, result = api.handle("POST", "/api/v1/agent/commands_list", arguments)
    assert status == 400 and result["error"]["code"] == "INVALID_ARGUMENT"
    for invoke in (lambda: AgentTools(api).call("commands_list", arguments),
                   lambda: AgentTools(api).commands_list(arguments),
                   lambda: service.command_catalog(include_schemas=invalid)):
        with pytest.raises(ValueError, match="includeSchemas.*boolean"):
            invoke()
