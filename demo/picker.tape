# Harpe — page-picker demo (VHS tape).
#
# Render:  vhs demo/picker.tape      → demo/harpe-picker.gif
# Needs:   vhs + ttyd + ffmpeg on PATH, and `harpe` installed (uv tool install).
#   Arch:  paru -S vhs ttyd   (ffmpeg + go are in extra)
#
# Shows: `harpe -p <url>` scanning a page, then the fzf picker — Tab to multi-select
# by real resolution, Enter to download the chosen images.
#
# NOTE: VHS's terminal can't do Kitty/Ghostty inline-image graphics, so the fzf
# preview pane shows the ramp/text only (no thumbnails) in the GIF. For a clip WITH
# real image previews, screen-record an actual Ghostty session instead.
# Run from the repo root so the Output path lands in demo/:
#   cd ~/Programming/harpe && vhs demo/picker.tape

Output demo/harpe-picker.gif

Set Shell "bash"
Set FontSize 18
Set Width 1240
Set Height 720
Set Padding 24
Set Theme "Aardvark Blue"
Set TypingSpeed 55ms
Set PlaybackSpeed 1.0

# Warm the uv-backed shim off-camera so the demo doesn't capture cold-start.
Hide
Type "harpe --help >/dev/null 2>&1"
Enter
Sleep 4s
Type "clear"
Enter
Show

# The command — Perseus (on-brand: the harpe-wielder), a content-rich static page
Type "harpe -p https://en.wikipedia.org/wiki/Perseus"
Sleep 600ms
Enter

# Scan + dimension probe, then fzf opens (Wikimedia probes can take a moment)
Sleep 6000ms

# Move through results and multi-select with Tab (biggest first)
Down@450ms 1
Tab
Down@450ms 1
Tab
Down@450ms 1
Tab
Sleep 900ms

# Download the selected images
Enter
Sleep 3500ms
