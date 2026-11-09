# Use CutVoke from Claude Code: free, local video editing over MCP

Let Claude Code make the rough cut, captions and vertical versions of your video while you keep a normal, editable timeline in the CutVoke editor.

## 1. Get the MCP command

1. [Download CutVoke](https://github.com/frankShan001/CutVoke/releases) and launch it once.
2. Open `profile/mcp-config.json` in the CutVoke data folder ([where is it?](README.md#where-the-config-comes-from)). You need the `cutvoke` entry: `command`, `args` and `env`.

## 2. Add it to Claude Code

The simplest way is `claude mcp add-json`, which accepts the entry as JSON. Replace the placeholders with the values from your file:

```bash
claude mcp add-json cutvoke --scope user '{
  "type": "stdio",
  "command": "/absolute/path/to/cutvoke-engine",
  "args": ["mcp", "--data", "/absolute/path/to/data/projects.sqlite"],
  "env": {
    "CUTVOKE_HOME": "/absolute/path/to/data-folder",
    "CUTVOKE_FONT_CACHE": "/absolute/path/to/data-folder/data/font-cache",
    "CUTVOKE_GPU_ACCELERATION": "1"
  }
}'
```

Or, with flags:

```bash
claude mcp add cutvoke --scope user \
  -e CUTVOKE_HOME="/absolute/path/to/data-folder" \
  -e CUTVOKE_FONT_CACHE="/absolute/path/to/data-folder/data/font-cache" \
  -e CUTVOKE_GPU_ACCELERATION=1 \
  -- "/absolute/path/to/cutvoke-engine" mcp --data "/absolute/path/to/data/projects.sqlite"
```

`--scope user` makes CutVoke available in every project. Omit it to add it only to the current project. On Windows, the engine path ends in `cutvoke-engine.exe`; in PowerShell, keep the paths in quotes.

Check it with `claude mcp list`, then start a new Claude Code session (or run `/mcp`) so it loads the CutVoke tools.

## 3. (Optional) Add the cutvoke-editor skill

Copy the whole [`skills/cutvoke-editor/`](../../skills/cutvoke-editor/) folder to `~/.claude/skills/cutvoke-editor/` so Claude Code can load CutVoke's editing workflow on demand. Without it, Claude can still read the same guides through the `editor_help` tool.

## 4. Try it

Keep the CutVoke editor open on the same project to watch the timeline change. Example prompts:

- *"Create a CutVoke project from the clips in ~/Videos/trip, cut the silences, and add captions."*
- *"Make a 9:16 version of this project for Shorts and show me a few frames before you export."*
- *"Find the sentence where I say 'pricing' in the transcript, remove it, and export a new MP4 next to the original."*

Automatic captions use an optional local speech model that downloads on first use ([Local ASR](../user/LOCAL_ASR.md)).

## Troubleshooting

- **Tools don't appear**: restart the session after adding the server, and confirm the `command` path exists.
- **Agent can't see projects from the editor**: `--data` must point at the same `projects.sqlite` that the desktop app uses. Copy it from `mcp-config.json` rather than typing it.
- **Moved the app**: launch it once to regenerate `mcp-config.json`, then update the Claude Code entry.

More: [all integrations](README.md) · [External agent editing](../user/external-agent-editing.md) · [Agent Skill Guide](../user/agent-skill.md)
