# ATS CV Engine: One Rule Set, Richer Structure

**Goal:** Make the ATS rewrite produce the CV the product promises — single
column, standard headings, projects and achievements included, bullets that lead
with a verb, skills in the right category, nothing invented — and make the
assisted-apply flow obey the same rules instead of its own thinner ones.

**Non-goals.** No new routes. No change to how CVs are uploaded, parsed into
storage, or scored. No redesign of the ATS page beyond the two result panels
described below. The OXBLOOD identity and the app shell stay exactly as they are.

## Why this, and not a prompt tweak

`api/app/services/ats.py:8` is a nineteen-line system prompt. It asks for
"concise bullet-style descriptions" and "no invented facts", and it is the only
place in the codebase where ATS rules exist at all. Four things follow from that,
each verifiable in the source:

1. **The schema cannot hold an ATS CV.** `CVData` (`api/app/schemas.py:28`) has no
   projects, no achievements, no per-experience location, and certifications are
   a bare `list[str]`. A rewrite prompt cannot emit a Projects section into a
   schema with no field for it.
2. **Experience descriptions are one string.** `Experience.description` is a
   single free-text field, so "3-5 bullets, strong verb first" is a request the
   renderer cannot honor and the model cannot express.
3. **The parser never looked for the missing data.** `cv_parser.py:4` extracts
   nine fields; projects and achievements are not among them. Even a perfect
   rewrite prompt would find nothing to reorganize, and the accuracy rule
   forbids inventing it.
4. **The apply flow has its own, weaker rules.** `apply.py:30` optimizes the CV
   for a posting with one line of guidance — "NEVER invent facts … only reorder,
   reword and emphasize". None of the categorization, section-structure, or
   date-consistency rules reach it. The same CV therefore comes out of
   `/apply/prepare` at a visibly lower standard than out of `/ats/rewrite`.

So the prompt is the smallest part of this. The work is schema, parser, prompt,
renderer, and the two result surfaces — in that dependency order.

## The data model

`api/app/schemas.py`. No existing field is removed, and every field keeps
accepting the data already written to it — `certifications` changes type but not
what it will parse (see below). Stored `parsed_data` JSON in Supabase keeps
loading without a migration.

Two new models:

```python
class Project(BaseModel):
    name: str
    kind: str | None = None          # academic | personal | freelance | professional
    technologies: list[str] = []
    bullets: list[str] = []

class Certification(BaseModel):
    name: str
    issuer: str | None = None
    date: str | None = None
```

`kind` exists as its own field, not as prose inside a bullet, because accuracy
rule 5 forbids presenting an academic project as commercial client work. A
separate field is a thing a test can assert on.

Extended fields:

| Field | Now | After |
|---|---|---|
| `Experience` | `description: str \| None` | adds `location: str \| None`, `bullets: list[str]` |
| `Education` | `degree, school, year` | adds `location: str \| None`, `start_date: str \| None`, `details: list[str]` |
| `CVData.certifications` | `list[str]` | `list[Certification]` |
| `CVData.projects` | — | `list[Project]` |
| `CVData.achievements` | — | `list[str]` |

`Education.details` is a flat list rather than one field per concept (GPA,
honors, scholarship, thesis). The source CV decides which of those exist; a
schema with four mostly-null fields invites the model to fill them.

**Backward compatibility, two mechanisms:**

- `Experience.description` stays. Rows written before this change have
  `description` set and `bullets` empty; the renderer prefers `bullets` and falls
  back to `description`. The rewrite always writes `bullets`.
- `certifications` changes type without breaking old data: a
  `field_validator(mode="before")` coerces a plain string into
  `Certification(name=...)`, so `["AWS SCA", "Scrum Master"]` still loads. The
  rejected alternative was a second `certification_details` field, which would
  have kept the same fact in two places.

`languages` stays `list[str]`. The source prompt gives it no format, and level
information — where the source CV has it — survives inside the string
("İngilizce (C1)"). Structuring it buys a job-requirement comparison we are not
building.

`cv_parser.py` extends to extract projects, achievements, structured
certifications, experience bullets and locations, and education details. Without
this the new sections stay permanently empty.

## The prompt

One rule set, two compositions, in a new module `api/app/services/ats_prompt.py`:

```python
ATS_RULES                         # the full rule text, one constant
build_rewrite_system(language)    # /ats/rewrite — no posting
build_apply_system(language)      # /apply/prepare — posting-aware
```

`build_apply_system` layers the posting-optimization rules and the existing
form-answering and cover-letter instructions on top of `ATS_RULES`. Both call
sites then share the accuracy rules, the section structure, the skill
categorization rules, and the date-format rules — none of which reach the apply
flow today.

**The rules are written in English.** Output language is unaffected: it stays
governed by the `{language}` parameter, and Turkish CVs keep coming out Turkish.
This follows the repo convention that file contents are English, and matches
every existing prompt in `api/app/services/`.

