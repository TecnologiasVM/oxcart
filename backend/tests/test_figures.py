"""Figures of the shown passages: named by digest, only from the shipped list, never by their own name.

Every name, digest and passage here is made up; the one real thing read is the shipped list's shape.
"""

import hashlib
import json
import re
import unicodedata

import pytest

from app import ask_service, figures, settings

from oxcart import config

BASE = "https://figures.example"
# a made-up document whose name changes under NFC: "e" + combining acute (NFD) against "é" (NFC)
NFC_NAME = "Boletín Inventado 7_page_003_figure_001.png"
NFD_NAME = unicodedata.normalize("NFD", NFC_NAME)
SHOWN, UNLISTED, REMOVED_ONE = (f"Made Up Journal 12_page_004_figure_00{i}.png" for i in (1, 2, 3))
PASSAGE = (f"An invented paragraph about a made-up cover.\\n![Figure](figures/{SHOWN})\\n"
           f"More invented words. ![Figure](figures/{UNLISTED}) ![Figure](figures/{REMOVED_ONE}) The end.")


def test_the_digest_is_the_first_20_hex_of_the_sha256_of_the_nfc_name():
    assert NFC_NAME != NFD_NAME
    expected = hashlib.sha256(NFC_NAME.encode("utf-8")).hexdigest()[:20]
    assert figures.digest(NFC_NAME) == expected
    assert figures.digest(NFD_NAME) == expected
    assert re.fullmatch(r"[0-9a-f]{20}", expected)


def test_the_stored_text_names_its_figures_in_order_each_once():
    text = f"![Figure](figures/{SHOWN}) a ![x](other/dir/{UNLISTED}) ![Figure](figures/{SHOWN})"
    assert figures.named(text) == [SHOWN, UNLISTED]
    assert figures.named("no figure here, ![broken(") == []


class Fake:
    def deps(self, text):
        return ask_service.AskDeps(
            embed=lambda q: [0.1],
            lookup=lambda q, v: [],
            search=lambda q, v: [{"doc_id": "Made Up Journal 12", "page": 4, "chunk_type": "text", "text": text, "score": 0.5}],
            verify_human=lambda token: "ok")


@pytest.fixture
def listed(monkeypatch):
    """A made-up list holding two of the three figures the passage names (one of them removed in a test)."""
    known = {figures.digest(SHOWN): (310, 180, "B"), figures.digest(REMOVED_ONE): (90, 120, "A")}
    monkeypatch.setattr(figures, "shipped", lambda: known)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "set-for-the-mode-label")
    monkeypatch.setattr(settings, "FIGURES_REMOVED", "")
    return known


def passages(text):
    return ask_service.answer("A made-up question?", Fake().deps(text))["passages"]


def test_a_passage_naming_three_figures_returns_those_in_the_list(monkeypatch, listed):
    monkeypatch.setattr(settings, "FIGURES_BASE", BASE)
    [p] = passages(PASSAGE)
    assert p["figures"] == [
        {"id": figures.digest(SHOWN), "width": 310, "height": 180, "class": "B"},
        {"id": figures.digest(REMOVED_ONE), "width": 90, "height": 120, "class": "A"},
    ]
    # the references stay out of the shown text, and no crop's own name is in the response
    body = json.dumps(p)
    assert "figure_00" not in body and ".png" not in body and "![" not in p["text"]


def test_a_removed_digest_is_never_named(monkeypatch, listed):
    monkeypatch.setattr(settings, "FIGURES_BASE", BASE)
    monkeypatch.setattr(settings, "FIGURES_REMOVED", f" {figures.digest(REMOVED_ONE).upper()} ,not-a-digest")
    [p] = passages(PASSAGE)
    assert [f["id"] for f in p["figures"]] == [figures.digest(SHOWN)]


def test_without_figures_base_the_passages_are_todays_byte_for_byte(monkeypatch, listed):
    today = json.dumps([{"doc_id": "Made Up Journal 12", "page": 4, "chunk_type": "text",
                         "text": "An invented paragraph about a made-up cover.\n\nMore invented words. The end.",
                         "clipped": False, "score": 0.5}])
    for off in ("", "http://figures.example", "ftp://figures.example", "javascript:alert(1)"):
        monkeypatch.setattr(settings, "FIGURES_BASE", off)
        assert json.dumps(passages(PASSAGE)) == today, off
    # on, and nothing the passage names is in the list: no key either
    monkeypatch.setattr(settings, "FIGURES_BASE", BASE)
    assert "figures" not in passages(f"![Figure](figures/{UNLISTED}) Words.")[0]


def test_the_figures_base_accepts_https_and_this_machine_only():
    ok = ["https://figures.example", "https://figures.example/path", "http://127.0.0.1:8123", "http://localhost:9000/f"]
    bad = ["", "http://figures.example", "https://", "https://a b", "https://x.example/\"onerror", "//x.example", "data:image/png"]
    assert all(settings.figures_base_ok(b) for b in ok)
    assert not any(settings.figures_base_ok(b) for b in bad)


def test_the_shipped_list_loads():
    figures.shipped.cache_clear()
    known = figures.shipped()
    assert len(known) == 8216
    lines = figures.SHIPPED.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 8216            # no line was skipped on reading
    for d, (width, height, kind) in known.items():
        assert re.fullmatch(r"[0-9a-f]{20}", d)
        assert width > 0 and height > 0
        assert kind in ("A", "B")
