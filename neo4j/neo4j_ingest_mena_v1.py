# This cell writes a ready-to-run Python ingestion script for Neo4j.
# Download it and run it locally in your Mac Jupyter environment (where Neo4j is running).
# You can edit the connection settings at the top of the script.

"""
Ingesta a Neo4j para el catálogo Mena (Costa Rica) a partir de JSON.
- Idempotente (usa MERGE y constraints).
- Pensado para ejecutarse en Jupyter o como script standalone.
- Probado con el JSON "reducido" (primeros issues) y escalable al total.

REQUISITOS en tu Mac (donde corre Neo4j):
    pip install neo4j tqdm

CONFIGURACIÓN:
    - Ajusta NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD.
    - Asegúrate de que tu Neo4j permite la autenticación indicada.
    - Coloca la ruta del JSON en DATA_JSON.

SUGERENCIA:
    - Ejecuta primero con un subconjunto de issues para validar.
"""
import os
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from pathlib import Path
import re

from neo4j import GraphDatabase, Transaction
from tqdm import tqdm

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

# ------------------------
# CONFIGURACIÓN
# ------------------------
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
DATA_JSON      = os.getenv("DATA_JSON",      "/path/to/mena_all_with_raw.json")  # Ajusta la ruta aquí

# Si solo quieres cargar los primeros N issues para pruebas:
LIMIT_ISSUES: Optional[int] = None  # e.g., 2 para solo 2 issues


# ==========================================================
# Helpers Cypher
# ==========================================================

CONSTRAINTS = [
    # Issues
    """CREATE CONSTRAINT issue_id IF NOT EXISTS
       FOR (i:Issue) REQUIRE i.issue_id IS UNIQUE""",

    # Stamps
    """CREATE CONSTRAINT stamp_key IF NOT EXISTS
       FOR (s:Stamp) REQUIRE (s.issue_id, s.catalog_no) IS UNIQUE""",

    # Varieties
    """CREATE CONSTRAINT variety_key IF NOT EXISTS
       FOR (v:Variety) REQUIRE (v.issue_id, v.base_catalog_no, v.suffix) IS UNIQUE""",

    # Proofs: code único (para DP/PP/CP/variants)
    """CREATE CONSTRAINT proof_code IF NOT EXISTS
       FOR (p:Proof) REQUIRE p.code IS UNIQUE""",

    # ProductionOrder
    """CREATE CONSTRAINT po_key IF NOT EXISTS
       FOR (po:ProductionOrder) REQUIRE (po.issue_id, po.date) IS UNIQUE""",

    # Quantity (incluye printings y remainders con po_key de texto)
    """CREATE CONSTRAINT qty_key IF NOT EXISTS
       FOR (q:Quantity) REQUIRE q.po_key IS UNIQUE""",

    # Actos legales
    """CREATE CONSTRAINT legal_act_key IF NOT EXISTS
       FOR (a:LegalAct) REQUIRE (a.type, a.id, a.date) IS UNIQUE""",

    # Personas y impresoras
    """CREATE CONSTRAINT person_name IF NOT EXISTS
       FOR (p:Person) REQUIRE p.name IS UNIQUE""",
    """CREATE CONSTRAINT printer_name IF NOT EXISTS
       FOR (p:Printer) REQUIRE p.name IS UNIQUE""",
    """CREATE CONSTRAINT org_name IF NOT EXISTS
       FOR (o:Organization) REQUIRE o.name IS UNIQUE""",
    """CREATE CONSTRAINT biblio_key IF NOT EXISTS
       FOR (b:BiblioRef) REQUIRE b.key IS UNIQUE""",

    # Placas
    """CREATE CONSTRAINT plate_key IF NOT EXISTS
       FOR (pl:Plate) REQUIRE (pl.issue_id, pl.denomination, pl.no) IS UNIQUE"""
]


def run_constraints(tx: Transaction):
    for c in CONSTRAINTS:
        tx.run(c)


def parse_position_to_int(pos: Any) -> Optional[int]:
    """Extracts an integer position from inputs like 'pos 87' or 87."""
    if pos is None:
        return None
    if isinstance(pos, int):
        return pos
    if isinstance(pos, str):
        match = re.search(r"\d+", pos)
        if match:
            return int(match.group())
    return None


def normalized_proof_code(raw_code: Optional[str], issue_id: str, proof_type: str, idx: int) -> str:
    """Guarantee a non-empty proof code to satisfy uniqueness constraints."""
    if raw_code:
        trimmed = str(raw_code).strip()
        if trimmed:
            return trimmed
    return f"__AUTO__|{issue_id}|{proof_type}|{idx}"


