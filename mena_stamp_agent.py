"""
Mena Stamp Catalogue Parser Agent usando BeeAI Framework
==========================================================

Parses Mena Catalogue–style stamp descriptions into structured data.

- Validates fields with Pydantic models.
- Uses LangChain few-shot examples (in the system prompt) to guide parsing.
- Applies ThinkTool for lightweight reasoning and self-checks.
- Enforces required fields and flow with RequirementAgent.
- Implements a ReAct loop with RETRY: on validation failure, it reflects,
  adjusts, and retries up to 3 times before returning a concise error.

Inputs: raw Mena-style description text (+ optional context).
Outputs: validated Pydantic objects ready for indexing or export.

"""

import asyncio
from typing import Optional, List, Any
from enum import Enum
from datetime import date

# Pydantic para esquema de datos
from pydantic import BaseModel, Field, validator, ConfigDict

# BeeAI Framework imports
from beeai_framework.agents.experimental import RequirementAgent
from beeai_framework.agents.experimental.requirements.conditional import ConditionalRequirement
from beeai_framework.backend import ChatModel
from beeai_framework.tools.think import ThinkTool
from beeai_framework.tools import Tool
from beeai_framework.memory import UnconstrainedMemory
from beeai_framework.backend import ChatModel, ChatModelParameters, UserMessage, SystemMessage
from beeai_framework.tools import StringToolOutput, Tool, ToolRunOptions
from beeai_framework.context import RunContext
from beeai_framework.emitter import Emitter
from beeai_framework.tools.handoff import HandoffTool
from beeai_framework.middleware.trajectory import GlobalTrajectoryMiddleware
from beeai_framework.agents.experimental.requirements.ask_permission import AskPermissionRequirement


# LangChain imports para few-shot prompting
from langchain_core.prompts import (
    ChatPromptTemplate,
    FewShotChatMessagePromptTemplate,
    MessagesPlaceholder,
)
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
import json


# ============================================================================
# Step 1: Pydantic Schema for Mena Parser
# ============================================================================
from mena_catalog_schema import *


# ============================================================================
# Step 2: Few-Shot Examples using LangChain
# ============================================================================

