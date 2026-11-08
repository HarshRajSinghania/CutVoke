# CutVoke v0.3.5 — Cross-platform preview / 跨平台预览版

This prerelease delivers the editing and external-render workflows added since
v0.3.4, with startup, transparent-cut and source-package fixes. The editable
CutVoke project and timeline remain authoritative.

Changes since the published v0.3.4 packages:

- Text-based editing can search, locate and audition sentence/word ranges,
  preview deletion impacts, and confirm one undoable synchronized picture,
  audio and caption edit. Stale project/preview responses and competing audition
  clocks no longer replace newer work or extend the selected audition range.
- Creative workflows add bounded recipe discovery, plan/review contracts and
  local repair previews. Evidence references organize review; the tool always
  leaves creative acceptance unassessed instead of certifying visual quality.
- External code-video manifests validate declared source/output hashes, decoded
  frame clocks, alpha and color contracts before importing ordinary media.
  Parameterized render requests validate bounded parameters and absolute frame
  windows before output exists, reuse verified exact/covering cached outputs,
  and work with native split/replace/revision/lease/undo operations.
- Builtin PCM WAV and static-background metadata reduce cold MCP startup work
  while preserving hash verification and media-probe fallback for unsupported
  or truncated inputs. Broken media tools no longer prevent project discovery.
- Transparent shots now obey half-open sequence-frame intervals, including
  single-frame cuts and NTSC preview origins. A timestamp-derived gate preserves
  delayed transparent video on FFmpeg 6 and 7. Preview caches rebuild for the
  updated rendering behavior.
- Worker archives exclude checkout-only asset generators, so direct wheel
  builds and source-archive rebuilds retain the same runtime worker payload and
  catalog hashes. Runtime code, guides, recipe data and worker license remain.

All four archives must be newly built and accepted at this version's exact
tagged main commit. BUILD-INFO.json records the source and build runs;
SHA256SUMS records the archive hashes. Download the matching Windows x64 portable
ZIP, macOS ARM64/Intel ZIP or Linux x64 tar.gz. These archives include the editor,
frozen backend, FFmpeg/ffprobe, resources and third-party notices. Basic editing
needs no separate Python, Node.js or system FFmpeg. Optional models and PyTorch
remain separate downloads.

Close CutVoke before updating, back up existing projects and preserve their
data/media directories. Existing releases and downloads remain available.

Scope and remaining boundaries:

- External renderers run independently and must be trusted. CutVoke does not
  execute arbitrary scene code or provide an isolation runtime, parameter GUI
  or external-renderer cancellation/recovery lifecycle.
- Source ZIPs and render-cache metadata remain outside .cvkpkg. Rendered media
  and ordinary editing survive project packaging; source-scene migration,
  restoration and cache transfer are not implemented.
- Frame/pixel, decode and audio measurements establish technical behavior.
  Synthetic examples do not establish subjective listening, artistic quality,
  real-footage improvements or cross-machine performance guarantees.
- Windows/Linux archives remain unsigned; macOS uses an ad-hoc integrity
  signature without Developer ID signing or notarization. Physical-device
  GPU/audio/microphone/native-picker and quarantined first-launch acceptance
  remain separate. The historical Intel export-preparation timeout still lacks
  a proven root cause; repeated native exports retain diagnostics if it recurs.
  Optional/environment-dependent Python skips and Windows frozen-app behavior
  with long-path policy disabled remain outside validated coverage.

本版将 v0.3.4 之后的文本剪辑、创作方案审阅与局部修补、外部代码视频素材桥接和
参数化渲染缓存打入新的四平台预发布包。工程和时间线仍由 CutVoke 原生编辑模型管理，
可继续人工修改、分割、替换和撤销。

按句/词定位与试听、删除影响预览和一次撤销保持画面、声音和字幕同步；修复过期工程/
预览响应与试听时钟竞争。创作契约和证据引用用于组织审阅，不自动给出艺术质量结论。
外部渲染请求支持有界参数、绝对帧窗口、已验证缓存复用和局部重渲；内置媒体元数据
减少 MCP 冷启动探测，并保留哈希和异常输入回退。透明切镜与单帧区间统一到序列时钟，
补齐 FFmpeg 6/7 和非整数帧率边界；源码重建与直接构建使用一致的 worker 内容。

发布须等待同一版本、同一 main/标签提交的 CI 和四平台真实成品验收，并核对包内
来源、BUILD-INFO.json、SHA256SUMS 及公开下载字节。继续提供 Windows 便携 ZIP、
两种 macOS ZIP 和 Linux tar.gz，不新增安装程序；基础使用无需另装开发环境。
更新前关闭应用，备份并保留工程及数据目录，旧版本与下载保持不变。

本版仍为预发布，保留原有签名、公证、实体设备与可选功能的未测边界。外部渲染器须
单独可信；任意代码隔离运行、参数 GUI、外部渲染作业取消/恢复，以及源码 ZIP 的工程包
迁移/恢复尚未实现。技术样例与音频测量不代表主观听评、艺术质量或跨设备性能保证。
