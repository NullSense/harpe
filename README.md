<div align="center">

# Harpe

**A hooked blade for the web — enter, catch, retrieve.**

Pull video, image galleries, a whole page of images, or gigapixel museum artwork —
with one command. The fzf picker is one frontend; the engine is UI-agnostic.

</div>

## Install

```bash
uv tool install git+https://github.com/NullSense/harpe
```

Needs [`yt-dlp`](https://github.com/yt-dlp/yt-dlp), [`gallery-dl`](https://github.com/mikf/gallery-dl),
[`dezoomify-rs`](https://github.com/lovasoa/dezoomify-rs), `fzf`, and (for previews) `chafa`
on your `PATH`.

## Use

```bash
harpe                  # interactive: prompts for a URL (pre-fills from clipboard)
harpe <url>            # auto-detect: video · art · museum page · images with picker
harpe -p <url>         # page picker: static-HTML scan, pick which images to grab
harpe -i <url>         # download whole gallery via gallery-dl (no picking)
harpe -s <query|url>   # search the same artwork across museums, grab the best scan
harpe -r <url|image>   # reverse-image: find the source + highest-res copy
harpe -v / -A / -a     # force video / audio / zoomable-art
```

`harpe <url>` routes for you: Google Arts & Culture / IIIF → tile-stitched; a museum or
encyclopedia artwork page → federated museum search (finds the same work as a CC0 original
elsewhere, far higher-res than the page thumbnail); a video URL → yt-dlp; anything else →
enumerate images first and **let you pick** when more than one is found.

Running `harpe` with no arguments enters **interactive mode**: it pre-fills the URL
from your clipboard (if one is there), lets you accept or type a new one, then routes
exactly like `harpe <url>`.

### Picking from a page

**Auto mode** (`harpe <url>`) enumerates images via `gallery-dl --get-urls` (fast,
handles auth) or a static-HTML scan, then:

- **1 image** → downloads it directly.
- **>1 images** → opens the fzf picker so you choose what to grab.
- **0 images** → falls back to a full `gallery-dl` download.

Use `-i` when you want everything without the picker.

`harpe -p` always opens the static-HTML picker regardless of image count:

```
🖼  biggest first · Tab to select · Ctrl-A all
4000×3000  the-deluge.jpg            ▒▒▒ preview ▒▒▒
1600×1200  detail-crop.jpg
 800× 600  thumbnail.jpg
```

`Tab` toggles selection, `Ctrl-A` selects all, `Enter` downloads the chosen images
(with the right Referer/UA and de-duped names). Static-HTML pages only — JS-rendered /
lazy-loaded images need the rendered-DOM frontend (roadmap).

> Render a live terminal GIF of this flow: `vhs demo/picker.tape` (see [`demo/`](demo/)).

## Frontends

fzf is just the bundled UI. The engine (`harpe.engine`) is plain JSON-in/JSON-out, so a
browser extension, a desktop GUI, or a service can drive the same core:

```bash
harpe -p <url> --json        # → [{url, name, dim, width, height}, …]
harpe -s <query|url> --json  # → ranked museum candidates
harpe -F <url>... --json     # download a chosen subset (reads stdin with `-F -`)
```

The engine owns extraction, UA/Referer, naming, dedupe, the 8K resolution cap, and
lossless EXIF/XMP metadata; a frontend only chooses what to grab.

### Harder sites (logged-in, TikTok, bot-walls)

Video downloads are always retried/segment-parallelised. Two opt-in env vars
unlock the rest (off by default so a plain install never breaks):

- `HARPE_COOKIES_FROM_BROWSER=firefox` — download **logged-in** content (Instagram,
  YouTube, private posts) using your own browser session. This is the CLI's edge
  over any server: it runs locally with your cookies and residential IP.
- `HARPE_IMPERSONATE=chrome` — TLS/HTTP impersonation that fixes TikTok and some
  bot-walls (install `yt-dlp[curl-cffi]` for impersonation targets).

## Sources

Keyless: Wikimedia Commons, Art Institute of Chicago, Cleveland Museum, The Met,
Victoria & Albert, Wikidata IIIF. Optional keys (read from env — inject them yourself,
e.g. `infisical run -- harpe …`): `FIRECRAWL_API_KEY`, `HARVARD_API_KEY`,
`SMITHSONIAN_API_KEY`, `EUROPEANA_API_KEY`, `SAUCENAO_API_KEY`.

## Develop

```bash
uv run pytest        # unit tests (routing, extraction, ranking, metadata, engine)
uv run harpe --help
```

Dependencies are locked with a 7-day `exclude-newer` supply-chain cutoff (`[tool.uv]`).

## Name

In Greek myth the *harpe* is the sickle-sword of Cronus and Perseus — a curved blade that
hooks in and cuts clean. Fitting, for a tool that reaches into a page and pulls one thing
out at full quality.

MIT © NullSense
