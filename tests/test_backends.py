import pytest

from harpe import backends


class _R:
    returncode = 0


def _capture(monkeypatch):
    """Capture the argv yt-dlp would be invoked with (no real subprocess)."""
    seen = {}

    def fake_run(cmd, *a, **k):
        seen["cmd"] = cmd
        return _R()

    monkeypatch.setattr(backends.subprocess, "run", fake_run)
    return seen


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("HARPE_COOKIES_FROM_BROWSER", raising=False)
    monkeypatch.delenv("HARPE_IMPERSONATE", raising=False)


def test_video_includes_resilience_flags(monkeypatch):
    seen = _capture(monkeypatch)
    backends.video(["https://x/v"])
    cmd = seen["cmd"]
    assert "--retries" in cmd and "--fragment-retries" in cmd and "--concurrent-fragments" in cmd


def test_no_cookies_or_impersonate_by_default(monkeypatch):
    seen = _capture(monkeypatch)
    backends.video(["https://x/v"])
    assert "--cookies-from-browser" not in seen["cmd"]
    assert "--impersonate" not in seen["cmd"]


def test_cookies_and_impersonate_are_opt_in(monkeypatch):
    monkeypatch.setenv("HARPE_COOKIES_FROM_BROWSER", "firefox")
    monkeypatch.setenv("HARPE_IMPERSONATE", "chrome")
    seen = _capture(monkeypatch)
    backends.audio(["https://x/a"])
    cmd = seen["cmd"]
    assert cmd[cmd.index("--cookies-from-browser") + 1] == "firefox"
    assert cmd[cmd.index("--impersonate") + 1] == "chrome"


def test_slug_from_google_arts_asset():
    assert backends.slug_from_url(
        "https://artsandculture.google.com/asset/the-feast-of-belshazzar/abc123"
    ) == "the-feast-of-belshazzar"


def test_slug_from_last_path_segment():
    assert backends.slug_from_url("https://example.org/art/the-deluge/") == \
        "the-deluge"


def test_slug_strips_query_and_fragment():
    assert backends.slug_from_url("https://x/iiif/manifest.json?v=2#z") == \
        "manifest.json"
