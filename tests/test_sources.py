from harpe import sources


def test_strip_html_removes_tags_and_collapses_ws():
    assert sources._strip_html("<p>Hello <b>world</b></p>\n  there") == \
        "Hello world there"


def test_strip_html_empty():
    assert sources._strip_html("") == ""
    assert sources._strip_html(None) == ""


def test_toint_handles_cleveland_string_dims():
    # Cleveland returns width/height as STRINGS — this was a real jq tonumber? bug.
    assert sources._toint("4000") == 4000
    assert sources._toint("4000px") == 4000
    assert sources._toint(3000) == 3000
    assert sources._toint(None) == 0
    assert sources._toint("") == 0
