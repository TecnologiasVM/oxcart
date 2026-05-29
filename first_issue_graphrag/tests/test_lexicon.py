"""
Regression tests for the LLM-free First Issue lexicon (the linking crux).

Run directly (no pytest harness required):
    ".venv-clean\\Scripts\\python.exe" first_issue_graphrag\\tests\\test_lexicon.py
Also pytest-compatible.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap: add the package dir so `import lexicon` works standalone.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lexicon as lx  # noqa: E402

# The canonical First Issue paragraph (from the Mena Issue.plain_raw_text).
FIRST_ISSUE_PARA = (
    "April 11, 1863. Decree #2 of August 18, 1862. Engraved and recess printed "
    "by ABNCo. in panes of 100. Perf 12. The half real and 2 reales stamps "
    "probably circulated on April 11, 1863. The second plate is in light blue "
    "with little or no sky over the mountains. Demonetized January 31, 1883."
)

# A real corroborating passage (BM25 surfaced this from OXCART50 p.19, verbatim).
DECIMAL_CURRENCY_PARA = (
    "In 1864, shortly after the stamps of the first issue were placed in use, "
    "Costa Rica adopted a decimal currency system, in which the peso, the value "
    "of which remained unchanged, was divided into 100 centavos, rather than the "
    "8 reales of the former currency. Thus, the real was worth 12-1/2 centavos "
    "and the medio real, 6-1/4 centavos."
)

# Negative: masthead/subscription blurb (the contaminated OXCART03 chunk text).
NEGATIVE_MASTHEAD = (
    "By and for collectors of Costa Rica Published quarterly at San Francisco, "
    "California Subscription - $4.00 per annum PUBLISHER Arthur L. Hebel"
)

# Negative: a later-issue paragraph that mentions a year but not the first issue.
NEGATIVE_OTHER_ISSUE = (
    "The 1921 air mail provisional was overprinted in red on the 1910 "
    "definitive series and sold in San Jose."
)

# Negative: GENERIC 'first issue' announcing a NEW 1961 commemorative series
# (this was a real false positive found in OXCART03/OXCART04 ground-truth read).
NEGATIVE_GENERIC_PHRASE = (
    "NEW ISSUE INFORMATION. Notices calling for bids on three new series of "
    "postage stamps appeared in La Gaceta of January 20, 1961. The first issue "
    "will be known as the First Continental Lawyers Conference, commemorating "
    "the event with a 10c brownish-red stamp."
)

# Negative: a single passing 'first issue' mention with no corroborating
# first-issue evidence (this was a real false positive: OXCART50 'President's Page').
NEGATIVE_SINGLE_MENTION = (
    "The President's Page. I would like to call the attention of members to the "
    "article on the next page, published by the Harmer organization. The article "
    "confirms the importance of the first issue to serious collectors."
)

# Negative: an article about COUNTERFEIT TELEGRAPH stamps (Scott 150) that
# name-drops a person + 'first issue' but has NO core first-issue cue (no 1863,
# no reales/peso denomination, no ABNCo, no plate). Real FP found in OXCART01.
NEGATIVE_COUNTERFEIT_TELEGRAPH = (
    "KOUNTERFIT KORNER. Notes on the 13c/40c Telegraph, Scott Nos. 150-150a, "
    "Saenz Nos. 381-381a. These covers demonstrate genuine postal use of "
    "counterfeits. As R. J. Mechin observed, the first issue of this forgery "
    "appeared on cover in fine condition."
)


def _check(name: str, cond: bool) -> bool:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    return cond


def run() -> int:
    failures = 0

    print("test_first_issue_paragraph_links_and_resolves_stamps")
    link = lx.score_chunk(FIRST_ISSUE_PARA)
    failures += not _check("links to issue", link.linked)
    failures += not _check("score >= 4", link.score >= 4)
    mena = {s.mena for s in link.stamps}
    failures += not _check("resolves stamp Mena 1 (half real)", "1" in mena)
    failures += not _check("resolves stamp Mena 2 (two reales)", "2" in mena)
    failures += not _check("PRINTER signal fired", bool(link.signals["PRINTER"]))
    failures += not _check("PLATE signal fired (second plate/light blue)", bool(link.signals["PLATE"]))

    print("test_decimal_currency_paragraph_links_via_phrase")
    link2 = lx.score_chunk(DECIMAL_CURRENCY_PARA)
    failures += not _check("links to issue (first issue + 1864 + peso)", link2.linked)
    failures += not _check("ISSUE_PHRASE fired", bool(link2.signals["ISSUE_PHRASE"]))

    print("test_masthead_does_not_link")
    link3 = lx.score_chunk(NEGATIVE_MASTHEAD)
    failures += not _check("masthead NOT linked", not link3.linked)

    print("test_other_issue_does_not_link")
    link4 = lx.score_chunk(NEGATIVE_OTHER_ISSUE)
    failures += not _check("other-issue paragraph NOT linked", not link4.linked)

    print("test_generic_first_issue_phrase_does_not_link")
    link5 = lx.score_chunk(NEGATIVE_GENERIC_PHRASE)
    failures += not _check("'first issue will be known as...' NOT linked", not link5.linked)
    failures += not _check("ISSUE_PHRASE suppressed for generic usage", not link5.signals["ISSUE_PHRASE"])
    failures += not _check("COMPETING context detected", bool(link5.signals.get("COMPETING")))

    print("test_single_passing_mention_does_not_link")
    link6 = lx.score_chunk(NEGATIVE_SINGLE_MENTION)
    failures += not _check(
        "single 'first issue' mention NOT linked (needs >=2 strong classes)",
        not link6.linked,
    )

    print("test_counterfeit_telegraph_does_not_link")
    link7 = lx.score_chunk(NEGATIVE_COUNTERFEIT_TELEGRAPH)
    failures += not _check(
        "counterfeit-telegraph article NOT linked (no core first-issue cue)",
        not link7.linked,
    )

    print("test_stamp_color_disambiguation")
    failures += not _check(
        "'4 reales green' -> Mena 3",
        any(s.mena == "3" for s in lx.match_stamps("the 4 reales green stamp")),
    )
    failures += not _check(
        "'1 peso orange' -> Mena 4",
        any(s.mena == "4" for s in lx.match_stamps("the 1 peso orange value")),
    )
    failures += not _check(
        "high confidence when color matches",
        all(
            s.confidence >= 0.9
            for s in lx.match_stamps("½ real blue")
            if s.mena == "1"
        ),
    )

    print()
    if failures:
        print(f"RESULT: {failures} check(s) FAILED")
        return 1
    print("RESULT: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
