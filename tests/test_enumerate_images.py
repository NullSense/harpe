"""Tests for engine.enumerate_images.

All subprocess calls are mocked so these tests have no network or tool deps.
"""
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from harpe import engine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_proc(returncode: int, stdout: str) -> MagicMock:
    m = MagicMock(spec=subprocess.CompletedProcess)
    m.returncode = returncode
    m.stdout = stdout
    return m


MEDIA_URLS = [
    "https://example.com/images/photo1.jpg",
    "https://example.com/images/photo2.png",
    "https://cdn.example.com/gallery/img.webp",
]

NON_MEDIA_LINES = [
    "https://example.com/",
    "not-a-url",
    "",
    "# gallery-dl output header",
]


# ---------------------------------------------------------------------------
# gallery-dl --get-urls happy path
# ---------------------------------------------------------------------------

def test_enumerate_images_parses_gallery_dl_urls():
    stdout = "\n".join(NON_MEDIA_LINES + MEDIA_URLS)
    proc = _make_proc(0, stdout)
    with patch("subprocess.run", return_value=proc) as mock_run:
        result = engine.enumerate_images("https://example.com/gallery")

    mock_run.assert_called_once_with(
        ["gallery-dl", "--get-urls", "https://example.com/gallery"],
        capture_output=True,
        text=True,
    )
    assert len(result) == 3
    assert result[0]["url"] == MEDIA_URLS[0]
    assert result[1]["url"] == MEDIA_URLS[1]
    assert result[2]["url"] == MEDIA_URLS[2]
    # Dims must be unknown for gallery-dl URLs
    for r in result:
        assert r["dim"] == "?"
        assert r["width"] is None
        assert r["height"] is None


def test_enumerate_images_names_from_path():
    proc = _make_proc(0, "https://cdn.example.com/images/sunset.jpg\n")
    with patch("subprocess.run", return_value=proc):
        result = engine.enumerate_images("https://example.com/page")
    assert result[0]["name"] == "sunset.jpg"


def test_enumerate_images_case_insensitive_ext():
    proc = _make_proc(0, "https://x.com/photo.JPEG\nhttps://x.com/pic.PNG\n")
    with patch("subprocess.run", return_value=proc):
        result = engine.enumerate_images("https://x.com/g")
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Fallback: gallery-dl exits 64 (unsupported URL)
# ---------------------------------------------------------------------------

def test_enumerate_images_falls_back_on_exit_64():
    proc = _make_proc(64, "")
    scan_result = [
        {"url": "https://x.com/a.jpg", "name": "a.jpg", "dim": "800x600",
         "width": 800, "height": 600}
    ]
    with patch("subprocess.run", return_value=proc):
        with patch.object(engine, "scan_page", return_value=scan_result) as mock_scan:
            result = engine.enumerate_images("https://x.com/page")
    mock_scan.assert_called_once_with("https://x.com/page")
    assert result == scan_result


# ---------------------------------------------------------------------------
# Fallback: gallery-dl returns no media URLs (but exits 0)
# ---------------------------------------------------------------------------

def test_enumerate_images_falls_back_when_no_media_urls():
    proc = _make_proc(0, "# some non-url output\nhttps://x.com/\n")
    scan_result = [
        {"url": "https://x.com/img.gif", "name": "img.gif", "dim": "?",
         "width": None, "height": None}
    ]
    with patch("subprocess.run", return_value=proc):
        with patch.object(engine, "scan_page", return_value=scan_result) as mock_scan:
            result = engine.enumerate_images("https://x.com/page")
    mock_scan.assert_called_once_with("https://x.com/page")
    assert result == scan_result


# ---------------------------------------------------------------------------
# Fallback: gallery-dl not installed (FileNotFoundError)
# ---------------------------------------------------------------------------

def test_enumerate_images_falls_back_when_gallery_dl_missing():
    scan_result = [
        {"url": "https://x.com/img.jpg", "name": "img.jpg", "dim": "1200x900",
         "width": 1200, "height": 900}
    ]
    with patch("subprocess.run", side_effect=FileNotFoundError):
        with patch.object(engine, "scan_page", return_value=scan_result) as mock_scan:
            result = engine.enumerate_images("https://x.com/page")
    mock_scan.assert_called_once_with("https://x.com/page")
    assert result == scan_result


# ---------------------------------------------------------------------------
# gallery-dl returns non-zero (but not 64) with empty media output → fallback
# ---------------------------------------------------------------------------

def test_enumerate_images_nonzero_non64_empty_falls_back():
    proc = _make_proc(1, "error: something failed\n")
    scan_result = []
    with patch("subprocess.run", return_value=proc):
        with patch.object(engine, "scan_page", return_value=scan_result) as mock_scan:
            result = engine.enumerate_images("https://x.com/page")
    mock_scan.assert_called_once()
    assert result == []


# ---------------------------------------------------------------------------
# gallery-dl returns non-zero (but not 64) WITH media URLs → use them
# ---------------------------------------------------------------------------

def test_enumerate_images_nonzero_non64_with_urls_uses_them():
    # Some extractors return exit 1 but still print URLs; we trust the URLs.
    stdout = "https://example.com/photo.avif\nhttps://example.com/photo2.tiff\n"
    proc = _make_proc(1, stdout)
    with patch("subprocess.run", return_value=proc):
        with patch.object(engine, "scan_page") as mock_scan:
            result = engine.enumerate_images("https://example.com/g")
    mock_scan.assert_not_called()
    assert len(result) == 2
    assert result[0]["url"] == "https://example.com/photo.avif"
