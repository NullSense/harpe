import contextlib
from pathlib import Path

from harpe import engine


class _FakeResp:
    def __init__(self, content_type, body=b"data"):
        self.headers = {"content-type": content_type}
        self._body = body

    def raise_for_status(self):
        pass

    def iter_bytes(self, _n):
        yield self._body


def _patch_stream(monkeypatch, content_type):
    @contextlib.contextmanager
    def fake_stream(method, url, **kw):
        yield _FakeResp(content_type)

    monkeypatch.setattr(engine.httpx, "stream", fake_stream)


def _patch_dirs(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "IMG_DIR", tmp_path / "Pictures" / "harpe")
    monkeypatch.setattr(engine, "VID_DIR", tmp_path / "Videos" / "harpe")
    monkeypatch.setattr(engine, "AUD_DIR", tmp_path / "Music" / "harpe")


def test_video_routes_to_vid_dir_and_keeps_mp4(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    _patch_stream(monkeypatch, "video/mp4")
    url = "https://video.twimg.com/amplify_video/1/vid/avc1/1080x1080/r2mYBJRfVf53plLi.mp4?tag=21"
    [res] = engine.fetch_images([url], referer="https://x.com/u/status/2")
    assert res["ok"] and res["kind"] == "video"
    p = Path(res["path"])
    assert p.name == "r2mYBJRfVf53plLi.mp4"      # not .mp4.jpg
    assert p.parent == tmp_path / "Videos" / "harpe" / "x.com"
    assert p.exists()


def test_extensionless_url_gets_ext_from_content_type(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    _patch_stream(monkeypatch, "image/jpeg")
    [res] = engine.fetch_images(["https://cdn.example.com/media/abc123"])
    p = Path(res["path"])
    assert p.suffix == ".jpg" and res["kind"] == "image"
    assert p.parent == tmp_path / "Pictures" / "harpe" / "cdn.example.com"


def test_explicit_dest_overrides_typed_dir(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    _patch_stream(monkeypatch, "video/mp4")
    dest = tmp_path / "chosen"
    [res] = engine.fetch_images(["https://h/clip.mp4"], dest=str(dest))
    assert Path(res["path"]).parent == dest


def test_suggested_name_and_author_grouping(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    _patch_stream(monkeypatch, "video/mp4")
    url = "https://video.twimg.com/amplify_video/1/vid/avc1/1080x1080/Qsru0ZY1KP6oU2ku.mp4?tag=21"
    [res] = engine.fetch_images(
        [url], referer="https://x.com/instance_11/status/2",
        items={url: {"name": "i envision a world without duplicates", "author": "instance_11"}},
        group="author")
    p = Path(res["path"])
    assert p.name == "i envision a world without duplicates.mp4"
    assert p.parent == tmp_path / "Videos" / "harpe" / "instance_11"


def test_group_both_nests_author_then_site(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    _patch_stream(monkeypatch, "video/mp4")
    url = "https://video.twimg.com/x/clip.mp4"
    [res] = engine.fetch_images(
        [url], referer="https://x.com/bob/status/9",
        items={url: {"author": "bob"}}, group="both")
    assert Path(res["path"]).parent == tmp_path / "Videos" / "harpe" / "bob" / "x.com"


def test_default_group_is_site(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    _patch_stream(monkeypatch, "image/jpeg")
    [res] = engine.fetch_images(["https://cdn.example.com/p/abc"])
    assert Path(res["path"]).parent == tmp_path / "Pictures" / "harpe" / "cdn.example.com"


def test_sanitize_stem_strips_path_chars():
    assert engine.sanitize_stem("a/b\\c: d?*") == "abc d"
    assert engine.sanitize_stem("  ...trim... ") == "trim"
    assert len(engine.sanitize_stem("x" * 200)) == 80


def test_sanitize_stem_blocks_traversal_and_empty():
    assert "/" not in engine.sanitize_stem("../../etc/passwd")
    assert "\\" not in engine.sanitize_stem("..\\..\\windows")
    assert engine.sanitize_stem("") == ""
    assert engine.sanitize_stem("///") == ""


def test_group_subpath_both_without_author_is_host():
    assert engine._group_subpath("both", "x.com", None) == "x.com"
    assert engine._group_subpath("author", "x.com", None) == "x.com"
    assert engine._group_subpath("none", "x.com", "bob") == ""


def test_roots_override_expands_user_and_vars(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    _patch_stream(monkeypatch, "video/mp4")
    monkeypatch.setenv("HOME", str(tmp_path))
    [res] = engine.fetch_images(["https://h/clip.mp4"],
                                roots={"video": "$HOME/customvids"})
    assert str(res["path"]).startswith(str(tmp_path / "customvids"))
