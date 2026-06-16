import io
import json

from harpe import nativehost


def test_message_framing_roundtrip():
    buf = io.BytesIO()
    nativehost.write_message(buf, {"hello": "wörld", "n": 3})
    buf.seek(0)
    assert nativehost.read_message(buf) == {"hello": "wörld", "n": 3}


def test_read_message_eof_returns_none():
    assert nativehost.read_message(io.BytesIO(b"")) is None
    assert nativehost.read_message(io.BytesIO(b"\x02\x00")) is None  # truncated length


def test_ping_returns_defaults_and_version():
    r = nativehost.handle({"ping": True})
    assert r["ok"] and r["pong"]
    assert set(r["defaults"]) == {"image", "video", "audio"}
    assert "version" in r


def test_open_dispatch(monkeypatch):
    seen = {}
    monkeypatch.setattr(nativehost, "open_in_file_manager", lambda p: seen.setdefault("p", p))
    assert nativehost.handle({"open": "/home/u/Videos/harpe/x.com"}) == {"ok": True}
    assert seen["p"] == "/home/u/Videos/harpe/x.com"


def test_open_failure_reports_error(monkeypatch):
    def boom(_):
        raise RuntimeError("no file manager")
    monkeypatch.setattr(nativehost, "open_in_file_manager", boom)
    r = nativehost.handle({"open": "/x"})
    assert r["ok"] is False and "no file manager" in r["error"]


def test_pick_dispatch(monkeypatch):
    monkeypatch.setattr(nativehost, "pick_folder", lambda start=None: "/chosen/dir")
    assert nativehost.handle({"pick": True, "start": "~"}) == {"ok": True, "path": "/chosen/dir"}


def test_grab_passes_items_group_roots_to_engine(monkeypatch):
    from harpe import engine
    captured = {}

    def fake_fetch(urls, referer=None, dest=None, items=None, group="site", roots=None):
        captured.update(urls=urls, referer=referer, items=items, group=group, roots=roots)
        return [{"url": urls[0], "ok": True, "path": "/x/clip.mp4", "kind": "video"}]

    monkeypatch.setattr(engine, "fetch_images", fake_fetch)
    url = "https://video.twimg.com/x/clip.mp4"
    r = nativehost.handle({
        "urls": [url], "referer": "https://x.com/bob/status/1",
        "dirs": {"video": "~/V"}, "group": "author",
        "items": {url: {"name": "a nice tweet", "author": "bob"}},
    })
    assert r["results"][0]["ok"]
    assert captured["group"] == "author"
    assert captured["roots"] == {"video": "~/V"}
    assert captured["items"][url]["author"] == "bob"


def test_grab_no_urls_errors():
    assert nativehost.handle({"urls": []})["error"] == "no urls provided"


def test_invalid_group_falls_back_to_site(monkeypatch):
    from harpe import engine
    captured = {}
    monkeypatch.setattr(engine, "fetch_images",
                        lambda *a, **k: captured.update(k) or [])
    nativehost.handle({"urls": ["https://h/x.jpg"], "group": "garbage"})
    assert captured["group"] == "site"


def test_partial_body_read_returns_none():
    # Declares 5 bytes but only 2 follow → clean None, not a crash.
    assert nativehost.read_message(io.BytesIO(b"\x05\x00\x00\x00hi")) is None


def test_run_loop_end_to_end_ping():
    inp = io.BytesIO()
    nativehost.write_message(inp, {"ping": True})
    inp.seek(0)
    out = io.BytesIO()
    rc = nativehost.run(inp, out)          # EOF after one message → returns 0
    out.seek(0)
    assert rc == 0
    reply = nativehost.read_message(out)
    assert reply["ok"] and reply["pong"]


def test_cap_reply_truncates_oversized_results():
    big = [{"url": f"u{i}", "ok": True, "path": "x" * 2000} for i in range(2000)]
    capped = nativehost.cap_reply({"results": big})
    assert capped["truncated"] is True
    assert len(capped["results"]) < len(big)
    assert len(json.dumps(capped).encode()) <= nativehost.MAX_REPLY


def test_cap_reply_passes_small_replies_unchanged():
    r = {"ok": True, "results": [{"url": "u", "ok": True}]}
    assert nativehost.cap_reply(r) == r
