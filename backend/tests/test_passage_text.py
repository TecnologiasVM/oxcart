"""The text of a passage as it is shown. Every string here is made up; none is from the literature."""

import pytest

from app.passage_text import tidy


def test_a_line_break_written_as_backslash_n_becomes_a_line_break():
    assert tidy("A heading\\n\\nThe first line.\\nThe second line.") == "A heading\n\nThe first line.\nThe second line."


def test_real_line_breaks_stay_and_long_runs_of_them_shrink_to_one_empty_line():
    assert tidy("one\ntwo\n\n\n\nthree  \n  four") == "one\ntwo\n\nthree\nfour"


def test_a_written_tab_becomes_a_space_but_a_tex_command_that_starts_with_t_is_not_cut():
    assert tidy("5 c\\tblue\\t1889") == "5 c blue 1889"
    assert tidy("perf $12 \\times 12$ and $4^{\\text{th}}$") == "perf 12 × 12 and 4th"


@pytest.mark.parametrize("stored, shown", [
    ("$\\text{O}^{\\text{n}}$ the fourth day", "On the fourth day"),
    ("a turn of $90^{\\circ}$", "a turn of 90°"),
    ("a turn of $90^\\circ$", "a turn of 90°"),
    ("$\\mathrm{N}^{\\mathrm{o}}$ 12", "No 12"),
    ("gauge $11 \\frac{1}{2}$", "gauge 11 1/2"),
    ("$\\mathbf{\\text{bold}}$ word", "bold word"),
    ("value $5 \\%$ more", "value 5 % more"),
    ("$\\unknowncommand{x}$ stays readable", "x stays readable"),
    ("$\\sum_{\\text {all values}}$ here", "all values here"),
    ("$\\unknown^{\\text{word}}$ kept", "word kept"),
    ("$\\text{first line}\\\\\\text{second line}$", "first line second line"),
])
def test_a_small_formula_is_shown_as_the_characters_it_stands_for(stored, shown):
    assert tidy(stored) == shown


def test_tex_outside_any_dollar_marks_is_unwrapped_and_an_unknown_command_is_left_as_it_is():
    assert tidy("\\text{N}^{\\text{o}} 12, a turn of 90^{\\circ}") == "No 12, a turn of 90°"
    assert tidy("an \\unknown word and \\unknown_{low} too") == "an \\unknown word and \\unknown low too"
    assert tidy("$$\n\\begin{array}{ll} first & second \\end{array}\n$$\nafter") == "first & second\n\nafter"
    assert tidy("\\end{array} {these words stay}") == "{these words stay}"


def test_prices_in_dollars_are_not_taken_for_a_formula():
    assert tidy("sold at $5 and later at $12 each") == "sold at $5 and later at $12 each"
    assert tidy("from $1.50 to $2.00\\nValues: $3") == "from $1.50 to $2.00\nValues: $3"


def test_a_reference_to_an_image_file_is_not_shown():
    assert tidy("Before. ![](images/abc123.jpg) After.") == "Before. After."
    assert tidy("![a caption](img/x.png)\\nThe text.") == "The text."


def test_tags_of_the_reading_tool_and_markdown_marks_are_dropped_and_their_words_kept():
    assert tidy("an <underline>underlined</underline> word and a <smiles>mark</smiles>") == "an underlined word and a mark"
    assert tidy("first<br>second<br/>third") == "first\nsecond\nthird"
    assert tidy("a **bold** word, 2 ** 3 is left alone") == "a bold word, 2 ** 3 is left alone"
    assert tidy("## A heading\nthe text") == "A heading\nthe text"
    assert tidy("a\\_b and \\[1\\]") == "a_b and [1]"


def test_the_lines_the_chunking_step_appended_are_not_shown():
    stored = "A sentence of the page.\\nFechas: 1901, 1902. \\nCondición: made up. \\n\\nA second paragraph.\\nColores: blue. "
    assert tidy(stored) == "A sentence of the page.\n\nA second paragraph."
    every = ("Catálogos internacionales: A 1. ", "Fechas: 1901. ", "Valores faciales: 5 c. ", "Especificaciones técnicas: perf 12. ",
             "Condición: made up. ", "Variedades EFO: made up. ", "Período Guanacaste 1885-1891. ", "Significado histórico: made up. ",
             "Colores: blue. ", "Diseños: made up. ", "Precios: 5. ")
    assert tidy("The page." + "".join("\\n" + line for line in every)) == "The page."
    assert tidy("Fechas: 1901. ") == ""                                  # nothing but an appended line: no text to show


def test_a_label_inside_a_sentence_stays():
    assert tidy("The list gives Colores: blue and red, in that order.") == "The list gives Colores: blue and red, in that order."
    assert tidy("Fechas importantes de la emisión\nde 1901") == "Fechas importantes de la emisión\nde 1901"
    assert tidy("Color: blue\nDirector: a made-up name") == "Color: blue\nDirector: a made-up name"


def test_a_reading_loop_is_shown_once_and_the_words_around_it_stay():
    assert tidy("The office opened in " + "la " * 200) == "The office opened in la […]"
    assert tidy("A first sentence. Then " + "para " * 60 + "and the text goes on here.") == "A first sentence. Then para […] and the text goes on here."
    assert tidy("Before " + "de la casa " * 40 + "after it.") == "Before de la casa […] after it."
    irregular = "Start of it " + "de la la quorl de la quorl " * 20 + "end of it."      # the loop changes its step
    assert tidy(irregular) == "Start of it de la quorl […] end of it."
    two = "One " + "la " * 40 + "middle words that are real " + "para " * 40 + "end."
    assert tidy(two) == "One la […] middle words that are real para […] end."


def test_no_word_of_a_loop_disappears_only_its_repeats():
    column = "Rates: " + "letters " * 25 + "prints " * 25 + "parcels " * 25 + "as listed."       # a table's column, flattened
    assert tidy(column) == "Rates: letters […] prints […] parcels […] as listed."
    chain = "x " + "".join(f"{word} " * 30 for word in ("alpha", "beta", "gamma", "delta", "epsilon"))
    shown = tidy(chain)
    assert all(word in shown.split() for word in ("x", "alpha", "beta", "gamma", "delta", "epsilon"))
    assert shown == "x alpha […] beta […] gamma […] delta […] epsilon […]"


def test_what_only_looks_like_a_loop_is_left_alone():
    for real in ("ja ja ja ja ja ja ja ja, said the letter",                              # a short run
                 "5 c. " * 40 + "blue",                                                   # a column of figures
                 "0 " * 60,
                 "id. " * 12 + "and the rest of the list",                                # ditto marks, a dozen
                 "la emisión de la serie de la casa de la moneda de la ciudad de la costa de la isla de la paz"):
        assert tidy(real) == " ".join(real.split())


def test_other_angle_brackets_are_left_as_they_are():
    assert tidy("see <the list> and a < b > c") == "see <the list> and a < b > c"


def test_plain_text_comes_back_unchanged_and_odd_input_does_not_raise():
    plain = "A plain sentence, with accents: emisión, 1863; and a price of ₡5."
    assert tidy(plain) == plain
    assert tidy("") == "" and tidy(None) == ""
    for odd in ("$", "$$", "\\", "\\n", "$\\frac{1}{$", "^{", "![](", "**", "$" * 500, "{" * 400 + "}" * 400):
        assert isinstance(tidy(odd), str)


def test_tidying_twice_changes_nothing_more():
    stored = "A\\n\\n$\\text{N}^{\\text{o}}$ 4 ![](i.png) **b** <underline>u</underline>\\tend"
    assert tidy(tidy(stored)) == tidy(stored)
