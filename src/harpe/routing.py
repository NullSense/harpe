"""URL classification + deriving an artwork search query from a page."""
import html as _html
import re
import subprocess

import httpx
from selectolax.parser import HTMLParser

from .config import UA

VIDEO_EXTS = {"mp4", "webm", "mkv", "mov", "m4v", "flv", "avi", "ts", "3gp",
              "mpg", "mpeg", "m2ts"}

# Single-artwork / encyclopedia pages: grabbing these with gallery-dl either dumps
# every image on the page or errors (exit 64). Route them to the federated museum
# search by derived name, which usually finds the same work as a CC0 original
# elsewhere (AIC/Met/Commons) at far higher resolution than the page's thumbnail.
REFERENCE_HOSTS = (
    "wikipedia.org/wiki/", "wikiart.org/", "britannica.com/",
    ".metmuseum.org/art/", "artic.edu/artworks/", "clevelandart.org/art/",
    "tate.org.uk/art/", "nationalgallery.org.uk/paintings/",
    "getty.edu/art/collection/object", "nga.gov/artworks/",
    "moma.org/collection/works/",
)

_BOTWALL = re.compile(
    r"security checkpoint|just a moment|attention required|access denied|are you a robot",
    re.I)
_SITE_TAIL = re.compile(
    r"\s*[|·–—-]\s+[^|·–—-]*"
    r"(Museum|Gallery|Institute|Collection|Wikipedia|Wikimedia|Culture|"
    r"Rijksmuseum|Europeana|WikiArt|Metropolitan)[^|·–—-]*$", re.I)
_PIPE_TAIL = re.compile(r"\s*\|\s*[^|]*$")
_ASSET = re.compile(r".*/asset/([^/?#]+).*")


def is_art_url(url: str) -> bool:
    u = url.lower()
    return ("artsandculture.google.com" in u or "/iiif/" in u
            or "?iiif" in u or "manifest.json" in u)


def is_reference_page(url: str) -> bool:
    u = url.lower()
    return any(h in u for h in REFERENCE_HOSTS)


def has_video(url: str) -> bool:
    """Fast probe: does this URL resolve to an actual video? yt-dlp matches many
    image pages too, so we check the media TYPE (first item's ext)."""
    try:
        out = subprocess.run(
            ["yt-dlp", "--quiet", "--no-warnings", "--simulate",
             "--playlist-items", "1", "--socket-timeout", "10",
             "--print", "%(ext)s", url],
            capture_output=True, text=True, timeout=60)
    except Exception:
        return False
    lines = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    return bool(lines) and lines[0] in VIDEO_EXTS


def clean_title(t: str) -> str:
    """Strip site/museum suffixes and reject bot-wall titles. Pure (testable)."""
    t = _html.unescape(t or "")
    t = _SITE_TAIL.sub("", t)
    t = _PIPE_TAIL.sub("", t)        # `|` is almost always a site separator
    if _BOTWALL.search(t):
        return ""
    return t.strip()


def _jsonld_query(html: str) -> str:
    """Most precise: schema.org VisualArtwork/Painting name (+creator)."""
    import json
    tree = HTMLParser(html)
    for node in tree.css('script[type="application/ld+json"]'):
        raw = node.text() or ""
        try:
            data = json.loads(raw)
        except Exception:
            continue
        for obj in _iter_objects(data):
            typ = str(obj.get("@type", "")).lower()
            name = obj.get("name")
            if name and re.search(r"painting|visualartwork|artwork", typ):
                if isinstance(name, list):
                    name = name[0] if name else ""
                creator = _creator_name(obj.get("creator") or obj.get("author"))
                return " ".join(p for p in (str(name), creator) if p).strip()
    return ""


def _iter_objects(data):
    if isinstance(data, dict):
        yield data
        for v in data.values():
            yield from _iter_objects(v)
    elif isinstance(data, list):
        for v in data:
            yield from _iter_objects(v)


def _creator_name(c) -> str:
    if isinstance(c, dict):
        return str(c.get("name", ""))
    if isinstance(c, list):
        for x in c:
            n = _creator_name(x)
            if n:
                return n
    if isinstance(c, str):
        return c
    return ""


def query_from_url(url: str) -> str:
    """Derive an artwork search query from a page URL (so you never type a name)."""
    m = _ASSET.match(url)
    if "/asset/" in url and m:                       # Google Arts & Culture
        return re.sub(r"[-_]+", " ", m.group(1)).strip()
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, follow_redirects=True,
                      timeout=15.0)
        html = r.text
    except Exception:
        return ""
    t = _jsonld_query(html)
    if not t:
        tree = HTMLParser(html)
        og = tree.css_first('meta[property="og:title"]')
        if og:
            t = og.attributes.get("content", "") or ""
        if not t:
            title = tree.css_first("title")
            t = title.text() if title else ""
    return clean_title(t)