def create_system_message():
    """
    A system prompt for Mena Catalogue parser with structured output.
    Focuses on interpretation rules and philatelic domain knowledge.  
    
    """
    
    system_message = """
    You are a structured parser for the Mena Catalog (Costa Rica). Extract data into ONE JSON object
    with EXACTLY these top-level keys:
    - "issue_data"
    - "production_orders"
    - "stamps"
    - "varieties"
    - "proofs"
    - "essays"
    - "specimens"
    - "postal_stationery"

    Return the FULL schema even if empty. If a section doesn't appear, return it as empty containers:
    - lists as []
    - maps as {{}}
    - dates as null
    - strings as ""

    Output schema (types and intent):

    issue_data:
      - issue_id (string): Stable unique ID (recommend COUNTRY-YYYY[-YYYY]-TITLE).
      - section (string): Catalog section (e.g., "Surface Mail").
      - title (string): Issue title as printed.
      - country (string): Country name.
      - issue_dates (object):
          announced | placed_on_sale | probable_first_circulation | second_plate_sale | demonetized (ISO or null)
      - legal_basis (array of objects):
          {{ type: "decree"|"law"|"letter"|"resolution"|..., id: string, date: ISO|null, ids: [], officials: [] }}
      - currency_context (object):
          original (string), decimal_adoption (ISO|null), revaluation_date (ISO|null), revaluation_map (object string->string)
      - printing (object):
          printer (string), process (string[]), format {{ panes: number|null }}, plates {{ "<denom_token>": {{ plates: number[], notes: string[] }} }}
      - perforation (string): numeric gauge like "12" if specified, else "".

    production_orders:
      - printings (array):
          {{ date: ISO|null, quantities: [ {{ plate_desc: string, quantity: number }} ] }}
      - remainders (object):
          {{ date: ISO|null, note: string, quantities: [ {{ plate_desc: string, quantity: number }} ] }}

    stamps (regular issues + souvenir sheets):
      - array of objects with these fields:
        
        FOR REGULAR STAMPS:
        {{
          catalog_no: string,                       // e.g., "54", "83", "1A"
          issue_id: string,                         // link to issue_data.issue_id
          denomination: {{                          // resulting face value of the issued stamp
            value: number,
            unit: "c" | "C" | "P" | "reales"        // normalize: centavo/cts/centime -> "c"; Colón -> "C"; Peso -> "P"; real/reales -> "reales"
          }},
          color: string,                            // "" if not stated
          plate: number | null,                     // null if not given
          perforation: string | "",                 // gauge only (e.g., "12"); "" if unknown (do NOT include "perf")
          watermark: string | null,                 // null if not mentioned
          quantity_reported: number | null,         // ONLY if the specific catalog number line states a quantity; else null
          status: "regular",                        // ALWAYS "regular" for regular stamps
          notes: string[],                          // [] if none

          // ONLY when the REGULAR stamp line itself is a surcharge/overprint listing (e.g., "2c/10C"):
          overprint?: {{
            present: boolean,
            type: "surcharge" | "overprint" | "bar_cancel" | "other",
            surcharge_denomination?: {{ value: number, unit: "c" | "C" | "P" | "reales" }},
            on_denomination?: {{ value: number, unit: "c" | "C" | "P" | "reales" }},
            color?: string
          }},
          base_stamp_ref?: string                   // optional cross-ref (e.g., "1", "1A", "091")
        }}
        
        FOR SOUVENIR SHEETS (SS codes):
        {{
          catalog_no: string,                       // e.g., "SSA752", "SS123"
          issue_id: string,                         // link to issue_data.issue_id
          denomination: {{
            value: null,                            // ALWAYS null for souvenir sheets
            unit: "sheet"                           // ALWAYS "sheet" for souvenir sheets
          }},
          color: string,                            // often "multicolor"
          plate: number | null,                     // usually null
          perforation: string | "",                 // gauge if perforated (e.g., "10.5"), "" if imperf
          watermark: string | null,                 // usually null
          quantity_reported: number | null,         // from table if available
          status: "souvenir_sheet",                 // ALWAYS "souvenir_sheet" for SS codes
          notes: string[],                          // describe contents: ["Souvenir sheet with 5 values perf and island map"]
          
          // OPTIONAL: list of stamps contained in the sheet
          sheet_contents?: string[]                 // e.g., ["A747", "A748", "A749", "A750", "A751"]
                                                    // Only populate if text explicitly lists which stamps
                                                    // Otherwise omit field or use []
        }}

    varieties:
      - array of:
        {{
          base_catalog_no: string,                 // base main number (e.g., "31", "1A")
          suffix: string,                          // LOWERCASE suffix only (e.g., "a", "b")
          type: "perforation"|"impression"|"plate_flaw"|"overprint"|"surcharge"|"color"|"color_shift"|"watermark"|"paper"|"gumming"|"other",
          description: string,
          position: string|null,
          plate: number|null
        }}

    proofs:
      - die_proofs: [
          {{ code: string, denomination: string, color: string, die_no: string, substrate: string, finish: string }}
        ]
      - plate_proofs: [
          {{ code: string, note: string, items: [ {{ variant: string, denomination: string, color: string, plate: number|null, note: string }} ] }}
        ]
      - color_proofs: [ {{ code: string, denomination: string, color: string, notes: string }} ]
      - imperforate_proofs: [ {{ code: string, denomination: string, notes: string }} ]

    essays:
      - [ {{ code: string, medium: string, paper: string, denomination: string, provenance: string[], notes: string[] }} ]

    specimens:
      - [ {{ code: string, applies_to: "proofs"|"stamps", type: "overprint"|"punch"|"perfin"|"handstamp"|string, denomination: string, base_color: string, overprint_color: string, notes: string }} ]
    postal_stationery: [
      {{
        catalog_no: string,                    // e.g., "PC1", "EN5", "LS1", "OEN2", "W1"
        issue_id: string,
        stationery_type: "postal_card" | "envelope" | "aerogramme" | "official_envelope" | "wrapper",
        denomination: {{
          value: number,
          unit: "c" | "C" | "P"
        }},
        color: string,                         // printed color
        paper: string,                         // e.g., "buff manila", "white laid", "thick paper"
        size: string,                          // dimensions (e.g., "132 x 80 mm", "138 x 80 mm")
        quantity_reported: number|null,
        notes: string[],
        
        // OPTIONAL fields (only when applicable):
        card_type?: "single" | "reply" | "double",  // only for postal_card type
        overprint?: {{                         // for official envelopes with overprints
          present: boolean,
          type: "overprint" | "surcharge",
          text: string,                        // e.g., "Servicio Oficial", "Libre de Porte"
          color: string
        }},
        base_ref?: string                      // if overprinted on another stationery item
      }}
    ]

    CRITICAL: Only populate postal_stationery if the input text explicitly 
    mentions postal cards (PC), envelopes (EN), aerogrammes (LS), wrappers (W), 
    or letter sheets.

    If there is NO mention of postal stationery in the input, return:
    "postal_stationery": []

    NEVER invent postal stationery data.

    --------------------------------------------------------------------------------
    HARD SEPARATION: SPECIMENS vs VARIETIES (NEVER MIX)
    --------------------------------------------------------------------------------
    A) SPECIMENS (S-codes)
    - Detector: any line that BEGINS with uppercase "S" + digits + optional lowercase (regex: ^S\\d+[a-z]?$).
    - Each S-code MUST yield ONE item in top-level "specimens".
    - NEVER place S-codes under "varieties", "proofs", or inside "stamps".
    - "applies_to": default "stamps". Use "proofs" ONLY if the text explicitly binds that S-code to proofs.
    - "type": default "overprint" unless the line explicitly indicates "punch", "perfin", "handstamp", etc.
    - 'Muestra' is an special specimen that is an overprint and always starts with MA, example: "MA46a bk 10c scarlet" → code: MA46a, overprint_color: black, denomination: 10c, base_color: scarlet
    - "denomination": take the face value and unit on the same row if present; if not, inherit from the row header ONLY if unambiguous; otherwise "".
    - "base_color": color BEFORE the overprint phrase, lowercased.
    - "overprint_color": keep orientation adjectives (e.g., "black", "red", "in a black circle").
    - "notes": carry remaining qualifiers (e.g., "imperforate; ungummed thin paper with hole"; "Perf 12.5"; "salesman samples").
    - IMPORTANT: Even if an S-code mentions “inverted overprint” or “Perf 12.5”, it REMAINS a specimen and stays in "specimens" (not in "varieties").

    B) VARIETIES (lowercase suffixes of MAIN numbers)
    - Detector: main catalog number + lowercase suffix (e.g., "31a", "33b", "1Aa").
    - Keep ONLY these in "varieties".
    - Uppercase letter immediately after digits forms a MAIN number (e.g., "1A"): keep in "stamps", not "varieties".
    - Typical entries: imperf between, margin imperf, inverted OP of a REGULAR non-S specimen, paper, watermark, color shade, plate flaw.
    - **VARIETY BASE NUMBER**:
      Always use catalog number from Column 1 as base_catalog_no, even if variety code in Column 2 
      contains a different number. Example: <tr><td>34</td><td>33d</td></tr> → base_catalog_no: "34", suffix: "d"
    Collision resolution:
    - If a feature appears both in a REGULAR listing and in an S-code list:
      • Regular listing feature → "varieties".
      • S-code feature → keep inside that S-code item in "specimens" (as type/notes). Do NOT mirror it into "varieties".

    --------------------------------------------------------------------------------
    PROGRESSIVE DIES & SPECIAL CASES
    --------------------------------------------------------------------------------
    - Progressive die (e.g., “DPA31a vignette only”): put under "proofs.die_proofs" as:
      {{ code: "DPA31a", denomination: "", color: "", die_no: "", substrate: "", finish: "progressive: vignette only" }}
    - Bar cancels: only use stamps[].overprint.type = "bar_cancel" when the main regular line defines it as such.
    - Do NOT convert progressive dies or salesman sheets into "varieties".

    --------------------------------------------------------------------------------
    NON-ISSUED STAMPS (NEA CODES)
    --------------------------------------------------------------------------------
    When a table shows specimen categories including "without overprint" or 
    "non-emis", these are non-issued stamps that should be captured in specimens.

    DETECTION:
    - Code pattern: NEA\d+[a-z]?
    - Table columns showing: I. Without overprint, II. specimen, III. muestra

    FIELD ASSIGNMENT:
    - code: as written (NEA46, NEA47, etc.)
    - applies_to: "stamps"
    - type: "non-issued" or "unissued"
    - overprint_color: "" (no overprint)
    - notes: "non-issued stamp without overprint" or similar

    These are distinct from regular specimens (SNEA, MNEA, MA codes).

    --------------------------------------------------------------------------------
    CONSTANT VARIETIES - EXPANSION RULE
    --------------------------------------------------------------------------------
    When text contains "Constant [X] varieties in [Y]:" followed by variety list,
    these varieties apply to ALL items in the specified range, not just one.

    DETECTION PATTERNS:
    1. "Constant overprint plate varieties in regular issue"
      → Apply to all regular stamps in the issue
      
    2. "Constant varieties in regular issue and 'muestra' overprints"
      → Apply to all regular stamps AND note in muestra specimens
      
    3. "Constant plate varieties"
      → Apply to all stamps using that plate

    IMPLEMENTATION:
    When parsing varieties section, if header says "Constant ... varieties in [scope]":

    Step 1: Parse the variety definitions:
      a: description (pos X)
      b: description (pos Y)
      
    Step 2: Identify the applicable range:
      - If "in regular issue": apply to ALL stamps with status="regular"
      - If "in stamps A46-A52": apply to that specific range
      - If no range specified: apply to all stamps in current issue
      
    Step 3: For EACH stamp in range, create variety entry:
      {{
        "base_catalog_no": "<stamp_catalog_no>",
        "suffix": "<variety_letter>",
        "type": "<variety_type>",
        "description": "<variety_description>",
        "position": "<pos if specified>",
        "plate": <plate_number if known>
      }}

    EXAMPLE FROM CURRENT TEST:
    Input:
      Regular stamps: A46, A47, A48, A49, A50, A51, A52, A53, A54
      "Constant overprint plate varieties in regular issue:
      a: hyphen missing between 2 and Diciembre (pos 13)
      b: DJA for DIA (pos 49)"

    Output varieties[] should contain 18 entries:
      - A46a, A46b
      - A47a, A47b
      - A48a, A48b
      - A49a, A49b
      - A50a, A50b
      - A51a, A51b
      - A52a, A52b
      - A53a, A53b
      - A54a, A54b

    All with the same descriptions but different base_catalog_no.

    --------------------------------------------------------------------------------
    OVERPRINT PROOFS (OP codes)
    --------------------------------------------------------------------------------
    Codes starting with "OP" (e.g., OPA46, OPB23) are OVERPRINT PROOFS.
    These should be placed in "proofs.plate_proofs", NOT in "imperforate_proofs".

    --------------------------------------------------------------------------------
    UNIT NORMALIZATION
    --------------------------------------------------------------------------------
    - UNITS normalization:
      • "c", "cent", "centavo", "centavos", "cts", "centime" -> "c"
      • Capital "C" = "Colón", MUST remain "C"
      • "P" = "Peso"; "real"/"reales" -> "reales"


    Pattern recognition:
    - "1.35C" → unit: "C" (Colón, not centavo)
    - "5C" → unit: "C" (Colón)
    - "10C" → unit: "C" (Colón)
    - "10c" → unit: "c" (centavo | centimo | cts)
    - "75c" → unit: "c" (centavo | centimo | cts)

    MUST preserve the case of the unit letter from the source.
    Never convert "C" → "c" or vice versa.

    --------------------------------------------------------------------------------
    DENOMINATIONS & SURCHARGES ("/" RULE)
    --------------------------------------------------------------------------------
    - "2c/10C" means a surcharge: the result denomination is 2c; base was 10C.
    - Populate:
      "denomination": {{ "value": 2, "unit": "c" }}
      "overprint": {{
        "present": true,
        "type": "surcharge",
        "surcharge_denomination": {{ "value": 2, "unit": "c" }},
        "on_denomination": {{ "value": 10, "unit": "C" }}
      }}
      
    --------------------------------------------------------------------------------
    DENOMINATION EXTRACTION - NO AUTO-CONVERSION
    --------------------------------------------------------------------------------
    CRITICAL: Extract denomination EXACTLY as written in the source.

    NEVER convert between units automatically:
    - If source says "90c" → value: 90, unit: "c" (NOT 0.9C)
    - If source says "0.9C" → value: 0.9, unit: "C" (NOT 90c)
    - If source says "2.10C" → value: 2.1, unit: "C"

    Even though 100 centavos = 1 Colón in Costa Rica, do NOT perform conversions.
    The denomination must reflect what is PRINTED on the stamp, not mathematical equivalents.


    --------------------------------------------------------------------------------
    SURCHARGE STAMPS - COLOR FIELD EXTRACTION
    --------------------------------------------------------------------------------
    For stamps with surcharge format: "Xc on Yc COLOR, in COLOR2"

    Example: "10c on 15c green, in black"
            "35c on 50c violet, in orange"

    PARSING RULES:
    1. denomination = Xc (the NEW value after surcharge)
    2. color = COLOR (ONLY the color of the BASE stamp)
    3. overprint.surcharge_denomination = Xc
    4. overprint.on_denomination = Yc
    5. overprint.color = COLOR2 (from "in COLOR2")

    CRITICAL: The "color" field must contain ONLY the base stamp color.
    Do NOT include the entire phrase "on Yc COLOR, in COLOR2".

    --------------------------------------------------------------------------------
    SOUVENIR SHEETS
    --------------------------------------------------------------------------------
    Souvenir sheets (SS codes like SSA752, SS123) are special collectible formats.

    DETECTION: Codes starting with "SS" followed by optional letter and numbers

    STRUCTURE (in stamps[] array):
    {{
      "catalog_no": "SSA752",
      "denomination": {{"value": null, "unit": "sheet"}},
      "status": "souvenir_sheet",
      "color": "multicolor",
      "perforation": "10.5",
      "quantity_reported": 40000,
      "notes": "Souvenir sheet with 5 values perf and island map",
      "sheet_contents": []  // optional: ["A747", "A748"] if explicitly stated
    }}

    VARIETIES: If SSA752a is imperforated version → place in varieties[], not stamps[]:
    {{
      "base_catalog_no": "SSA752",
      "suffix": "a",
      "type": "perforation",
      "description": "imperforated"
    }}

    EXAMPLE:
    Input:
      SSA752    sheet with 5 values perf    40,000
      SSA752a   sheet imperforated

    Output:
    - stamps[]: SSA752 with status: "souvenir_sheet", unit: "sheet", value: null
    - varieties[]: SSA752a as perforation variety

    --------------------------------------------------------------------------------
    SPECIAL PREFIX CODES - IA, IB, IC (Imperforate Variants)
    --------------------------------------------------------------------------------
    Some catalog systems use prefix codes for special variants:

    DETECTION:
    Codes starting with "I" followed by regular code: IA722, IB123, IC45

    MEANING:
    - IA722 = Imperforate version of A722
    - Similar to SSA (Souvenir Sheet A), IA (Imperforate A)

    CLASSIFICATION:
    These are COMPLETE catalog codes, NOT suffixes.

    IA722 is NOT the same as A722i or A722a

    PLACE AS SEPARATE STAMP:
    {{
      "catalog_no": "IA722",
      "denomination": {{...}},
      "perforation": "",  // always imperf for IA codes
      "status": "error" | "printer_waste" | "regular",  // based on context
      "notes": "Imperforate (printer's waste)" or similar
    }}

    --------------------------------------------------------------------------------
    ATM STAMPS (VARIABLE VALUE STAMPS)
    --------------------------------------------------------------------------------
    ATM stamps (Automaten Marken - Automated Teller Machine stamps) are variable 
    value stamps printed by machines. They have no fixed denomination.

    DETECTION: Codes starting with "ATM" followed by numbers: ATM9, ATM12, ATM5

    STRUCTURE (in stamps[] array):
    {{
      "catalog_no": "ATM9",
      "denomination": {{
        "value": null,           // no fixed value
        "unit": "variable"       // special unit for ATM stamps
      }},
      "status": "atm",           // special status
      "color": string,           // if mentioned
      "perforation": "",         // typically imperf or machine cut
      "quantity_reported": null, // variable, not typically reported
      "notes": string            // include description, e.g., "Papagayo Gulf. Variable value stamp. Size 57 x 27 mm"
    }}

    NOTES FIELD:
    Include relevant details:
    - Subject/design description
    - Size dimensions (e.g., "Size 57 x 27 mm")
    - "Variable value stamp" or "ATM stamp"
    - Any special characteristics

    --------------------------------------------------------------------------------
    CHRISTMAS POSTAL TAX STAMPS
    --------------------------------------------------------------------------------
    Christmas Tax stamps (CT codes) are special postal tax stamps.

    DETECTION: Codes starting with "CT" followed by numbers/letters: CT1, CT1A, CT25

    STRUCTURE (in stamps[] array):
    {{
      "catalog_no": "CT1",
      "denomination": {{
        "value": number,              // the surcharge/final value (e.g., 5)
        "unit": "c" | "C"             // standard units
      }},
      "status": "postal_tax",         // special status for tax stamps
      "color": string,
      "perforation": string,
      "quantity_reported": number|null,
      "notes": string,                // include "Christmas postal tax stamp" + details
      
      // Most CT stamps are surcharges on other stamps:
      "overprint": {{
        "present": true,
        "type": "surcharge",
        "surcharge_denomination": {{value: number, unit: string}},
        "on_denomination": {{value: number, unit: string}},
        "color": string
      }},
      "base_stamp_ref": string        // e.g., "A210"
    }}


    --------------------------------------------------------------------------------
    POSTAL STATIONERY (Unified Category)
    --------------------------------------------------------------------------------
    Postal stationery are pre-stamped items (cards, envelopes, etc.), separate from 
    adhesive stamps. All types go in the "postal_stationery" array.

    CODE DETECTION & TYPE MAPPING:
    Pattern              stationery_type        Example
    ^PC\d+[a-z]?$       → "postal_card"        PC1, PC25
    ^EN\d+[a-z]?$       → "envelope"           EN1, EN12
    ^LS\d+[a-z]?$       → "aerogramme"         LS1, LS5
    ^OEN\d+[a-z]?$      → "official_envelope"  OEN1, OEN23
    ^W\d+[a-z]?$        → "wrapper"            W1, W3

    STRUCTURE:
    {{
      "catalog_no": "PC1",
      "stationery_type": "postal_card",
      "denomination": {{"value": 2, "unit": "c"}},
      "color": "black",
      "paper": "buff manila",
      "size": "132 x 80 mm",
      "quantity_reported": 50000,
      "notes": [],
      
      // ONLY for postal_card type:
      "card_type": "single" | "reply" | "double"
    }}

    CARD TYPES (postal_card only):
    - "single": Regular postal card
    - "reply": Card mentions "with reply card" or "reply card"
    - "double": Double-sized reply card format

    OFFICIAL ENVELOPES with overprints:
    {{
      "catalog_no": "OEN1",
      "stationery_type": "official_envelope",
      "denomination": {{"value": 2, "unit": "c"}},
      "color": "green",
      "notes": ["For use by Secretary of Finance"],
      "overprint": {{
        "present": true,
        "type": "overprint",
        "text": "Servicio Oficial",
        "color": "black"
      }}
    }}

    PROOFS & SPECIMENS OF POSTAL STATIONERY:
    Identified by prefix + stationery type:
    - DPPC# = Die Proof Postal Card → proofs.die_proofs[]
    - DPEN# = Die Proof Envelope → proofs.die_proofs[]
    - DPLS# = Die Proof Aerogramme → proofs.die_proofs[]
    - DPOEN# = Die Proof Official Envelope → proofs.die_proofs[]
    - DPW# = Die Proof Wrapper → proofs.die_proofs[]

    - MPC# = Muestra Postal Card → specimens[]
    - MEN# = Muestra Envelope → specimens[]
    - MLS# = Muestra Aerogramme → specimens[]
    - etc.

    For specimens, use applies_to: "postal_stationery"

    VARIETIES:
    Lowercase suffixes go in varieties[]:
    {{
      "base_catalog_no": "EN1",
      "suffix": "a",
      "type": "color" | "impression" | "overprint" | "plate_flaw",
      "description": "pale blue" | "double impression" | "inverted op"
    }}

    CRITICAL POSTAL STATIONARY NOTES:
    - ALL postal stationery types go in ONE "postal_stationery" array
    - stationery_type field distinguishes the specific type
    - Postal stationery are NOT stamps - don't put in stamps[] array
    - Uppercase letter suffixes (EN1A) = main items, not varieties
    - Lowercase suffixes (EN1a) = varieties → varieties[] array
    - Proofs use DP + type prefix (DPPC, DPEN, DPLS, DPOEN, DPW)
    - Specimens use M + type prefix (MPC, MEN, MLS, MOEN, MW)

    --------------------------------------------------------------------------------
    OFFICIAL STAMPS (Surface Mail & Airmail)
    --------------------------------------------------------------------------------
    Official stamps are regular postage stamps overprinted for official government 
    use. They go in the stamps[] array with special status and overprint structure.

    CODE DETECTION:
    Surface Mail:     ^O\d+[a-z]?$        → O1, O25, O3a
    Airmail:          ^OA\d+[a-z]?$       → OA107, OA115, OA119a

    Both types use same structure, only differ in section (Surface Mail vs Airmail).

    STRUCTURE (in stamps[] array):
    {{
      "catalog_no": "O1" | "OA107",
      "issue_id": string,
      "denomination": {{
        "value": number,
        "unit": "c" | "C" | "P" | "reales"
      }},
      "color": string,                      // color of base stamp
      "perforation": string,
      "quantity_reported": number|null,
      "status": "official",                 // same status for O and OA
      "notes": string[],
      
      "overprint": {{
        "present": true,
        "type": "overprint",
        "text": string,                       // e.g., "Oficial", "OFFICIAL"
        "color": string                     // color of overprint
      }},
      "base_stamp_ref": string              // reference to base stamp
    }}

    OVERPRINT EXTRACTION:
    - From text: "Overprint 'Oficial' in red" → text: "Oficial", color: "red"
    - Color format: "5c green, in red" → base: green, overprint: red
    - If no explicit text, use: "Official use overprint"

    SPECIMENS: SO# (surface) and SOA# (airmail) → specimens[] with applies_to: "stamps"
    VARIETIES: Lowercase suffixes (O2a, OA115a) → varieties[]
    SECTION: O# → "Surface Mail", OA# → "Airmail"

    EXAMPLE:

    Input:
      Overprint Issue of 1934
      Overprint "Oficial" in red. Perf 12.
      
      Overprint "specimen" in red
      SOA107   5c green
      
      Regular issue
      OA107    5c green       75,000
      OA108    10c carmine rose   35,000
      OA108a   inverted overprint

    Output:
    {{
      "issue_data": {{"section": "Airmail", ...}},
      "stamps": [
        {{
          "catalog_no": "OA107",
          "denomination": {{"value": 5, "unit": "c"}},
          "color": "green",
          "perforation": "12",
          "quantity_reported": 75000,
          "status": "official",
          "notes": ["Official airmail stamp"],
          "overprint": {{"present": true, "type": "overprint", "text": "Oficial", "color": "red"}},
          "base_stamp_ref": "A107"
        }},
        {{
          "catalog_no": "OA108",
          "denomination": {{"value": 10, "unit": "c"}},
          "color": "carmine rose",
          "perforation": "12",
          "quantity_reported": 35000,
          "status": "official",
          "overprint": {{"present": true, "type": "overprint", "text": "Oficial", "color": "red"}},
          "base_stamp_ref": "A108"
        }}
      ],
      "varieties": [
        {{"base_catalog_no": "OA108", "suffix": "a", "type": "overprint", "description": "inverted overprint"}}
      ],
      "specimens": [
        {{"code": "SOA107", "applies_to": "stamps", "type": "overprint", "denomination": "5c", "base_color": "green", "overprint_color": "red", "notes": "SPECIMEN overprint"}}
      ]
    }}

    CRITICAL FOR OFFICIAL STAMPS: O# and OA# both use status: "official" and go in stamps[] array.
    Base ref: remove O/OA prefix (OA107 → A107, O5 → 5).

    --------------------------------------------------------------------------------
    GUANACASTE OVERPRINTS
    --------------------------------------------------------------------------------
    Guanacaste stamps are regular postage or revenue stamps overprinted with 
    "Guanacaste" for use in Guanacaste Province (1885-1892). They go in stamps[] 
    array with special status and overprint structure.

    CODE DETECTION:
    Postage:    ^G\d+[a-z]?$        → G1, G5, G12a
    Revenue:    ^GR\d+[a-z]?$       → GR1, GR5, GR8a

    STRUCTURE (in stamps[] array):
    {{
      "catalog_no": "G1" | "GR1",
      "issue_id": string,
      "denomination": {{
        "value": number,
        "unit": "c" | "C" | "P" | "reales"
      }},
      "color": string,                      // color of base stamp
      "perforation": string,
      "watermark": string|null,
      "quantity_reported": number|null,
      "status": "guanacaste" | "guanacaste_revenue",
      "notes": string[],
      
      "overprint": {{
        "present": true,
        "type": "overprint",
        "text": "Guanacaste",
        "color": "black" | "red"            // extracted from section header
      }},
      "base_stamp_ref": string              // reference to base stamp
    }}

    STATUS VALUES:
    - G# codes → status: "guanacaste"
    - GR# codes → status: "guanacaste_revenue"

    OVERPRINT COLOR:
    Extract from section headers:
    - "Black Overprint" → all following stamps have color: "black"
    - "Red Overprint" → all following stamps have color: "red"

    PLATE ERRORS (varieties):
    When text describes plate errors with positions:
    "a: first A broken (pos 19)" → create variety with position: 19

    {{
      "base_catalog_no": "G1",
      "suffix": "a",
      "type": "plate_flaw",
      "description": "first A broken",
      "position": 19,
      "plate": 1
    }}

    VARIETIES:
    - Lowercase suffixes (G1a, GR4a) go in varieties[]
    - Include position when mentioned (pos 19, pos 37, etc.)
    - type: usually "plate_flaw" or "impression"

    GUANACASTE CRITICAL NOTES:
    - G# and GR# codes go in stamps[] array
    - G# → status: "guanacaste"
    - GR# → status: "guanacaste_revenue"
    - overprint.text always "Guanacaste"
    - Overprint color from section headers (Black/Red Overprint)
    - Plate errors with positions go in varieties[] with position field populated
    - Base ref: G1 → "1", GR1 → "R1"

    --------------------------------------------------------------------------------
    SEMIPOSTAL STAMPS
    --------------------------------------------------------------------------------
    Semipostal stamps are postage stamps sold at a premium above face value, with 
    proceeds benefiting charitable causes. They go in stamps[] array with special 
    status and optional surcharge structure.

    CODE DETECTION:
    Regular:    ^SP\d+[a-z]?$        → SP1, SP2, SP4a
    Imperf:     ^ISP\d+[a-z]?$       → ISP2, ISP4a

    STRUCTURE (in stamps[] array):
    {{
      "catalog_no": "SP1" | "ISP2",
      "issue_id": string,
      "denomination": {{
        "value": number,
        "unit": "c" | "C" | "P"
      }},
      "color": string,
      "perforation": string,              // "" for ISP codes
      "quantity_reported": number|null,
      "status": "semipostal",             // for both SP and ISP
      "notes": string[],                  // include benefit purpose and premium
      
      // ONLY when surcharged:
      "overprint": {{
        "present": true,
        "type": "surcharge",
        "surcharge_denomination": {{value: number, unit: string}},
        "on_denomination": {{value: number, unit: string}},
        "color": string
      }},
      "base_stamp_ref": string
    }}

    NOTES FIELD:
    Include charitable purpose and premium amount:
    - "Sold with 10c premium for Olympic Games Committee benefit"
    - "Red Cross Society benefit. Premium: 5c"

    ISP CODES (Imperforates):
    - ISP# are separate catalog items, NOT varieties
    - status: "semipostal" (same as SP)
    - perforation: "" (empty for imperf)

    PROOFS:
    - DPSP# → proofs.die_proofs[]
    - OPSP# → proofs.overprint_proofs[]
    - Color proofs in combined format: "SP2-4a brown red" means one proof sheet 
      with SP2, SP3, SP4 in same color → one entry in color_proofs[]

    VARIETIES:
    Lowercase suffixes (SP1a, ISP4a) go in varieties[]:
    - "tete-beche" → type: "arrangement"
    - "lower surcharge" → type: "overprint"
    - "shifted perf" → type: "perforation"

    EXAMPLE:

    Input:
      Red Cross Society benefit surcharge
      October 17, 1922. Surcharge on 1910 stamp. Perf 12.
      
      Overprint Proof
      OPSP1  5c red on onionskin paper
      
      Regular issue
      SP1    5c on 5c orange (68)    200,000
      SP1a   lower surcharge
      SP1b   surcharge displaced upwards
      
      Sold with 5c premium for Red Cross benefit.
      
      Olympic Games benefit
      Die Proofs
      DPSP2  5c black
      DPSP3  10c black
      
      Three values in a sheet
      SP2-4a brown red
      SP2-4b black
      
      Imperforate
      ISP2   5c dark green    15,000
      ISP3   10c carmine      15,000
      
      Regular issue
      SP2    5c dark green    15,000
      SP3    10c carmine      15,000
      SP4    20c dark blue    15,000
      SP4a   vertical pair tete beche
      
      Sold with 10c surcharge for Olympic Games Committee benefit.

    Output:
    {{
      "stamps": [
        {{
          "catalog_no": "SP1",
          "denomination": {{"value": 5, "unit": "c"}},
          "color": "orange",
          "perforation": "12",
          "quantity_reported": 200000,
          "status": "semipostal",
          "notes": ["Red Cross Society benefit. Sold with 5c premium"],
          "overprint": {{
            "present": true,
            "type": "surcharge",
            "surcharge_denomination": {{"value": 5, "unit": "c"}},
            "on_denomination": {{"value": 5, "unit": "c"}},
            "color": "red"
          }},
          "base_stamp_ref": "68"
        }},
        {{
          "catalog_no": "ISP2",
          "denomination": {{"value": 5, "unit": "c"}},
          "color": "dark green",
          "perforation": "",
          "quantity_reported": 15000,
          "status": "semipostal",
          "notes": ["Olympic Games benefit. Sold with 10c premium. Imperforate"]
        }},
        {{
          "catalog_no": "ISP3",
          "denomination": {{"value": 10, "unit": "c"}},
          "color": "carmine",
          "perforation": "",
          "quantity_reported": 15000,
          "status": "semipostal",
          "notes": ["Olympic Games benefit. Sold with 10c premium. Imperforate"]
        }},
        {{
          "catalog_no": "SP2",
          "denomination": {{"value": 5, "unit": "c"}},
          "color": "dark green",
          "perforation": "12",
          "quantity_reported": 15000,
          "status": "semipostal",
          "notes": ["Olympic Games benefit. Sold with 10c premium"]
        }},
        {{
          "catalog_no": "SP3",
          "denomination": {{"value": 10, "unit": "c"}},
          "color": "carmine",
          "perforation": "12",
          "quantity_reported": 15000,
          "status": "semipostal",
          "notes": ["Olympic Games benefit. Sold with 10c premium"]
        }},
        {{
          "catalog_no": "SP4",
          "denomination": {{"value": 20, "unit": "c"}},
          "color": "dark blue",
          "perforation": "12",
          "quantity_reported": 15000,
          "status": "semipostal",
          "notes": ["Olympic Games benefit. Sold with 10c premium"]
        }}
      ],
      "varieties": [
        {{
          "base_catalog_no": "SP1",
          "suffix": "a",
          "type": "overprint",
          "description": "lower surcharge",
          "position": null,
          "plate": null
        }},
        {{
          "base_catalog_no": "SP1",
          "suffix": "b",
          "type": "overprint",
          "description": "surcharge displaced upwards",
          "position": null,
          "plate": null
        }},
        {{
          "base_catalog_no": "SP4",
          "suffix": "a",
          "type": "arrangement",
          "description": "vertical pair tete-beche",
          "position": null,
          "plate": null
        }}
      ],
      "proofs": {{
        "die_proofs": [
          {{"code": "DPSP2", "denomination": "5c", "color": "black", "substrate": "bond paper", ...}},
          {{"code": "DPSP3", "denomination": "10c", "color": "black", "substrate": "bond paper", ...}}
        ],
        "overprint_proofs": [
          {{"code": "OPSP1", "denomination": "5c", "color": "red", "substrate": "onionskin paper", ...}}
        ],
        "color_proofs": [
          {{"code": "SP2-4a", "denomination": "5c/10c/20c", "color": "brown red", "notes": "Three values in a sheet"}},
          {{"code": "SP2-4b", "denomination": "5c/10c/20c", "color": "black", "notes": "Three values in a sheet"}}
        ]
      }}
    }}

    SEMI POSTAL CRITICAL NOTES:
    - SP# and ISP# codes go in stamps[] array
    - Both use status: "semipostal"
    - ISP# are imperf stamps, NOT varieties
    - Notes must include benefit purpose and premium amount
    - Combined color proofs (SP2-4a) → one entry in color_proofs[]
    - Varieties (SP1a, ISP4a) go in varieties[]
    - Proofs: DPSP#, OPSP# go in respective proof sections

    --------------------------------------------------------------------------------
    POSTAGE DUE STAMPS
    --------------------------------------------------------------------------------
    Postage due stamps are used to collect unpaid or underpaid postage. They go in 
    stamps[] array with special status.

    CODE DETECTION:
    Regular:    ^D\d+[a-z]?$         → D1, D8, D15a
    Specimens:  ^SD\d+[a-z]?$        → SD1, SD4a
    Proofs:     ^DPD\d+$             → DPD1

    STRUCTURE (in stamps[] array):
    {{
      "catalog_no": "D1",
      "issue_id": string,
      "denomination": {{
        "value": number,
        "unit": "c" | "C" | "P"
      }},
      "color": string,
      "perforation": string,
      "watermark": string|null,
      "quantity_reported": number|null,
      "status": "postage_due",
      "notes": string[]
    }}

    SPECIMENS:
    SD# codes go in specimens[] array:
    {{
      "code": "SD1",
      "applies_to": "stamps",
      "type": "overprint",
      "denomination": "5c",
      "base_color": string,
      "overprint_color": "black" | "purple",
      "notes": "SPECIMEN overprint" or "Waterlow & Sons Ltd/Specimen"
    }}

    PROOFS:
    DPD# codes go in proofs.die_proofs[]:
    {{
      "code": "DPD1",
      "denomination": string or "no numeral",
      "color": "black",
      "die_no": string,
      "substrate": "bond paper",
      "finish": ""
    }}

    VARIETIES:
    Lowercase suffixes (D1a, SD4a) go in varieties[] for D codes.
    For SD codes with lowercase, they may be separate specimens if significantly 
    different (color/perforation changes).

    EXAMPLE:

    Input:
      Issue of 1903
      September 10, 1903. Decree #53. Engraved by Waterlow & Sons. Perf 14, 15.
      
      Die Proof
      DPD1  black, no numeral, bond paper #3428
      
      Overprint "specimen" in black, numerals in black
      SD1   5c slate blue
      SD2   10c brown orange
      SD4   20c carmine
      
      Overprint "Waterlow & Sons Ltd/Specimen"
      SD4a  20c red orange, imperf
      SD4b  20c red orange, perf 12.5
      
      Regular issue
      D1    5c slate blue
      D2    10c brown orange
      D3    15c yellow green
      D4    20c carmine
      D5    25c slate gray

    Output:
    {{
      "issue_data": {{
        "issue_id": "CR-1903-POSTAGE-DUE",
        "section": "Postage Due",
        ...
      }},
      "stamps": [
        {{
          "catalog_no": "D1",
          "denomination": {{"value": 5, "unit": "c"}},
          "color": "slate blue",
          "perforation": "14",
          "quantity_reported": null,
          "status": "postage_due",
          "notes": ["Postage due stamp"]
        }},
        {{
          "catalog_no": "D2",
          "denomination": {{"value": 10, "unit": "c"}},
          "color": "brown orange",
          "perforation": "14",
          "status": "postage_due",
          "notes": ["Postage due stamp"]
        }},
        {{
          "catalog_no": "D3",
          "denomination": {{"value": 15, "unit": "c"}},
          "color": "yellow green",
          "perforation": "14",
          "status": "postage_due",
          "notes": ["Postage due stamp"]
        }},
        {{
          "catalog_no": "D4",
          "denomination": {{"value": 20, "unit": "c"}},
          "color": "carmine",
          "perforation": "14",
          "status": "postage_due",
          "notes": ["Postage due stamp"]
        }},
        {{
          "catalog_no": "D5",
          "denomination": {{"value": 25, "unit": "c"}},
          "color": "slate gray",
          "perforation": "14",
          "status": "postage_due",
          "notes": ["Postage due stamp"]
        }}
      ],
      "proofs": {{
        "die_proofs": [
          {{
            "code": "DPD1",
            "denomination": "no numeral",
            "color": "black",
            "die_no": "3428",
            "substrate": "bond paper",
            "finish": ""
          }}
        ]
      }},
      "specimens": [
        {{
          "code": "SD1",
          "applies_to": "stamps",
          "type": "overprint",
          "denomination": "5c",
          "base_color": "slate blue",
          "overprint_color": "black",
          "notes": "SPECIMEN overprint"
        }},
        {{
          "code": "SD2",
          "applies_to": "stamps",
          "type": "overprint",
          "denomination": "10c",
          "base_color": "brown orange",
          "overprint_color": "black",
          "notes": "SPECIMEN overprint"
        }},
        {{
          "code": "SD4",
          "applies_to": "stamps",
          "type": "overprint",
          "denomination": "20c",
          "base_color": "carmine",
          "overprint_color": "black",
          "notes": "SPECIMEN overprint"
        }},
        {{
          "code": "SD4a",
          "applies_to": "stamps",
          "type": "overprint",
          "denomination": "20c",
          "base_color": "red orange",
          "overprint_color": "black",
          "notes": "Waterlow & Sons Ltd/Specimen. Imperf"
        }},
        {{
          "code": "SD4b",
          "applies_to": "stamps",
          "type": "overprint",
          "denomination": "20c",
          "base_color": "red orange",
          "overprint_color": "black",
          "notes": "Waterlow & Sons Ltd/Specimen. Perf 12.5"
        }}
      ]
    }}

    POSTAGE DUES CRITICAL NOTES:
    - D# codes go in stamps[] with status: "postage_due"
    - SD# codes go in specimens[] (NOT stamps[])
    - DPD# codes go in proofs.die_proofs[]
    - SD codes with suffixes (SD4a, SD4b) are separate specimen items if they have 
      different perforation/color, NOT varieties
    - Section: "Postage Due" for issue_data

    --------------------------------------------------------------------------------
    SPECIAL DELIVERY STAMPS
    --------------------------------------------------------------------------------
    Special delivery stamps (Entrega Inmediata) are used for express mail service. 
    They go in stamps[] array with special status.

    CODE DETECTION:
    Regular:       ^SD\d+[a-z]?$         → SD3, SD5, SD6a
    Color Proofs:  ^CPSD\d+$             → CPSD3

    STRUCTURE (in stamps[] array):
    {{
      "catalog_no": "SD3",
      "issue_id": string,
      "denomination": {{
        "value": number,
        "unit": "c" | "C" | "P"
      }},
      "color": string,
      "perforation": string,
      "quantity_reported": number|null,
      "status": "special_delivery",
      "notes": string[]                   // include service type (local/international)
    }}

    NOTES FIELD:
    Include service type when mentioned:
    - "Special delivery. Local rate"
    - "Special delivery. International rate"
    - "Special delivery. Local and U.P.A.E. countries rate"

    PROOFS:
    CPSD# codes go in proofs.color_proofs[]:
    {{
      "code": "CPSD3",
      "denomination": "75c",
      "color": "black",
      "notes": "Color proof"
    }}

    VARIETIES:
    Lowercase suffixes (SD5a, SD6a) go in varieties[]:
    - "triple impression" → type: "impression"
    - "imperf left margin" → type: "perforation"
    - "double impression" → type: "impression"

    SPECIAL DELIVERY STAMPS CRITICAL NOTES:
    - SD# codes go in stamps[] with status: "special_delivery"
    - CPSD# codes go in proofs.color_proofs[]
    - Include service type in notes (local/international/U.P.A.E.)
    - Varieties (SD5a, SD6b) go in varieties[]
    - Section: "Special Delivery" or can be included in "Surface Mail"/"Airmail"

    --------------------------------------------------------------------------------
    POSTAL RELATED REVENUE STAMPS
    --------------------------------------------------------------------------------
    These are stamps with postal-revenue connections:
    1. PR# = Postal stamps surcharged/overprinted for Revenue/Fiscal use (various types: 
      regular fiscal, electoral, archive, etc.)
    2. R# = Revenue stamps used for Postal purposes

    CODE DETECTION:
    Postal to Revenue:         ^PR\d+[a-z]?$       → PR4, PR12
    Revenue to Postal:         ^R\d+[a-z]?$        → R23, R25
    Specimens:                 ^MPR\d+[a-z]?$      → MPR12a
    Surcharge Proofs:          ^SPPR\d+[a-z]?$     → SPPR13a

    STRUCTURE (in stamps[] array):

    FOR PR# (Postal stamps converted to revenue use):
    {{
      "catalog_no": "PR4",
      "denomination": {{"value": number, "unit": "c"|"C"|"P"}},
      "color": string,
      "quantity_reported": number|null,
      "status": "postal_revenue",
      "notes": string[],                    // Include type: "Electoral stamp", "Archive stamp", etc.
      
      "overprint": {{
        "present": true,
        "type": "surcharge" | "overprint",
        "text": string,                     // e.g., "Elecciones/1946", "Timbre de/Archivo"
        "surcharge_denomination": {{...}},  // only for surcharges
        "on_denomination": {{...}},         // only for surcharges
        "color": string
      }},
      "base_stamp_ref": string
    }}

    FOR R# (Revenue stamps used for postage):
    {{
      "catalog_no": "R23",
      "denomination": {{"value": number, "unit": "c"|"C"|"P"}},
      "color": string,
      "status": "revenue_postal",
      "notes": ["Revenue stamp used for postage without authorization"]
    }}

    SPECIMENS & PROOFS:
    - MPR# → specimens[] with applies_to: "stamps"
    - SPPR# → proofs.surcharge_proofs[] or proofs.overprint_proofs[]

    NOTES FIELD for PR#:
    Include specific use type:
    - "Regular postal stamp surcharged for fiscal use"
    - "Electoral stamp. National Exposition overprinted Elecciones/1946"
    - "Archive stamp. Postage due surcharged Timbre de/Archivo"

    EXAMPLE:

    Input:
      REGULAR FISCAL USE
      1947. Airmail stamps surcharged "Timbre Fiscal/1947/ Dos Colones".
      PR4  2C on 5C black, in red      25,500
      
      ELECTORAL STAMPS
      1946. National Exposition stamps overprinted "Elecciones/1946", in black.
      Overprint "muestra"
      MPR12a  2c gray black
      MPR12b  3c red orange, no date
      Regular issue
      PR12    2c gray black
      
      ARCHIVE STAMPS
      1946. Postage due stamps surcharged "Timbre de/ Archivo" and value, in blue.
      Surcharge Proofs
      SPPR13a  10c on 10c violet, in black
      SPPR13b  10c on 10c violet, in red

    Output:
    {{
      "stamps": [
        {{
          "catalog_no": "PR4",
          "denomination": {{"value": 2, "unit": "C"}},
          "color": "black",
          "quantity_reported": 25500,
          "status": "postal_revenue",
          "notes": ["Regular airmail stamp surcharged for fiscal use. Timbre Fiscal 1947"],
          "overprint": {{
            "present": true,
            "type": "surcharge",
            "text": "Timbre Fiscal/1947/ Dos Colones",
            "surcharge_denomination": {{"value": 2, "unit": "C"}},
            "on_denomination": {{"value": 5, "unit": "C"}},
            "color": "red"
          }},
          "base_stamp_ref": "A26"
        }},
        {{
          "catalog_no": "PR12",
          "denomination": {{"value": 2, "unit": "c"}},
          "color": "gray black",
          "status": "postal_revenue",
          "notes": ["Electoral stamp. National Exposition overprinted Elecciones/1946"],
          "overprint": {{
            "present": true,
            "type": "overprint",
            "text": "Elecciones/1946",
            "color": "black"
          }},
          "base_stamp_ref": "A31"
        }}
      ],
      "specimens": [
        {{
          "code": "MPR12a",
          "applies_to": "stamps",
          "type": "overprint",
          "denomination": "2c",
          "base_color": "gray black",
          "overprint_color": "black",
          "notes": "MUESTRA overprint. Electoral stamp"
        }},
        {{
          "code": "MPR12b",
          "applies_to": "stamps",
          "type": "overprint",
          "denomination": "3c",
          "base_color": "red orange",
          "overprint_color": "black",
          "notes": "MUESTRA overprint. Electoral stamp, no date"
        }}
      ],
      "proofs": {{
        "surcharge_proofs": [
          {{
            "code": "SPPR13a",
            "denomination": "10c on 10c",
            "color": "violet",
            "surcharge_color": "black",
            "notes": "Surcharge proof. Archive stamp"
          }},
          {{
            "code": "SPPR13b",
            "denomination": "10c on 10c",
            "color": "violet",
            "surcharge_color": "red",
            "notes": "Surcharge proof. Archive stamp"
          }}
        ]
      }}
    }}

    POSTAL RELATED REVENUES CRITICAL NOTES:
    - PR# = Postal → Revenue (various fiscal uses: regular, electoral, archive)
    - R# = Revenue → Postal
    - PR# codes have status: "postal_revenue" WITH overprint/surcharge
    - R# codes have status: "revenue_postal" WITHOUT overprint
    - MPR# specimens → specimens[] with applies_to: "stamps"
    - SPPR# proofs → proofs.surcharge_proofs[] or proofs.overprint_proofs[]
    - Notes should specify type: electoral, archive, regular fiscal, etc.

    --------------------------------------------------------------------------------
    TELEGRAPH STAMPS AND SEALS
    --------------------------------------------------------------------------------
    Telegraph items include regular telegraph stamps (T#), telegraph seals (TS#), 
    and radiogram seals (RS#). All go in stamps[] array with appropriate status.

    CODE DETECTION:
    Telegraph Stamps:      ^T\d+[A-Z]?[a-z]?$     → T1, T2A, T3a
    Telegraph Seals:       ^TS\d+[a-z]?$          → TS1, TS5, TS8a
    Radiogram Seals:       ^RS\d+[a-z]?$          → RS1, RS6
    Imperf Radiogram:      ^IRS\d+[a-z]?$         → IRS1

    Proofs:
    Die Proofs Telegraph:       ^DPT\d+[a-z]?$     → DPT1
    Plate Proofs Telegraph:     ^PPT\d+[a-z]?$     → PPT1
    Plate Proofs Telegraph Seal: ^PTS\d+[a-z]?$    → PTS2, PTS5a
    Specimens Telegraph:        ^ST\d+[a-z]?$      → ST1

    IMPORTANT: Uppercase letter suffixes (T2A) are separate stamps, not varieties.
    Lowercase suffixes (TS2a, RS5a) are varieties.

    STRUCTURE (in stamps[] array):

    FOR T# (Telegraph Stamps):
    {{
      "catalog_no": "T2" | "T2A",
      "denomination": {{"value": number, "unit": "c"|"C"|"P"}},
      "color": string,
      "perforation": string,
      "watermark": string|null,
      "status": "telegraph",
      "notes": ["Telegraph stamp"]
    }}

    FOR TS# (Telegraph Seals):
    {{
      "catalog_no": "TS2",
      "denomination": {{"value": null, "unit": "seal"}},  // seals have no denomination
      "color": string,
      "paper": string,                    // "white paper", "pink paper", etc.
      "perforation": string,
      "status": "telegraph_seal",
      "notes": ["Telegraph seal"]
    }}

    FOR RS# and IRS# (Radiogram Seals):
    {{
      "catalog_no": "RS1" | "IRS1",
      "denomination": {{"value": null, "unit": "seal"}},
      "color": string,
      "paper": string,                    // paper color
      "perforation": string,              // often ""
      "status": "radiogram_seal",
      "notes": ["Radiogram seal. Design with CR/RN in center"]
    }}

    PROOFS:
    - DPT#/PPT# → telegraph stamp proofs
    - PTS# → telegraph seal proofs (proofs.plate_proofs[])

    EXAMPLE:

    Input:
      TELEGRAPH SEALS
      Lithography by Litografia Nacional. Perf 12.
      
      Proofs, imperf
      PTS2   blue, white paper
      PTS2a  blue, pink paper
      PTS5   dark blue, white paper
      
      Regular issue
      TS1    blue
      TS2    light blue, perf 12
      TS2a   horizontal pair imperf between
      TS3    black, imperf
      TS5    dark blue, white paper
      TS8    blue, pink paper
      
      RADIOGRAM SEALS
      "Radios de Costa Rica". "CR" in center. Imperforate.
      
      IRS1   brown, yellow paper
      RS1    brown, yellow paper
      RS2    reddish brown, pink paper
      RS6    brown, pink paper

    Output:
    {{
      "stamps": [
        {{
          "catalog_no": "TS1",
          "denomination": {{"value": null, "unit": "seal"}},
          "color": "blue",
          "paper": "",
          "perforation": "12",
          "status": "telegraph_seal",
          "notes": ["Telegraph seal"]
        }},
        {{
          "catalog_no": "TS2",
          "denomination": {{"value": null, "unit": "seal"}},
          "color": "light blue",
          "paper": "",
          "perforation": "12",
          "status": "telegraph_seal",
          "notes": ["Telegraph seal"]
        }},
        {{
          "catalog_no": "TS3",
          "denomination": {{"value": null, "unit": "seal"}},
          "color": "black",
          "paper": "",
          "perforation": "",
          "status": "telegraph_seal",
          "notes": ["Telegraph seal. Imperf"]
        }},
        {{
          "catalog_no": "TS5",
          "denomination": {{"value": null, "unit": "seal"}},
          "color": "dark blue",
          "paper": "white paper",
          "perforation": "12",
          "status": "telegraph_seal",
          "notes": ["Telegraph seal"]
        }},
        {{
          "catalog_no": "TS8",
          "denomination": {{"value": null, "unit": "seal"}},
          "color": "blue",
          "paper": "pink paper",
          "perforation": "12",
          "status": "telegraph_seal",
          "notes": ["Telegraph seal"]
        }},
        {{
          "catalog_no": "IRS1",
          "denomination": {{"value": null, "unit": "seal"}},
          "color": "brown",
          "paper": "yellow paper",
          "perforation": "",
          "status": "radiogram_seal",
          "notes": ["Radiogram seal. Radios de Costa Rica. Imperf"]
        }},
        {{
          "catalog_no": "RS1",
          "denomination": {{"value": null, "unit": "seal"}},
          "color": "brown",
          "paper": "yellow paper",
          "perforation": "",
          "status": "radiogram_seal",
          "notes": ["Radiogram seal. Radios de Costa Rica. Imperf"]
        }},
        {{
          "catalog_no": "RS2",
          "denomination": {{"value": null, "unit": "seal"}},
          "color": "reddish brown",
          "paper": "pink paper",
          "perforation": "",
          "status": "radiogram_seal",
          "notes": ["Radiogram seal. Design with CR in center. Imperf"]
        }},
        {{
          "catalog_no": "RS6",
          "denomination": {{"value": null, "unit": "seal"}},
          "color": "brown",
          "paper": "pink paper",
          "perforation": "",
          "status": "radiogram_seal",
          "notes": ["Radiogram seal. Design with RN in center. Imperf"]
        }}
      ],
      "varieties": [
        {{
          "base_catalog_no": "TS2",
          "suffix": "a",
          "type": "perforation",
          "description": "horizontal pair imperf between",
          "position": null,
          "plate": null
        }}
      ],
      "proofs": {{
        "plate_proofs": [
          {{"code": "PTS2", "denomination": "seal", "color": "blue", "notes": "Telegraph seal proof. White paper. Imperf"}},
          {{"code": "PTS2a", "denomination": "seal", "color": "blue", "notes": "Telegraph seal proof. Pink paper. Imperf"}},
          {{"code": "PTS5", "denomination": "seal", "color": "dark blue", "notes": "Telegraph seal proof. White paper. Imperf"}}
        ]
      }}
    }}

    TELEGRAPH STAMPS AND SEALS CRITICAL NOTES:
    - T# → status: "telegraph" (stamps with denominations)
    - TS# → status: "telegraph_seal" (seals without denominations)
    - RS#/IRS# → status: "radiogram_seal" (radio service seals)
    - Seals have denomination.unit: "seal" with value: null
    - Paper color is important field for seals
    - T#A (uppercase) = separate stamps in stamps[]
    - TS#a/RS#a (lowercase) = varieties in varieties[]
    - PTS# proofs → proofs.plate_proofs[]
    - IRS# are complete catalog codes, NOT varieties

    --------------------------------------------------------------------------------
    QUANTITIES & DATES
    --------------------------------------------------------------------------------
    - Tables of print runs by denomination → "production_orders.printings".
    - DO NOT assign table totals to "stamps[*].quantity_reported" unless that SPECIFIC catalog number line states a quantity.
    - Ignore placeholder zeros: if a table shows 0 for a denomination/period, omit that row.
    - Remainders (Mint/Used) → "production_orders.remainders.quantities" with the Mint/Used tag in "plate_desc".
    - Dates: ISO (YYYY-MM-DD). If only month/year, use first day of month. Do NOT invent "probable_first_circulation" unless explicitly stated.

    --------------------------------------------------------------------------------
    PERFORATIONS
    --------------------------------------------------------------------------------
    - "issue_data.perforation" can contain a range summary (e.g., "13.5-15.5") IF stated.
    - "stamps[*].perforation" should contain a specific gauge if uniquely stated for that stamp; otherwise "" (do not copy the range blindly).
    - Do NOT include the word "perf" in this field (gauge only).

    --------------------------------------------------------------------------------
    POST-PARSE VALIDATION CHECKLIST (MANDATORY)
    --------------------------------------------------------------------------------
    Before emitting JSON, ensure ALL are true:
    1) All S-codes are present EXCLUSIVELY in top-level "specimens". There are NO S-codes in "varieties", "proofs", or "stamps".
    2) "varieties" ONLY contains lowercase-suffix items of real main catalog numbers (e.g., "31a"). No S-codes here.
    3) "stamps[*].quantity_reported" is null unless a catalog line gives a specific quantity for that exact number.
    4) Progressive dies (e.g., "DPA…") are in "proofs.die_proofs" with finish starting "progressive:".
    5) No placeholder zeros were recorded in "production_orders.printings".
    6) All required top-level keys exist and are arrays/objects per schema.
    7) Notes fields are strings or arrays of strings (no nested objects).
    8) No extra keys beyond the schema.

    --------------------------------------------------------------------------------
    JSON FORMAT GUARDRAILS
    --------------------------------------------------------------------------------
    - Return ONLY the JSON object (no commentary or markdown).
    - Never emit code inside values.
    - Unknowns → "", null, [], or {{}} per schema.
    - If multiple notes are present, return an array of strings. If a single note is present, a single string is acceptable.

    """

    return system_message

