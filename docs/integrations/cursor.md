# Use CutVoke from Cursor: free, local video editing over MCP

Let Cursor's agent build and revise a CutVoke timeline (rough cuts, captions, vertical versions, exports) while you keep full manual control in the CutVoke editor.

## 1. Get the MCP config

1. [Download CutVoke](https://github.com/frankShan001/CutVoke/releases) and launch it once.
2. Open `profile/mcp-config.json` in the CutVoke data folder ([where is it?](README.md#where-the-config-comes-from)).

## 2. Add it to Cursor

Cursor uses the same `mcpServers` format, so you can paste the file's contents directly:

- **All projects**: `~/.cursor/mcp.json`
- **One project**: `.cursor/mcp.json` in the project root

```json
{
  "mcpServers": {
    "cutvoke": {
      "command": "/absolute/path/to/cutvoke-engine",
      "args": ["mcp", "--data", "/absolute/path/to/data/projects.sqlite"],
      "env": {
        "CUTVOKE_HOME": "/absolute/path/to/data-folder",
        "CUTVOKE_FONT_CACHE": "/absolute/path/to/data-folder/data/font-cache",
        "CUTVOKE_GPU_ACCELERATION": "1"
      }
    }
  }
}
```

If `mcp.json` already has other servers, add only the `"cutvoke": { ... }` entry inside the existing `mcpServers` object. On Windows, JSON paths need doubled backslashes (`D:\\CutVoke\\...`), which is already the case in the generated file.

Open Cursor Settings → MCP (Tools & MCP) and check that `cutvoke` is enabled and its tools are listed.

## 3. (Optional) Give the agent the editing workflow

Point the agent at [`skills/cutvoke-editor/SKILL.md`](../../skills/cutvoke-editor/SKILL.md) (for example by adding the folder to your workspace and referencing it in chat), or let it call the `editor_help` tool, which serves the same guides over MCP.

## 4. Try it

Keep the CutVoke editor open on the same project to watch the timeline change. Example prompts:

- *"Create a CutVoke project from ./footage, cut the silences, add captions, and show me frames before exporting."*
- *"Make a 9:16 version of the current project and export it into this repo's `out/` folder."*
- *"Tighten the intro to under 5 seconds and keep the rest of the timeline unchanged."*

Automatic captions use an optional local speech model that downloads on first use ([Local ASR](../user/LOCAL_ASR.md)).

## Troubleshooting

- **Server shows an error**: confirm the `command` path exists; relaunch the desktop app if you moved it.
- **Agent can't see the editor's projects**: `--data` must be the same `projects.sqlite` the desktop app uses.

More: [all integrations](README.md) · [External agent editing](../user/external-agent-editing.md) · [Agent Skill Guide](../user/agent-skill.md)
