"""A passage as a person reads it: the stored text with the marks of its preparation undone.

The literature was read from scans and exports, and what is stored carries marks of that work: line
breaks written as the two characters backslash and n, references to image files, small formulas in TeX
where the page had a superscript or a degree sign, tags left by the tool that read the page, Markdown
emphasis. On a page those marks read as errors.

The stored text also holds lines that are not the literature's: the chunking step
(``pipeline/philatelic_chunk_logic.py``) appended metadata it had extracted, one labelled line each
("Fechas: ...", "Condición: ...", "Colores: ..."), so that the search would find it. They help the search
and are not shown: under a paragraph they read as part of the page, which they are not.
``pipeline/first_issue_graph/sanitize_chunks.py`` strips the same lines for the graph.

A few fragments (about one in a thousand) hold a reading loop: where the tool that read the scan lost
the page it wrote one word, or two or three, over and over ("la la la la ..."), sometimes for the rest of
the fragment. That run is not the page's text either. Each of its words is shown once, and ``[…]`` stands for the repeats.

``tidy`` undoes the marks, leaves those lines out, cuts a loop short, and does nothing else. It adds no
word, drops no word of the page and changes no order; a line break stays a line break. It works on the
text that is shown: the stores, the search and the evaluation still see the text as stored.
"""

from __future__ import annotations

import re

# TeX commands that only wrap their argument: \text{th} -> th
_WRAPPERS = re.compile(
    r"\\(?:text|textbf|textit|textrm|mathrm|mathbf|mathbb|mathcal|mathfrak|mathit|mathsf|operatorname|boldsymbol"
    r"|underline|overline|bar|hat|tilde|vec)\s*\{([^{}]*)\}")