def create_few_shot_system_prompt() -> str:
    """
    Creates a system prompt with few-shot examples.
    
    The examples teach the LLM how to parse stamp catalog descriptions
    and extract structured information into JSON format.
    
    Returns:
        str: Complete prompt string with system instructions and examples
    """
    
    # Define input/output examples
    examples = [
        {
            "input": """<table id="8-I">
        <tr><td id="8-J">Regular issue</td><td id="8-K"></td><td id="8-L"></td></tr>
        <tr><td id="8-M">1</td><td id="8-N">½ real blue (plate 1)</td><td id="8-O">3,000,000</td></tr>
        <tr><td id="8-P">1a</td><td id="8-Q">double perf horizontal</td><td id="8-R"></td></tr>
        <tr><td id="8-S">1b</td><td id="8-T">double perf diagonal</td><td id="8-U"></td></tr>
        <tr><td id="8-V">1c</td><td id="8-W">double impression at right</td><td id="8-X"></td></tr>
        <tr><td id="8-Y">1d</td><td id="8-Z">cracked plate (pos 1)</td><td id="8-10"></td></tr>
        <tr><td id="8-11">1e</td><td id="8-12">cracked plate (pos 11)</td><td id="8-13"></td></tr>
        <tr><td id="8-14">1f</td><td id="8-15">cracked plate (pos 21)</td><td id="8-16"></td></tr>
        </table>

        Constant plate varieties:
        g: period in center second star (pos 87)
        h: period in center third star (pos 89)
        I: line on top volcano (pos 96)

        <table><thead><tr><th>Col&nbsp;1</th><th>Col&nbsp;2</th></tr></thead><tbody>
        <tr><td>1A 1½ real light blue (plate 2)</td><td>2,750,000</td></tr>
        <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;1Aa imperf horizontal (pair or blocks-38)</td><td></td></tr>
        <tr><td>2 2 reales scarlet</td><td>750,000</td></tr>
        <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;2a engraver line through DOS (pos 1)</td><td></td></tr>
        <tr><td>3 4 reales green</td><td>70,000</td></tr>
        <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;3a double entry of "Correos de Costa Rica" (pos 8)</td><td></td></tr>
        <tr><td>4 1 peso yellow</td><td>35,000</td></tr>
        </tbody></table>
        """,
            "output": json.dumps({
                "issue_data": {
                    "issue_id": "CR-1863-FIRST-ISSUE",
                    "section": "Surface Mail",
                    "title": "Regular issue",
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
                    "remainders": {"date": None, "notes": [], "quantities": []}
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
                    },
                    {
                        "catalog_no": "1A",
                        "issue_id": "CR-1863-FIRST-ISSUE",
                        "denomination": {"value": 1.5, "unit": "real"},
                        "color": "light blue",
                        "plate": 2,
                        "perforation": "",
                        "watermark": None,
                        "quantity_reported": 2750000,
                        "status": "regular",
                        "notes": []
                    },
                    {
                        "catalog_no": "2",
                        "issue_id": "CR-1863-FIRST-ISSUE",
                        "denomination": {"value": 2, "unit": "real"},
                        "color": "scarlet",
                        "plate": None,
                        "perforation": "",
                        "watermark": None,
                        "quantity_reported": 750000,
                        "status": "regular",
                        "notes": []
                    },
                    {
                        "catalog_no": "3",
                        "issue_id": "CR-1863-FIRST-ISSUE",
                        "denomination": {"value": 4, "unit": "real"},
                        "color": "green",
                        "plate": None,
                        "perforation": "",
                        "watermark": None,
                        "quantity_reported": 70000,
                        "status": "regular",
                        "notes": []
                    },
                    {
                        "catalog_no": "4",
                        "issue_id": "CR-1863-FIRST-ISSUE",
                        "denomination": {"value": 1, "unit": "P"},
                        "color": "yellow",
                        "plate": None,
                        "perforation": "",
                        "watermark": None,
                        "quantity_reported": 35000,
                        "status": "regular",
                        "notes": []
                    }
                ],
                "varieties": [
                    {"base_catalog_no": "1", "suffix": "a", "type": "perforation", "description": "double perf horizontal", "position": None, "plate": None},
                    {"base_catalog_no": "1", "suffix": "b", "type": "perforation", "description": "double perf diagonal", "position": None, "plate": None},
                    {"base_catalog_no": "1", "suffix": "c", "type": "impression", "description": "double impression at right", "position": None, "plate": None},
                    {"base_catalog_no": "1", "suffix": "d", "type": "plate_flaw", "description": "cracked plate", "position": "pos 1", "plate": 1},
                    {"base_catalog_no": "1", "suffix": "e", "type": "plate_flaw", "description": "cracked plate", "position": "pos 11", "plate": 1},
                    {"base_catalog_no": "1", "suffix": "f", "type": "plate_flaw", "description": "cracked plate", "position": "pos 21", "plate": 1},
                    {"base_catalog_no": "1", "suffix": "g", "type": "plate_flaw", "description": "period in center second star", "position": "pos 87", "plate": None},
                    {"base_catalog_no": "1", "suffix": "h", "type": "plate_flaw", "description": "period in center third star", "position": "pos 89", "plate": None},
                    {"base_catalog_no": "1", "suffix": "i", "type": "plate_flaw", "description": "line on top volcano", "position": "pos 96", "plate": None},
                    {"base_catalog_no": "1A", "suffix": "a", "type": "perforation", "description": "imperf horizontal (pair or blocks-38)", "position": None, "plate": 2},
                    {"base_catalog_no": "2", "suffix": "a", "type": "plate_flaw", "description": "engraver line through DOS", "position": "pos 1", "plate": None},
                    {"base_catalog_no": "3", "suffix": "a", "type": "plate_flaw", "description": "double entry of \"Correos de Costa Rica\"", "position": "pos 8", "plate": None}
                ],
                "proofs": {"die_proofs": [], "plate_proofs": [], "color_proofs": [], "imperforate_proofs": []},
                "essays": [],
                "specimens": [],
                "postal_stationery": []
            }, indent=2)
        },
        {
            "input": """Surcharges 1881-82

        December 16, 1880. Accord 53 (2c), September or October 1882 (1c), December 1882 (5c).
        Surcharged by Imprenta Nacional in vermilion.
        Decimal currency was adopted in 1864: 100 centavos = 1 peso.
        Quantities unknown. Demonetized February 1, 1883. (Ref Ox 100, 1985, Ox 211, 2013).

        5
        1c on ½ real (plate 1) in straight letters

        5a
        surcharge on 1A (plate 2)

        6
        1c on ½ real (plate 1) in cursive letters

        7
        2c on ½ real (plate 1)

        7a
        surcharge on 1A (plate 2)

        7b
        double surcharge

        7c
        inverted op (one known in a block)

        7d
        Cts instead of cts (doubtful-Ox 114)

        8
        5c on ½ real 1A (plate 2) - never used

        8a
        double surcharge

        All varieties of base stamp #1 exist on stamp #5, 6 and 7.
        #5 and 6 exist se-tenant.
        Proofs in black of 5, 7 & 8 may exist.
        """,
            "output": json.dumps({
                "issue_data": {
                    "issue_id": "CR-1881-82-SURCHARGES",
                    "section": "Surface Mail",
                    "title": "Surcharges 1881–82",
                    "country": "Costa Rica",
                    "issue_dates": {
                        "announced": None,
                        "placed_on_sale": "1880-12-16",
                        "probable_first_circulation": None,
                        "second_plate_sale": None,
                        "demonetized": "1883-02-01"
                    },
                    "legal_basis": ["Accord 53 (2c)", "September or October 1882 (1c)", "December 1882 (5c)"],
                    "currency_context": {
                        "original": "centavo/peso",
                        "decimal_adoption": "1864",
                        "revaluation_date": None,
                        "revaluation_map": {"100 centavos": "1 peso"}
                    },
                    "printing": {
                        "printer": "Imprenta Nacional",
                        "process": ["surcharged in vermilion"],
                        "format": {"panes": None},
                        "plates": {}
                    },
                    "perforation": ""
                },
                "production_orders": {
                    "printings": [],
                    "remainders": {"date": None, "notes": "Quantities unknown", "quantities": []}
                },
                "stamps": [
                    {
                        "catalog_no": "5",
                        "issue_id": "CR-1881-82-SURCHARGES",
                        "denomination": {"value": 1, "unit": "c"},
                        "color": "blue with vermilion surcharge",
                        "plate": 1,
                        "perforation": "",
                        "watermark": None,
                        "quantity_reported": None,
                        "status": "regular",
                        "notes": ["1c on ½ real (plate 1) in straight letters"]
                    },
                    {
                        "catalog_no": "6",
                        "issue_id": "CR-1881-82-SURCHARGES",
                        "denomination": {"value": 1, "unit": "c"},
                        "color": "blue with vermilion surcharge",
                        "plate": 1,
                        "perforation": "",
                        "watermark": None,
                        "quantity_reported": None,
                        "status": "regular",
                        "notes": ["1c on ½ real (plate 1) in cursive letters"]
                    },
                    {
                        "catalog_no": "7",
                        "issue_id": "CR-1881-82-SURCHARGES",
                        "denomination": {"value": 2, "unit": "c"},
                        "color": "blue with vermilion surcharge",
                        "plate": 1,
                        "perforation": "",
                        "watermark": None,
                        "quantity_reported": None,
                        "status": "regular",
                        "notes": ["2c on ½ real (plate 1)"]
                    },
                    {
                        "catalog_no": "8",
                        "issue_id": "CR-1881-82-SURCHARGES",
                        "denomination": {"value": 5, "unit": "c"},
                        "color": "light blue with vermilion surcharge",
                        "plate": 2,
                        "perforation": "",
                        "watermark": None,
                        "quantity_reported": None,
                        "status": "regular",
                        "notes": ["5c on ½ real 1A (plate 2) - never used"]
                    }
                ],
                "varieties": [
                    {"base_catalog_no": "5", "suffix": "a", "type": "plate", "description": "surcharge on 1A (plate 2)", "position": None, "plate": 2},
                    {"base_catalog_no": "7", "suffix": "a", "type": "plate", "description": "surcharge on 1A (plate 2)", "position": None, "plate": 2},
                    {"base_catalog_no": "7", "suffix": "b", "type": "surcharge", "description": "double surcharge", "position": None, "plate": None},
                    {"base_catalog_no": "7", "suffix": "c", "type": "surcharge", "description": "inverted op (one known in a block)", "position": None, "plate": None},
                    {"base_catalog_no": "7", "suffix": "d", "type": "surcharge", "description": "Cts instead of cts (doubtful-Ox 114)", "position": None, "plate": None},
                    {"base_catalog_no": "8", "suffix": "a", "type": "surcharge", "description": "double surcharge", "position": None, "plate": None}
                ],
                "proofs": {
                    "die_proofs": [],
                    "plate_proofs": [],
                    "color_proofs": [
                        {"code": "5P", "denomination": "1c", "color": "black", "notes": "Proof in black (may exist)"},
                        {"code": "7P", "denomination": "2c", "color": "black", "notes": "Proof in black (may exist)"},
                        {"code": "8P", "denomination": "5c", "color": "black", "notes": "Proof in black (may exist)"}
                    ],
                    "imperforate_proofs": []
                },
                "essays": [],
                "specimens": [],
                "postal_stationery": []
            }, indent=2)
        },
        {
            "input": """TELEGRAPH SEALS
        Lithography by Litografia Nacional. Perf 12.
        
        Proofs, imperf
        PTS2   blue, white paper
        PTS2a  blue, pink paper
        PTS5   dark blue, white paper
        
        Regular issue
        TS1    blue
        TS2    light blue, perf 12
        TS2a   horizontal pair imperf between
        TS3    black, imperf
        TS5    dark blue, white paper
        TS8    blue, pink paper
        
        RADIOGRAM SEALS
        "Radios de Costa Rica". "CR" in center. Imperforate.
        
        IRS1   brown, yellow paper
        RS1    brown, yellow paper
        RS2    reddish brown, pink paper
        RS6    brown, pink paper
        """,
            "output": json.dumps({
                "stamps": [
                    {
                        "catalog_no": "TS1",
                        "denomination": {"value": None, "unit": "seal"},
                        "color": "blue",
                        "paper": "",
                        "perforation": "12",
                        "status": "telegraph_seal",
                        "notes": ["Telegraph seal"]
                    },
                    {
                        "catalog_no": "TS2",
                        "denomination": {"value": None, "unit": "seal"},
                        "color": "light blue",
                        "paper": "",
                        "perforation": "12",
                        "status": "telegraph_seal",
                        "notes": ["Telegraph seal"]
                    },
                    {
                        "catalog_no": "TS3",
                        "denomination": {"value": None, "unit": "seal"},
                        "color": "black",
                        "paper": "",
                        "perforation": "",
                        "status": "telegraph_seal",
                        "notes": ["Telegraph seal. Imperf"]
                    },
                    {
                        "catalog_no": "TS5",
                        "denomination": {"value": None, "unit": "seal"},
                        "color": "dark blue",
                        "paper": "white paper",
                        "perforation": "12",
                        "status": "telegraph_seal",
                        "notes": ["Telegraph seal"]
                    },
                    {
                        "catalog_no": "TS8",
                        "denomination": {"value": None, "unit": "seal"},
                        "color": "blue",
                        "paper": "pink paper",
                        "perforation": "12",
                        "status": "telegraph_seal",
                        "notes": ["Telegraph seal"]
                    },
                    {
                        "catalog_no": "IRS1",
                        "denomination": {"value": None, "unit": "seal"},
                        "color": "brown",
                        "paper": "yellow paper",
                        "perforation": "",
                        "status": "radiogram_seal",
                        "notes": ["Radiogram seal. Radios de Costa Rica. Imperf"]
                    },
                    {
                        "catalog_no": "RS1",
                        "denomination": {"value": None, "unit": "seal"},
                        "color": "brown",
                        "paper": "yellow paper",
                        "perforation": "",
                        "status": "radiogram_seal",
                        "notes": ["Radiogram seal. Radios de Costa Rica. Imperf"]
                    },
                    {
                        "catalog_no": "RS2",
                        "denomination": {"value": None, "unit": "seal"},
                        "color": "reddish brown",
                        "paper": "pink paper",
                        "perforation": "",
                        "status": "radiogram_seal",
                        "notes": ["Radiogram seal. Design with CR in center. Imperf"]
                    },
                    {
                        "catalog_no": "RS6",
                        "denomination": {"value": None, "unit": "seal"},
                        "color": "brown",
                        "paper": "pink paper",
                        "perforation": "",
                        "status": "radiogram_seal",
                        "notes": ["Radiogram seal. Design with RN in center. Imperf"]
                    }
                ],
                "varieties": [
                    {
                        "base_catalog_no": "TS2",
                        "suffix": "a",
                        "type": "perforation",
                        "description": "horizontal pair imperf between",
                        "position": None,
                        "plate": None
                    }
                ],
                "proofs": {
                    "plate_proofs": [
                        {"code": "PTS2", "denomination": "seal", "color": "blue", "notes": "Telegraph seal proof. White paper. Imperf"},
                        {"code": "PTS2a", "denomination": "seal", "color": "blue", "notes": "Telegraph seal proof. Pink paper. Imperf"},
                        {"code": "PTS5", "denomination": "seal", "color": "dark blue", "notes": "Telegraph seal proof. White paper. Imperf"}
                    ]
                }
            }, indent=2)
        }
    ]
    
    # System message with blank instruction sections
    system_message = create_system_message()
    
    # Build complete prompt string
    full_prompt = system_message + "\n\n"
    
    # Add examples in a formatted way
    for i, example in enumerate(examples, 1):
        full_prompt += f"{'='*80}\n"
        full_prompt += f"EXAMPLE {i}\n"
        full_prompt += f"{'='*80}\n\n"
        full_prompt += f"INPUT:\n{example['input']}\n\n"
        full_prompt += f"OUTPUT:\n{example['output']}\n\n"
    
    # Add final instruction section
    final_instruction = """
Now, when given a text from Mena Catalog, you must:
1. First analyze the input and identify key components
2. Extract all available information following the Mena Catalogue format
3. Output ONLY valid JSON matching the MenaCatalogEntry schema
4. If information is missing or unclear, use null for optional fields
5. Always validate your output against the schema before returning

Remember: Quality and accuracy are paramount in philately!
"""
    
    full_prompt += final_instruction
    
    return full_prompt


