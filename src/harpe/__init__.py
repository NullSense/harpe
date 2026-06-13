"""Harpe — a hooked blade for the web.

Like the mythic sickle-sword (Cronus, Perseus), Harpe enters a page, hooks what
you want, and retrieves it: video, image galleries, a page full of images, or
high-resolution artwork from museum collections.

The download backends (yt-dlp, gallery-dl, dezoomify-rs) are invoked as
subprocesses; the orchestration, federated museum search, ranking, page-image
extraction, and metadata handling are Python. The fzf TUI is just one frontend —
the engine (harpe.engine) is frontend-agnostic (see README). The `grab` command
is kept as an alias.
"""
__version__ = "0.1.0"
