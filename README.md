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
harpe <url>            # auto-detect: video · gallery · zoomable art · museum page
harpe -p <url>         # scan a page, pick which images to grab (fzf, multi-select)
harpe -s <query|url>   # search the same artwork across museums, grab the best scan
harpe -r <url|image>   # reverse-image: find the source + highest-res copy
harpe -v / -A / -i / -a   # force video / audio / gallery / zoomable-art
```

`harpe <url>` routes for you: Google Arts & Culture / IIIF → tile-stitched; a museum or
encyclopedia artwork page → federated museum search (finds the same work as a CC0 original
elsewhere, far higher-res than the page thumbnail); a video URL → yt-dlp; anything else →
gallery-dl, falling back to the **page picker** when no extractor exists.

### Picking from a page

`harpe -p` reads a page, ranks every image by real pixel size, and opens an fzf grid with
live previews:

```
🖼  biggest first · Tab/Space to pick · Ctrl-A all
4000×3000  the-deluge.jpg            ▒▒▒ preview ▒▒▒
1600×1200  detail-crop.jpg
 800× 600  thumbnail.jpg
```

`Tab`/`Space` toggle images, `Ctrl-A` selects all, `Enter` downloads the lot (with the
right Referer/UA and de-duped names). Static-HTML pages only for now — JS-rendered /
lazy-loaded images need the rendered-DOM frontend (roadmap).

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

## Sources

Keyless: Wikimedia Commons, Art Institute of Chicago, Cleveland Museum, The Met,
Victoria & Albert, Wikidata IIIF. Optional keys (read from env — inject them yourself,
e.g. `infisical run -- harpe …`): `FIRECRAWL_API_KEY`, `HARVARD_API_KEY`,
`SMITHSONIAN_API_KEY`, `EUROPEANA_API_KEY`, `SAUCENAO_API_KEY`.

## Develop

```bash
uv run pytest        # 59 unit tests (routing, extraction, ranking, metadata)
uv run harpe --help
```

Dependencies are locked with a 7-day `exclude-newer` supply-chain cutoff (`[tool.uv]`).

## Name

In Greek myth the *harpe* is the sickle-sword of Cronus and Perseus — a curved blade that
hooks in and cuts clean. Fitting, for a tool that reaches into a page and pulls one thing
out at full quality.

MIT © NullSense