# ============================================================================
# Step 3: CustomMenaParserTool
# ============================================================================
class MenaEntryParserInput(BaseModel):
    """Input model for Mena Catalog entry parsing."""
    
    model_config = ConfigDict(extra='forbid')  # This helps with OpenAI schema
    
    # Change from 'dict' to 'str' - LLM will provide JSON string
    parsed_data: str = Field(
        description="JSON string containing the complete parsed catalog entry data with all required sections: "
                    "issue_data, production_orders, stamps, varieties, proofs, essays, specimens, postal_stationery. "
                    "Must be valid JSON format."
    )


class MenaEntryParserTool(Tool[MenaEntryParserInput, ToolRunOptions, StringToolOutput]):
    """
    Custom tool that uses Pydantic schema to validate and structure
    the agent's output for Mena Catalog entries.
    """
    name = "MenaEntryParserTool"
    description = (
        "Validates and structures Costa Rica stamp catalog entries in Mena Catalog format. "
        "Takes a JSON string with parsed catalog data and validates it against the MenaCatalogEntry schema. "
        "Returns validation results with detailed feedback."
    )
    input_schema = MenaEntryParserInput

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        super().__init__(options)

    def _create_emitter(self) -> Emitter:
        return Emitter.root().child(
            namespace=["tool", "mena", "parser"],
            creator=self,
        )

    async def _run(
        self, 
        input: MenaEntryParserInput, 
        options: ToolRunOptions | None, 
        context: RunContext
    ) -> StringToolOutput:
        """
        Executes parsing and validation.
        
        Args:
            input: MenaEntryParserInput with parsed_data as JSON string
            options: Tool run options
            context: Run context
            
        Returns:
            StringToolOutput with validation results
        """
        try:
            # Parse JSON string to dict
            data_dict = json.loads(input.parsed_data)
            
            # Validate against Pydantic schema
            catalog_entry = MenaCatalogEntry(**data_dict)
            
            # Generate success output
            output = f"✅ Mena Catalog Entry Validation SUCCESS\n"
            output += f"{'='*60}\n\n"
            output += f"Issue ID: {catalog_entry.issue_data.issue_id}\n"
            output += f"Title: {catalog_entry.issue_data.title}\n"
            output += f"Country: {catalog_entry.issue_data.country}\n\n"
            output += f"📊 Summary:\n"
            output += f"  • Stamps: {len(catalog_entry.stamps)}\n"
            output += f"  • Varieties: {len(catalog_entry.varieties)}\n"
            
            total_proofs = (
                len(catalog_entry.proofs.die_proofs) +
                len(catalog_entry.proofs.plate_proofs) +
                len(catalog_entry.proofs.color_proofs) +
                len(catalog_entry.proofs.imperforate_proofs)
            )
            output += f"  • Proofs: {total_proofs}\n"
            output += f"  • Specimens: {len(catalog_entry.specimens)}\n"
            output += f"  • Essays: {len(catalog_entry.essays)}\n"
            output += f"  • Postal Stationery: {len(catalog_entry.postal_stationery)}\n\n"
            
            output += f"✅ All validation checks passed!\n"
            output += f"Entry {catalog_entry.issue_data.issue_id} is ready to use.\n"
            
            return StringToolOutput(output)
            
        except json.JSONDecodeError as e:
            # JSON parsing error
            output = f"❌ JSON Parsing Error\n"
            output += f"{'='*60}\n\n"
            output += f"Error: Invalid JSON format\n"
            output += f"Details: {str(e)}\n\n"
            output += f"Please ensure the parsed_data is valid JSON.\n"
            
            return StringToolOutput(output)
            
        except Exception as e:
            # Validation error
            output = f"❌ Mena Catalog Entry Validation FAILED\n"
            output += f"{'='*60}\n\n"
            output += f"Error: {str(e)}\n\n"
            output += f"Schema validation failed. Please check:\n"
            output += f"  • All required fields are present\n"
            output += f"  • issue_data has valid issue_id, title, country\n"
            output += f"  • stamps array has valid catalog_no and denomination\n"
            output += f"  • All 8 sections are included (even if empty)\n"
            
            return StringToolOutput(output)

