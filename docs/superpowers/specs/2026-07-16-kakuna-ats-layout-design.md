# ATS PDF: Kakuna-style layout (photoless) + first-person summary

Date: 2026-07-16
Status: approved (user chose photoless variant; photos hurt real ATS parsing)

## Goal

Make the generated ATS PDF look like the Kakuna resume template (reference:
user's `kakuna.jpg`) while staying single-column and ATS-safe, and make the
rewritten summary read in first person instead of third-person past tense.

## Scope

1. **Header, centered** — name (large, bold), professional title under it,
   contact line (`location | phone | email`) below. No photo.
2. **Section rules** — every section heading is centered with a thin
   full-width horizontal line attached, separating it from the previous part.
3. **First-person summary** — the ATS rewrite prompt instructs the LLM to
   write the summary in first person ("ben dili"), active voice.
4. **New `title` field** — `CVData.title: str | None` (professional headline,
   e.g. "Senior Web Developer"). Parser extracts it; ATS rewrite may derive it
   from the most recent role when missing. Optional, so stored CVs still load.

## Non-goals

- Photo support (rejected: ATS parsers mishandle images).
- Kakuna's two-column experience layout (single column is ATS-safer).
- Web UI changes; the frontend keeps rendering the same JSON and just
  downloads the PDF.

## Implementation

- `api/app/schemas.py` — add `title` to `CVData`.
- `api/app/services/cv_parser.py` — add `title` to the extraction schema.
- `api/app/services/ats.py` — prompt: first-person summary + title
  derivation; `render_pdf()`: centered header block, centered headings with a
  full-width rule drawn under each heading.

## Testing

- Existing 44-test suite must stay green (optional field is
  backward-compatible).
- New assertions: `title` renders into the PDF (extract text with PyMuPDF),
  Turkish characters still render.
- Visual check: render a sample PDF, rasterize page 1, compare against
  kakuna.jpg proportions.
