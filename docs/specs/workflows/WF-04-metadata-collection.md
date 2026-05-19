# Workflow: PGDP Metadata Collection

**Priority:** P2
**Affects:** New step in project creation wizard (step 3) OR new "PGDP Export" page
**Audience:** Content provider who is also the project manager on PGDP

## Problem

After downloading the package zip, the user must manually enter all book metadata
into PGDP's project creation form: author (Last, First), full title, language,
character suites (Latin/Greek/etc.), genre, difficulty, credits, and copyright
clearance key. None of this is collected by the app.

## Goal

Collect PGDP-required metadata and export it alongside the package zip as a
filled-in reference sheet the user can copy-paste into PGDP's form.

## Actor & Entry Points

- **Who:** Content provider after book name step
- **Enters from:** CreateProjectModal (optional step 3) or Settings-level project details

## Step-by-Step Flow

1. After book name step in CreateProjectModal, a new optional step 3 appears:
   "PGDP project details (optional — skip if not submitting to PGDP)".
2. User fills in fields (all optional at creation time, can be edited later).
3. Fields are saved to `ProjectConfig.pgdp_metadata`.
4. After `build_package` completes, a "PGDP Reference Sheet" section appears
   in the Pipeline tab alongside the download button.
5. Reference sheet shows all fields in copy-paste-friendly format.
6. "Copy all fields" button copies as tab-delimited text for easy form entry.

## Happy Path Mockup Spec

### Step 3 in CreateProjectModal (optional)

Dialog expands to show:

- "PGDP Project Details" header + "Skip →" link (right-aligned, ghost)
- Two-column form:
  - Left column: Author (Last, First) text input; Full title text input; Subtitle text input (optional label)
  - Right column: Language multi-select (primary + secondary); Character suites multi-checkbox
    (Basic Latin ✓ by default, Greek, Cyrillic, etc.)
- Second row: Genre dropdown (PGDP's list); Difficulty radio (Easy / Average / Hard)
- Credits section (collapsible "Advanced"): Image preparer, Text preparer,
  OCR tool (Select: DocTR / Tesseract / ABBYY / Other)
- Clearance key text input (PGLAF clearance key, 8-char format hint)
- "Save & continue" primary button

### PGDP Reference Sheet (Pipeline tab, after build_package)

Card below the download/validation panel. Header "PGDP Submission Reference".
Two-column layout of field/value pairs:

- Name of Work: [title] | Author: [Last, First]
- Language: [lang] | Character Suites: [list]
- Genre: [genre] | Difficulty: [level]
- Credits: [formatted] | Clearance: [key]

Footer: "Copy all" button → copies as formatted text for PGDP form.

## Open Design Questions

- Should the app validate the clearance key format (8-char alphanumeric)?
- Should there be a "Search Library of Congress" button to autofill title/author from ISBN?
- Should character suites be auto-detected from the OCR text?
