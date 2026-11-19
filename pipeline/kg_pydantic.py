"""
Costa Rica Philatelic Knowledge Graph - Unified Pydantic Models
Version: 2.0 - Updated for Pydantic v2.11.7
Author: CR-PhilKG Project

Este módulo define TODOS los nodos y relaciones para el grafo filatélico
unificado de Costa Rica, compatible con Scott y Mena.
"""

from typing import Optional, List, Dict, Any, Literal, Union, Annotated
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pydantic import (
    BaseModel, 
    Field, 
    field_validator,
    model_validator,
    ConfigDict,
    field_serializer
)
from uuid import uuid4


# ============================================================================
# ENUMS - Vocabularios Controlados
# ============================================================================

class CatalogSource(str, Enum):
    """Catálogos autorizados"""
    SCOTT = "Scott"
    MENA = "Mena"
    MICHEL = "Michel"
    YVERT = "Yvert"
    STANLEY_GIBBONS = "Stanley Gibbons"


class StampType(str, Enum):
    """Tipos de sellos según uso postal"""
    REGULAR = "Regular Postage"
    AIRMAIL = "Airmail"
    SEMI_POSTAL = "Semi-Postal"
    SPECIAL_DELIVERY = "Special Delivery"
    REGISTRATION = "Registration"
    POSTAGE_DUE = "Postage Due"
    OFFICIAL = "Official"
    NEWSPAPER = "Newspaper"
    PARCEL_POST = "Parcel Post"
    POSTAL_TAX = "Postal Tax"
    WAR_TAX = "War Tax"
    TELEGRAPH = "Telegraph"
    LOCAL = "Local"
    MILITARY = "Military"


class PhilatelicMaterialType(str, Enum):
    """Tipos de material filatélico"""
    ISSUED_STAMP = "Issued Stamp"
    ESSAY = "Essay"
    DIE_PROOF = "Die Proof"
    PLATE_PROOF = "Plate Proof"
    COLOR_PROOF = "Color Proof"
    SPECIMEN = "Specimen"
    TRIAL_COLOR = "Trial Color"
    REPRINT = "Reprint"
    FORGERY = "Forgery"
    CINDERELLA = "Cinderella"


class VarietyType(str, Enum):
    """Tipos de variedades"""
    PERFORATION_ERROR = "Perforation Error"
    COLOR_SHADE = "Color Shade"
    PAPER_VARIETY = "Paper Variety"
    WATERMARK_VARIETY = "Watermark Variety"
    OVERPRINT_ERROR = "Overprint Error"
    SURCHARGE_ERROR = "Surcharge Error"
    PRINTING_ERROR = "Printing Error"
    PLATE_VARIETY = "Plate Variety"
    DESIGN_VARIETY = "Design Variety"
    GUM_VARIETY = "Gum Variety"


class PrintingMethod(str, Enum):
    """Métodos de impresión"""
    ENGRAVED = "Engraved"
    LITHOGRAPHED = "Lithographed"
    TYPOGRAPHED = "Typographed"
    PHOTOGRAVURE = "Photogravure"
    OFFSET = "Offset"
    EMBOSSED = "Embossed"
    RECESS = "Recess"
    COMBINATION = "Combination"


class PaperType(str, Enum):
    """Tipos de papel"""
    WOVE = "Wove"
    LAID = "Laid"
    PELURE = "Pelure"
    GRANITE = "Granite"
    CHALK_SURFACED = "Chalk-Surfaced"
    INDIA = "India"
    CARD = "Card"
    BLUISH = "Bluish"
    YELLOWISH = "Yellowish"


class Condition(str, Enum):
    """Estado del sello"""
    MINT_NH = "Mint Never Hinged"
    MINT_LH = "Mint Lightly Hinged"
    MINT_H = "Mint Hinged"
    MINT_OG = "Mint Original Gum"
    MINT_NG = "Mint No Gum"
    USED = "Used"
    ON_COVER = "On Cover"
    ON_PIECE = "On Piece"


