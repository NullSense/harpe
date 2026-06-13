"""Best-effort artwork description from an arbitrary page, via trafilatura.

trafilatura is a main-content / boilerplate-removal extractor — exactly right for
pulling a clean prose description of an artwork page (and exactly wrong for
enumerating gallery images, which is extract.py's job with selectolax).
"""


def page_description(url: str, max_chars: int = 600) -> str:
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return ""
        text = trafilatura.extract(downloaded, include_comments=False,
                                   include_images=False, favor_precision=True) or ""
    except Exception:
        return ""
    text = " ".join(text.split())
    return text[:max_chars]