# ==========================================================
# Helper functions for provenance classification
# ==========================================================
def strip_ex_prefix(name: str) -> tuple[str, bool]:
    """Return (clean_name, had_ex_prefix). Handles 'ex-' / 'ex ' prefixes."""
    if not isinstance(name, str):
        return str(name), False
    t = name.strip()
    m = re.match(r"(?i)^ex[-\s]+(.+)$", t)
    if m:
        return m.group(1).strip(), True
    return t, False

def classify_provenance(token: str) -> str:
    """
    Classify a provenance token into 'Person', 'Organization', or 'BiblioRef'.
    Heuristics:
      - Starts with 'Ref' → BiblioRef
      - Contains org keywords (bank, company, institute, society, etc.) → Organization
      - If looks like a personal name (2–4 capitalized words, no digits) → Person
      - Otherwise → Organization
    """
    if not isinstance(token, str):
        return 'Organization'
    t = token.strip()
    # Bibliographic reference
    if re.match(r"(?i)^ref\b|^ref\.\b", t):
        return 'BiblioRef'
    # Or if it contains digits and a comma, likely a citation
    if re.search(r"\d", t) and ("," in t or "#" in t):
        # e.g., 'CRFil 47, 1962' or 'Decree #2'
        # Only treat as BiblioRef when it didn't come via LegalAct pipeline
        if t.lower().startswith('crfil') or 'crfil' in t.lower():
            return 'BiblioRef'
    org_keywords = (
        'bank', 'note', 'co', 'company', 'press', 'imprenta', 'society', 'sociedad',
        'instituto', 'institute', 'university', 'universidad', 'ministerio', 'correos',
        'postal', 'club', 'museum', 'museo', 'office', 'department', 'dirección',
        'gazette', 'gaceta', 'filatelic', 'filatélica'
    )
    low = t.lower()
    if any(k in low for k in org_keywords):
        return 'Organization'
    # Likely a person: 2-4 capitalized words, no digits
    if not re.search(r"\d", t):
        words = re.split(r"[\s\u00A0]+", t)
        if 2 <= len(words) <= 4 and all(re.match(r"^[A-ZÁÉÍÓÚÑ][\w\.'-]*$", w) for w in words):
            return 'Person'
    return 'Organization'

# ==========================================================
# Helper: Heuristic to check if a string looks like a person name
# ==========================================================
def looks_like_person_name(token: str) -> bool:
    """Heuristic: true if token looks like a personal name (2–4 capitalized words, no digits)."""
    if not isinstance(token, str):
        return False
    t = token.strip()
    # Exclude anything with digits or known session markers
    if re.search(r"\d", t):
        return False
    if re.search(r"(?i)\b(sesion|sesión|session)\b", t):
        return False
    words = re.split(r"[\s\u00A0]+", t)
    return 2 <= len(words) <= 4 and all(re.match(r"^[A-ZÁÉÍÓÚÑ][\w\.'-]*$", w) for w in words)


# ==========================================================
# Funciones de ingesta
# ==========================================================

