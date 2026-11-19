"""
LLM-free entity lexicon + scorer for the Costa Rica 1863 First Issue.

This module is the core of the *lexical graph*: given a chunk of clean text it
decides, deterministically, whether the chunk talks about the First Issue and —
if so — which specific stamp(s) it refers to. No embeddings, no LLM. Pure
regex + a small weighted-signal scoring model derived from the domain facts in
the Mena/Scott catalogs.

Signal classes (each contributes a weight when present):
  ISSUE_PHRASE  "first issue" / "primera emisión"        weight 3
  YEAR_1863     the anchor year 1863                       weight 2
  YEAR_OTHER    other first-issue-timeline years           weight 1
  DENOM         a first-issue denomination                 weight 2
  PRINTER       ABNCo / American Bank Note                 weight 2
  DESIGN        coat of arms / volcano-ship-stars motif    weight 1
  ENTITY        people/events unique to the issue          weight 1
  PLATE         second-plate / known plate positions       weight 1

Linking rule (tunable via config):
  link if total_score >= FIRST_ISSUE_MIN_LINK_SCORE
       OR (ISSUE_PHRASE present AND total_score >= FIRST_ISSUE_PHRASE_MIN_SCORE)

Stamp disambiguation uses denomination + color co-occurrence to map a passage
to a Mena/Scott catalog number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Set

from oxcart.config import (
    FIRST_ISSUE_COMPETING_MIN_CLASSES,
    FIRST_ISSUE_MIN_LINK_SCORE,
    FIRST_ISSUE_MIN_STRONG_CLASSES,
    FIRST_ISSUE_STAMP_MIN_CONF,
)

# --------------------------------------------------------------------------- #
# Regex building blocks (compiled once)
# --------------------------------------------------------------------------- #
_FLAGS = re.IGNORECASE

ISSUE_PHRASE_RE = re.compile(
    r"\b("
    r"first\s+issue|"
    # Spanish "primera emisión / primera serie", OCR-tolerant (emision/emission),
    # plus "primer(a) sello/estampilla" and "emisión inicial".
    r"primera?\s+(?:emisi[oó]n|emision|emission|serie)|"
    r"primer\s+emisi[oó]n|"
    r"primer(?:a|os|as)?\s+(?:sello|estampilla)s?|"
    r"emisi[oó]n\s+inicial"
    r")\b",
    _FLAGS,
)

# "first issue" used GENERICALLY (a new/forthcoming issue, not the 1863 proper
# noun). E.g. "the first issue will be known as the First Continental ...".
GENERIC_PHRASE_RE = re.compile(
    r"first\s+issue\s+(?:will\b|shall\b|is\s+(?:the|going|to)\b|"
    r"of\s+(?:these|the\s+new|this\s+series|the\s+three)\b|known\s+as\b|"
    r"to\s+be\s+(?:known|issued|called)\b)",
    _FLAGS,
)

# Competing / later-issue context: strong cue that a DIFFERENT issue is the
# subject (commemoratives, air mail, charity, sports, named modern series).
# Also: the 1881-83 SURCHARGE issue (overprints on the reales base, U.P.U.),
# the 1885+ Guanacaste overprints, and provisionals — these reuse first-issue
# cues (reales, escudo, ABNCo) but are NOT the 1863 postage first issue.
# (FISCAL/revenue context is handled by its own HARD guard below.)
COMPETING_RE = re.compile(
    r"\b(commemorat\w*|conmemorativ\w*|conference|congress|olympic\w*|olimpiad\w*|centennial|"
    r"anniversary|souvenir\s+sheet|air\s*mail|a[eé]reo|red\s+cross|cruz\s+roja|"
    r"boy\s+scout|unicef|world\s+cup|copa\s+mundial|cocor[ií]|san\s+vicente|"
    r"188[12]|u\.?\s*p\.?\s*u\.?|guanacaste|provisional\w*|sobretasa)\b",
    _FLAGS,
)

# Foreign classic issues share the SAME cues as Costa Rica's (reales, escudo,
# "primera emisión"). Latin-American neighbours especially. If a passage is
# explicitly about one of these AND never mentions Costa Rica, it is not ours.
# Note: México also appears as the old spelling "Méjico/mejicano".
FOREIGN_COUNTRY_RE = re.compile(
    r"\b(m[eé][xj]ico|m[eé]?xican\w*|mejican\w*|colombia\w*|granadin\w*|chile\w*|chilen\w*|"
    r"per[uú]\b|peruan\w*|peruvian\w*|argentin\w*|guatemal\w*|nicarag\w*|hondur\w*|salvador\w*|"
    r"panam[aá]\w*|venezuel\w*|ecuador\w*|bolivia\w*|brasil\w*|brazil\w*|cuba\w*|espa[nñ]a|spain\b)\b",
    _FLAGS,
)

# Costa Rica as the subject (country / adjective / "C.R.").
COSTA_RICA_RE = re.compile(r"\b(costa\s*rica\w*|costarricens\w*|c\.\s*r\.)", _FLAGS)

# FISCAL / revenue-stamp context. The Timbre journal mixes postage and revenue;
# a revenue article can say "primera emisión [de timbres fiscales]" (the first
# issue of REVENUE stamps) and reuse escudo/ABNCo. Treated as a HARD guard:
# fiscal context with NO 1863 anchor cannot be the 1863 postage first issue,
# even if an (ambiguous) issue-phrase is present.
FISCAL_RE = re.compile(r"\b(fiscal\w*|papel\s+sellado|timbre\s+de\s+renta)\b", _FLAGS)

# First-issue timeline years. 1863 is the anchor; others corroborate.
YEAR_ANCHOR = 1863
FIRST_ISSUE_YEARS: Set[int] = {1862, 1863, 1864, 1866, 1875, 1883}
YEAR_RE = re.compile(r"\b(18\d{2})\b")

PRINTER_RE = re.compile(
    r"\b(abnco?\.?|american\s+bank\s*note(?:\s+co\.?)?|"
    r"banco\s+americano\s+de\s+billetes)\b",
    _FLAGS,
)

DESIGN_RE = re.compile(
    r"\b(coat\s+of\s+arms|escudo(?:\s+de\s+armas)?|volcano(?:es)?|volc[aá]n(?:es)?|"
    r"sailing\s+ship|velero|five\s+stars|cinco\s+estrellas|ornate\s+scrollwork|"
    r"papel\s+indio|india\s+paper)\b",
    _FLAGS,
)

# People / events that are specific to the First Issue narrative.
ENTITY_RE = re.compile(
    r"\b(mechin|mayer|jaime\s+ross|julian\s+volio|francisco\s+echeverr[ií]a|"
    r"luis\s+molina|demonetiz\w*|desmonetiz\w*|"
    r"decree\s*#?\s*2\b|decreto\s+n[°ºo.\s]*2\b)\b",
    _FLAGS,
)

PLATE_RE = re.compile(
    r"\b(second\s+plate|primera\s+plancha|segunda\s+plancha|plate\s+(?:2|two|ii)\b|"
    r"light\s+blue|pos\s*\.?\s*(?:2|8|87|89|96)\b|plate\s+variet|"
    r"rotura\s+de\s+la\s+plancha|sin\s+perforar|sin\s+dentar|imperforad\w*)",
    _FLAGS,
)

# Colors relevant to the four denominations.
COLOR_PATTERNS: Dict[str, re.Pattern] = {
    "blue": re.compile(r"\bblue\b|\bazul\b", _FLAGS),
    "scarlet": re.compile(r"\bscarlet\b|\bescarlata\b", _FLAGS),
    "red": re.compile(r"\bred\b|\brojo\b|\breddish\b", _FLAGS),
    "orange": re.compile(r"\borange\b|\bnaranja\b", _FLAGS),
    "green": re.compile(r"\bgreen\b|\bverde\b", _FLAGS),
    "yellow": re.compile(r"\byellow\b|\bamarillo\b", _FLAGS),
}

# Denomination detectors. key -> compiled regex.
DENOM_PATTERNS: Dict[str, re.Pattern] = {
    "half_real": re.compile(
        r"(½|1\s*/\s*2|\bhalf\b|\bmedi[oa]\b)\s*real(?:es)?\b", _FLAGS
    ),
    "two_reales": re.compile(r"\b(2|dos|two)\s*real(?:es)?\b", _FLAGS),
    "four_reales": re.compile(r"\b(4|cuatro|four)\s*real(?:es)?\b", _FLAGS),
    "one_peso": re.compile(r"\b(1|un|uno|one)\s*peso(?:s)?\b", _FLAGS),
}

# Catalog references that strongly imply the issue (Scott/Mena 1-4 are first issue).
CATALOG_REF_RE = re.compile(
    r"\b(?:scott|mena|sc\.?|#)\s*#?\s*([1-4][a-bA-B]?)\b", _FLAGS
)


# --------------------------------------------------------------------------- #
# Stamp signatures: denomination + expected colors -> catalog numbers
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StampSignature:
    mena: str
    scott: str
    denom_key: str
    colors: Set[str]
    label: str


STAMP_SIGNATURES: List[StampSignature] = [
    StampSignature("1", "1", "half_real", {"blue"}, "½ real blue"),
    StampSignature("2", "2", "two_reales", {"scarlet", "red", "orange"}, "2 reales scarlet"),
    StampSignature("3", "3", "four_reales", {"green"}, "4 reales green"),
    StampSignature("4", "4", "one_peso", {"orange", "yellow"}, "1 peso orange"),
]

# Signal weights
W_ISSUE_PHRASE = 3
W_YEAR_ANCHOR = 2
W_YEAR_OTHER = 1
W_DENOM = 2
W_PRINTER = 2
W_DESIGN = 1
W_ENTITY = 1
W_PLATE = 1


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #
@dataclass
class StampMatch:
    mena: str
    scott: str
    label: str
    confidence: float
    signals: List[str] = field(default_factory=list)


@dataclass
class ChunkLink:
    score: float
    linked: bool
    signals: Dict[str, List[str]]
    stamps: List[StampMatch]

    def signal_summary(self) -> List[str]:
        """Flat list of signal-class names that fired (for storing on the edge)."""
        return sorted(k for k, v in self.signals.items() if v)


# --------------------------------------------------------------------------- #
# Pure extractors
# --------------------------------------------------------------------------- #
def extract_years(text: str) -> List[int]:
    return [int(y) for y in YEAR_RE.findall(text or "")]


def first_issue_years_in(text: str) -> List[int]:
    return sorted({y for y in extract_years(text) if y in FIRST_ISSUE_YEARS})


def extract_denominations(text: str) -> List[str]:
    return [k for k, rx in DENOM_PATTERNS.items() if rx.search(text or "")]


def extract_colors(text: str) -> List[str]:
    found: List[str] = []
    for color, rx in COLOR_PATTERNS.items():
        if rx.search(text or ""):
            found.append(color)
    # Normalize: scarlet/reddish imply red family but keep distinct tokens.
    return found


def extract_catalog_refs(text: str) -> List[str]:
    return [m.lower() for m in CATALOG_REF_RE.findall(text or "")]


def match_stamps(text: str) -> List[StampMatch]:
    """Map a passage to specific first-issue stamps via denomination+color."""
    text = text or ""
    denoms = set(extract_denominations(text))
    colors = set(extract_colors(text))
    matches: List[StampMatch] = []
    for sig in STAMP_SIGNATURES:
        if sig.denom_key not in denoms:
            continue
        color_overlap = sig.colors & colors
        signals = [f"denom:{sig.denom_key}"]
        if color_overlap:
            conf = 0.9
            signals.append("color:" + "/".join(sorted(color_overlap)))
        else:
            conf = 0.5  # denomination only — plausible but weaker
        if conf >= FIRST_ISSUE_STAMP_MIN_CONF:
            matches.append(
                StampMatch(sig.mena, sig.scott, sig.label, conf, signals)
            )
    return matches


# Strong signal classes — a link requires at least N DISTINCT of these to fire.
# (YEAR_OTHER and CATALOG are corroborating-only and do NOT count toward this.)
STRONG_CLASSES = ("ISSUE_PHRASE", "YEAR_ANCHOR", "DENOM", "PRINTER", "ENTITY", "PLATE", "DESIGN")

# CORE signal classes — high-precision, first-issue-SPECIFIC cues. A link must
# fire at least one of these. This rejects passages that match only on generic
# corroborators (a person name via ENTITY + an incidental "first issue" phrase,
# or a bare "plate"/"overprint" mention on a revenue stamp). The anchor year
# 1863, a reales/peso denomination, or the ABNCo printer are the trustworthy
# first-issue cues; PLATE stays a STRONG (corroborating) class but is not core.
CORE_CLASSES = ("YEAR_ANCHOR", "DENOM", "PRINTER")


def has_real_issue_phrase(text: str) -> bool:
    """
    True if "first issue" appears as the 1863 proper-noun referent, NOT as a
    generic 'the first issue will be ...' construction announcing a new issue.
    Spanish 'primera emisión' is always treated as the proper-noun referent.
    """
    text = text or ""
    matches = list(ISSUE_PHRASE_RE.finditer(text))
    if not matches:
        return False
    for m in matches:
        # A match is "real" unless it begins a generic construction.
        if not GENERIC_PHRASE_RE.match(text[m.start(1):]):
            return True
    return False


# --------------------------------------------------------------------------- #
# Scorer
# --------------------------------------------------------------------------- #
def score_chunk(text: str) -> ChunkLink:
    """Score a chunk's relevance to the First Issue and resolve stamp mentions."""
    text = text or ""
    signals: Dict[str, List[str]] = {
        "ISSUE_PHRASE": [],
        "YEAR_ANCHOR": [],
        "YEAR_OTHER": [],
        "DENOM": [],
        "PRINTER": [],
        "DESIGN": [],
        "ENTITY": [],
        "PLATE": [],
        "CATALOG": [],
    }

    score = 0.0

    if has_real_issue_phrase(text):
        signals["ISSUE_PHRASE"] = [m.group(0).lower() for m in ISSUE_PHRASE_RE.finditer(text)]
        score += W_ISSUE_PHRASE

    years = first_issue_years_in(text)
    if YEAR_ANCHOR in years:
        signals["YEAR_ANCHOR"] = [str(YEAR_ANCHOR)]
        score += W_YEAR_ANCHOR
    other_years = [str(y) for y in years if y != YEAR_ANCHOR]
    if other_years:
        signals["YEAR_OTHER"] = other_years
        score += W_YEAR_OTHER

    denoms = extract_denominations(text)
    if denoms:
        signals["DENOM"] = denoms
        score += W_DENOM

    if PRINTER_RE.search(text):
        signals["PRINTER"] = [m.group(0).lower() for m in PRINTER_RE.finditer(text)]
        score += W_PRINTER

    if DESIGN_RE.search(text):
        signals["DESIGN"] = sorted({m.group(0).lower() for m in DESIGN_RE.finditer(text)})
        score += W_DESIGN

    if ENTITY_RE.search(text):
        signals["ENTITY"] = sorted({m.group(0).lower() for m in ENTITY_RE.finditer(text)})
        score += W_ENTITY

    if PLATE_RE.search(text):
        signals["PLATE"] = sorted({m.group(0).lower() for m in PLATE_RE.finditer(text)})
        score += W_PLATE

    cat_refs = extract_catalog_refs(text)
    if cat_refs:
        signals["CATALOG"] = cat_refs  # informational; not scored to avoid FP from bare "1"

    # Competing / later-issue context (commemoratives etc.) — recorded as a signal
    # so it is visible on the edge, and used to raise the linking bar.
    competing = sorted({m.group(0).lower() for m in COMPETING_RE.finditer(text)})
    if competing:
        signals["COMPETING"] = competing

    # --- Precision gate -----------------------------------------------------
    # Require a minimum weighted score AND a minimum number of DISTINCT strong
    # signal classes. The class count is what rejects single-cue false positives
    # (e.g. a lone ambiguous "first issue" mention, or a stray year).
    strong_classes = sum(1 for k in STRONG_CLASSES if signals.get(k))
    has_core = any(signals.get(k) for k in CORE_CLASSES)
    needed = FIRST_ISSUE_COMPETING_MIN_CLASSES if competing else FIRST_ISSUE_MIN_STRONG_CLASSES
    linked = (score >= FIRST_ISSUE_MIN_LINK_SCORE) and (strong_classes >= needed) and has_core
    # In competing context, also require the 1863 anchor or a proper-noun phrase
    # so a commemorative passage cannot link on denomination/printer alone.
    if linked and competing and not (signals.get("YEAR_ANCHOR") or signals.get("ISSUE_PHRASE")):
        linked = False

    # Geographic guard: a passage explicitly about ANOTHER country that never
    # mentions Costa Rica is a foreign classic issue reusing the same cues
    # (reales / escudo / "primera emisión"), not our 1863 first issue.
    foreign = sorted({m.group(0).lower() for m in FOREIGN_COUNTRY_RE.finditer(text)})
    if foreign:
        signals["FOREIGN"] = foreign
        if linked and not COSTA_RICA_RE.search(text):
            linked = False

    # Fiscal/revenue HARD guard: "first issue of fiscal stamps" must not pass as
    # the 1863 postage first issue. Only the 1863 anchor rescues a fiscal passage.
    if FISCAL_RE.search(text):
        signals["FISCAL"] = sorted({m.group(0).lower() for m in FISCAL_RE.finditer(text)})
        if linked and not signals.get("YEAR_ANCHOR"):
            linked = False

    stamps = match_stamps(text) if linked else []

    return ChunkLink(score=score, linked=linked, signals=signals, stamps=stamps)


if __name__ == "__main__":
    import json
    import sys

    sample = (
        "April 11, 1863. Engraved and recess printed by ABNCo. The half real and "
        "2 reales stamps probably circulated. The second plate is in light blue."
    )
    text = sys.argv[1] if len(sys.argv) > 1 else sample
    link = score_chunk(text)
    print(json.dumps(
        {
            "score": link.score,
            "linked": link.linked,
            "signals": link.signal_summary(),
            "stamps": [s.__dict__ for s in link.stamps],
        },
        indent=2,
    ))
