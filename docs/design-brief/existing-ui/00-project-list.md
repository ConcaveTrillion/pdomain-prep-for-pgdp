# Screen: Project List

**Route:** `/`
**Component:** `pages/ProjectListPage.tsx`
**Screenshot:** `screenshots/00-project-list.png`

## Purpose

The home screen. Lists all projects the current user has created, with status
at a glance. Users land here after login and return here between books. A content
provider manages multiple books simultaneously; this screen is their dashboard.

## Layout

Single column, full width. TopNav across the top (amber brand, search, bell, user).
PageHeader below with "Projects" title and "+ New Project" button (primary, top-right).
Below that: a responsive grid of ProjectCards (3-column at 1440px, 2-col at 1024px,
1-col at 768px). Infinite scroll — 200 cards per page. No sidebar.

## Component Inventory

| Component | Location | Description |
|---|---|---|
| TopNav | header | Dark bar: brand word, search pill, bell, user menu |
| PageHeader | below nav | "Projects" h1 + "+ New Project" primary button |
| ProjectCard | grid | One card per project: name, page count, status badge, delete |
| CreateProjectModal | overlay | 2-step new-project dialog (see screen 01) |
| EmptyState | center | Illustration + CTA when no projects exist |

## State & Data

- **Data fetched:** `GET /api/data/projects?limit=200&cursor=…` → `Project[]`
- **User-mutable state:** Create (opens modal), Delete (AlertDialog confirmation)

## Key Interactions

- Click "+ New Project" → opens `CreateProjectModal`
- Click `ProjectCard` → navigates to `/projects/:id`
- Click delete icon on card → `AlertDialog` "Delete project? This is permanent." → `DELETE /api/data/projects/:id`
- Scroll to bottom → loads next 200 projects (infinite scroll)

## Empty / Error States

- No projects: centered illustration + "No projects yet" + "Create your first project" button
- Network error: inline error banner with retry button

## Open Design Questions

- Should ProjectCard show a thumbnail of the first page image?
- Should there be a search/filter bar above the grid for large project lists?
- Should projects be grouped by status (active / packaged / archived)?
