"""harpe — command-line dispatcher and the bundled fzf frontend.

  harpe                 interactive: paste/type a URL, then route like auto
  harpe <url>...        auto-detect backend; >1 image → fzf picker to choose
  harpe -v <url>        video      (yt-dlp, true max quality)
  harpe -A <url>        audio only (yt-dlp -x, no re-encode)
  harpe -i <url>        images     (gallery-dl whole gallery, no picking)
  harpe -p <url>        page picker (static-HTML scan, pick which images to grab)
  harpe -a <url>        art/zoomable (dezoomify-rs)
  harpe -r <url|img>    reverse image: find source + highest-res copy
  harpe -s <query|url>  artwork scans across museums (a URL auto-derives the name)
  harpe -F <url>...     fetch: download given image URLs (the engine's download half)
  harpe install-host    register the browser-extension native host (auto on first run)
  harpe uninstall-host  remove the native-host registration
  harpe --native-host   speak the browser native-messaging protocol (run BY the browser)

Default auto mode enumerates images first (via gallery-dl --get-urls or static scan):
  exactly 1 found → download directly; >1 → fzf picker; 0 → gallery-dl full download.
  Use -i to always download the whole gallery without prompting.

Frontend-agnostic use (browser extension / GUI / service):
  harpe -p <url> --json            -> JSON candidate list (no UI); or scan the DOM yourself
  harpe -s <query> --json          -> JSON ranked museum candidates
  harpe -F <url>... [--referer R] [--dest D] [--json]  -> download a chosen subset
The default (no --json) launches the bundled fzf picker. See engine.py for the API.
"""
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from . import (backends, describe, engine, metadata, notify, picker, rank,
               routing, sources)
from .config import ART_DIR, IMG_DIR, UA
from .reverse import reverse_search

_C, _R = "\033[1;36m", "\033[0m"


def note(msg: str) -> None:
    print(f"{_C}▸ {msg}{_R}", file=sys.stderr)


def die(msg: str) -> int:
    print(f"harpe: {msg}", file=sys.stderr)
    raise SystemExit(1)


class Spinner:
    """Braille spinner on stderr for network waits. Silent when not a TTY."""
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, msg: str):
        self.msg = msg
        self._stop = None
        self._thread = None

    def __enter__(self):
        import threading
        if sys.stderr.isatty():
            self._stop = threading.Event()
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        else:
            note(f"{self.msg}…")
        return self

    def _spin(self):
        import itertools
        import time
        for ch in itertools.cycle(self.FRAMES):
            if self._stop.is_set():
                break
            print(f"\r{_C}{ch} {self.msg}…{_R}", end="", file=sys.stderr, flush=True)
            time.sleep(0.08)

    def __exit__(self, *exc):
        if self._stop:
            self._stop.set()
            self._thread.join(timeout=0.3)
            print("\r\033[K", end="", file=sys.stderr, flush=True)


# --- download backends (pass-through) --------------------------------------

def flow_video(urls):
    note("video → yt-dlp")
    return backends.video(urls)


def flow_audio(urls):
    note("audio → yt-dlp (extract, no re-encode)")
    return backends.audio(urls)


def flow_image(urls):
    """Download the entire gallery via gallery-dl — no picking (-i flag)."""
    note("images → gallery-dl (whole gallery)")
    import time
    start = time.time()
    rc = backends.gallery(urls, IMG_DIR)
    if rc == 64:                       # gallery-dl: Unsupported URL
        page = next((u for u in urls if not u.startswith("-")), None)
        if page:
            note("gallery-dl has no extractor for that URL — scanning the page "
                 "for images instead")
            return flow_page(page)
        return rc
    _notify_newest(IMG_DIR, start, "gallery-dl")
    return rc


def flow_art(urls):
    note("art → dezoomify-rs")
    ART_DIR.mkdir(parents=True, exist_ok=True)
    rc = 0
    for url in urls:
        if url.startswith("-"):
            continue
        out = engine.unique_path(ART_DIR / f"{backends.slug_from_url(url)}.jpg")
        if backends.dezoomify(url, out, maxpx=0) != 0:   # explicit -a = full res
            note(f"dezoomify-rs failed on {url}")
            rc = 1
        else:
            note(f"saved → {out}")
    return rc


# --- page picker (engine.scan_page + fzf frontend + engine.fetch_images) ----

