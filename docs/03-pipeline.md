# 03 — Pipeline

Spec 02 enumerates 10 pipeline steps. This doc describes the actual
implementation, where each step lives, and how the OCR mirrors `pd-ocr-cli`.

## Step map

| Step | Code | Status |
|---|---|---|
| 0 — Ingest | `core/ingest.py` `ingest_source()` | ✅ |
| 1 — JP2→JPG | (skipped today; cv2.imdecode handles JP2 directly) | ⏭ |
| 2 — Thumbnails | `core/ingest.py` `_make_thumbnail_bytes()` (in-memory) | ✅ |
| 3 — Configure | UI-only; `assign_prefixes` re-derives prefixes after PATCH | ✅ |
| 4 — Process page (CPU path) | `core/pipeline/process_page.py` | ✅ |
| 4b — Blank proof | `core/pipeline/blank_proof.py` | ✅ |
| 4.5 — Illustrations | `core/illustrations.py` (extract + auto-detect) | ✅ |
| 5 — Inspect | UI-only — handled by review queue + per-page status | ✅ |
| 6 — Crop for OCR | `core/pipeline/crop_for_ocr.py` | ✅ |
| 7 — OCR | `core/ocr.py` (mirrors pd-ocr-cli) | ✅ |
| 8 — Text post-process | `core/text_postprocess.py` | ✅ |
| 9 — Text review | UI-only; `PATCH /pages/{idx0}/text` | ✅ |
| 10 — Package | `core/packaging.py` | ✅ |

## Step 0 — `ingest_source`

Inputs: a `Project`, source key (zip or storage prefix), the storage adapter,
and the database.

For zip sources: `_enumerate_zip` reads the zip from storage, extracts each
image entry under `projects/<id>/source/<stem>.<ext>`. For folder sources:
`_enumerate_folder` walks the storage prefix and reads bytes inline. Both
sort by stem so `idx0` is deterministic.

For each entry `_build_page_records`:

1. Decodes + resizes to a 400-px JPG thumbnail (in-memory cv2; written to
   `projects/<id>/thumbnails/<stem>.jpg`).
2. If `auto_detect=True` (default), runs `core.auto_detect.detect_page_attributes`
   on the source bytes to suggest `page_type` (blank / plate_p / normal) and
   `alignment` (default / center).
