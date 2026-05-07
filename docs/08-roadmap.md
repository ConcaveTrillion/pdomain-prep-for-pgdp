# 08 — Roadmap

> Shipped items live in `08-roadmap-shipped.md` — kept out of this file
> so the active roadmap stays focused on open work.

This roadmap is the **forward** view, organised by priority. Shipped
work is in `08-roadmap-shipped.md`; per-iteration history lives in
`git log`.

**Local-first priority (2026-05-07):** the user-facing punch list below
focuses on the local solo / self-hosted-team experience using the
SQLite + filesystem + CPU shape. Everything that requires cloud
infrastructure (Postgres, Modal/S3, registry pushes, install-pipe
verification on a clean network) is parked under "Deferred — remote /
cloud mode" at the bottom of this file. Revisit those once the local
flow is fully shipped.

---

## P0 — local-mode user flow gaps

_All P0 local-mode UX items shipped — see `08-roadmap-shipped.md`._
_§L1 (port auto-select + persistence + in-UI URL display) and §L2_
_(`make run`/`make run-cpu`) are complete. Next user-visible-progress_
_candidates live under P1 / P2 below. Cloud/remote-mode items are_
_parked under "Deferred — remote / cloud mode" at the bottom._

---

## P0.5 — Pipeline task-model refactor (canonical local-mode work)

**Spec:** [`docs/specs/pipeline-task-model.md`](specs/pipeline-task-model.md)
(draft 2026-05-07).

User directive (2026-05-07): the current row-based pipeline (ingest /
thumbnails / batch_process_pages / batch_extract_illustrations /
batch_ocr / batch_text_postprocess / build_package) is too coarse-
grained. `batch_process_pages` is a 14-sub-step monolith
(`core/pipeline/process_page.py`); the user wants each sub-step to be
an individually runnable, individually inspectable stage with dirty
propagation across a DAG. The spec proposes a `page_stages` table,
per-stage artifact storage, and a workbench artifact viewer.

**Decisions Q1–Q7 — Locked (2026-05-07).** See spec §"Open questions —
Locked (2026-05-07)" for the full table; in summary:

+ Q1 → normalised `page_stages` SQLite table.
+ Q2 → eager dirty propagation.
+ Q3 → checkpoint-only artifact persistence + `PGDP_FULL_STAGE_ARTIFACTS=1`
  debug switch (M1 must not preclude; switch may land in M2).
+ Q4 → manual `stage_version` registry in M2.
+ Q5 → `STAGE_IMPL[stage_id][device]` registry; LocalBackend becomes a
  device-chooser, in M2.
+ Q6 → splits stay as configuration to `ocr_crop` (no new DAG nodes) in M2.
+ Q7 → `text_review` modelled as a gate stage; `build_package` gates on
  `require_text_review` (default off in M2).

**Memory-resident execution model added 2026-05-07.** The per-page
stage DAG operates on in-memory image objects during a run; disk
I/O is reserved for checkpoint persistence (off the critical path
via a bounded deferred-write executor) and partial-rerun lazy loads.
This impacts **M2 runner design** (must include a refcount-driven
in-memory cache + bounded deferred-write executor) and **M3 workbench**
(remains purely a disk read — does not require a live in-memory
DAG run). New questions Q8 (deferred-write concurrency cap), Q9
(failure-mode status mapping), and Q10 (canonical in-memory
artifact format) are open in the spec and must be locked before
M2 runner work begins. M1 (schema + DAG enumeration) remains
unblocked because it touches neither the runner nor the workbench.

M1 is unblocked.

**Milestones:**

+ **M1 — Schema + DAG enumeration.** Add `page_stages` table + indexes
  to `SqliteDatabase`. Land a `core/pipeline/dag.py` module with the
  stage registry, dependency map, and `descendants()` helper. No UI,
  no runner changes. Tests: schema round-trip, topological order,
  descendants are correct for every node.
+ **M2 — Per-page stage runner backend + dirty propagation.** Each
  stage gets a `STAGE_IMPL[stage_id][device]` callable. New
  `POST /api/gpu/page-stage` endpoint with `mode ∈ {single, from, dirty}`.
  Eager dirty cascade on rerun. Stage-version registry. Collapse
  `LocalBackend` to device-chooser. Old endpoints
  (`/api/gpu/process-page`, `/api/gpu/run-ocr-page`) become thin
  shims onto the new endpoint.
