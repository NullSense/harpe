from harpe import backends


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
