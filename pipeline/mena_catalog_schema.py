"""
Pydantic models for Mena Catalog (Costa Rica) structured parser output.

This schema defines all data structures needed to parse stamp catalog
information including issues, stamps, varieties, proofs, specimens, and more.
"""

from typing import Optional, List, Dict, Literal, Union
from pydantic import BaseModel, Field
from datetime import date


# ============================================================================
# NESTED MODELS FOR ISSUE_DATA
# ============================================================================

class IssueDates(BaseModel):
    """Issue-related dates in ISO format"""
    announced: Optional[str] = None
    placed_on_sale: Optional[str] = None
    probable_first_circulation: Optional[str] = None
    second_plate_sale: Optional[str] = None
    demonetized: Optional[str] = None


class LegalBasis(BaseModel):
    """Legal authorization for stamp issue"""
    type: str = ""  # "decree", "law", "letter", "resolution", etc.
    id: str = ""
    date: Optional[str] = None
    ids: List[str] = Field(default_factory=list)
    officials: List[str] = Field(default_factory=list)


class CurrencyContext(BaseModel):
    """Currency information and revaluations"""
    original: str = ""
    decimal_adoption: Optional[str] = None
    revaluation_date: Optional[str] = None
    reevaluation_map: Optional[Dict[str, str]] = None


class PrintingFormat(BaseModel):
    """Printing format details"""
    panes: Optional[int] = None


class PlateInfo(BaseModel):
    """Plate information for a denomination"""
    plates: List[int] = Field(default_factory=list)
    notes: Union[str, List[str]] = Field(default_factory=list)


class Printing(BaseModel):
    """Printing process and details"""
    printer: str = ""
    process: List[str] = Field(default_factory=list)
    format: PrintingFormat = Field(default_factory=PrintingFormat)
    plates: Optional[Dict[str, PlateInfo]] = None

class IssueData(BaseModel):
    """Top-level issue metadata"""
    issue_id: str
    section: str = ""  # e.g., "Surface Mail"
    title: str = ""
    country: str = ""
    issue_dates: IssueDates = Field(default_factory=IssueDates)
    legal_basis: List[Union[LegalBasis, str]] = Field(default_factory=list)  # Can be objects or strings
    currency_context: CurrencyContext = Field(default_factory=CurrencyContext)
    printing: Printing = Field(default_factory=Printing)
    perforation: str = ""  # Numeric gauge like "12" or range like "13.5-15.5"


# ============================================================================
# PRODUCTION ORDERS
# ============================================================================

class QuantityItem(BaseModel):
    """Single quantity entry"""
    plate_desc: str = ""  # Description (e.g., "Plate 1", "Mint", "Used")
    quantity: int = 0


class PrintingOrder(BaseModel):
    """Single printing order with date and quantities"""
    date: Optional[str] = None
    quantities: List[QuantityItem] = Field(default_factory=list)


class Remainders(BaseModel):
    """Information about stamp remainders"""
    date: Optional[str] = None
    notes: Union[str, List[str]] = Field(default_factory=list)
    quantities: List[QuantityItem] = Field(default_factory=list)


class ProductionOrders(BaseModel):
    """Production and printing information"""
    printings: List[PrintingOrder] = Field(default_factory=list)
    remainders: Remainders = Field(default_factory=Remainders)


# ============================================================================
# STAMPS (REGULAR, SOUVENIR SHEETS, TELEGRAPH)
# ============================================================================

class Denomination(BaseModel):
    """Stamp denomination"""
    value: Optional[float] = None  # None for souvenir sheets and seals
    unit: str  # "c", "C", "P", "reales", "real", "sheet", "seal"


class Overprint(BaseModel):
    """Overprint or surcharge information"""
    present: bool = True
    type: Literal["surcharge", "overprint", "bar_cancel", "other"] = "overprint"
    surcharge_denomination: Optional[Denomination] = None
    on_denomination: Optional[Denomination] = None
    color: str = ""


