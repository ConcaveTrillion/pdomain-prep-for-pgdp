# 08 — Roadmap

The build has moved through 22 iterations. Each iteration was small, TDD-led
where possible, and ended with a green test suite. Full per-iteration history
is in `~/.claude/projects/-workspaces-ocr-container-pd-prep-for-pgdp/memory/project_state.md`.

This roadmap is the **forward** view, organised by priority.

---

## P0 — needed for a real first deploy

### 1. Modal app S3 wiring

**File:** `src/pd_prep_for_pgdp/adapters/gpu/modal_app.py`

`process_page` / `run_ocr` / `run_batch` currently raise NotImplementedError.
They need to:

1. Receive an S3-storage config (bucket + region) — either through
   environment in the Modal container or a wrapped storage adapter.
2. Read the source bytes from S3 inside the function.
3. Call `core.pipeline.process_page_cpu` (or a CUDA variant once
   `cupy_processing` is wired) for the actual processing.
4. Write outputs back to S3.
5. Return the spec-04 `ProcessPageResponse` shape.

`ModalBackend` (the dispatcher side) is fully tested via the fake module
trick. The blocker is the **Modal-side** function bodies + access to a real
account for an end-to-end test.

**Acceptance:** `modal deploy adapters/gpu/modal_app.py` then a real
`process-page` request through `ModalBackend` writes a PNG to S3.

### 2. Postgres adapter

**File:** `src/pd_prep_for_pgdp/adapters/database/postgres.py` (doesn't
exist yet).

Mirror the SQLite shape: every Pydantic model lives in a JSON column;
`pages` is keyed on `(project_id, idx0)`; `jobs` indexed on
`(owner_id, created_at DESC)`. Use SQLAlchemy + psycopg.

**TDD plan:** add a `db` fixture factory that yields either `SqliteDatabase`
or `PostgresDatabase` (skipping postgres when unavailable), then parametrise
the existing `test_assign_prefixes.py`, `test_job_runner.py`, etc. over both.

### 3. install.sh end-to-end exercise

We've authored `install.sh`/`install.ps1`/`Makefile.install` but never run the
curl-pipe-sh path in a clean shell with internet access. Worth a 10-minute
session to confirm `uv tool install git+...@<tag>[cuda] --extra-index-url ...`
actually resolves and the resulting `pgdp-prep` command works.

### 4. CI container push

`.github/workflows/release.yml` builds the managed-mode container on tag
push but doesn't push to a registry. User to wire ECR (or GHCR) credentials.

---

## P1 — UX completeness

### 5. Per-page batch_process_pages progress

**File:** `src/pd_prep_for_pgdp/core/job_runner.py:_run_batch_pages`

Today it reports overall ok/err only. Should emit per-item progress events
through `events.publish` so the workbench / RunPipelinePanel can show "page
12 of 400" rather than just "running".

Pattern is set by ingest (iteration 22): add a `progress_cb` to the
backend `run_batch` API, propagate to the runner, the runner calls
`_update_progress`. ~50 LOC + a TDD test mirroring `test_ingest_progress.py`.

### 6. OcrWord bbox highlight on TextReviewPage

The `OcrWord` shape (with `bounding_box`) is already in the OCR response.
TextReview doesn't yet visualise it. Konva canvas overlay: clicking a word
in the textarea highlights its bbox over the page image; clicking a bbox
selects the word.

### 7. Per-page text diff after re-OCR

When the user clicks "Re-OCR this page" in TextReview, show the diff
between the prior text and the new text inline (a `react-diff-view`-style
component or a hand-rolled split-line diff). Helps reviewers see what
changed from layout-aware reorganization.

### 8. Source preview before ingest

In the create-project flow, after the zip is uploaded but before ingest
runs, show a thumbnail strip of the first ~10 page images. Helps the user
catch wrong-zip mistakes early.

### 9. Vitest + msw for the SPA

Blocked on npm in this devcontainer. Once available, port the
create-project flow, the page-tagger grid bulk actions, and the workbench
drag-create flow into Vitest tests with msw mocking the FastAPI routes.

