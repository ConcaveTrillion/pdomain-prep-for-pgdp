# Screen: Text Review

**Route:** `/projects/:projectId/pages/:idx0/review`
**Component:** `pages/TextReviewPage.tsx`
**Screenshot:** `screenshots/05-text-review.png`

## Purpose

Focused OCR text review for a single page. The user reads the OCR output, clicks
on problem words (highlighted in the word-bbox overlay), edits inline, and marks
the page reviewed. Also supports a "re-OCR diff" view to compare current text
against a fresh OCR pass.

## Layout

Two-pane layout (side-by-side at 1440px, stacked on mobile):

- **Left pane** (~50%): source proofing image with WordBboxOverlay. Split suffix selector
  (if page has splits) at top. Active word highlighted.
- **Right pane** (~50%): Textarea for OCR text (monospaced). Below textarea: word count,
  "Mark page reviewed" CTA, "Re-OCR & diff" button. If diff active: LineDiffView replaces textarea.

## Component Inventory

| Component | Pane | Description |
|---|---|---|
| `WordBboxOverlay` | left | Konva bbox overlay; click-to-select syncs with textarea position |
| ToggleGroup | left top | Split suffix selector (if splits exist) |
| Textarea | right | OCR text; monospace; auto-height |
| `LineDiffView` | right (diff mode) | Side-by-side diff of old vs new OCR text |
| Undo window | right | 5s countdown bar after word delete |

## Key Interactions

- Click word bbox → scrolls textarea to that word's position; word highlighted
- Click word in textarea → highlights corresponding bbox
- Edit textarea → marks page dirty (unsaved)
- "Save" (auto or explicit) → `PUT /api/data/pages/:idx0/text`
- "Delete word" (via bbox click + delete button) → removes word from OcrWord list + text
- Undo window (5s) → can reverse last delete
- "Mark page reviewed" → `POST .../review` → transitions to clean; redirects to review queue or next page
- "Re-OCR & diff" → runs OCR again + shows diff vs current text
- Escape → exits diff view back to textarea

## Open Design Questions

- Undo strategy: server-side `OcrWord.deleted` flag, or client debounce window?
- Should there be a "copy clean text to clipboard" button?
