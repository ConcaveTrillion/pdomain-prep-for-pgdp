# Spec 08 — Data Models

Pydantic models are the source of truth. TypeScript types are generated from
`/openapi.json` via `openapi-typescript` and live in
`frontend/src/api/types.ts`. There is no parallel TypeScript-first definition
and no `packages/api-types` workspace.

The schema below describes the persisted shape (what appears in S3/JSON files
and database rows) and the wire shape (what crosses `/api/data` and
`/api/gpu`). They are the same.

---

## SystemDefaults

System-wide tunables. Spec 01 has the rationale.

```python
class SystemDefaults(BaseModel):
    text_threshold: int = 140
    page_h_w_ratio: float = 1.65
    default_fuzzy_pct: float = 0.02
    default_pixel_count_columns: int = 150
    default_pixel_count_rows: int = 75
    ocr_engine: Literal["doctr", "tesseract"] = "doctr"
    ocr_model_key: str | None = None
    ocr_dpi: int = 150
    ocr_bbox_edge_min_words: int = 5
    layout_detector: Literal[
        "none", "contour", "pp-doclayout-plus-l"
    ] = "pp-doclayout-plus-l"
    layout_detector_confidence: float = 0.5
    layout_checkpoint: str | None = None
    standard_scannos: dict[str, str] = Field(default_factory=dict)
    hyphenation_join_list: list[str] = Field(default_factory=list)
```

| Mode | Persistence |
|---|---|
| Local | `~/.config/pgdp-prep/defaults.json` |
| Self-hosted | `<data_root>/system_defaults.json` |
| Managed | `system_defaults` Postgres row, keyed by user (admin row as fallback) |

---

## ProjectConfig

```python
class ProjectConfig(BaseModel):
    book_name: str
    source_uri: str

    proof_start_idx0: int = 0
    proof_end_idx0: int = 0
    cover_idx0: int | None = None
    title_idx0: int | None = None
    frontmatter_start_idx0: int = 0
    frontmatter_end_idx0: int = 0
    bodymatter_start_idx0: int = 0
    bodymatter_end_idx0: int = 0
    frontmatter_page_nbr_start: int = 1
    bodymatter_page_nbr_start: int = 1

    initial_crop_all: tuple[int, int, int, int] = (0, 0, 0, 0)
    ocr_crop_top: int = 0
    ocr_crop_bottom: int = 0
    ocr_crop_left: int = 0
    ocr_crop_right: int = 0

    custom_regex_passes: list[tuple[str, str]] = Field(default_factory=list)
    custom_scannos: dict[str, str] = Field(default_factory=dict)

    default_overrides: dict[str, object] = Field(default_factory=dict)
    """Sparse map: SystemDefaults field name → override value for this project."""
```

Stored at `projects/<id>/project.json`.

---

## Project

```python
class ProjectStatus(str, Enum):
    ingesting   = "ingesting"
    configuring = "configuring"
    processing  = "processing"
    reviewing   = "reviewing"
    packaging   = "packaging"
    complete    = "complete"

class Project(BaseModel):
    id: str
    owner_id: str = "default"
    name: str
    created_at: datetime
    updated_at: datetime
    status: ProjectStatus
    page_count: int
    proof_page_count: int
    config: ProjectConfig
    pipeline_state: "PipelineState"
    storage_prefix: str         # "projects/<id>/" — backend-agnostic
```

The `Project` is the API-shaped wrapper around `ProjectConfig` plus runtime
state. Persisted as one JSON document or one row depending on the database
adapter.

---

## PageRecord

One file/row per source page.

