# M3 — Workbench artifact viewer + stage controls panel

> **Status**: Draft
> **Last updated**: 2026-05-11
> **Spec-Issue**: ConcaveTrillion/pd-prep-for-pgdp#44

## TL;DR

M3 turns the per-page stage DAG into a first-class workbench experience: a polished stage-chain rail
(replacing the M2 debug panel), side-by-side artifact compare, a stage-filtered `ResolvedPageConfig`
controls panel, and live SSE updates for stage transitions. Acceptance is a real per-stage artifact
strip on a real page with ≤2s feedback when one stage's config changes.

## Context

M2 shipped the per-page runner, eager dirty cascade, and a debug-style chip rail (`StageChainRail`
in `PageWorkbench`, commit `8af4f15`). M3 replaces the debug rail with a polished UX: visible
thumbnails per stage, click-to-select navigation, an artifact viewer pane that compares two stages,
and a controls panel that filters `ResolvedPageConfig` to just the fields the selected stage reads.
Live SSE makes the rail update across tabs without manual refresh.

Parent (retro-demoted on 2026-05-11): #9. Roadmap section: `docs/08-roadmap.md` §M3 (lines
~312–367).

## Constraints

- **M2 must be shipped** (per-page runner, eager dirty cascade, basic chip rail). Currently in
  flight; M3 work cannot start until M2's last slices land.
- **Field-to-stage mapping** needs a stable backend source — the controls panel must not duplicate
  stage-specific field knowledge in the frontend.
- **Artifact endpoint** (`GET /api/data/projects/{id}/pages/{idx0}/stages/{stage_id}/artifact`,
  shipped in M2 commit `55dbc9d`) is the read path; cache busting must compose with that route.
- **Stage versioning (Q4 lock)** means a stage's input fields may change between code versions; the
  field-to-stage map must be version-aware or rebuilt on stage-version bump.
- **Frontend stack:** React 19 + Vite + TS + TanStack Query + Konva + Tailwind + shadcn/ui (Radix);
  no new heavy deps for live updates.
- **Frontend file layout** mirrors the existing `PageWorkbench` composition; new components land
  alongside `StageChainRail`.

## Decision

Four concurrent UI pieces, each backed by a thin server contract:

1. **Polished stage-chain rail.** 22 chips, one per stage, in DAG order. Each chip shows: status
   pill (`clean`/`dirty`/`running`/`failed`/`not-applicable`/`not-run`), inline thumbnail of the
   stage's output when present, and a click-to-select handle. Replaces the M2 debug panel.

2. **Side-by-side artifact viewer.** Two `Stage: [▼]` selectors (`Stage`, `Compare with`). The two
   artifacts stream from the artifact endpoint and render at the same scale. Default `Compare with`
   is the immediate upstream stage. The selectors offer all stages with `status ∈ {clean, dirty}`
   (artifact present).

3. **Stage-controls panel.** Backed by a backend-served field-to-stage map (`GET
   /api/data/pipeline/stages/{stage_id}/fields` returns the `ResolvedPageConfig` field names the
   stage reads). Renders `Apply` + `Run this stage` buttons. `Apply` mutates `ResolvedPageConfig` on
   the page; `Run` calls the existing stage-run endpoint.

4. **SSE for stage transitions.** New endpoint `GET /api/data/projects/{id}/pages/{idx0}/events`
   streams `stage-status` and `stage-progress` events. Frontend subscribes via `EventSource`;
   TanStack Query cache is invalidated on transition events so cross-tab consistency emerges from
   query refetch.

**Cache-busting:** artifact URLs include `?v=<page_stages.last_run_at>` (RFC 3339 timestamp). A
re-run mutates `last_run_at` → URL changes → browser fetches fresh bytes.

## Contract / Acceptance

- **Chip rail:** opening a fresh page shows 22 chips in DAG order with the correct initial status
  (`not-run` everywhere except `ingest_source`/`thumbnail` which the project pipeline already ran).
- **Click-to-select:** clicking a chip with `status ∈ {clean, dirty}` updates the `Stage` selector
  and the viewer pane. Clicking `not-run`/`not-applicable` is a no-op (or shows a tooltip).
- **Compare:** opening `threshold` auto-selects `grayscale` as the compare; both images render at
  full image resolution side-by-side.
- **Stage-controls Apply+Run:** changing `threshold_level` from `Otsu auto` → `160` → `Apply + Run`
  flickers the chip `running` → `clean`, the viewer swaps to the new output, and downstream chips
  flip `dirty` — all without a page reload, within 2s.
- **Cross-tab SSE:** in tab A, run a stage; tab B observes the chip statuses transition live (no
  manual refresh).
- **Cache-busting:** after a re-run, the artifact `<img src>` URL differs from the prior URL by its
  `?v=` parameter; the browser fetches the new image.
