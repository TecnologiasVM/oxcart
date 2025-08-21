"""
Philatelic Pattern Matching and Metadata Enrichment - VERSION 3.0

This module contains advanced patterns, regex definitions, and enrichment logic
for comprehensive philatelic document analysis and research.

VERSION: 3.0 - Advanced Philatelic Research System
- International catalog systems (Michel, Yvert, Zumstein)
- Technical specifications (perforation, paper, printing)
- EFO classification system
- Weaviate-optimized metadata structure
- Advanced condition assessment
- Costa Rica specialized patterns
- All patterns are case-insensitive and robust
"""

import re
import datetime
from typing import Dict, Any, Optional, List, Tuple, Union
import json
from pathlib import Path


# ====== INTERNATIONAL CATALOG SYSTEMS ======

# SCOTT CATALOG - Highly robust pattern for all variations
# Matches: Scott 20, scott #a43, SCOTT No. 147, scott's C1, etc.
RX_SCOTT = re.compile(
    r"\b(?:scott(?:'?s)?)\s*(?:no\.?|#)?\s*([a-z]?\d+[a-z\-]*)", 
    re.IGNORECASE
)

# SCOTT RANGES - For "Scott Nos. 1-5", "scott ## 10-15", etc.
RX_SCOTT_RANGE = re.compile(
    r"\b(?:scott(?:'?s)?)\s+(?:nos?\.?|##?)\s*([a-z]?\d+[a-z\-]*)\s*(?:–|-|to|through)\s*([a-z]?\d+[a-z\-]*)", 
    re.IGNORECASE
)

# MICHEL CATALOG - German philatelic catalog (e.g., "Michel 247", "Michel-Nr. 15a")
RX_MICHEL = re.compile(
    r"\b(?:michel(?:-?nr\.?)?|mi\.?)\s*([a-z]?\d+[a-z\-]*)", 
    re.IGNORECASE
)

# YVERT & TELLIER - French catalog (e.g., "Yvert 123", "Y&T 45a")
RX_YVERT = re.compile(
    r"\b(?:yvert(?:\s*&\s*tellier)?|y\s*&\s*t|yt)\s*([a-z]?\d+[a-z\-]*)", 
    re.IGNORECASE
)

# ZUMSTEIN - Swiss catalog (e.g., "Zumstein 67", "Zum. 15b")
RX_ZUMSTEIN = re.compile(
    r"\b(?:zumstein|zum\.)\s*([a-z]?\d+[a-z\-]*)", 
    re.IGNORECASE
)

# STANLEY GIBBONS - British catalog (enhanced pattern)
RX_GIBBONS = re.compile(
    r"\b(?:(?:stanley\s+)?gibbons?|sg)\s*(?:no\.?\s*)?([a-z]?\d+[a-z\-]*)", 
    re.IGNORECASE
)

# DEPRECATED CATALOGS - Legacy M and A patterns for Costa Rica
RX_M = re.compile(r"\bM\s*(\d+[A-Za-z]?)\b", re.IGNORECASE)
RX_A = re.compile(r"\bA\s*(\d+[A-Za-z]?)\b", re.IGNORECASE)

# ====== DATE PATTERNS ======

# DATE PATTERNS - More robust and case-insensitive
MONTHS_EN = r"(?:january|february|march|april|may|june|july|august|september|october|november|december)"
MONTHS_ES = r"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)"

# English dates: "January 15, 1960" or "january 15, 1960"
RX_DATE_EN = re.compile(rf"\b({MONTHS_EN})\s+\d{{1,2}},\s*\d{{4}}\b", re.IGNORECASE)

# Spanish dates: "15 de enero 1960" or "15 enero 1960"
RX_DATE_ES = re.compile(rf"\b\d{{1,2}}\s+(?:de\s+)?({MONTHS_ES})\s+\d{{4}}\b", re.IGNORECASE)

# Years: 1800-2099
RX_YEAR = re.compile(r"\b(18|19|20)\d{2}\b")

# ====== PRICE AND VALUE PATTERNS ======

# PRICE PATTERNS - More comprehensive currency detection
RX_PRICE = re.compile(
    r"(?:us?\$|\$|₡|¢|colones?|dollars?|pesos?)\s*[\d.,]+", 
    re.IGNORECASE
)

