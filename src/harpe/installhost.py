"""Register Harpe as a native-messaging host for installed browsers.

This is what makes the engine "just work" after install (`uv tool install
git+https://github.com/NullSense/harpe`) — no
separate shell script for the user to run. It writes a tiny launcher that runs
`harpe --native-host`, then drops the host manifest into each browser's
NativeMessagingHosts directory (or the Windows registry), allowing the Harpe
extension to connect.

Public API: install(...) / uninstall(...) / is_installed(), plus a first-run
auto-register helper used by the CLI.
"""
import json
import os
import shutil
import sys
from pathlib import Path

HOST_NAME = "com.nullsense.harpe"
EXTENSION_ID = "ginhcamellmffiamggkiaemdklcnechf"   # Chromium id (from manifest "key")
GECKO_ID = "harpe@nullsense.com"                      # Firefox id
_DESC = "Harpe native messaging host — downloads media via the harpe engine."


def _data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "harpe"
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "harpe"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "harpe"


def _state_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "harpe"
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "harpe"
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "harpe"


def _harpe_command() -> list[str]:
    """How to invoke harpe. Prefer the installed console script; fall back to
    `python -m harpe` so a `pip install -e .` checkout works too."""
    exe = shutil.which("harpe")
    if exe:
        return [exe]
    return [sys.executable, "-m", "harpe"]


def write_launcher() -> str:
    """Write the launcher the browser executes, returning its absolute path. It
    just runs `harpe --native-host`, absorbing whatever args the browser appends."""
    d = _data_dir()
    d.mkdir(parents=True, exist_ok=True)
    cmd = _harpe_command()
    if os.name == "nt":
        path = d / "harpe-native-host.bat"
        quoted = " ".join(f'"{c}"' for c in cmd)
        path.write_text(f'@echo off\r\n{quoted} --native-host %*\r\n')
        return str(path)
    path = d / "harpe-native-host"
    quoted = " ".join(f'"{c}"' for c in cmd)
    path.write_text(f'#!/bin/sh\nexec {quoted} --native-host "$@"\n')
    path.chmod(0o755)
    return str(path)


# ── manifest payloads ───────────────────────────────────────────────────────────

def _chrome_manifest(launcher: str, ids: list[str]) -> dict:
    return {"name": HOST_NAME, "description": _DESC, "path": launcher, "type": "stdio",
            "allowed_origins": [f"chrome-extension://{i}/" for i in ids]}


def _firefox_manifest(launcher: str, ids: list[str]) -> dict:
    return {"name": HOST_NAME, "description": _DESC, "path": launcher, "type": "stdio",
            "allowed_extensions": ids}


# ── per-OS browser locations ────────────────────────────────────────────────────

def _browser_dirs() -> tuple[list[Path], list[Path], str, str]:
    """Returns (chromium_base_dirs, firefox_base_dirs, chromium_subdir, firefox_subdir)."""
    home = Path.home()
    if sys.platform == "darwin":
        a = home / "Library" / "Application Support"
        chromium = [a / "Google/Chrome", a / "Google/Chrome Beta", a / "Chromium",
                    a / "BraveSoftware/Brave-Browser", a / "Microsoft Edge", a / "Vivaldi",
                    a / "net.imput.helium"]
        firefox = [a / "Mozilla", a / "LibreWolf", a / "zen"]
        return chromium, firefox, "NativeMessagingHosts", "NativeMessagingHosts"
    c = home / ".config"
    chromium = [c / "google-chrome", c / "google-chrome-beta", c / "chromium",
                c / "BraveSoftware/Brave-Browser", c / "microsoft-edge", c / "vivaldi",
                c / "helium"]
    firefox = [home / ".mozilla", home / ".librewolf", home / ".zen"]
    return chromium, firefox, "NativeMessagingHosts", "native-messaging-hosts"


# ── Windows registry ─────────────────────────────────────────────────────────────

