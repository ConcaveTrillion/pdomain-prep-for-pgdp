"""Cover the small helpers in `core.illustrations`.

- `_map_region_type` maps decoration/figure/table region types onto the
  spec-05 string fields,
- `synthesise_plate_region` produces a full-page region for plate_p
  pages whose source dimensions are known,
- `regions_for_page` returns user-configured regions when present,
  falls back to the synthesised plate region when needed, and returns
  [] otherwise.
"""

from __future__ import annotations

from pd_prep_for_pgdp.core.illustrations import (
    _map_region_type,
    regions_for_page,
    synthesise_plate_region,
)
from pd_prep_for_pgdp.core.models import (
    IllustrationRegion,
    PageRecord,
    PageType,
    SystemDefaults,
)

# ── _map_region_type ───────────────────────────────────────────────────────


class _RT:
    def __init__(self, name: str) -> None:
        self.name = name


def test_map_region_type_decoration() -> None:
    assert _map_region_type(_RT("DECORATION")) == "decoration"


def test_map_region_type_figure() -> None:
    assert _map_region_type(_RT("Figure")) == "illustration"


def test_map_region_type_table() -> None:
    assert _map_region_type(_RT("table")) == "illustration"


def test_map_region_type_unknown_falls_through_to_illustration() -> None:
    assert _map_region_type(_RT("UnknownThing")) == "illustration"


# ── synthesise_plate_region ────────────────────────────────────────────────


def test_synthesise_plate_region_for_plate_p_page() -> None:
    page = PageRecord(project_id="p", idx0=0, prefix="p001", source_stem="src1", page_type=PageType.plate_p)
    region = synthesise_plate_region(page, source_dimensions=(2000, 1500))
    assert region.index == 1
    assert region.type == "plate"
    assert region.L == 0 and region.T == 0
    assert region.R == 1500 and region.B == 2000  # full-page extent
    assert region.output_format == "jpg"


def test_synthesise_plate_region_for_non_plate_page_uses_illustration_type() -> None:
    """Defensive: if synthesise_plate_region is called for a non-plate
    page, the type falls back to "illustration"."""
    page = PageRecord(project_id="p", idx0=0, prefix="p001", source_stem="src1")
    region = synthesise_plate_region(page, source_dimensions=(100, 50))
    assert region.type == "illustration"


# ── regions_for_page ───────────────────────────────────────────────────────


def test_regions_for_page_returns_configured_regions() -> None:
    page = PageRecord(
        project_id="p",
        idx0=0,
        prefix="p001",
        source_stem="src1",
        illustration_regions=[
            IllustrationRegion(index=1, L=0, R=10, T=0, B=10, output_format="jpg"),
        ],
    )
    out = regions_for_page(page, system=SystemDefaults())
    assert len(out) == 1
    assert out[0].index == 1


def test_regions_for_page_synthesises_for_plate_p_with_dimensions() -> None:
    page = PageRecord(project_id="p", idx0=0, prefix="p001", source_stem="src1", page_type=PageType.plate_p)
    out = regions_for_page(page, system=SystemDefaults(), source_dimensions=(800, 600))
    assert len(out) == 1
    assert out[0].type == "plate"


def test_regions_for_page_returns_empty_for_normal_page_with_no_regions() -> None:
    page = PageRecord(project_id="p", idx0=0, prefix="p001", source_stem="src1")
    out = regions_for_page(page, system=SystemDefaults())
    assert out == []


def test_regions_for_page_plate_p_without_dimensions_returns_empty() -> None:
    """Without source_dimensions we can't synthesise — return [] rather
    than guess at the page extent."""
    page = PageRecord(project_id="p", idx0=0, prefix="p001", source_stem="src1", page_type=PageType.plate_p)
    out = regions_for_page(page, system=SystemDefaults())
    assert out == []