# POSTAGE VALUES - Face value on stamps
RX_POSTAGE_VAL = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(ct|cts|c|c\.|centimos?|centavos?|colones?|pesos?)\b", 
    re.IGNORECASE
)

# ====== DOCUMENT TYPE PATTERNS ======

# DOCUMENT TYPE PATTERNS - Enhanced detection
RX_DECREE = re.compile(
    r"\b(?:legislative\s+)?decre(?:e|to)\b|\bdecreto\s+no?\.?|\bdecrease\s+no?\.?", 
    re.IGNORECASE
)

RX_ISSUE = re.compile(
    r"\b(?:first\s+day\s+of\s+issue|primer(?:\s+d[ií]a)?\s+de\s+emisi[oó]n|is\s+authorized|autorizado|emitido)\b", 
    re.IGNORECASE
)

RX_AUCTION = re.compile(
    r"\b(?:brought|realized|estimate|lot|sale|subasta|remate|vendido)\b.*?[\$₡][\d.,]+", 
    re.IGNORECASE
)

# ====== APPEARANCE PATTERNS ======

# COLOR PATTERNS - Expanded color detection
RX_COLOR = re.compile(
    r"\b(?:violet|deep\s+blue|orange|green|red|black|coffee|beige|grey|gray|ultramarine|scarlet|" +
    r"blue|yellow|brown|pink|purple|magenta|cyan|white|dark|light)\b", 
    re.IGNORECASE
)

# DESIGN PATTERNS - Common Costa Rican stamp subjects
RX_DESIGN = re.compile(
    r"\b(?:jaguar|deer|tapir|ocelot|peccary|cathedral|map|columbus|coat\s+of\s+arms|" +
    r"escudo|mapa|catedral|fauna|flora)\b", 
    re.IGNORECASE
)

# ====== TECHNICAL SPECIFICATIONS PATTERNS ======

# PERFORATION PATTERNS - Precise measurements and types
RX_PERF_MEASURE = re.compile(
    r"\b(?:perf(?:oration)?|perforado?)\s*(?:gauge)?\s*([\d.]+(?:\s*[x×:]\s*[\d.]+)?)\b", 
    re.IGNORECASE
)

RX_IMPERF = re.compile(
    r"\b(?:imperf(?:orate)?|sin\s+perforar|imperfecto)\b", 
    re.IGNORECASE
)

RX_PERF_TYPES = re.compile(
    r"\b(?:pin\s+perf|line\s+perf|comb\s+perf|harrow\s+perf|roulette|rouletted|" +
    r"serpentine\s+die\s+cut|straight\s+edge)\b", 
    re.IGNORECASE
)

# PAPER PATTERNS - Types and characteristics
RX_PAPER_TYPES = re.compile(
    r"\b(?:wove\s+paper|laid\s+paper|granite\s+paper|pelure\s+paper|" +
    r"quadrille\s+paper|batonne\s+paper|manila\s+paper|safety\s+paper|" +
    r"papel\s+(?:satinado|ordinario|grueso|delgado))\b", 
    re.IGNORECASE
)

RX_PAPER_THICKNESS = re.compile(
    r"\b(?:thick|thin|medium|grueso|delgado|mediano)\s+paper\b", 
    re.IGNORECASE
)

# WATERMARK PATTERNS - Enhanced detection
RX_WATERMARK_TYPES = re.compile(
    r"\b(?:watermark|filigrana|marca\s+de\s+agua|" +
    r"multiple\s+(?:crown|star|cross)|single\s+(?:crown|star|cross)|" +
    r"script\s+(?:ca|cr)|coat\s+of\s+arms\s+watermark)\b", 
    re.IGNORECASE
)

RX_WATERMARK_POSITION = re.compile(
    r"\b(?:watermark|filigrana)\s+(?:inverted|invertida|sideways|lateral|normal|upright)\b", 
    re.IGNORECASE
)

# PRINTING METHODS - Production techniques
RX_PRINTING_METHODS = re.compile(
    r"\b(?:lithograph(?:y|ed)?|engraved?|engraving|intaglio|offset|" +
    r"photogravure|heliogravure|typography|letterpress|screen\s+print|" +
    r"litografía|grabado|calcografía|tipografía)\b", 
    re.IGNORECASE
)

