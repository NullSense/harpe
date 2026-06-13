"""extract.select — ranking, icon floor, and the never-empty fallback."""
from harpe import extract


def _ok(url, w, h):
    return (url, "ok", (w, h))


def test_ranks_biggest_first():
    rows = extract.select([_ok("a", 100, 100), _ok("b", 4000, 3000)], minpx=100)
    assert [u for _d, u in rows] == ["b", "a"]


def test_floor_drops_icons_but_keeps_thumbnails():
    probed = [_ok("cover", 125, 155), _ok("icon", 32, 32), _ok("banner", 4000, 800)]
    urls = [u for _d, u in extract.select(probed, minpx=100)]
    assert "icon" not in urls          # 32px chrome dropped
    assert "cover" in urls and "banner" in urls


def test_mixed_page_keeps_small_covers_alongside_big():
    # The books.toscrape.com regression: 155px covers must NOT be hidden by a big image.
    probed = [_ok(f"cover{i}", 125, 155) for i in range(20)] + [_ok("hero", 4000, 4000)]
    urls = [u for _d, u in extract.select(probed, minpx=100)]
    assert urls[0] == "hero"
    assert sum(1 for u in urls if u.startswith("cover")) == 20


def test_thumbnail_only_page_never_empty():
    # Every image below the floor -> floor relaxed so the picker isn't empty.
    probed = [_ok("t1", 80, 90), _ok("t2", 70, 60)]
    urls = [u for _d, u in extract.select(probed, minpx=256)]
    assert set(urls) == {"t1", "t2"}


def test_drops_non_images_keeps_unknown_last():
    probed = [_ok("img", 500, 500), ("wrapper", "drop", None),
              ("rate_limited", "retry", None)]
    rows = extract.select(probed, minpx=100)
    urls = [u for _d, u in rows]
    assert "wrapper" not in urls
    assert urls == ["img", "rate_limited"]      # unknown sorts last
    assert rows[-1][0] == "?"
