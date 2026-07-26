"""A Chromium profile carries the user's logged-in job-site cookies. Two users
must never share one, and Chromium cannot open the same profile dir twice."""
from app.services import browser
from tests.conftest import make_token
from tests.fake_browser import FakeDriver

LOGIN_WALL = "<html><body><form><input type='password' name='p'></form></body></html>"


def test_profile_dir_is_unique_per_user():
    a = browser.profile_dir_for("user-a")
    b = browser.profile_dir_for("user-b")
    assert a != b


def test_profile_dir_is_stable_for_one_user():
    # same user, later session: the dir must repeat so their job-site logins
    # survive between applications
    assert browser.profile_dir_for("user-a") == browser.profile_dir_for("user-a")


def test_profile_dir_lives_under_the_configured_base():
    base = browser.get_settings().browser_profile_dir
    assert browser.profile_dir_for("user-a").startswith(base)


def test_profile_dir_is_path_safe_for_hostile_user_ids():
    hostile = browser.profile_dir_for("../../etc/passwd")
    assert ".." not in hostile


def test_driver_factory_binds_the_users_own_profile(monkeypatch):
    seen: list[tuple[bool, str]] = []

    class _Recorder:
        def __init__(self, headed, profile_dir):
            seen.append((headed, profile_dir))

    monkeypatch.setattr(browser, "PlaywrightDriver", _Recorder)
    browser.driver_factory_for("user-a")(True)
    assert seen == [(True, browser.profile_dir_for("user-a"))]


def test_a_real_request_gets_the_caller_s_own_profile(client, monkeypatch):
    """End-to-end through the real dependency graph: every /apply test overrides
    the driver factory, so without this nothing would catch the caller's identity
    failing to reach the profile directory."""
    seen: list[str] = []

    class _Recorder(FakeDriver):
        def __init__(self, headed, profile_dir):
            super().__init__([LOGIN_WALL])
            seen.append(profile_dir)

    monkeypatch.setattr(browser, "PlaywrightDriver", _Recorder)
    body = {"cv": {"full_name": "Ada"}, "url": "https://jobs.example.com/1"}
    for user in ("user-1", "user-2"):
        res = client.post("/apply/prepare", json=body,
                          headers={"Authorization": f"Bearer {make_token(user)}"})
        assert res.status_code == 200, res.text

    assert seen == [browser.profile_dir_for("user-1"),
                    browser.profile_dir_for("user-2")]
    assert seen[0] != seen[1]
