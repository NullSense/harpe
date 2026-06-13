"""Federated artwork search across museum / aggregator APIs (parallel, async).

Keyless sources always run; keyed ones (Harvard/Smithsonian/Europeana/Firecrawl)
light up only when their env var is set (12-factor: caller injects via
`infisical run`). Each returns a list[Candidate]; a failing source never blocks
the rest.
"""
import asyncio
import os
import re

import httpx

from .config import API_UA, UA, firecrawl_key
from .models import Candidate

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WD_API = "https://www.wikidata.org/w/api.php"
WD_SPARQL = "https://query.wikidata.org/sparql"


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", "", s or "")).strip()


def _toint(v) -> int:
    try:
        return int(re.sub(r"\D", "", str(v)) or 0)
    except (TypeError, ValueError):
        return 0


async def _commons(client, q):
    r = await client.get(COMMONS_API, params={
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": q, "gsrnamespace": 6, "gsrlimit": 15,
        "prop": "imageinfo", "iiprop": "url|size|mime", "iiurlwidth": 400})
    out = []
    pages = (r.json().get("query", {}) or {}).get("pages", {}) or {}
    for page in pages.values():
        ii = (page.get("imageinfo") or [{}])[0]
        if not re.match(r"image/(jpeg|png|tiff|webp)", ii.get("mime", "")):
            continue
        w, h = ii.get("width", 0), ii.get("height", 0)
        title = re.sub(r"\.[A-Za-z]+$", "",
                       re.sub(r"^File:", "", page.get("title", "")))
        out.append(Candidate(area=w * h, res=f"{w}x{h}", source="Commons",
                             title=title, spec="url:" + ii.get("url", ""),
                             thumb=ii.get("thumburl", "")))
    return out


async def _aic(client, q):
    r = await client.get("https://api.artic.edu/api/v1/artworks/search", params={
        "q": q, "limit": 8,
        "fields": "id,title,artist_title,date_display,medium_display,description,"
                  "dimensions,image_id,is_public_domain,thumbnail"})
    j = r.json()
    iiif = (j.get("config", {}) or {}).get("iiif_url") or "https://www.artic.edu/iiif/2"
    out = []
    for d in j.get("data", []) or []:
        if not (d.get("is_public_domain") and d.get("image_id")):
            continue
        th = d.get("thumbnail") or {}
        w, h = th.get("width") or 0, th.get("height") or 0
        img = d["image_id"]
        out.append(Candidate(
            area=(w or 0) * (h or 0), res=f"{w or '?'}x{h or '?'}", source="AIC",
            title=d.get("title", ""), artist=d.get("artist_title") or "",
            date=d.get("date_display") or "",
            spec=f"url:{iiif}/{img}/full/full/0/default.jpg",
            thumb=f"{iiif}/{img}/full/400,/0/default.jpg",
            medium=d.get("medium_display") or "",
            desc=_strip_html(d.get("description") or "")[:400],
            physdim=(d.get("dimensions") or "").split(";")[0]))
    return out


async def _cleveland(client, q):
    r = await client.get("https://openaccess-api.clevelandart.org/api/artworks/",
                         params={"q": q, "has_image": 1, "cc0": 1, "limit": 8})
    out = []
    for d in r.json().get("data", []) or []:
        imgs = d.get("images") or {}
        im = imgs.get("full") or imgs.get("print") or imgs.get("web")
        if not im:
            continue
        w, h = _toint(im.get("width")), _toint(im.get("height"))
        creators = d.get("creators") or []
        artist = creators[0].get("description", "") if creators else ""
        web = (imgs.get("web") or {}).get("url") or (imgs.get("print") or {}).get("url") or ""
        out.append(Candidate(
            area=w * h, res=f"{im.get('width', '?')}x{im.get('height', '?')}",
            source="Cleveland", title=d.get("title", ""), artist=artist,
            date=d.get("creation_date") or "", spec="url:" + im.get("url", ""),
            thumb=web, medium=d.get("technique") or "",
            desc=_strip_html(d.get("description") or "")[:400],
            physdim=d.get("measurements") or ""))
    return out


