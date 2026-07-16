import pytest

from app.schemas import CVData, EvaluationResult, stars_from_percent


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
