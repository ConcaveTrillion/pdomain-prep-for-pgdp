# Workflow: Illustration Format & Size Controls

**Priority:** P2
**Affects:** `04-page-workbench.md` StageControlsPanel for extract_illustrations stage
**Audience:** Content provider

## Problem

PGDP has specific requirements per illustration type:

- Line art / maps: PNG preferred
- Photographs / halftones: JPG required
- Inline illustrations: ≤ 256 KB, max 5000×5000 px
- Linked illustrations: ≤ 1 MB, max 5000×5000 px

The app exports illustrations at native source resolution with no format enforcement.

## Goal

Let the user specify format (PNG/JPG), quality (for JPG), and size constraints
per illustration region; show estimated output size before running the stage.

## Step-by-Step Flow

1. User selects `extract_illustrations` stage in the StageChainRail.
2. StageControlsPanel shows the illustration region list for this page.
3. Each region shows: bbox coords, auto-detected category, format/quality controls.
4. User sets format (PNG / JPG) and JPG quality (0–100) per region.
5. Estimated output file size shown (calculated from bbox dimensions + format).
6. Warning badge if estimated size exceeds PGDP limits.
7. User clicks "Apply & Run" → stage runs with the new settings.

## Happy Path Mockup Spec

### StageControlsPanel — extract_illustrations stage

Header: "Illustration Regions" + "Add region manually" button.

Each region row (Accordion):

Header: "Region 1 — p045 area (320×480px)" + category badge ("illustration") + expand ▾

Expanded:

- Format: Select [PNG | JPG]
- Quality (JPG only): slider 60–100, number input
- Type: Select [Inline (≤256 KB) | Linked (≤1 MB) | Cover (≥1600×2560)]
- Estimated size: "~84 KB" (green) or "~312 KB ⚠ exceeds inline limit" (amber)
- Output preview: small thumbnail of the cropped region

Footer: "Apply & Run extract_illustrations" primary button

## Open Design Questions

- Should format auto-default based on auto-detected category (photo→JPG, line art→PNG)?
- Should the "type" (inline/linked) affect how the file is named in the output zip?