_FRACTION = re.compile(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
_ROOT = re.compile(r"\\sqrt\s*\{([^{}]*)\}")
_RAISED = re.compile(r"[\^_]\s*\{([^{}]*)\}")
_RAISED_AFTER_COMMAND = re.compile(r"(\\[a-zA-Z]+)[\^_]\s*\{([^{}]*)\}")
_BREAK_BEFORE_COMMAND = re.compile(r"\\\\(?=\\[a-zA-Z])")
_RAISED_ONE = re.compile(r"[\^_]\s*([^\s{}\\^_])")
_SYMBOLS = {
    "circ": "°", "degree": "°", "times": "×", "prime": "′", "cdot": "·", "pm": "±", "div": "÷", "leq": "≤", "le": "≤",
    "geq": "≥", "ge": "≥", "neq": "≠", "approx": "≈", "sim": "~", "ldots": "…", "cdots": "…", "dots": "…",
    "rightarrow": "→", "to": "→", "leftarrow": "←", "bullet": "•", "ast": "*", "star": "*", "S": "§", "pounds": "£",
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "theta": "θ", "lambda": "λ", "mu": "μ",
    "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "phi": "φ", "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
    "quad": " ", "qquad": " ", "left": "", "right": "", "displaystyle": "", "scriptstyle": "", "limits": "",
}
_COMMAND = re.compile(r"\\([a-zA-Z]+)")
# \begin{array}{ll} ... \end{array}: the marks go, what stands between them stays
_ENVIRONMENT = re.compile(r"\\begin\s*\{[a-zA-Z*]{1,20}\}(?:[ \t]*\{[lcr| ]{1,40}\})?|\\end\s*\{[a-zA-Z*]{1,20}\}")
_ESCAPED = re.compile(r"\\([%$&#_{}])")
_SPACING = re.compile(r"\\[,;:! ]")
# a formula: $$...$$ over a few lines, or $...$ on one line. Taken as a formula only when it
# holds TeX (a price like $5 does not).
_BLOCK = re.compile(r"\$\$(.{1,2000}?)\$\$", re.DOTALL)
_FORMULA = re.compile(r"\$([^$\n]{1,400}?)\$")
_HOLDS_TEX = re.compile(r"[\\^{}]|_\{")

# backslash-t written out, unless it starts a TeX command (\text, \times, \theta, \tau, \to, \tilde)
_WRITTEN_TAB = re.compile(r"\\t(?!(?:ext[a-z]*|imes|heta|au|o|ilde|frac)(?![a-zA-Z]))")
# the lines the chunking step appended, by the labels it writes (philatelic_chunk_logic.py), and its one
# fixed sentence; a line is taken only when it starts with the label
_APPENDED = re.compile(
    r"(?m)^[ \t]*(?:(?:Catálogos internacionales|Fechas|Valores faciales|Especificaciones técnicas|Condición"
    r"|Variedades EFO|Significado histórico|Colores|Diseños|Precios):[^\n]*|Período Guanacaste 1885-1891\.[ \t]*)(?:\n|$)")
_IMAGE = re.compile(r"!\[[^\]\n]*\]\((?:[^()\n]|\([^()\n]*\))*\)")
_BREAK_TAG = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TOOL_TAG = re.compile(r"</?(?:underline|smiles|u|sub|sup)>", re.IGNORECASE)
_BOLD = re.compile(r"\*\*(?=\S)([^*\n]{1,300}?)(?<=\S)\*\*")
_HEADING = re.compile(r"(?m)^[ \t]*#{1,6}[ \t]+")
_MARKDOWN_ESCAPE = re.compile(r"\\([_*#\[\]()])")


def _unwrap(text: str) -> str:
    r"""\text{th} -> th, \frac{1}{2} -> 1/2: forms that only TeX writes, wherever they are."""
    for _ in range(4):                               # wrappers can sit inside one another
        before = text
        text = _WRAPPERS.sub(r"\1", text)
        text = _FRACTION.sub(r"\1/\2", text)
        text = _ROOT.sub(r"√\1", text)
        if text == before:
            break
    return _ENVIRONMENT.sub("", text)


def _lower(text: str) -> str:
    """^{o} -> o and _{2} -> 2. After a command a space is kept, so the two do not run into one name."""
    for _ in range(3):
        text = _RAISED.sub(r"\1", _RAISED_AFTER_COMMAND.sub(r"\1 \2", text))
    return text


def _formula(match: re.Match) -> str:
    inner = match.group(1)
    if not _HOLDS_TEX.search(inner):
        return match.group(0)
    inner = _unwrap(inner.replace("\\\\", " "))      # a TeX line break (two backslashes) first: \\\text{word} is not \word
    inner = _ESCAPED.sub(r"\1", inner)
    inner = _SPACING.sub(" ", inner)
    # commands first, raised parts after: \sum_{all} must not become the unknown command \sumall
    inner = _COMMAND.sub(lambda m: _SYMBOLS.get(m.group(1), ""), inner)      # inside a formula an unknown command is dropped
    inner = _RAISED_ONE.sub(r"\1", _lower(inner))
    return inner.replace("{", "").replace("}", "")


def _loose_tex(text: str) -> str:
    """TeX outside any $...$ (a formula whose marks were lost): unwrap it, name the symbols, leave the rest."""
    text = _BREAK_BEFORE_COMMAND.sub(" ", text)
    text = _COMMAND.sub(lambda m: _SYMBOLS.get(m.group(1), m.group(0)), _unwrap(text))
    return _unwrap(_lower(text))


# A reading loop: LOOP_WINDOW words in a row that are made of at most LOOP_WORDS different words.
# Prose never does that; a column of figures can, so only words made of letters count.
LOOP_WINDOW, LOOP_WORDS, LOOP_MARK = 20, 3, "[…]"
LOOP_MARK_AFTER = 5            # this many repeats in a row are marked; fewer are dropped without a mark
_WORD = re.compile(r"\S+")


def _cut_loops(text: str) -> str:
    """Show a reading loop once. Inside the loop each different word is kept the first time it
    comes, in its order, and a stretch of repeats becomes ``[…]``; so no word disappears, only
    its repeats. The words before and after the loop are not touched."""
    tokens = list(_WORD.finditer(text))
    if len(tokens) < LOOP_WINDOW:
        return text
    keys = [m.group(0).strip(".,;:!?()[]\"'«»“”-–—").lower() for m in tokens]
    lettered = [k.isalpha() for k in keys]
    inside = [False] * len(tokens)
    for i in range(len(tokens) - LOOP_WINDOW + 1):
        if all(lettered[i:i + LOOP_WINDOW]) and len(set(keys[i:i + LOOP_WINDOW])) <= LOOP_WORDS:
            inside[i:i + LOOP_WINDOW] = [True] * LOOP_WINDOW
    if not any(inside):
        return text
    out, at, i = [], 0, 0
    while i < len(tokens):
        if not inside[i]:
            i += 1
            continue
        j = i
        while j < len(tokens) and inside[j]:
            j += 1
        seen, kept, repeats = set(), [], 0
        for n in range(i, j):
            if keys[n] in seen:
                repeats += 1
                continue
            if repeats >= LOOP_MARK_AFTER:
                kept.append(LOOP_MARK)
            repeats = 0
            seen.add(keys[n])
            kept.append(tokens[n].group(0))
        if repeats >= LOOP_MARK_AFTER:
            kept.append(LOOP_MARK)
        out.append(text[at:tokens[i].start()] + " ".join(kept))
        at = tokens[j - 1].end()
        i = j
    return "".join(out) + text[at:]


def tidy(text: str) -> str:
    """The stored text without the marks of its extraction. Never raises on odd input."""
    text = text or ""
    if "\\" in text:
        # backslash-n is a line break here, always: the stored text has it in two fragments of three
        text = _WRITTEN_TAB.sub(" ", text.replace("\\n", "\n"))
    text = _BREAK_TAG.sub("\n", text)
    text = _APPENDED.sub("", text)
    text = _IMAGE.sub("", text)
    text = _FORMULA.sub(_formula, _BLOCK.sub(_formula, text))
    if "\\" in text:
        text = _loose_tex(text)
    text = _TOOL_TAG.sub("", text)
    text = _BOLD.sub(r"\1", text)
    text = _HEADING.sub("", text)
    text = _MARKDOWN_ESCAPE.sub(r"\1", text)
    text = _cut_loops(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
