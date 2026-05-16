# Screen: Page Workbench

**Route:** `/projects/:projectId/pages/:idx0`
**Component:** `pages/PageWorkbenchPage.tsx`
**Screenshots:** `screenshots/04-workbench-view.png`, `screenshots/04-workbench-split-mode.png`, `screenshots/04-workbench-illustration-mode.png`

## Purpose

Single-page interactive pipeline editor. The user inspects each page's processing
output, tweaks per-page config, re-runs individual stages, draws splits and
illustration regions, and marks the page reviewed. Highest-density UI in the app.

## Layout

Four vertical zones (top to bottom):

1. **Workbench header** (~48px): breadcrumb (Project / Page N of M), prev/next arrows,
   edit-mode selector (View / Split / Illustration / Rotate), "Mark reviewed" button.
2. **StageChainRail** (~72px): horizontal scrollable chip strip, one chip per stage (22 total).
   Each chip: colored status dot, stage name (abbreviated), lazy thumbnail for image stages.
3. **Main pane** (fills remaining height): split 60/40 — ArtifactViewer (left) / StageControlsPanel (right).
4. **TextReview section** (below main pane, collapsible): OCR text textarea with word-count, "Mark page reviewed" CTA.

### ArtifactViewer (left 60%)

Top bar: primary stage selector (synced to chip rail) + compare stage selector (dropdown).
Two side-by-side image panes (or text for non-image stages). Image pane supports
pinch-to-zoom / scroll-wheel zoom and Konva canvas overlay for word bboxes,
split regions, illustration regions.

### StageControlsPanel (right 40%)

Header: selected stage name + "Apply & Run" / "Apply & Run from here" buttons.
Body: dynamic form fields for the selected stage's `PageConfigOverrides`.

Fields visible depend on selected stage:

- **grayscale**: perceptual mode toggle (WF-11)
- **threshold**: threshold_level (0–255 slider + number input)
- **find_content_edges**: fuzzy_pct, pixel_count_columns, pixel_count_rows
- **auto_deskew**: skip_auto_deskew (checkbox), deskew_before_crop, deskew_after_crop (angles)
- **canvas_map**: force_align (Top/Center/Bottom/Default), white_space_additional (4 margins),
  single_dimension_rescale, rotated_standard
- **morph_fill**: do_morph (checkbox), skip_denoise (checkbox)
- **extract_illustrations**: format/size controls per region (WF-08)

## Edit Modes

| Mode | Canvas behavior |
|---|---|
| View | Read-only; click word bbox to select |
| Split | Draw rectangle bbox to define split regions; commit creates sibling pages |
| Illustration | Draw rectangle bbox to mark illustration regions |
| Rotate | Drag to set manual rotation angle |

## Component Inventory

| Component | Zone | Description |
|---|---|---|
| `StageChainRail` | rail | 22 chips, color-coded, click to select/run |
| `ArtifactViewer` | left pane | Image/text artifact display with stage comparison |
| `StageControlsPanel` | right pane | Dynamic per-stage config form |
| Konva canvas | left pane | Word bboxes, split regions, illustration regions |
| `WordBboxOverlay` | canvas layer | Colored bboxes for each OcrWord |
| TextReview textarea | bottom | Collapsible OCR text editor |

## Key Interactions

- Click chip → selects stage; ArtifactViewer + StageControlsPanel update
- Click chip "run" icon → runs that stage (sync or async)
- "Apply & Run" → saves overrides + re-runs selected stage
- "Apply & Run from here" → saves overrides + re-runs selected stage AND all downstream
- Draw bbox in Split mode → "Commit split" → creates N sibling pages
- Draw bbox in Illustration mode → adds region to illustration_regions list
- Click word bbox → selects word; "Delete selected" removes it
- Marquee drag → selects range of word bboxes
- prev/next arrows → navigate to adjacent pages

## Empty / Error States

- Stage not yet run: ArtifactViewer shows "Not run yet — click Run in the rail"
- Stage failed: ArtifactViewer shows error message + log excerpt
- Loading: skeleton shimmer in both panes

## Open Design Questions

- Should StageControlsPanel be a slide-out drawer on smaller viewports?
- Should the chip rail show elapsed time on the last run?
- Should "Apply & Run from here" show a preview of which stages will re-run?
