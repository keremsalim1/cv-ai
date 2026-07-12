from pydantic import BaseModel, Field


def stars_from_percent(percent: int) -> int:
    return min(5, max(1, (percent - 1) // 20 + 1))


class Experience(BaseModel):
    title: str
    company: str
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None


class Education(BaseModel):
    degree: str
    school: str
    year: str | None = None


class CVData(BaseModel):
    full_name: str
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    summary: str | None = None
    experiences: list[Experience] = []
    education: list[Education] = []
    skills: list[str] = []
    languages: list[str] = []
    certifications: list[str] = []


class JobCriteria(BaseModel):
    title: str
    company: str | None = None
    requirements: list[str] = []
    skills: list[str] = []


class EvaluationResult(BaseModel):
    percent: int = Field(ge=0, le=100)
    stars: int = Field(ge=1, le=5)
    strengths: list[str] = []
    gaps: list[str] = []
    suggestions: list[str] = []
