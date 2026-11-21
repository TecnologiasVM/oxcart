"""The excerpt of a long passage that is nearest the question. Every text is made up."""

from app import ask_service

FILLER = "Nothing in this part of the made-up passage speaks of the matter at hand. " * 30
HIT = "The lilac parrot overprint was applied in Turrialba by a travelling clerk during the flood. "


def test_a_passage_within_the_limit_is_shown_whole():
    assert ask_service.excerpt("A short made-up passage.", "Any question?", 700) == ("A short made-up passage.", False)


def test_the_stretch_that_shares_the_most_words_with_the_question_is_shown():
    text = FILLER + HIT + FILLER
    shown, cut = ask_service.excerpt(text, "Where was the lilac parrot overprint applied?", 700)
    assert cut and "Turrialba" in shown
    assert shown.startswith("…") and shown.endswith("…")
    assert len(shown) <= 702
    assert "Turrialba" not in ask_service.clip(text, 700)[0]          # the start of the passage does not hold it


def test_accents_and_case_do_not_matter_and_the_common_words_do_not_count():
    text = FILLER + "El resello lila del loro se aplicó en Turrialba. " + FILLER
    shown, _ = ask_service.excerpt(text, "¿DÓNDE SE APLICO EL RESELLO LILA DEL LORO?", 700)
    assert "Turrialba" in shown
    assert ask_service._terms("What stamps of Costa Rica?") == set()


def test_with_nothing_shared_the_start_is_shown_as_before():
    text = FILLER + HIT
    shown, cut = ask_service.excerpt(text, "¿Quién diseñó el matasellos?", 700)
    assert cut and shown == ask_service.clip(text, 700)[0]


def test_the_start_is_kept_when_it_shares_as_many_words_as_any_other_stretch():
    text = HIT + FILLER + HIT + FILLER
    shown, _ = ask_service.excerpt(text, "Where was the lilac parrot overprint applied?", 700)
    assert shown == ask_service.clip(text, 700)[0]


def test_the_shared_words_sit_inside_the_stretch_not_at_its_edge():
    text = FILLER + HIT + FILLER
    shown, _ = ask_service.excerpt(text, "Where was the lilac parrot overprint applied?", 700)
    assert 150 < shown.index("lilac parrot") < 450


def test_the_last_words_of_a_passage_can_be_reached():
    text = FILLER + FILLER + "At the very end stands the cinnamon heron essay."
    shown, _ = ask_service.excerpt(text, "What is known about the cinnamon heron essay?", 700)
    assert shown.endswith("cinnamon heron essay.") and shown.startswith("…")


def test_the_setting_chooses_which_excerpt_the_question_path_shows(monkeypatch):
    from app import settings
    assert settings.ASK_EXCERPT == "start"                             # the served default until the numbers choose