---

## P2 — Frontend polish

### 10. Konva Transformer rotate + flip

Currently `rotateEnabled=false`, `flipEnabled=false`. Spec 06 doesn't ask
for them, but proofers occasionally need to fix scanner-frame skew that
falls outside the auto-deskew range; expose rotate handles for the rare case.

### 11. JWT login state in nav with profile dropdown

`AuthBadge` shows the JWT `sub` claim + Sign-out today. Add a tiny dropdown
with email (from the JWT `email` claim if present), API token expiry, and
a "Refresh token" item.

### 12. Project archive (soft-delete)

`DELETE /projects/{id}` is hard-delete today. Add `archived: bool` to
`Project`; archived projects hidden from the default list, surfaced via a
filter toggle.

### 13. Search across pages

For very large books (>500 pages), let the user search the OCR text. Needs
a `pages.ocr_text` index column or full-text search. SQLite FTS5 is fine
for local; Postgres has built-in TS.

---

## P3 — Pipeline depth

### 14. CUDA path (LocalBackend)

Spec 04 GPU path. Mirror `process_page_cpu` using
`pd_book_tools.image_processing.cupy_processing` primitives + nvImageCodec
for source decode. The orchestration shape is identical; the primitives
differ. Behind a `[cuda]` extra so the wheel install stays slim.

### 15. Shared GPU container backend

`SharedContainerBackend` is a placeholder. Implementation: an HTTP client
pointing at a long-running `pgdp-prep --mode gpu_worker_only` ECS task with
per-tenant authentication. Spec 09 §"Backend 2".

### 16. Job retry with payload override

`POST /jobs/{id}/retry` copies the original payload verbatim. Sometimes you
want to retry with different `page_idxs` or a tweaked confidence threshold.
Accept an optional `payload_override` body field.

### 17. Spec-01 off-by-one in `compute_prefix`

Logged in iteration 1. The spec's loop `range(start, min(idx0, end+1))` is
empty when `idx0 == start`, so the first frontmatter page is `f000` instead
of `f001` despite `frontmatter_page_nbr_start=1`. Implementation matches
spec verbatim; needs a user decision on whether the spec or the field name
is wrong, then a one-line fix + a test update.

---

## P4 — Operations / observability

### 18. Structured logging

The codebase uses `logging.getLogger(__name__)` everywhere but the format is
default. Switch to JSON logs with request-id correlation for managed mode.

### 19. Health check endpoint

`GET /healthz` returning `{status, gpu_backend, dispatcher, db_reachable}`.
Useful for ECS / k8s liveness.

### 20. OpenAPI codegen

Once npm is available, run `make openapi-export` to replace the
hand-written `frontend/src/api/types.ts` with a generated file. Add a CI
check that fails the build if the committed file diverges from
`/openapi.json`.

### 21. Memory pruning revisit

`memory/project_state.md` was pruned at iteration 11 (collapsed iterations
1-7 into a table). It's grown again. Fold older "Done" sections into the
table once they're stable.

---

## P5 — Stretch

### 22. PDF export

PGDP packages don't need PDFs, but some users want them as a sanity-check
artefact alongside the zip.

### 23. Multi-user permissions

Spec 00 §"stretch goal" says the architecture doesn't block multi-user.
Today every route filters by `user.user_id`. Needs an "owner_id" filter on
the page tagger that respects the JWT identity, plus per-project sharing.

### 24. Internationalisation

The UI is English-only. The OCR pipeline is language-agnostic via DocTR;
the SPA strings would need an i18n layer (react-intl or similar).

---

## How to pick up

1. Read `docs/01-overview.md` (this directory) for the high-level shape.
2. Read the relevant spec for whatever layer you're touching.
3. Check `~/.claude/projects/-workspaces-ocr-container-pd-prep-for-pgdp/memory/project_state.md`
   "Next up" — that's the live work queue, kept in sync with this file but
   without the priority structure.
4. TDD-first when possible; the test recipe is in `docs/07-testing.md`.
5. Update both this roadmap **and** `project_state.md` when you finish
   something.
