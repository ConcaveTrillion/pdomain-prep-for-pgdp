# Screen: Crops Grid

**Route:** `/projects/:projectId/crops`
**Component:** `pages/CropsGridPage.tsx`
**Screenshot:** `screenshots/06-crops-grid.png`

## Purpose

Batch crop review pass. Shows canvas_map stage thumbnails for every page in a
responsive grid so the user can visually scan for deskew failures, over-crops,
or alignment issues without clicking into each page's workbench individually.

## Layout

PageHeader "Crop Review" + back-to-project link. Below: responsive grid, 4 columns
at 1440px. Each cell: canvas_map thumbnail (square, object-fit: contain, white bg),
page prefix label (mono, below image), status dot (stage status), clickable → workbench.
Infinite scroll, 200 per page.

## Key Interactions

- Click any grid cell → navigates to `/projects/:id/pages/:idx0` (workbench, auto-selects canvas_map stage)

## Open Design Questions

- **WF-10:** Should this grid support bulk marking (e.g., "flag these pages for manual review")?
- Should cells show which specific issue was detected (e.g., "auto-deskew skipped", "near-margin content")?
