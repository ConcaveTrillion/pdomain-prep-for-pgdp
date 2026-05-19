# Workflow: Hyphen-Join Rule Workbench

**Priority:** P2
**Affects:** `08-settings.md` (replace textarea with library UI) + new per-book panel in configure settings tab
**Audience:** Content provider during text post-processing

## Problem

The legacy notebook had a shared `hyphenated-line-join.json` with beginnings, endings,
always-join, and always-hyphenate rule lists accumulated across books. The app has
only a raw textarea in Settings. There is no mismatched-dash detection report, no
way to discover new rules from the current book's text, and no cross-book rule library.

## Goal

A structured hyphen-join workbench that:

1. Shows which cross-line hyphens were joined/left in the current book's OCR text
2. Lets the user confirm/deny individual joins to build the rule library
3. Surfaces a mismatched-dash detection report

## Step-by-Step Flow

1. After `text_post_process` stage completes for all pages, a hyphen analysis pass
   extracts all cross-line hyphen cases from the OCR text.
2. "Hyphen Report" panel in Settings tab of ProjectConfigurePage shows:
   - Auto-joined count (applied from rule library)
   - Undecided count (no matching rule; shown as review list)
   - Mismatched dash count (e.g., "arding-ly" appears both joined and un-joined)
3. User reviews undecided cases one at a time:
   - Shows: "end-\norsham" → proposed join: "endorsham" | keep hyphen: "end-orsham"
   - Buttons: "Always join" (adds to library) / "Always keep hyphen" / "Skip" / "This book only"
4. Mismatched dash report shows pairs: "bosham (×3)" alongside "bos-ham (×1)" → resolve.
5. On resolve, `text_post_process` re-runs on affected pages.

## Happy Path Mockup Spec

### Hyphen Report Panel (Settings tab, ProjectConfigurePage)

Collapsible Accordion section: "Hyphen Join Report".
Header row: three StatTiles — "42 auto-joined | 7 undecided | 3 mismatched"

Expand: two sub-sections.

**Undecided hyphens list:**

Each row:

- Left: context snippet — "…Sussex _end-↵orsham_ road…" (word highlighted, line break shown as ↵)
- Center: proposed join highlighted in green ("endorsham") OR original hyphen in amber ("end-orsham")
- Right: three buttons: "Always join ✓" (green) | "Keep ✗" (red) | "This book only ↗" (ghost)

"Apply all 'Always join'" batch button at bottom.

**Mismatched dash report:**

Two-column table: "Joined form" vs "Hyphenated form" vs "Count each".
Click either form → links to a TextReviewPage search for that word.

### Shared Rule Library (Settings page)

Replace scannos textarea with a tabbed panel:

- Tab "Scannos": table of find/replace pairs (add/delete rows, import/export CSV)
- Tab "Hyphen rules": four sub-lists (beginnings / endings / always-join / always-hyphenate),
  each as a tag-input component. Import from JSON. Export as JSON.

## Open Design Questions

- Should the rule library be workspace-global (across all books) or per-installation?
- Should new rules auto-trigger a re-run of `text_post_process` on the current book?
