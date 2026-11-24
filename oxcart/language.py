"""Which language a passage is in, Spanish or English, by its own words. No model, nothing stored.

A rule over function words: the small words every sentence needs and that belong to one of the two
languages only. Words both languages write (a, no, me, as, has, son, con, he, fin) are in neither list, and
accents are removed first, so a scan that lost them is told the same.

``of_passage`` says "es", "en" or None. None means it cannot be told: fewer than MIN_WORDS of these words
(a list, a header, a table of values), or both languages in comparable parts.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

_WORD = re.compile(r"[^\W\d_]+")
SPANISH = frozenset("""
el la los las del de y que en un una unos unas por para como pero este esta estos estas ese esa esos esas
aquel aquella su sus lo le les se al es era eran fue fueron ser sido esta estan estaba hay ha han habia
cual cuales cuando donde quien quienes porque sino tambien muy mas sin sobre entre desde hasta segun durante
otro otra otros otras todo toda todos todas cada ya dos tres solo
""".split())
ENGLISH = frozenset("""
the of and to in is was were are be been being that this these those which who whom whose when where what
with from for by at on or an it its his her their there they them she we our you your but not have had
would could should will shall may might can did does do into upon than then also only such very more most
other others each all any some both between during after before because so if
""".split())
_BOTH = SPANISH & ENGLISH
MIN_WORDS = 5           # function words that a passage needs before its language is told
TIMES = 2               # and one language needs this many times the other's


def words_of_each(text: str) -> tuple[int, int]:
    """(Spanish function words, English function words) in the text."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", (text or "").lower()) if not unicodedata.combining(c))
    words = _WORD.findall(plain)
    return (sum(w in SPANISH and w not in _BOTH for w in words), sum(w in ENGLISH and w not in _BOTH for w in words))


def of_passage(text: str) -> Optional[str]:
    """"es", "en", or None when the passage is too short to tell or holds both."""
    spanish, english = words_of_each(text)
    if spanish + english < MIN_WORDS:
        return None
    if spanish >= TIMES * english:
        return "es"
    if english >= TIMES * spanish:
        return "en"
    return None