class RelationshipType(str, Enum):
    """Tipos de relaciones entre nodos"""
    BELONGS_TO_ISSUE = "BELONGS_TO_ISSUE"
    USES_DESIGN = "USES_DESIGN"
    VARIANT_OF = "VARIANT_OF"
    COLOR_VARIANT_OF = "COLOR_VARIANT_OF"
    PRECEDED_BY = "PRECEDED_BY"
    FOLLOWED_BY = "FOLLOWED_BY"
    PRINTED_FROM = "PRINTED_FROM"
    PROOF_OF = "PROOF_OF"
    ESSAY_FOR = "ESSAY_FOR"
    SPECIMEN_OF = "SPECIMEN_OF"
    OVERPRINTED_FROM = "OVERPRINTED_FROM"
    SURCHARGED_FROM = "SURCHARGED_FROM"
    DERIVED_FROM = "DERIVED_FROM"
    DESCRIBES = "DESCRIBES"
    SAME_AS = "SAME_AS"
    LIKELY_SAME_AS = "LIKELY_SAME_AS"
    HAS_DISCREPANCY = "HAS_DISCREPANCY"
    CORRECTED_BY = "CORRECTED_BY"
    PRINTED_BY = "PRINTED_BY"
    USED_FOR = "USED_FOR"
    HAS_NOTE = "HAS_NOTE"


# ============================================================================
# BASE MODELS - Común a ambos catálogos
# ============================================================================

class BaseNode(BaseModel):
    """Nodo base para todos los objetos del grafo"""
    id: str = Field(default_factory=lambda: str(uuid4()), description="UUID único")
    node_type: str = Field(..., description="Tipo de nodo")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    model_config = ConfigDict(
        use_enum_values=True,
        arbitrary_types_allowed=True,
        json_encoders={
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: float(v),
        }
    )
    
    # Serializers for special types
    @field_serializer('created_at', 'updated_at')
    def serialize_datetime(self, dt: Optional[datetime]) -> Optional[str]:
        return dt.isoformat() if dt else None


class MonetaryValue(BaseModel):
    """Valor monetario con moneda"""
    amount: Decimal = Field(..., ge=0, description="Monto")
    currency: str = Field(default="USD", description="Código ISO de moneda")
    
    @field_validator('amount', mode='before')
    @classmethod
    def parse_amount(cls, v):
        if isinstance(v, str):
            # Parsear "$1,000.50" → 1000.50
            v = v.replace('$', '').replace(',', '').strip()
        return Decimal(str(v))
    
    @field_serializer('amount')
    def serialize_amount(self, amount: Decimal) -> float:
        return float(amount)


class DateRange(BaseModel):
    """Rango de fechas"""
    start: Optional[date] = None
    end: Optional[date] = None
    circa: bool = Field(default=False, description="¿Es fecha aproximada?")
    note: Optional[str] = None


class Denomination(BaseModel):
    """Denominación del sello"""
    value: Decimal = Field(..., description="Valor numérico")
    unit: str = Field(..., description="Unidad (real, peso, centavo, colón)")
    display: Optional[str] = Field(None, description="Texto inscrito en sello")
    
    @field_validator('value', mode='before')
    @classmethod
    def parse_value(cls, v):
        if isinstance(v, str):
            # Parsear "1/2" → 0.5, "1/3" → 0.333
            if '/' in v:
                parts = v.split('/')
                return Decimal(parts[0]) / Decimal(parts[1])
        return Decimal(str(v))
    
    @field_serializer('value')
    def serialize_value(self, value: Decimal) -> float:
        return float(value)
    
    def __str__(self):
        return f"{self.value}{self.unit}"


class Perforation(BaseModel):
    """Información de perforación"""
    measurement: Optional[str] = Field(None, description="e.g., '12', '12x13'")
    type: Optional[str] = Field(None, description="uniform, compound, etc.")
    is_imperforate: bool = Field(default=False)
    details: Optional[str] = None
    
    @field_validator('measurement')
    @classmethod
    def validate_measurement(cls, v):
        if v and not v.replace('x', '').replace('.', '').replace(' ', '').isdigit():
            raise ValueError(f"Invalid perforation: {v}")
        return v


