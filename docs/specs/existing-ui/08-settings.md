# Screen: Settings

**Route:** `/settings`
**Component:** `pages/SettingsPage.tsx`
**Screenshot:** `screenshots/08-settings.png`

## Purpose

System-wide defaults that apply to all new projects. Power-user screen.
A content provider sets these once when they install the app, then rarely revisits.
Currently covers: OCR engine, layout detector, scannos list, hyphenation list.

## Layout

Single column, 640px max-width centered. PageHeader "Settings". Sections separated
by `Separator`. Each section: heading + form fields. Save button at bottom.

## Component Inventory

| Component | Location | Description |
|---|---|---|
| Select | OCR engine | Dropdown: "DocTR (default)", "Tesseract" |
| Select | Layout detector | Dropdown: detector model names |
| Textarea | Scannos | Tab-delimited find→replace pairs, one per line |
| Textarea | Hyphenation | Word list for cross-line hyphen joining |
| Button (primary) | bottom | "Save settings" |

## State & Data

- **Data fetched:** `GET /api/data/settings` → `SystemDefaults`
- **Draft state:** local copy edited before save
- **Save:** `PUT /api/data/settings`

## Key Interactions

- Edit any field → "Save settings" becomes enabled
- Click Save → `PUT` + success toast

## Empty / Error States

- Load error: error banner

## Open Design Questions

- **WF-12:** Scannos and hyphenation lists should become first-class libraries, not raw textareas.
- Should there be per-language settings sections?
- Should settings show a "test OCR on sample image" affordance?
