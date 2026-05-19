# Workflow: Per-Book Regex Workbench

**Priority:** P2
**Affects:** Settings tab of `03-project-configure.md` (replaces raw textarea)
**Audience:** Content provider during text post-processing

## Problem

The legacy notebook had ad-hoc regex cells for book-specific text fixes. The app
has a "book-specific scannos" textarea in the settings tab, but no way to preview
matches before applying, apply multiple passes in sequence, or see a diff of what changed.

## Goal

A structured regex workbench for book-specific post-processing: write a regex,
preview matches across all pages' OCR text, apply it, see a diff.

## Step-by-Step Flow

1. User opens the "Regex" section in the Configure Settings tab.
2. Two text inputs: Find (regex, with `i` flag checkbox) + Replace (backreference-aware).
3. "Preview" button → scans all pages' OCR text, returns: match count + first 5 matches
   in context (snippet, with match highlighted).
4. User refines the regex until matches are correct.
5. "Apply to all pages" → runs find-replace across all text files + marks `text_post_process` dirty on affected pages.
6. Diff panel shows old→new for each affected page (collapsible per page).
7. User can add multiple regex passes as an ordered list; each has an enable/disable toggle.

## Happy Path Mockup Spec

### Regex Workbench Panel (in Configure Settings tab)

Header: "Text Regex Passes" + "Add pass" button.

**Pass row (each):**

Left: drag handle (reorder). Center: condensed display "s/pattern/replacement/i" (monospace).
Right: enable toggle + expand chevron.

**Expanded pass:**

- Find: text input (monospaced, full-width, `pattern` placeholder)
- Flags: checkboxes [i] case-insensitive, [m] multiline, [s] dot-all
- Replace: text input (monospaced, `$1 replacement` placeholder)
- Preview button → shows match count badge + first 5 snippets in a scrollable list
  (each snippet: "…context [MATCH] context…" with match in amber bg)
- Apply button → runs replacement + shows diff

**Diff panel (after apply):**

Collapsible list of affected pages (prefix label). Expand each → line diff:
removed lines in red bg, added lines in green bg (same styling as TextReviewPage LineDiffView).

## Open Design Questions

- Should "preview" run server-side or client-side?