class ColorDescription(BaseModel):
    """Descripción de color"""
    primary: str = Field(..., description="Color principal")
    secondary: Optional[str] = Field(None, description="Color secundario")
    modifier: Optional[str] = Field(None, description="deep, dark, light, pale")
    full_description: Optional[str] = None
    
    def __str__(self):
        parts = []
        if self.modifier:
            parts.append(self.modifier)
        parts.append(self.primary)
        if self.secondary:
            parts.append(f"& {self.secondary}")
        return " ".join(parts)


# ============================================================================
# CATALOG ENTRY MODELS - Entradas específicas de catálogos
# ============================================================================

class ScottNumber(BaseModel):
    """Número Scott parseado"""
    full_number: str = Field(..., description="Número completo: e.g., 'C146a'")
    prefix: Optional[str] = Field(None, description="Prefijo: C, B, O, etc.")
    base_number: int = Field(..., description="Número base")
    major_suffix: Optional[str] = Field(None, pattern=r'^[A-Z]$', description="Sufijo mayor: A-Z")
    minor_suffix: Optional[str] = Field(None, pattern=r'^[a-z]+$', description="Sufijo menor: a-z")
    is_variety: bool = Field(default=False)
    
    @model_validator(mode='after')
    def construct_full_number(self):
        """Reconstruir full_number si falta"""
        if not self.full_number:
            parts = []
            if self.prefix:
                parts.append(self.prefix)
            parts.append(str(self.base_number))
            if self.major_suffix:
                parts.append(self.major_suffix)
            if self.minor_suffix:
                parts.append(self.minor_suffix)
            self.full_number = ''.join(parts)
        return self
    
    def __str__(self):
        return self.full_number


class MenaNumber(BaseModel):
    """Número Mena parseado"""
    full_number: str = Field(..., description="e.g., 'PP1a', 'DP4b', 'E1'")
    entry_type: PhilatelicMaterialType
    base_designation: Optional[str] = None
    suffix: Optional[str] = None
    
    def __str__(self):
        return self.full_number


class CatalogEntry(BaseNode):
    """Entrada genérica de catálogo (Scott o Mena)"""
    node_type: Literal["CatalogEntry"] = "CatalogEntry"
    catalog_source: CatalogSource
    catalog_number: Union[ScottNumber, MenaNumber]
    
    # Información básica
    denomination: Optional[Denomination] = None
    color: Optional[ColorDescription] = None
    year_issue: Optional[int] = Field(None, ge=1840, le=2030)
    date_issue: Optional[date] = None
    
    # Información técnica
    stamp_type: Optional[StampType] = None
    material_type: PhilatelicMaterialType = PhilatelicMaterialType.ISSUED_STAMP
    perforation: Optional[Perforation] = None
    printing_method: Optional[PrintingMethod] = None
    paper_type: Optional[PaperType] = None
    watermark: Optional[str] = None
    
    # Diseño
    illustration_number: Optional[str] = Field(None, description="e.g., 'A53', 'AP12'")
    design_description: Optional[str] = None
    
    # Valores de mercado
    mint_value: Optional[MonetaryValue] = None
    used_value: Optional[MonetaryValue] = None
    
    # Variedades
    is_variety: bool = False
    variety_type: Optional[VarietyType] = None
    variety_description: Optional[str] = None
    parent_stamp: Optional[str] = Field(None, description="ID del sello base")
    
    # Notas
    notes: List[str] = Field(default_factory=list)
    special_characteristics: List[str] = Field(default_factory=list)
    
    # Metadata del catálogo
    catalog_page: Optional[int] = None
    catalog_edition: Optional[str] = None


class ScottEntry(CatalogEntry):
    """Entrada específica de Scott"""
    node_type: Literal["ScottEntry"] = "ScottEntry"

    catalog_source: Literal[CatalogSource.SCOTT] = CatalogSource.SCOTT
    catalog_number: ScottNumber
    
    # Campos específicos de Scott
    illustration_type: Optional[str] = Field(None, description="A, AP, SP, etc.")
    set_range: Optional[str] = Field(None, description="e.g., '69-76 (8)'")
    
    # Cross-references Scott
    overprint_references: List[str] = Field(default_factory=list)
    surcharge_references: List[str] = Field(default_factory=list)
    related_scott_numbers: List[str] = Field(default_factory=list)


