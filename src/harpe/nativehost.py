"""Harpe as a browser native-messaging host.

The Harpe extension talks to this over Chrome/Firefox native messaging (4-byte
little-endian length prefix + UTF-8 JSON). Previously a separate `harpe_host.py`
shelled out to the `harpe` CLI; now `harpe --native-host` IS the host and calls
the engine in-process — so installing `harpe` is all a user needs (see
:mod:`harpe.installhost`), no extra script.

Message protocol (extension → host → reply):
  {"ping": true}                              → {ok, pong, defaults:{image,video,audio}, version}
  {"open": "<path>"}                          → {ok} | {ok:false, error}
  {"pick": true, "start": "<dir>"}            → {ok, path:"<chosen>"|null}
  {"urls":[…], "referer", "dirs"?, "dest"?,   → {results:[{url, ok, path?, kind?|error?}]}
   "items"?, "group"?}
"""
import json
import logging
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("harpe.nativehost")

HOST_NAME = "com.nullsense.harpe"
try:
    from importlib.metadata import version as _pkg_version
    VERSION = _pkg_version("harpe")
except Exception:
    VERSION = "0"


# ── framing ───────────────────────────────────────────────────────────────────

def read_message(stream) -> dict | None:
    raw_len = stream.read(4)
    if len(raw_len) < 4:
        return None  # stdin closed → caller exits
    (length,) = struct.unpack("<I", raw_len)
    if length == 0:
        return {}
    raw = stream.read(length)
    if len(raw) < length:
        return None
    return json.loads(raw.decode("utf-8"))


def write_message(stream, obj: dict) -> None:
    payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    stream.write(struct.pack("<I", len(payload)))
    stream.write(payload)
    stream.flush()


# ── desktop integration (open folder / pick folder) ────────────────────────────

def default_dirs() -> dict:
    """The engine's current per-type roots (honouring HARPE_*_DIR env), so the
    extension can show real default paths as placeholders."""
    from . import config
    return {"image": str(config.IMG_DIR), "video": str(config.VID_DIR),
            "audio": str(config.AUD_DIR)}


def _linux_session_env() -> dict:
    """Reconstruct the desktop session env. The browser may launch the host
    without WAYLAND_DISPLAY/DISPLAY/DBUS, which makes GUI tools (xdg-open, the
    folder picker) silently no-op — recover them from the runtime dir."""
    env = os.environ.copy()
    try:
        uid = os.getuid()
    except AttributeError:
        return env
    run = env.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}"
    env.setdefault("XDG_RUNTIME_DIR", run)
    if not env.get("WAYLAND_DISPLAY") and not env.get("DISPLAY"):
        for name in ("wayland-1", "wayland-0"):
            if os.path.exists(os.path.join(run, name)):
                env["WAYLAND_DISPLAY"] = name
                break
        env.setdefault("DISPLAY", ":0")
    if not env.get("DBUS_SESSION_BUS_ADDRESS"):
        bus = os.path.join(run, "bus")
        if os.path.exists(bus):
            env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={bus}"
    return env


def open_in_file_manager(target: str) -> None:
    """Reveal a saved file/folder in the OS file manager. Raises if no opener
    could be launched (so the extension can fall back to showing the path)."""
    p = Path(os.path.expanduser(os.path.expandvars(target)))
    folder = str(p if p.is_dir() else p.parent)
    if sys.platform == "darwin":
        subprocess.Popen(["open", folder]); return
    if os.name == "nt":
        subprocess.Popen(["explorer", folder]); return
    env = _linux_session_env()
    for cmd in (["xdg-open", folder], ["gio", "open", folder], ["nautilus", folder],
                ["dolphin", folder], ["thunar", folder], ["nemo", folder],
                ["pcmanfm", folder]):
        if shutil.which(cmd[0]):
            subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    raise RuntimeError("no file manager found (xdg-open/gio/nautilus/dolphin/thunar/nemo/pcmanfm)")


def pick_folder(start: str | None = None) -> str | None:
    """Open a native folder-chooser and return the chosen absolute path, or None
    if cancelled / unavailable. Used by the extension's 'Browse…' button."""
    start = os.path.expanduser(os.path.expandvars(start)) if start else os.path.expanduser("~")
    if sys.platform == "darwin":
        script = (f'POSIX path of (choose folder with prompt "Harpe — save to" '
                  f'default location POSIX file "{start}")')
        out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        return out.stdout.strip() or None
    if os.name == "nt":
        ps = ("Add-Type -AssemblyName System.Windows.Forms;"
              "$d=New-Object System.Windows.Forms.FolderBrowserDialog;"
              "if($d.ShowDialog() -eq 'OK'){$d.SelectedPath}")
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True)
        return out.stdout.strip() or None
    env = _linux_session_env()
    if shutil.which("zenity"):
        out = subprocess.run(["zenity", "--file-selection", "--directory",
                              f"--filename={start}/", "--title=Harpe — save to"],
                             capture_output=True, text=True, env=env)
        return out.stdout.strip() or None
    if shutil.which("kdialog"):
        out = subprocess.run(["kdialog", "--getexistingdirectory", start],
                             capture_output=True, text=True, env=env)
        return out.stdout.strip() or None
    return None


# ── request handlers ────────────────────────────────────────────────────────────

def handle(msg: dict) -> dict:
    """Dispatch one decoded request to a reply dict. Pure-ish (does real I/O for
    downloads/desktop), no framing — kept separate so it's unit-testable."""
    from . import engine

    if msg.get("ping"):
        return {"ok": True, "pong": True, "defaults": default_dirs(), "version": VERSION}

    if msg.get("open"):
        try:
            open_in_file_manager(str(msg["open"]))
            return {"ok": True}
        except Exception as exc:
            log.error("open failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    if msg.get("pick"):
        try:
            return {"ok": True, "path": pick_folder(msg.get("start"))}
        except Exception as exc:
            log.error("pick failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    urls = [str(u).strip() for u in (msg.get("urls") or []) if u and str(u).strip()]
    if not urls:
        return {"results": [], "error": "no urls provided"}

    referer = msg.get("referer") or ""
    dirs = msg.get("dirs") if isinstance(msg.get("dirs"), dict) else None
    items = msg.get("items") if isinstance(msg.get("items"), dict) else None
    group = msg.get("group") if msg.get("group") in ("site", "author", "both", "none") else "site"
    dest = None
    if isinstance(msg.get("dest"), str) and msg["dest"].strip():
        dest = os.path.expanduser(os.path.expandvars(msg["dest"].strip()))

    results = engine.fetch_images(urls, referer=referer, dest=dest,
                                  items=items, group=group, roots=dirs)
    return {"results": results}


def run() -> int:
    """Main native-messaging loop: read framed requests from stdin, reply on
    stdout, until stdin closes."""
    logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                        format="harpe-host %(levelname)s: %(message)s")
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    log.info("harpe native host started (pid=%d, v%s)", os.getpid(), VERSION)
    while True:
        try:
            msg = read_message(stdin)
        except Exception as exc:
            log.error("read error: %s", exc)
            return 1
        if msg is None:
            log.info("stdin closed — exiting")
            return 0
        if not msg:
            continue
        try:
            write_message(stdout, handle(msg))
        except Exception as exc:
            log.error("handler error: %s", exc)
            try:
                write_message(stdout, {"ok": False, "results": [], "error": str(exc)})
            except Exception:
                return 1
