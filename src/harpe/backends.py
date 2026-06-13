"""Thin subprocess wrappers around the download backends."""
import re
import subprocess
from pathlib import Path

from .config import AUD_DIR, MAXPX, VID_DIR

_VID_TMPL = ("%(extractor_key)s/%(uploader_id,uploader|unknown)s/"
             "%(title).80B (%(upload_date>%Y-%m-%d|no-date)s) [%(id)s].%(ext)s")


def video(urls) -> int:
    return subprocess.run([
        "yt-dlp", "-S", "res,fps,tbr", "--merge-output-format", "mp4",
        "--embed-metadata", "-o", f"{VID_DIR}/{_VID_TMPL}", *urls]).returncode


def audio(urls) -> int:
    return subprocess.run([
        "yt-dlp", "-x", "--audio-format", "best", "--audio-quality", "0",
        "--embed-metadata", "--embed-thumbnail",
        "-o", f"{AUD_DIR}/{_VID_TMPL}", *urls]).returncode


def gallery(urls, dest) -> int:
    Path(dest).mkdir(parents=True, exist_ok=True)
    return subprocess.run(["gallery-dl", "-d", str(dest), *urls]).returncode


def dezoomify(src: str, out, maxpx: int = MAXPX) -> int:
    if maxpx and maxpx > 0:
        cmd = ["dezoomify-rs", "--max-width", str(maxpx),
               "--max-height", str(maxpx), src, str(out)]
    else:
        cmd = ["dezoomify-rs", "-l", src, str(out)]
    return subprocess.run(cmd).returncode


def slug_from_url(url: str) -> str:
    if "/asset/" in url:
        s = re.sub(r".*/asset/([^/?#]+).*", r"\1", url)
    else:
        s = re.sub(r".*/([^/?#]+).*", r"\1", url.rstrip("/"))
    return s or "artwork"