class Stamp(BaseModel):
    """Regular stamp, souvenir sheet, or telegraph stamp/seal"""
    catalog_no: str
    issue_id: str = ""
    denomination: Denomination
    color: str = ""
    plate: Optional[int] = None
    perforation: str = ""  # Gauge only (e.g., "12"), no "perf" word
    watermark: Optional[str] = None
    quantity_reported: Optional[int] = None
    status: Literal[
        "regular", 
        "souvenir_sheet", 
        "telegraph", 
        "telegraph_seal", 
        "radiogram_seal"
    ] = "regular"
    notes: Union[str, List[str]] = Field(default_factory=list)
    
    # Optional fields
    overprint: Optional[Overprint] = None
    base_stamp_ref: Optional[str] = None  # For surcharges
    sheet_contents: Optional[List[str]] = None  # For souvenir sheets
    paper: Optional[str] = None  # For telegraph seals and stationery


# ============================================================================
# VARIETIES
# ============================================================================

class Variety(BaseModel):
    """Stamp variety (lowercase suffix)"""
    base_catalog_no: str  # e.g., "31", "1A"
    suffix: str  # Lowercase only: "a", "b", "c"
    type: Literal[
        "perforation",
        "impression",
        "plate_flaw",
        "overprint",
        "surcharge",
        "color",
        "color_shift",
        "watermark",
        "paper",
        "gumming",
        "plate",
        "other"
    ]
    description: str
    position: Optional[str] = None  # e.g., "pos 1", "pos 87"
    plate: Optional[int] = None


# ============================================================================
# PROOFS
# ============================================================================

class DieProof(BaseModel):
    """Die proof information"""
    code: str  # e.g., "DP1", "DPA47"
    denomination: str = ""
    color: str = ""
    die_no: str = ""
    substrate: str = ""
    finish: str = ""  # e.g., "progressive: state 1"


class PlateProofVariant(BaseModel):
    """Individual variant within a plate proof"""
    variant: str = ""
    denomination: str = ""
    color: str = ""
    plate: Optional[int] = None
    notes: Union[str, List[str]] = Field(default_factory=list)


class PlateProof(BaseModel):
    """Plate proof information"""
    code: str  # e.g., "PP1", "PTS2"
    notes: Union[str, List[str]] = Field(default_factory=list)
    denomination: Optional[str] = None  
    color: Optional[str] = None  
    notes: Union[str, List[str]] = Field(default_factory=list)
    items: List[PlateProofVariant] = Field(default_factory=list)


class ColorProof(BaseModel):
    """Color trial proof"""
    code: str  # e.g., "CP1"
    denomination: str = ""
    color: str = ""
    notes: Union[str, List[str]] = Field(default_factory=list)


class ImperforateProof(BaseModel):
    """Imperforate proof"""
    code: str
    denomination: str = ""
    notes: Union[str, List[str]] = Field(default_factory=list)


class Proofs(BaseModel):
    """All proof types"""
    die_proofs: List[DieProof] = Field(default_factory=list)
    plate_proofs: List[PlateProof] = Field(default_factory=list)
    color_proofs: List[ColorProof] = Field(default_factory=list)
    imperforate_proofs: List[ImperforateProof] = Field(default_factory=list)


# ============================================================================
# ESSAYS
# ============================================================================

class Essay(BaseModel):
    """Stamp essay/design study"""
    code: str
    medium: str = ""
    paper: str = ""
    denomination: str = ""
    provenance: List[str] = Field(default_factory=list)
    notes: Union[str, List[str]] = Field(default_factory=list)


# ============================================================================
# SPECIMENS
# ============================================================================

class Specimen(BaseModel):
    """Specimen overprint (S-codes, MA codes)"""
    code: str  # e.g., "S47", "S47a", "MA46a"
    applies_to: Literal["proofs", "stamps"] = "stamps"
    type: str = "overprint"  # "overprint", "punch", "perfin", "handstamp"
    denomination: str = ""
    base_color: str = ""
    overprint_color: str = ""
    notes: Union[str, List[str]] = Field(default_factory=list)


# ============================================================================
# POSTAL STATIONERY
# ============================================================================

class PostalStationeryOverprint(BaseModel):
    """Overprint on postal stationery"""
    present: bool = True
    type: Literal["overprint", "surcharge"] = "overprint"
    text: str = ""
    color: str = ""


class PostalStationery(BaseModel):
    """Postal card, envelope, aerogramme, wrapper"""
    catalog_no: str  # e.g., "PC1", "EN5", "LS1", "OEN2", "W1"
    issue_id: str = ""
    stationery_type: Literal[
        "postal_card",
        "envelope",
        "aerogramme",
        "official_envelope",
        "wrapper"
    ]
    denomination: Denomination
    color: str = ""
    paper: str = ""  # e.g., "buff manila", "white laid"
    size: str = ""  # e.g., "132 x 80 mm"
    quantity_reported: Optional[int] = None
    notes: Union[str, List[str]] = Field(default_factory=list)
    
    # Optional fields
    card_type: Optional[Literal["single", "reply", "double"]] = None
    overprint: Optional[PostalStationeryOverprint] = None
    base_ref: Optional[str] = None