# GUM PATTERNS - Gum types and conditions
RX_GUM_TYPES = re.compile(
    r"\b(?:original\s+gum|goma\s+original|o\.?g\.?|" +
    r"tropical\s+gum|white\s+gum|yellow\s+gum|" +
    r"no\s+gum|sin\s+goma|regummed|regomado)\b", 
    re.IGNORECASE
)

# ====== CONDITION ASSESSMENT PATTERNS ======

# CONDITION GRADES - Mint and used conditions
RX_CONDITION_MINT = re.compile(
    r"\b(?:mint\s+(?:never\s+hinged|nh)|mnh|mint\s+(?:lightly\s+hinged|lh)|mlh|" +
    r"mint\s+hinged|mh|mint\s+no\s+gum|mng)\b", 
    re.IGNORECASE
)

RX_CONDITION_USED = re.compile(
    r"\b(?:used|cancelled\s+to\s+order|cto|first\s+day\s+cancel|fdc|" +
    r"postally\s+used|commercially\s+used)\b", 
    re.IGNORECASE
)

# CENTERING GRADES
RX_CENTERING = re.compile(
    r"\b(?:perfectly?\s+centered|superb|extremely?\s+fine|xf|very\s+fine|vf|" +
    r"fine|f|very\s+good|vg|good|g|poor|off\s+center)\b", 
    re.IGNORECASE
)

# DEFECTS
RX_DEFECTS = re.compile(
    r"\b(?:crease|creased|thin|thins|spot|stain|tear|torn|short\s+perf|" +
    r"pulled\s+perf|corner\s+crease|bend|bent|fade|faded)\b", 
    re.IGNORECASE
)

# ====== EFO (ERRORS, FREAKS & ODDITIES) PATTERNS ======

# INVERTED OVERPRINTS
RX_OVERPRINT_INVERTED = re.compile(
    r"\b(?:sobrecarga(?:s)?\s+invertid[ao]s?|invertid[ao]\b|al\s+rev[eé]s|" +
    r"inverted\s+overprint|overprint\s+inverted|upside[-\s]?down\s+overprint)\b",
    re.IGNORECASE
)

# DOUBLE OVERPRINTS
RX_OVERPRINT_DOUBLE = re.compile(
    r"\b(?:sobrecarga(?:s)?\s+doble?s?|double\s+overprint|doble\s+impresion)\b", 
    re.IGNORECASE
)

# OVERPRINT TEXT TYPES
RX_OVERPRINT_TEXT = re.compile(
    r"\b(?:lindbergh|guanacaste|correos|oficial|renta\s+postales|habilitado)\b", 
    re.IGNORECASE
)

# COLOR ERROR PATTERNS
RX_COLOR_ERROR = re.compile(
    r"\b(?:error(?:es)?\s+de\s+color|color\s+incorrecto|color\s+equivocado|" +
    r"desplazamiento\s+de\s+color|falta\s+de\s+color|color\s+shift|" +
    r"missing\s+color|wrong\s+color|double\s+impression)\b",
    re.IGNORECASE
)

RX_COLOR_SHIFT = re.compile(
    r"\b(?:desplazamiento\s+de\s+color|color\s+shift)\b", 
    re.IGNORECASE
)

RX_MISSING_COLOR = re.compile(
    r"\b(?:falta\s+de\s+color|missing\s+color)\b", 
    re.IGNORECASE
)

RX_WRONG_COLOR = re.compile(
    r"\b(?:color\s+incorrecto|color\s+equivocado|wrong\s+color)\b", 
    re.IGNORECASE
)

# MIRROR/REVERSED PATTERNS
RX_MIRROR = re.compile(
    r"\b(?:espejo|impresi[oó]n\s+espejo|impresi[oó]n\s+en\s+espejo|" +
    r"mirror\s+print|mirror\s+image|reversed\s+impression)\b",
    re.IGNORECASE
)

RX_REVERSED = re.compile(r"\b(?:reversed|invertido)\b", re.IGNORECASE)

# ====== COSTA RICA SPECIFIC PATTERNS ======

