"""STAGE_IMPL[stage_id][device] registry — flat dispatch for the per-page DAG.

Spec: `docs/specs/pipeline-task-model.md` §"Q5 — STAGE_IMPL registry"
(locked 2026-05-07).

Replaces the old GPU-backend method-dispatch hierarchy
(`LocalBackend.process_page` / `CpuBackend.process_page` / etc.) with a
flat map keyed by `(stage_id, device)`. The runner (Slice 3) will:

1. Resolve the stage's depends_on artifacts off disk.
2. Bridge them to the chosen device's canonical in-memory type
   (numpy.ndarray for cpu, cupy.ndarray for cuda — Q10).
3. Look up the callable here via `get_stage_impl(stage_id, device)`.
4. Call it.
5. Take the returned artifact, dual-write it (existing
   `commit_stage_artifact`).

This module is intentionally **thin and side-effect free**. It must not
import the runner, the writer, or anything that would create an import
cycle. The signatures here are device-canonical types only — the
runner is the one place that decides numpy-vs-cupy.

## Why a typed `StageNotImplemented` sentinel

Spec Q9 says "fail loudly" — every stage failure marks the page_stages
row `failed` with an `error_message`. The runner needs to distinguish:

- **Real bug in a registered stage** → bubble up; Q9 fail-loud, the
  message is whatever the implementation raised.
- **Stage has no implementation registered yet** → record a clear
  user-facing message ("not yet implemented in registry"), don't claim
  the engine is broken.

Built-in `NotImplementedError` is conventionally raised by abstract
methods to signal "subclass must implement this" — which is the wrong
shape for "we know this stage exists but no one wrote the code yet."
A separate exception class also lets us subclass `RuntimeError`, so
`except Exception` paths catch it without needing to know the sentinel
exists.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..models import PAGE_STAGE_IDS

# ─── Sentinel exception ─────────────────────────────────────────────────────


class StageNotImplemented(RuntimeError):
    """Raised by placeholder stage callables when invoked.

    The runner catches this and records the page_stages row as `failed`
    with a clear "not yet implemented in registry" message. **Not** a
    subclass of `NotImplementedError` (Q9 rationale above).
    """


def _make_placeholder(stage_id: str) -> Callable[..., Any]:
    """Build a placeholder callable for stages without a real impl yet.

    Returns a function that, when called, raises ``StageNotImplemented``
    naming the stage. Closure-bound so the message is correct without
    relying on traceback-walk hacks.
    """

    def _placeholder(*_args: Any, **_kwargs: Any) -> Any:
        raise StageNotImplemented(
            f"stage {stage_id!r} has no implementation registered for cpu yet "
            "(M2 placeholder — wire up in a future slice)"
        )

    _placeholder.__name__ = f"placeholder_{stage_id}"
    _placeholder.__doc__ = f"Placeholder for stage {stage_id!r} — raises StageNotImplemented."
    return _placeholder


# ─── Real implementations: pure-function chain (M2 Slice 2 + 6) ─────────────
#
# The full image-processing chain still lives in process_page.py for now;
# extracting all 22 stages atomically would be a 500-line refactor. These
# stages are the simplest pure-function transformations on a single image
# and are independent enough to wire into the registry without touching
# process_page yet.
#
# Each takes the canonical input type per `Stage.input_type` (an ndarray
# at the right shape) and returns the canonical output type. The runner
# is responsible for hashing, dual-writing, and decoding/encoding bytes
# at the disk boundary.
#
# `decode_source` / `initial_crop` / `manual_deskew_pre` are pass-through
# stages at this iteration: the runner already cv2.imdecodes parent bytes
# before calling the impl (so `decode_source` is identity in ndarray
# space), and `initial_crop` / `manual_deskew_pre` honour their
# default-config "no-op" branches in `process_page_cpu` (no crop / no
# rotation) until ResolvedPageConfig plumbing lands. Carving them out
# now — even as no-ops — is the load-bearing change: it makes the chain
# runnable end-to-end from `ingest_source` through `invert` without
# manual SQLite seeding, which is the M2 smoke-test pass criterion.


def _grayscale_cpu(image: Any) -> Any:
    """Convert a 3-channel BGR ndarray to a 2-D grayscale ndarray.

    Wraps ``pd_book_tools.image_processing.cv2_processing.cv2_convert_to_grayscale``
    so the CPU image-processing path stays consistent with the monolithic
    process_page chain.
    """
    from pd_book_tools.image_processing.cv2_processing import (  # type: ignore[import-not-found]
        cv2_convert_to_grayscale,
    )

    return cv2_convert_to_grayscale(image)


def _threshold_cpu(image: Any) -> Any:
    """Otsu binarisation of a 2-D grayscale ndarray.

    The full `Stage.threshold` in the monolithic chain also handles a
    user-set ``threshold_level`` override — that lands when the runner
    wires `ResolvedPageConfig` into stage inputs (Slice 3 / M3). For
    now, plain Otsu is the documented behavior and the test fixture.
    """
    from pd_book_tools.image_processing.cv2_processing import (  # type: ignore[import-not-found]
        otsu_binary_thresh,
    )

    return otsu_binary_thresh(image)


def _invert_cpu(image: Any) -> Any:
    """Bitwise complement of a uint8 ndarray (`255 - x`).

    Wraps ``pd_book_tools.image_processing.cv2_processing.invert_image``.
    Idempotent under double-application (Q3-friendly: `invert(invert(x)) == x`).
    """
    from pd_book_tools.image_processing.cv2_processing import (  # type: ignore[import-not-found]
        invert_image,
    )

    return invert_image(image)


def _ingest_source_cpu(source_bytes: bytes) -> bytes:
    """Pass through the per-page source bytes unchanged.

    The runner reads the bytes from IStorage at the page's `source_key`
    and passes them in here. Persisting them at the canonical
    `pages/<page_id>/stages/ingest_source/output.png` path crystallises
    the chain root as a real on-disk artifact (Q3 every-intermediate-
    persistence) and gives `decode_source` a well-defined parent. The
    bytes themselves are written verbatim — the runner does NOT
    re-encode for output_type='image_bytes' stages.

    Note that the canonical filename is `output.png` regardless of the
    upload's actual format (jpg, jpeg, etc) — the writer's
    `OUTPUT_EXT_BY_TYPE` maps `image_bytes` to a single canonical
    extension. cv2.imdecode handles either format transparently when
    downstream stages read it back.
    """
    return source_bytes


def _decode_source_cpu(image: Any) -> Any:
    """Pass through the already-decoded source image unchanged.

    The runner cv2.imdecodes parent bytes before calling the impl, so by
    the time `decode_source` runs the input is already a 3-channel uint8
    ndarray. Persisting it as its own artifact (Q3 every-intermediate-
    persistence) gives `initial_crop` a well-defined parent path while
    keeping the registry impl pure in ndarray space.
    """
    return image


def _initial_crop_cpu(image: Any) -> Any:
    """Apply project/per-page initial-crop insets, or pass through at default.

    Mirrors `process_page_cpu`'s 4d branch: when the resolved
    `(left, right, top, bottom)` insets are all zero the image is
    forwarded unchanged. ResolvedPageConfig plumbing through the runner
    isn't wired yet (Q5 follow-up), so this iteration's impl always
    takes the no-crop branch — that's the documented default and the
    one the M2 smoke-test exercises. When the config plumbing lands the
    signature gains a `cfg: ResolvedPageConfig` kwarg and the actual
    `crop_edges` call moves here.
    """
    return image


def _manual_deskew_pre_cpu(image: Any) -> Any:
    """Apply the optional pre-crop manual rotation, or pass through at default.

    Mirrors `process_page_cpu`'s 4e branch: rotation only fires when
    `cfg.deskew_before_crop is not None`. At default the image is
    forwarded unchanged. Same ResolvedPageConfig follow-up as
    `initial_crop` — the impl learns about cfg later.
    """
    return image


# ─── Real implementations: post-invert chain (Slice 9–11) ───────────────────
#
# `find_content_edges` returns a bbox tuple (4 ints), not an ndarray.
# The runner handles this by branching on `Stage.output_type == 'bbox'`:
# it JSON-encodes the tuple and writes it as `output.json`.
#
# `crop_to_content` has two parents: an image (binary ndarray) and a bbox
# (4-tuple loaded from the JSON artifact). The runner passes both in the
# order declared in `Stage.depends_on`: (invert_image, bbox).
#
# `auto_deskew`, `morph_fill`, `rescale`, `canvas_map` are single-parent
# image→image transforms that carve out the remainder of the 4i–4n chain.


def _find_content_edges_cpu(image: Any) -> tuple[int, int, int, int]:
    """Find the bounding box of the content region in a binary inverted image.

    Returns (minX, maxX, minY, maxY) — the four edge coordinates passed to
    `crop_to_rectangle` in step 4j. Wraps `find_edges` from pd_book_tools
    using the same default parameters as `process_page_cpu` (4i).

    The runner encodes this as a JSON list and writes it to `output.json`.
    """
    from pd_book_tools.image_processing.cv2_processing import (  # type: ignore[import-not-found]
        find_edges,
    )

    return find_edges(image)


def _crop_to_content_cpu(image: Any, bbox: tuple[int, int, int, int]) -> Any:
    """Crop the binary image to the content bounding box (step 4j).

    `image` is the inverted binary ndarray (from `invert`);
    `bbox` is (minX, maxX, minY, maxY) from `find_content_edges`.

    Wraps `crop_to_rectangle`. The optional whitespace-pad step in
    `process_page_cpu` 4j fires only when `cfg.white_space_additional`
    is set — at default config (no override) it is skipped.
    ResolvedPageConfig plumbing into the runner lands later; this
    iteration always takes the no-pad branch.
    """
    from pd_book_tools.image_processing.cv2_processing import (  # type: ignore[import-not-found]
        crop_to_rectangle,
    )

    minX, maxX, minY, maxY = bbox
    return crop_to_rectangle(image, minX, maxX, minY, maxY)


def _auto_deskew_cpu(image: Any) -> Any:
    """Auto-deskew the binary content image (step 4k).

    Mirrors `process_page_cpu`'s 4k branch for the common case
    (no manual override, non-special alignment, standard orientation).
    ResolvedPageConfig skip conditions land when config plumbing is wired;
    for now, always attempt auto-deskew via `auto_deskew(pct=0.30)`.
    """
    from pd_book_tools.image_processing.cv2_processing import (  # type: ignore[import-not-found]
        auto_deskew,
    )

    out = auto_deskew(image, pct=0.30)
    # `auto_deskew` may return either a bare ndarray or a (ndarray, angle) tuple.
    return out[0] if isinstance(out, tuple) else out


def _morph_fill_cpu(image: Any) -> Any:
    """Apply morphological fill to close small gaps in text strokes (step 4l).

    Optional in `process_page_cpu` via `cfg.do_morph`; default is False,
    but wiring the impl now means the stage can run harmlessly via morph_fill
    at its default call — pd_book_tools' `morph_fill` is idempotent on
    already-clean binary images. ResolvedPageConfig plumbing will expose
    the do_morph toggle; until then the impl always runs.
    """
    from pd_book_tools.image_processing.cv2_processing import (  # type: ignore[import-not-found]
        morph_fill,
    )

    return morph_fill(image)


def _rescale_cpu(image: Any) -> Any:
    """Re-invert + rescale to canonical aspect ratio (step 4m).

    `process_page_cpu` calls `rescale_image(invert_image(img_deskewed), target_short_side=1000)`.
    The inversion here is intentional: `morph_fill` outputs a binary image with
    text=255/bg=0; `rescale_image` expects text=0/bg=255 (white-on-black).
    The inversion restores that convention before scaling.
    """
    from pd_book_tools.image_processing.cv2_processing import (  # type: ignore[import-not-found]
        invert_image,
        rescale_image,
    )

    return rescale_image(invert_image(image), target_short_side=1000)


def _canvas_map_cpu(image: Any) -> Any:
    """Map the rescaled image onto a canonical canvas (step 4n).

    Wraps `map_content_onto_scaled_canvas` with the default alignment
    (Alignment.DEFAULT) and the canonical h/w ratio used in `process_page_cpu`.
    ResolvedPageConfig plumbing (alignment override, page_h_w_ratio from
    per-page config) lands when the runner passes cfg into impls; for now,
    DEFAULT alignment and ratio=1.294 (US Letter ~8.5:11) are the documented
    defaults and the ones the M2/Slice-11 smoke-test exercises.

    Returns an ndarray; the runner encodes it to PNG (output_type='image_bytes').
    """
    from pd_book_tools.image_processing.cv2_processing import (  # type: ignore[import-not-found]
        Alignment,
        map_content_onto_scaled_canvas,
    )

    return map_content_onto_scaled_canvas(
        image,
        force_align=Alignment.DEFAULT,
        height_width_ratio=1.294,
    )


# ─── Registry assembly ──────────────────────────────────────────────────────

# Real implementations registered for cpu. Keys must be in `PAGE_STAGE_IDS`.
_REAL_CPU_IMPLS: dict[str, Callable[..., Any]] = {
    "ingest_source": _ingest_source_cpu,
    "decode_source": _decode_source_cpu,
    "initial_crop": _initial_crop_cpu,
    "manual_deskew_pre": _manual_deskew_pre_cpu,
    "grayscale": _grayscale_cpu,
    "threshold": _threshold_cpu,
    "invert": _invert_cpu,
    # Slice 9–11: post-invert proofing chain through canvas_map.
    "find_content_edges": _find_content_edges_cpu,
    "crop_to_content": _crop_to_content_cpu,
    "auto_deskew": _auto_deskew_cpu,
    "morph_fill": _morph_fill_cpu,
    "rescale": _rescale_cpu,
    "canvas_map": _canvas_map_cpu,
}


def _build_registry() -> dict[str, dict[str, Callable[..., Any]]]:
    """Materialise STAGE_IMPL once at import time.

    For every canonical stage_id, register a `'cpu'` entry — either the
    real implementation if listed in `_REAL_CPU_IMPLS`, or a placeholder
    that raises `StageNotImplemented`.

    CUDA entries are intentionally absent at M2 Slice 2; later slices
    register them alongside the cpu ones (Q10 auto-bridge handles the
    fallback from a `'cuda'` request to `'cpu'` when the cuda entry is
    missing — that fallback lives in the runner, not here).
    """
    registry: dict[str, dict[str, Callable[..., Any]]] = {}
    for sid in PAGE_STAGE_IDS:
        impl = _REAL_CPU_IMPLS.get(sid) or _make_placeholder(sid)
        registry[sid] = {"cpu": impl}
    return registry


STAGE_IMPL: dict[str, dict[str, Callable[..., Any]]] = _build_registry()
"""Module-level dispatch table. Keys: stage_id (str) → device (str) → callable.

Stable in-process; no expectation of mutation at runtime. Tests assert
exhaustiveness via `PAGE_STAGE_IDS`.
"""


def get_stage_impl(stage_id: str, device: str) -> Callable[..., Any]:
    """Return the callable registered for ``(stage_id, device)``.

    Raises ``KeyError`` for unknown stage_ids or unregistered devices —
    callers are expected to validate first (the runner does, before it
    starts the dual-write transaction).
    """
    devices = STAGE_IMPL[stage_id]
    return devices[device]
