# Screen: Project Configure

**Route:** `/projects/:projectId`
**Component:** `pages/ProjectConfigurePage.tsx`
**Screenshots:** `screenshots/03-configure-pipeline-tab.png`, `screenshots/03-configure-pages-tab.png`, `screenshots/03-configure-settings-tab.png`

## Purpose

The main project hub after ingest. Three tabs: Pipeline (orchestration controls),
Pages (full page list with drag-reorder and status), Settings (book-level config).
Users spend most of their time here: kicking off pipeline runs, checking for errors,
managing page order.

## Layout

PageHeader: book name + breadcrumb back to projects. Below: Tabs (Pipeline / Pages
/ Settings) full-width. Tab content fills remaining viewport height.

### Pipeline Tab

Left column (~320px): RunAllDirtyPanel (primary CTA), AwaitingReviewBanner (amber,
conditional), OpenTasksBell popover, DiskCostBanner. Right column: stage status
summary grid (22 stage chips, project-level aggregate clean/dirty/failed counts).

### Pages Tab

Toolbar: multi-select checkbox, bulk page-type dropdown, "Show split parents" toggle.
Full-width table: one PageRow per page. Columns: drag handle, page number (mono),
source stem (truncated), page type badge, alignment badge, stage status dot, chevron.
Infinite scroll at 200 rows. Shift+click range-select.
Clicking a row opens PageDrawer (right-side slide-in panel) OR navigates to workbench.

### Settings Tab

Book-level config form: proof range (start/end idx), frontmatter range + starting
page number, bodymatter range + starting page number, initial crop margins (4 numbers),
OCR crop margins (4 numbers), page H/W ratio, book-specific scannos textarea,
book-specific hyphenation textarea. Save button.

## Component Inventory

| Component | Tab | Description |
|---|---|---|
| `RunAllDirtyPanel` | Pipeline | "Run all dirty stages" CTA + job progress |
| `AwaitingReviewBanner` | Pipeline | Amber alert: N pages need review |
| `OpenTasksPopover` | Pipeline | Bell icon + task list |
| `DiskCostBanner` | Pipeline | Stage artifact disk usage |
| `PageRow` | Pages | Drag handle, page #, stem, badges, status |
| `PageDrawer` | Pages | Right-side slide-in with per-page config |
| Book settings form | Settings | Proof range, frontmatter, bodymatter, crops |

## State & Data

- **Data fetched:** `GET /api/data/projects/:id` → `Project`; `GET .../pages` → `Page[]`
- **Optimistic reorder:** `localPageOrder` state, patched on drag-end

## Key Interactions

- "Run all dirty stages" → `POST /api/data/projects/:id/run-dirty` + SSE progress
- "Build package" → `POST .../build-package` + SSE; disabled until all reviewed
- Drag page row → optimistic reorder → `PATCH .../pages` with new order
- Shift+click rows → range select → bulk page-type dropdown applies to all
- Click page row → opens PageDrawer with that page's overrides
- Click workbench icon in PageDrawer → navigates to `/projects/:id/pages/:idx0`

## Empty / Error States

- Pages tab empty: "No pages yet — run ingest"
- Stage errors: page rows show red status dot; filter "Errors only" available

## Open Design Questions

- **WF-09 (page reorder):** Drag-reorder UX needs detailed wireframe
- **WF-03 (source quality):** Should this screen show a "pages needing attention" banner post-ingest?
- Should the Pipeline tab show a per-stage breakdown across all pages?
