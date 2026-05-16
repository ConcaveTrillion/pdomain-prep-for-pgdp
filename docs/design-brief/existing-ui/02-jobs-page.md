# Screen: Jobs

**Route:** `/jobs`
**Component:** `pages/JobsPage.tsx`
**Screenshot:** `screenshots/02-jobs-page.png`

## Purpose

Global view of all background jobs across all projects. Users visit this when
something is running slowly, to diagnose a failure, or to check what's queued.
In local mode, jobs run immediately in-process; in managed mode they queue.

## Layout

Full-width single column. PageHeader "Jobs" with ToggleGroup filter (All /
Running / Queued / Done / Errored / Awaiting review) as a segmented control
in the header actions slot. Below: scrollable list of JobCard rows, newest first.
Polling at 5s for live updates.

## Component Inventory

| Component | Location | Description |
|---|---|---|
| ToggleGroup | header actions | Mutually exclusive filter: All/Running/Queued/Done/Errored/Review |
| JobCard | list rows | Type badge, project name, progress bar, status badge, log button, more ⋯ |
| Progress | in JobCard | Linear progress 0–100% |
| Badge | in JobCard | Status color-coded pill |
| EmptyState | center | "No jobs" when filter returns nothing |

## State & Data

- **Data fetched:** `GET /api/data/jobs?status=…` → `Job[]`, polling 5s
- **User-mutable state:** Filter selection

## Key Interactions

- Click filter chip → updates list
- Click "View logs" in JobCard → opens log drawer or expands card
- Click "⋯" on card → dropdown: cancel (if running/queued), retry (if errored)
- Click project name in JobCard → navigates to `/projects/:id`

## Empty / Error States

- No jobs match filter: "No [status] jobs" empty state
- Network error: banner with retry

## Open Design Questions

- Should jobs link directly to the specific page that failed (when job is per-page)?
- Should completed jobs be auto-hidden after N minutes?