def ingest_issue(tx: Transaction, issue: Dict[str, Any]):
    i = issue.get("issue_data", {})
    issue_dates = i.get("issue_dates")
    issue_dates_prop = json.dumps(issue_dates, ensure_ascii=False) if issue_dates else None
    iss_props = {
        "issue_id": i.get("issue_id"),
        "section": i.get("section"),
        "title": i.get("title"),
        "country": i.get("country"),
        "perforation": i.get("perforation"),
        "plain_raw_text": i.get("plain_raw_text"),
        "pictures_raw_text": i.get("pictures_raw_text"),
        # Neo4j solo acepta primitivos; almacenamos el mapa como JSON.
        "issue_dates": issue_dates_prop,
        "source": "Mena JSON",
    }
    tx.run(
        """
        MERGE (iss:Issue {issue_id:$issue_id})
        ON CREATE SET iss.section=$section, iss.title=$title, iss.country=$country,
                      iss.perforation=$perforation, iss.issue_dates=$issue_dates,
                      iss.plain_raw_text=$plain_raw_text,
                      iss.pictures_raw_text=$pictures_raw_text,
                      iss.source=$source, iss.ingested_at=date()
        """,
        **iss_props
    )

    # Printer
    printing = i.get("printing", {})
    printer = printing.get("printer")
    if printer:
        tx.run(
            """
            MERGE (iss:Issue {issue_id:$issue_id})
            MERGE (pr:Printer {name:$printer})
            MERGE (iss)-[:PRINTED_BY]->(pr)
            """,
            issue_id=i.get("issue_id"), printer=printer
        )

    # Legal acts (legal_basis) + officials as Person (Issue AUTHORIZED_BY LegalAct)
    for lb in i.get("legal_basis", []) or []:
        doc_date = lb.get("date")
        if not doc_date:
            id_part = lb.get("id") or "sin-id"
            type_part = lb.get("type") or "sin-tipo"
            doc_date = f"__NO_DATE__|{id_part}|{type_part}"
        ids_list = [x for x in (lb.get("ids") or []) if isinstance(x, str) and x.strip()]
        tx.run(
            """
            MERGE (d:LegalAct {type:$type, id:$id, date:$date})
            ON CREATE SET d.ids = $ids
            MERGE (iss:Issue {issue_id:$issue_id})
            MERGE (iss)-[:AUTHORIZED_BY]->(d)
            """,
            type=lb.get("type"), id=lb.get("id"), date=doc_date,
            issue_id=i.get("issue_id"),
            ids=ids_list
        )
        for fn in lb.get("officials", []) or []:
            if looks_like_person_name(fn):
                tx.run(
                    """
                    MERGE (p:Person {name:$name})
                    MERGE (d:LegalAct {type:$type, id:$id, date:$date})
                    MERGE (d)-[:SIGNED_BY]->(p)
                    """,
                    name=fn, type=lb.get("type"), id=lb.get("id"), date=doc_date
                )
            else:
                # If it doesn't look like a person (e.g., 'session #229'), append it to LegalAct.ids instead
                tx.run(
                    """
                    MATCH (d:LegalAct {type:$type, id:$id, date:$date})
                    SET d.ids = CASE WHEN d.ids IS NULL THEN $vals ELSE d.ids + $vals END
                    """,
                    type=lb.get("type"), id=lb.get("id"), date=doc_date, vals=[fn]
                )

    # Plates (por denominación) con notas
    plates = printing.get("plates", {}) or {}
    for denom, info in plates.items():
        notes = info.get("notes")
        for plate_no in info.get("plates", []) or []:
            tx.run(
                """
                MERGE (pl:Plate {issue_id:$issue_id, denomination:$denomination, no:toString($no)})
                ON CREATE SET pl.notes=$notes
                MERGE (iss:Issue {issue_id:$issue_id})
                MERGE (iss)-[:HAS_PLATE]->(pl)
                """,
                issue_id=i.get("issue_id"), denomination=denom, no=plate_no, notes=notes
            )


def ingest_stamps(tx: Transaction, issue: Dict[str, Any]):
    issue_id = issue.get("issue_data", {}).get("issue_id")
    for s in issue.get("stamps", []) or []:
        tx.run(
            """
            MERGE (iss:Issue {issue_id:$issue_id})
            MERGE (st:Stamp {issue_id:$issue_id, catalog_no:$catalog_no})
            ON CREATE SET st.denomination_value = $den_val,
                          st.denomination_unit  = $den_unit,
                          st.color              = $color,
                          st.perforation        = $perf,
                          st.watermark          = $wm,
                          st.quantity_reported  = $qty,
                          st.status             = $status,
                          st.notes              = $notes,
                          st.base_stamp_ref     = $base_ref
            MERGE (iss)-[:HAS_STAMP]->(st)
            """,
            issue_id=s.get("issue_id") or issue_id,
            catalog_no=s.get("catalog_no"),
            den_val=(s.get("denomination") or {}).get("value"),
            den_unit=(s.get("denomination") or {}).get("unit"),
            color=s.get("color"),
            perf=s.get("perforation"),
            wm=s.get("watermark"),
            qty=s.get("quantity_reported"),
            status=s.get("status"),
            notes=s.get("notes"),
            base_ref=s.get("base_stamp_ref")
        )

        # Vincular a Plate si existe prop "plate"
        if s.get("plate") is not None:
            tx.run(
                """
                MATCH (st:Stamp {issue_id:$issue_id, catalog_no:$catalog_no})
                MATCH (pl:Plate {issue_id:$issue_id, no:toString($plate)})
                MERGE (st)-[:USES_PLATE]->(pl)
                """,
                issue_id=s.get("issue_id") or issue_id,
                catalog_no=s.get("catalog_no"),
                plate=s.get("plate")
            )

        # Overprint/surcharge relaciones (derivados sobre un base)
        op = s.get("overprint") or {}
        base_ref = s.get("base_stamp_ref")
        if op.get("present") and base_ref:
            rel_props = {
                "type": op.get("type"),
                "surcharged_value": (op.get("surcharge_denomination") or {}).get("value"),
                "surcharged_unit": (op.get("surcharge_denomination") or {}).get("unit"),
                "on_value": (op.get("on_denomination") or {}).get("value"),
                "on_unit": (op.get("on_denomination") or {}).get("unit"),
            }
            rel_props = {k: v for k, v in rel_props.items() if v is not None}
            tx.run(
                """
                MATCH (derived:Stamp {issue_id:$issue_id, catalog_no:$derived_no})
                MATCH (base:Stamp   {issue_id:$base_issue_id, catalog_no:$base_no})
                MERGE (derived)-[rel:OVERPRINTED_ON]->(base)
                SET rel += $rel_props
                """,
                issue_id=s.get("issue_id") or issue_id,
                derived_no=s.get("catalog_no"),
                base_issue_id="CR-1863-FIRST-ISSUE",  # para el sample, ajustar si hay otros casos
                base_no=base_ref,
                rel_props=rel_props or {}
            )