# ============================================================================
# Step 4: MenaParser RequirementAgent with ThinkTool
# ============================================================================
async def create_mena_catalogue_agent():
    """
    Creates the RequirementAgent configured to parse Mena Catalogue entries.
    
    Uses GPT-5-mini reasoning model (no ThinkTool needed)
    """
    
    llm = ChatModel.from_name("openai:gpt-5-mini", ChatModelParameters(temperature=0)) #openai:gpt-5-nano #watsonx:meta-llama/llama-4-maverick-17b-128e-instruct-fp8
    
    # Create system prompt with few-shot examples
    system_prompt = create_few_shot_system_prompt()
    # Create agent with requirements
    agent = RequirementAgent(
        llm=llm,
        tools = [],
        # # Available tools
        # tools=[
        #     MenaEntryParserTool(),  # For final validation
        # ],
        
        # # Requirements:
        # requirements=[
        #   # Step 1: Then validate with parser
        #   ConditionalRequirement(
        #       MenaEntryParserTool,
        #       force_at_step=2,
        #       max_invocations=1,  
        #       consecutive_allowed=False
        #   ),
        # ],
        
        # Agent role and instructions
        #role="Mena Catalogue Costa Rica Philately Expert",
        
        instructions=system_prompt,
        
        # Memory to maintain context
        memory=UnconstrainedMemory(),
    )
    
    return agent


