# Connect an AI agent to CutVoke

CutVoke ships a local stdio MCP server inside the desktop app. Your agent edits the same project library that the editor shows, so you can watch changes and fix anything by hand.

- [Claude Code](claude-code.md)
- [Codex](codex.md)
- [Cursor](cursor.md)
- Other MCP clients (Claude Desktop, etc.): paste the `mcpServers` block from `profile/mcp-config.json` into the client's MCP config.

## Where the config comes from

Launch the desktop app once. It writes `profile/mcp-config.json` in the CutVoke data folder:

| Platform | Data folder |
| :--- | :--- |
| Windows (portable) | `CutVoke Data` next to `CutVoke.exe` |
| macOS | `~/Library/Application Support/CutVoke/` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/CutVoke/` |

The file has this shape (values are absolute paths on your machine):

```json
{
  "mcpServers": {
    "cutvoke": {
      "command": "<absolute path to the bundled cutvoke-engine>",
      "args": ["mcp", "--data", "<absolute path to data/projects.sqlite>"],
      "env": {
        "CUTVOKE_HOME": "<data folder>",
        "CUTVOKE_FONT_CACHE": "<data folder>/data/font-cache",
        "CUTVOKE_GPU_ACCELERATION": "1"
      }
    }
  }
}
```

Always copy the values from your own file. On Windows the bundled command is `cutvoke-engine.exe`. `CUTVOKE_GPU_ACCELERATION` is `"1"` unless GPU acceleration is turned off in the app, which writes `"0"`. If you move the app, launch it once more to refresh the paths. No system Python is needed for the packaged engine.

Running the desktop app from a source checkout, without the bundled engine, writes the same file with a different command: the checkout's `.venv` Python, args `["-m", "cutvoke", "mcp", "--data", "<projects.sqlite>"]`, and `PYTHONPATH` set to the repository `src` directory. An activated environment can also use `cutvoke mcp --data <path>` or `cutvoke-mcp --data <path>`, pointed at the same library the editor uses. See [external-agent-editing.md](../user/external-agent-editing.md).

## Optional: the cutvoke-editor skill

[`skills/cutvoke-editor/`](../../skills/cutvoke-editor/) teaches an agent CutVoke's editing workflow (plan, rough cut, captions, frame review, export). MCP-only clients can also get the same guides through the `editor_help` tool. See the [Agent Skill Guide](../user/agent-skill.md).
