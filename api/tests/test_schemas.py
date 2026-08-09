import pytest

from app.schemas import Certification, CVData, EvaluationResult, Project, stars_from_percent


@pytest.mark.parametrize("percent,expected", [
    (0, 1), (20, 1), (21, 2), (40, 2), (41, 3), (60, 3),
    (61, 4), (80, 4), (81, 5), (100, 5),
])
def test_stars_from_percent(percent, expected):
    assert stars_from_percent(percent) == expected


def test_cvdata_minimal():
    cv = CVData(full_name="Ada Lovelace")
    assert cv.skills == [] and cv.experiences == []


def test_education_degree_may_be_null():
    # Real CVs include entries with no degree title (e.g. high school);
    # the LLM returns null for them and parsing must not fail.
    cv = CVData.model_validate({
        "full_name": "Ada Lovelace",
        "education": [
            {"degree": "BSc Mathematics", "school": "Cambridge", "year": "2019"},
            {"degree": None, "school": "Anadolu Lisesi", "year": None},
        ],
    })
    assert cv.education[1].degree is None
    assert cv.education[1].school == "Anadolu Lisesi"


def test_evaluation_result_bounds():
    with pytest.raises(Exception):
        EvaluationResult(percent=101, stars=5, strengths=[], gaps=[], suggestions=[])


LEGACY_CV = {
    "full_name": "Ada Lovelace",
    "summary": "Engineer.",
    "experiences": [{"title": "Developer", "company": "Analytical Engine Corp",
                     "start_date": "2020", "end_date": "2024",
                     "description": "Built compute engines."}],
    "education": [{"degree": "BSc Mathematics", "school": "Cambridge", "year": "2019"}],
    "skills": ["Python"],
    "languages": ["English"],
    "certifications": ["AWS Solutions Architect", "Scrum Master"],
}


def test_legacy_parsed_data_still_loads():
    cv = CVData.model_validate(LEGACY_CV)
    assert cv.experiences[0].description == "Built compute engines."
    assert cv.experiences[0].bullets == []
    assert cv.experiences[0].location is None
    assert cv.projects == []
    assert cv.achievements == []


def test_legacy_string_certifications_are_coerced():
    cv = CVData.model_validate(LEGACY_CV)
    assert cv.certifications[0] == Certification(name="AWS Solutions Architect")
    assert cv.certifications[1].issuer is None
    assert cv.certifications[1].date is None


def test_structured_certifications_load():
    cv = CVData.model_validate({
        **LEGACY_CV,
        "certifications": [{"name": "AWS SAA", "issuer": "Amazon", "date": "Mar 2024"}],
    })
    assert cv.certifications[0].issuer == "Amazon"
    assert cv.certifications[0].date == "Mar 2024"


def test_projects_and_achievements_load():
    cv = CVData.model_validate({
        **LEGACY_CV,
        "projects": [{"name": "Bombe", "kind": "academic",
                      "technologies": ["Python"], "bullets": ["Cracked ciphers."]}],
        "achievements": ["Best paper award, 1843"],
    })
    assert cv.projects[0] == Project(name="Bombe", kind="academic",
                                     technologies=["Python"], bullets=["Cracked ciphers."])
    assert cv.achievements == ["Best paper award, 1843"]


def test_education_and_experience_details_load():
    cv = CVData.model_validate({
        **LEGACY_CV,
        "experiences": [{"title": "Developer", "company": "Acme",
                         "location": "İstanbul, Türkiye",
                         "start_date": "Oca 2024", "end_date": "Devam Ediyor",
                         "bullets": ["Designed REST APIs.", "Tuned SQL queries."]}],
        "education": [{"degree": "BSc", "school": "Cambridge", "location": "Cambridge, UK",
                       "start_date": "2015", "year": "2019",
                       "details": ["GPA 3.8/4.0", "Thesis on analytical engines"]}],
    })
    assert cv.experiences[0].location == "İstanbul, Türkiye"
    assert cv.experiences[0].bullets == ["Designed REST APIs.", "Tuned SQL queries."]
    assert cv.education[0].details == ["GPA 3.8/4.0", "Thesis on analytical engines"]
    assert cv.education[0].start_date == "2015"