# ============================================================================
# STEP 5: Main function to execute the agent
# ============================================================================
def generate_mena_report(entry: MenaCatalogEntry) -> str:
    """
    Generate a human-readable report from a Mena catalog entry.
    
    Args:
        entry: Validated MenaCatalogEntry
        
    Returns:
        Formatted report string
    """
    report = f"""
{'='*80}
MENA CATALOG ENTRY REPORT
{'='*80}

ISSUE INFORMATION
─────────────────
Issue ID:     {entry.issue_data.issue_id}
Title:        {entry.issue_data.title}
Country:      {entry.issue_data.country}
Section:      {entry.issue_data.section}
Perforation:  {entry.issue_data.perforation if entry.issue_data.perforation else 'Not specified'}

DATES
─────
"""
    
    if entry.issue_data.issue_dates.placed_on_sale:
        report += f"Placed on Sale:  {entry.issue_data.issue_dates.placed_on_sale}\n"
    if entry.issue_data.issue_dates.announced:
        report += f"Announced:       {entry.issue_data.issue_dates.announced}\n"
    if entry.issue_data.issue_dates.demonetized:
        report += f"Demonetized:     {entry.issue_data.issue_dates.demonetized}\n"
    
    if entry.issue_data.legal_basis:
        report += f"\nLEGAL BASIS\n───────────\n"
        for i, basis in enumerate(entry.issue_data.legal_basis[:3], 1):
            basis_text = basis if isinstance(basis, str) else getattr(basis, 'id', str(basis))
            report += f"{i}. {basis_text}\n"
    
    if entry.issue_data.printing.printer:
        report += f"\nPRINTING\n────────\n"
        report += f"Printer:  {entry.issue_data.printing.printer}\n"
        if entry.issue_data.printing.process:
            report += f"Process:  {', '.join(entry.issue_data.printing.process)}\n"
    
    report += f"\nSTAMPS: {len(entry.stamps)}\n{'─'*80}\n"
    
    for stamp in entry.stamps[:10]:  # Show first 10
        if stamp.denomination.value:
            denom = f"{stamp.denomination.value}{stamp.denomination.unit}"
        else:
            denom = stamp.denomination.unit
        
        color = f" - {stamp.color}" if stamp.color else ""
        qty = f" (Qty: {stamp.quantity_reported:,})" if stamp.quantity_reported else ""
        
        report += f"  {stamp.catalog_no:6s} │ {denom:10s}{color:20s} │ {stamp.status:15s}{qty}\n"
    
    if len(entry.stamps) > 10:
        report += f"  ... and {len(entry.stamps) - 10} more stamps\n"
    
    if entry.varieties:
        report += f"\nVARIETIES: {len(entry.varieties)}\n{'─'*80}\n"
        for variety in entry.varieties[:5]:  # Show first 5
            report += f"  {variety.base_catalog_no}{variety.suffix:2s} │ {variety.type:15s} │ {variety.description}\n"
        if len(entry.varieties) > 5:
            report += f"  ... and {len(entry.varieties) - 5} more varieties\n"
    
    total_proofs = (
        len(entry.proofs.die_proofs) +
        len(entry.proofs.plate_proofs) +
        len(entry.proofs.color_proofs) +
        len(entry.proofs.imperforate_proofs)
    )
    
    if total_proofs > 0:
        report += f"\nPROOFS: {total_proofs}\n{'─'*80}\n"
        report += f"  Die proofs:         {len(entry.proofs.die_proofs)}\n"
        report += f"  Plate proofs:       {len(entry.proofs.plate_proofs)}\n"
        report += f"  Color proofs:       {len(entry.proofs.color_proofs)}\n"
        report += f"  Imperforate proofs: {len(entry.proofs.imperforate_proofs)}\n"
    
    if entry.specimens:
        report += f"\nSPECIMENS: {len(entry.specimens)}\n{'─'*80}\n"
        for specimen in entry.specimens[:3]:
            report += f"  {specimen.code:8s} │ {specimen.type:12s} │ {specimen.denomination}\n"
    
    if entry.essays:
        report += f"\nESSAYS: {len(entry.essays)}\n"
    
    if entry.postal_stationery:
        report += f"\nPOSTAL STATIONERY: {len(entry.postal_stationery)}\n{'─'*80}\n"
        for item in entry.postal_stationery[:3]:
            denom = f"{item.denomination.value}{item.denomination.unit}" if item.denomination.value else ""
            report += f"  {item.catalog_no:6s} │ {item.stationery_type:18s} │ {denom}\n"
    
    if entry.production_orders.printings:
        total_printed = sum(
            sum(q.quantity for q in printing.quantities)
            for printing in entry.production_orders.printings
        )
        if total_printed > 0:
            report += f"\nTOTAL PRODUCTION: {total_printed:,} stamps\n"
    
    report += f"\n{'='*80}\n"
    
    return report
