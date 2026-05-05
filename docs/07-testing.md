# 07 — Testing

## What's covered

128 tests across 35 files (`tests/test_*.py`).

| Area | Files | Approx. count |
|---|---|---|
| Smoke / wiring | `test_smoke.py`, `test_entry_point.py` | 6 |
| Models / resolver / prefix | `test_config_resolver.py`, `test_assign_prefixes.py` | 12 |
| Pipeline | `test_blank_proof.py`, `test_process_page.py`, `test_crop_for_ocr.py`, `test_text_postprocess.py`, `test_packaging.py`, `test_cover_title_packaging.py`, `test_illustrations.py` | 27 |
| OCR / detection | `test_auto_detect.py`, `test_ocr_engine_override.py` | 8 |
| Ingest | `test_ingest.py`, `test_ingest_auto_detect.py`, `test_ingest_layout_detect.py`, `test_ingest_progress.py` | 11 |
| Job runner / events / dispatcher | `test_job_runner.py`, `test_job_handlers.py`, `test_batch_jobs.py`, `test_concurrent_jobs.py`, `test_dispatcher_integration.py`, `test_job_events.py`, `test_job_events_sse.py`, `test_job_event_types.py`, `test_job_retry.py`, `test_jobs_filter.py`, `test_priority_queue.py` | 32 |
| Routes / e2e | `test_e2e_ingest.py`, `test_e2e_pipeline.py`, `test_cdn_upload.py`, `test_env_js.py`, `test_auth_me.py`, `test_delete_project.py`, `test_project_rename.py`, `test_text_review_alignment.py`, `test_page_processing_error.py`, `test_system_defaults_route.py`, `test_system_defaults_export.py`, `test_system_defaults_reset.py` | 25 |
| Modal wire shape | `test_modal_backend.py` | 3 |

## How to run

```sh
cd /workspaces/ocr-container/pd-prep-for-pgdp
PYTHONPATH=src /workspaces/ocr-container/.venv/bin/python -m pytest tests/ -q
```

Expected: `128 passed`. Runs in ~12s on a modest dev machine.

The shared parent `.venv` already has fastapi, pydantic, uvicorn, httpx,
pytest, pd-book-tools, plus the pydantic-settings + sse-starlette +
pytest-asyncio that iteration 1 added. When the user runs `make setup` for
real, uv creates a project-local `.venv`.

## Conventions

**TDD-first** for pure-function additions and route handlers — see
`feedback_tdd_when_possible.md` in the memory directory. The pattern: write
the test with concrete expected output, run it (red), implement, run it
(green). Examples:

- `test_text_postprocess.py` — exact expected output for each transform.
- `test_packaging.py` — assert specific files in the zip + manifest fields.
- `test_assign_prefixes.py` — assert specific prefixes (with the off-by-one
  noted).

**Stub-shaped work** (route stubs, adapter Protocols) is exempt — just write
the stub when no behaviour exists yet.

**Pipeline modules** that depend on cv2 or pd-book-tools get
integration-shaped tests on synthetic inputs (e.g. `test_process_page.py`'s
black-on-white round-trip through Step 4, asserting canonical aspect ratio).

## Fixtures (`conftest.py`)

- `settings(tmp_path)` — `Settings(...)` pointing at `tmp_path` for both
  `data_root` and the SQLite database. Filesystem storage, none auth, cpu
  GPU, immediate dispatch.
- `client(settings)` — `TestClient(build_app(settings))`. The TestClient
  enters the FastAPI lifespan, so jobs created in tests actually run
  (the InProcessJobRunner is alive while the client is open).

A few async tests construct their own `SqliteDatabase` directly (e.g.
`test_text_review_alignment.py`) to seed state before the TestClient opens.
Those use `asyncio.run(_seed())` — using `get_event_loop().run_until_complete`
hijacks the test loop and was the cause of an iteration-6 flake.

## What's deliberately not tested

- **Real DocTR / cv2 model loads** — cost too much per test run. The OCR
  layer mocks `_ocr_page_tesseract` for engine-override testing; the
  Modal layer mocks the `modal` module via `monkeypatch.setitem(sys.modules,
  ...)`.
- **Real Modal dispatch** — no Modal account in the devcontainer.
  `test_modal_backend.py` injects a `FakeFunctionRegistry` so the wire
  shapes are still verified.
- **Frontend** — Vitest is deferred (no npm in this devcontainer). The
  pages have testable seams (named hooks, exported helpers) for when it lands.
- **install.sh end-to-end** — would need internet + a clean shell.

## Test stability

Three known sensitive areas:

1. **`test_text_review_alignment.py`** seeds via a throwaway `asyncio.run`
   *before* opening the TestClient — using a shared loop caused flakes.
2. **`test_concurrent_jobs.py`** passes `max_concurrency=N` to the runner
   and mocks the ingest handler to sleep deterministically. The SQLite
   cursor lock (added in iteration 10) was needed to make this stable.
3. **`test_ingest_progress.py`** subscribes to the broker BEFORE submitting
   the job, then awaits `listener` after `run_pending`. The progress events
   are guaranteed because the runner publishes synchronously from the
   ingest callback; no `asyncio.sleep` race.

After 22 iterations of building this, we routinely run the suite 3–5 times
to catch flakes; current stability is "100% over five consecutive runs."