def ingest_varieties(tx: Transaction, issue: Dict[str, Any]):
    i_id = issue.get("issue_data", {}).get("issue_id")
    for v in issue.get("varieties", []) or []:
        tx.run(
            """
            MATCH (st:Stamp {issue_id:$issue_id, catalog_no:$base_no})
            MERGE (var:Variety {issue_id:$issue_id, base_catalog_no:$base_no, suffix:$suffix})
            ON CREATE SET var.type=$type, var.description=$desc, var.position=$pos, var.plate=$plate
            MERGE (st)-[:HAS_VARIETY]->(var)
            """,
            issue_id=i_id,
            base_no=v.get("base_catalog_no"),
            suffix=v.get("suffix"),
            type=v.get("type"),
            desc=v.get("description"),
            pos=v.get("position"),
            plate=v.get("plate")
        )

        # Si hay posición del tipo "pos 87" y sabemos la placa, opcional: crear PlatePosition
        pos_raw = v.get("position")
        plate = v.get("plate")
        pos_value = parse_position_to_int(pos_raw)
        if pos_value is not None and plate is not None:
            # Intento heurístico de denominación desde el sello base (para mapear a Plate)
            base_no = v.get("base_catalog_no")
            tx.run(
                """
                MATCH (st:Stamp {issue_id:$issue_id, catalog_no:$base_no})
                WITH st
                // buscamos una Plate por issue y número (denominación puede ser ambigua; si tienes la denom exacta, cámbiala aquí)
                MATCH (pl:Plate {issue_id:$issue_id, no:toString($plate)})
                MERGE (plpos:PlatePosition {plate_element_id:elementId(pl), pos:$pos})
                WITH plpos
                MATCH (var:Variety {issue_id:$issue_id, base_catalog_no:$base_no, suffix:$suffix})
                MERGE (var)-[:AT_POSITION]->(plpos)
                """,
                issue_id=i_id, base_no=base_no, plate=plate, pos=pos_value, suffix=v.get("suffix")
            )