+ **M3 — Workbench artifact viewer.** Per-page route shows the stage
  chain with status pills + per-stage artifact thumbnails + side-by-
  side compare. Stage-controls panel filters
  `ResolvedPageConfig` fields by which stage reads them. SSE updates
  per stage transition.
+ **M4 — Migration of existing projects.** Lazy-migrate on first
  access: synthesise `page_stages` rows from legacy `processing_status`,
  with `artifact_key` set only for stages whose legacy outputs already
  exist on disk. Add `pgdp-prep migrate-projects --rebuild` for the
  opt-in force-rebuild path.
+ **M5 — Project-level orchestration fan-out.** New
  `JobType.project_run_stage_all_pages` and `project_run_dirty` that
  dispatch per-page stage tasks under the hood. Existing
  `batch_process_pages` etc. job rows continue to run via a
  compatibility shim that translates them to the new model.
+ **M6 — Cleanup.** Remove the deprecated `batch_*` `JobType` values,
  the old endpoints, and `process_page_cpu`'s monolithic body (now an
  imperative composition of the stage registry callables for the
  project-level "run everything CPU" code path).

**Acceptance for the whole sequence:** opening a page in the workbench
shows a stage chain with intermediate artifact images for each
checkpoint stage. Re-running `threshold` on a page marks `invert`
through `text_review` dirty; `build_package` skips that page until
`page.run_dirty(idx0)` brings it back to clean.

---

## P1 — UX completeness

### 9a-followup. Word-delete editor — undo/soft-delete schema decision

§9 (Vitest + msw) and §9a (word-delete editor: backend, frontend v1,
marquee bulk-select, a11y polish, generated-types swap) all shipped —
see `08-roadmap-shipped.md`. One follow-up remains and is **blocked on
a user schema decision**:

+ **Undo / soft-delete strategy.** The v1 endpoint hard-rewrites
  `<root>.words.json` + `<root>.txt`, so honest single-level undo
  needs either (a) a server-side `OcrWord.deleted: bool` flag with a
  flip-restore endpoint and `remaining_words` filtered to non-deleted
  rows, or (b) a client-side debounced commit window (e.g. five-second
  Undo banner that only fires the DELETE after dismissal). Either
  layers cleanly onto the existing wire contract — `remaining_words`
  already lets the client be agnostic about server strategy.

A second follow-up — a five-minute manual marquee runtime smoke-test
in `make frontend-dev` to exercise the Konva pointer-capture preview
rect — is tracked in agent memory and shipped in any tick that already
has a dev server running; not appropriate for an overnight loop.

---

## P2 — Frontend polish

### 10. Konva Transformer rotate + flip

Currently `rotateEnabled=false`, `flipEnabled=false`. Spec 06 doesn't ask
for them, but proofers occasionally need to fix scanner-frame skew that
falls outside the auto-deskew range; expose rotate handles for the rare case.

### 13. Search across pages

For very large books (>500 pages), let the user search the OCR text. Needs
a `pages.ocr_text` index column or full-text search. SQLite FTS5 is fine
for local; Postgres has built-in TS.

### 13a. Adopt shadcn/ui + Radix and close the spec/code divergence

`specs/00-overview.md:57,126` and `specs/03-ui-layout.md:5,404` name
shadcn/ui (Radix-backed) as the intended component library.
**All major library swaps shipped** (see `08-roadmap-shipped.md` §13a
steps 1, 1b, 2, 3): Radix Dialog + AlertDialog wrappers retired the
hand-rolled ProjectListPage modal + delete confirm; `sonner` +
`<Toaster>` retired the inline red error bodies; `vite-tsconfig-paths`
gave us `@/*` aliases for the deepening tree; `react-hotkeys-hook`
folded the raw `window.addEventListener("keydown", ...)` in
TextReviewPage into a hook with built-in form-tag scoping.

Remaining open work (opportunistic, pick whichever pairs with the
next slice that touches its surface):

