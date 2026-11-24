"""Which language a passage is in, by its function words. Every text is made up."""

from oxcart import language

SPANISH = "El resello de la emisión se hizo en la imprenta para los sellos que se usaron en la provincia."
ENGLISH = "The overprint of the issue was made at the printing office for the stamps that were used there."


def test_a_passage_is_told_by_its_own_function_words():
    assert language.of_passage(SPANISH) == "es"
    assert language.of_passage(ENGLISH) == "en"


def test_accents_and_case_do_not_matter():
    assert language.of_passage("LA EMISION SE HIZO EN LA IMPRENTA PARA LOS SELLOS DE ESTA PROVINCIA") == "es"
    assert language.of_passage("Según el catálogo, también había más sellos sin dentar durante ese año.") == "es"


def test_a_passage_with_too_few_such_words_cannot_be_told():
    assert language.of_passage("") is None and language.of_passage(None) is None
    assert language.of_passage("1863 1864 1865 2 reales 4 reales") is None
    assert language.of_passage("Guanacaste overprint, 5 centavos") is None


def test_a_passage_that_holds_both_in_comparable_parts_cannot_be_told():
    assert language.of_passage(SPANISH + " " + ENGLISH) is None
    assert language.of_passage(SPANISH + " " + SPANISH + " " + SPANISH + " The stamp.") == "es"


def test_words_both_languages_write_are_in_neither_list():
    assert not (language.SPANISH & language.ENGLISH)
    for word in ("a", "no", "me", "has", "son", "con", "he", "fin", "as"):
        assert word not in language.SPANISH and word not in language.ENGLISH
    assert language.words_of_each("a no me has son con he fin") == (0, 0)