# GUANACASTE OVERPRINTS - Historical Costa Rican overprints (1885-1891)
RX_GUANACASTE_OVERPRINT = re.compile(
    r"\b(?:guanacaste|provincia\s+de\s+guanacaste|gto\.?)\b", 
    re.IGNORECASE
)

# COSTA RICA HISTORICAL PERIODS
RX_CR_PERIODS = re.compile(
    r"\b(?:colonial\s+period|período\s+colonial|republic\s+period|" +
    r"período\s+republicano|modern\s+era|era\s+moderna)\b", 
    re.IGNORECASE
)

# COSTA RICAN PERSONALITIES
RX_CR_PERSONALITIES = re.compile(
    r"\b(?:jesús\s+jiménez|juan\s+mora\s+fernández|braulio\s+carrillo|" +
    r"tomás\s+guardia|rafael\s+yglesias|ricardo\s+jiménez|" +
    r"rafael\s+calderón\s+guardia|josé\s+figueres)\b", 
    re.IGNORECASE
)

# COSTA RICAN GEOGRAPHIC FEATURES
RX_CR_GEOGRAPHY = re.compile(
    r"\b(?:volcán\s+(?:arenal|irazú|poás)|cordillera\s+(?:central|talamanca)|" +
    r"golfo\s+(?:dulce|nicoya)|península\s+(?:nicoya|osa)|" +
    r"puerto\s+(?:limón|caldera|puntarenas))\b", 
    re.IGNORECASE
)

# ====== ADVANCED TOPIC CLASSIFICATION ======

# TOPIC PATTERNS - Enhanced with Costa Rica specifics
TOPIC_PATTERNS = {
    "fauna_cr": r"\b(?:jaguar|ocelot|manigordo|tapir|cariblanco|quetzal|tucán|perezoso|rana\s+(?:dardo|verde)|colibrí)\b",
    "flora_cr": r"\b(?:guaria\s+morada|café|cacao|banano|orquídea|cecropia|pochote|roble)\b",
    "aviacion": r"\b(?:aviaci[oó]n|airmail|correo\s+a[eé]reo|av[ií]on|lindbergh|aereo)\b",
    "historia_postal": r"\b(?:tarifa|franqueo|carta|sobrecargo|postmark|cancelaci[oó]n|paquete|cto|postal\s+history)\b",
    "overprint": r"\b(?:sobrecarga|overprint|a\s?\d+|guanacaste|oficial|correos)\b",
    "watermark": r"\b(?:filigrana|marca\s+de\s+agua|watermark)\b",
    "perforation": r"\b(?:perf(?:oration)?|perforaci[oó]n|imperf|\d{1,2}(?:\.\d+)?(?:\s*[x×]\s*\d{1,2}(?:\.\d+)?)?)\b",
    "proofs_essays": r"\b(?:proof|prueba|essay|color\s+trial|plate\s+proof|ensayo)\b",
    "mapas_cr": r"\b(?:mapa\s+de\s+costa\s+rica|map\s+of\s+costa\s+rica|costa\s+rica\s+map)\b",
    "personajes_cr": r"\b(?:jesús\s+jiménez|columbus|orlich|soley|moya|bolívar|colón|figueres)\b",
    "arquitectura_cr": r"\b(?:teatro\s+nacional|catedral\s+metropolitana|palacio\s+nacional|edificio\s+correos)\b",
    "deportes": r"\b(?:deporte|olímpic[oa]s|sports|juegos|fútbol|soccer)\b",
    "commemorative_events": r"\b(?:centenario|aniversario|bicentenario|independencia|anniversary)\b"
}

# TYPE PATTERNS - Enhanced classification
TYPE_PATTERNS = {
    "airmail": r"\b(?:airmail|correo\s+a[eé]reo|^c\d+\b)",
    "postage_due": r"\b(?:postage\s+due|p1\b|p2\b|insuficiente\s+franqueo)\b",
    "official": r"\b(?:oficial|official\s+stamps?)\b",
    "revenue": r"\b(?:revenue|fiscal|renta\s+postales)\b",
    "semipostal": r"\b(?:semi[-\s]?postal|b\d+\b)\b",
    "commemorative": r"\b(?:comemorativ[oa]|commemorative|aniversario|centenari[oa])\b",
    "definitive": r"\b(?:definitiv[oa]|definitive|regular\s+issue)\b",
    "booklet_coil": r"\b(?:booklet\s+pane|coil|carnet)\b",
    "souvenir_sheet": r"\b(?:souvenir\s+sheet|hoja\s+(?:recuerdo|souvenir)|minisheet)\b"
}