async def _met(client, q):
    r = await client.get(
        "https://collectionapi.metmuseum.org/public/collection/v1/search",
        params={"q": q, "hasImages": "true"})
    ids = (r.json().get("objectIDs") or [])[:5]

    async def one(i):
        rr = await client.get(
            f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{i}")
        d = rr.json()
        if not (d.get("isPublicDomain") and d.get("primaryImage")):
            return None
        return Candidate(
            area=30_000_000, res="Met·full", source="Met",
            title=d.get("title", ""), artist=d.get("artistDisplayName") or "",
            date=d.get("objectDate") or "", spec="url:" + d["primaryImage"],
            thumb=d.get("primaryImageSmall") or "", medium=d.get("medium") or "",
            physdim=re.sub(r"\s+", " ", d.get("dimensions") or ""))

    res = await asyncio.gather(*(one(i) for i in ids), return_exceptions=True)
    return [c for c in res if isinstance(c, Candidate)]


async def _vam(client, q):
    r = await client.get("https://api.vam.ac.uk/v2/objects/search",
                         params={"q": q, "images_exist": 1, "page_size": 10},
                         headers={"User-Agent": UA})
    out = []
    for d in r.json().get("records", []) or []:
        pid = d.get("_primaryImageId")
        if not pid:
            continue
        base = f"https://framemark.vam.ac.uk/collections/{pid}"
        out.append(Candidate(
            area=30_000_000, res="V&A·full", source="V&A",
            title=d.get("_primaryTitle") or d.get("_objectType") or "untitled",
            artist=(d.get("_primaryMaker") or {}).get("name", ""),
            date=d.get("_primaryDate") or "",
            spec=f"url:{base}/full/full/0/default.jpg",
            thumb=f"{base}/full/!400,400/0/default.jpg"))
    return out


async def _harvard(client, q):
    key = os.environ.get("HARVARD_API_KEY")
    if not key:
        return []
    r = await client.get("https://api.harvardartmuseums.org/object",
                         params={"apikey": key, "q": q, "hasimage": 1, "size": 10,
                                 "fields": "title,people,primaryimageurl,images,dated"},
                         headers={"User-Agent": UA})
    out = []
    for d in r.json().get("records", []) or []:
        if not d.get("primaryimageurl"):
            continue
        im = (d.get("images") or [{}])[0]
        w, h = im.get("width") or 0, im.get("height") or 0
        people = d.get("people") or []
        artist = next((p.get("name", "") for p in people if p.get("role") == "Artist"),
                      people[0].get("name", "") if people else "")
        out.append(Candidate(
            area=w * h, res=f"{w}x{h}" if w else "Harvard·full", source="Harvard",
            title=d.get("title", ""), artist=artist, date=d.get("dated") or "",
            spec="url:" + d["primaryimageurl"], thumb=d["primaryimageurl"]))
    return out


async def _smithsonian(client, q):
    key = os.environ.get("SMITHSONIAN_API_KEY")
    if not key:
        return []
    r = await client.get("https://api.si.edu/openaccess/api/v1.0/search",
                         params={"api_key": key, "q": q, "rows": 15},
                         headers={"User-Agent": UA})
    out = []
    for d in r.json().get("response", {}).get("rows", []) or []:
        content = d.get("content", {}) or {}
        media = (((content.get("descriptiveNonRepeating") or {})
                  .get("online_media") or {}).get("media") or [{}])[0]
        if not media.get("content"):
            continue
        ft = content.get("freetext", {}) or {}
        out.append(Candidate(
            area=30_000_000, res="SI·full", source="Smithsonian",
            title=d.get("title") or "untitled",
            artist=(ft.get("name") or [{}])[0].get("content", ""),
            date=(ft.get("date") or [{}])[0].get("content", ""),
            spec="url:" + media["content"],
            thumb=media.get("thumbnail") or (media["content"] + "&max=400")))
    return out


async def _europeana(client, q):
    key = os.environ.get("EUROPEANA_API_KEY")
    if not key:
        return []
    r = await client.get("https://api.europeana.eu/record/v2/search.json",
                         params={"wskey": key, "query": q, "rows": 10,
                                 "media": "true", "qf": "TYPE:IMAGE"},
                         headers={"User-Agent": UA})
    out = []
    for it in r.json().get("items", []) or []:
        img = (it.get("edmIsShownBy") or it.get("edmPreview") or [None])[0]
        if not img:
            continue
        out.append(Candidate(
            area=30_000_000, res="EU·web", source="Europeana",
            title=(it.get("title") or ["untitled"])[0],
            artist=(it.get("dcCreator") or [""])[0],
            date=(it.get("year") or [""])[0], spec="url:" + img,
            thumb=(it.get("edmPreview") or [img])[0]))
    return out


async def _wikidata(client, q):
    r = await client.get(WD_API, params={
        "action": "wbsearchentities", "format": "json", "language": "en",
        "limit": 7, "search": q})
    qids = [x["id"] for x in r.json().get("search", []) or []]
    if not qids:
        return []
    values = " ".join(f"wd:{x}" for x in qids)
    query = (f"SELECT ?itemLabel ?manifest WHERE {{ VALUES ?item {{ {values} }} "
             f"?item wdt:P6108 ?manifest. SERVICE wikibase:label "
             f'{{ bd:serviceParam wikibase:language "en". }} }}')
    rr = await client.get(WD_SPARQL, params={"query": query, "format": "json"},
                          headers={"Accept": "application/sparql-results+json"})
    out = []
    for b in rr.json().get("results", {}).get("bindings", []) or []:
        man = b.get("manifest", {}).get("value", "")
        if man.startswith("http"):
            out.append(Candidate(
                area=999_999_999, res="IIIF·max", source="Wikidata",
                title=b.get("itemLabel", {}).get("value", ""), spec="iiif:" + man))
    return out


async def _firecrawl(client, q):
    key = firecrawl_key()
    if not key:
        return []
    r = await client.post("https://api.firecrawl.dev/v2/search",
                          headers={"Authorization": f"Bearer {key}",
                                   "Content-Type": "application/json"},
                          json={"query": f"{q} larger:1200x1200",
                                "sources": ["images"], "limit": 12}, timeout=30.0)
    out = []
    for im in (r.json().get("data", {}) or {}).get("images", []) or []:
        u, w, h = im.get("imageUrl"), im.get("imageWidth") or 0, im.get("imageHeight") or 0
        if not (u and w > 0 and h > 0):
            continue
        out.append(Candidate(area=w * h, res=f"{w}x{h}", source="Web",
                             title=im.get("title") or "web image",
                             spec="url:" + u, thumb=u))
    return out


_SOURCES = [_commons, _aic, _cleveland, _met, _vam, _harvard, _smithsonian,
            _europeana, _wikidata, _firecrawl]


async def _gather_async(q):
    limits = httpx.Limits(max_connections=20)
    async with httpx.AsyncClient(follow_redirects=True,
                                 headers={"User-Agent": API_UA},
                                 timeout=20.0, limits=limits) as client:
        results = await asyncio.gather(*(fn(client, q) for fn in _SOURCES),
                                       return_exceptions=True)
    out = []
    for res in results:
        if isinstance(res, list):
            out.extend(res)
    return out


def gather(q: str) -> list[Candidate]:
    return asyncio.run(_gather_async(q))
