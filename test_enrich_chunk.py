# -*- coding: utf-8 -*-
from typing import Dict, Any, Optional, List
import re
import datetime
import copy
import json

# ====== patrones útiles ======
# PATRÓN MEJORADO: Ahora captura tanto "Scott No. 147" como "Scott 147"
RX_SCOTT = re.compile(r"\bScott(?:'s)?(?:\s+No\.?)?\s*([A-Z]?\d+[A-Za-z\-]*)", re.I)
RX_SCOTT_RANGE = re.compile(r"\bScott(?:'s)?\s+Nos?\.?\s*([\dA-Za-z\-]+)\s*(?:–|-|to)\s*([\dA-Za-z\-]+)", re.I)
RX_M = re.compile(r"\bM\s*(\d+[A-Za-z]?)\b")
RX_A = re.compile(r"\bA\s*(\d+[A-Za-z]?)\b")
RX_GIBBONS = re.compile(r"\bGibbons\b.*?\b([A-Z]?\d+[A-Za-z\-]*)", re.I)
RX_SANABRIA = re.compile(r"\bSan(?:abria)?\b.*?\b([A-Z]?\d+[A-Za-z\-]*)", re.I)

MONTHS_EN = r"January|February|March|April|May|June|July|August|September|October|November|December"
MONTHS_ES = r"Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|Septiembre|Setiembre|Octubre|Noviembre|Diciembre"
RX_DATE_EN = re.compile(rf"\b({MONTHS_EN})\s+\d{{1,2}},\s*\d{{4}}\b", re.I)
RX_DATE_ES = re.compile(rf"\b\d{{1,2}}\s+(?:de\s+)?({MONTHS_ES})\s+\d{{4}}\b", re.I)
RX_YEAR = re.compile(r"\b(18|19|20)\d{2}\b")

RX_PRICE = re.compile(r"(?:US?\$|\$|₡|¢|colones?)\s*[\d.,]+", re.I)
RX_POSTAGE_VAL = re.compile(r"\b(\d+(?:\.\d+)?)\s*(ct|cts|c|C\.|centimos|centavos|colones?|peso?s?)\b", re.I)

RX_DECREE = re.compile(r"\b(LEGISLATIVE\s+)?DECRE(E|TO)\b|DECREE\s+No\.?", re.I)
RX_ISSUE = re.compile(r"\b(First day of issue|primer(?:\s+d[ií]a)?\s+de\s+emisi[oó]n|is authorized)\b", re.I)
RX_AUCTION = re.compile(r"\b(brought|realized|estimate|lot|sale)\b.*?\$[\d.,]+", re.I)

RX_COLOR = re.compile(r"\b(violet|deep blue|orange|green|red|black|coffee|beige|grey|gray|ultramarine|scarlet)\b", re.I)
RX_DESIGN = re.compile(r"\b(Jaguar|Deer|Tapir|Ocelot|Peccary|Cathedral|Map|Columbus)\b", re.I)

MONTH_MAP = {
    "january":"01","february":"02","march":"03","april":"04","may":"05","june":"06",
    "july":"07","august":"08","september":"09","october":"10","november":"11","december":"12",
    "enero":"01","febrero":"02","marzo":"03","abril":"04","mayo":"05","junio":"06",
    "julio":"07","agosto":"08","septiembre":"09","setiembre":"09","octubre":"10","noviembre":"11","diciembre":"12",
}

def _norm_date_string(s: str) -> Optional[str]:
    s = s.strip()
    m_en = RX_DATE_EN.search(s)
    m_es = RX_DATE_ES.search(s)
    if m_en:
        month = m_en.group(1).lower()
        day_m = re.search(r"\b(\d{1,2})\b", s)
        year_m = RX_YEAR.search(s)
        if not (day_m and year_m): return None
        day = day_m.group(1)
        year = year_m.group(0)
        return f"{year}-{MONTH_MAP.get(month,'01')}-{int(day):02d}"
    if m_es:
        month = m_es.group(1).lower()
        day_m = re.search(r"\b(\d{1,2})\b", s)
        year_m = RX_YEAR.search(s)
        if not (day_m and year_m): return None
        day = day_m.group(1)
        year = year_m.group(0)
        return f"{year}-{MONTH_MAP.get(month,'01')}-{int(day):02d}"
    y = RX_YEAR.search(s)
    return y.group(0) if y else None