# MONTH MAPPING - All lowercase for case-insensitive matching
MONTH_MAP = {
    # English months
    "january": "01", "february": "02", "march": "03", "april": "04", 
    "may": "05", "june": "06", "july": "07", "august": "08", 
    "september": "09", "october": "10", "november": "11", "december": "12",
    
    # Spanish months
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04", 
    "mayo": "05", "junio": "06", "julio": "07", "agosto": "08", 
    "septiembre": "09", "setiembre": "09", "octubre": "10", 
    "noviembre": "11", "diciembre": "12",
}

# ====== UTILITY FUNCTIONS ======

def _norm_date_string(s: str) -> Optional[str]:
    """Normalize date strings to YYYY-MM-DD format or YYYY for years only"""
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
    """Normalize price strings with currency detection"""
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
    """Remove duplicate dictionaries from list"""
    seen = set()
    out = []
    for it in items:
        key = tuple(sorted((k, str(v)) for k, v in it.items()))
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out

def _add_variety(ents: dict, data: Dict[str, Any]):
    """Add variety to entities varieties list"""
    arr = ents.setdefault("varieties", [])
    arr.append(data)

def _calculate_quality_score(metadata: Dict[str, Any]) -> float:
    """Calculate data quality score based on completeness and consistency"""
    score = 0.5  # Base score
    
    entities = metadata.get("entities", {})
    
    # Catalog presence
    if entities.get("catalog"):
        score += 0.2
        # Scott catalog bonus
        scott_matches = [c for c in entities["catalog"] if c.get("system") == "Scott"]
        if scott_matches:
            score += 0.1
    
    # Date presence
    if entities.get("dates"):
        score += 0.1
    
    # Technical specifications
    tech_specs = sum([
        1 for key in ["perforation", "paper", "printing", "watermark", "gum"] 
        if entities.get(key)
    ])
    score += tech_specs * 0.02
    
    # Variety detection
    if entities.get("varieties"):
        score += 0.05
    
    # Topic classification
    topics = metadata.get("topics", {})
    if topics.get("primary"):
        score += 0.03
    
    return min(0.99, score)

# ====== ADVANCED ENRICHMENT FUNCTIONS ======

def extract_technical_specs(text: str) -> Dict[str, Any]:
    """Extract technical specifications from text"""
    specs = {}
    
    # Perforation
    perf_measures = RX_PERF_MEASURE.findall(text)
    if perf_measures:
        specs["perforation"] = {"measurements": perf_measures}
    
    if RX_IMPERF.search(text):
        specs.setdefault("perforation", {})["type"] = "imperforate"
    
    perf_types = RX_PERF_TYPES.findall(text)
    if perf_types:
        specs.setdefault("perforation", {})["method"] = perf_types[0]
    
    # Paper
    paper_types = RX_PAPER_TYPES.findall(text)
    if paper_types:
        specs["paper"] = {"type": paper_types[0]}
    
    paper_thickness = RX_PAPER_THICKNESS.findall(text)
    if paper_thickness:
        specs.setdefault("paper", {})["thickness"] = paper_thickness[0]
    
    # Watermark
    watermark_types = RX_WATERMARK_TYPES.findall(text)
    if watermark_types:
        specs["watermark"] = {"type": watermark_types[0]}
    
    watermark_pos = RX_WATERMARK_POSITION.findall(text)
    if watermark_pos:
        specs.setdefault("watermark", {})["position"] = watermark_pos[0]
    
    # Printing
    printing_methods = RX_PRINTING_METHODS.findall(text)
    if printing_methods:
        specs["printing"] = {"method": printing_methods[0]}
    
    # Gum
    gum_types = RX_GUM_TYPES.findall(text)
    if gum_types:
        specs["gum"] = {"type": gum_types[0]}
    
    return specs

