"""Frontend-agnostic core. No UI, no fzf, no desktop calls — just data in/out.

A frontend (the bundled fzf TUI, a browser extension, a GUI, an HTTP service)
drives the engine with two primitives:

    scan_page(url)            -> list[dict]   # candidate images on a page
    fetch_images(urls, ...)   -> list[dict]   # download a chosen subset

…and for artwork search:

    search_art(query)         -> list[dict]   # ranked museum candidates

Everything returned is plain JSON-serializable dicts so any frontend (or the CLI
`--json` mode) can consume it. UI concerns (presenting choices, desktop
notifications) live in the frontend, not here.
"""
import dataclasses
import os
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from . import extract, rank, sources
from .config import AUD_DIR, IMG_DIR, UA, VID_DIR


# --- shared download helpers (used by the page + art flows) -----------------

def origin(url: str) -> str:
    return re.sub(r"^(https?://[^/]+)/.*", r"\1/", url)


def ext_of(url: str) -> str:
    m = re.search(r"\.([A-Za-z0-9]+)$", urlsplit(url).path)
    return m.group(1).lower() if m else ""


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    return path.with_name(f"{path.stem}-{time.strftime('%H%M%S')}{path.suffix}")


def human(n: float) -> str:
    for unit in ("B", "K", "M", "G"):
        if n < 1024 or unit == "G":
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.0f}T"


def download_file(url: str, out: Path, referer: str | None = None) -> None:
    headers = {"User-Agent": UA, "Referer": referer or origin(url)}
    with httpx.stream("GET", url, headers=headers, follow_redirects=True,
                      timeout=60.0) as r:
        r.raise_for_status()
        with open(out, "wb") as f:
            for chunk in r.iter_bytes(65536):
                f.write(chunk)


# --- primitives ------------------------------------------------------------

def scan_page(url: str) -> list[dict]:
    """Candidate images on a page, biggest first. Frontend-agnostic."""
    return [_row_to_dict(dim, u, name)
            for dim, u, name in extract.page_images(url)]


def _row_to_dict(dim: str, url: str, name: str) -> dict:
    w = h = None
    if "x" in dim:
        try:
            w, h = (int(x) for x in dim.split("x"))
        except ValueError:
            pass
    return {"url": url, "name": name, "dim": dim, "width": w, "height": h}


_MEDIA_URL_RE = re.compile(
    r"^https?://\S+\.(?:jpe?g|png|webp|gif|tiff?|bmp|avif|svg)(\?[^#\s]*)?$",
    re.IGNORECASE,
)


def enumerate_images(url: str) -> list[dict]:
    """List images on *url* without downloading, biggest first.

    Strategy:
      1. Try ``gallery-dl --get-urls <url>`` — fast, handles auth/cookies.
         Parse stdout for http(s) media URLs.
      2. If gallery-dl returns nothing OR exits 64 (unsupported URL),
         fall back to ``scan_page(url)`` (static-HTML extraction).

    Returns dicts in scan_page's shape: {url, name, dim, width, height}.
    Dims may be "?" / None for URLs that come from gallery-dl (no HEAD probe).

    Note: picked items are downloaded via httpx (fetch_images); that path
    may miss site auth/cookies that gallery-dl would supply on a full download.
    """
    try:
        proc = subprocess.run(
            ["gallery-dl", "--get-urls", url],
            capture_output=True,
            text=True,
        )
        exit_code = proc.returncode
        if exit_code != 64:  # 64 = unsupported URL
            media_urls = [
                ln.strip()
                for ln in proc.stdout.splitlines()
                if _MEDIA_URL_RE.match(ln.strip())
            ]
            if media_urls:
                return [
                    {"url": u, "name": urlsplit(u).path.rsplit("/", 1)[-1] or u,
                     "dim": "?", "width": None, "height": None}
                    for u in media_urls
                ]
    except FileNotFoundError:
        pass  # gallery-dl not installed; fall through to scan_page
    return scan_page(url)


def _root_for(kind: str) -> Path:
    """Type-appropriate download root: images → IMG_DIR, video → VID_DIR,
    audio → AUD_DIR."""
    return {"video": VID_DIR, "audio": AUD_DIR}.get(kind, IMG_DIR)


