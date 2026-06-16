"""Tier-1 page-image extraction: enumerate images in static HTML, biggest first.

Pulls candidate image URLs from <img> src/srcset/lazy-attrs, <source> srcset,
<a> links to image files, inline CSS background-image, <link rel=preload>, and
og/twitter meta — maps Wikimedia thumbnails back to their full-res originals,
collapses CDN size-variants, then probes each one's real pixel dimensions with a
tiny ranged GET (header bytes only) so they can be ranked and icons dropped.

Static HTML only — images injected purely by JS / lazy-loaded on scroll are not
visible here (that's the Tier-2 rendered-DOM job).
"""
import asyncio
import re
from urllib.parse import urldefrag, urljoin, urlsplit, unquote, parse_qs

import httpx
from PIL import ImageFile
from selectolax.parser import HTMLParser

from .config import PAGE_MAX, PAGE_MINPX, UA

IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".tiff", ".tif", ".bmp")
VIDEO_EXT = (".mp4", ".webm", ".mkv", ".mov", ".m4v", ".ts")
AUDIO_EXT = (".mp3", ".m4a", ".aac", ".opus", ".ogg", ".oga", ".wav", ".flac")
# Every extension the fetcher recognises as a real media file (so a video URL
# like .../clip.mp4 keeps its suffix instead of being mislabelled .jpg).
MEDIA_EXT = IMG_EXT + VIDEO_EXT + AUDIO_EXT

# Map a server Content-Type to a canonical extension — used to repair the
# filename when the URL has no/ambiguous extension (common on CDN download URLs).
_CT_EXT = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
    "image/webp": ".webp", "image/avif": ".avif", "image/tiff": ".tiff",
    "image/bmp": ".bmp", "image/svg+xml": ".svg",
    "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov",
    "video/x-matroska": ".mkv", "video/mp2t": ".ts",
    "audio/mpeg": ".mp3", "audio/mp4": ".m4a", "audio/aac": ".aac",
    "audio/ogg": ".ogg", "audio/opus": ".opus",
    "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/flac": ".flac",
}


def ext_from_content_type(ct: str | None) -> str | None:
    """Canonical extension for a Content-Type header value, or None if unknown."""
    if not ct:
        return None
    return _CT_EXT.get(ct.split(";")[0].strip().lower())


def kind_for_ext(ext: str) -> str:
    """Classify a file extension as 'video', 'audio', or (default) 'image'."""
    ext = ext.lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    return "image"
LAZY_ATTRS = ("data-src", "data-lazy-src", "data-original", "data-hi-res-src",
              "data-large", "data-zoom-image", "data-image")
_WM_THUMB = re.compile(
    r"^(https?://upload\.wikimedia\.org/wikipedia/[^/]+/)thumb/(.+?)/\d+px-[^/]+$")
_PX = re.compile(r"/(\d{2,5})px-")


def _wm_original(url: str) -> str:
    """Map a Wikimedia thumbnail URL to its full-resolution original."""
    m = _WM_THUMB.match(url)
    return m.group(1) + m.group(2) if m else url


def _size_hint(url: str, descriptor: int = 0) -> int:
    if descriptor:
        return descriptor
    qs = parse_qs(urlsplit(url).query)
    for k in ("w", "width", "sz", "size", "mw"):
        if k in qs:
            digits = re.sub(r"\D", "", qs[k][0])
            if digits:
                return int(digits)
    m = _PX.search(url)
    return int(m.group(1)) if m else 0


def _add_srcset(value, add):
    if not value:
        return
    for part in value.split(","):
        toks = part.strip().split()
        if not toks:
            continue
        desc = 0
        if len(toks) > 1 and toks[1].endswith("w"):
            try:
                desc = int(toks[1][:-1])
            except ValueError:
                desc = 0
        add(toks[0], desc)


def collect(html: str, base: str) -> list[str]:
    """Return de-duplicated absolute image URLs found in the HTML."""
    raw: list[tuple[str, int]] = []

    def add(u, descriptor=0):
        if not u:
            return
        u = u.strip()
        if not u or u.startswith(("data:", "javascript:")):
            return
        u = urldefrag(urljoin(base, u))[0]
        if u.startswith("http"):
            raw.append((u, descriptor))

    tree = HTMLParser(html)
    for img in tree.css("img"):
        a = img.attributes
        add(a.get("src"))
        _add_srcset(a.get("srcset"), add)
        _add_srcset(a.get("data-srcset"), add)
        for attr in LAZY_ATTRS:
            if a.get(attr):
                add(a.get(attr))
    for src in tree.css("source"):
        _add_srcset(src.attributes.get("srcset"), add)
    for a_ in tree.css("a[href]"):
        href = a_.attributes.get("href") or ""
        if urlsplit(href).path.lower().endswith(IMG_EXT):
            add(href)
    for ln in tree.css('link[rel="preload"]'):
        if ln.attributes.get("as") == "image":
            add(ln.attributes.get("href"))
    for m in tree.css("meta"):
        a = m.attributes
        if (a.get("property") in ("og:image", "og:image:url")
                or a.get("name") == "twitter:image"):
            add(a.get("content"))
    for el in tree.css("[style]"):
        for mm in re.finditer(r"url\((['\"]?)(.*?)\1\)",
                              el.attributes.get("style") or ""):
            add(mm.group(2))

    # Normalize Wikimedia thumbs to originals, then keep one URL per (host, path),
    # preferring the largest known size variant (collapses ?w=400 vs ?w=2000 and
    # /330px- vs /960px- to the biggest). Originals always win over any thumb.
    best: dict[tuple[str, str], tuple[str, int]] = {}
    for u, desc in raw:
        u2 = _wm_original(u)
        hint = 10 ** 7 if u2 != u else _size_hint(u, desc)
        s = urlsplit(u2)
        key = (s.netloc, s.path)
        if key not in best or hint > best[key][1]:
            best[key] = (u2, hint)
    return [v[0] for v in best.values()]


