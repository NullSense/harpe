"""schema.org JSON-LD artwork extraction (the most precise query-from-page path)."""
from harpe import routing


def test_painting_with_creator():
    html = ('<script type="application/ld+json">'
            '{"@type":"Painting","name":"The Night Watch",'
            '"creator":{"@type":"Person","name":"Rembrandt"}}</script>')
    assert routing._jsonld_query(html) == "The Night Watch Rembrandt"


def test_graph_nesting_and_array_name_and_author_list():
    html = ('<script type="application/ld+json">'
            '{"@graph":[{"@type":"WebPage"},'
            '{"@type":"VisualArtwork","name":["Starry Night"],'
            '"author":[{"name":"van Gogh"}]}]}</script>')
    assert routing._jsonld_query(html) == "Starry Night van Gogh"


def test_no_artwork_returns_empty():
    html = ('<script type="application/ld+json">'
            '{"@type":"Organization","name":"Some Museum"}</script>')
    assert routing._jsonld_query(html) == ""


def test_malformed_json_is_ignored():
    html = '<script type="application/ld+json">{not valid json,,,}</script>'
    assert routing._jsonld_query(html) == ""
