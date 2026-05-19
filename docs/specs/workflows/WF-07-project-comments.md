# Workflow: PGDP Project Comments Generator

**Priority:** P3
**Affects:** New "Submission" section in Pipeline tab after build_package
**Audience:** Content provider / project manager

## Problem

PGDP requires project managers to write project comments describing any non-standard
formatting: plate pages, illustrations, split pages, poetry, sidenotes, headers,
small caps, blackletter. Writing these from scratch is time-consuming and easy to forget.

## Goal

Auto-generate a draft project comments block from the book's configuration
(page type counts, illustration regions, special page handling) that the
user can copy into PGDP's project creation form.

## Step-by-Step Flow

1. After build_package, "PGDP Submission" card appears in Pipeline tab.
2. Card has two sub-panels: Package section (download link) + Project Comments section.
3. Project Comments section: "Generate draft" button.
4. On click: backend inspects the project config — count plate pages, blank pages,
   illustration pages; detect special alignments; detect split pages; detect custom scannos applied.
5. Returns a structured draft in PGDP project comment format.
6. Draft shown in editable textarea. User edits inline.
7. "Copy" button copies to clipboard.

## Happy Path Mockup Spec

### Project Comments Card

Card header: "PGDP Project Comments" + "Generate draft" button (secondary).
After generate: textarea (10 rows) pre-filled with draft like:

  This project has 6 plate pages (b suffix: blank backs; p suffix: full-page
  illustrations). Plate pages should be left blank.

  Pages 93-94 are a full-width map; the image is included as i_p088_01.jpg.

Below textarea: character count + "Copy to clipboard" button.

## Open Design Questions

- Should the generator use Claude API to produce more natural prose?
- Should the comments follow a PGDP standard template format?
