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
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from . import extract, rank, sources
from .config import IMG_DIR, UA


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


def fetch_images(urls, referer: str | None = None, dest=None) -> list[dict]:
    """Download a list of image URLs. Returns one result dict per URL:
    {url, ok, path?|error?}. The default destination is IMG_DIR/<host>."""
    base = Path(dest) if dest else None
    results = []
    for url in urls:
        d = base or (IMG_DIR / (urlsplit(referer or url).netloc or "harpe"))
        d.mkdir(parents=True, exist_ok=True)
        out = unique_path(d / extract.display_name(url))
        try:
            download_file(url, out, referer)
            results.append({"url": url, "ok": True, "path": str(out)})
        except Exception as e:
            results.append({"url": url, "ok": False, "error": str(e)})
    return results


def search_art(query: str) -> list[dict]:
    """Ranked artwork candidates across museum sources. Frontend-agnostic."""
    return [dataclasses.asdict(c) for c in rank.rank(query, sources.gather(query))]
