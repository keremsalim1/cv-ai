from app.schemas import FieldAnswer, FormField, FormSchema
from app.services.fill_strategies import fill_and_verify, fill_field
from tests.fake_browser import FakeDriver


def field(**kw) -> FormField:
    kw.setdefault("id", "f1")
    kw.setdefault("selector", '[data-cvai-ref="0-1"]')
    kw.setdefault("label", "Field")
    return FormField(**kw)


def test_text_is_typed_into_its_own_frame():
    d = FakeDriver(["<html></html>"])
    out = fill_field(d, field(type="text", frame=2), "Ada", pdf_path="/tmp/cv.pdf")
    assert d.fills == [('[data-cvai-ref="0-1"]', "Ada", 2)]
    assert out.status == "filled"


def test_a_native_select_uses_select_by_label():
    d = FakeDriver(["<html></html>"])
    fill_field(d, field(type="select", options=["Türkiye"]), "Türkiye", "/tmp/cv.pdf")
    assert d.selects == [('[data-cvai-ref="0-1"]', "Türkiye", 0)]


def test_a_combobox_opens_then_clicks_the_matching_option():
    # after the click that opens it, the collector reports the popup's options
    d = FakeDriver(["<html></html>"], evaluations=[
        [{"ref": "0-9", "role": "option", "label_text": "Türkiye", "frame": 0},
         {"ref": "0-10", "role": "option", "label_text": "Almanya", "frame": 0}],
    ])
    out = fill_field(d, field(type="combobox"), "Almanya", "/tmp/cv.pdf")
    assert d.clicks == ['[data-cvai-ref="0-1"]', '[data-cvai-ref="0-10"]']
    assert out.status == "filled"


def test_a_typeahead_types_before_picking():
    d = FakeDriver(["<html></html>"], evaluations=[
        [{"ref": "0-9", "role": "option", "label_text": "Ankara", "frame": 0}],
    ])
    fill_field(d, field(type="typeahead"), "Ankara", "/tmp/cv.pdf")
    assert d.fills == [('[data-cvai-ref="0-1"]', "Ankara", 0)]
    assert d.clicks == ['[data-cvai-ref="0-9"]']


def test_a_combobox_whose_option_never_appears_fails_loudly():
    d = FakeDriver(["<html></html>"], evaluations=[[]])
    out = fill_field(d, field(type="combobox"), "Mars", "/tmp/cv.pdf")
    assert out.status == "failed"
    assert "Mars" in out.reason


def test_option_matching_ignores_case_and_padding():
    d = FakeDriver(["<html></html>"], evaluations=[
        [{"ref": "0-9", "role": "option", "label_text": "  TÜRKIYE ", "frame": 0}],
    ])
    out = fill_field(d, field(type="combobox"), "Türkiye", "/tmp/cv.pdf")
    assert out.status == "filled"


def test_an_empty_answer_is_skipped_not_failed():
    d = FakeDriver(["<html></html>"])
    out = fill_field(d, field(type="text"), "", "/tmp/cv.pdf")
    assert out.status == "skipped"
    assert d.fills == []


def test_a_file_field_uploads_the_cv_without_an_answer():
    d = FakeDriver(["<html></html>"])
    out = fill_field(d, field(type="file"), "", "/tmp/cv.pdf")
    assert d.files == [('[data-cvai-ref="0-1"]', "/tmp/cv.pdf", 0)]
    assert out.status == "filled"


def test_a_radio_clicks_the_option_selector_for_the_chosen_label():
    d = FakeDriver(["<html></html>"])
    out = fill_field(d, field(type="radio", options=["Yes", "No"],
                              option_selectors=['[data-cvai-ref="0-3"]',
                                                '[data-cvai-ref="0-4"]']),
                     "No", "/tmp/cv.pdf")
    assert d.clicks == ['[data-cvai-ref="0-4"]']
    assert out.status == "filled"


def test_a_radio_answer_outside_the_choices_fails():
    d = FakeDriver(["<html></html>"])
    out = fill_field(d, field(type="radio", options=["Yes"],
                              option_selectors=['[data-cvai-ref="0-3"]']),
                     "Maybe", "/tmp/cv.pdf")
    assert out.status == "failed"
    assert d.clicks == []


def test_a_driver_error_becomes_a_failed_outcome_not_an_exception():
    class Boom(FakeDriver):
        def fill(self, selector, value, frame=0):
            raise RuntimeError("element is not visible")

    out = fill_field(Boom(["<html></html>"]), field(type="text"), "Ada", "/tmp/cv.pdf")
    assert out.status == "failed"
    assert "not visible" in out.reason


def test_a_control_that_did_not_take_the_value_is_reported_as_failed():
    schema = FormSchema(fields=[field(id="name", type="text", label="Full name")])
    # the fill call reports success, but the verification probe shows the
    # control is still empty — a silently-ignored click looks exactly like this
    d = FakeDriver(["<html></html>"], evaluations=[
        [{"ref": "0-1", "role": "textbox", "value": "", "frame": 0}],
    ])
    outcomes = fill_and_verify(d, schema, [FieldAnswer(field_id="name", value="Ada")],
                               "/tmp/cv.pdf")
    assert outcomes[0].status == "failed"
    assert "did not take" in outcomes[0].reason


def test_a_control_holding_the_value_stays_filled():
    schema = FormSchema(fields=[field(id="name", type="text", label="Full name")])
    d = FakeDriver(["<html></html>"], evaluations=[
        [{"ref": "0-1", "role": "textbox", "value": "Ada", "frame": 0}],
    ])
    outcomes = fill_and_verify(d, schema, [FieldAnswer(field_id="name", value="Ada")],
                               "/tmp/cv.pdf")
    assert outcomes[0].status == "filled"


def test_verification_never_downgrades_a_skipped_or_failed_field():
    schema = FormSchema(fields=[field(id="name", type="text", label="Full name")])
    d = FakeDriver(["<html></html>"], evaluations=[[]])
    outcomes = fill_and_verify(d, schema, [FieldAnswer(field_id="name", value="")],
                               "/tmp/cv.pdf")
    assert outcomes[0].status == "skipped"


def test_a_widget_we_cannot_read_back_is_left_as_filled():
    # comboboxes often keep their value in a hidden node; absence of evidence
    # must not be reported as evidence of failure
    schema = FormSchema(fields=[field(id="c", type="combobox", label="Country")])
    d = FakeDriver(["<html></html>"], evaluations=[
        [{"ref": "0-9", "role": "option", "label_text": "Türkiye", "frame": 0}],
        [],
    ])
    outcomes = fill_and_verify(d, schema, [FieldAnswer(field_id="c", value="Türkiye")],
                               "/tmp/cv.pdf")
    assert outcomes[0].status == "filled"
