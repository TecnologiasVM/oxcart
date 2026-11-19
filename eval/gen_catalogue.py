"""Part (a) of the test set: questions whose answer is a catalogue fact in the graph.

    python -m eval.gen_catalogue select     # draw the facts from the snapshot (seeded)
    python -m eval.gen_catalogue build      # write the questions, Spanish and English

`select` reads local-data/eval/catalogue_snapshot.json (python -m eval.snapshot_graph) and
writes the drawn facts. `build` needs one hand-written Spanish name per drawn issue
(titles in the catalogue are English) and writes two questions per fact.

40 facts over seven kinds, each from a different issue, spread over four periods.
Every gold value is read from the snapshot and can be re-read from the graph with the
stored Cypher, so the answers are checked automatically.
"""

from __future__ import annotations

import collections
import json
import random
import re
import sys
from pathlib import Path

from eval import stores

DATA = stores.REPO / "local-data" / "eval"
SNAPSHOT = DATA / "catalogue_snapshot.json"
SELECTION = DATA / "catalogue_selection.json"
TITLES_ES = stores.data_file("catalogue_titles_es.json")
OUT = DATA / "questions_catalogue.jsonl"

SEED = 1863
PERIODS = [("to 1900", 0, 1900), ("1901-1950", 1901, 1950), ("1951-2000", 1951, 2000), ("2001-2025", 2001, 2100)]
KINDS = {"date_on_sale": 7, "stamp_colour": 7, "stamp_quantity": 7, "printer": 6, "legal_act": 6,
         "varieties": 5, "scott_equivalent": 2}
GENERIC_TITLE = re.compile(
    r"(?i)^\s*(((definitive|regular|airmail|air mail|official)\s+)?(issue|issues|surcharges?|overprints?)(\s+of)?\s+\d{4}"
    r"|\d{4}(-\d{2,4})?\s+issue\s*$)")
PLAIN_NUMBER = re.compile(r"^[A-Z]{0,3}\d+[A-Za-z]?$")  # one stamp, not a range such as "73/77"
MONTH = re.compile(r"(?i)\b(january|february|march|april|may|june|july|august|september|october|november|december)\b")
# The catalogue's colour field sometimes holds a design note ("with flute player"); those are not colour facts.
NOT_A_COLOUR = re.compile(r"(?i)\b(with|without|and the|portrait|view|map)\b")

UNITS_EN = {"c": ("céntimo", "céntimos"), "C": ("colón", "colones"), "P": ("peso", "pesos"),
            "real": ("real", "reales"), "reales": ("real", "reales")}

CYPHER = {
    "date_on_sale": "MATCH (i:Issue {issue_id:$issue_id}) RETURN i.issue_dates AS value",
    "stamp_colour": "MATCH (:Issue {issue_id:$issue_id})-[:HAS_STAMP]->(s:Stamp {catalog_no:$catalog_no}) RETURN s.color AS value",
    "stamp_quantity": "MATCH (:Issue {issue_id:$issue_id})-[:HAS_STAMP]->(s:Stamp {catalog_no:$catalog_no}) RETURN s.quantity_reported AS value",
    "printer": "MATCH (:Issue {issue_id:$issue_id})-[:PRINTED_BY]->(p:Printer) RETURN p.name AS value ORDER BY value",
    "legal_act": "MATCH (:Issue {issue_id:$issue_id})-[:AUTHORIZED_BY]->(a:LegalAct) RETURN a.id AS value, a.date AS date ORDER BY date, value",
    "varieties": "MATCH (:Issue {issue_id:$issue_id})-[:HAS_STAMP]->(s:Stamp {catalog_no:$catalog_no})-[:HAS_VARIETY]->(v:Variety) RETURN v.suffix AS value, v.description AS description ORDER BY value",
    "scott_equivalent": "MATCH (:Issue {issue_id:$issue_id})-[:HAS_STAMP]->(s:Stamp {catalog_no:$catalog_no})-[:EQUIVALENT_TO]->(sc:ScottStamp) RETURN sc.scott_number AS value",
}


def year_of(issue_id: str) -> int | None:
    m = re.search(r"(1[89]\d\d|20\d\d)", issue_id or "")
    return int(m.group(1)) if m else None


def period_of(year: int) -> str:
    return next(name for name, lo, hi in PERIODS if lo <= year <= hi)