def _norm_price(s: str) -> Optional[Dict[str, Any]]:
    raw = re.findall(r"[\d.,]+", s)
    if not raw:
        return None
    num = raw[0]
    try:
        if (s.count(",")>0 and s.count(".")==0):
            amount = float(num.replace(".", "").replace(",", "."))
        else:
            amount = float(num.replace(",", ""))
    except:
        return None
    currency = "USD" if "$" in s else ("CRC" if ("₡" in s or "colones" in s.lower()) else "CENT")
    return {"amount": amount, "currency": currency, "raw": s.strip()}

def _dedup_list_dicts(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for it in items:
        key = tuple(sorted((k, str(v)) for k, v in it.items()))
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out

# --- Patrones de variedades filatélicas ---
RX_OVERPRINT_INVERTED = re.compile(
    r"\b(sobrecarga(?:s)?\s+invertid[ao]s?|invertid[ao]\b|al\s+rev[eé]s|inverted\s+overprint|overprint\s+inverted|upside[- ]down\s+overprint)\b",
    re.I
)
RX_OVERPRINT_DOUBLE = re.compile(r"\b(sobrecarga(?:s)?\s+doble?s?|double\s+overprint)\b", re.I)
RX_OVERPRINT_TEXT = re.compile(r"\b(Lindbergh|Guanacaste|CORREOS|OFICIAL|Renta\s+Postales)\b", re.I)

RX_COLOR_ERROR = re.compile(
    r"\b(error(?:es)?\s+de\s+color|color\s+incorrecto|color\s+equivocado|desplazamiento\s+de\s+color|falta\s+de\s+color|"
    r"color\s+shift|missing\s+color|wrong\s+color|double\s+impression)\b",
    re.I
)
RX_COLOR_SHIFT = re.compile(r"\b(desplazamiento\s+de\s+color|color\s+shift)\b", re.I)
RX_MISSING_COLOR = re.compile(r"\b(falta\s+de\s+color|missing\s+color)\b", re.I)
RX_WRONG_COLOR = re.compile(r"\b(color\s+incorrecto|color\s+equivocado|wrong\s+color)\b", re.I)

RX_MIRROR = re.compile(
    r"\b(espejo|impresi[oó]n\s+espejo|impresi[oó]n\s+en\s+espejo|mirror\s+print|mirror\s+image|reversed\s+impression)\b",
    re.I
)
RX_REVERSED = re.compile(r"\b(reversed)\b", re.I)

def _add_variety(ents: dict, data: Dict[str, Any]):
    arr = ents.setdefault("varieties", [])
    arr.append(data)

def tag_varieties_filatelia(chunk: dict) -> dict:
    text = chunk.get("text","") or ""
    md = chunk.setdefault("metadata", {})
    ents = md.setdefault("entities", {})

    # --- OVERPRINTS ---
    if RX_OVERPRINT_INVERTED.search(text):
        ents.setdefault("overprint", {})
        ents["overprint"]["orientation"] = "inverted"
        mtxt = RX_OVERPRINT_TEXT.search(text)
        if mtxt:
            ents["overprint"]["text"] = mtxt.group(1)
        _add_variety(
            ents,
            {
                "class":"overprint",
                "subtype":"inverted",
                "label":"sobrecarga invertida",
                "details": text[:240],
                "confidence": 0.7
            }
        )
        if (chunk.get("chunk_type") or "").lower() in {"text","paragraph",""}:
            chunk["chunk_type"] = "overprint"

    if RX_OVERPRINT_DOUBLE.search(text):
        ents.setdefault("overprint", {})
        ents["overprint"]["count"] = max(2, ents["overprint"].get("count", 0))
        _add_variety(
            ents,
            {
                "class":"overprint",
                "subtype":"double_overprint",
                "label":"doble sobrecarga",
                "details": text[:240],
                "confidence": 0.6
            }
        )

    # --- COLOR ERRORS ---
    if RX_COLOR_ERROR.search(text):
        if RX_COLOR_SHIFT.search(text): subtype = "color_shift"
        elif RX_MISSING_COLOR.search(text): subtype = "missing_color"
        elif RX_WRONG_COLOR.search(text): subtype = "wrong_color"
        else: subtype = "unspecified"
        _add_variety(
            ents,
            {
                "class":"color_error",
                "subtype": subtype,
                "label":"error de color",
                "details": text[:240],
                "confidence": 0.6
            }
        )

    # --- MIRROR / ESPEJO ---
    if RX_MIRROR.search(text) or RX_REVERSED.search(text):
        is_mirror = RX_MIRROR.search(text) is not None
        _add_variety(
            ents,
            {
                "class":"mirror_print",
                "subtype":"mirror" if is_mirror else "reversed",
                "label":"impresión espejo" if is_mirror else "reversed impression",
                "details": text[:240],
                "confidence": 0.6
            }
        )
        if (chunk.get("chunk_type") or "").lower() in {"text","paragraph",""}:
            chunk["chunk_type"] = "mirror_print"

    # dedupe por si varias reglas disparan similar
    if "varieties" in ents:
        ents["varieties"] = _dedup_list_dicts(ents["varieties"])

    return chunk

TOPIC_PATTERNS = {
  "fauna": r"\b(jaguar|ocelot|manigordo|tapir|cariblanco|fauna|wildlife|animal)\b",
  "aviación": r"\b(aviaci[oó]n|airmail|correo\s+a[eé]reo|av[ií]on|Lindbergh)\b",
  "historia_postal": r"\b(tarifa|franqueo|carta|sobrecargo|postmark|cancelaci[oó]n|paquete|CTO)\b",
  "overprint": r"\b(sobrecarga|overprint|A\s?\d+|Guanacaste|OFICIAL|CORREOS)\b",
  "watermark": r"\b(filigrana|marca\s+de\s+agua|watermark)\b",
  "perforation": r"\b(perf(?:oration)?|perforaci[oó]n|imperf|11(?:\.\d)?(?:\s*[x×]\s*\d{1,2}(?:\.\d)?)?)\b",
  "proofs/essays": r"\b(proof|prueba|essay|color\s+trial|plate\s+proof)\b",
  "flora": r"\b(flora|bot[aá]nica|plantas|coffee|caf[eé])\b",
  "mapas": r"\b(map(?:a)?|map of Costa Rica)\b",
  "personajes": r"\b(Jes[uú]s Jim[eé]nez|Columbus|Orlich|Soley|Moya|Bol[ií]var)\b",
  "arquitectura": r"\b(catedral|edificio|palacio|oficina\s+postal)\b",
  "deportes": r"\b(deporte|ol[ií]mpic[oa]s|sports)\b"
}

TYPE_PATTERNS = {
  "airmail": r"\b(airmail|correo\s+a[eé]reo|^C\d+\b)",
  "postage_due": r"\b(postage\s+due|P1\b|P2\b|insuficiente\s+franqueo)\b",
  "official": r"\b(OFICIAL|official\s+stamps?)\b",
  "revenue": r"\b(revenue|fiscal|renta\s+postales)\b",
  "semipostal": r"\b(semi[- ]?postal|B\d+\b)\b",
  "commemorative": r"\b(comemorativ[oa]|commemorative|aniversario|centenari[oa])\b",
  "definitive": r"\b(definitiv[oa]|definitive)\b",
  "booklet/coil": r"\b(booklet\s+pane|coil)\b"
}

def add_topics(chunk: Dict[str, Any]) -> Dict[str, Any]:
    text = (chunk.get("text") or "").lower()
    md = chunk.setdefault("metadata", {})
    topics = md.setdefault("topics", {"secondary": [], "tags": []})
    hits = []

    # theme/domain
    for k, rx in TOPIC_PATTERNS.items():
        if re.search(rx, text, flags=re.I):
            hits.append(k)

    # type
    types = []
    for k, rx in TYPE_PATTERNS.items():
        if re.search(rx, text, flags=re.I):
            types.append(k)

    # primary/secondary
    if hits:
        topics["primary"] = topics.get("primary", hits[0])
        topics["secondary"] = sorted(list(set(topics.get("secondary", []) + [h for h in hits if h != topics.get("primary")])))
    if types:
        md.setdefault("axes", {})
        md["axes"]["type"] = sorted(list(set(md["axes"].get("type", []) + types)))

    # period (década) si ya tienes years
    years = md.get("entities", {}).get("dates", [])
    if years:
        y = None
        for d in years:
            if len(d) >= 4 and d[:4].isdigit():
                y = int(d[:4]); break
        if y:
            decade = f"{(y//10)*10}s"
            md.setdefault("axes", {})
            md["axes"]["period"] = sorted(list(set(md["axes"].get("period", []) + [decade])))

    # simple confidence
    conf = 0.5 + 0.1*min(len(hits), 3) + 0.05*min(len(types), 2)
    topics["confidence"] = min(0.95, conf)

    # tags libres rápidas
    if "triang" in text: topics["tags"].append("triangular")
    if "watermark" in text or "filigrana" in text: topics["tags"].append("watermark")
    topics["tags"] = sorted(list(set(topics["tags"])))

    return chunk

def enrich_chunk_filatelia(chunk: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enriquecimiento de un chunk estilo OXCART con metadatos filatélicos:
    - catálogos (Scott/M/A/Gibbons/Sanabria)
    - fechas normalizadas (YYYY-MM-DD / YYYY)
    - precios y valores postales
    - colores, diseños
    - upgrade de chunk_type (decree/auction/issue_notice) si aplica
    - variedades (overprint invertida, errores de color, espejo, etc.)
    - topics/facetas (fauna, aviación, type=airmail, period=1960s, ...)
    """
    text = chunk.get("text", "") or ""
    md = chunk.setdefault("metadata", {})
    ents = md.setdefault("entities", {})

    # 1) Catálogos
    sc = RX_SCOTT.findall(text)
    if not sc:
        r = RX_SCOTT_RANGE.search(text)
        if r:
            sc = [f"{r.group(1)}–{r.group(2)}"]
    if sc:
        ents.setdefault("catalog", [])
        for x in sc:
            ents["catalog"].append({"system":"Scott", "number":x})

    for rx, sys in [(RX_M,"M"), (RX_A,"A")]:
        for x in rx.findall(text):
            ents.setdefault("catalog", []).append({"system":sys, "number":x})

    for x in RX_GIBBONS.findall(text):
        ents.setdefault("catalog", []).append({"system":"Gibbons", "number":x})
    for x in RX_SANABRIA.findall(text):
        ents.setdefault("catalog", []).append({"system":"Sanabria", "number":x})

    if "catalog" in ents:
        ents["catalog"] = _dedup_list_dicts(ents["catalog"])

    # 2) Fechas
    dates = []
    # fechas completas EN/ES
    for m in RX_DATE_EN.finditer(text):
        nd = _norm_date_string(m.group(0))
        if nd: dates.append(nd)
    for m in RX_DATE_ES.finditer(text):
        nd = _norm_date_string(m.group(0))
        if nd: dates.append(nd)
    # fallback: solo año
    if not dates:
        y = RX_YEAR.search(text)
        if y: dates.append(y.group(0))
    if dates:
        ents["dates"] = sorted(set(dates))

    # 3) Precios
    prices = []
    for s in RX_PRICE.findall(text):
        p = _norm_price(s)
        if p: prices.append(p)
    if prices:
        ents["prices"] = prices

    # 4) Valores postales (face value)
    vals = []
    for v, unit in RX_POSTAGE_VAL.findall(text):
        try:
            vals.append({"face_value": float(v), "unit": unit.strip()})
        except:
            pass
    if vals:
        ents["values"] = vals

    # 5) Colores / diseños
    colors = [c.lower() for c in RX_COLOR.findall(text)]
    if colors:
        ents["colors"] = sorted(set(colors))
    designs = RX_DESIGN.findall(text)
    if designs:
        ents["designs"] = sorted(set(designs))

    # 6) Clasificador por reglas (upgrade chunk_type respetando etiquetas Dolphin)
    ctype = (chunk.get("chunk_type") or "").lower()
    is_textish = ctype in {"text", "paragraph", ""}

    if RX_DECREE.search(text) and is_textish:
        chunk["chunk_type"] = "decree"
        md.setdefault("labels", []).append("rule_decree")
    elif RX_AUCTION.search(text) and is_textish:
        chunk["chunk_type"] = "auction_result"
        md.setdefault("labels", []).append("rule_auction")
    elif RX_ISSUE.search(text) and is_textish:
        chunk["chunk_type"] = "issue_notice"
        md.setdefault("labels", []).append("rule_issue_notice")

    # 7) Variedades (overprint/color/mirror…)
    chunk = tag_varieties_filatelia(chunk)

    # 8) Topics/facetas (fauna/aviación/period/type…)
    chunk = add_topics(chunk)

    return chunk

# === PRUEBA PRINCIPAL ===
if __name__ == "__main__":
    # Chunk problemático original
    chunk_problema = {
        'chunk_id': 'OXCART22:003:1-1:0',
        'chunk_type': 'text',
        'text': "On p.p. 63 & 64 of the OXCART for July, 1964 (Vol. IV, No. 3), I gave in brief the story of the Lindbergh stamp (Scott 147) and a resume of the Colonel's visit to Costa Rica in January, 1928. This is now followed up below with some - excellent illustrations of (a) stamp with genuine surcharge; (b) stamp with the forged surcharge; and, (c) the inverted surcharge, which also is a forgery.",
        'grounding': [{'page': 3, 'box': None}],
        'metadata': {'labels': ['para'], 'reading_order_range': [1, 1]}
    }

    print("PRUEBA DE ENRIQUECIMIENTO CON PATRON MEJORADO")
    print("=" * 60)

    print(f"\nTexto original:")
    print(f"'{chunk_problema['text']}'")

    # Hacer una copia para no modificar el original
    chunk_copia = copy.deepcopy(chunk_problema)

    # Aplicar enriquecimiento
    chunk_enriquecido = enrich_chunk_filatelia(chunk_copia)

    print(f"\nRESULTADOS DEL ENRIQUECIMIENTO:")
    print("-" * 40)

    # Verificar si se detectó el catálogo Scott
    entities = chunk_enriquecido.get('metadata', {}).get('entities', {})
    print(f"Catalogos detectados: {entities.get('catalog', 'NINGUNO')}")

    # Verificar fechas
    print(f"Fechas detectadas: {entities.get('dates', 'NINGUNO')}")

    # Verificar topics
    topics = chunk_enriquecido.get('metadata', {}).get('topics', {})
    print(f"Topic principal: {topics.get('primary', 'NINGUNO')}")
    print(f"Topics secundarios: {topics.get('secondary', [])}")

    # Verificar axes/period
    axes = chunk_enriquecido.get('metadata', {}).get('axes', {})
    print(f"Periodo detectado: {axes.get('period', 'NINGUNO')}")

    # Verificar variedades
    if entities.get('varieties'):
        print(f"Variedades detectadas: {len(entities['varieties'])}")
        for v in entities['varieties']:
            print(f"  - {v['class']}: {v['label']}")
    else:
        print("Variedades detectadas: NINGUNO")

    print(f"\nChunk enriquecido completo:")
    print(f"Chunk ID: {chunk_enriquecido['chunk_id']}")
    print(f"Tipo: {chunk_enriquecido['chunk_type']}")

    # Mostrar toda la metadata
    print(f"\nMetadata completa:")
    print(json.dumps(chunk_enriquecido['metadata'], indent=2, ensure_ascii=False))