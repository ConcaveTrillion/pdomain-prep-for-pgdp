# pd-prep-for-pgdp — Architecture Docs

These docs describe **what's actually built**. They complement the design specs
in [`../specs/`](../specs/) (which capture the *target* design).

| Doc | Topic |
|---|---|
| [`01-overview.md`](01-overview.md) | The 30-second tour: what runs where |
| [`02-backend.md`](02-backend.md) | FastAPI app, adapters, settings, lifespan |
| [`03-pipeline.md`](03-pipeline.md) | Steps 0–10, job runner, dispatcher, OCR |
| [`04-frontend.md`](04-frontend.md) | React SPA pages, state, auth |
| [`05-events-and-jobs.md`](05-events-and-jobs.md) | Job events, SSE, in-process priority queue |
| [`06-deployment.md`](06-deployment.md) | Local / self-hosted / managed shapes |
| [`07-testing.md`](07-testing.md) | TDD conventions, test layout, what's covered |
| [`08-roadmap.md`](08-roadmap.md) | What's done + what's next, by priority |
| [`futures/`](futures/) | Future-state design notes (not current milestones) |

## Status snapshot

- **~381 tests collected** in `tests/` — run via `make test` (excludes
  `tests/e2e/`). The Vitest SPA suite (`make frontend-test`) sits alongside
  it with **61+ tests**; both are wired into `make ci`.
- **Backend** is feature-complete relative to specs 01/02/04/05/07/08; the CPU
  pipeline is wired end-to-end (ingest → process_page → ocr → text_postprocess
  → package), with auto-detect + layout-aware OCR via `pd-book-tools`.
- **Frontend** covers every spec-03 page (ProjectList, ProjectConfigure,
  PageWorkbench, TextReview, ReviewQueue, Jobs, Settings, Login). Vitest +
  msw harness landed (roadmap §9); pure-function and wire-level coverage in
  place for `lineDiff`, `wordOffsets`, `marquee`, `api/client`, `api/pages`,
  `api/workbench`, `WordBboxOverlay`, `ProjectListPage`, `TextReviewPage`.
- **Adapters fully wired:** `IStorage` (filesystem + S3), `IDatabase` (SQLite),
  `IAuth` (none / apikey / jwt), `GPUBackend` (CPU + Modal dispatcher).
- **Adapters scaffolded (raise `NotImplementedError`):** Postgres database
  adapter is not yet written (P0 #2), Modal-side function bodies in
  `adapters/gpu/modal_app.py` (P0 #1), `adapters/gpu/local.py` CUDA path,
  `adapters/gpu/shared_container.py`.
- **Operations:** structured logging + request-id correlation
  (roadmap §18), `GET /healthz` liveness probe (§19), CI guard that the
  built wheel contains the SPA bundle (§22) all landed.

## Spec ↔ implementation index

| Spec | Coverage |
|---|---|
| 00 — Overview | Architecture matches; "single FastAPI process" delivered. |
| 01 — Configuration model | `core/models.py`, `core/config_resolver.py`, `core/prefix.py`. |
| 02 — Pipeline steps | `core/ingest.py`, `core/pipeline/{process_page,crop_for_ocr,blank_proof}.py`, `core/text_postprocess.py`, `core/illustrations.py`, `core/packaging.py`. |
| 03 — UI layout | `frontend/src/pages/*.tsx`. |
| 04 — GPU acceleration | `adapters/gpu/{base,cpu,modal_backend,modal_app,local,shared_container}.py`. CPU + Modal scaffold are tested; CUDA + shared-container are scaffolds only. |
| 05 — Illustrations | `core/illustrations.py` + `auto_detect_illustrations` in ingest. |
| 06 — Page workbench | `frontend/src/pages/PageWorkbenchPage.tsx` (Konva + drag-create + drag-resize). |
| 07 — API design | `api/data/`, `api/gpu/`, `api/auth/`, `api/cdn.py`, `api/env_js.py`. |
| 08 — Data models | `core/models.py` (every model from spec 08). |
| 09 — Deployment | `Dockerfile`, `install.sh`, `install.ps1`, `Makefile`, `.github/workflows/release.yml`. |

## How to read these docs

Specs in [`../specs/`](../specs/) are the **source of truth for design**. These
docs are about **the actual code** and may diverge from the spec when an
intentional decision was made; those divergences are called out explicitly.

For a new contributor (or AI assistant), the recommended reading order:

1. [`../CLAUDE.md`](../CLAUDE.md) — quick start
2. [`01-overview.md`](01-overview.md) — high-level shape
3. [`08-roadmap.md`](08-roadmap.md) — what to work on next
4. The spec for whatever layer you're touching, then the docs for that layer