class MenaEntry(CatalogEntry):
    """Entrada específica de Mena"""
    node_type: Literal["MenaEntry"] = "MenaEntry"
    catalog_source: Literal[CatalogSource.MENA] = CatalogSource.MENA
    catalog_number: MenaNumber
    
    # Campos específicos de Mena (mucho más detalle)
    printer: Optional[str] = Field(None, description="e.g., 'ABNCo'")
    printer_full_name: Optional[str] = None
    die_number: Optional[str] = Field(None, description="e.g., '332', '388'")
    plate_number: Optional[int] = None
    
    # Información histórica (Mena tiene mucho más)
    decree_number: Optional[str] = None
    decree_date: Optional[date] = None
    circulation_date: Optional[date] = None
    demonetization_date: Optional[date] = None
    
    # Proofs y Essays
    proof_details: Optional[Dict[str, Any]] = None
    essay_details: Optional[Dict[str, Any]] = None
    
    # Producción
    sheet_format: Optional[str] = Field(None, description="e.g., 'panes of 100'")
    print_run: Optional[int] = None
    
    # Specimens
    specimen_overprint_color: Optional[str] = None
    specimen_details: Optional[str] = None
    
    # Referencias a Scott
    scott_equivalent: Optional[str] = Field(None, description="Número Scott relacionado")


# ============================================================================
# CANONICAL MODELS - El Merge Definitivo
# ============================================================================

class CanonicalStamp(BaseNode):
    """
    Nodo canónico que representa el SELLO REAL.
    Merge de toda la información de Scott + Mena.
    """
    node_type: Literal["CanonicalStamp"] = "CanonicalStamp"
    
    # Identificadores canónicos
    canonical_id: str = Field(..., description="ID único del sello real")
    country: str = Field(default="Costa Rica")
    
    # Denominación canónica (resuelta)
    denomination: Denomination
    denomination_note: Optional[str] = Field(
        None, 
        description="Nota sobre discrepancias (e.g., 'Scott lists 1/3r but stamp says MEDIO REAL')"
    )
    
    # Información visual
    color: ColorDescription
    design_type: Optional[str] = None
    design_description: Optional[str] = None
    inscription: Optional[str] = Field(None, description="Texto en el sello")
    
    # Información técnica (authoritative)
    year_issue: int
    date_issue: Optional[date] = None
    stamp_type: StampType
    perforation: Perforation
    printing_method: PrintingMethod
    paper_type: Optional[PaperType] = None
    watermark: Optional[str] = None
    
    # Producción (principalmente de Mena)
    printer: Optional[str] = None
    printer_full_name: Optional[str] = None
    die_number: Optional[str] = None
    plate_number: Optional[int] = None
    sheet_format: Optional[str] = None
    print_run: Optional[int] = None
    
    # Historia (principalmente de Mena)
    decree_info: Optional[str] = None
    circulation_info: Optional[str] = None
    demonetization_date: Optional[date] = None
    historical_notes: List[str] = Field(default_factory=list)
    
    # Valores (principalmente de Scott)
    mint_value: Optional[MonetaryValue] = None
    used_value: Optional[MonetaryValue] = None
    value_notes: Optional[str] = None
    
    # Rareza y características
    rarity_level: Optional[str] = None
    is_key_stamp: bool = False
    special_characteristics: List[str] = Field(default_factory=list)
    
    # Referencias a catálogos
    catalog_references: Dict[str, str] = Field(
        default_factory=dict,
        description="{'Scott': '1', 'Mena': 'M1', 'Michel': '1'}"
    )
    
    # Authority tracking
    denomination_authority: CatalogSource = Field(
        default=CatalogSource.MENA,
        description="Qué catálogo es autoritativo para denominación"
    )
    technical_details_authority: CatalogSource = Field(
        default=CatalogSource.MENA,
        description="Qué catálogo es autoritativo para detalles técnicos"
    )
    market_value_authority: CatalogSource = Field(
        default=CatalogSource.SCOTT,
        description="Qué catálogo es autoritativo para valores"
    )
    
    # Confidence score
    merge_confidence: Annotated[float, Field(ge=0.0, le=1.0)] = Field(
        default=1.0,
        description="Confianza en el merge (0-1)"
    )
    requires_review: bool = Field(default=False)


