"""The figures a shown passage names, as the page may show them.

The literature was read from scans, and a figure on a scanned page was cropped to a file of its own,
named ``<document>_page_N_figure_M.png``. The stored text of a passage names the crops of its page
(a Markdown image, ``![Figure](figures/<name>)``); ``passage_text.tidy`` drops those references from the
text that is shown, and this module reads them.

A crop is never named to the page by its own name. Its public name is a digest: the first 20 hex
characters of the SHA-256 of the name normalised to NFC. The figures host serves ``<digest>.png``.

A figure is named only when its digest is in the list the backend ships with (``data/figures.tsv``:
digest, width, height and class, one line each, no name) and not in ``FIGURES_REMOVED``. Without
``FIGURES_BASE`` figures are off: nothing is named, and the response is what it was before figures.

Class A is a stamp; class B a cover or a postal marking. The page builds its alt text from the class
and the figure's place; nothing about a figure is written by a model.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from app import settings

SHIPPED = Path(__file__).resolve().parent / "data" / "figures.tsv"
DIGEST_CHARS = 20
_DIGEST = re.compile(r"[0-9a-f]{20}")
# the target of a Markdown image, one level of parentheses allowed inside it (as passage_text reads it)
_IMAGE_TARGET = re.compile(r"!\[[^\]\n]*\]\(((?:[^()\n]|\([^()\n]*\))*)\)")


def digest(name: str) -> str:
    """The public name of a crop, without its extension."""
    return hashlib.sha256(unicodedata.normalize("NFC", name).encode("utf-8")).hexdigest()[:DIGEST_CHARS]


def read_list(path: Path) -> dict[str, tuple[int, int, str]]:
    """``{digest: (width, height, class)}`` from a list file. A line that does not hold all four is skipped."""
    known: dict[str, tuple[int, int, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) != 4 or not _DIGEST.fullmatch(parts[0]) or parts[3] not in ("A", "B"):
            continue
        try:
            width, height = int(parts[1]), int(parts[2])
        except ValueError:
            continue
        if width > 0 and height > 0:
            known[parts[0]] = (width, height, parts[3])
    return known


@lru_cache(maxsize=1)
def shipped() -> dict[str, tuple[int, int, str]]:
    """The list the backend ships with, read once."""
    return read_list(SHIPPED)


def removed() -> frozenset[str]:
    """``FIGURES_REMOVED``: digests never named, whatever the list says."""
    return frozenset(d.strip().lower() for d in settings.FIGURES_REMOVED.split(",") if _DIGEST.fullmatch(d.strip().lower()))


def on() -> bool:
    """Figures are named only when the figures host is set (settings.figures_base_ok)."""
    return settings.figures_base_ok(settings.FIGURES_BASE)


def named(text: str) -> list[str]:
    """The file names the stored text refers to, in their order, each once."""
    names: list[str] = []
    for target in _IMAGE_TARGET.findall(text or ""):
        name = target.strip().strip("<>").rsplit("/", 1)[-1].strip()
        if name and name not in names:
            names.append(name)
    return names


def of_passage(text: str, known: dict[str, tuple[int, int, str]] | None = None) -> list[dict]:
    """The figures a stored passage names that may be shown: digest, pixel size and class.

    ``known`` is the list to check against (the shipped one by default). A name whose digest is
    not in it, or is in ``FIGURES_REMOVED``, is left out; a name is never returned.
    """
    known = shipped() if known is None else known
    gone = removed()
    out: list[dict] = []
    for name in named(text):
        d = digest(name)
        if d in gone or d not in known or any(f["id"] == d for f in out):
            continue
        width, height, kind = known[d]
        out.append({"id": d, "width": width, "height": height, "class": kind})
    return out
