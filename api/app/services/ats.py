from pathlib import Path

from fpdf import FPDF
from pydantic import BaseModel

from app.schemas import CVData
from app.services.ats_prompt import build_rewrite_system
from app.services.llm import MODEL_SMART, LLMClient


class RewriteOut(BaseModel):
    cv: CVData
    # What the model could not confirm from the source, and what it changed.
    # Neither reaches the PDF; both are shown next to the result.
    verification_required: list[str] = []
    optimization_summary: list[str] = []

# "BECERİLER", not "TEKNİK BECERİLER": group names already adapt to the
# person's profession, and a hard "Technical Skills" heading would be wrong on a
# nurse's or an accountant's CV.
HEADINGS = {
    "tr": {"summary": "PROFESYONEL ÖZET", "skills": "BECERİLER",
           "experience": "İŞ DENEYİMİ", "projects": "PROJELER",
           "education": "EĞİTİM", "certifications": "SERTİFİKALAR",
           "achievements": "BAŞARILAR VE AKTİVİTELER", "languages": "YABANCI DİLLER"},
    "en": {"summary": "PROFESSIONAL SUMMARY", "skills": "SKILLS",
           "experience": "EXPERIENCE", "projects": "PROJECTS",
           "education": "EDUCATION", "certifications": "CERTIFICATIONS",
           "achievements": "ACHIEVEMENTS", "languages": "LANGUAGES"},
}

_FONT_CANDIDATES = [
    (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]


def _find_fonts() -> tuple[str, str]:
    for regular, bold in _FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold).exists():
            return regular, bold
    raise RuntimeError("No Unicode TTF font found; set font paths in ats.py")


def rewrite_ats(cv: CVData, language: str, llm: LLMClient) -> RewriteOut:
    return llm.chat_json(MODEL_SMART, build_rewrite_system(language),
                         cv.model_dump_json(), RewriteOut)


def render_pdf(cv: CVData, language: str) -> bytes:
    h = HEADINGS.get(language, HEADINGS["en"])
    regular, bold = _find_fonts()
    pdf = FPDF()
    pdf.add_font("Main", "", regular)
    pdf.add_font("Main", "B", bold)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def heading(text: str):
        # Left-aligned section break over a full-width rule
        pdf.ln(1)
        pdf.set_font("Main", "B", 12)
        pdf.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(120, 120, 120)
        pdf.set_line_width(0.3)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(2)
        pdf.set_font("Main", "", 10.5)

    def line(text: str):
        # fpdf2 2.8.x leaves the cursor at line end; reset to the left margin
        pdf.multi_cell(0, 5.5, text, new_x="LMARGIN", new_y="NEXT")

    def bullet(text: str):
        pdf.set_x(pdf.l_margin + 4)
        pdf.multi_cell(0, 5.5, f"• {text}", new_x="LMARGIN", new_y="NEXT")

    def bold_line(text: str):
        pdf.set_font("Main", "B", 10.5)
        line(text)
        pdf.set_font("Main", "", 10.5)

    def joined(*parts: str | None) -> str:
        return " | ".join(x for x in parts if x)

    def span(start: str | None, end: str | None) -> str:
        return " - ".join(x for x in (start, end) if x)

    pdf.set_font("Main", "B", 19)
    pdf.cell(0, 11, cv.full_name, new_x="LMARGIN", new_y="NEXT")
    if cv.title:
        pdf.set_font("Main", "", 12)
        pdf.cell(0, 7, cv.title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Main", "", 10)
    # Two blocks on two lines: long profile URLs stop competing with the phone
    # number for one line, and both stay plain text for the parser.
    for block in ((cv.location, cv.phone, cv.email),
                  (cv.linkedin, cv.github, cv.website)):
        text = joined(*block)
        if text:
            pdf.cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Fixed section order. Empty sections are skipped, which is what lifts
    # education and projects to the top for a candidate with no experience.
    if cv.summary:
        heading(h["summary"]); line(cv.summary); pdf.ln(2)

    if cv.skill_groups or cv.skills:
        heading(h["skills"])
        if cv.skill_groups:
            for g in cv.skill_groups:
                if not g.skills:
                    continue
                pdf.set_font("Main", "B", 10.5)
                pdf.write(5.5, f"{g.name}: ")
                pdf.set_font("Main", "", 10.5)
                pdf.write(5.5, ", ".join(g.skills))
                pdf.ln(6.5)
        else:
            line(", ".join(cv.skills))
        pdf.ln(2)

    if cv.experiences:
        heading(h["experience"])
        for e in cv.experiences:
            bold_line(e.title)
            line(joined(e.company, e.location))
            dates = span(e.start_date, e.end_date)
            if dates:
                line(dates)
            for b in e.bullets:
                bullet(b)
            if not e.bullets and e.description:
                line(e.description)
            pdf.ln(1)
        pdf.ln(1)

    if cv.projects:
        heading(h["projects"])
        for p in cv.projects:
            bold_line(joined(p.name, p.kind))
            if p.technologies:
                line(", ".join(p.technologies))
            for b in p.bullets:
                bullet(b)
            pdf.ln(1)
        pdf.ln(1)

    if cv.education:
        heading(h["education"])
        for ed in cv.education:
            bold_line(ed.degree or ed.school)
            if ed.degree:
                line(joined(ed.school, ed.location))
            elif ed.location:
                line(ed.location)
            dates = span(ed.start_date, ed.year)
            if dates:
                line(dates)
            for d in ed.details:
                bullet(d)
            pdf.ln(1)
        pdf.ln(1)

    if cv.certifications:
        heading(h["certifications"])
        for c in cv.certifications:
            line(joined(c.name, c.issuer, c.date))
        pdf.ln(2)

    if cv.achievements:
        heading(h["achievements"])
        for a in cv.achievements:
            bullet(a)
        pdf.ln(2)

    if cv.languages:
        heading(h["languages"]); line(", ".join(cv.languages))

    return bytes(pdf.output())
