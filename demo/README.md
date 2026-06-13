# Demos

Terminal demos are scripted with [VHS](https://github.com/charmbracelet/vhs) so they're
reproducible and re-renderable (no manual screen-recording, version-controlled, can run in CI).

## Render

```bash
# Arch: paru -S vhs ttyd        (ffmpeg + go already in extra)
# else: go install github.com/charmbracelet/vhs@latest  +  install ttyd + ffmpeg
vhs demo/picker.tape            # → demo/harpe-picker.gif
```

Then reference the GIF from the top of the main README, e.g.:

```md
![Harpe picking images from a page](demo/harpe-picker.gif)
```

## Notes

- `picker.tape` runs the real `harpe -p` against a fast static page (books.toscrape.com),
  opens the fzf picker, multi-selects with `Tab`, and downloads with `Enter`.
- In VHS's terminal the fzf image preview falls back to ANSI blocks (no Kitty graphics) —
  that still reads well in a GIF; in a real Kitty/Ghostty terminal you get inline images.
- For the **web tool** (the landing page's "paste a URL" + museum search), a screen-capture
  MP4 (e.g. Screen Studio, auto-zoom) embedded as a muted autoplay hero converts best —
  GitHub also hosts MP4s dropped into a README.