```python
class PageType(str, Enum):
    normal  = "normal"
    blank   = "blank"
    plate_b = "plate_b"
    plate_p = "plate_p"
    plate_r = "plate_r"

class AlignmentOverride(str, Enum):
    default = "default"
    top     = "top"
    center  = "center"
    bottom  = "bottom"

class PageProcessingStatus(str, Enum):
    pending    = "pending"
    processing = "processing"
    complete   = "complete"
    error      = "error"


class PageConfigOverrides(BaseModel):
    """Per-page processing overrides. Every field is None = inherit."""
    initial_crop: tuple[int, int, int, int] | None = None
    white_space_additional: tuple[float, float, float, float] | None = None
    threshold_level: int | None = None        # None = Otsu auto
    fuzzy_pct: float | None = None
    pixel_count_columns: int | None = None
    pixel_count_rows: int | None = None
    skip_auto_deskew: bool | None = None
    deskew_before_crop: float | None = None
    deskew_after_crop: float | None = None
    do_morph: bool | None = None
    skip_denoise: bool | None = None
    use_ocr_bbox_edge: bool | None = None
    rotated_standard: bool | None = None
    single_dimension_rescale: bool | None = None


class PageOutput(BaseModel):
    """One per split, or one for whole page."""
    full_prefix: str                # "p045" or "p045a"
    split_suffix: str | None
    reading_order: int

    proofing_image_key: str | None = None
    pre_ocr_image_key: str | None = None
    ocr_image_key: str | None = None
    ocr_text_key: str | None = None
    for_zip_image_key: str | None = None
    for_zip_text_key: str | None = None

    ocr_status: PageProcessingStatus = PageProcessingStatus.pending
    ocr_job_id: str | None = None
    ocr_error: str | None = None


class PageRecord(BaseModel):
    project_id: str
    idx0: int
    prefix: str
    source_stem: str
    ignore: bool = False               # outside proof range

    page_type: PageType = PageType.normal
    alignment: AlignmentOverride = AlignmentOverride.default

    config_overrides: PageConfigOverrides = Field(default_factory=PageConfigOverrides)

    splits: list["PageSplit"] = Field(default_factory=list)
    illustration_regions: list["IllustrationRegion"] = Field(default_factory=list)

    # Storage keys (None = not yet generated)
    source_key: str | None = None
    thumbnail_key: str | None = None
    processed_image_key: str | None = None
    ocr_image_key: str | None = None

    # Processing status
    processing_status: PageProcessingStatus = PageProcessingStatus.pending
    processing_job_id: str | None = None
    processing_error: str | None = None
    last_processed_at: datetime | None = None

    outputs: list[PageOutput] = Field(default_factory=list)
```

Stored at `projects/<id>/pages/<idx0>.json` (one file per page in S3/filesystem
mode), or as a row in `pages` table (Postgres mode).

`page_type` and `alignment` were previously list-on-`BookConfig` fields; they
now live on the page itself. See spec 01 for the full justification.

---

## PageSplit

Replaces the notebook's `PageSectionSplit`.

```python
class PageSplit(BaseModel):
    suffix: str                     # appended to page prefix: "a", "b", "cl"
    reading_order: int              # 0-based; determines output sort order

    # Bbox in PROCESSED image coordinates (post-deskew, pre-rescale).
    L: int | None = None            # None = image edge
    R: int | None = None
    T: int | None = None
    B: int | None = None

    scale_to_standard_page: bool = True
    alignment: AlignmentOverride | None = None
    ocr_engine: Literal["doctr", "tesseract"] | None = None
```

Splits live on `PageRecord.splits` (not `ProjectConfig`). Workbench drag-edits
write here directly.

---

## IllustrationRegion

```python
class IllustrationRegion(BaseModel):
    index: int = 1                              # 1-based illustration number on the page
    label: str = ""                             # human label, not in filename
    type: Literal["illustration", "decoration", "plate"] = "illustration"

    # Bbox in SOURCE image coordinates (original scan, pre-processing)
    L: int | None = None
    R: int | None = None
    T: int | None = None
    B: int | None = None

    output_format: Literal["jpg", "png"] = "jpg"
    jpeg_quality: int = 85
    convert_to_grayscale: bool = False
```

Lives on `PageRecord.illustration_regions`.

Plate pages (`page_type == "plate_p"`) automatically get a synthesised
full-page region at extraction time if none is configured; the user can edit
it.

---

## PipelineState

```python
class StepStatus(str, Enum):
    pending  = "pending"
    running  = "running"
    complete = "complete"
    error    = "error"

class StepState(BaseModel):
    status: StepStatus = StepStatus.pending
    pages_complete: list[int] = Field(default_factory=list)
    pages_error: dict[int, str] = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    job_id: str | None = None

# Step IDs match spec 02
StepId = Literal[1, 2, 4, 5, 6, 7, 8, 9, 10]

class PipelineState(BaseModel):
    steps: dict[StepId, StepState] = Field(default_factory=dict)
```

Stored as part of `Project`. Updated by job runners.

