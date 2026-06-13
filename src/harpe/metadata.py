"""Filename slugs, captions, lossless metadata embedding, and the resolution cap."""
import re
import shutil
import subprocess
from pathlib import Path

from .config import MAXPX
from .models import Candidate


def name_parts(cand: Candidate) -> tuple[str, str, str]:
    """Return (display_name, artist, year). Drops nationality/life-date suffixes."""
    artist = re.sub(r"\s*\(.*\)$", "", cand.artist or "")
    ym = re.search(r"\d{3,4}", cand.date or "")
    year = ym.group(0) if ym else ""
    name = cand.title or "artwork"
    if artist:
        name = f"{artist} - {cand.title}"
    if year:
        name = f"{name} ({year})"
    name = f"{name} [{cand.source}]"
    return name, artist, year


def build_slug(cand: Candidate) -> str:
    name, _, _ = name_parts(cand)
    slug = re.sub(r'[/\\:*?"<>|]+', " ", name)
    slug = re.sub(r"[\x00-\x1f]", "", slug)
    slug = re.sub(r"\s+", " ", slug).strip()[:150]
    return slug or "artwork"


def captions(cand: Candidate, res: str) -> tuple[str, str]:
    _, artist, year = name_parts(cand)
    caption = cand.title
    if artist:
        caption = f"{artist} — {cand.title}"
    if year:
        caption = f"{caption} ({year})"
    parts = [p for p in (cand.medium, cand.physdim) if p]
    body = "\n".join(parts)
    line = f"{res} · {cand.source}"
    body = f"{body}\n{line}" if body else line
    if cand.desc:
        body = f"{body}\n\n{cand.desc}"
    return caption, body


def image_res(path) -> str | None:
    try:
        out = subprocess.run(["identify", "-format", "%wx%h", f"{path}[0]"],
                             capture_output=True, text=True)
        return out.stdout.strip() or None
    except Exception:
        return None


def cap_image(path) -> None:
    """Downscale in place if it exceeds MAXPX on either axis (0 = keep full res)."""
    if not (MAXPX and MAXPX > 0) or not shutil.which("magick"):
        return
    res = image_res(path)
    if not res or "x" not in res:
        return
    try:
        w, h = (int(x) for x in res.split("x"))
    except ValueError:
        return
    if w <= MAXPX and h <= MAXPX:
        return
    subprocess.run(["magick", str(path), "-resize", f"{MAXPX}x{MAXPX}>", str(path)])


def embed(path, cand: Candidate, caption: str) -> bool:
    """Embed metadata into the image losslessly (exiftool, else exiv2)."""
    _, artist, _ = name_parts(cand)
    src = cand.source_url
    if shutil.which("exiftool"):
        cmd = ["exiftool", "-overwrite_original", "-q", "-m",
               f"-IFD0:ImageDescription={caption}", f"-IFD0:Artist={artist}",
               f"-XMP-dc:Title={cand.title}", f"-XMP-dc:Creator={artist}",
               f"-XMP-dc:Description={cand.desc}", f"-XMP-dc:Date={cand.date}",
               f"-XMP-dc:Format={cand.medium}", f"-XMP-dc:Source={src}",
               str(path)]
        if subprocess.run(cmd, capture_output=True).returncode == 0:
            return True
    if shutil.which("exiv2"):
        m = [f"-Mset Exif.Image.ImageDescription {caption}"]
        if artist:
            m.append(f"-Mset Exif.Image.Artist {artist}")
        m.append(f"-Mset Xmp.dc.title {cand.title}")
        if artist:
            m.append(f"-Mset Xmp.dc.creator {artist}")
        if cand.desc:
            m.append(f"-Mset Xmp.dc.description {cand.desc}")
        if cand.date:
            m.append(f"-Mset Xmp.dc.date {cand.date}")
        if cand.medium:
            m.append(f"-Mset Xmp.dc.format {cand.medium}")
        if cand.physdim:
            m.append(f"-Mset Xmp.dc.extent {cand.physdim}")
        m.append(f"-Mset Xmp.dc.source {src}")
        if subprocess.run(["exiv2", *m, str(path)],
                          capture_output=True).returncode == 0:
            return True
    return False


def write_sidecar(path, cand: Candidate, res: str) -> None:
    """Fallback when no embedder is installed."""
    p = Path(f"{path}.txt")
    lines = [f"Title: {cand.title}"]
    if cand.artist:
        lines.append(f"Artist: {cand.artist}")
    if cand.date:
        lines.append(f"Date: {cand.date}")
    if cand.medium:
        lines.append(f"Medium: {cand.medium}")
    if cand.physdim:
        lines.append(f"Dimensions: {cand.physdim}")
    lines += [f"Resolution: {res}", f"Source: {cand.source}",
              f"Source URL: {cand.source_url}"]
    if cand.desc:
        lines += ["", cand.desc]
    p.write_text("\n".join(lines) + "\n")