def flow_page(page, as_json=False):
    if as_json:
        print(json.dumps(engine.scan_page(page)))
        return 0
    with Spinner("scanning page for images"):
        cands = engine.scan_page(page)
    if not cands:
        note("no images in the page's static HTML — it may load them with "
             "JavaScript or on scroll (that's the Tier-2 rendered-DOM path)")
        return 1
    note(f"{len(cands)} image(s) found")
    picks = picker.pick_page([(c["dim"], c["url"], c["name"]) for c in cands])
    if not picks:
        return 0                      # cancel is not an error
    return _save_and_notify(
        engine.fetch_images([u for u, _n in picks], referer=page))


def flow_fetch(args, as_json=False, referer=None, dest=None):
    urls = _read_urls(args)
    if not urls:
        return die("no image URLs given")
    results = engine.fetch_images(urls, referer=referer, dest=dest)
    if as_json:
        print(json.dumps(results))
        return 0 if any(r["ok"] for r in results) else 1
    return _save_and_notify(results)


def _save_and_notify(results):
    saved = [r for r in results if r["ok"]]
    for r in results:
        if r["ok"]:
            try:
                sz = engine.human(Path(r["path"]).stat().st_size)
            except OSError:
                sz = "?"
            note(f"saved → {r['path']} ({sz})")
        else:
            note(f"failed: {r['url']} ({r.get('error')})")
    if saved:
        last = saved[-1]["path"]
        n = len(saved)
        host = urlsplit(saved[-1]["url"]).netloc
        notify.send(last, f"Saved {n} image{'s' if n != 1 else ''}",
                    f"{Path(last).name}\n{host}")
        note(f"notified + copied to clipboard ({n} saved)")
    return 0 if saved else 1


def _read_urls(args):
    if args == ["-"]:
        return [ln.strip() for ln in sys.stdin if ln.strip()]
    return [a for a in args if not a.startswith("-")]


# --- reverse image ----------------------------------------------------------

def flow_reverse(input_url):
    import shutil
    import subprocess

    from .config import GRAB_THUMB
    img = _resolve_image(input_url)
    note(f"image: {img}")
    note("searching reverse-image engines (a few seconds)…")
    hits = reverse_search(img)            # "engine\tsim\ttitle\turl\tthumb"
    if not hits:
        enc = httpx.QueryParams({"url": img})
        note("no matches found — opening Yandex visual search instead…")
        _open(f"https://yandex.com/images/search?rpt=imageview&{enc}")
        return 0
    if not shutil.which("fzf"):
        return die("fzf required for reverse search")
    args = ["fzf", "--delimiter=\t", "--with-nth=1,2,3",
            f"--preview={GRAB_THUMB} {{5}} {{1}} · {{2}} · {{3}}",
            "--preview-window=right,48%,border-left",
            "--header=🔎  matches · most relevant first · full-res preview →",
            "--no-multi", "--height=90%", "--reverse"]
    p = subprocess.run(args, input="\n".join(hits), text=True,
                       stdout=subprocess.PIPE)
    if p.returncode != 0 or not p.stdout.strip():
        return die("cancelled")
    url = p.stdout.splitlines()[0].split("\t")[3]
    if not url:
        return die("no source URL in selection")
    note(f"fetching full-res from source via gallery-dl → {url}")
    if backends.gallery([url], IMG_DIR) != 0:
        note("gallery-dl couldn't fetch it — opening source in browser")
        _open(url)
    return 0


# --- artwork search ---------------------------------------------------------

def flow_search(args_list, as_json=False):
    first = args_list[0]
    page_url = None
    if first.startswith(("http://", "https://")):
        query = routing.query_from_url(first)
        if not query:
            return die('couldn\'t read an artwork name from that page — try: '
                       'grab -s "<name>"')
        page_url = first
        note(f"art page → museum search: {query}")
    else:
        query = " ".join(args_list)
    if as_json:
        print(json.dumps(engine.search_art(query)))
        return 0
    return _art_search_interactive(query, page_url)


def _art_search_interactive(query, page_url=None):
    ART_DIR.mkdir(parents=True, exist_ok=True)
    with Spinner(f"searching museums for “{query}”"):
        cands = rank.rank(query, sources.gather(query))
    if not cands:
        return die(f"no scans found for: {query}")
    note(f"{len(cands)} candidate(s) found — most relevant first (preview shows "
         "the image)")
    cand = picker.pick_art(cands)
    if cand is None:
        return die("cancelled")
    if not cand.desc and page_url:
        cand.desc = describe.page_description(page_url)
    out = _download_candidate(cand)
    res = metadata.image_res(out) or cand.res
    caption, body = metadata.captions(cand, res)
    if metadata.embed(out, cand, caption):
        note("metadata embedded in image (EXIF/XMP)")
    else:
        metadata.write_sidecar(out, cand, res)
        note(f"metadata → {out}.txt (install exiv2/exiftool to embed it instead)")
    notify.send(str(out), caption, body)
    note("notified + copied to clipboard")
    return 0


