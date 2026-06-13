"""Every image-source path in extract.collect() is exercised here."""
from harpe import extract


def test_img_src_absolutized():
    assert extract.collect('<img src="/i/a.jpg">', "https://s.test/page") == \
        ["https://s.test/i/a.jpg"]


def test_srcset_extracts_all_candidates():
    html = '<img srcset="https://cdn.x/a-320.jpg 320w, https://cdn.x/a-1024.jpg 1024w">'
    assert set(extract.collect(html, "https://cdn.x/")) == {
        "https://cdn.x/a-320.jpg", "https://cdn.x/a-1024.jpg"}


def test_source_srcset_in_picture():
    html = ('<picture><source srcset="https://cdn.x/p.webp">'
            '<img src="https://cdn.x/p.jpg"></picture>')
    urls = extract.collect(html, "https://cdn.x/")
    assert "https://cdn.x/p.webp" in urls and "https://cdn.x/p.jpg" in urls


def test_a_href_to_image_file():
    html = '<a href="/full/photo.png"><img src="/thumb/photo.png"></a>'
    urls = extract.collect(html, "https://s.test/")
    assert "https://s.test/full/photo.png" in urls


def test_a_href_non_image_ignored():
    html = '<a href="/about.html">x</a>'
    assert extract.collect(html, "https://s.test/") == []


def test_css_background_image():
    html = '<div style="background-image:url(https://cdn.x/bg.jpg)"></div>'
    assert extract.collect(html, "https://cdn.x/") == ["https://cdn.x/bg.jpg"]


def test_og_image_meta():
    html = '<meta property="og:image" content="https://cdn.x/social.jpg">'
    assert extract.collect(html, "https://cdn.x/") == ["https://cdn.x/social.jpg"]


def test_twitter_image_meta():
    html = '<meta name="twitter:image" content="https://cdn.x/tw.jpg">'
    assert extract.collect(html, "https://cdn.x/") == ["https://cdn.x/tw.jpg"]


def test_lazy_data_src():
    html = '<img data-src="https://cdn.x/lazy.jpg">'
    assert extract.collect(html, "https://cdn.x/") == ["https://cdn.x/lazy.jpg"]


def test_link_preload_as_image():
    html = '<link rel="preload" as="image" href="https://cdn.x/hero.jpg">'
    assert extract.collect(html, "https://cdn.x/") == ["https://cdn.x/hero.jpg"]


def test_data_uri_and_javascript_skipped():
    html = ('<img src="data:image/png;base64,AAAA">'
            '<img src="javascript:void(0)">'
            '<img src="https://cdn.x/real.jpg">')
    assert extract.collect(html, "https://cdn.x/") == ["https://cdn.x/real.jpg"]
