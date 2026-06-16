from harpe import extract


def test_wm_thumb_maps_to_original():
    thumb = ("https://upload.wikimedia.org/wikipedia/commons/thumb/c/ce/"
             "John_Martin_-_Macbeth.jpg/960px-John_Martin_-_Macbeth.jpg")
    orig = ("https://upload.wikimedia.org/wikipedia/commons/c/ce/"
            "John_Martin_-_Macbeth.jpg")
    assert extract._wm_original(thumb) == orig


def test_wm_original_passthrough_non_thumb():
    u = "https://example.org/a/b/photo.jpg"
    assert extract._wm_original(u) == u


def test_size_hint_from_query_and_px():
    assert extract._size_hint("https://x/i.jpg?w=2000") == 2000
    assert extract._size_hint("https://x/640px-i.jpg") == 640
    assert extract._size_hint("https://x/i.jpg", descriptor=1500) == 1500


def test_collect_dedupes_wm_variants_to_one_original():
    html = """
    <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/c/ce/A.jpg/330px-A.jpg"
         srcset="https://upload.wikimedia.org/wikipedia/commons/thumb/c/ce/A.jpg/660px-A.jpg 2x">
    """
    urls = extract.collect(html, "https://en.wikipedia.org/")
    assert urls == ["https://upload.wikimedia.org/wikipedia/commons/c/ce/A.jpg"]


def test_collect_absolutizes_and_skips_data_uri():
    html = '<img src="/img/a.png"><img src="data:image/png;base64,xxxx">'
    urls = extract.collect(html, "https://site.test/page")
    assert urls == ["https://site.test/img/a.png"]


def test_collect_picks_largest_query_variant():
    html = ('<img src="https://cdn.test/p.jpg?w=400">'
            '<img src="https://cdn.test/p.jpg?w=1600">')
    assert extract.collect(html, "https://cdn.test/") == \
        ["https://cdn.test/p.jpg?w=1600"]


def test_display_name_adds_extension():
    assert extract.display_name("https://x/foo").endswith(".jpg")
    assert extract.display_name("https://x/bar.png") == "bar.png"


def test_display_name_keeps_video_extension():
    # Regression: a Twitter/CDN MP4 must not become "<name>.mp4.jpg".
    n = extract.display_name(
        "https://video.twimg.com/amplify_video/123/vid/avc1/1080x1080/r2mYBJRfVf53plLi.mp4?tag=21")
    assert n == "r2mYBJRfVf53plLi.mp4"


def test_ext_from_content_type():
    assert extract.ext_from_content_type("video/mp4") == ".mp4"
    assert extract.ext_from_content_type("image/jpeg; charset=binary") == ".jpg"
    assert extract.ext_from_content_type("audio/mpeg") == ".mp3"
    assert extract.ext_from_content_type("application/octet-stream") is None
    assert extract.ext_from_content_type(None) is None


def test_kind_for_ext():
    assert extract.kind_for_ext(".mp4") == "video"
    assert extract.kind_for_ext(".MP3") == "audio"
    assert extract.kind_for_ext(".png") == "image"
    assert extract.kind_for_ext("") == "image"