---

## ResolvedPageConfig

Output of `resolve_page_config()` (spec 01). This is what the pipeline
consumes; not persisted.

```python
class ResolvedPageConfig(BaseModel):
    text_threshold: int
    page_h_w_ratio: float
    fuzzy_pct: float
    pixel_count_columns: int
    pixel_count_rows: int
    ocr_bbox_edge_min_words: int
    ocr_engine: Literal["doctr", "tesseract"]
    ocr_model_key: str | None
    ocr_dpi: int

    initial_crop_all: tuple[int, int, int, int]
    ocr_crop: tuple[int, int, int, int]            # (top, bottom, left, right)

    page_type: PageType
    alignment: AlignmentOverride
    initial_crop: tuple[int, int, int, int] | None
    white_space_additional: tuple[float, float, float, float] | None
    threshold_level: int | None                    # None = Otsu (preserved)
    skip_auto_deskew: bool
    deskew_before_crop: float | None
    deskew_after_crop: float | None
    do_morph: bool
    skip_denoise: bool
    use_ocr_bbox_edge: bool
    rotated_standard: bool
    single_dimension_rescale: bool
```

---

## Job

```python
class JobStatus(str, Enum):
    queued       = "queued"
    scheduled    = "scheduled"        # waiting for dispatcher flush (managed mode)
    running      = "running"
    complete     = "complete"
    error        = "error"
    cancelled    = "cancelled"

class JobType(str, Enum):
    ingest                       = "ingest"
    batch_process_pages          = "batch_process_pages"
    batch_ocr                    = "batch_ocr"
    batch_text_postprocess       = "batch_text_postprocess"
    batch_extract_illustrations  = "batch_extract_illustrations"
    build_package                = "build_package"

class JobProgress(BaseModel):
    current: int = 0
    total: int = 0
    current_page: int | None = None
    message: str = ""

class Job(BaseModel):
    id: str
    project_id: str
    owner_id: str = "default"
    type: JobType
    status: JobStatus = JobStatus.queued
    progress: JobProgress = Field(default_factory=JobProgress)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    next_dispatch_at: datetime | None = None       # set when status == scheduled
    error_message: str | None = None
    gpu_backend: Literal["local", "cpu", "modal", "shared_container"] = "local"
```

Stored at `jobs/<id>.json` (filesystem/S3) or as a row in `jobs` table.

---

## OcrWord

Returned by `/api/gpu/run-ocr-page` and embedded in OCR result files.

```python
class BoundingBox(BaseModel):
    left: int
    top: int
    width: int
    height: int

class OcrWord(BaseModel):
    id: str                           # stable UUIDv4 across retries for same position
    text: str
    confidence: float                 # 0..1
    bounding_box: BoundingBox
    split_suffix: str | None = None   # coords are in this split's local image space
```

---

## Storage Layout

Same logical layout for filesystem and S3 backends:

```
<root>/
├── system_defaults.json         (self-hosted only; local uses ~/.config)
├── projects/
│   └── <project-id>/
│       ├── project.json         ← Project + ProjectConfig + PipelineState
│       ├── pages/
│       │   ├── 0.json           ← PageRecord per idx0
│       │   ├── 1.json
│       │   └── …
│       ├── source/              ← original scans
│       ├── thumbnails/          ← 400 px JPGs
│       ├── processed/           ← Step 4 PNGs
│       ├── workbench_temp/
│       │   └── <idx0>/          ← per-page workbench preview
│       ├── ocr_images/          ← Step 6 OCR-cropped PNGs
│       ├── ocr_text/            ← .txt OCR output
│       ├── hi_res/              ← illustration extractions
│       └── for_zip/             ← PGDP package staging
└── jobs/
    └── <job-id>.json
```

In Postgres mode (`IDatabase.postgres`), `project.json`, `pages/*.json`, and
`jobs/*.json` are replaced by tables of the same shape. Image files stay on
the storage backend.

CloudFront caching rules (managed mode):

| Prefix | TTL | Notes |
|---|---|---|
| `thumbnails/`, `processed/`, `hi_res/` | 24 h | Immutable once written |
| `ocr_text/` | 0 | Editable |
| `project.json`, `pages/*.json` | 0 | Frequently updated |
| `for_zip/` | 1 h | Updated only during packaging |