- **Field-to-stage map endpoint:** returns a deterministic field list per stage; the list matches
  what the stage's `STAGE_IMPL[stage_id]` actually reads from `ResolvedPageConfig` (mismatch = bug).
- **Backwards compatibility:** M4 migration of pre-M1 projects still works (chip rail correctly
  shows every stage as `dirty`).

## Trade-offs considered

- **SSE vs WebSocket vs polling.** WebSocket is bidirectional (overkill); polling is wasteful at the
  2s budget. SSE is the right shape: one-way server-push, EventSource is built into the browser,
  reconnect-on-error is automatic.
- **Field-to-stage map: backend-served vs frontend-hardcoded.** Frontend-hardcoded duplicates source
  of truth and rots on stage-version bumps. Decided: backend-served via a new endpoint.
- **Cache-busting: `last_run_at` vs `input_hash`.** `input_hash` would also catch upstream changes
  that don't bump `last_run_at`, but `last_run_at` is bumped on every successful write so it's
  sufficient for cache invalidation. `input_hash` is reserved for content-addressable use cases.
- **Thumbnails: on-demand vs pre-generated.** Pre-generating at stage-write time costs disk and
  write latency; on-demand at artifact-serve time costs CPU at view time but composes with the
  existing `thumbnail` stage's logic. Decided: pre-generated per stage (the per-stage thumbnail uses
  the same path as the existing `thumbnail` stage, just scoped to the stage output).
- **Compare-with default: previous-stage vs same-stage on another page vs none.** Previous-stage is
  the highest-utility default for the "why did this regression happen?" workflow; users can pick
  something else from the selector.

## Consequences

- **Backend:** one new endpoint (`/api/data/pipeline/stages/{stage_id}/fields`), one new SSE
  endpoint (`/api/data/projects/{id}/pages/{idx0}/events`), one tweak to the artifact endpoint
  (`?v=` cache buster — already wired via `last_run_at`).
- **Frontend:** the M2 debug rail is replaced; the workbench page composition gains `ArtifactViewer`
  and `StageControlsPanel` components. SSE wiring lives in a small `useStageEvents(projectId, idx0)`
  hook.
- **Test surface:** Playwright e2e for the workbench needs a multi-tab variant to assert SSE
  cross-tab updates; vitest coverage for the field-to-stage map + cache-busting logic.
- **Field-to-stage map must stay in sync** with `STAGE_IMPL[stage_id]`'s actual reads — covered by
  an integration test that introspects each stage's `read_fields` declaration.
- **Cleanup tax:** the M2 debug rail's UI code is deleted in M3, not M6.
- **Performance:** 22 chips × thumbnails could be heavy; lazy-load thumbnails as chips enter
  viewport.

## Open questions

- **Field-to-stage map source of truth.** Should the map be derived from a `read_fields` declaration
  on each `STAGE_IMPL[stage_id]` registration, or from a separate `stage_metadata.py` file?
  **Flagged for CT review** — recommend `read_fields` declaration on registration so adding a stage
  automatically updates the map.
- **SSE channel scope.** Per-page (current proposal) vs per-project. Per-project lets the JobsPage
  subscribe to one stream and react to any page's transition; per-page is simpler and tighter.
  **Flagged for CT review** — recommend per-page for M3; project-level subscription can be added in
  M5.
- **Thumbnail pre-generation strategy.** Currently the M2 chip rail uses no thumbnails. Should the
  M3 polished rail (a) require all stages to emit a thumbnail at write time, or (b) lazy-generate
  from the artifact on first chip render? **Flagged for CT review** — recommend (a) for predictable
  bandwidth.
- **Stage-controls panel write semantics.** When the user clicks `Apply` without `Run`, does the
  page's `ResolvedPageConfig` mutate immediately (and dirty all downstream stages that read those
  fields), or only on `Run`? **Flagged for CT review** — recommend `Apply` writes config + cascades
  dirty; `Run` is a separate action.
- **Dirty visual treatment during a live run.** When chip X transitions to `running` and downstream
  Y, Z are getting marked `dirty` by the eager cascade, what's the correct sequence the rail shows
  (X-running then Y/Z-dirty after X-clean, or all three transitions visible simultaneously)?
  **Flagged for CT review** — recommend simultaneous.

## References

- Roadmap: `pd-prep-for-pgdp/docs/08-roadmap.md` §M3 (lines 312–367)
- Long-form pipeline spec: `pd-prep-for-pgdp/docs/specs/pipeline-task-model.md` §Workbench UX
- Pipeline-task-model design (this spec set): `2026-05-11-pipeline-task-model-design.md`
- M2 chip rail commit: `8af4f15` (StageChainRail in PageWorkbench)
- M2 artifact endpoint commit: `55dbc9d` (GET stage artifact route)
- Parent spec issue (retro-demoted): #9
- This spec's issue: #44