async def _probe(client, url):
    """Probe an image's dimensions from its leading bytes.

    Returns (verdict, size) where verdict is:
      "ok"    — got real dimensions (size is (w, h))
      "image" — confirmed image/* but couldn't read size from the header window
      "retry" — rate-limited / timed out / errored (might be a real image)
      "drop"  — confirmed NON-image response (HTML wrapper, SVG, etc.) → discard
    Only header bytes are read, never the whole file. Retries once on HTTP 429
    (Wikimedia rate-limits bursts of ranged GETs).
    """
    for attempt in (0, 1):
        try:
            async with client.stream("GET", url,
                                     headers={"Range": "bytes=0-131071"},
                                     timeout=8.0) as r:
                if r.status_code == 429 and attempt == 0:
                    await asyncio.sleep(0.4)
                    continue
                if r.status_code >= 400:
                    return "retry", None
                ct = r.headers.get("content-type", "").split(";")[0].strip().lower()
                if ct == "image/svg+xml":
                    return "drop", None          # not raster, not useful here
                if ct and not ct.startswith("image/"):
                    return "drop", None          # HTML wrapper / error page
                parser = ImageFile.Parser()
                read = 0
                async for chunk in r.aiter_bytes(16384):
                    parser.feed(chunk)
                    read += len(chunk)
                    if parser.image is not None:
                        return "ok", parser.image.size
                    if read >= 131072:
                        break
                return "image", None
        except Exception:
            return "retry", None
    return "retry", None


async def _probe_all(urls):
    # 8 connections is polite enough to avoid Wikimedia 429s while still fast.
    limits = httpx.Limits(max_connections=8)
    async with httpx.AsyncClient(follow_redirects=True,
                                 headers={"User-Agent": UA},
                                 limits=limits) as c:
        sem = asyncio.Semaphore(8)

        async def one(u):
            async with sem:
                return (u, *await _probe(c, u))

        return await asyncio.gather(*(one(u) for u in urls))


def display_name(url: str) -> str:
    n = unquote(urlsplit(url).path.rsplit("/", 1)[-1]) or "image"
    n = re.sub(r"[^\w.\- ]+", "_", n)[:80]
    if not n.lower().endswith(MEDIA_EXT):
        n += ".jpg"
    return n


def page_images(page: str) -> list[tuple[str, str, str]]:
    """Return rows of (WxH|?, url, display_name), largest first, unknowns last."""
    with httpx.Client(follow_redirects=True,
                      headers={"User-Agent": UA, "Accept-Language": "en"},
                      timeout=20.0) as c:
        r = c.get(page)
        base, html = str(r.url), r.text
    urls = collect(html, base)[:PAGE_MAX]
    if not urls:
        return []
    selected = select(asyncio.run(_probe_all(urls)), PAGE_MINPX)
    return [(dim, u, display_name(u)) for dim, u in selected]


def select(probed, minpx):
    """Turn probe results into ranked (dim, url) rows. Pure (testable).

    `probed` is a list of (url, verdict, size). Drops confirmed non-images, ranks
    by pixel area (biggest first), keeps unknown-size images at the bottom. The
    `minpx` floor removes chrome icons — BUT if applying it would hide every real
    image (e.g. a catalog of small thumbnails), it's relaxed so you never get an
    empty picker when the page actually has images.
    """
    ok, unknown = [], []
    for url, verdict, size in probed:
        if verdict == "drop":                 # confirmed non-image (HTML/SVG)
            continue
        if verdict == "ok" and size:
            w, h = size
            ok.append((w * h, f"{w}x{h}", url, max(w, h)))
        else:                                 # image/* but size unknown / rate-limited
            unknown.append((-1, "?", url))
    big = [r for r in ok if r[3] >= minpx]
    use = big if big else ok                  # never hide all real images
    rows = [(a, dim, u) for a, dim, u, _edge in use] + unknown
    rows.sort(key=lambda r: r[0], reverse=True)
    return [(dim, u) for _area, dim, u in rows]
