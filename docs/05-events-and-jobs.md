# 05 — Events, Jobs, and the In-Process Queue

The system has three coordination layers, each solving a different problem:

| Layer | Where | What it serialises |
|---|---|---|
| `SingleExecutor` | `core/queue/single_executor.py` | GPU-bound work onto one thread, with INTERACTIVE-preempts-BATCH ordering. |
| `JobEventBroker` | `core/job_events.py` | Status transitions for SSE consumers. |
| `BatchDispatcher` | `dispatcher/batched.py` | Per-page items grouped by `job_id` for managed-mode flush. |

Plus the orchestration layer:

- `InProcessJobRunner` (`core/job_runner.py`) — polls queued jobs from the
  database, runs them with a semaphore (`max_concurrency`), publishes events
  through the broker, hands batch work to the dispatcher when configured.

## `SingleExecutor`

Spec 07 §"in-process queue" mandates a single GPU thread with a 200ms batch
window. `SingleExecutor` wraps `concurrent.futures.ThreadPoolExecutor(max_workers=1)`:

```python
class Priority(IntEnum):
    INTERACTIVE = 0  # workbench live preview / single-page OCR
    BATCH       = 1  # batch jobs

ex.submit(priority, fn, *args) -> asyncio.Future
ex.run_drain_loop()  # background task; opens a 200ms window per drain
```

Each drain pulls the first item, then collects more until the deadline. The
batch is sorted lexicographically on `(priority, sequence)` so INTERACTIVE
items dispatch before BATCH ones queued at the same time. Items run
serially on the worker thread (the GPU isn't safe to share across threads).

`atexit.register(self._thread.shutdown, wait=False)` runs on interpreter
shutdown so a missed `__aexit__` doesn't pin the process.

`bootstrap.build_app` constructs one `SingleExecutor` and starts its drain
loop in the lifespan handler. `CpuBackend` submits through it.

## `JobEventBroker`

```python
broker = JobEventBroker()
await broker.publish(job_id, event_dict)
async for event in broker.subscribe(job_id): ...
await broker.close(job_id)  # signals end-of-stream to subscribers
```

- **Fan-out**: every active subscriber for a `job_id` gets every event.
- **No buffering**: events published before subscribe arrive nowhere.
- **Per-subscriber queue**: each `subscribe()` gets its own
  `asyncio.Queue`. The async iterator yields until a `_CLOSED` sentinel
  arrives.

The runner publishes after every status transition (running → progress
updates → complete/error). The SSE handler in `api/gpu/jobs.py` first emits
a snapshot frame from the database (so a late subscriber sees current state
immediately), then enters `async for ev in events.subscribe(job_id)`. The
event `type` is one of `progress`, `complete`, `error`, `cancelled`.

## `BatchDispatcher`

Managed-mode batching: items are queued in memory grouped by `job_id`,
flushed every `dispatch_interval_seconds` (default 300s) as one
`gpu.run_batch(items)` call. Per-job completion callbacks fire after each
flush so `InProcessJobRunner` can mark the originating job complete.

```python
dispatcher = BatchDispatcher(gpu, interval_seconds=300)
dispatcher.add_completion_callback(runner._on_dispatcher_flush)
await dispatcher.submit(item, job_id="abc")  # buffer
await dispatcher.flush()  # fires completion callback per (job_id, results)
```

`ImmediateDispatcher` is the same shape but `submit` runs the item right
away. Local + self-hosted modes use it.

## Job runner flow

```
poll → claim queued job → mark running + emit progress
                                      │
                                      ▼
                 ingest? → core.ingest.ingest_source(progress_cb=...)
                 build_package? → core.packaging.build_package
                 batch_text_postprocess? → walk pages + write
                 batch_extract_illustrations? → walk regions + write
                 batch_process_pages?
                 batch_ocr?
                       │
                       │   if dispatcher: enqueue + mark scheduled
                       │                  (completion callback marks
                       │                   complete on flush)
                       │   else:          gpu.run_batch(items) inline
                       ▼
                       success → mark complete + emit terminal event
                       failure → mark error + emit terminal event
```

`max_concurrency=N` in the runner constructor turns the per-iteration loop
into a semaphore-bounded `asyncio.gather` of `_run_one(job)` coroutines.

## Where SSE plugs in

- **PageWorkbench** doesn't subscribe (it does sync `POST /process-page`).
- **RunPipelinePanel** + **ProjectJobsFeed**'s inline `JobProgressInline`
  open one `EventSource` per active job. Closes the channel on terminal
  status. Falls back to a one-shot GET on connection error so the UI
  reflects terminal state even when SSE is unavailable.
- **JobsPage** uses polling (`refetchInterval: 5s`) because it lists many
  jobs at once.

## What's still hand-rolled

- The runner's `_find_queued()` walks every owner's recent jobs and filters
  to `queued`. Fine for SQLite + small fleets; Postgres should grow a real
  index + query. Logged in roadmap.
- The dispatcher's per-job grouping happens in memory. Across multiple
  FastAPI instances (managed mode with >1 Fargate task), this becomes
  inconsistent — the design expects the BatchDispatcher to be co-resident
  with the runner. Multi-instance managed mode would need Redis or SQS
  fan-out.