3. If a `layout_detector` is supplied, calls `auto_detect_illustrations`
   (writes a tempfile so pd-book-tools' detector can take a path) and
   filters to figure / decoration / table regions above the confidence
   threshold.
4. Constructs a `PageRecord` and appends. After each page, `progress_cb`
   fires with `(processed, total, stem)` so the runner emits an SSE event.

Corrupt entries land in `IngestResult.errors` without aborting the batch.

After the loop, if any pages were ingested and `auto_detect=True`, the median
`height/width` ratio is recorded into `Project.config.default_overrides["page_h_w_ratio"]`.

## Step 4 — Process page (CPU)

`process_page_cpu(source_image_bytes, cfg: ResolvedPageConfig)` orchestrates
4c–4o using `pd_book_tools.image_processing.cv2_processing` primitives:

```
4c read source ─┐
4d initial crop  │
4e optional manual deskew before crop
4f grayscale
4g threshold (Otsu auto unless override)
4h invert (text=255, bg=0)
4i find_edges (pixel-based)
4j crop_to_rectangle + optional whitespace pad
4k auto_deskew (skipped for non-default alignment / rotated-standard)
4l optional morph_fill
4m re-invert + rescale_image to canonical aspect
4n map_content_onto_scaled_canvas with alignment
4o cv2.imencode(".png")
```

Returns `ProcessPageOutput(proofing_png, pre_ocr_png, height, width)`.

For `page_type ∈ {blank, plate_b, plate_r}` the function short-circuits to a
canonical-aspect blank PNG (`blank_proof.create_blank_proof`).

The GPU path (`adapters/gpu/local.py`) is a placeholder — the orchestration
shape is the same, but `pd_book_tools.image_processing.cupy_processing`
primitives haven't been wired yet.

## Step 6 — `crop_for_ocr`

Uniform OCR border crop (project-wide top/bottom/left/right) applied to the
proofing image. If `page.splits` is non-empty, yields one crop per split in
reading order; otherwise one whole-page crop.

## Step 7 — OCR (mirrors pd-ocr-cli)

`core/ocr.py` follows `pd-ocr-cli/pd_ocr_cli/ocr_to_txt.py:307–540` verbatim
(see `feedback_ocr_follows_pd_ocr_cli.md` in memory):

1. **Resolve models** (`core/hf_models.py`):
   - `resolve_ocr_models(repo, det_filename, reco_filename, ...)` — local
     paths or HF Hub download with `(.arch, .vocab)` sidecars.
   - `resolve_layout_source(layout_model, layout_checkpoint)` — for
     `pp-doclayout-plus-l`, looks up the HF repo + revision exposed by
     `pd_book_tools.layout.adapters.pp_doclayout.PPDocLayoutPlusLDetector`.
   - `prefetch_layout_files()` pre-downloads transformers files so the later
     `from_pretrained()` is a cache hit.
2. **Process-singleton predictors** (`get_predictor()`, `get_layout_detector()`)
   — load each model once per process, keyed by model paths + device.
3. **Per page**:
   - `Document.from_image_ocr_via_doctr(image_path, ..., predictor)`.
   - `layout_detector.detect(image_path)` (skipped when `layout_detector="none"`).
   - Snapshot `pre_reorg = list(page.words)` if `validate_reorg`.
   - `page.reorganize_page(layout=page_layout)` (or no kwarg if no detector).
   - When `validate_reorg`: `validate_word_preservation(pre, post)` → log a
     warning if any words were dropped.
4. **Adapt** the resulting `pd_book_tools.ocr.word.Word` objects to spec-08
   `OcrWord` (`_to_ocr_word`).
5. **Tesseract path** (`engine="tesseract"`) bypasses DocTR + layout entirely
   and uses `pytesseract.image_to_string` + `image_to_data` for word boxes.

`engine=` kwarg overrides `cfg.ocr_engine` for one call (so the per-page UI
can force Tesseract on a stubborn page without rewriting the config).

## Step 8 — Text post-process

`core/text_postprocess.py` orchestrator:

```
quotes(curly→straight) → em-dash(→--) → join_hyphenated_lines(allow-list)
→ apply_scannos(system) → apply_scannos(project) → apply_custom_regex_passes(project)
```

Hyphenation join only fires when the prefix is in the allow-list (so genuine
compounds like "self-aware" don't get rejoined). Scannos are case-sensitive
word-boundaried replacements.

## Step 4.5 — Illustrations

`extract_illustration(source_image_bytes, region)` decodes via cv2, clamps
coords, optionally converts to grayscale, and encodes JPG (with quality) or
PNG.

`regions_for_page(page, system, source_dimensions=...)` returns either
the user-confirmed `page.illustration_regions`, or a synthesised full-page
region for `plate_p` pages.

`auto_detect_illustrations(image_path, layout_detector, confidence_threshold)`
runs the detector on the source image and filters to figure / decoration /
table region types above the threshold; type is mapped to spec-05's
`"illustration" | "decoration" | "plate"`.

## Step 10 — Package

`build_package(project, pages, storage)` assembles a zip:

- One `<full_prefix>.png` + `<full_prefix>.txt` per non-ignored page output
  (so splits get their own entries).
- `cover.png` aliased from the page where `idx0 == config.cover_idx0`.
- `images/<prefix>_<NN>.<ext>` for each illustration region whose hi-res
  crop exists at `projects/<id>/hi_res/<prefix>_<NN>.<ext>`.
- `pgdp.json` manifest (book_name, project_id, built_at, page_count,
  illustration_count, pages[], optional cover_prefix / title_prefix).

Written to `projects/<id>/for_zip/<book_name>.zip` via `IStorage.put_bytes`.

## Configuration resolution

Spec 01 says the pipeline never reads raw config layers — only a resolved
flat object. `core/config_resolver.py`:

```python
def resolve_page_config(
    system: SystemDefaults,
    project: ProjectConfig,
    page: PageRecord,
) -> ResolvedPageConfig
```

Resolution rule: **page override > project default override > system default**.

`compute_prefix(idx0, project, pages_by_idx)` derives `f###` / `p###` /
`p###[bpr]` from the proof / frontmatter / bodymatter ranges + page types.
*Known off-by-one* in the spec's loop: `range(start, min(idx0, end+1))` is
empty when `idx0 == start`, so the first frontmatter page resolves to `f000`
not `f001`. Implementation matches spec verbatim; test asserts current
behaviour.