def extract_condition_assessment(text: str) -> Dict[str, Any]:
    """Extract condition assessment from text"""
    condition = {}
    
    # Mint condition
    mint_cond = RX_CONDITION_MINT.search(text)
    if mint_cond:
        condition["mint_status"] = mint_cond.group(0)
    
    # Used condition
    used_cond = RX_CONDITION_USED.search(text)
    if used_cond:
        condition["used_status"] = used_cond.group(0)
    
    # Centering
    centering = RX_CENTERING.search(text)
    if centering:
        condition["centering"] = centering.group(0)
    
    # Defects
    defects = RX_DEFECTS.findall(text)
    if defects:
        condition["defects"] = defects
    
    return condition

def extract_all_catalog_numbers(text: str) -> List[Dict[str, Any]]:
    """Extract all catalog numbers from text"""
    catalogs = []
    
    # Scott
    sc = RX_SCOTT.findall(text)
    if not sc:
        r = RX_SCOTT_RANGE.search(text)
        if r:
            sc = [f"{r.group(1)}–{r.group(2)}"]
    
    for x in sc:
        catalogs.append({"system": "Scott", "number": x})
    
    # Michel
    for x in RX_MICHEL.findall(text):
        catalogs.append({"system": "Michel", "number": x})
    
    # Yvert & Tellier
    for x in RX_YVERT.findall(text):
        catalogs.append({"system": "Yvert", "number": x})
    
    # Zumstein
    for x in RX_ZUMSTEIN.findall(text):
        catalogs.append({"system": "Zumstein", "number": x})
    
    # Gibbons
    for x in RX_GIBBONS.findall(text):
        catalogs.append({"system": "Gibbons", "number": x})
    
    # Legacy M and A
    for rx, sys in [(RX_M, "M"), (RX_A, "A")]:
        for x in rx.findall(text):
            catalogs.append({"system": sys, "number": x})
    
    return _dedup_list_dicts(catalogs)

def classify_efo_varieties(text: str) -> List[Dict[str, Any]]:
    """Classify Errors, Freaks & Oddities"""
    varieties = []
    
    # Overprint errors
    if RX_OVERPRINT_INVERTED.search(text):
        mtxt = RX_OVERPRINT_TEXT.search(text)
        varieties.append({
            "class": "overprint",
            "subtype": "inverted",
            "label": "sobrecarga invertida",
            "text": mtxt.group(0) if mtxt else None,
            "confidence": 0.8
        })
    
    if RX_OVERPRINT_DOUBLE.search(text):
        varieties.append({
            "class": "overprint", 
            "subtype": "double",
            "label": "doble sobrecarga",
            "confidence": 0.7
        })
    
    # Color errors
    if RX_COLOR_ERROR.search(text):
        if RX_COLOR_SHIFT.search(text): 
            subtype = "color_shift"
        elif RX_MISSING_COLOR.search(text): 
            subtype = "missing_color"
        elif RX_WRONG_COLOR.search(text): 
            subtype = "wrong_color"
        else: 
            subtype = "unspecified"
        
        varieties.append({
            "class": "color_error",
            "subtype": subtype,
            "label": "error de color",
            "confidence": 0.7
        })
    
    # Mirror/reversed
    if RX_MIRROR.search(text) or RX_REVERSED.search(text):
        is_mirror = RX_MIRROR.search(text) is not None
        varieties.append({
            "class": "mirror_print",
            "subtype": "mirror" if is_mirror else "reversed",
            "label": "impresión espejo" if is_mirror else "impresión invertida",
            "confidence": 0.7
        })
    
    return varieties

def classify_costa_rica_context(text: str) -> Dict[str, Any]:
    """Extract Costa Rica specific context"""
    context = {}
    
    # Guanacaste overprints
    if RX_GUANACASTE_OVERPRINT.search(text):
        context["guanacaste_period"] = True
        context["historical_significance"] = "1885-1891 Guanacaste overprint period"
    
    # Historical periods
    periods = RX_CR_PERIODS.findall(text)
    if periods:
        context["historical_periods"] = periods
    
    # Personalities
    personalities = RX_CR_PERSONALITIES.findall(text)
    if personalities:
        context["personalities"] = personalities
    
    # Geography
    geography = RX_CR_GEOGRAPHY.findall(text)
    if geography:
        context["geographic_features"] = geography
    
    return context

