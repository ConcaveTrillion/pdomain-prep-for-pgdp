# Workflow: Settings Page Enhancements

**Priority:** P2
**Affects:** `08-settings.md` (complete redesign of scannos + hyphenation sections)
**Audience:** Content provider

## Problem

The Settings page has raw textareas for scannos (tab-delimited find/replace) and
hyphenation (word list). These are error-prone to edit and don't support bulk
import/export, per-entry enable/disable, or testing a scanno against sample text.

## Goal

Replace raw textareas with structured, manageable rule library panels.

## Happy Path Mockup Spec

### Scannos Library (in Settings)

Tabbed panel header: "Scannos" tab | "Hyphen Rules" tab (see WF-05)

Scannos tab:

- Filter bar: search input + "Language" Select + "Category" Select
- Rule table (sortable):

| Find (regex) | Replace | Category | Lang | Enabled | Actions |
|---|---|---|---|---|---|
| "1n" | "in" | OCR errors | All | ✓ | edit / delete |

- "Add rule" button → inline form row
- "Import JSON / CSV" button → file picker → preview + confirm
- "Export" button → downloads as JSON or CSV

Each rule row editable inline (click to edit Find/Replace fields).
Enable/disable toggle per row (preserves rule without deleting).

## Open Design Questions

- Should the global scanno library be separate from per-book scannos?
- Should there be a "test rule" button that applies a scanno to a pasted text sample?
