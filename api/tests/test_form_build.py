import json
from pathlib import Path

from app.services.form_build import accessible_name, build_form
from app.services.page_probe import RawControl

FIXTURES = Path(__file__).parent / "fixtures" / "inventories"


def c(**kw) -> RawControl:
    kw.setdefault("ref", "0-1")
    return RawControl(**kw)


def test_accessible_name_prefers_labelledby_over_placeholder():
    assert accessible_name(c(labelledby_text="Country", placeholder="Pick one")) == "Country"


def test_accessible_name_falls_back_through_the_chain():
    assert accessible_name(c(aria_label="Email")) == "Email"
    assert accessible_name(c(label_text="Phone")) == "Phone"
    assert accessible_name(c(placeholder="Portfolio URL")) == "Portfolio URL"
    assert accessible_name(c(name="linkedin")) == "linkedin"


def test_page_chrome_is_dropped():
    form = build_form([
        c(ref="0-1", role="searchbox", aria_label="Search jobs", landmark="navigation"),
        c(ref="0-2", role="textbox", aria_label="Full name", landmark="main"),
    ])
    assert [f.label for f in form.fields] == ["Full name"]


def test_a_dialog_wins_over_the_rest_of_the_page():
    form = build_form([
        c(ref="0-1", role="textbox", aria_label="Newsletter email", landmark="main"),
        c(ref="0-2", role="textbox", aria_label="Full name", landmark="dialog"),
        c(ref="0-3", role="combobox", aria_label="Country", landmark="dialog"),
    ])
    assert [f.label for f in form.fields] == ["Full name", "Country"]


def test_invisible_disabled_and_password_controls_never_become_fields():
    form = build_form([
        c(ref="0-1", role="textbox", aria_label="Hidden", visible=False),
        c(ref="0-2", role="textbox", aria_label="Disabled", disabled=True),
        c(ref="0-3", role="password", aria_label="Password"),
        c(ref="0-4", role="textbox", aria_label="Full name"),
    ])
    assert [f.label for f in form.fields] == ["Full name"]


def test_a_typeahead_combobox_is_typed_apart_from_a_plain_one():
    form = build_form([
        c(ref="0-1", role="combobox", aria_label="Country"),
        c(ref="0-2", role="combobox", aria_label="City", autocomplete_hint="list"),
    ])
    assert [f.type for f in form.fields] == ["combobox", "typeahead"]


def test_a_native_select_stays_a_select():
    form = build_form([c(role="combobox", tag="select", aria_label="Country",
                         options=["Türkiye", "Almanya"])])
    assert form.fields[0].type == "select"
    assert form.fields[0].options == ["Türkiye", "Almanya"]


def test_radios_collapse_into_one_grouped_field():
    form = build_form([
        c(ref="0-1", role="radio", name="auth", label_text="Yes"),
        c(ref="0-2", role="radio", name="auth", label_text="No"),
    ])
    assert len(form.fields) == 1
    assert form.fields[0].type == "radio"
    assert form.fields[0].options == ["Yes", "No"]
    assert form.fields[0].option_selectors == [
        '[data-cvai-ref="0-1"]', '[data-cvai-ref="0-2"]']


def test_selector_and_frame_address_the_control():
    form = build_form([c(ref="2-7", frame=2, role="textbox", aria_label="Email")])
    assert form.fields[0].selector == '[data-cvai-ref="2-7"]'
    assert form.fields[0].frame == 2


def test_assisted_mode_never_exposes_a_submit_button():
    form = build_form([c(role="textbox", aria_label="Email")])
    assert form.submit_selector is None


def test_field_ids_stay_unique_when_labels_repeat():
    form = build_form([
        c(ref="0-1", role="textbox", aria_label="Name"),
        c(ref="0-2", role="textbox", aria_label="Name"),
    ])
    assert len({f.id for f in form.fields}) == 2


def test_a_popup_option_is_not_mistaken_for_a_field():
    # the collector reports role=option so fill strategies can find popups; they
    # are choices, not questions, and must never reach the LLM as fields
    form = build_form([
        c(ref="0-1", role="combobox", aria_label="Country"),
        c(ref="0-2", role="option", label_text="Türkiye"),
    ])
    assert [f.type for f in form.fields] == ["combobox"]


def test_real_captured_inventories_yield_fields():
    for path in FIXTURES.glob("*.json"):
        controls = [RawControl(**c) for c in json.loads(path.read_text(encoding="utf-8"))]
        form = build_form(controls)
        assert form.fields, f"{path.name} produced no fields"
        assert all(f.label for f in form.fields), f"{path.name} has an unlabelled field"
