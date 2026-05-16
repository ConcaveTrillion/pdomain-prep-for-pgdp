# Screen: New Project (Modal)

**Route:** `/` (modal overlay)
**Component:** `pages/ProjectListPage.tsx → CreateProjectModal`
**Screenshots:** `screenshots/01-new-project-modal.png`, `screenshots/01-new-project-upload.png`

## Purpose

Two-step wizard to create a project and upload source images. Step 1: book name.
Step 2: source upload (currently zip only — P0.3 blocker: folder not yet supported).
After upload completes, ingest runs automatically and the user is navigated to
`/projects/:id/configure`.

## Layout

Radix Dialog, centered at 560px wide, 2-step wizard. Step indicator at top.
Step 1: single text input for book name + Next button.
Step 2: drag-drop zone (dashed border, cloud-upload icon) + file picker fallback.
Progress bar replaces drag-drop zone during upload. SSE streams ingest progress.

## Component Inventory

| Component | Location | Description |
|---|---|---|
| Dialog | overlay | Focus-trapped modal with Escape-to-close |
| StepIndicator | top of dialog | "1 — Name → 2 — Upload" breadcrumb |
| Input | step 1 | Book name text field |
| DropZone | step 2 | Drag-drop target for .zip file |
| Progress | step 2 | Upload + ingest progress bar |
| FormErrorBanner | bottom | sonner toast on error |

## State & Data

- **Step 1 state:** `bookName` (string)
- **Step 2 state:** `file` (File | null), `uploadProgress` (0–100), `ingestJobId`
- **API calls:** `POST /api/data/projects` → create; PUT (upload URL) → upload zip;
  `POST /api/gpu/ingest` → trigger ingest; SSE → ingest progress

## Key Interactions

- Type book name → Next → shows step 2
- Drag zip file onto zone OR click to browse → file selected
- Click "Start Upload" → progress bar animates; SSE updates ingest status
- Ingest complete → navigate to `/projects/:id/configure`
- Escape / X → close modal (confirms if upload in progress)

## Empty / Error States

- Name empty: Next button disabled
- Wrong file type: "Please upload a .zip file" error
- Upload fails: error banner + "Retry" button
- Ingest fails: "Ingest failed — see error below" with job log excerpt

## Open Design Questions

- **P0.3:** How should folder upload work? Options:
  - (a) Browser drag-drop a folder (webkitdirectory API, JSZip client-side)
  - (b) Multi-file picker (select all files in folder)
  - (c) Server-side: accept a path on the local filesystem (local-mode only)
- Should there be a step 3 for book metadata (author, language, clearance)?
- Should ingest progress show per-page thumbnails as they generate?