1. **More Radix primitives** for `Tabs`, `Select`, `Popover`,
   `Tooltip`. The `Dialog` and `AlertDialog` primitives in
   `components/ui/` are the template — install the relevant
   `@radix-ui/react-*`, write a thin wrapper, swap in callers. No
   active surface forces the swap yet; pick when one comes up.

---

## P3 — Pipeline depth

### 14. CUDA path (LocalBackend) — primitives only

**Status (2026-05-07):** `LocalBackend` is no longer a NotImplementedError
stub — it now subclasses `CpuBackend`, which means the CPU pipeline runs
on a CUDA host with DocTR/PyTorch automatically picking up `cuda:0`. So
end users with a GPU get GPU-accelerated OCR today via the same code
path as CPU users. What's still open is the Step 4 image-processing
fast-path: replace cv2/numpy with
`pd_book_tools.image_processing.cupy_processing` primitives + nvImageCodec
for source decode. Orchestration shape is identical; only the inner
primitives change. Behind a `[cuda]` extra so the wheel install stays
slim.

### 15. Shared GPU container backend

`SharedContainerBackend` is a placeholder. Implementation: an HTTP client
pointing at a long-running `pgdp-prep --mode gpu_worker_only` ECS task with
per-tenant authentication. Spec 09 §"Backend 2".

### 16. Thumbnail nvjpeg / DALI GPU path (future)

**Status (2026-05-07):** **deferred.** Step 2 thumbnail generation is
CPU-bound JPEG decode + resize + encode. The current shipped approach
parallelises across cores via `concurrent.futures.ProcessPoolExecutor`
(default `max_workers=os.cpu_count()`, override `PGDP_THUMBNAIL_WORKERS`,
1 disables); see `_make_thumbnail_bytes` and the pool wiring in
`core/ingest.generate_thumbnails`. That is the right default — the
work is trivially data-parallel and each worker stays in its own cv2
process, so there is no shared-state contention.

A GPU fast path (NVIDIA **nvjpeg** for decode/encode, optionally
**DALI** for the resize pipeline) is _not_ a free win on the
thumbnail workload. nvjpeg shines when many images stay resident on
the GPU for downstream work; here each thumbnail is a one-shot
decode → resize → encode → return-to-host. The per-image PCIe
round-trip (host→device for source bytes, device→host for the
encoded JPEG) typically washes the kernel speedup unless the batch
is large enough to amortise it via streams, and even then the
encode is the bottleneck and `nvjpegEncoder` is finicky about
chroma subsampling and quality knobs matching cv2 output.

Revisit only if profiling on a real book (≥500 pages, GPU host)
shows the CPU pool path becoming the dominant Step-2 cost _after_
storage I/O. Implementation sketch when picked up: a
`thumbnails_backend = "cpu" | "nvjpeg"` adapter selector that lives
alongside `GpuBackend`; nvjpeg path gated behind a `[cuda]` extra
the same way Step 4's CUDA primitives are (#14).

### 17. Spec question: `compute_prefix` first-frontmatter-page numbering

Logged in iteration 1. The spec's loop `range(start, min(idx0, end+1))` is
empty when `idx0 == start`, so the first frontmatter page resolves to
`f000` instead of `f001` despite `frontmatter_page_nbr_start=1`.
Implementation matches the spec verbatim — `test_compute_prefix_basic_numbering`
asserts the current `f000` behavior, so this is **not a latent bug**: any
change to `f001` would be an _intentional_ rewrite of the spec, and the
asserting test would need to be updated in the same change.

This entry tracks an open spec question, not a fix-on-sight bug. The
decision is whether (a) the field name `frontmatter_page_nbr_start=1`
should imply `f001` and the spec loop is wrong, or (b) the `f000`-from-1
behavior is intentional zero-based numbering and the field name / docs
should be clarified. A user decision unblocks the change; either path is
a one-line code (or spec) edit plus a deliberate test update.

---

## P5 — Stretch

### 23. PDF export

PGDP packages don't need PDFs, but some users want them as a sanity-check
artefact alongside the zip.

### 24. Multi-user permissions

Spec 00 §"stretch goal" says the architecture doesn't block multi-user.
Today every route filters by `user.user_id`. Needs an "owner_id" filter on
the page tagger that respects the JWT identity, plus per-project sharing.

