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

HEADINGS = {
    "tr": {"summary": "ÖZET", "experience": "İŞ DENEYİMİ", "education": "EĞİTİM",
           "skills": "BECERİLER", "languages": "DİLLER", "certifications": "SERTİFİKALAR"},
    "en": {"summary": "SUMMARY", "experience": "EXPERIENCE", "education": "EDUCATION",
           "skills": "SKILLS", "languages": "LANGUAGES", "certifications": "CERTIFICATIONS"},
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
        # Kakuna-style section break: centered heading over a full-width rule
        pdf.set_font("Main", "B", 12)
        pdf.cell(0, 9, text, new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.set_draw_color(120, 120, 120)
        pdf.set_line_width(0.3)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(2)
        pdf.set_font("Main", "", 10.5)

    def line(text: str):
        # fpdf2 2.8.x leaves the cursor at line end; reset to the left margin
        pdf.multi_cell(0, 5.5, text, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Main", "B", 19)
    pdf.cell(0, 11, cv.full_name, new_x="LMARGIN", new_y="NEXT", align="C")
    if cv.title:
        pdf.set_font("Main", "", 12)
        pdf.cell(0, 7, cv.title, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Main", "", 10)
    contact = " | ".join(x for x in [cv.location, cv.phone, cv.email,
                                     cv.linkedin, cv.github, cv.website] if x)
    if contact:
        pdf.cell(0, 6, contact, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(3)

    if cv.summary:
        heading(h["summary"]); line(cv.summary); pdf.ln(2)
    if cv.experiences:
        heading(h["experience"])
        for e in cv.experiences:
            pdf.set_font("Main", "B", 10.5)
            dates = f" ({e.start_date or ''} - {e.end_date or ''})".replace("( - )", "")
            line(f"{e.title} — {e.company}{dates}")
            pdf.set_font("Main", "", 10.5)
            if e.description:
                line(e.description)
        pdf.ln(2)
    if cv.education:
        heading(h["education"])
        for ed in cv.education:
            entry = f"{ed.degree} — {ed.school}" if ed.degree else ed.school
            line(entry + (f" ({ed.year})" if ed.year else ""))
        pdf.ln(2)
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
    if cv.languages:
        heading(h["languages"]); line(", ".join(cv.languages)); pdf.ln(2)
    if cv.certifications:
        heading(h["certifications"]); line(", ".join(cv.certifications))

    return bytes(pdf.output())