#------------------------------------------------------------

# -----------------------------------------------------------------------------
# LLM factory
# -----------------------------------------------------------------------------
def _make_llm():
    # Swap to another model if you like
    return ChatModel.from_name("watsonx:openai/gpt-oss-120b", ChatModelParameters(temperature=0))


# =============================================================================
# 1) EXPERT AGENTS
# =============================================================================

def create_mena_generator_agent() -> RequirementAgent:
    """
    EXPERT 1 — GENERATOR
    Produces the first JSON version strictly following your schema.
    Must return ONLY the JSON object with the 8 top-level sections.
    """
    llm = _make_llm()
    sys_prompt = create_few_shot_system_prompt()

    return RequirementAgent(
        llm=llm,
        tools=[],
        instructions=sys_prompt,
        memory=UnconstrainedMemory(),
        # Keep it clean: no middleware/requirements here
    )


def create_mena_critic_agent() -> RequirementAgent:
    """
    EXPERT 2 — CRITIC (RUBRIC ONLY)
    Provides rubric-style coverage feedback ONLY (no low-level schema validation, no patch ops).
    Must return ONE JSON object:

    {
      "rubric": [
        { "section":"issue_data","score_5":0.0,"stars":"★★★★✩","percent":0,
          "what_was_captured":[], "what_is_missing":[], "improvements":[] },
        ... for each section ...
      ],
      "overall": {"score_5":0.0,"stars":"★★★★✩","percent":0},
      "global_notes_to_add": [],
      "fix_priorities": []
    }
    """
    llm = _make_llm()
    critic_system = """
You are a rubric-style reviewer for the Mena Catalogue parser.
Assess COVERAGE and CLARITY ONLY. Do NOT validate schema paths or produce code/patch ops.
Return ONE JSON object (no prose/markdown) with this shape:

{
  "rubric": [
    {
      "section": "issue_data",
      "score_5": 0.0,            // 0..5 (fractional allowed)
      "stars": "★★★✩✩",          // visual representation
      "percent": 0,              // round(score_5 * 20)
      "what_was_captured": ["..."],
      "what_is_missing": ["..."], // exact items from source_text absent in generator_output
      "improvements": ["..."]     // actionable steps (coverage/clarity only)
    },
    { "section": "production_orders", ... },
    { "section": "stamps", ... },
    { "section": "varieties", ... },
    { "section": "proofs", ... },
    { "section": "essays", ... },
    { "section": "specimens", ... },
    { "section": "postal_stationery", ... }
  ],
  "overall": {
    "score_5": 0.0,
    "stars": "★★★★✩",
    "percent": 0
  },
  "global_notes_to_add": [],
  "fix_priorities": []
}

SCORING:
- 0..5 stars per section. percent = round(score_5 * 20).
- Focus on coverage: Did the generator include all items clearly present in source_text?
- “what_is_missing” should list concrete items from source_text that are absent in the JSON.
CONSTRAINTS:
- Do NOT invent data. Base everything on source_text and generator_output.
- Output ONLY the JSON object above (no prose/markdown).
"""
    return RequirementAgent(
        llm=llm,
        tools=[],
        instructions=critic_system,
        memory=UnconstrainedMemory(),
    )


def create_mena_fixer_agent() -> RequirementAgent:
    """
    EXPERT 3 — FIXER
    Uses the critic’s rubric & the source_text to produce the final, schema-correct JSON.
    Must output ONLY one JSON object with EXACTLY these top-level keys:
      "issue_data", "production_orders", "stamps", "varieties",
      "proofs", "essays", "specimens", "postal_stationery"
    """
    llm = _make_llm()
    fixer_system = """
You are the Fixer for the Mena Catalogue parser.
Inputs you receive:
- source_text: original catalog text
- generator_output: initial JSON from the Generator
- critic_feedback: rubric-style JSON with coverage scores, missing items, improvements

TASK:
- Improve coverage based on critic_feedback.rubric[*].what_is_missing using ONLY source_text.
- Preserve critic_feedback.global_notes_to_add in appropriate notes[] fields.
- Apply improvements that are supported by source_text.
- Enforce master schema rules (units, surcharge parsing, S-codes only in specimens, postal_stationery logic, etc.).
- Do NOT invent codes, quantities, colors, or dates not present in source_text.
- Keep quantity_reported null unless explicitly stated for that catalog_no.
- Keep strict separation between specimens, varieties, and stamps.
- Output ONLY ONE final JSON object with EXACTLY the 8 required top-level keys.

UNKNOWN/UNSTATED:
- Use "", null, [], {} as appropriate per schema.

NO EXTRAS:
- Do not add keys beyond the schema.
"""
    return RequirementAgent(
        llm=llm,
        tools=[],
        instructions=fixer_system,
        memory=UnconstrainedMemory(),
    )


# =============================================================================
# 2) COORDINATOR + HANDOFFS
# =============================================================================

