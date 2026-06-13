"""fzf pickers. The image preview is the kept bash helper ~/bin/grab-thumb."""
import shutil
import subprocess

from .config import GRAB_THUMB
from .models import Candidate


def _clean(s) -> str:
    return str(s or "").replace("\t", " ").replace("\n", " ").replace("\r", " ")


def _fzf(lines, with_nth, preview, header, multi):
    if not shutil.which("fzf"):
        raise SystemExit("grab: fzf not found")
    args = ["fzf", "--delimiter=\t", f"--with-nth={with_nth}",
            f"--preview={preview}", "--preview-window=right,48%,border-left",
            f"--header={header}", "--height=90%", "--reverse"]
    if multi:
        # Tab/Space toggle (fzf default); Ctrl-A select all, Ctrl-T invert.
        args += ["--multi", "--bind=ctrl-a:select-all,ctrl-t:toggle-all"]
    else:
        args += ["--no-multi"]
    p = subprocess.run(args, input="\n".join(lines), text=True,
                       stdout=subprocess.PIPE)
    if p.returncode != 0:
        return []
    return [ln for ln in p.stdout.splitlines() if ln.strip()]


def pick_art(cands: list[Candidate]) -> Candidate | None:
    """Single-select. Returns the chosen Candidate or None if cancelled."""
    lines = []
    for i, c in enumerate(cands):
        lines.append("\t".join(_clean(x) for x in [
            i, c.res, c.source, c.title, c.artist, c.date, c.spec, c.thumb,
            c.medium, c.desc, c.physdim]))
    preview = (f"{GRAB_THUMB} {{8}} {{2}} · {{3}} · {{4}} {{5}} {{6}} · {{9}}")
    sel = _fzf(lines, with_nth="2,3,4,5,6", preview=preview,
               header="🎨  most relevant first · resolution at left, full preview →",
               multi=False)
    if not sel:
        return None
    return cands[int(sel[0].split("\t")[0])]


def pick_page(rows: list[tuple[str, str, str]]) -> list[tuple[str, str]]:
    """Multi-select. Returns [(url, display_name), ...] for the chosen images."""
    lines = ["\t".join(_clean(x) for x in row) for row in rows]
    preview = f"{GRAB_THUMB} {{2}} {{1}} · {{3}}"
    sel = _fzf(lines, with_nth="1,3", preview=preview,
               header="🖼  biggest first · Tab to select · Ctrl-A all",
               multi=True)
    out = []
    for ln in sel:
        parts = ln.split("\t")
        if len(parts) >= 2:
            out.append((parts[1], parts[2] if len(parts) > 2 else ""))
    return out
