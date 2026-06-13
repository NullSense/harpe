from harpe import routing


def test_clean_title_strips_pipe_site():
    assert routing.clean_title(
        "‘Moses Breaketh the Tables’, John Martin, published 1833 | Tate"
    ) == "‘Moses Breaketh the Tables’, John Martin, published 1833"


def test_clean_title_strips_dash_museum():
    assert routing.clean_title("The Night Watch - Rijksmuseum") == "The Night Watch"


def test_clean_title_keeps_artist_dash():
    # "Title - Artist" must NOT be stripped (Artist isn't a museum keyword,
    # and there's no trailing pipe).
    assert routing.clean_title("The Bedroom - Vincent van Gogh") == \
        "The Bedroom - Vincent van Gogh"


def test_clean_title_rejects_botwall():
    assert routing.clean_title("Just a moment...") == ""
    assert routing.clean_title("Vercel Security Checkpoint") == ""


def test_clean_title_decodes_entities():
    assert routing.clean_title("Mother &amp; Child") == "Mother & Child"


def test_is_reference_page():
    assert routing.is_reference_page(
        "https://www.tate.org.uk/art/artworks/martin-x-t04895")
    assert routing.is_reference_page("https://en.wikipedia.org/wiki/The_Deluge")
    assert not routing.is_reference_page("https://x.com/user/status/123")


def test_is_art_url():
    assert routing.is_art_url(
        "https://artsandculture.google.com/asset/x/y")
    assert routing.is_art_url("https://example.org/iiif/2/abc/manifest.json")
    assert not routing.is_art_url("https://example.org/gallery")