# ---------------- Coordinator with strict order ----------------
def build_coordinator() -> RequirementAgent:
    llm = _make_llm()

    # Experts
    gen_agent = create_mena_generator_agent()
    critic_agent = create_mena_critic_agent()
    fixer_agent = create_mena_fixer_agent()

    # Handoffs (named)
    to_generator = HandoffTool(gen_agent,   name="Generator",
                               description="Create first JSON draft (schema-aware).")
    to_critic   = HandoffTool(critic_agent, name="Critic",
                               description="Return rubric-only coverage feedback.")
    to_fixer    = HandoffTool(fixer_agent,  name="Fixer",
                               description="Apply rubric + source to output final schema-valid JSON.")

    # Coordinator prompt tells the agent exactly what to call at each step
    coord_sys = """
You are the COORDINATOR for the Mena pipeline. Follow this exact order:

Step 1 (Think): Use ThinkTool to plan the handoffs.
Step 2 (Generator): Call Tool "Generator" with {"source_text": <text>} → get generator_output (JSON only).
Step 3 (Critic): Call Tool "Critic" with {"source_text": <text>, "generator_output": <generator_output>} → critic_feedback.
Step 4 (Fixer): Call Tool "Fixer" with {"source_text": <text>, "generator_output": <generator_output>, "critic_feedback": <critic_feedback>} → final_output.

Your FINAL response must be ONE JSON object (no prose/markdown):
{
  "generator_output": <generator_output>,
  "critic_feedback": <critic_feedback>,
  "final_output": <final_output>
}
"""

    coordinator = RequirementAgent(
        llm=llm,
        tools=[to_generator, to_critic, to_fixer, ThinkTool()],
        instructions=coord_sys,
        memory=UnconstrainedMemory(),
        middlewares=[GlobalTrajectoryMiddleware(included=[Tool])],
        requirements=[
            # ENFORCE STRICT ORDER:
            # 1) ThinkTool must run first, exactly once
            ConditionalRequirement(ThinkTool, force_at_step=1, min_invocations=1, max_invocations=1),

            # 2) Generator must run second, exactly once (after ThinkTool)
            ConditionalRequirement(to_generator, force_at_step=2, min_invocations=1, max_invocations=1, only_after=[ThinkTool]),

            # 3) Critic must run third, exactly once (after Generator)
            ConditionalRequirement(to_critic,   force_at_step=3, min_invocations=1, max_invocations=1, only_after=[type(to_generator)]),

            # 4) Fixer must run last, exactly once (after Critic)
            ConditionalRequirement(to_fixer,    force_at_step=4, min_invocations=1, max_invocations=1, only_after=[type(to_critic)]),

            # (Optional) ask permission before using any handoff tools
            #AskPermissionRequirement(["Generator", "Critic", "Fixer"])
        ],
    )

    return coordinator


# =============================================================================
# 3) PUBLIC API
# =============================================================================

async def run_mena_pipeline_with_coordinator(source_text: str) -> Dict[str, Any]:
    """
    Public entrypoint: one call, coordinator handles the full pipeline via handoffs.
    Returns dict with: generator_output, critic_feedback, final_output
    """
    coordinator = build_coordinator()

    # The coordinator expects a single string prompt. We pass a compact JSON string with the source.
    payload = json.dumps({"source_text": source_text}, ensure_ascii=False)
    try:
      result = await coordinator.run(payload)  #, expected_output=MenaCatalogEntry)
      #Coordinator is instructed to return ONE JSON object in result.answer.text
      assembled = json.loads(result.answer.text)
      catalog_entry = assembled.get("generator_output")
      
      if catalog_entry:
          print(f"\n{'='*80}")
          print("✅ Successfully parsed and validated catalog entry!")
          print(f"{'='*80}\n")
          
          # Generate and print report
          report = generate_mena_report(catalog_entry)
          print(report)
          
          # Save to file
          with open('mena_catalog_output.json', 'w', encoding='utf-8') as f:
              f.write(catalog_entry.model_dump_json(indent=2, exclude_none=True))
          print("💾 Saved to: mena_catalog_output.json")
          
          return catalog_entry
      else:
          print("⚠️ No structured output available")
          return None
      
    except Exception as e:
      print(f"\n❌ Error: {str(e)}")
      import traceback
      traceback.print_exc()
      return None


# async def parse_mena_catalog_entry(catalog_text: str):
#     """
#     Parses a catalog entry in Mena Catalogue format.
    
#     Args:
#         catalog_text: Text in Mena Catalogue format (can include HTML tables)
        
#     Returns:
#         Dict with parsed and validated catalog entry
#     """
#     # Create the agent
#     agent = await create_mena_catalogue_agent()
    
#     # Prepare user prompt
#     user_prompt = f"""Parse the following catalog entry according to Mena Catalogue format:

#     {catalog_text}

#     Extract and return ONLY the structured JSON data with all 8 required sections:
#     - issue_data
#     - production_orders
#     - stamps
#     - varieties
#     - proofs
#     - essays
#     - specimens
#     - postal_stationery

#     """
    
#     # Execute agent
#     print(f"\n{'='*80}")
#     print("🔍 Starting Mena Catalogue Parser Agent")
#     print(f"{'='*80}\n")
#     print(f"Input:\n{catalog_text[:200]}...\n")
    
#     try:
#         response = await agent.run(
#             prompt=user_prompt,
#             expected_output=MenaCatalogEntry
#         )
        
#         print(f"\n{'='*80}")
#         print("✅ Agent Response:")
#         print(f"{'='*80}\n")
#         print(response.answer.text)
        
#         catalog_entry = response.answer_structured
        
#         if catalog_entry:
#             print(f"\n{'='*80}")
#             print("✅ Successfully parsed and validated catalog entry!")
#             print(f"{'='*80}\n")
            
#             # Generate and print report
#             report = generate_mena_report(catalog_entry)
#             print(report)
            
#             # Save to file
#             with open('mena_catalog_output.json', 'w', encoding='utf-8') as f:
#                 f.write(catalog_entry.model_dump_json(indent=2, exclude_none=True))
#             print("💾 Saved to: mena_catalog_output.json")
            
#             return catalog_entry
#         else:
#             print("⚠️ No structured output available")
#             return None
        
#     except Exception as e:
#         print(f"\n❌ Error: {str(e)}")
#         import traceback
#         traceback.print_exc()
#         return None


# Convenience wrapper (if you want a function name similar to your previous API)
async def parse_mena_catalog_entry(catalog_text: str) -> Dict[str, Any]:
    """
    Backward-friendly wrapper that uses the new coordinator pipeline.
    Saves the final output to disk as 'mena_catalog_output.json'
    """
    print("\n" + "="*80)
    print("🤝 Mena Multi-Agent (Coordinator + Handoffs) — Generator → Critic → Fixer")
    print("="*80 + "\n")

    assembled = await run_mena_pipeline_with_coordinator(catalog_text)

    return assembled



# ============================================================================
# EXAMPLE USAGE
# ============================================================================


# Run the example
if __name__ == "__main__":
    """Example usage with Costa Rica insect issue"""
    
    test = """
    ## First Issue
    April 11, 1863. Decree #2 of August 18, 1862. Engraved and recess printed by ABNCo. in panes of 100. Perf 12. The half real and 2 reales stamps probably circulated on April 11, 1863. No authorizing decree is known for the 4 reales and 1 peso stamps. Circulation was authorized by letters No. 30 of August 27, 1863 from Francisco Echeverria to the Minister of Foreign Relations and No. 53 of August 30, 1863 from Julian Volio, Minister of Foreign Relations, to Luis Molina, the Costa Rican Ambassador in Washington. Probably placed on sale in December 1863. Second plate half real stamps probably were placed on sale in September 1875. The half real stamp printed from two plates since the original one developed a crack. The second plate is in light blue with little or no sky over the mountains. After decimal currency was adopted in 1864 and since June 9, 1866 the 2 real stamp had a value of 5c, the 2 reales 25c and the 4 reales 50c. Perf 12. Demonetized January 31, 1883. Remainders were sold to Jaime Ross on May 23, 1883. (Ref The Collectors Club Philatelist, April 1948; Ox 75, 1979.)

    Essay on thick grayish laid paper, on card
    E1 dark blue, hand painted (ex-Mayer)

    Die Proofs on India paper, imperf or sunk on card

    DP1: ½ real black die #332
    DP2: 2 reales black die #330
      DP2a: scarlet
    DP3: 4 reales black die #387
    DP4: 1 peso black die #388
      DP4a: green
      DP4b: brown
      DP4c: reddish brown

    <table id="7-1">
    <tr><td id="7-2">Plate PP1</td><td id="7-3" colspan="2">Proofs in India paper, impert or on card 1½ real blue (plate 1)</td></tr>
    <tr><td id="7-4"></td><td id="7-5">PP1a PP1b PP1c PP1d</td><td id="7-6">black on backer paper yellow green orange</td></tr>
    <tr><td id="7-7">PP1A PP2</td><td id="7-8"></td><td id="7-9">1/2 real light blue (plate 2) 2 reales scarlet</td></tr>
    <tr><td id="7-a"></td><td id="7-b">PP2a PP2c PP2d</td><td id="7-c" rowspan="2">reddish purple yellow green 4 reales green blue</td></tr>
    <tr><td id="7-d">PP3</td><td id="7-e">PP3a</td></tr>
    <tr><td id="7-f">PP4</td><td id="7-g">PP4a PP4b PP4c PP4d</td><td id="7-h">1 peso yellow black green gray brown red brown</td></tr>
    <tr><td id="7-i" colspan="3">Same as above overprinted "specimen"</td></tr>
    <tr><td id="7-j">S1a</td><td id="7-k"></td><td id="7-l">½ real blue, yellow op</td></tr>
    <tr><td id="7-m">S1b</td><td id="7-n"></td><td id="7-o">blue, dark red op</td></tr>
    </table>



    SURFACE MAIL

    Costa Rica Postal Catalogue

    S2a 2 reales scarlet, oblique black op
    S2b scarlet, oblique red op
    S2c scarlet, vertical red op
    S3a 4 reales green, oblique black op
    S3b green, oblique green op
    S3c green, oblique red op
    S4a 1 peso yellow, oblique black op
    S4b yellow, oblique red op
    Many of these proofs also exist mounted on card.





    ABNCo. used the 2 reales stamp with 18 stamps from other countries in sample sheets for its salesman in 1867-8. They are known in about 150 varieties of color and paper, mostly engraved and perforated, but also lithographed and imperforate.

    Color Proofs, perf 12, thick gum (may come from above mentioned sample sheets)

    CP2a: 2 reales light green
    CP2b: dark green
    CP2c: blue
    CP2d: brown
    CP2e: black

    <table id="8-1">
    <tr><td id="8-2">Date of order</td><td id="8-3">1½ real 1st plate</td><td id="8-4">1½real 2nd plate</td><td id="8-5">2 reales</td><td id="8-6">4 reales</td><td id="8-7">1 peso</td></tr>
    <tr><td id="8-8">October 11, 1862</td><td id="8-9">250,000</td><td id="8-a">---</td><td id="8-b">250,000</td><td id="8-c">---</td><td id="8-d">---</td></tr>
    <tr><td id="8-e">September 30, 1863</td><td id="8-f">---</td><td id="8-g">---</td><td id="8-h">---</td><td id="8-i">20,000</td><td id="8-j">10,000</td></tr>
    <tr><td id="8-k">September 1865</td><td id="8-l">500,000</td><td id="8-m">---</td><td id="8-n">500,000</td><td id="8-o">50,000</td><td id="8-p">25,000</td></tr>
    <tr><td id="8-q">December 24, 1872</td><td id="8-r">2,000,000</td><td id="8-s">---</td><td id="8-t">---</td><td id="8-u">---</td><td id="8-v">---</td></tr>
    <tr><td id="8-w">June 18, 1875</td><td id="8-x">250,000</td><td id="8-y">2,750,000</td><td id="8-z">---</td><td id="8-A">---</td><td id="8-B">---</td></tr>
    <tr><td id="8-C">Sold to J. Ross</td><td id="8-D">1,000,000</td><td id="8-E">1,615,000</td><td id="8-F">385,000</td><td id="8-G">23,000</td><td id="8-H">10,500</td></tr>
    </table>

    <table id="8-I">
    <tr><td id="8-J">Regular issue</td><td id="8-K"></td><td id="8-L"></td></tr>
    <tr><td id="8-M">1</td><td id="8-N">½ real blue (plate 1)</td><td id="8-O">3,000,000</td></tr>
    <tr><td id="8-P">1a</td><td id="8-Q">double perf horizontal</td><td id="8-R"></td></tr>
    <tr><td id="8-S">1b</td><td id="8-T">double perf diagonal</td><td id="8-U"></td></tr>
    <tr><td id="8-V">1c</td><td id="8-W">double impression at right</td><td id="8-X"></td></tr>
    <tr><td id="8-Y">1d</td><td id="8-Z">cracked plate (pos 1)</td><td id="8-10"></td></tr>
    <tr><td id="8-11">1e</td><td id="8-12">cracked plate (pos 11)</td><td id="8-13"></td></tr>
    <tr><td id="8-14">1f</td><td id="8-15">cracked plate (pos 21)</td><td id="8-16"></td></tr>
    </table>

    Constant plate varieties:
    g: period in center second star (pos 87)
    h: period in center third star (pos 89)
    I: line on top volcano (pos 96)

    <table><thead><tr><th>Col&nbsp;1</th><th>Col&nbsp;2</th></tr></thead><tbody><tr><td>1A 1½ real light blue (plate 2)</td><td>2,750,000</td></tr><tr><td>&nbsp;&nbsp;&nbsp;&nbsp;1Aa imperf horizontal (pair or blocks-38)</td><td></td></tr><tr><td>2 2 reales scarlet</td><td>750,000</td></tr><tr><td>&nbsp;&nbsp;&nbsp;&nbsp;2a engraver line through DOS (pos 1)</td><td></td></tr><tr><td>3 4 reales green</td><td>70,000</td></tr><tr><td>&nbsp;&nbsp;&nbsp;&nbsp;3a double entry of "Correos de Costa Rica" (pos 8)</td><td></td></tr><tr><td>4 1 peso yellow</td><td>35,000</td></tr></tbody></table>





    SURFACE MAIL

    Costa Rica Postal Catalogue









    pos 2

    pos 96




    pos 8
    """
  
    import asyncio
    asyncio.run(parse_mena_catalog_entry(test))
    