# ============================================================================
# ROOT MODEL
# ============================================================================

class MenaCatalogEntry(BaseModel):
    """
    Complete Mena Catalog entry with all sections.
    
    This is the root model that should be used to parse LLM output.
    All sections are required but can be empty containers.
    """
    issue_data: IssueData
    production_orders: ProductionOrders = Field(default_factory=ProductionOrders)
    stamps: List[Stamp] = Field(default_factory=list)
    varieties: List[Variety] = Field(default_factory=list)
    proofs: Proofs = Field(default_factory=Proofs)
    essays: List[Essay] = Field(default_factory=list)
    specimens: List[Specimen] = Field(default_factory=list)
    postal_stationery: List[PostalStationery] = Field(default_factory=list)
    
    class Config:
        # Allow extra fields during development
        extra = "forbid"
        # Use enum values
        use_enum_values = True


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

if __name__ == "__main__":
    import json
    
    # Example 1: Simple regular issue
    example1 = {
        "issue_data": {
            "issue_id": "CR-1863-FIRST-ISSUE",
            "section": "Surface Mail",
            "title": "Regular issue",
            "country": "Costa Rica",
            "issue_dates": {},
            "legal_basis": [],
            "currency_context": {"original": "", "revaluation_map": {}},
            "printing": {"printer": "", "process": [], "format": {}, "plates": {}},
            "perforation": ""
        },
        "production_orders": {
            "printings": [],
            "remainders": {"date": None, "notes": "", "quantities": []}
        },
        "stamps": [
            {
                "catalog_no": "1",
                "issue_id": "CR-1863-FIRST-ISSUE",
                "denomination": {"value": 0.5, "unit": "real"},
                "color": "blue",
                "plate": 1,
                "perforation": "",
                "watermark": None,
                "quantity_reported": 3000000,
                "status": "regular",
                "notes": []
            }
        ],
        "varieties": [],
        "proofs": {
            "die_proofs": [],
            "plate_proofs": [],
            "color_proofs": [],
            "imperforate_proofs": []
        },
        "essays": [],
        "specimens": [],
        "postal_stationery": []
    }
    
    example2 = {
            "issue_data": {
                "issue_id": "CR-SPECIMENS-SEGMENT",
                "section": "Surface Mail",
                "title": "Specimens",
                "country": "Costa Rica",
                "issue_dates": {
                    "announced": None,
                    "placed_on_sale": None,
                    "probable_first_circulation": None,
                    "second_plate_sale": None,
                    "demonetized": None
                },
                "legal_basis": [],
                "currency_context": {
                    "original": "",
                    "decimal_adoption": None,
                    "revaluation_date": None,
                    "revaluation_map": {}
                },
                "printing": {
                    "printer": "",
                    "process": [],
                    "format": {"panes": None},
                    "plates": {}
                },
                "perforation": ""
            },
            "production_orders": {
                "printings": [],
                "remainders": {"date": None, "notes": "", "quantities": []}
            },
            "stamps": [],
            "varieties": [],
            "proofs": {
                "die_proofs": [],
                "plate_proofs": [],
                "color_proofs": [],
                "imperforate_proofs": []
            },
            "essays": [],
            "specimens": [
                {
                    "code": "MA46a",
                    "applies_to": "stamps",
                    "type": "overprint",
                    "denomination": "10c",
                    "base_color": "scarlet",
                    "overprint_color": "black",
                    "notes": "MUESTRA overprint"
                },
                {
                    "code": "MA47a",
                    "applies_to": "stamps",
                    "type": "overprint",
                    "denomination": "15c",
                    "base_color": "purple",
                    "overprint_color": "red",
                    "notes": "MUESTRA overprint"
                },
                {
                    "code": "MA48a",
                    "applies_to": "stamps",
                    "type": "overprint",
                    "denomination": "25c",
                    "base_color": "light blue",
                    "overprint_color": "red",
                    "notes": "MUESTRA overprint"
                },
                {
                    "code": "MA49a",
                    "applies_to": "stamps",
                    "type": "overprint",
                    "denomination": "35c",
                    "base_color": "bistre brown",
                    "overprint_color": "red",
                    "notes": "MUESTRA overprint"
                },
                {
                    "code": "MA50a",
                    "applies_to": "stamps",
                    "type": "overprint",
                    "denomination": "60c",
                    "base_color": "bluish green",
                    "overprint_color": "red",
                    "notes": "MUESTRA overprint"
                },
                {
                    "code": "MA51a",
                    "applies_to": "stamps",
                    "type": "overprint",
                    "denomination": "75c",
                    "base_color": "olive",
                    "overprint_color": "red",
                    "notes": "MUESTRA overprint"
                },
                {
                    "code": "MA52a",
                    "applies_to": "stamps",
                    "type": "overprint",
                    "denomination": "1.35C",
                    "base_color": "red orange",
                    "overprint_color": "black",
                    "notes": "MUESTRA overprint"
                },
                {
                    "code": "MA53a",
                    "applies_to": "stamps",
                    "type": "overprint",
                    "denomination": "5C",
                    "base_color": "sepia",
                    "overprint_color": "red",
                    "notes": "MUESTRA overprint"
                },
                {
                    "code": "MA54a",
                    "applies_to": "stamps",
                    "type": "overprint",
                    "denomination": "10C",
                    "base_color": "red lilac",
                    "overprint_color": "black",
                    "notes": "MUESTRA overprint"
                },
                {
                    "code": "MA180",
                    "applies_to": "stamps",
                    "type": "overprint",
                    "denomination": "15c",
                    "base_color": "blue",
                    "overprint_color": "red",
                    "notes": "MUESTRA overprint oblique"
                },
                {
                    "code": "MA181",
                    "applies_to": "stamps",
                    "type": "overprint",
                    "denomination": "20c",
                    "base_color": "red",
                    "overprint_color": "red",
                    "notes": "MUESTRA overprint oblique"
                },
                {
                    "code": "MA182",
                    "applies_to": "stamps",
                    "type": "overprint",
                    "denomination": "35c",
                    "base_color": "dark green",
                    "overprint_color": "red",
                    "notes": "MUESTRA overprint oblique"
                },
                {
                    "code": "MA183",
                    "applies_to": "stamps",
                    "type": "overprint",
                    "denomination": "45c",
                    "base_color": "purple",
                    "overprint_color": "red",
                    "notes": "MUESTRA overprint oblique"
                },
                {
                    "code": "MA184",
                    "applies_to": "stamps",
                    "type": "overprint",
                    "denomination": "50c",
                    "base_color": "carmine",
                    "overprint_color": "red",
                    "notes": "MUESTRA overprint oblique"
                },
                {
                    "code": "MA185",
                    "applies_to": "stamps",
                    "type": "overprint",
                    "denomination": "75c",
                    "base_color": "red violet",
                    "overprint_color": "red",
                    "notes": "MUESTRA overprint oblique"
                },
                {
                    "code": "MA186",
                    "applies_to": "stamps",
                    "type": "overprint",
                    "denomination": "1C",
                    "base_color": "olive",
                    "overprint_color": "red",
                    "notes": "MUESTRA overprint oblique"
                },
                {
                    "code": "MA187",
                    "applies_to": "stamps",
                    "type": "overprint",
                    "denomination": "2C",
                    "base_color": "red brown",
                    "overprint_color": "red",
                    "notes": "MUESTRA overprint oblique"
                },
                {
                    "code": "MA188",
                    "applies_to": "stamps",
                    "type": "overprint",
                    "denomination": "5C",
                    "base_color": "orange yellow",
                    "overprint_color": "red",
                    "notes": "MUESTRA overprint oblique"
                },
                {
                    "code": "MA189",
                    "applies_to": "stamps",
                    "type": "overprint",
                    "denomination": "10C",
                    "base_color": "bright blue",
                    "overprint_color": "red",
                    "notes": "MUESTRA overprint oblique"
                } ],
            "postal_stationery" : []
        }
    
    # Validate
    try:
        entry = MenaCatalogEntry(**example2)
        print("✅ Validation successful!")
        print(f"\nParsed entry: {entry.issue_data.title}")
        print(f"Number of stamps: {len(entry.stamps)}")
        print(f"\nJSON output:\n{entry.model_dump_json(indent=2, exclude_none=True)}")
    except Exception as e:
        print(f"❌ Validation error: {e}")