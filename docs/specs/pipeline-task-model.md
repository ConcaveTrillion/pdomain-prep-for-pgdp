# Pipeline Task Model — granular per-page stages with dirty propagation

> **Status:** draft (2026-05-07). Spec-only — no source code yet.
> Open questions at the bottom; user decisions unblock M1.
>
> **Supersedes (in intent):** the coarse-grained `JobType` set
> (`batch_process_pages`, `batch_extract_illustrations`, `batch_ocr`,
> `batch_text_postprocess`, `build_package`) as the *user-visible*
> pipeline shape. Those job types remain available as fan-out
> orchestrators during M5, then are deprecated in M6.

## Why this exists

Today the user sees seven row-types in the workbench (ingest,
thumbnails, batch_process_pages, batch_extract_illustrations, batch_ocr,
batch_text_postprocess, build_package). `batch_process_pages` is a
monolithic Step 4 (`core/pipeline/process_page.py:42`) that runs 4c → 4o
in one shot. When a single sub-step is wrong (e.g. the auto-deskew
over-rotated; the threshold ate a thin glyph row), the user has no way
to:

1. See the intermediate image after each sub-step.
2. Re-run *just* the affected sub-step.
3. Make downstream sub-steps inherit the corrected upstream artifact
   without rerunning the whole page.

This spec replaces that monolith with a **DAG of named stages**, each
with a typed input/output artifact, persisted state, and a dirty-
propagation rule. The workbench surfaces every stage's artifact and
gives the user "run this stage / run from here / rerun all dirty"
controls.

The orchestration shape is unchanged for headless / batch users: a
project-level "process all pages" task fans out to per-stage page tasks
internally.

---

## Two scopes of task

The current pipeline mixes "operate on the whole project" with "operate
on one page" under a single `JobType` enum. The new model splits them:

### Project-level tasks

Operate on the whole project, or on a stage *across* all pages.

| Task | Replaces | Notes |
|---|---|---|
| `project.ingest` | `JobType.unzip` | Zip / folder ingest. |
| `project.thumbnails` | `JobType.thumbnails` | Step 2 fan-out. |
| `project.run_stage_all_pages(stage_id)` | `batch_process_pages`, `batch_extract_illustrations`, `batch_ocr`, `batch_text_postprocess` | Generic — runs `stage_id` on every page that needs it. |
| `project.run_dirty(stage_filter?)` | (new) | Runs every dirty stage on every page until clean. Optional stage filter narrows the sweep. |
| `project.build_package` | `build_package` | Unchanged; reads only completed page outputs. |
| `project.report` | (new, later) | Project-wide reports (page count by status, error summary, etc.). |

### Page-level tasks

Operate on one page. Each is a single stage execution.

| Task | Notes |
|---|---|
| `page.run_stage(idx0, stage_id)` | Run one stage on one page; mark downstream dirty. |
| `page.run_from(idx0, stage_id)` | Run `stage_id` and all downstream stages serially. |
| `page.run_dirty(idx0)` | Run all currently-dirty stages on this page in DAG order. |

All page-level tasks are also valid as project-level fan-outs (the
project-level form just iterates pages).

---

## Per-page stage DAG

The current `process_page_cpu(source_image_bytes, cfg)` body is a linear
chain (4c→4o). We promote each step to a named stage with an explicit
input artifact name, output artifact name, and dependency list.

Stage IDs are stable strings (used as DB keys, storage path components,
and API query strings). They are versioned via `stage_version`
(see "Stage versioning" under Open Questions).

### Page-level stages

Pre-existing today (already discrete; just naming them):

| Stage ID | Input | Output | Depends on | Code today |
|---|---|---|---|---|
| `ingest_source` | source bytes from upload | `source_image` (the original scan, persisted) | (project.ingest) | `core/ingest.py` |
| `thumbnail` | `source_image` | `thumbnail` (400-px JPG) | `ingest_source` | `core/ingest._make_thumbnail_bytes` |
| `auto_detect_attrs` | `source_image` | `page_type`, `alignment` (recorded on `PageRecord`) | `ingest_source` | `core/auto_detect.py` |
| `auto_detect_illustrations` | `source_image` | `illustration_regions[]` (recorded on `PageRecord`) | `ingest_source` | `core/illustrations.auto_detect_illustrations` |

New, decomposed from `process_page_cpu` (current sub-steps 4c–4o):