_WIN_CHROME_KEYS = [r"Software\Google\Chrome\NativeMessagingHosts",
                    r"Software\Microsoft\Edge\NativeMessagingHosts",
                    r"Software\Chromium\NativeMessagingHosts",
                    r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts"]
_WIN_FIREFOX_KEYS = [r"Software\Mozilla\NativeMessagingHosts"]


def _install_windows(launcher, chrome_ids, firefox_ids):
    import winreg
    d = _data_dir()
    chrome_mf = d / f"{HOST_NAME}.json"
    ff_mf = d / f"{HOST_NAME}.firefox.json"
    chrome_mf.write_text(json.dumps(_chrome_manifest(launcher, chrome_ids), indent=2))
    ff_mf.write_text(json.dumps(_firefox_manifest(launcher, firefox_ids), indent=2))
    written = []
    for base, mf in [(_WIN_CHROME_KEYS, chrome_mf), (_WIN_FIREFOX_KEYS, ff_mf)]:
        for keypath in base:
            try:
                k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{keypath}\\{HOST_NAME}")
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, str(mf))
                winreg.CloseKey(k)
                written.append(keypath)
            except OSError:
                pass
    return written


def _uninstall_windows():
    import winreg
    for keypath in _WIN_CHROME_KEYS + _WIN_FIREFOX_KEYS:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, f"{keypath}\\{HOST_NAME}")
        except OSError:
            pass


# ── public API ───────────────────────────────────────────────────────────────────

def install(extra_chrome_ids=None, extra_firefox_ids=None, all_browsers=False) -> list[str]:
    """Register the host for every detected browser. Returns the list of written
    manifest paths (or registry key paths on Windows). Idempotent."""
    chrome_ids = [EXTENSION_ID, *(extra_chrome_ids or [])]
    firefox_ids = [GECKO_ID, *(extra_firefox_ids or [])]
    launcher = write_launcher()

    if os.name == "nt":
        written = _install_windows(launcher, chrome_ids, firefox_ids)
    else:
        chromium, firefox, ch_sub, ff_sub = _browser_dirs()
        written = []
        for base in chromium:
            if all_browsers or base.is_dir():
                dest = base / ch_sub
                dest.mkdir(parents=True, exist_ok=True)
                f = dest / f"{HOST_NAME}.json"
                f.write_text(json.dumps(_chrome_manifest(launcher, chrome_ids), indent=2))
                written.append(str(f))
        for base in firefox:
            if all_browsers or base.is_dir():
                dest = base / ff_sub
                dest.mkdir(parents=True, exist_ok=True)
                f = dest / f"{HOST_NAME}.json"
                f.write_text(json.dumps(_firefox_manifest(launcher, firefox_ids), indent=2))
                written.append(str(f))
    _state_dir().mkdir(parents=True, exist_ok=True)
    (_state_dir() / "host-installed").write_text(launcher + "\n")
    return written


def uninstall() -> list[str]:
    """Remove the host manifest from every browser. Returns removed paths."""
    removed = []
    if os.name == "nt":
        _uninstall_windows()
    else:
        chromium, firefox, ch_sub, ff_sub = _browser_dirs()
        for base in chromium:
            f = base / ch_sub / f"{HOST_NAME}.json"
            if f.exists():
                f.unlink(); removed.append(str(f))
        for base in firefox:
            f = base / ff_sub / f"{HOST_NAME}.json"
            if f.exists():
                f.unlink(); removed.append(str(f))
    sentinel = _state_dir() / "host-installed"
    if sentinel.exists():
        sentinel.unlink()
    return removed


def is_installed() -> bool:
    return (_state_dir() / "host-installed").exists()


def auto_register_once() -> None:
    """Best-effort first-run registration: if the host has never been installed,
    register it silently (one note to stderr). Lets installing harpe be the
    only step. Guarded by a sentinel so it runs once."""
    if is_installed():
        return
    try:
        written = install()
        if written:
            print(f"harpe: registered native host for the browser extension "
                  f"({len(written)} location(s)). Run `harpe uninstall-host` to undo.",
                  file=sys.stderr)
    except Exception:
        pass  # never block normal CLI use on registration trouble