# ============================================================================
# ISSUE MODELS - Emisiones
# ============================================================================

class Issue(BaseNode):
    """Emisión/Serie postal"""
    node_type: Literal["Issue"] = "Issue"
    
    # Identificación
    issue_id: str = Field(..., description="e.g., 'cr_1863_first'")
    country: str = Field(default="Costa Rica")
    year: int = Field(..., ge=1840, le=2030)
    issue_name: str = Field(..., description="e.g., '1863 First Issue - Coat of Arms'")
    
    # Rango de catálogo
    scott_range: Optional[str] = Field(None, description="e.g., '1-4', '69-76'")
    total_stamps: Optional[int] = None
    
    # Información técnica
    perforation: Optional[str] = None
    perforation_type: Optional[str] = None
    printing_method: Optional[PrintingMethod] = None
    watermark: Optional[str] = None
    paper_type: Optional[PaperType] = None
    
    # Producción
    printer: Optional[str] = None
    printer_full_name: Optional[str] = None
    sheet_format: Optional[str] = None
    
    # Historia administrativa
    authorizing_decree: Optional[str] = None
    decree_date: Optional[date] = None
    circulation_dates: Optional[Dict[str, str]] = None
    demonetization_date: Optional[date] = None
    
    # Valores del set
    set_mint_value: Optional[MonetaryValue] = None
    set_used_value: Optional[MonetaryValue] = None
    
    # Notas
    historical_context: Optional[str] = None
    special_notes: List[str] = Field(default_factory=list)
    
    # Significancia
    is_first_issue: bool = False
    historical_significance: Optional[str] = None


# ============================================================================
# DESIGN & PRODUCTION MODELS
# ============================================================================

class DesignType(BaseNode):
    """Tipo de diseño (illustration number)"""
    node_type: Literal["DesignType"] = "DesignType"
    
    illustration_number: str = Field(..., description="e.g., 'A1', 'A53', 'AP12'")
    design_name: Optional[str] = Field(None, description="e.g., 'Coat of Arms'")
    design_description: Optional[str] = None
    designer: Optional[str] = None
    engraver: Optional[str] = None
    
    # Características visuales
    depicts: Optional[str] = Field(None, description="What the design shows")
    theme: Optional[str] = None
    
    # Stamps que usan este diseño
    used_by_stamps: List[str] = Field(default_factory=list, description="Lista de stamp IDs")


class PrintingPlate(BaseNode):
    """Plancha de impresión"""
    node_type: Literal["PrintingPlate"] = "PrintingPlate"
    
    plate_number: int
    plate_id: str = Field(..., description="e.g., 'plate_1_first'")
    stamp_denomination: str
    
    # Características
    color: Optional[str] = None
    distinguishing_features: Optional[str] = None
    creation_reason: Optional[str] = Field(
        None, 
        description="e.g., 'Original plate developed a crack'"
    )
    date_in_use: Optional[date] = None
    
    # Referencias
    produces_stamps: List[str] = Field(default_factory=list)


class Printer(BaseNode):
    """Impresor (e.g., ABNCo)"""
    node_type: Literal["Printer"] = "Printer"
    
    name: str = Field(..., description="e.g., 'ABNCo'")
    full_name: Optional[str] = Field(None, description="American Bank Note Company")
    country: Optional[str] = None
    specialty: Optional[str] = None
    active_period: Optional[str] = None
    
    # Contratos
    contracts_with_countries: List[str] = Field(default_factory=list)


class DieNumber(BaseNode):
    """Número de cuño ABNCo"""
    node_type: Literal["DieNumber"] = "DieNumber"
    
    die_number: str = Field(..., description="e.g., '332', '388'")
    denomination: str
    country: str
    year: int
    printer: str = Field(default="ABNCo")


# ============================================================================
# PRE-PRODUCTION MATERIAL (Principalmente Mena)
# ============================================================================