| Stage ID | Input | Output | Depends on | Code today |
|---|---|---|---|---|
| `decode_source` | `source_image` (bytes) | `decoded_color` (BGR ndarray; persisted as PNG checkpoint) | `ingest_source` | 4c — `cv2.imdecode` in `process_page.py:88` |
| `initial_crop` | `decoded_color` | `initial_cropped` | `decode_source` | 4d — `crop_edges` |
| `manual_deskew_pre` | `initial_cropped` | `pre_deskewed` | `initial_crop` | 4e — `rotate_image(deskew_before_crop)` |
| `grayscale` | `pre_deskewed` | `gray` | `manual_deskew_pre` | 4f — `cv2_convert_to_grayscale` |
| `threshold` | `gray` | `binary` | `grayscale` | 4g — `otsu_binary_thresh` / `binary_thresh` |
| `invert` | `binary` | `inverted` (text=255) | `threshold` | 4h — `invert_image` |
| `find_content_edges` | `inverted` | `content_bbox` (4-tuple, no image) | `invert` | 4i — `find_edges` |
| `crop_to_content` | `inverted` + `content_bbox` | `content_cropped` | `find_content_edges` | 4j — `crop_to_rectangle` (+ optional `add_whitespace_percentage`) |
| `auto_deskew` | `content_cropped` | `auto_deskewed` | `crop_to_content` | 4k — `auto_deskew` (or pass-through) |
| `morph_fill` | `auto_deskewed` | `morphed` (or pass-through) | `auto_deskew` | 4l — `morph_fill` |
| `rescale` | `morphed` (re-inverted) | `rescaled` | `morph_fill` | 4m — `rescale_image(target_short_side=1000)` |
| `canvas_map` | `rescaled` | `proofing_image` (canonical aspect, PNG bytes) | `rescale` | 4n + 4o — `map_content_onto_scaled_canvas` + `cv2.imencode` |

Then the post-Step-4 chain (each is already a named module, just
formalised):

| Stage ID | Input | Output | Depends on | Code today |
|---|---|---|---|---|
| `ocr_crop` | `proofing_image` | `ocr_image` (one per split, in reading order) | `canvas_map` | `core/pipeline/crop_for_ocr.py` |
| `extract_illustrations` | `source_image` + `illustration_regions` | `hi_res_crops[]` | `auto_detect_illustrations` (and any user edits to `illustration_regions`) | `core/illustrations.extract_illustration` |
| `ocr` | `ocr_image[]` | `ocr_words[]`, raw `ocr_text` | `ocr_crop` | `core/ocr.py` |
| `text_postprocess` | raw `ocr_text` | final `ocr_text` | `ocr` | `core/text_postprocess.py` |
| `text_review` | final `ocr_text` | reviewed `ocr_text` (user-edited) | `text_postprocess` | `PATCH /pages/{idx0}/text` (UI-only stage; "complete" when user marks reviewed) |

`build_package` is **project-level**, not a page stage; it consumes
each page's `text_review` (or `text_postprocess` if review is skipped)
plus `extract_illustrations` outputs.

### Blank-page short circuit

For `page_type ∈ {blank, plate_b, plate_r}` the current code returns
a synthesised blank PNG. In the new model:

+ Stages `decode_source` … `morph_fill` are **skipped** and recorded as
  `not-applicable` (a separate status from `clean`/`dirty`).
+ `rescale` + `canvas_map` are replaced by a single
  `blank_proof_synth` stage that depends on `auto_detect_attrs` (it
  needs `page_type` + `page_h_w_ratio`) and emits `proofing_image`.

