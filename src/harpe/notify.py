"""Desktop notification + clipboard — cross-platform.

On Linux it delegates to the rich bash helper ~/bin/grab-notify when present
(thumbnail icon + image-to-clipboard). Otherwise it uses a built-in path:
macOS via osascript, bare Linux via notify-send / wl-copy. All best-effort —
silently no-ops if the tools (or a display) are missing.
"""
import shutil
import subprocess
import sys

from .config import GRAB_NOTIFY


def send(path, caption: str = "Saved", body: str = "") -> None:
    p = str(path)
    if GRAB_NOTIFY.exists():
        subprocess.run([str(GRAB_NOTIFY), p, caption, body])
        return
    if sys.platform == "darwin":
        _mac(p, caption, body)
    else:
        _linux(p, caption, body)


def _mac(path: str, caption: str, body: str) -> None:
    if not shutil.which("osascript"):
        return
    subprocess.run(["osascript", "-e", _applescript_setclip(path)],
                   capture_output=True)
    subprocess.run(["osascript", "-e", _applescript_notify(caption, body)],
                   capture_output=True)


def _linux(path: str, caption: str, body: str) -> None:
    if shutil.which("wl-copy"):
        if shutil.which("magick"):
            png = subprocess.run(["magick", path, "-resize", "3000x3000>", "png:-"],
                                 capture_output=True)
            if png.returncode == 0:
                subprocess.run(["wl-copy", "--type", "image/png"], input=png.stdout)
        if caption or body:
            subprocess.run(["wl-copy", "--primary"],
                           input=f"{caption}\n\n{body}".encode())
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", "-a", "harpe", "-i", path, f"🖼 {caption}", body])


def _osa_escape(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _applescript_notify(caption: str, body: str) -> str:
    return (f'display notification "{_osa_escape(body)}" '
            f'with title "{_osa_escape(caption)}"')


def _applescript_setclip(path: str) -> str:
    # PNG class is the reliable one; other formats may not stick (best-effort).
    return (f'set the clipboard to (read (POSIX file "{_osa_escape(path)}") '
            f'as «class PNGf»)')