**The rules are condensed, not shortened.** The source specification runs ~2,400
words. Every normative rule survives; what collapses is repetition and the
worked examples (the "weak phrasing → stronger phrasing" pair becomes one line).
Two reasons: the full text would add roughly 3,000 tokens to every `/ats/rewrite`
and `/apply/prepare` call, and — the larger risk — a long prompt dilutes the
rules that matter most. The accuracy rules are stated once, near the top.

**`/ats/rewrite` takes no job description.** The ATS page has no posting input,
and posting-aware optimization is what `/apply/prepare` is for. The source
specification's "the posting may be absent" branch is exactly this case.

### Response shape

| Endpoint | Now | After |
|---|---|---|
| `/ats/rewrite` | `{cv}` | `{cv, verification_required[], optimization_summary[]}` |
| `/apply/prepare` | `{cv, changes[], cover_letter, answers[], company, title}` | adds `verification_required[]` |

`PrepareOut.changes` already is the optimization summary under a different name.
Reusing it keeps `ApprovalScreen` working and avoids two fields meaning one
thing.

## The PDF

`render_pdf` in `api/app/services/ats.py:55` moves to the layout the source
specification describes:

```
KEREM SALIM
Backend Developer

İstanbul, Türkiye | +90 5xx xxx xx xx | mail@x.com
linkedin.com/in/... | github.com/...

İŞ DENEYİMİ
────────────────────────────────────────
Backend Developer
Acme Yazılım | İstanbul, Türkiye
Oca 2024 - Devam Ediyor
  • …
```

Name, title, and headings left-aligned; the contact block split across two lines
so long LinkedIn and GitHub URLs stop competing for one line; the full-width rule
under each heading kept from the current design. Bullets render with a `• `
prefix and a hanging indent, wrapping through `multi_cell`.

**Section order is fixed:** Summary → Skills → Experience → Projects → Education
→ Certifications → Achievements → Languages. Empty sections are already skipped,
which is what makes this sufficient: a new graduate has no experiences, so
Education and Projects rise to the top on their own. The alternative — having the
model return a `section_order` list — was rejected because an unknown or
duplicated section name is a new failure mode in the renderer, and the fixed
order plus skipping already produces the intended result.

`HEADINGS` gains `projects` and `achievements` in both `tr` and `en`, and
`summary` becomes "PROFESYONEL ÖZET" / "PROFESSIONAL SUMMARY".

**The skills heading stays "BECERİLER" / "SKILLS", not "TEKNİK BECERİLER".** The
source specification's structure list says Technical Skills, but `ats.py:16-24`
deliberately derives skill group names from the person's profession so a nurse or
an accountant is not given technology categories. A hard "Technical Skills"
heading would be wrong on exactly those CVs. The specification's own skills
section offers its categories as candidates rather than requirements, so this
reading is consistent with it.

## The surfaces

- **ATS page** (`web/src/app/(app)/ats/page.tsx`): two blocks beside the result —
  "Doğrulaman gerekenler" (`verification_required`) and "Yapılan düzenlemeler"
  (`optimization_summary`). Neither goes into the PDF.
- **Approval screen** (assisted apply): the existing `changes` list gains a
  verification list next to it.
- **CV detail page** (`web/src/app/(app)/cv/[id]/page.tsx`): renders projects,
  achievements, and structured certifications. Without this the newly parsed data
  is invisible everywhere in the product.
- `web/src/types/api.ts` mirrors the schema; `tr` and `en` message files gain the
  new labels.

## Testing

Test-first, per the repo's existing pytest and vitest suites.

**API (pytest):**
- A pre-change `parsed_data` fixture — including `certifications` as plain
  strings and experiences with `description` but no `bullets` — loads into the new
  `CVData` unchanged.
- `build_apply_system` includes the posting block; `build_rewrite_system` does
  not.
- `/ats/rewrite` returns all three keys, with a fake LLM.
- The parser extracts projects and achievements from a fixed CV text, with a fake
  LLM returning the new shape.
- `render_pdf` produces non-empty bytes for a CV with projects, achievements and
  bullets; and falls back to `description` when `bullets` is empty.

**Web (vitest):**
- The ATS page renders both panels when the API returns them, and neither when
  the lists are empty.
- The CV detail page lists projects and structured certifications.

## Risks

- **Prompt dilution.** More rules can mean weaker adherence to any one of them.
  The accuracy rules are the ones that matter; they lead the prompt, and the
  "no invented facts" tests are the ones to watch after the first real run.
- **Parser regression.** Extending `cv_parser.py` changes a prompt that currently
  works. Its existing tests must keep passing unchanged.
- **Token cost.** Both flows pay for the shared rules on every call, against a
  `DAILY_AI_LIMIT` of 20. Condensing the rules is what keeps this acceptable.