class Essay(BaseNode):
    """Ensayo - diseño no adoptado"""
    node_type: Literal["Essay"] = "Essay"
    
    mena_number: str = Field(..., description="e.g., 'E1'")
    description: str
    color: Optional[ColorDescription] = None
    paper: Optional[PaperType] = None
    mount: Optional[str] = Field(None, description="e.g., 'on card'")
    technique: Optional[str] = Field(None, description="e.g., 'hand painted'")
    
    # Relacionado a
    intended_denomination: Optional[str] = None
    related_to_stamp: Optional[str] = Field(None, description="Scott number si existe")
    
    # Provenance
    provenance: Optional[str] = None
    rarity: Optional[str] = None


class DieProof(BaseNode):
    """Prueba de cuño"""
    node_type: Literal["DieProof"] = "DieProof"
    
    mena_number: str = Field(..., description="e.g., 'DP1', 'DP4a'")
    denomination: str
    color: ColorDescription
    die_number: str = Field(..., description="ABNCo die number")
    
    # Características
    paper: PaperType = PaperType.INDIA
    format: str = Field(default="imperf or sunk on card")
    is_color_variant: bool = False
    
    # Referencias
    scott_related_to: Optional[str] = None
    proof_type: Literal["die_proof"] = "die_proof"


class PlateProof(BaseNode):
    """Prueba de plancha"""
    node_type: Literal["PlateProof"] = "PlateProof"
    
    mena_number: str = Field(..., description="e.g., 'PP1', 'PP4b'")
    denomination: str
    color: ColorDescription
    plate: Optional[int] = None
    
    # Características
    paper: Optional[PaperType] = PaperType.INDIA
    format: str = Field(default="imperf or on card")
    is_color_variant: bool = False
    
    # Referencias
    scott_related_to: Optional[str] = None
    proof_type: Literal["plate_proof"] = "plate_proof"


class Specimen(BaseNode):
    """Muestra con sobrecarga SPECIMEN"""
    node_type: Literal["Specimen"] = "Specimen"
    
    mena_number: str = Field(..., description="e.g., 'S1a'")
    denomination: str
    base_color: ColorDescription
    overprint_color: str
    overprint_text: str = Field(default="SPECIMEN")
    
    # Base
    paper: Optional[PaperType] = None
    scott_related_to: Optional[str] = None
    proof_type: Literal["specimen"] = "specimen"


# ============================================================================
# DISCREPANCY & VALIDATION MODELS
# ============================================================================

class CatalogDiscrepancy(BaseNode):
    """Discrepancia entre catálogos"""
    node_type: Literal["CatalogDiscrepancy"] = "CatalogDiscrepancy"
    
    affects_stamp: str = Field(..., description="Canonical stamp ID")
    discrepancy_type: str = Field(
        ..., 
        description="denomination_error, color_mismatch, date_conflict, etc."
    )
    
    # Valores en conflicto
    scott_value: Optional[Any] = None
    mena_value: Optional[Any] = None
    other_values: Dict[str, Any] = Field(default_factory=dict)
    
    # Resolución
    resolved_value: Optional[Any] = None
    resolution_authority: Optional[CatalogSource] = None
    resolution_evidence: Optional[str] = None
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] = Field(default=0.5)
    
    # Notas
    description: str
    resolution_note: Optional[str] = None
    requires_expert_review: bool = False


class PhilatelicNote(BaseNode):
    """Nota filatélica general"""
    node_type: Literal["PhilatelicNote"] = "PhilatelicNote"
    
    note_type: str = Field(..., description="imperforate_explanation, usage_note, etc.")
    applies_to: List[str] = Field(..., description="Lista de stamp IDs")
    description: str
    source: Optional[CatalogSource] = None


# ============================================================================
# RELATIONSHIP MODELS
# ============================================================================

class Relationship(BaseModel):
    """Relación genérica entre nodos"""
    relationship_id: str = Field(default_factory=lambda: str(uuid4()))
    relationship_type: RelationshipType
    
    source_id: str = Field(..., description="ID del nodo origen")
    source_type: str = Field(..., description="Tipo del nodo origen")
    
    target_id: str = Field(..., description="ID del nodo destino")
    target_type: str = Field(..., description="Tipo del nodo destino")
    
    # Propiedades de la relación
    properties: Dict[str, Any] = Field(default_factory=dict)
    
    # Metadata
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] = Field(default=1.0)
    created_at: datetime = Field(default_factory=datetime.now)
    created_by: str = Field(default="system")
    notes: Optional[str] = None
    
    model_config = ConfigDict(use_enum_values=True)