def money(value, unit: str) -> str | None:
    if value is None or unit not in UNITS_EN or not float(value).is_integer():
        return None  # fractions (the ½ real) read differently in each language: left out of the templates
    number = int(value) if float(value).is_integer() else value
    one, many = UNITS_EN[unit]
    return f"{number} {one if number == 1 else many}"


def eligible(snapshot: dict) -> dict:
    """kind -> period -> list of candidate facts."""
    title_count = collections.Counter(i["title"] for i in snapshot["issues"])
    issues = {}
    for i in snapshot["issues"]:
        y = year_of(i["issue_id"])
        if y and i.get("title") and title_count[i["title"]] == 1 and not GENERIC_TITLE.match(i["title"]):
            issues[i["issue_id"]] = dict(i, year=y)
    stamps = collections.defaultdict(list)
    for s in snapshot["stamps"]:
        stamps[s["issue_id"]].append(s)
    number_count = collections.Counter(s["catalog_no"] for s in snapshot["stamps"])
    printers = collections.defaultdict(list)
    for p in snapshot["printers"]:
        printers[p["issue_id"]].append(p["name"])
    acts = collections.defaultdict(list)
    for a in snapshot["acts"]:
        acts[a["issue_id"]].append(a)
    varieties = collections.defaultdict(list)
    for v in snapshot["varieties"]:
        varieties[(v["issue_id"], v["catalog_no"])].append(v)

    out = {k: collections.defaultdict(list) for k in KINDS}

    def add(kind, issue, **fact):
        out[kind][period_of(issue["year"])].append(
            dict(kind=kind, issue_id=issue["issue_id"], title=issue["title"], year=issue["year"],
                 section=issue.get("section"), **fact))

    for iid, issue in issues.items():
        own = [s for s in stamps.get(iid, []) if s.get("status") == "regular"]
        date = (issue.get("issue_dates") or {}).get("placed_on_sale")
        if date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date)) and not MONTH.search(issue["title"]) \
                and not str(date).endswith("-01-01"):  # January 1 is the catalogue's placeholder for "year only"
            add("date_on_sale", issue, gold=[date])
        faces = collections.Counter((s["value"], s["unit"]) for s in own)
        for s in own:
            face = money(s["value"], s["unit"])
            colour = (s.get("color") or "").strip()
            if (face and faces[(s["value"], s["unit"])] == 1 and colour and len(colour) <= 30
                    and colour.lower() != "multicolor" and not NOT_A_COLOUR.search(colour)):
                add("stamp_colour", issue, catalog_no=s["catalog_no"], face=face, gold=[s["color"]])
                break
        for s in own:
            if (s.get("quantity") and number_count[s["catalog_no"]] == 1 and PLAIN_NUMBER.match(s["catalog_no"])
                    and len(set(x["quantity"] for x in own)) > 1):
                add("stamp_quantity", issue, catalog_no=s["catalog_no"], gold=[s["quantity"]])
                break
        if len(printers.get(iid, [])) == 1 and " or " not in printers[iid][0]:
            add("printer", issue, gold=printers[iid])
        if (len(acts.get(iid, [])) == 1 and acts[iid][0].get("id")
                and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(acts[iid][0].get("date") or ""))
                and not acts[iid][0]["id"].lower().startswith("no ")):
            a = acts[iid][0]
            add("legal_act", issue, act_type=a.get("type"), gold=[a["id"], a["date"]])
        for s in own:
            vs = varieties.get((iid, s["catalog_no"]), [])
            if (2 <= len(vs) <= 6 and number_count[s["catalog_no"]] == 1 and PLAIN_NUMBER.match(s["catalog_no"])
                    and all(v.get("description") for v in vs)):
                add("varieties", issue, catalog_no=s["catalog_no"],
                    gold=[f"{v['suffix']}: {v['description']}" for v in vs])
                break
    by_id = {i["issue_id"]: dict(i, year=year_of(i["issue_id"])) for i in snapshot["issues"]}
    for e in snapshot["scott"]:
        issue = by_id[e["issue_id"]]
        if e["catalog_no"] != str(e["scott_number"]) or e["catalog_no"] == "4":
            out["scott_equivalent"][period_of(issue["year"])].append(
                dict(kind="scott_equivalent", issue_id=e["issue_id"], title=issue["title"], year=issue["year"],
                     section=issue.get("section"), catalog_no=e["catalog_no"], gold=[str(e["scott_number"])]))
    return out


