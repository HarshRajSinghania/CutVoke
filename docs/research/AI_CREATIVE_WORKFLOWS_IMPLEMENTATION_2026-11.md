# Creative workflow implementation, November 2026

This first batch adopts the project research report **AI视频制作实战经验与CutVoke改进路线** (research through 2026-11-02). The report was read as a complete local DOCX; it distinguishes creator accounts, interviews, official workflows and studies from independently replayed output. Its proposed style cards are synthesized experiments, not validated optimal templates. No source film, study, third-party repository or creator budget was independently replicated in this implementation.

## What runs

`creative_workflow` exposes bounded English/Chinese recipe discovery and individual details, strict version-1 plan/review/repair schemas, current-project contract validation, and a read-only local repair preview. MCP and the existing HTTP Agent endpoint share the implementation. The previous editor_help and resource documents retain their routes. An installed Skill is optional. The recipe catalog is packaged with the application; no model, network service or project migration is needed.

The catalog separates audience purpose, expressive grammar and publishing dimensions/context. It contains 18 options across product/brand, conversation/highlights, knowledge, tutorials, travel, news/history, portraits, fiction, music, events and private memories. Prerequisites, source roles, narrative development, sound, captions, failure patterns, fallback choices and purpose-specific acceptance are explicit. A recipe gives options rather than fixed shot durations, effect counts or a generic cinematic score.

The [runnable stdio example](../../examples/creative-workflow/README.md) demonstrates the complete mechanical loop using owned synthetic fixtures and actual exports. Contract and transport tests cover revision/sequence mismatch, missing references, pending evidence, protected ranges, scope, controller/shared composition boundaries, invalid input, idempotency and undo. These are correctness checks, not blind creative evaluation.

## Reused and deliberately bounded

Existing rational timing, transaction preview, batch commands, leases, revision checks, idempotency, undo, media import, captions, audio processing, preview and export are reused. The preceding unpublished editing-review branch provides text audition/deletion review, stale preview isolation and compact command discovery. This branch depends on that base; it does not present those as new engine work.

Repair preview compares the actual candidate state, not just handler change metadata. It conservatively rejects unbounded/global changes, nested/shared composition edits, and clip edits in projects with scalar controller, matte or stateful mixer/sidechain dependencies. Implementing dependency-expanded source/instance/render mappings remains separate work. Ordinary editing APIs do not automatically enforce optional plan artifacts, and semantic preserve notes are not machine-proven constraints.

Artifact references are opaque references, not authenticated evidence. The tool does not open paths or URLs, watch frames, listen to sound, check rights, fact-check or certify a reviewer. It always returns creativeAcceptance=not_assessed. Pending sensory review must stay visible even when schemas, codecs and numeric checks pass.

## What remains from the report

- Real-footage quality baselines: fixed authorized briefs and materials, competing cuts, independent complete AV review and audience comprehension tasks across types. Synthetic color/tone integration cannot establish a quality improvement.
- Revision-bound automatic evidence packaging with actual artifact hashes, export metadata, representative frames, cut neighborhoods and device views. Current contracts organize Agent-produced references without certifying bytes.
- Complete source-to-instance-to-render mappings for repeated sources, retiming, reverse, freeze frames, nested/shared sequences, controllers and audio dependency propagation. The first bounded repair interface rejects unsupported cases instead of guessing.
- Semantic selection/ranking, visual continuity suggestions and bulk delivery variants, only after real evaluations establish a useful bottleneck. No paid video generation or new model service is added.

Examples informing the report include [travel A-roll before B-roll](https://li-yang.cn/ai-edited-new-zealand-vlogs/), [a director's actual-output checks](https://evandro-miguel.com/articles/isa-short-film-production/), [staged brand production](https://medium.com/@gorociao/the-ai-directors-playbook-where-traditional-filmmaking-instincts-meet-generative-workflows-414632651815), [sound scoring choices](https://transom.org/2019/scoring-stories-part-2/), and [conditional wedding multicam assistance](https://whoismatt.com/use-ai-to-edit-wedding-ceremony-videos-fast-in-premiere-pro/). The machine-readable catalog preserves the report's source IDs, direct links and reading limitations. These links describe provenance; they are not evidence that this software produced comparable films.
