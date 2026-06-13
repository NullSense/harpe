"""Multi-engine keyless reverse-image search (PicImageSearch).

Returns TSV rows "engine\tsimilarity\ttitle\tsource_url\tthumb", ranked with
original-source domains first (our proxy for "highest-resolution copy", since
reverse engines don't report pixel dimensions). SauceNAO is included only when a
registered key exists at ~/.config/grab/saucenao.key or $SAUCENAO_API_KEY.
"""
import asyncio
import os
import pathlib

# Domains that host the ORIGINAL (usually highest-resolution) of a work.
ORIGINAL_SOURCES = (
    "pixiv.net", "danbooru.donmai.us", "gelbooru.com", "yande.re", "konachan",
    "deviantart.com", "artstation.com", "behance.net", "tumblr.com",
    "twitter.com", "x.com", "flickr.com", "artsy.net", "wikiart.org",
    "wikimedia.org", "wikipedia.org", "metmuseum.org", "artic.edu",
    "clevelandart.org", "rijksmuseum.nl", ".museum",
)


def _saucenao_key():
    p = pathlib.Path.home() / ".config/grab/saucenao.key"
    if p.is_file() and p.read_text().strip():
        return p.read_text().strip()
    return os.environ.get("SAUCENAO_API_KEY") or None


async def _run(url):
    from PicImageSearch import Ascii2D, Iqdb, Network, SauceNAO, Yandex
    rows = []  # (priority, rank, -sim, engine, sim_str, title, link, thumb)

    def add(engine, rank, sim, title, link, thumb=""):
        if not link:
            return
        link = link.strip()
        host = link.split("/")[2].lower() if "://" in link else ""
        priority = 0 if any(s in host for s in ORIGINAL_SOURCES) else 1
        title = (title or "").replace("\t", " ").replace("\n", " ").strip()
        thumb = (thumb or "").replace("\t", " ").replace("\n", " ").strip()
        try:
            simnum = float(sim)
            s = f"{simnum:.0f}%"
        except (TypeError, ValueError):
            simnum, s = -1.0, "~"
        rows.append((priority, rank, -simnum, engine, s, title[:70], link, thumb))

    async with Network() as client:
        key = _saucenao_key()

        async def saucenao():
            if not key:
                return
            r = await SauceNAO(client=client, api_key=key).search(url=url)
            for i, x in enumerate(r.raw[:8]):
                add("SauceNAO", i, getattr(x, "similarity", None),
                    getattr(x, "title", ""), getattr(x, "url", ""),
                    getattr(x, "thumbnail", ""))

        async def ascii2d():
            r = await Ascii2D(client=client).search(url=url)
            for i, x in enumerate(r.raw[:6]):
                add("Ascii2D", i, None,
                    getattr(x, "title", "") or getattr(x, "author", ""),
                    getattr(x, "url", ""), getattr(x, "thumbnail", ""))

        async def iqdb():
            r = await Iqdb(client=client).search(url=url)
            for i, x in enumerate(r.raw[:6]):
                add("IQDB", i, getattr(x, "similarity", None),
                    getattr(x, "content", "") or getattr(x, "source", ""),
                    getattr(x, "url", ""), getattr(x, "thumbnail", ""))

        async def yandex():
            r = await Yandex(client=client).search(url=url)
            for i, x in enumerate((r.raw or [])[:8]):
                add("Yandex", i, None, getattr(x, "title", ""),
                    getattr(x, "url", ""), getattr(x, "thumbnail", ""))

        await asyncio.gather(saucenao(), ascii2d(), iqdb(), yandex(),
                             return_exceptions=True)

    # Dedup by URL (drop tracking query strings), keep the best-ranked copy,
    # then order: original-source first, then engine rank, then similarity.
    best = {}
    for row in rows:
        k = row[6].split("?")[0]
        if k not in best or row[:3] < best[k][:3]:
            best[k] = row
    return ["\t".join((e, s, t, l, th)) for (_p, _r, _s, e, s, t, l, th)
            in sorted(best.values(), key=lambda r: (r[0], r[1], r[2], r[3]))]


def reverse_search(url: str) -> list[str]:
    try:
        return asyncio.run(_run(url))
    except Exception:
        return []
