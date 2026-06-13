"""Cross-platform notify command builders (pure string building)."""
from harpe import notify


def test_osa_escape_quotes_and_newlines():
    assert notify._osa_escape('say "hi"\nthere') == 'say \\"hi\\" there'
    assert notify._osa_escape('a\\b') == 'a\\\\b'
    assert notify._osa_escape(None) == ""


def test_applescript_notify():
    s = notify._applescript_notify("Saved 3 images", "books.toscrape.com")
    assert s == ('display notification "books.toscrape.com" '
                 'with title "Saved 3 images"')


def test_applescript_setclip_uses_png_class():
    s = notify._applescript_setclip("/tmp/a.png")
    assert '(POSIX file "/tmp/a.png")' in s
    assert "«class PNGf»" in s