def ingest_proofs(tx: Transaction, issue: Dict[str, Any]):
    i_id = issue.get("issue_data", {}).get("issue_id")
    proofs = issue.get("proofs") or {}

    # Die proofs
    for idx, dp in enumerate(proofs.get("die_proofs", []) or [], start=1):
        code = normalized_proof_code(dp.get("code"), i_id, "die_proof", idx)
        tx.run(
            """
            MERGE (p:Proof:DieProof {code:$code})
            ON CREATE SET p.denomination=$denomination, p.color=$color, p.die_no=$die_no,
                          p.substrate=$substrate, p.finish=$finish
            MERGE (iss:Issue {issue_id:$issue_id})
            MERGE (iss)-[:HAS_PROOF]->(p)
            """,
            code=code, denomination=dp.get("denomination"), color=dp.get("color"),
            die_no=dp.get("die_no"), substrate=dp.get("substrate"), finish=dp.get("finish"),
            issue_id=i_id
        )

    # Plate proofs (grupos con items/variants)
    plate_idx = 1
    for group in proofs.get("plate_proofs", []) or []:
        g_code = group.get("code")
        g_note = group.get("note")
        for it in group.get("items", []) or []:
            code = normalized_proof_code(it.get("variant") or g_code, i_id, "plate_proof", plate_idx)
            plate_idx += 1
            tx.run(
                """
                MERGE (p:Proof:PlateProof {code:$code})
                ON CREATE SET p.group_code=$group_code, p.note=$note,
                              p.denomination=$denomination, p.color=$color, p.plate=$plate
                MERGE (iss:Issue {issue_id:$issue_id})
                MERGE (iss)-[:HAS_PROOF]->(p)
                """,
                code=code, group_code=g_code, note=g_note, denomination=it.get("denomination"),
                color=it.get("color"), plate=it.get("plate"), issue_id=i_id
            )

    # Color proofs
    for idx, cp in enumerate(proofs.get("color_proofs", []) or [], start=1):
        fallback = f"{cp.get('denomination','')}_{cp.get('color','')}"
        code = normalized_proof_code(cp.get("code") or fallback, i_id, "color_proof", idx)
        tx.run(
            """
            MERGE (p:Proof:ColorProof {code:$code})
            ON CREATE SET p.denomination=$denomination, p.color=$color, p.notes=$notes
            MERGE (iss:Issue {issue_id:$issue_id})
            MERGE (iss)-[:HAS_PROOF]->(p)
            """,
            code=code, denomination=cp.get("denomination"), color=cp.get("color"),
            notes=cp.get("notes"), issue_id=i_id
        )


def ingest_production_orders(tx: Transaction, issue: Dict[str, Any]):
    i_id = issue.get("issue_data", {}).get("issue_id")
    po = issue.get("production_orders") or {}

    # Printings
    for pr in po.get("printings", []) or []:
        pr_date = pr.get("date")
        if not pr_date:
            continue
        tx.run(
            """
            MERGE (po:ProductionOrder {issue_id:$issue_id, date:$date})
            MERGE (iss:Issue {issue_id:$issue_id})
            MERGE (iss)-[:HAS_PRODUCTION_ORDER]->(po)
            """,
            issue_id=i_id, date=pr_date
        )
        for q in pr.get("quantities", []) or []:
            po_key = f"{i_id}|{pr_date}|{q.get('plate_desc')}"
            tx.run(
                """
                MERGE (qty:Quantity {po_key:$po_key})
                ON CREATE SET qty.plate_desc=$plate_desc, qty.quantity=$quantity
                WITH qty
                MATCH (po:ProductionOrder {issue_id:$issue_id, date:$date})
                MERGE (po)-[:INCLUDES]->(qty)
                """,
                po_key=po_key, plate_desc=q.get("plate_desc"), quantity=q.get("quantity"),
                issue_id=i_id, date=pr_date
            )

    # Remainders
    rem = po.get("remainders") or {}
    if rem.get("date"):
        tx.run(
            """
            MERGE (ev:RemaindersEvent {issue_id:$issue_id, date:$date})
            ON CREATE SET ev.note=$note
            MERGE (iss:Issue {issue_id:$issue_id})
            MERGE (iss)-[:HAS_REMAINDERS]->(ev)
            """,
            issue_id=i_id, date=rem.get("date"), note=rem.get("note")
        )
        # comprador: si aparece en nota podemos crear Person, pero aquí va fijo si está explícito en nota
        if "Jaime Ross" in (rem.get("note") or ""):
            tx.run(
                """
                MERGE (p:Person {name:"Jaime Ross"})
                WITH p
                MATCH (ev:RemaindersEvent {issue_id:$issue_id, date:$date})
                MERGE (ev)-[:SOLD_TO]->(p)
                """,
                issue_id=i_id, date=rem.get("date")
            )
        for q in rem.get("quantities", []) or []:
            po_key = f"REM|{i_id}|{rem.get('date')}|{q.get('plate_desc')}"
            tx.run(
                """
                MERGE (qty:Quantity {po_key:$po_key})
                ON CREATE SET qty.plate_desc=$plate_desc, qty.quantity=$quantity
                WITH qty
                MATCH (ev:RemaindersEvent {issue_id:$issue_id, date:$date})
                MERGE (ev)-[:INCLUDES]->(qty)
                """,
                po_key=po_key, plate_desc=q.get("plate_desc"), quantity=q.get("quantity"),
                issue_id=i_id, date=rem.get("date")
            )


