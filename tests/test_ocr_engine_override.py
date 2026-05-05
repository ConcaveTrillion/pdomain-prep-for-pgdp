"""Tests-first: per-call `engine=` override on `core.ocr.ocr_page`.

`OcrPageRequest.engine` was already on the wire shape, but the ocr_page
function ignored it and always trusted `cfg.ocr_engine`. These tests lock
in that the kwarg now overrides the resolved config for that one call.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pd_prep_for_pgdp.core.models import (
    AlignmentOverride,
    PageType,
    ResolvedPageConfig,
    SystemDefaults,
)


def _cfg(*, engine: str = "doctr") -> ResolvedPageConfig:
    return ResolvedPageConfig(
        text_threshold=140,
        page_h_w_ratio=1.65,
        fuzzy_pct=0.02,
        pixel_count_columns=150,
        pixel_count_rows=75,
        ocr_bbox_edge_min_words=5,
        ocr_engine=engine,  # type: ignore[arg-type]
        ocr_model_key=None,
        ocr_dpi=150,
        initial_crop_all=(0, 0, 0, 0),
        ocr_crop=(0, 0, 0, 0),
        page_type=PageType.normal,
        alignment=AlignmentOverride.default,
        initial_crop=None,
        white_space_additional=None,
        threshold_level=None,
        skip_auto_deskew=True,
        deskew_before_crop=None,
        deskew_after_crop=None,
        do_morph=False,
        skip_denoise=False,
        use_ocr_bbox_edge=False,
        rotated_standard=False,
        single_dimension_rescale=False,
    )


def test_engine_kwarg_overrides_resolved_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from pd_prep_for_pgdp.core import ocr as ocr_module

    captured: dict[str, Any] = {}

    def fake_tesseract(image_path: Path, *, cfg: ResolvedPageConfig, system: SystemDefaults):
        captured["used"] = "tesseract"
        captured["engine_in_cfg"] = cfg.ocr_engine
        return ocr_module.OcrPageResult(text="t", words=[], page=None)

    monkeypatch.setattr(ocr_module, "_ocr_page_tesseract", fake_tesseract)

    # Resolved config says doctr, but the call passes engine="tesseract".
    ocr_module.ocr_page(
        Path("/tmp/does-not-need-to-exist.png"),
        cfg=_cfg(engine="doctr"),
        system=SystemDefaults(),
        engine="tesseract",
    )
    assert captured["used"] == "tesseract"
    assert captured["engine_in_cfg"] == "tesseract"


def test_no_engine_kwarg_uses_resolved_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from pd_prep_for_pgdp.core import ocr as ocr_module

    captured: dict[str, Any] = {}

    def fake_tesseract(image_path: Path, *, cfg: ResolvedPageConfig, system: SystemDefaults):
        captured["used"] = "tesseract"
        return ocr_module.OcrPageResult(text="t", words=[], page=None)

    monkeypatch.setattr(ocr_module, "_ocr_page_tesseract", fake_tesseract)

    # No engine kwarg + cfg says tesseract -> tesseract path runs.
    ocr_module.ocr_page(
        Path("/tmp/x.png"),
        cfg=_cfg(engine="tesseract"),
        system=SystemDefaults(),
    )
    assert captured["used"] == "tesseract"