def enrich_chunk_advanced_philatelic(chunk: Dict[str, Any]) -> Dict[str, Any]:
    """
    Advanced philatelic enrichment for comprehensive metadata extraction
    """
    text = chunk.get("text", "") or ""
    md = chunk.setdefault("metadata", {})
    ents = md.setdefault("entities", {})
    
    # 1) All catalog systems
    catalogs = extract_all_catalog_numbers(text)
    if catalogs:
        ents["catalog"] = catalogs
    
    # 2) Dates (enhanced)
    dates = []
    for m in RX_DATE_EN.finditer(text):
        nd = _norm_date_string(m.group(0))
        if nd: dates.append(nd)
    for m in RX_DATE_ES.finditer(text):
        nd = _norm_date_string(m.group(0))
        if nd: dates.append(nd)
    if not dates:
        y = RX_YEAR.search(text)
        if y: dates.append(y.group(0))
    if dates:
        ents["dates"] = sorted(set(dates))
    
    # 3) Prices
    prices = []
    for s in RX_PRICE.findall(text):
        p = _norm_price(s)
        if p: prices.append(p)
    if prices:
        ents["prices"] = prices
    
    # 4) Postage values
    vals = []
    for v, unit in RX_POSTAGE_VAL.findall(text):
        try:
            vals.append({"face_value": float(v), "unit": unit.strip()})
        except:
            pass
    if vals:
        ents["values"] = vals
    
    # 5) Colors and designs
    colors = [c.lower() for c in RX_COLOR.findall(text)]
    if colors:
        ents["colors"] = sorted(set(colors))
    
    designs = RX_DESIGN.findall(text)
    if designs:
        ents["designs"] = sorted(set(designs))
    
    # 6) Technical specifications
    tech_specs = extract_technical_specs(text)
    if tech_specs:
        ents.update(tech_specs)
    
    # 7) Condition assessment
    condition = extract_condition_assessment(text)
    if condition:
        ents["condition"] = condition
    
    # 8) EFO varieties
    varieties = classify_efo_varieties(text)
    if varieties:
        ents["varieties"] = varieties
    
    # 9) Costa Rica context
    cr_context = classify_costa_rica_context(text)
    if cr_context:
        ents["costa_rica_context"] = cr_context
    
    # 10) Advanced topic classification
    text_lower = text.lower()
    topics = md.setdefault("topics", {"secondary": [], "tags": []})
    hits = []
    
    for k, rx in TOPIC_PATTERNS.items():
        if re.search(rx, text_lower, flags=re.I):
            hits.append(k)
    
    types = []
    for k, rx in TYPE_PATTERNS.items():
        if re.search(rx, text_lower, flags=re.I):
            types.append(k)
    
    # Primary/secondary topics
    if hits:
        topics["primary"] = topics.get("primary", hits[0])
        topics["secondary"] = sorted(list(set(topics.get("secondary", []) + 
                                                [h for h in hits if h != topics.get("primary")])))
    
    if types:
        md.setdefault("axes", {})
        md["axes"]["type"] = sorted(list(set(md["axes"].get("type", []) + types)))
    
    # Period classification
    years = ents.get("dates", [])
    if years:
        y = None
        for d in years:
            if len(d) >= 4 and d[:4].isdigit():
                y = int(d[:4])
                break
        if y:
            decade = f"{(y//10)*10}s"
            md.setdefault("axes", {})
            md["axes"]["period"] = sorted(list(set(md["axes"].get("period", []) + [decade])))
    
    # Enhanced confidence calculation  
    topics["confidence"] = _calculate_quality_score(md)
    
    # Enhanced tags
    enhanced_tags = []
    if "triang" in text_lower: enhanced_tags.append("triangular")
    if "watermark" in text_lower or "filigrana" in text_lower: enhanced_tags.append("watermark")
    if "imperf" in text_lower: enhanced_tags.append("imperforate")
    if "proof" in text_lower or "prueba" in text_lower: enhanced_tags.append("proof")
    if "error" in text_lower: enhanced_tags.append("error")
    if "variety" in text_lower or "variedad" in text_lower: enhanced_tags.append("variety")
    
    topics["tags"] = sorted(list(set(topics.get("tags", []) + enhanced_tags)))
    
    # Document type classification
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
    
    # Data quality score
    md["quality_score"] = _calculate_quality_score(md)
    
    return chunk