def _download_candidate(cand) -> Path:
    slug = metadata.build_slug(cand)
    if cand.spec.startswith("url:"):
        url = cand.spec[4:]
        out = engine.unique_path(ART_DIR / f"{slug}.{engine.ext_of(url) or 'jpg'}")
        note(f"downloading → {out}")
        try:
            engine.download_file(url, out)
        except Exception as e:
            die(f"download failed: {e}")
        metadata.cap_image(out)
    elif cand.spec.startswith("iiif:"):
        out = engine.unique_path(ART_DIR / f"{slug}.jpg")
        note(f"stitching IIIF tiles → {out}")
        if backends.dezoomify(cand.spec[5:], out) != 0:
            die("dezoomify-rs failed")
    else:
        die(f"unknown candidate spec: {cand.spec}")
    note(f"saved → {out} ({engine.human(out.stat().st_size)})")
    return out


# --- helpers ---------------------------------------------------------------

def _resolve_image(input_url):
    if re.search(r"\.(jpe?g|png|webp|gif|tiff?|bmp|avif)([?#]|$)", input_url, re.I):
        return input_url
    note("resolving main image from page…")
    try:
        r = httpx.get(input_url, headers={"User-Agent": UA}, follow_redirects=True,
                      timeout=15.0)
        from selectolax.parser import HTMLParser
        og = HTMLParser(r.text).css_first('meta[property="og:image"]')
        if og and og.attributes.get("content"):
            return og.attributes["content"]
    except Exception:
        pass
    return input_url


def _notify_newest(root: Path, since: float, label: str):
    exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    newest, newest_mt, count = None, 0.0, 0
    for p in root.rglob("*"):
        try:
            if p.suffix.lower() in exts and p.stat().st_mtime >= since:
                count += 1
                if p.stat().st_mtime > newest_mt:
                    newest, newest_mt = p, p.stat().st_mtime
        except OSError:
            continue
    if newest:
        notify.send(str(newest),
                    f"Saved {count} image{'s' if count != 1 else ''}",
                    f"{newest.name}\n{label}")


