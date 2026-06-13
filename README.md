# Harpe

**A hooked blade for the web — enter, catch, retrieve.**

One tool for pulling video, image galleries, a whole page of images, or
high-resolution artwork from museum collections. In Greek myth the *harpe* is the
sickle-sword of Cronus and Perseus — a curved blade that hooks in and severs clean.
That's the metaphor: a search that *enters a page, hooks what you want, and pulls it
out at full quality*.

The command is `harpe` (the alias `grab` is kept for muscle memory). The
orchestration, federated museum search, page-image extraction, ranking, and metadata
handling are Python; the download backends (yt-dlp, gallery-dl, dezoomify-rs) and the
preview/notify helpers stay external. The fzf TUI is just one frontend — the engine
is UI-agnostic (see **Frontends**).

## Modes

```
harpe <url>...        auto-detect backend
harpe -v <url>        video       (yt-dlp, true max quality: -S res,fps,tbr)
harpe -A <url>        audio only  (yt-dlp -x, no re-encode)
harpe -i <url>        images      (gallery-dl; falls back to the page picker if unsupported)
harpe -p <url>        page picker (scan a page, multi-select which images to grab)
harpe -a <url>        art/zoomable (dezoomify-rs: IIIF / Zoomify / DeepZoom / GA&C)
harpe -r <url|img>    reverse image: find source + highest-res copy
harpe -s <query|url>  artwork scans across museums (a URL auto-derives the name)
```

Auto-routing: Google Arts&Culture / IIIF → dezoomify; major museum & encyclopedia
single-artwork pages → federated museum search (finds the same work as a CC0 original
elsewhere, far higher-res than the page thumbnail); video URL → yt-dlp; else gallery-dl,
which falls back to the **page picker** when it has no extractor (this is what makes a
"page of many images" downloadable: scan static HTML → rank by real pixel size →
fzf multi-select with image previews).

## Frontends (the engine is UI-agnostic)

fzf is just the *bundled* frontend. The engine (`harpe.engine`) exposes plain
JSON-in/JSON-out primitives so any UI — a browser extension, a macOS/GTK GUI, a
local HTTP service — can drive it without touching fzf:

```
scan_page(url)          -> [{url, name, dim, width, height}, ...]   # candidates
fetch_images(urls, ...) -> [{url, ok, path|error}, ...]            # download subset
search_art(query)       -> [{title, artist, res, spec, thumb, ...}, ...]
```

Exposed on the CLI for non-Python frontends:

```bash
harpe -p <url> --json                         # candidate images on a page (no UI)
harpe -s <query|url> --json                   # ranked museum candidates (no UI)
harpe -F <url>... [--referer R] [--dest D] [--json]   # download a chosen subset
```

A browser extension flow: either `harpe -p <url> --json` for engine-side scanning,
**or** scan the rendered DOM yourself (better for JS pages — see below) and POST the
chosen URLs to `harpe -F - --json` (reads newline URLs from stdin). The engine handles
UA, Referer, naming, dedupe; the frontend owns presentation + notifications.

## Architecture

| Layer | Lives in |
|-------|----------|
| CLI dispatch / flows | `harpe.cli` |
| URL classification + query-from-page | `harpe.routing` |
| Page-image extraction (selectolax + ranged dim-probe) | `harpe.extract` |
| Federated museum sources (async fan-out) | `harpe.sources` |
| Relevance+resolution ranking & dedup | `harpe.rank` |
| Reverse-image search (PicImageSearch) | `harpe.reverse` |
| Filename slug, captions, EXIF/XMP embed, resolution cap | `harpe.metadata` |
| trafilatura description extraction | `harpe.describe` |
| fzf pickers | `harpe.picker` |
| Backend subprocess wrappers | `harpe.backends` |

External, intentionally not reimplemented: **yt-dlp**, **gallery-dl**, **dezoomify-rs**
(backends); `~/bin/grab-thumb` (fzf image preview, perf-critical) and
`~/bin/grab-notify` (notification + clipboard).

## Secrets (12-factor)

The tool only *reads* env vars; the caller injects them. Keyless sources always run.
Keyed (optional): `FIRECRAWL_API_KEY`, `HARVARD_API_KEY`, `SMITHSONIAN_API_KEY`,
`EUROPEANA_API_KEY`, `SAUCENAO_API_KEY`. From the SUPER+ALT+G menu these come via
`infisical run`; for direct CLI use: `infisical run -- harpe -s "<query>"`.

## Tunables

`GRAB_ART_MAXPX` (default 7680; 0 = full res) · `GRAB_PAGE_MINPX` (100) ·
`GRAB_PAGE_MAX` (200).

## Platforms

The engine + CLI are cross-platform (Linux, macOS). What's OS-specific:

| Piece | Linux | macOS |
|-------|-------|-------|
| Notifications + clipboard | `~/bin/grab-notify` (or notify-send/wl-copy) | osascript / pbcopy (`harpe.notify` built-in) |
| Open in browser | helium / xdg-open | `open` |
| Preview helper (`bin/grab-thumb`) | curl + file + chafa | same (chafa auto-detects iTerm2/kitty/sixel) |
| SUPER+ALT+G menu (`grab-menu`) | Hyprland/Walker only | — use the CLI, or wire Raycast/Alfred to `grab` |

**macOS setup:**
```bash
brew install fzf chafa imagemagick exiv2 yt-dlp gallery-dl   # tools
brew install dezoomify-rs   # or: cargo install dezoomify-rs
brew install uv
uv tool install --editable .   # installs both `harpe` and `grab` on PATH
```
Everything else (the Python engine, page picker, museum search, formats) is identical.
The Hyprland keybind/menu is the only Linux-only frontend; on macOS drive `grab` from
the terminal or a launcher — the frontend-agnostic engine (above) is exactly the seam
for a native macOS GUI later.

## Dev

```
uv run pytest        # unit tests (pure logic: routing, extract, rank, metadata)
uv run harpe --help
```

Dependencies are resolver-pinned with a 7-day `exclude-newer` supply-chain cutoff
(see `[tool.uv]` in `pyproject.toml`) — bump it deliberately when updating deps.