The DAG is the same downstream of `canvas_map` / `blank_proof_synth`
(they're the two producers of `proofing_image`).

### `plate_p` page

For `page_type=plate_p` the OCR / text stages are skipped (status
`not-applicable`). `extract_illustrations` does the real work — the
whole page becomes one illustration crop.

### DAG (fan-in/fan-out)

```
ingest_source ─┬─ thumbnail
               ├─ auto_detect_attrs
               ├─ auto_detect_illustrations ─→ extract_illustrations ──┐
               └─ decode_source ─→ initial_crop ─→ manual_deskew_pre   │
                                                          ↓             │
                                                       grayscale        │
                                                          ↓             │
                                                       threshold        │
                                                          ↓             │
                                                       invert ─→ find_content_edges
                                                          ↓             ↓
                                                          └→ crop_to_content
                                                                  ↓
                                                              auto_deskew
                                                                  ↓
                                                               morph_fill
                                                                  ↓
                                                               rescale
                                                                  ↓
                                                            canvas_map ─→ proofing_image
                                                                  ↓
                                                              ocr_crop
                                                                  ↓
                                                                 ocr
                                                                  ↓
                                                          text_postprocess
                                                                  ↓
                                                             text_review ─┐
                                                                          ▼
                                                                 (project) build_package
```

`auto_detect_attrs` also feeds `canvas_map` (page_type / alignment) and
the upstream `find_content_edges` indirectly through resolved config —
but **artifact-level** dependency is only what the algorithm reads as
bytes / numbers. Config changes are handled via the `config_hash`
input-fingerprint (see "Stage versioning"), not via DAG edges; otherwise
every stage would depend on everything that touches `ProjectConfig`.

---

## Memory-resident execution model

> Added 2026-05-07 per user directive. The per-page stage DAG operates
> on **in-memory image objects** during a page-processing run, not
> through disk between every stage. Disk I/O is reserved for
> persistence checkpoints and reruns; it is not on the per-stage
> critical path.

### In-memory by default during a run

When stages 1..N execute as part of a single page-processing pass
(e.g. `page.run_dirty(idx0)`, `page.run_from(idx0, stage_id)`, or a
project-level fan-out's per-page worker), the output of stage K is
held in RAM and passed directly to its DAG-downstream dependents. The
DAG executor maintains a **refcount / last-consumer** scheme keyed by
artifact name: each in-memory artifact's refcount equals the number of
stages in this run that still have it as an unconsumed input. The
artifact may be released only when refcount falls to zero **and** any
deferred persistence (below) has been queued.

### Deferred disk writes

When a stage's output is destined for persistence — i.e. the stage is
in the checkpoint set (Q3) or `PGDP_FULL_STAGE_ARTIFACTS=1` is set —
the write does not block the DAG. The serialized artifact is submitted
to a background thread / executor and the DAG immediately advances to
the next stage on the in-memory copy.

Failures in deferred writes are captured by the executor and surfaced
as a stage-error after the in-memory run completes; they do not block
compute and they do not roll back the page's in-memory state. See Q9
below for status-mapping policy.

### Drop-on-last-consumer

Once an in-memory artifact has been consumed by all of its DAG-
downstream dependents in this run **and** its persistence (if any) has
been queued, the runner drops its reference so the GC can reclaim the
buffer. For a long page-process pass this keeps peak RAM bounded by
the working-set size of the DAG (typically 2–3 active artifacts), not
the cumulative size of the full chain.

### Lazy load on partial / single-stage reruns

When a user invokes "rerun stage K on page Y" from the workbench:

1. Only stage K's input artifacts are loaded from disk — from the
   nearest persisted upstream checkpoint. Earlier stages are not
   re-executed.
2. Stage K runs against those in-memory inputs.
3. Dirty propagation still flags downstream stages (per §Dirty
   propagation), but those reruns — when triggered — also follow the
   memory-resident pattern starting from K's output. They do not
   round-trip through disk between K and K+1.

This means a "rerun K then run dirty" sequence on a single page pulls
checkpoint(K-1) once, then runs K..N entirely in RAM, persisting only
the checkpoint stages off the critical path.

### Workbench artifact viewer

The artifact viewer (per §Workbench UX) reads from disk — from the
persisted checkpoint or, with `PGDP_FULL_STAGE_ARTIFACTS=1`, the full
artifact set. It does **not** trigger or require an in-memory DAG
run; it is a read-after-the-fact view. This decouples "interactive
inspect" from "compute pipeline" so that opening a page in the
workbench costs only object-storage reads.

### Edge cases (open — see Q8/Q9/Q10 below)

The exact bounded-queue size for deferred writes, the failure-mode
status mapping, and the canonical in-memory artifact representation
are deferred to Q8/Q9/Q10 and require explicit user lock before M2
runner work.

---

## Persistence model

> The on-disk schema below describes the **final-rest state** of a
> page's artifacts after a run has completed and any deferred writes
> have flushed. It is **not** the per-stage critical-path state — the
> latter lives only in memory during the run, per §Memory-resident
> execution model. A stage's row in `page_stages` does not appear with
> an `artifact_key` until the deferred write has committed.

### Filesystem layout (under `~/pgdp-projects/<id>/`, via `IStorage`)

Existing keys (preserved):

```
projects/<id>/source/<stem>.<ext>            # ingest_source output
projects/<id>/thumbnails/<stem>.jpg          # thumbnail output
projects/<id>/hi_res/<prefix>_<NN>.<ext>     # extract_illustrations output
projects/<id>/for_zip/<book_name>.zip        # build_package output
```

New per-stage artifact keys (the **checkpoint** stages — see
"Artifact storage" open question for the recommendation; non-checkpoint
stages don't persist images):

```
projects/<id>/stages/<idx0>/<stage_id>/<ext>
  e.g. projects/<id>/stages/0042/threshold/out.png
       projects/<id>/stages/0042/canvas_map/out.png      # == proofing_image
       projects/<id>/stages/0042/ocr_crop/<suffix>.png
       projects/<id>/stages/0042/ocr/words.json
       projects/<id>/stages/0042/ocr/raw.txt
       projects/<id>/stages/0042/text_postprocess/out.txt
```

The existing `processed_image_key`, `pre_ocr_image_key`,
`ocr_image_key`, and the per-output keys on `PageOutput` continue to
exist and are aliases / pointers into the new stage layout
(`canvas_map/out.png`, `ocr_crop/<suffix>.png`, etc.). M4 migration
back-fills them.

`idx0` is zero-padded to 4 digits in the path (sortable on the
filesystem and in `list_prefix` output).

### SQLite schema

**Recommendation:** new normalised `page_stages` table; do not extend the
JSON `body` on `pages` with a stage map. Reason: dirty propagation
needs cheap queries like "give me all dirty stages for project X", and
"mark every downstream stage of (idx0, stage_id) dirty" — both are
single SQL UPDATEs against an indexed table. With JSON-in-`body` the
runner has to read every page row, deserialise, mutate, re-serialise.
At 500 pages × 18 stages = 9000 rows the normalised path is also still
trivially small.

Trade-off explicitly listed in Open Questions §Q1.

```sql
CREATE TABLE IF NOT EXISTS page_stages (
    project_id    TEXT    NOT NULL,
    idx0          INTEGER NOT NULL,
    stage_id      TEXT    NOT NULL,
    status        TEXT    NOT NULL,   -- 'not-run' | 'clean' | 'dirty' | 'running' | 'failed' | 'not-applicable'
    stage_version INTEGER NOT NULL,   -- bumped when the stage's code/algorithm changes
    config_hash   TEXT,               -- hash(resolved-config-fields-this-stage-reads)
    input_hash    TEXT,               -- hash(upstream artifact fingerprints)
    artifact_key  TEXT,               -- IStorage key, NULL if not a checkpoint stage or never-run
    last_run_at   REAL,               -- epoch seconds
    duration_ms   INTEGER,
    error_message TEXT,
    job_id        TEXT,               -- last job that touched this row
    PRIMARY KEY (project_id, idx0, stage_id)
);
CREATE INDEX IF NOT EXISTS page_stages_proj_status
    ON page_stages(project_id, status);
CREATE INDEX IF NOT EXISTS page_stages_proj_idx0
    ON page_stages(project_id, idx0);
```

Reads are JSON-bodied wire models (a `PageStageState` Pydantic class)
constructed from the row; the wire form may add a derived `is_checkpoint`
boolean from a static lookup.

The existing `pages.body` JSON keeps `processing_status` / `outputs` as
**rolled-up** views (all stages clean ⇒ page complete), recomputed by the
runner whenever a stage transitions. We do **not** duplicate per-stage
state in two places.

---

## Dirty propagation

> Dirty propagation operates on **persisted checkpoint state** —
> i.e. against rows in `page_stages` whose `artifact_key` is committed.
> In-memory mid-run artifacts (per §Memory-resident execution model)
> do **not** appear in `page_stages` until their persistence write has
> succeeded; until then the row's status remains `running`. This
> guarantees that "is page P complete?" reads from a coherent
> persisted view and never observes a half-written run.

When stage `S` on page `P` re-runs (or its config / input fingerprint
changes), all stages reachable from `S` in the DAG on page `P` get
status `dirty`. The transition is **eager** at write time (see
Open Question §Q2 for the trade-off vs lazy):

```
def mark_dirty(project_id, idx0, stage_id):
    UPDATE page_stages
       SET status = 'dirty', artifact_key = NULL
     WHERE project_id = ?
       AND idx0       = ?
       AND stage_id IN (<topologically_downstream_of(stage_id)>);
```

The downstream set is a static lookup — `STAGE_DAG.descendants(stage_id)` —
not a DB query. The DAG is hard-coded in the runner, so this is just an
in-memory transitive closure.

A page is **complete** iff every applicable stage has `status='clean'`.
Project-level `build_package` reads `pages` rows whose computed
"complete" rolls true; pages with any dirty / failed / running stage
are skipped (and surfaced in the workbench's "blocked" list).

### Re-run modes

+ `page.run_stage(idx0, stage_id)` — runs *only* `stage_id`. Marks
  downstream dirty (they had been depending on the old output).
  Operator must run them (or `page.run_dirty`) to bring page back to
  complete.
+ `page.run_from(idx0, stage_id)` — runs `stage_id`, then walks
  downstream in topological order, running each. Equivalent to
  `run_stage` followed by `run_dirty`.
+ `page.run_dirty(idx0)` — runs every dirty stage in DAG order. Skips
  `not-applicable`. Used when the user has fiddled with multiple
  upstream stages and wants the workbench to settle.

---

## API surface

New routes under `/api/gpu/*` (synchronous per-stage execution) and
`/api/data/*` (state reads):

| Route | Body / Query | Behaviour |
|---|---|---|
| `GET /api/data/projects/{id}/pages/{idx0}/stages` | — | Returns ordered list of `PageStageState` for this page. |
| `GET /api/data/projects/{id}/stages` | `?stage_id=&status=` | Project-wide stage view; cheap because of the `(project_id, status)` index. Used by the project-level "blocked pages" report. |
| `POST /api/gpu/page-stage` | `{idx0, stage_id, mode: "single" \| "from" \| "dirty"}` | Sync-or-async per spec-04 sync rules. `single` / `from` mirror the workbench preview (interactive priority). `dirty` queues a job. |
| `POST /api/gpu/jobs` (existing) | `{type: "project.run_stage_all_pages", payload:{stage_id, only_dirty:bool}}` | Replaces the targeted-fan-out batch jobs. |
| `POST /api/gpu/jobs` | `{type: "project.run_dirty", payload:{stage_filter?:[...]}}` | The "run everything that's dirty" project sweep. |

Existing endpoints (`POST /api/gpu/process-page`, `POST /api/gpu/run-ocr-page`)
are kept for backward compatibility through M5; under the hood they
become `page-stage` calls with `stage_id="canvas_map"` (run_from) and
`stage_id="ocr"` respectively. They are deprecated in M6.

`JobType` gains:

```python
class JobType(str, Enum):
    # existing
    unzip = "unzip"
    thumbnails = "thumbnails"
    build_package = "build_package"
    # NEW
    project_run_stage_all = "project.run_stage_all_pages"
    project_run_dirty     = "project.run_dirty"
    page_run_stage        = "page.run_stage"     # used by run_dirty mode
    # DEPRECATED in M6 (kept for migration / job retry of in-flight rows)
    batch_process_pages = "batch_process_pages"
    batch_ocr = "batch_ocr"
    batch_text_postprocess = "batch_text_postprocess"
    batch_extract_illustrations = "batch_extract_illustrations"
```

`Job.payload` carries `{stage_id, page_idxs?, only_dirty}`. SSE events
now include `stage_id` so the workbench can highlight the stage
currently running.

---

## Workbench UX (per-page view)

Per-page route stays `/project/{id}/page/{idx0}`. Layout sketch:

```
┌─────────────────────────────────────────────────────────────────────┐
│ p045 (idx 49)                            [Run dirty] [Run from →]  │
│                                                                      │
│ ┌── Stage chain ────────────────────────────────────────────────┐  │
│ │ ●  ingest_source        clean    artifact: source/<stem>.jp2  │  │
│ │ ●  thumbnail            clean    artifact: thumbnails/<stem>… │  │
│ │ ●  auto_detect_attrs    clean    page_type=normal             │  │
│ │ ●  auto_detect_illus    clean    3 regions                    │  │
│ │ ─                                                              │  │
│ │ ●  decode_source        clean                                  │  │
│ │ ●  initial_crop         clean    [view artifact]               │  │
│ │ ●  manual_deskew_pre    n/a      (no override set)             │  │
│ │ ●  grayscale            clean    [view artifact]               │  │
│ │ ⚠  threshold            DIRTY    (changed level: 140→160)      │  │
│ │ ○  invert               not-run                                │  │
│ │ ○  find_content_edges   not-run                                │  │
│ │ … (etc.)                                                       │  │
│ │                                                                │  │
│ │ Affordances per row: [▶ Run this]  [▶ Run from here]           │  │
│ │ Header affordances:  [Run all dirty]  [Reset page (re-run all)]│  │
│ └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│ ┌── Artifact viewer ─────────────────────────────────────────────┐  │
│ │ Stage: [threshold ▼]    Compare with: [grayscale ▼]            │  │
│ │ ┌────────────┐  ┌────────────┐                                  │  │
│ │ │ before     │  │ after      │   ←  side-by-side checkpoint     │  │
│ │ │ (gray)     │  │ (binary)   │      images at full image res    │  │
│ │ └────────────┘  └────────────┘                                  │  │
│ │ Diff overlay: [✓]  Histogram: [✓]                              │  │
│ └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│ ┌── Stage controls (selected stage: threshold) ──────────────────┐  │
│ │  Otsu auto                              [✓]                    │  │
│ │  Manual level                           [   140 ]              │  │
│ │  ─                                                              │  │
│ │  [Apply + Run this stage]    [Apply + Run from here]            │  │
│ └────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

Reads:

+ `GET /api/data/projects/{id}/pages/{idx0}/stages` for the chain.
+ For each row, `IStorage.presign_get(artifact_key)` for the thumbnail
  / artifact viewer. The chain shows a tiny inline thumbnail per
  checkpoint stage (lazy-loaded on row expand).

Writes:

+ Selecting a stage → populates Stage controls panel with the subset
  of `ResolvedPageConfig` fields relevant to that stage (a static map
  on the frontend). "Apply" PATCHes `page.config_overrides`, then
  fires `POST /api/gpu/page-stage` with `mode=single` or `from`.
+ The "Stage chain" left rail listens on the page's job SSE stream
  for stage transitions and updates row status live.

Non-checkpoint stages (intermediate algebraic steps that don't have an
output image worth viewing — `find_content_edges` returns a 4-tuple,
not an image) render as a small numeric / textual artifact rather than
an image preview.

The illustration regions and split editor from the existing workbench
spec (`specs/06-page-workbench.md`) remain — they live in their own
panels and don't change. `extract_illustrations` is a stage in the
chain but its "artifact" is the hi-res crop set; the existing
illustration panel is the right viewer for it.

---

## Migration story (M4)

Existing projects under `~/pgdp-projects/<id>/` have:

+ Source files at `source/<stem>.<ext>` ✅ (preserved verbatim).
+ Thumbnails at `thumbnails/<stem>.jpg` ✅.
+ Possibly cached proofing PNGs at the legacy
  `processed_image_key` / `pre_ocr_image_key` paths ✅.
+ OCR text + words at the legacy keys.
+ **No** `stages/` tree.
+ `pages` rows with `processing_status` ∈ {pending, processing,
  complete, error}.

**Recommendation: lazy-migrate on first access.** When the runner or
workbench first reads `page_stages` for `(project_id, idx0)` and finds
zero rows:

1. Synthesise a `page_stages` row per stage. Status is derived from
   the legacy `processing_status`:
   + `complete` → mark every applicable stage `clean`.
     `artifact_key` for `canvas_map` is set to the legacy
     `processed_image_key`; intermediate stages get `artifact_key=NULL`
     (we never had those checkpoints).
   + `error` → mark `canvas_map` as `failed` with the legacy
     `processing_error`; everything upstream `clean`; downstream
     `not-run`.
   + `pending` / `processing` → all stages `not-run`.
2. `stage_version` is set to the current code's version (so we don't
   immediately mark the page dirty under "code changed underneath").
3. `config_hash` and `input_hash` are computed.
4. Write the rows in one transaction.

Trade-off vs. force-rebuild:

+ **Lazy-migrate** (recommended): Zero downtime, proof of every old
  project's compatibility happens incrementally. Downside: the old
  intermediate artifacts don't exist as files, so the workbench's
  artifact viewer for those rows will be empty until the user re-runs
  the stages — but this is *exactly* the semantics of "we never
  computed those artifacts before" and is correctly represented by
  `artifact_key=NULL`, not stale state.
+ **Force-rebuild on next open**: Cleaner state but throws away
  user-acceptable existing outputs. Bad UX for a user with a 500-page
  book they finished proofing yesterday.

A `pgdp-prep migrate-projects --rebuild` CLI affordance is added for
users who want to forcibly rebuild — opt-in, never automatic.

---

## Open questions — Locked (2026-05-07)

The seven open questions below are **locked** as of 2026-05-07; the
spec's recommendations are now the canonical decisions. Implementation
proceeds against these defaults. If a locked decision turns out to be
materially worse than its alternative during implementation, surface
it for re-evaluation rather than silently flipping.

| # | Decision | Lock |
|---|---|---|
| Q1 | Stage-state persistence | Normalised `page_stages` SQLite table (not JSON-on-`pages.body`). |
| Q2 | Dirty propagation | Eager — UPDATE all downstream rows to `dirty` at write time. |
| Q3 | Artifact storage | Checkpoint stages only; `PGDP_FULL_STAGE_ARTIFACTS=1` env switch enables full-intermediate persistence for debugging (switch may land in M2; M1 only must not preclude it). |
| Q4 | Stage versioning | Manual `stage_version` registry (`STAGE_VERSIONS = {...}`), bumped by hand when a stage's algorithm changes. Lands in M2. Auto-derive deferred. |
| Q5 | LocalBackend collapse | `STAGE_IMPL[stage_id][device]` registry; `LocalBackend` becomes a device-chooser (cuda where available, else cpu). Lands in M2. |
| Q6 | Splits in the DAG | Splits remain configuration to `ocr_crop`, not first-class DAG nodes. Per-split rerun granularity revisited only if proofers ask. Lands in M2. |
| Q7 | `text_review` as a stage | Yes — gate stage with `not-run` = unreviewed, `clean` = user-attested. `build_package` gates on it via `require_text_review` (default off in M2). |

The original recommendation rationale follows for context:

### Q1. Stage-state persistence: extend `Page` body vs. new `page_stages` table

| | Extend `Page.body` JSON | New `page_stages` table |
|---|---|---|
| Read "all stages for one page" | Cheap (one row) | Cheap (one query, indexed) |
| Read "all dirty stages in project" | Expensive — scan every page row, JSON-decode, filter | Single indexed query |
| Mark downstream dirty (one page) | Read row, mutate JSON, write row | One UPDATE with `IN` |
| Mark downstream dirty (all pages, e.g. project config change) | Re-read & re-write every page row | One UPDATE |
| Schema migration | Free (JSON) | New table, but additive |
| Postgres parity | Same JSONB pattern as today | Same SQL works on both |

**Recommendation:** new `page_stages` table. The dominant queries
(`list project's dirty stages`, `mark downstream dirty across N pages
when project config changes`) are O(1) SQL with the table and O(N) JSON
mutation without it.

### Q2. Dirty propagation: eager vs. lazy

+ **Eager** (recommended): on stage rerun, immediately UPDATE all
  downstream rows to `dirty`. Easy to reason about; the DB always
  reflects truth.
+ **Lazy**: on stage rerun, only update *that* row; on read, recompute
  whether downstream rows are stale by chasing fingerprints. Cheaper
  writes, but every reader becomes a fingerprint walker, and "is page
  P complete?" becomes non-trivial.

**Recommendation:** eager. Dirty cascades are bounded (max 18 rows per
page); writes are infrequent; the simplicity wins.

### Q3. Artifact storage: every intermediate vs. checkpoints only

+ **Every intermediate** (~12 PNGs/page × 500 pages = ~6k extra files,
  ~600 MB at typical proof sizes): full diff-able workbench, no extra
  CPU on viewer open. Disk-heavy on big books; S3 PUT cost in managed
  mode.
+ **Checkpoints only** (recommended; see list below): store a small set
  of "interesting" stages and reconstruct intermediate views on demand
  by re-running the relevant micro-step from the prior checkpoint.

**Recommendation:** checkpoints. Default checkpoint set:
`decode_source`, `initial_crop`, `threshold`, `crop_to_content`,
`auto_deskew`, `canvas_map`, `ocr_crop`, `ocr` (words.json + raw.txt),
`text_postprocess`. Non-checkpoint stages (`grayscale`, `invert`,
`find_content_edges`, `morph_fill`, `rescale`) reconstruct on viewer
open by reading the prior checkpoint and replaying the missing
sub-steps — fast on CPU (<200 ms) and avoids storing near-duplicates.
A `PGDP_FULL_STAGE_ARTIFACTS=1` env switch enables "store all" for
debugging hard pipelines.

### Q4. Stage versioning / "code changed underneath"

Today there's no detection that the code that produced an artifact has
changed (e.g. `pd-book-tools` upgrade rewrites `auto_deskew`). We can
hash `(stage_version, config_hash, input_hash)` and treat a mismatch as
implicit-dirty.

+ **Yes (recommended for M2):** `stage_version: int` lives in a static
  registry (`STAGE_VERSIONS = {"auto_deskew": 3, ...}`) the runner
  bumps when the algorithm changes. A row whose `stage_version` is
  behind is treated as `dirty` on read.
+ **Later:** auto-derive `stage_version` from a hash of the relevant
  function source. More magic, more brittle.
+ **No:** rely on user awareness. Risky after a `pd-book-tools` upgrade.

**Recommendation:** manual `stage_version` registry in M2. Auto-derive
deferred unless it bites.

### Q5. `LocalBackend` vs `CpuBackend` in the new model

In the current code `LocalBackend` is a thin subclass of `CpuBackend`
(DocTR / PyTorch auto-pick CUDA when available). The CUDA path for
Step 4 image-processing primitives (cupy_processing) is parked.

In the new model, "execution path" (CPU primitives vs CUDA primitives)
is orthogonal to "stage definition" — the DAG is identical, only the
function dispatch changes. The cleanest collapse is:

+ One `GPUBackend.run_stage(stage_id, ...)` entry point.
+ Each stage's implementation is a registry lookup
  `STAGE_IMPL[stage_id][device]` where `device ∈ {"cpu", "cuda"}`.
+ `LocalBackend` chooses `device="cuda"` when available, else falls
  through to `device="cpu"`.

**Recommendation:** collapse `LocalBackend` to "device chooser only" in
M2. `CpuBackend` remains for the explicit-CPU test default.

### Q6. Where do `splits` live in the DAG?

`PageSplit` produces multiple OCR outputs per page. Today
`crop_for_ocr` honours splits implicitly. In the new model, splits are
configuration consumed by `ocr_crop` (one stage; output is a *list* of
artifacts keyed by `split_suffix`). Downstream `ocr` and
`text_postprocess` stages also operate on the list.

**Recommendation:** model splits as configuration to `ocr_crop` (no
new DAG nodes), and have stage outputs that are "list of artifacts"
naturally — already true in the OCR side. A future M-something can
promote per-split execution to per-stage rows if proofers want
"re-run OCR for split b only" granularity. For M2 the unit of
re-run on this side is the page.

### Q7. Should `text_review` be a stage at all?

It's a UI-only step — no compute. Modelling it as a stage gives a
single "is the page reviewed?" gate for `build_package`, but conflates
"computed" with "human-attested."

**Recommendation:** include it as a stage with status semantics:
`not-run` = unreviewed, `clean` = reviewed (set by an explicit
"mark reviewed" action). `build_package` requires `text_review.clean`
when project config has `require_text_review=True` (default off in M2,
flip to on once review UX exists). This gives the workbench one
uniform completion view.

---

## Open questions — NEW (not yet locked, added 2026-05-07)

The following questions arose with the §Memory-resident execution
model amendment and **must be explicitly locked by the user before
M2 runner work**. Recommendations are written below for each, but
per the project's "no implicit approval" rule, they are not in force
until the user says so.

### Q8. Concurrency cap on in-flight deferred-write tasks

When a page-processing run produces multiple checkpoint outputs in
quick succession, how do we bound the deferred-write executor?

+ **Bounded executor + bounded queue** (recommended): a per-process
  `ThreadPoolExecutor` with a small worker count (e.g. 2–4) and a
  bounded submission queue. When the queue is full, the DAG runner
  blocks on submission — back-pressure prevents unbounded RAM growth
  if disk is slow. Cap is configurable; default sized so a typical
  fast SSD never blocks but a slow networked storage in self-hosted
  shapes degrades gracefully.
+ **Unbounded fire-and-forget**: simpler, but a slow `IStorage` (e.g.
  S3 with backpressure, or a full disk) can grow the in-flight set
  unboundedly and OOM the worker.

**Recommendation:** bounded executor with bounded queue.

### Q9. Behaviour when a deferred write fails mid-run

If the in-memory compute succeeded but a deferred persistence write
fails (e.g. disk full, S3 PUT 5xx after retries), what status does
the page's run land in?

+ **Per-artifact policy** (recommended):
  + If the failed write is a **checkpoint stage** artifact —
    something the workbench / `build_package` may legitimately need
    to read later — the page transitions to `failed` for that stage
    (and downstream stages stay `not-run` from this run's
    perspective; their in-memory outputs are discarded since their
    correctness is moot if the upstream persistence didn't land).
  + If the failed write is a **non-checkpoint** artifact under
    `PGDP_FULL_STAGE_ARTIFACTS=1` (debug-only persistence), the
    stage status is `clean-with-write-warning` and the run as a
    whole completes; the workbench shows a banner. Compute is the
    canonical truth; the missing debug artifact is regenerable.
+ **Always-fail**: any write failure fails the page. Simple but
  noisy in debug mode.
+ **Always-warn**: any write failure is downgraded to a warning.
  Risk: a page reads `clean` even though its checkpoint isn't on
  disk, breaking the next stage's lazy load.

**Recommendation:** the per-artifact policy above —
`failed` for checkpoint writes, `clean-with-write-warning` for
non-checkpoint debug writes.

### Q10. Format of in-memory artifacts

What is the canonical exchange type between stages while running in
memory?

+ **Numpy ndarray as canonical** (recommended): every stage's input
  and output is a `numpy.ndarray` (BGR for color images, single-
  channel for grayscale/binary). Optional accompanying lightweight
  metadata struct (a small dataclass — dtype, channel order,
  origin-bbox, resampling provenance — to avoid per-stage cv2 vs
  PIL conversion churn).
+ **Per-stage native type**: each stage uses whatever its underlying
  library prefers (PIL for some, numpy for others, cv2 Mat for
  others). Less conversion in some hot paths but introduces
  N×M conversion combinations across stage boundaries and makes the
  refcount / drop logic harder to write generically.

**Recommendation:** numpy ndarray as the canonical exchange type
plus a small optional cv2-style metadata struct, with adapters at
the entry/exit of any stage that internally prefers PIL or torch
tensors.

---

## Suggested order to lock decisions

1. **Q1 (table vs JSON)** and **Q2 (eager vs lazy)** first — they
   shape the schema and the runner's hot path. Locking them unblocks
   M1 work.
2. **Q3 (artifact storage)** before M2 — it shapes the storage layout
   and the workbench API contract.
3. **Q4 (stage versioning)** can land in parallel with M2; the
   registry is a small additive change.
4. **Q5 (backend collapse)** before M2's GPUBackend rework.
5. **Q6 (splits)** can stay as a footnote until M3 reveals friction.
6. **Q7 (text_review as stage)** before M3's workbench wiring.