def ingest_specimens_essays(tx: Transaction, issue: Dict[str, Any]):
    i_id = issue.get("issue_data", {}).get("issue_id")

    # Essays
    for e in issue.get("essays", []) or []:
        tx.run(
            """
            MERGE (es:Essay {code:$code})
            ON CREATE SET es.medium=$medium, es.paper=$paper, es.denomination=$denomination, es.notes=$notes
            MERGE (iss:Issue {issue_id:$issue_id})
            MERGE (iss)-[:HAS_ESSAY]->(es)
            """,
            code=e.get("code"), medium=e.get("medium"), paper=e.get("paper"),
            denomination=e.get("denomination"), notes=e.get("notes"), issue_id=i_id
        )
        for prov in e.get("provenance", []) or []:
            cleaned, had_ex = strip_ex_prefix(prov)
            kind = classify_provenance(cleaned)
            if kind == 'BiblioRef':
                # Store bibliographic citations as separate nodes
                key = re.sub(r"(?i)^ref\.?\s*", "", cleaned).strip() or cleaned
                tx.run(
                    """
                    MERGE (b:BiblioRef {key:$key})
                    WITH b
                    MATCH (es:Essay {code:$code})
                    MERGE (es)-[:CITED_IN]->(b)
                    """,
                    key=key, code=e.get("code")
                )
            elif kind == 'Person':
                if had_ex:
                    tx.run(
                        """
                        MERGE (p:Person {name:$name})
                        WITH p
                        MATCH (es:Essay {code:$code})
                        MERGE (es)-[:EX_PROVENANCE]->(p)
                        """,
                        name=cleaned, code=e.get("code")
                    )
                else:
                    tx.run(
                        """
                        MERGE (p:Person {name:$name})
                        WITH p
                        MATCH (es:Essay {code:$code})
                        MERGE (es)-[:PROVENANCE]->(p)
                        """,
                        name=cleaned, code=e.get("code")
                    )
            else:
                # Organization
                if had_ex:
                    tx.run(
                        """
                        MERGE (o:Organization {name:$name})
                        WITH o
                        MATCH (es:Essay {code:$code})
                        MERGE (es)-[:EX_PROVENANCE]->(o)
                        """,
                        name=cleaned, code=e.get("code")
                    )
                else:
                    tx.run(
                        """
                        MERGE (o:Organization {name:$name})
                        WITH o
                        MATCH (es:Essay {code:$code})
                        MERGE (es)-[:PROVENANCE]->(o)
                        """,
                        name=cleaned, code=e.get("code")
                    )

    # Specimens
    for s in issue.get("specimens", []) or []:
        tx.run(
            """
            MERGE (sp:Specimen {code:$code})
            ON CREATE SET sp.applies_to=$applies_to, sp.type=$type, sp.denomination=$denomination,
                          sp.base_color=$base_color, sp.overprint_color=$overprint_color, sp.notes=$notes
            MERGE (iss:Issue {issue_id:$issue_id})
            MERGE (iss)-[:HAS_SPECIMEN]->(sp)
            """,
            code=s.get("code"), applies_to=s.get("applies_to"), type=s.get("type"),
            denomination=s.get("denomination"), base_color=s.get("base_color"),
            overprint_color=s.get("overprint_color"), notes=s.get("notes"),
            issue_id=i_id
        )


# ==========================================================
# Rutina principal
# ==========================================================

def load_json(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list), "El JSON raíz debe ser una lista de issues"
    return data


def ingest_all(issues: List[Dict[str, Any]]):
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver, driver.session() as session:
        # Constraints
        session.execute_write(run_constraints)

        # Ingesta por issue
        iterable = issues if LIMIT_ISSUES is None else issues[:LIMIT_ISSUES]
        for issue in tqdm(iterable, desc="Ingestando issues"):
            session.execute_write(ingest_issue, issue)
            session.execute_write(ingest_stamps, issue)
            session.execute_write(ingest_varieties, issue)
            session.execute_write(ingest_proofs, issue)
            session.execute_write(ingest_production_orders, issue)
            session.execute_write(ingest_specimens_essays, issue)


def main():
    data_path = Path(DATA_JSON)
    if not data_path.exists():
        raise FileNotFoundError(f"No se encuentra el archivo JSON en: {data_path.resolve()}")
    issues = load_json(str(data_path))
    print(f"Total de issues en JSON: {len(issues)}")
    ingest_all(issues)
    print("✅ Ingesta completada.")


if __name__ == "__main__":
    main()