def sanitize_stem(s: str | None, limit: int = 80) -> str:
    """Filesystem-safe filename/folder stem from arbitrary text (tweet/author).
    Collapses whitespace, strips path-hostile chars, trims length."""
    s = re.sub(r"\s+", " ", (s or "").strip())
    s = re.sub(r'[\\/:*?"<>|]+', "", s)        # illegal on common filesystems
    s = re.sub(r"[^\w.\- ]+", "_", s)          # tame the rest
    return s.strip(". _")[:limit]


def _group_subpath(group: str, host: str, author: str | None) -> str:
    """Where to nest a download: by source site (default), by author/account,
    both, or flat. Author falls back to host when unknown."""
    a = sanitize_stem(author, 60)
    if group == "none":
        return ""
    if group == "author":
        return a or host
    if group == "both":
        return f"{a}/{host}" if a else host
    return host  # "site"


def _roots_from(roots: dict | None) -> dict:
    """Resolve a {kind: path} override map (expanding ~ and $VARS), falling back
    to the configured defaults for any kind not supplied."""
    out = {"image": IMG_DIR, "video": VID_DIR, "audio": AUD_DIR}
    if roots:
        for kind in out:
            v = roots.get(kind)
            if isinstance(v, str) and v.strip():
                out[kind] = Path(os.path.expanduser(os.path.expandvars(v.strip())))
    return out


def fetch_images(urls, referer: str | None = None, dest=None,
                 items: dict | None = None, group: str = "site",
                 roots: dict | None = None) -> list[dict]:
    """Download a list of media URLs (images, video, or audio). Returns one
    result dict per URL: {url, ok, path?, kind?|error?}.

    Files land in the type-appropriate root (Pictures/Videos/Music under "harpe",
    or per-type ``roots``, or a single ``dest``), nested per ``group`` ("site" |
    "author" | "both" | "none"). ``items`` optionally maps a url → {"name":
    descriptive base, "author": who} so callers (the extension) can supply a
    readable filename + account instead of the opaque CDN basename. The saved
    extension is corrected from the response Content-Type, so a Twitter MP4 is
    saved as .mp4, not .jpg."""
    base = Path(dest) if dest else None
    typed = _roots_from(roots)
    items = items or {}
    results = []
    for url in urls:
        host = urlsplit(referer or url).netloc or "harpe"
        meta = items.get(url) or {}
        try:
            out, kind = _download_media(url, out_base=base, host=host, referer=referer,
                                        suggested=meta.get("name"),
                                        author=meta.get("author"), group=group, roots=typed)
            results.append({"url": url, "ok": True, "path": str(out), "kind": kind})
        except Exception as e:
            results.append({"url": url, "ok": False, "error": str(e)})
    return results


def _download_media(url: str, out_base, host: str, referer: str | None,
                    suggested: str | None = None, author: str | None = None,
                    group: str = "site", roots: dict | None = None):
    """Stream one URL to disk, choosing the filename + folder from a caller hint,
    the response Content-Type, and the URL (in that order). Returns (path, kind)."""
    headers = {"User-Agent": UA, "Referer": referer or origin(url)}
    url_name = extract.display_name(url)
    with httpx.stream("GET", url, headers=headers, follow_redirects=True,
                      timeout=60.0) as r:
        r.raise_for_status()
        ct_ext = extract.ext_from_content_type(r.headers.get("content-type"))

        # Stem: prefer a descriptive caller-supplied name, else the URL basename.
        stem = sanitize_stem(suggested) if suggested else ""
        if not stem:
            stem = url_name
            for e in extract.MEDIA_EXT:
                if stem.lower().endswith(e):
                    stem = stem[: -len(e)]
                    break
        # Extension: Content-Type wins; else the URL's real media ext; else .jpg.
        url_ext = Path(url_name).suffix
        ext = ct_ext or (url_ext if url_ext.lower() in extract.MEDIA_EXT else ".jpg")
        name = stem + ext
        kind = extract.kind_for_ext(ext)

        # Explicit dest = exact folder. Otherwise nest under the type root
        # (caller override or default) by the chosen grouping.
        if out_base is not None:
            d = out_base
        else:
            root = (roots or {}).get(kind) or _root_for(kind)
            sub = _group_subpath(group, host, author)
            d = root / sub if sub else root
        d.mkdir(parents=True, exist_ok=True)
        out = unique_path(d / name)
        with open(out, "wb") as f:
            for chunk in r.iter_bytes(65536):
                f.write(chunk)
    return out, kind


def search_art(query: str) -> list[dict]:
    """Ranked artwork candidates across museum sources. Frontend-agnostic."""
    return [dataclasses.asdict(c) for c in rank.rank(query, sources.gather(query))]