def select() -> None:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    pool = eligible(snapshot)
    rng = random.Random(SEED)
    used: set[str] = set()
    facts = []
    order = [p[0] for p in PERIODS]
    for kind, wanted in KINDS.items():
        for candidates in pool[kind].values():
            candidates.sort(key=lambda f: (f["issue_id"], f.get("catalog_no", "")))
            rng.shuffle(candidates)
        got, turn = 0, 0
        while got < wanted and any(pool[kind][p] for p in order):
            period = order[turn % len(order)]
            turn += 1
            while pool[kind][period]:
                fact = pool[kind][period].pop()
                if fact["issue_id"] in used and kind != "scott_equivalent":
                    continue
                used.add(fact["issue_id"])
                fact["period"] = period
                facts.append(fact)
                got += 1
                break
        if got < wanted:
            print(f"only {got} of {wanted} facts available for {kind}")
    for n, fact in enumerate(facts, start=1):
        fact["id"] = f"cat-{n:03d}"
    SELECTION.write_text(json.dumps({"seed": SEED, "snapshot_date": snapshot.get("snapshot_date"), "facts": facts},
                                    ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(facts), "facts;", len({f["issue_id"] for f in facts}), "issues")
    print("by kind:", dict(collections.Counter(f["kind"] for f in facts)))
    print("by period:", dict(collections.Counter(f["period"] for f in facts)))
    print("by section:", dict(collections.Counter(f["section"] for f in facts)))
    for f in facts:
        print(f"  {f['id']} {f['kind']:<16} {f['year']} | {f['title']} | {f.get('catalog_no', '')} {f.get('face', '')}")


TEMPLATES = {
    "date_on_sale": ("When was the {ref_en} placed on sale?", "¿Cuándo se puso a la venta {ref_es}?"),
    "stamp_colour": ("What colour is the {face} stamp of the {ref_en}?", "¿De qué color es el sello de {face} de {ref_es}?"),
    "stamp_quantity": ("How many copies were printed of the stamp with Mena number {catalog_no}?",
                       "¿Cuántos ejemplares se imprimieron del sello número {catalog_no} del catálogo Mena?"),
    "printer": ("Who printed the {ref_en}?", "¿Quién imprimió {ref_es}?"),
    "legal_act": ("Which legal act authorized the {ref_en}, and on what date?",
                  "¿Qué disposición legal autorizó {ref_es}, y en qué fecha?"),
    "varieties": ("Which varieties does the catalogue list for the stamp with Mena number {catalog_no}?",
                  "¿Qué variedades registra el catálogo para el sello número {catalog_no} del catálogo Mena?"),
    "scott_equivalent": ("What is the Scott number of the stamp with Mena number {catalog_no}, from the {ref_en}?",
                         "¿Cuál es el número Scott del sello número {catalog_no} del catálogo Mena, de {ref_es}?"),
}


def build() -> None:
    selection = json.loads(SELECTION.read_text(encoding="utf-8"))
    titles_es = json.loads(TITLES_ES.read_text(encoding="utf-8")) if TITLES_ES.exists() else {}
    missing = sorted({f["issue_id"] for f in selection["facts"]} - set(titles_es))
    if missing:
        raise SystemExit(f"{len(missing)} issues have no Spanish name in {TITLES_ES.name}: {missing[:5]} ...")
    lines = []
    for f in selection["facts"]:
        title = f["title"]
        ref_en = f"{f['year']} {title}" if not re.search(r"\b(1[89]|20)\d\d\b", title) else title
        values = dict(ref_en=ref_en, ref_es=titles_es[f["issue_id"]], catalog_no=f.get("catalog_no", ""), face=f.get("face", ""))
        params = {"issue_id": f["issue_id"]}
        if f.get("catalog_no"):
            params["catalog_no"] = f["catalog_no"]
        for lang, template in zip(("en", "es"), TEMPLATES[f["kind"]]):
            lines.append({
                "id": f"{f['id']}-{lang}", "pair": f["id"], "lang": lang, "type": "catalogue",
                "question": re.sub(r"\bde el\b", "del", template.format(**values)),
                "issue_ids": [f["issue_id"]], "fact": f["kind"],
                "period": f["period"], "section": f.get("section"),
                "gold": {"cypher": CYPHER[f["kind"]], "params": params, "value": f["gold"],
                         "graph_snapshot": selection.get("snapshot_date")},
            })
    OUT.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines), encoding="utf-8")
    print(len(lines), "questions ->", OUT.relative_to(stores.REPO))


if __name__ == "__main__":
    {"select": select, "build": build}[sys.argv[1] if len(sys.argv) > 1 else "select"]()
