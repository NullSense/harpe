"""Paths, user agents, and env-tunable knobs."""
import os
import sys
from pathlib import Path

HOME = Path.home()
# macOS calls the video folder "Movies"; Linux/Windows use "Videos".
_VIDEOS = "Movies" if sys.platform == "darwin" else "Videos"
# Default download roots, grouped by media type. Override any of them with the
# HARPE_*_DIR env vars (e.g. HARPE_IMG_DIR) — the browser extension passes its
# own --dest, which takes precedence over all of these.
VID_DIR = Path(os.environ.get("HARPE_VID_DIR", HOME / _VIDEOS / "harpe"))
IMG_DIR = Path(os.environ.get("HARPE_IMG_DIR", HOME / "Pictures" / "harpe"))
ART_DIR = Path(os.environ.get("HARPE_ART_DIR", IMG_DIR / "art"))
AUD_DIR = Path(os.environ.get("HARPE_AUD_DIR", HOME / "Music" / "harpe"))

# Browser UA — some museum/CDN servers (Met/Vercel, AIC IIIF) bot-block non-browser
# agents and hotlinks. Used for image downloads + previews.
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"
# Polite descriptive UA for the API / SPARQL calls.
API_UA = "harpe/0.1 (personal art archival; +https://commons.wikimedia.org)"

BIN = HOME / "bin"
# Preview helper ships WITH the repo (cross-platform: needs only curl/file/chafa),
# so it isn't tied to the Linux ~/bin layout; fall back to ~/bin if absent.
_BUNDLED_THUMB = Path(__file__).resolve().parents[2] / "bin" / "grab-thumb"
GRAB_THUMB = _BUNDLED_THUMB if _BUNDLED_THUMB.exists() else BIN / "grab-thumb"
# Desktop notify + clipboard: the Linux bash helper if present, else notify.py's
# built-in cross-platform path (macOS osascript / Linux notify-send).
GRAB_NOTIFY = BIN / "grab-notify"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# Long-edge cap for saved art so gigapixel scans actually open in viewers.
# 0 = full resolution. (IIIF is capped at the source via dezoomify --max-*.)
MAXPX = _env_int("GRAB_ART_MAXPX", 7680)
# Page-image picker: drop images whose long edge is below this (chrome icons),
# and cap how many candidates we probe. 100 keeps real thumbnails (book covers,
# gallery tiles ~120-200px) while dropping 16-64px UI icons; the floor is auto-
# relaxed if it would empty the list (see extract.select).
PAGE_MINPX = _env_int("GRAB_PAGE_MINPX", 100)
PAGE_MAX = _env_int("GRAB_PAGE_MAX", 200)


def firecrawl_key() -> str | None:
    """12-factor: the tool only READS the key. Caller injects via `infisical run`.
    Also accept a plain key file as a no-Infisical fallback."""
    k = os.environ.get("FIRECRAWL_API_KEY")
    if k:
        return k
    f = HOME / ".config" / "grab" / "firecrawl.key"
    if f.is_file():
        v = f.read_text().strip()
        if v:
            return v
    return None
