# 08 — Roadmap

> Shipped items live in `08-roadmap-shipped.md`. Locked architecture
> decisions live in `architecture-decisions.md`. This file is the
> **forward** view of open work.

**Local-first priority (locked 2026-05-07 — see AD-4 in
`architecture-decisions.md`):** all P0 / P1 / P2 work below targets
the SQLite + filesystem + CPU shape. Cloud / remote items are parked
under "Deferred — remote / cloud mode" at the bottom.

**Reference for finished work:**

- Pipeline task-model M1–M6 — fully shipped (see
  `08-roadmap-shipped.md` §P0.5).
- §13a Radix primitives — fully shipped.
- §9a soft-delete / restore — shipped.
- §13 search across pages — shipped (#76).
- §10 Konva rotate — shipped (#100); flip is **blocked on CT design**
  (see P2 below).

---

## P0 — Daily-use blockers

Items that prevent a user from completing a real book end-to-end in
`make run` today.

### P0.1. RunPipelinePanel is stale — submits to deleted `POST /api/gpu/jobs`

`frontend/src/pages/ProjectConfigurePage.tsx` line ~696 (`STEPS`
constant) and `RunPipelinePanel` (~725) submit `batch_process_pages`,
`batch_ocr`, `batch_text_postprocess`,
`batch_extract_illustrations`, `build_package` JobTypes to
`POST /api/gpu/jobs`.

After M6 (2026-05-15) `JobType.batch_*` is gone and `POST /api/gpu/jobs`
returns 405. The 5-row "Run pipeline" panel in the Pipeline tab is a
dead UI surface — pressing Run on any of the first four rows fails
silently.

**Pass criterion:** in `make run`, on the Pipeline tab, every Run
button either (a) works end-to-end, or (b) is removed. The
`build_package` row in particular needs to submit to
`POST /api/data/projects/{id}/build-package` (which exists and is
tested).

### P0.2. No "Download package" UI

After `build_package` completes, there is no UI affordance to
download the resulting zip. The `GET /api/data/projects/{id}/assets/download-url`
endpoint exists but no page links to it.

**Pass criterion:** in `make run`, after `build_package` completes, the
user sees a "Download package" link / button that triggers the
download in the browser.

### P0.3. Folder upload (zip-only ingest blocks Internet Archive workflow)

`ProjectListPage` create-project modal only accepts `.zip` /
`application/zip`. Many proofers work from a folder of PNGs (the
typical Internet Archive download is a folder of `.jp2` or `.png`,
not a zip). Today the user has to zip the folder client-side first.

The backend ingest jobs handle `source_type: "zip"` exclusively; a
folder upload requires either client-side zipping in the browser, or
a new `source_type: "folder"` path that accepts multipart-uploaded
files.

**Pass criterion:** in `make run`, the user can drop a folder of
PNGs / JPGs onto the create-project modal and the project ingests.

---

## P1 — UX completeness

### P1.1. Page reorder UI + endpoint

There is no way to fix page-order mistakes (e.g. a scan came in
out-of-order, or the user wants to insert / remove a page between
ingest and build_package). No backend endpoint, no UI.

Sketch: `PATCH /api/data/projects/{id}/pages/{idx0}` already exists
for per-page metadata; add a `move_to_idx0` or `reading_order`
mutation, and a drag-handle in the Pages tab `PageRow`. Splits
already have a `reading_order` column — extend it project-wide.

### P1.2. Crop / rotate review pass before OCR

The auto-deskew + initial_crop stages don't always get it right. The
workbench shows the artifact viewer per-stage, but there's no
batch-level "review every page's `canvas_map` artifact" affordance
short of clicking through every page individually.

Sketch: a "Review crops" project-level page that grids the
`canvas_map` thumbnails for every page, lets the user click into the
ones that look wrong, and surfaces the per-page workbench Konva
rotate handle (already shipped §10).

### 9a-followup. Word-delete editor — undo / soft-delete schema

§9a hard-delete shipped (`DELETE /api/data/projects/{id}/pages/{idx0}/words`
rewrites `<root>.words.json` + `<root>.txt`). §9a soft-delete +
restore shipped (`OcrWord.deleted` flag, restore endpoint,
get_page_text overlay filter, 14 tests).

**BLOCKED: needs CT decision** — which Undo strategy to ship to the
TextReviewPage UI:

- (a) wire the existing server-side `deleted: bool` flag into the
  TextReviewPage with a "Restore last delete" / banner-style Undo,
- (b) layer a client-side debounced commit window (5 s Undo banner)
  that delays the DELETE,
- or (c) leave the v1 hard-delete as-is.

Either (a) or (b) layers cleanly onto the existing wire contract —
`remaining_words` already lets the client be agnostic.

---

## P2 — Polish / nice-to-have

### P2.1. Konva Transformer flip

`rotateEnabled` and Rotate toolbar shipped (#100, 2026-05-14).
`flipEnabled=false` remains.

**BLOCKED: needs CT decision** — is horizontal/vertical flip needed
for any real proofing case, or skip it? (Rare; most flip errors
should be handled by the user re-scanning, not by a destructive
client-side flip applied to the proof PNG.)

---

## P3 — Pipeline depth

### P3.1. `compute_prefix` first-frontmatter-page numbering (f000 vs f001)

**BLOCKED: needs CT decision** — is the current `f000` behavior
intentional zero-based numbering (the field name
`frontmatter_page_nbr_start=1` should be clarified to mean "start
at offset 1 within zero-based numbering"), or is it a latent
spec bug and the first frontmatter page should be `f001`?

Current behavior is documented as locked in
`architecture-decisions.md` §AD-5. `test_compute_prefix_basic_numbering`
asserts `f000`. Either path is a one-line code or spec edit plus a
deliberate test update.

---

## P5 — Stretch (post-daily-use)

### S1. PDF export

PGDP packages don't need PDFs, but some users want them as a
sanity-check artefact alongside the zip.

### S2. Multi-user permissions

Spec 00 §"stretch goal" says the architecture doesn't block
multi-user. Today every route filters by `user.user_id`. Needs an
"owner_id" filter on the page tagger that respects the JWT identity,
plus per-project sharing.

### S3. Internationalisation

The UI is English-only. The OCR pipeline is language-agnostic via
DocTR; the SPA strings would need an i18n layer.

---

## Deferred — remote / cloud mode

Revisit only after the local-mode flow above is end-to-end coherent.
None of these are in scope for daily-use rollout.

### D1. Modal app S3 wiring

`src/pd_prep_for_pgdp/adapters/gpu/modal_app.py` — `process_page` /
`run_ocr` / `run_batch` raise `NotImplementedError`. Needs S3
storage config wiring + Modal-side function bodies + a real account
for end-to-end tests.

### D2. Postgres adapter — live-DB integration tests

Scaffold shipped (`adapters/database/postgres.py`); direct-class
tests `importorskip` psycopg cleanly. Reviving requires (1) a
Postgres service in the dev container, (2) a parametrised `db`
fixture factory yielding SQLite **or** Postgres, (3) deciding the
managed-mode default (currently empty `database_url` falls back to
SQLite).

### D3. install.sh end-to-end exercise

`install.sh` / `install.ps1` / `Makefile.install` are authored but
the curl-pipe-sh path has never been exercised in a clean shell.
Note: long-term strategy is the self-hosted PEP 503 index
(AD-10); fix the latent wheel-METADATA bug pre-fixed in pd-ocr-cli
before exercising.

### D4. CI container push

`.github/workflows/release.yml` builds the managed-mode container
on tag push but doesn't push to a registry. Wire ECR / GHCR creds.

### D5. CUDA `STAGE_IMPL` entries

Today every `STAGE_IMPL[stage_id]` only has a `"cpu"` entry. A
real GPU host would benefit from CUDA primitives for the
proofing-chain stages (`grayscale`, `threshold`,
`find_content_edges`, `auto_deskew`, `morph_fill`, `rescale`,
`canvas_map`) backed by `pd_book_tools.image_processing.cupy_processing`,
behind a `[cuda]` extra so the wheel install stays slim. Track as
a slice when the registry is the only call path (already true
post-M6).

### D6. Shared GPU container backend

`SharedContainerBackend` is a placeholder. Long-running
`pgdp-prep --mode gpu_worker_only` ECS task with per-tenant
authentication. Spec 09 §"Backend 2".

### D7. Thumbnail nvjpeg / DALI GPU path

Deferred per AD-9. CPU pool is the right default. Revisit only
after profiling on a real book (≥500 pages, GPU host) shows the
CPU path dominates after storage I/O.

---

## How to pick up

1. Read `docs/01-overview.md` for the high-level shape.
2. Read `architecture-decisions.md` for the locked decisions.
3. Pick the lowest-numbered open item in this file. **Skip BLOCKED
   items unless you have a CT decision in writing.** Skip the
   "Deferred" section unless the user explicitly revives it.
4. TDD-first when possible; the test recipe is in `docs/07-testing.md`.
5. When you finish an item, **move it out** of this file into
   `08-roadmap-shipped.md` with a condensed summary + commit SHAs.
