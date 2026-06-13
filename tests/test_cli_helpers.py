"""Engine download helpers + candidate shaping (frontend-agnostic core)."""
from harpe import engine


def test_ext_of():
    assert engine.ext_of("https://x/a.JPG?q=1") == "jpg"
    assert engine.ext_of("https://x/photo.webp") == "webp"
    assert engine.ext_of("https://x/noext") == ""
    assert engine.ext_of("https://x/dir/") == ""


def test_origin():
    assert engine.origin("https://h.test/a/b.jpg") == "https://h.test/"
    assert engine.origin("http://h.test/x") == "http://h.test/"


def test_human():
    assert engine.human(500) == "500B"
    assert engine.human(2048) == "2K"
    assert engine.human(5 * 1024 * 1024) == "5M"
    assert engine.human(3 * 1024 ** 3) == "3G"


def test_row_to_dict_parses_dims():
    d = engine._row_to_dict("4000x3000", "https://x/a.jpg", "a.jpg")
    assert d == {"url": "https://x/a.jpg", "name": "a.jpg", "dim": "4000x3000",
                 "width": 4000, "height": 3000}


def test_row_to_dict_unknown_dims():
    d = engine._row_to_dict("?", "https://x/a.jpg", "a.jpg")
    assert d["width"] is None and d["height"] is None and d["dim"] == "?"
