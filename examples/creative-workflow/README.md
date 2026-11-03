# A reproducible Agent creative loop

Run from an installed source checkout (Python dependencies and FFmpeg/ffprobe on PATH):

```bash
python skills/cutvoke-editor/scripts/creative_demo.py --output /absolute/new/creative-loop
```

On Windows pass a new absolute directory such as `C:\work\creative-loop`. Existing output is refused. The container holds a new managed project directory and database. Plans, review files, source fixtures, frames, calls and MP4s live under the project's returned directory. No existing media library, network generation or paid provider is used.

The script uses real stdio MCP and current command help. It selects a product-demonstration recipe, creates original color/tone fixtures, assembles an editable rough cut with a deliberately wrong literal caption, exports it, validates a versioned plan and evidence-backed issue, dry-runs one local caption repair, explicitly commits with a lease and stable command ID, checks idempotent replay, rejects the stale issue, and exports/rechecks the new version. It keeps `plan-before/after`, `review-before/after`, the repair and its preview as actual JSON examples.

Actual final MP4 checks cover full decoding, duration, stable red/blue regions and 440/880 Hz audio, with clip/media state unchanged. The fixture deliberately has no real speech, product proof or narrative; the script marks continuous AV inspection and audience comprehension pending. Running it does not demonstrate better artistic work. Use licensed real footage and meaningful briefs for separate creative evaluation.

For an MCP-only client, start `editor_help(topic="creative")`, follow `recipes`, then load `guide="creative-workflow"`. The same tool is exposed at `POST /api/v1/agent/creative_workflow`. See the [contract and limitations](../../skills/cutvoke-editor/references/creative-workflow.md).

中文：此示例执行真实 MCP 的“配方→粗剪→版本化审片→局部预演→显式提交→新版本复查”闭环，产出可继续编辑工程和真实 MP4。红蓝色块、音调和字幕错误均为自造测试数据；技术通过不等于产品视频真实、有说服力或精彩。实际创作仍须核对原片、听完整声音并检查目标观众能否理解。
