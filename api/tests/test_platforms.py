from app.services.form_build import build_form
from app.services.page_probe import RawControl
from app.services.platforms import Platform, platform_for


def test_an_unknown_host_has_no_platform():
    assert platform_for("https://jobs.example.com/apply") is None


def test_a_registered_host_matches_its_subdomains(monkeypatch):
    import app.services.platforms as mod
    entry = Platform(name="test", hosts=("myworkdayjobs.com",))
    monkeypatch.setattr(mod, "REGISTRY", (entry,))
    assert mod.platform_for("https://acme.wd3.myworkdayjobs.com/job/1") is entry
    assert mod.platform_for("https://myworkdayjobs.com/job/1") is entry
    # a lookalike suffix must not match
    assert mod.platform_for("https://notmyworkdayjobs.com/job/1") is None


def test_a_platform_can_pin_the_scope_that_generic_rules_would_miss():
    # generic scoping would pick the dialog; this platform says the real form
    # is the main region
    controls = [
        RawControl(ref="0-1", role="textbox", aria_label="Cookie consent",
                   landmark="dialog", visible=True),
        RawControl(ref="0-2", role="textbox", aria_label="Full name",
                   landmark="main", visible=True),
    ]
    assert [f.label for f in build_form(controls).fields] == ["Cookie consent"]
    pinned = Platform(name="test", hosts=("t.example",), scope_landmark="main")
    assert [f.label for f in build_form(controls, pinned).fields] == ["Full name"]