# ============================================================================
# CURRENCY SYSTEM
# ============================================================================

class CurrencyUnit(BaseModel):
    """Unidad monetaria"""
    unit: str = Field(..., description="real, peso, centavo, colón")
    plural: Optional[str] = None
    abbreviation: Optional[str] = None
    value_in_base: Optional[Decimal] = Field(
        None, 
        description="Valor en unidad base (e.g., real=1, peso=8)"
    )
    
    @field_serializer('value_in_base')
    def serialize_value_in_base(self, value: Optional[Decimal]) -> Optional[float]:
        return float(value) if value else None


class CurrencySystem(BaseNode):
    """Sistema monetario de un período"""
    node_type: Literal["CurrencySystem"] = "CurrencySystem"
    
    country: str = Field(default="Costa Rica")
    period_start: date
    period_end: Optional[date] = None
    
    units: List[CurrencyUnit]
    conversion_info: Optional[str] = None
    
    # Decimal conversion (si aplica)
    decimal_adoption_date: Optional[date] = None
    decimal_conversions: Dict[str, str] = Field(
        default_factory=dict,
        description="{'1/2 real': '12.5 centavos'}"
    )


# ============================================================================
# HELPER MODELS - Para procesamiento
# ============================================================================

class ParsingResult(BaseModel):
    """Resultado del parsing de un issue"""
    issue_id: str
    catalog_source: CatalogSource
    
    # Nodos extraídos
    issue: Optional[Issue] = None
    catalog_entries: List[Union[ScottEntry, MenaEntry]] = Field(default_factory=list)
    design_types: List[DesignType] = Field(default_factory=list)
    
    # Material pre-producción (solo Mena)
    essays: List[Essay] = Field(default_factory=list)
    die_proofs: List[DieProof] = Field(default_factory=list)
    plate_proofs: List[PlateProof] = Field(default_factory=list)
    specimens: List[Specimen] = Field(default_factory=list)
    
    # Relaciones identificadas
    relationships: List[Relationship] = Field(default_factory=list)
    
    # Metadata
    raw_text: Optional[str] = None
    parsing_confidence: Annotated[float, Field(ge=0.0, le=1.0)] = Field(default=1.0)
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class MergeResult(BaseModel):
    """Resultado del merge Scott + Mena"""
    canonical_stamp: CanonicalStamp
    
    # Referencias originales
    scott_entry: Optional[ScottEntry] = None
    mena_entry: Optional[MenaEntry] = None
    
    # Material adicional de Mena
    related_proofs: List[Union[DieProof, PlateProof]] = Field(default_factory=list)
    related_essays: List[Essay] = Field(default_factory=list)
    related_specimens: List[Specimen] = Field(default_factory=list)
    
    # Discrepancias
    discrepancies: List[CatalogDiscrepancy] = Field(default_factory=list)
    
    # Relaciones creadas
    relationships: List[Relationship] = Field(default_factory=list)
    
    # Metadata del merge
    merge_method: str = Field(default="llm_assisted")
    merge_confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    requires_review: bool
    merge_notes: List[str] = Field(default_factory=list)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def create_scott_number(full: str) -> ScottNumber:
    """
    Parse a Scott number string into ScottNumber object.
    
    Examples:
        "69" -> ScottNumber(base=69)
        "C146a" -> ScottNumber(prefix="C", base=146, minor_suffix="a")
        "16A" -> ScottNumber(base=16, major_suffix="A")
    """
    import re
    
    pattern = r'^([A-Z]{1,4})?(\d+)([A-Z])?([a-z]+)?$'
    match = re.match(pattern, full)
    
    if not match:
        raise ValueError(f"Invalid Scott number: {full}")
    
    prefix, base, major, minor = match.groups()
    
    return ScottNumber(
        full_number=full,
        prefix=prefix,
        base_number=int(base),
        major_suffix=major,
        minor_suffix=minor,
        is_variety=bool(minor)
    )