def _open(url):
    import shutil
    import subprocess
    cmds = ["open"] if sys.platform == "darwin" else ["helium", "xdg-open"]
    for cmd in cmds:
        if shutil.which(cmd):
            subprocess.Popen([cmd, url], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return


def flow_auto_image(page: str) -> int:
    """Auto mode for a single non-video, non-art URL.

    Enumerates images first (gallery-dl --get-urls or static scan):
      - exactly 1  → download directly via httpx
      - >1         → open fzf picker, download chosen subset via httpx
      - 0          → fall back to full gallery-dl download (current -i behaviour)

    Note: the picker path downloads via httpx (engine.fetch_images), which may
    miss site auth/cookies that gallery-dl handles on a full -i run.
    """
    with Spinner("enumerating images"):
        cands = engine.enumerate_images(page)

    if not cands:
        # No images found via either strategy — fall back to full gallery-dl.
        note("no images enumerated — falling back to gallery-dl full download")
        return flow_image([page])

    if len(cands) == 1:
        note("1 image found — downloading directly")
        return _save_and_notify(
            engine.fetch_images([cands[0]["url"]], referer=page))

    note(f"{len(cands)} image(s) found — opening picker")
    picks = picker.pick_page(
        [(c["dim"], c["url"], c["name"]) for c in cands])
    if not picks:
        return 0   # user cancelled — not an error
    return _save_and_notify(
        engine.fetch_images([u for u, _n in picks], referer=page))


def flow_auto(urls):
    rc = 0
    for url in urls:
        if url.startswith("-"):
            continue
        if routing.is_art_url(url):
            rc |= flow_art([url])
        elif routing.is_reference_page(url):
            rc |= flow_search([url])
        elif routing.has_video(url):
            rc |= flow_video([url])
        else:
            rc |= flow_auto_image(url)
    return rc


def _clipboard_url() -> str | None:
    """Try to read a URL from the system clipboard. Returns None on any failure."""
    import shutil
    cmd = "pbpaste" if sys.platform == "darwin" else "wl-paste"
    if not shutil.which(cmd):
        return None
    try:
        import subprocess as _sp
        result = _sp.run([cmd], capture_output=True, text=True, timeout=3)
        text = result.stdout.strip()
        if text.startswith(("http://", "https://")):
            return text
    except Exception:
        pass
    return None


def flow_interactive() -> int:
    """Interactive mode: prompt for a URL then route like auto."""
    clip = _clipboard_url()
    if clip:
        prompt = f"URL [{clip}]: "
    else:
        prompt = "URL: "
    try:
        raw = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return 130
    url = raw or clip
    if not url:
        return die("no URL provided")
    if not url.startswith(("http://", "https://")):
        return die(f"not a valid URL: {url}")
    return flow_auto([url])


def main(argv=None):
    raw = sys.argv[1:] if argv is None else list(argv)

    # Native-messaging host mode: the browser launches us via the installed
    # launcher (harpe --native-host …). Intercept BEFORE argparse — the browser
    # appends its own args (the extension origin / manifest path) that argparse
    # would reject. This must produce no stdout except framed messages.
    if "--native-host" in raw:
        from . import nativehost
        return nativehost.run()

    # Host registration commands (no argparse: simple verbs).
    if raw and raw[0] in ("install-host", "uninstall-host"):
        from . import installhost
        if raw[0] == "uninstall-host":
            removed = installhost.uninstall()
            note(f"removed native host from {len(removed)} location(s)")
            return 0
        rest, chrome_ids, firefox_ids, all_b = raw[1:], [], [], False
        i = 0
        while i < len(rest):
            if rest[i] == "--chrome-id" and i + 1 < len(rest):
                chrome_ids.append(rest[i + 1]); i += 2
            elif rest[i] == "--firefox-id" and i + 1 < len(rest):
                firefox_ids.append(rest[i + 1]); i += 2
            elif rest[i] == "--all":
                all_b = True; i += 1
            else:
                i += 1
        written = installhost.install(chrome_ids, firefox_ids, all_b)
        note(f"registered native host in {len(written)} location(s)")
        return 0

    # First run: register the host so the extension's engine "just works". Only on
    # interactive (tty) use — never as a surprise side effect of scripted/--json/
    # piped calls or CI. Explicit `harpe install-host` covers the headless case.
    try:
        if sys.stdin.isatty() and sys.stdout.isatty():
            from . import installhost
            installhost.auto_register_once()
    except Exception:
        pass

    # prog left to argparse default (argv0 basename) so help shows `harpe` or
    # `grab` depending on which command was invoked.
    p = argparse.ArgumentParser(add_help=True, description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group()
    g.add_argument("-v", "--video", action="store_const", dest="mode", const="video")
    g.add_argument("-A", "--audio", action="store_const", dest="mode", const="audio")
    g.add_argument("-i", "--image", action="store_const", dest="mode", const="image",
                   help="download whole gallery via gallery-dl (no picking)")
    g.add_argument("-p", "--page", action="store_const", dest="mode", const="page",
                   help="scan static HTML, pick which images to grab (fzf multi-select)")
    g.add_argument("-a", "--art", action="store_const", dest="mode", const="art")
    g.add_argument("-r", "--reverse", action="store_const", dest="mode", const="reverse")
    g.add_argument("-s", "--search", action="store_const", dest="mode", const="search")
    g.add_argument("-F", "--fetch", action="store_const", dest="mode", const="fetch")
    p.add_argument("--json", action="store_true",
                   help="emit candidates/results as JSON instead of launching the fzf UI")
    p.add_argument("--referer", help="Referer header for --fetch downloads")
    p.add_argument("--dest", help="destination dir for --fetch downloads")
    p.add_argument("args", nargs="*", metavar="url|query")
    p.set_defaults(mode="auto")
    ns = p.parse_args(argv)

    mode, a = ns.mode, ns.args

    # No-args → interactive mode (prompt for URL, then route like auto).
    if not a and mode == "auto":
        try:
            return flow_interactive()
        except KeyboardInterrupt:
            return 130

    if not a:
        p.error("at least one URL/query is required")

    try:
        if mode == "video":
            return flow_video(a)
        if mode == "audio":
            return flow_audio(a)
        if mode == "image":
            return flow_image(a)
        if mode == "page":
            return flow_page(a[0], as_json=ns.json)
        if mode == "art":
            return flow_art(a)
        if mode == "reverse":
            return flow_reverse(a[0])
        if mode == "search":
            return flow_search(a, as_json=ns.json)
        if mode == "fetch":
            return flow_fetch(a, as_json=ns.json, referer=ns.referer, dest=ns.dest)
        return flow_auto(a)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main() or 0)
