from pathlib import Path

from fpdf import FPDF

from app.schemas import CVData
from app.services.llm import MODEL_SMART, LLMClient

SYSTEM = (
    "You rewrite CVs to be ATS-compliant. Rules: standard section wording, "
    "concise bullet-style descriptions, measurable achievements where the "
    "original supports them, no invented facts, no tables/graphics/icons. "
    "Answer in language: {language}. Respond ONLY with JSON in the same CV schema "
    "you received."
)

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


def rewrite_ats(cv: CVData, language: str, llm: LLMClient) -> CVData:
    return llm.chat_json(MODEL_SMART, SYSTEM.format(language=language),
                         cv.model_dump_json(), CVData)


def render_pdf(cv: CVData, language: str) -> bytes:
    h = HEADINGS.get(language, HEADINGS["en"])
    regular, bold = _find_fonts()
    pdf = FPDF()
    pdf.add_font("Main", "", regular)
    pdf.add_font("Main", "B", bold)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def heading(text: str):
        pdf.set_font("Main", "B", 13)
        pdf.cell(0, 9, text, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Main", "", 10.5)

    def line(text: str):
        # fpdf2 2.8.x leaves the cursor at line end; reset to the left margin
        pdf.multi_cell(0, 5.5, text, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Main", "B", 17)
    pdf.cell(0, 10, cv.full_name, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Main", "", 10)
    contact = " | ".join(x for x in [cv.email, cv.phone, cv.location] if x)
    if contact:
        line(contact)
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
            line(f"{ed.degree} — {ed.school}" + (f" ({ed.year})" if ed.year else ""))
        pdf.ln(2)
    if cv.skills:
        heading(h["skills"]); line(", ".join(cv.skills)); pdf.ln(2)
    if cv.languages:
        heading(h["languages"]); line(", ".join(cv.languages)); pdf.ln(2)
    if cv.certifications:
        heading(h["certifications"]); line(", ".join(cv.certifications))

    return bytes(pdf.output())