def create_relationship(
    source: BaseNode,
    target: BaseNode,
    rel_type: RelationshipType,
    **properties
) -> Relationship:
    """Helper para crear relaciones fácilmente"""
    return Relationship(
        relationship_type=rel_type,
        source_id=source.id,
        source_type=source.node_type,
        target_id=target.id,
        target_type=target.node_type,
        properties=properties
    )


# ============================================================================
# VALIDATION HELPERS
# ============================================================================

class ValidationRule(BaseModel):
    """Regla de validación"""
    rule_name: str
    rule_type: str  # "consistency", "completeness", "plausibility"
    description: str
    
    def validate(self, node: BaseNode) -> tuple[bool, Optional[str]]:
        """Override en subclases"""
        return True, None


class DenominationConsistencyRule(ValidationRule):
    """Valida que denominación sea consistente con inscripción"""
    rule_name: str = "denomination_consistency"
    rule_type: str = "consistency"
    description: str = "Denomination must match stamp inscription"
    
    def validate(self, stamp: CanonicalStamp) -> tuple[bool, Optional[str]]:
        if stamp.inscription and stamp.denomination:
            # Si dice "MEDIO REAL" debe ser 1/2 real
            if "MEDIO REAL" in stamp.inscription.upper():
                if stamp.denomination.value != Decimal("0.5"):
                    return False, f"Inscription says MEDIO REAL but denomination is {stamp.denomination.value}"
        return True, None


# ============================================================================
# EXPORT TO NEO4J
# ============================================================================

class Neo4jNode(BaseModel):
    """Formato para exportar a Neo4j"""
    labels: List[str] = Field(..., description="Node labels")
    properties: Dict[str, Any] = Field(..., description="Node properties")
    
    @classmethod
    def from_base_node(cls, node: BaseNode) -> "Neo4jNode":
        """Convert any BaseNode to Neo4j format"""
        labels = [node.node_type]
        
        # Serializar a dict, manejando tipos especiales
        props = node.model_dump(exclude={'id', 'node_type'})
        props['_id'] = node.id  # Neo4j puede usar su propio ID
        
        return cls(labels=labels, properties=props)


class Neo4jRelationship(BaseModel):
    """Formato para exportar relación a Neo4j"""
    type: str
    start_node_id: str
    end_node_id: str
    properties: Dict[str, Any]
    
    @classmethod
    def from_relationship(cls, rel: Relationship) -> "Neo4jRelationship":
        return cls(
            type=rel.relationship_type.value,
            start_node_id=rel.source_id,
            end_node_id=rel.target_id,
            properties=rel.properties
        )


# ============================================================================
# EJEMPLO DE USO
# ============================================================================

if __name__ == "__main__":
    # Ejemplo: Crear Scott 1 (1863)
    scott_1 = ScottEntry(
        catalog_number=create_scott_number("1"),
        denomination=Denomination(value=Decimal("0.5"), unit="real", display="MEDIO REAL"),
        color=ColorDescription(primary="blue"),
        year_issue=1863,
        stamp_type=StampType.REGULAR,
        perforation=Perforation(measurement="12"),
        printing_method=PrintingMethod.ENGRAVED,
        illustration_number="A1",
        mint_value=MonetaryValue(amount=Decimal("0.50")),
        used_value=MonetaryValue(amount=Decimal("1.10"))
    )
    
    # Ejemplo: Crear Mena Die Proof
    mena_dp1 = DieProof(
        mena_number="DP1",
        denomination="1/2 real",
        color=ColorDescription(primary="black"),
        die_number="332",
        scott_related_to="1"
    )
    
    # Ejemplo: Crear relación
    rel = create_relationship(
        source=mena_dp1,
        target=scott_1,
        rel_type=RelationshipType.PROOF_OF
    )
    
    # Print JSON
    print("Scott Entry:")
    print(scott_1.model_dump_json(indent=2, exclude_none=True))
    
    print("\nMena Die Proof:")
    print(mena_dp1.model_dump_json(indent=2, exclude_none=True))
    
    print("\nRelationship:")
    print(rel.model_dump_json(indent=2))