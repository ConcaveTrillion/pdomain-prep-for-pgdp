# Screen: Project Review Queue

**Route:** `/projects/:projectId/review`
**Component:** `pages/ProjectReviewQueuePage.tsx`
**Screenshot:** `screenshots/07-review-queue.png`

## Purpose

Filtered list of pages awaiting text review before `build_package` can resume.
The user works through this queue page-by-page until it is empty, at which point
the parked build_package job auto-resumes.

## Layout

PageHeader "Review Queue" + count badge ("12 pages remaining"). Amber
ReviewQueueBanner below header. Then: same PageRow list as the Pages tab of
ProjectConfigurePage, filtered to `text_review.status = dirty`. "Review next
page →" CTA navigates to the first page in queue.

## Key Interactions

- "Review next page →" → navigates to `/projects/:id/pages/:idx0/review` for first unreviewed page
- Each page in list is clickable → navigates directly to that page's review
- When queue empties: banner changes to "All pages reviewed — package resuming" + auto-redirects