### 25. Internationalisation

The UI is English-only. The OCR pipeline is language-agnostic via DocTR;
the SPA strings would need an i18n layer (react-intl or similar).

---

## Deferred — remote / cloud mode (revisit after local is fully shipped)

The following items were originally tracked as P0 but are all
prerequisites for the cloud / multi-tenant deployment shape, not the
local solo / self-hosted-team flow. They are parked here intentionally
until the local-mode user experience is end-to-end coherent — picking
them up early forces design tradeoffs around adapters that the local
shape doesn't actually exercise.

### D1. Modal app S3 wiring (was P0 #1)

**File:** `src/pd_prep_for_pgdp/adapters/gpu/modal_app.py`

`process_page` / `run_ocr` / `run_batch` raise NotImplementedError.
Needs S3 storage config wiring, source-bytes read inside the Modal
function, a call into `core.pipeline.process_page_cpu` (or the future
CUDA variant), output write-back, and a spec-04 `ProcessPageResponse`
return shape. `ModalBackend` (dispatcher side) is fully tested via the
fake-module trick; the blocker is **Modal-side** function bodies + a
real account for end-to-end tests.

**Acceptance:** `modal deploy adapters/gpu/modal_app.py`, then a real
`process-page` request through `ModalBackend` writes a PNG to S3.

### D2. Postgres adapter — live-DB integration tests (was P0 #2)

**File:** `src/pd_prep_for_pgdp/adapters/database/postgres.py` —
scaffold shipped (commit `77072c6`, mirrors `SqliteDatabase` exactly:
JSON/JSONB-per-record, `pages` keyed on `(project_id, idx0)`, `jobs`
indexed on `(owner_id, created_at DESC)`; raw async psycopg, no ORM).
`tests/test_postgres_adapter.py` covers URL validation, the
`put_pages([])` no-op contract, and the bootstrap-friendly error when
the `[postgres]` extra is absent — all class-direct tests
`importorskip` psycopg cleanly.

**Still open (when revived):**

1. Wire a Postgres service into the dev container (or a CI service) so
   the existing direct-class tests stop skipping.
2. Add a parametrised `db` fixture factory yielding `SqliteDatabase`
   **or** `PostgresDatabase` (skip-postgres when the service is
   unavailable), then run existing `test_assign_prefixes.py`,
   `test_job_runner.py`, `test_project_archive.py`, etc. over both.
3. Decide bootstrap default: empty `database_url` currently falls back
   to SQLite. Managed-mode container should require an explicit
   `postgres://` URL — surface a clearer error when neither is set.

The scaffold is preserved on `main`; nothing to revert when this is
revived.

### D3. install.sh end-to-end exercise (was P0 #3)

`install.sh` / `install.ps1` / `Makefile.install` are authored but the
curl-pipe-sh path has never been exercised in a clean shell with
internet. Needs ~10 min to confirm
`uv tool install git+...@<tag>[cuda] --extra-index-url ...` resolves
and the resulting `pgdp-prep` command works. Note: the long-term
release strategy is a self-hosted PEP 503 index
(`ConcaveTrillion/pd-index`); install.sh has the same latent
wheel-METADATA bug pre-fixed in pd-ocr-cli — see agent memory
`release_strategy_self_hosted_index.md` before touching this.

### D4. CI container push (was P0 #4)

`.github/workflows/release.yml` builds the managed-mode container on
tag push but doesn't push to a registry. User must wire ECR (or GHCR)
credentials.

---

## How to pick up

1. Read `docs/01-overview.md` (this directory) for the high-level shape.
2. Read the relevant spec for whatever layer you're touching.
3. Pick the lowest-numbered open item in this file (P0 first); shipped
   items live in `08-roadmap-shipped.md` for context. **Skip the
   "Deferred — remote / cloud mode" section** unless the user
   explicitly revives it — local mode is the priority.
4. TDD-first when possible; the test recipe is in `docs/07-testing.md`.
5. When you finish an item, **move it out** of this file into
   `08-roadmap-shipped.md` with a condensed summary + commit SHAs.
   Don't leave shipped items in this file with a "done" flag.
