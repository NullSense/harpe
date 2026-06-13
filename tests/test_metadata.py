from harpe import metadata
from harpe.models import Candidate


def test_name_parts_drops_nationality_and_extracts_year():
    c = Candidate(title="The Bedroom", artist="Vincent van Gogh (Dutch, 1853–1890)",
                  date="1888", source="AIC")
    name, artist, year = metadata.name_parts(c)
    assert artist == "Vincent van Gogh"
    assert year == "1888"
    assert name == "Vincent van Gogh - The Bedroom (1888) [AIC]"


def test_build_slug_sanitizes_filesystem_chars():
    c = Candidate(title="A/B: C?", artist="X", date="1900", source="Met")
    slug = metadata.build_slug(c)
    assert "/" not in slug and ":" not in slug and "?" not in slug
    assert slug.startswith("X - A B C")


def test_captions_compose_body():
    c = Candidate(title="The Deluge", artist="John Martin", date="1834",
                  source="AIC", medium="oil on canvas",
                  physdim="100 x 200 cm", desc="An apocalyptic flood.")
    caption, body = metadata.captions(c, "5000x3000")
    assert caption == "John Martin — The Deluge (1834)"
    assert "oil on canvas" in body
    assert "100 x 200 cm" in body
    assert "5000x3000 · AIC" in body
    assert body.endswith("An apocalyptic flood.")


def test_source_url_strips_prefix():
    assert Candidate(spec="url:https://x/y.jpg").source_url == "https://x/y.jpg"
    assert Candidate(spec="iiif:https://x/m.json").source_url == "https://x/m.json"
