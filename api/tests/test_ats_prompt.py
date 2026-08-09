from app.services.ats_prompt import ATS_RULES, build_apply_system, build_rewrite_system


def test_both_prompts_carry_the_shared_rules():
    assert ATS_RULES in build_rewrite_system("tr")
    assert ATS_RULES in build_apply_system("tr")


def test_rewrite_prompt_has_no_posting_block():
    # "form" alone matches "information"; assert on tokens only the apply
    # contract uses.
    system = build_rewrite_system("en")
    assert "job_text" not in system
    assert "field_id" not in system
    assert "cover_letter" not in system
    assert "verification_required" in system
    assert "optimization_summary" in system


def test_apply_prompt_has_the_posting_and_form_contract():
    system = build_apply_system("en")
    assert "job_text" in system
    assert "field_id" in system
    assert "cover_letter" in system
    assert "verification_required" in system


def test_language_is_injected():
    assert "Answer in language: tr." in build_rewrite_system("tr")
    assert "Answer in language: en." in build_apply_system("en")


def test_prompts_contain_no_unformatted_placeholders():
    # These strings are composed with f-strings, never str.format(). A stray
    # doubled brace would reach the model verbatim.
    for system in (build_rewrite_system("tr"), build_apply_system("tr")):
        assert "{{" not in system
        assert "{language}" not in system


def test_accuracy_rules_lead_the_prompt():
    # The rules the model most needs to obey must not sit behind 2,000 words of
    # formatting guidance.
    assert ATS_RULES.index("ACCURACY") < ATS_RULES.index("STRUCTURE")
