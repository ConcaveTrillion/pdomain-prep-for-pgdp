# Screen: Application Shell

**Route:** all routes
**Component:** `components/shell/AppShell.tsx`, `TopNav.tsx`, `PageHeader.tsx`

## Purpose

Persistent chrome that frames every page. Provides navigation, global search,
job notifications, and user identity.

## Layout

CSS grid: 3 rows (auto / 1fr / auto). Full 100dvh height.

- **Row 1 (TopNav):** ~56px dark bar. Left: amber "pgdp-prep" brand word. Center: search pill
  "Search pages… ⌘K". Right: bell icon (with count badge), user avatar (opens dropdown).
- **Row 2 (main):** scrollable content area, bg-page.
- **Row 3 (ServerInfoFooter):** ~32px, server URL + copy button.

## Component Inventory

| Component | Description |
|---|---|
| `TopNav` | Dark header: brand, search pill, OpenTasksPopover (bell), UserMenu |
| `SearchModal` | Full-screen search dialog (Cmd+K): FTS5 query + snippet results |
| `OpenTasksPopover` | Bell popover: list of in-progress/attention items across all projects |
| `HotkeyHelpModal` | ? key: keyboard shortcut reference sheet |
| `UserMenu` | Avatar dropdown: username, theme toggle (light/dark), sign out |
| `ServerInfoFooter` | Bottom bar: server URL (selectable) + copy icon |

## Key Interactions

- Cmd+K → opens SearchModal (global FTS5 across all OCR text)
- ? → opens HotkeyHelpModal
- Bell click → OpenTasksPopover with task list
- Avatar → UserMenu with theme toggle and sign out
- Brand word → navigates to `/`

## Open Design Questions

- Should the bell show separate counts for "jobs running" vs "pages needing review"?
- Should TopNav include a breadcrumb for deep routes (project → page)?
