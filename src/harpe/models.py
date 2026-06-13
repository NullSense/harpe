"""Shared data types."""
from dataclasses import dataclass


@dataclass
class Candidate:
    """One image candidate for an artwork, from any federated source.

    `spec` carries how to fetch it: "url:<direct-image>" or "iiif:<manifest>".
    `area` is the pixel area used as the resolution sort key (sources without
    real dimensions use a large sentinel so they still rank as high-res).
    """
    area: int = 0
    res: str = "?"
    source: str = ""
    title: str = ""
    artist: str = ""
    date: str = ""
    spec: str = ""
    thumb: str = ""
    medium: str = ""
    desc: str = ""
    physdim: str = ""

    @property
    def source_url(self) -> str:
        for p in ("url:", "iiif:"):
            if self.spec.startswith(p):
                return self.spec[len(p):]
        return self.spec
