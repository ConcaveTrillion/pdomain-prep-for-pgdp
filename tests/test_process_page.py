"""Step 4 — proofing-image pipeline (CPU) integration test.

Locks in: blank-page short-circuit, normal-page output dimensions match
canonical aspect, and the pipeline does not raise on plausible inputs.
"""

from __future__ import annotations

import numpy as np
import pytest

from pd_prep_for_pgdp.core.models import (
    AlignmentOverride,
    PageType,
    ResolvedPageConfig,
)
from pd_prep_for_pgdp.core.pipeline.process_page import process_page_cpu


def _cfg(*, page_type: PageType = PageType.normal) -> ResolvedPageConfig:
    return ResolvedPageConfig(
        text_threshold=140,
        page_h_w_ratio=1.65,
        fuzzy_pct=0.02,
        pixel_count_columns=150,
        pixel_count_rows=75,
        ocr_bbox_edge_min_words=5,
        ocr_engine="doctr",
        ocr_model_key=None,
        ocr_dpi=150,
        initial_crop_all=(0, 0, 0, 0),
        ocr_crop=(0, 0, 0, 0),
        page_type=page_type,
        alignment=AlignmentOverride.default,
        initial_crop=None,
        white_space_additional=None,
        threshold_level=None,
        skip_auto_deskew=True,  # avoid auto-deskew on synthetic input
        deskew_before_crop=None,
        deskew_after_crop=None,
        do_morph=False,
        skip_denoise=False,
        use_ocr_bbox_edge=False,
        rotated_standard=False,
        single_dimension_rescale=False,
    )


def _png_with_text_block(h: int = 1200, w: int = 800) -> bytes:
    """Synthetic page: black rectangle on a white page (proxy for text)."""
    cv2 = pytest.importorskip("cv2")
    img = np.full((h, w, 3), 255, dtype=np.uint8)
    cv2.rectangle(img, (100, 100), (w - 100, h - 100), (0, 0, 0), -1)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return bytes(buf.tobytes())


def test_blank_page_short_circuits_to_blank_proof() -> None:
    pytest.importorskip("cv2")
    src = _png_with_text_block()
    out = process_page_cpu(src, _cfg(page_type=PageType.blank))
    assert out.proofing_png == out.pre_ocr_png  # identical for blank pages
    # canonical-aspect blank
    assert out.height > 0 and out.width > 0


def test_plate_b_short_circuits() -> None:
    pytest.importorskip("cv2")
    out = process_page_cpu(_png_with_text_block(), _cfg(page_type=PageType.plate_b))
    assert out.height > 0


def test_normal_page_pipeline_produces_canonical_aspect() -> None:
    cv2 = pytest.importorskip("cv2")
    src = _png_with_text_block(h=1200, w=800)
    out = process_page_cpu(src, _cfg())
    decoded = cv2.imdecode(np.frombuffer(out.proofing_png, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    assert decoded is not None
    h, w = decoded.shape
    # Canonical aspect 1.65; tolerate +/- 5% for cv2 rounding.
    aspect = h / w
    assert 1.65 * 0.95 <= aspect <= 1.65 * 1.05, f"aspect {aspect} not near 1.65"
    # Output has the proofing+pre_ocr identical (same bytes), per spec 4o.
    assert out.proofing_png == out.pre_ocr_png