def enrich_all_chunks_advanced_philatelic(ox: Dict[str, Any]) -> Dict[str, Any]:
    """
    Advanced enrichment for all chunks with comprehensive philatelic metadata
    """
    for ch in ox.get("chunks", []):
        enrich_chunk_advanced_philatelic(ch)
    
    # Document-level metadata
    ox.setdefault("extraction_metadata", {})["enrichment_version"] = "philately-advanced-v3.0"
    ox["extraction_metadata"]["enriched_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    ox["extraction_metadata"]["features"] = [
        "international_catalogs", "technical_specs", "efo_classification",
        "condition_assessment", "costa_rica_context", "advanced_topics"
    ]
    
    return ox

def save_json(data: dict, out_path: str) -> str:
    """Save data as JSON to the specified path."""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return out_path

# ====== WEAVIATE SCHEMA OPTIMIZATION ======

def generate_weaviate_properties(chunk_metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate Weaviate-optimized properties from philatelic metadata
    for efficient filtering and search
    """
    props = {}
    entities = chunk_metadata.get("entities", {})
    
    # Catalog identifiers - indexed for exact match
    if entities.get("catalog"):
        props["scott_numbers"] = [c["number"] for c in entities["catalog"] if c["system"] == "Scott"]
        props["michel_numbers"] = [c["number"] for c in entities["catalog"] if c["system"] == "Michel"]
        props["yvert_numbers"] = [c["number"] for c in entities["catalog"] if c["system"] == "Yvert"]
        props["catalog_systems"] = list(set(c["system"] for c in entities["catalog"]))
    
    # Temporal properties
    if entities.get("dates"):
        dates = entities["dates"]
        props["issue_dates"] = dates
        # Extract years for decade filtering
        years = []
        for d in dates:
            if len(d) >= 4 and d[:4].isdigit():
                years.append(int(d[:4]))
        if years:
            props["issue_years"] = years
            props["decades"] = list(set(f"{(y//10)*10}s" for y in years))
    
    # Technical specifications - filterable
    tech_fields = ["perforation", "paper", "printing", "watermark", "gum"]
    for field in tech_fields:
        if entities.get(field):
            props[f"{field}_type"] = entities[field].get("type", "")
    
    # Condition properties
    if entities.get("condition"):
        condition = entities["condition"]
        props["mint_status"] = condition.get("mint_status", "")
        props["used_status"] = condition.get("used_status", "")
        props["centering"] = condition.get("centering", "")
        props["has_defects"] = bool(condition.get("defects"))
    
    # Variety classification
    if entities.get("varieties"):
        varieties = entities["varieties"]
        props["variety_classes"] = list(set(v["class"] for v in varieties))
        props["variety_subtypes"] = list(set(v["subtype"] for v in varieties))
        props["has_errors"] = any(v["class"] in ["color_error", "overprint"] for v in varieties)
    
    # Topic classification
    topics = chunk_metadata.get("topics", {})
    if topics.get("primary"):
        props["primary_topic"] = topics["primary"]
    if topics.get("secondary"):
        props["secondary_topics"] = topics["secondary"]
    if topics.get("tags"):
        props["philatelic_tags"] = topics["tags"]
    
    # Type classification
    axes = chunk_metadata.get("axes", {})
    if axes.get("type"):
        props["stamp_types"] = axes["type"]
    if axes.get("period"):
        props["periods"] = axes["period"]
    
    # Costa Rica specific
    if entities.get("costa_rica_context"):
        cr_ctx = entities["costa_rica_context"]
        props["is_guanacaste"] = cr_ctx.get("guanacaste_period", False)
        if cr_ctx.get("personalities"):
            props["cr_personalities"] = cr_ctx["personalities"]
        if cr_ctx.get("geographic_features"):
            props["cr_geography"] = cr_ctx["geographic_features"]
    
    # Quality metrics
    props["quality_score"] = chunk_metadata.get("quality_score", 0.5)
    props["confidence"] = topics.get("confidence", 0.5)
    
    return props