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

# BeeAI Framework imports
from beeai_framework.agents.experimental import RequirementAgent
from beeai_framework.memory import TokenMemory
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



# =============================================================================
# 1. WATSONX MODEL CONFIG
# =============================================================================

def _make_generator_llm():
    return ChatModel.from_name(
        "watsonx:mistralai/mistral-medium-2505",
        ChatModelParameters(
            temperature=0.3,
            max_tokens=4000
        )
    )


def _make_critic_llm():
    return ChatModel.from_name(
        "watsonx:granite-3-2-8b-instruct",
        ChatModelParameters(
            temperature=0.1,
            max_tokens=2000
        )
    )


def _make_fixer_llm():
    return ChatModel.from_name(
        "watsonx:mistralai/mistral-medium-2505",  # Corregido: openai (no openain)
        ChatModelParameters(
            temperature=0.2,
            max_tokens=4000
        )
    )


def _make_coordinator_llm():
    """LLM optimizado para coordinación y decisiones."""
    return ChatModel.from_name(
        "watsonx:mistralai/mistral-medium-2505",  # Corregido: openai (no openain)
        ChatModelParameters(
            temperature=0.0,
            max_tokens=4000
        )
    )

# ============================================================================
# Step 1: Pydantic Schema for Mena Parser (MenaCatalogEntry)
# ============================================================================
from mena_catalog_schema import *


# ============================================================================
# Step 2: Few-Shot Examples using LangChain
# ============================================================================

from mena_stamp_agent_prompts import *

SCHEMA_EXPLANATION = create_system_message()
FEW_SHOT_EXAMPLES =  create_few_shot_examples()

# =============================================================================
# 4. PROMPTS MEJORADOS PARA CADA AGENTE
# =============================================================================

GENERATOR_SYSTEM_PROMPT = f"""
You are the MENA Catalog JSON Generator Expert.

{SCHEMA_EXPLANATION}

{FEW_SHOT_EXAMPLES}

YOUR TASK:
1. Read the catalog source_text carefully
2. Extract ALL information present (dates, quantities, codes, colors, etc.)
3. Generate ONE complete JSON object with EXACTLY 8 top-level sections
4. Follow the schema rules STRICTLY
5. Use the examples as your guide for structure
6. For unknown/unstated values, use "", null, [], or {{}} (NOT "unknown" or "N/A")

QUALITY CHECKLIST:
✓ All 8 sections present: issue_data, production_orders, stamps, varieties, proofs, essays, specimens, postal_stationery
✓ Denominations are objects with value + unit
✓ S-codes in specimens section (not stamps)
✓ Lowercase suffixes in varieties section (not stamps)
✓ quantity_reported only if explicitly stated
✓ Valid units: "c", "C", "P", "reales", "real", "sheet", "seal"

OUTPUT: ONE JSON object only (no markdown, no explanations, no commentary)
"""


CRITIC_SYSTEM_PROMPT = f"""
You are the MENA Catalog Coverage Critic.

YOUR SOLE TASK: Assess COVERAGE and CLARITY of the generated JSON.

{SCHEMA_EXPLANATION}

SCORING METHODOLOGY:
For each of the 8 sections, evaluate:
- What was captured correctly from source_text?
- What is missing from source_text?
- How complete is the coverage?

Score 0-5 stars:
- 5 stars (100%): All items from source_text present and correct
- 4 stars (80-99%): Most items present, minor omissions
- 3 stars (60-79%): Significant items present, some gaps
- 2 stars (40-59%): Less than half captured
- 1 star (20-39%): Very incomplete
- 0 stars (<20%): Almost nothing captured

WHAT TO CHECK IN EACH SECTION:

1. **issue_data**: dates (announced, placed_on_sale, etc.), legal basis, printing details
2. **production_orders**: all printing dates and their quantities
3. **stamps**: catalog numbers, denominations, colors, quantities
4. **varieties**: suffixes (a, b, c), types, descriptions
5. **proofs**: DP/PP/CP codes with colors and details
6. **essays**: E codes with descriptions
7. **specimens**: S codes or MUESTRA overprints
8. **postal_stationery**: envelopes, cards

OUTPUT FORMAT (JSON only, no markdown):
{{
  "rubric": [
    {{
      "section": "issue_data",
      "score_5": 0.0,
      "stars": "★★★✩✩",
      "percent": 0,
      "what_was_captured": ["list specific items captured"],
      "what_is_missing": ["list specific items from source_text that are absent"],
      "improvements": ["actionable steps for better coverage"]
    }},
    ... (for all 8 sections)
  ],
  "overall": {{
    "score_5": 0.0,
    "stars": "★★★★✩",
    "percent": 0
  }},
  "global_notes_to_add": ["notes that should be added"],
  "fix_priorities": ["most important fixes needed"]
}}

CRITICAL RULES:
- Base everything on source_text and generator_output
- Do NOT invent data not in source_text
- Be specific in what_is_missing (exact items)
- Output ONLY the JSON rubric (no markdown, no explanations)
"""


FIXER_SYSTEM_PROMPT = f"""
You are the MENA Catalog Fixer Agent.

YOUR INPUTS:
1. source_text: original catalog text
2. generator_output: initial JSON from Generator
3. critic_feedback: rubric with coverage scores and missing items

YOUR TASK: Produce the FINAL, CORRECT JSON with all 8 sections.

{SCHEMA_EXPLANATION}

IMPROVEMENT STRATEGY:

Step 1: Review Critic Feedback
- Look at critic_feedback.rubric for each section
- Note what_is_missing items
- Check fix_priorities

Step 2: Find Missing Items in Source Text
- Search source_text for each missing item
- Extract the exact information present

Step 3: Add to Correct Section
- issue_data: add missing dates, legal basis, printing info
- production_orders: add missing printings or remainders
- stamps: add missing catalog numbers
- varieties: add missing suffixes
- proofs: add missing DP/PP/CP codes
- essays: add missing E codes
- specimens: add missing S codes or MUESTRA overprints
- postal_stationery: add missing envelopes/cards

Step 4: Apply Schema Rules
- Denominations: {{"value": float, "unit": string}}
- Valid units: "c", "C", "P", "reales", "real", "sheet", "seal"
- S-codes → specimens section (NOT stamps)
- Lowercase suffixes → varieties section (NOT stamps)
- quantity_reported: ONLY if explicitly stated
- Unknown values: use "", null, [], {{}}

Step 5: Preserve Good Data
- Keep correctly extracted items from generator_output
- Add global_notes_to_add to appropriate notes fields
- Don't remove valid information

CRITICAL: DO NOT INVENT
- Codes not in source_text
- Quantities not explicitly stated
- Colors not mentioned
- Dates not present
- Any information not in source_text

OUTPUT: ONE complete JSON with EXACTLY 8 top-level keys:
issue_data, production_orders, stamps, varieties, proofs, essays, specimens, postal_stationery

NO markdown, NO explanations, ONLY the JSON object.
"""


COORDINATOR_SYSTEM_PROMPT = """
You are the MENA Pipeline Coordinator.

YOUR ROLE: Orchestrate the three specialists to parse catalog entries.

WORKFLOW:
1. Think: Use ThinkTool to plan your approach
2. Generate: Delegate to Generator with source_text
   - Generator will create initial JSON
3. Review: Delegate to Critic with source_text + generator_output
   - Critic will assess coverage and identify missing items
4. Fix: Delegate to Fixer with source_text + generator_output + critic_feedback
   - Fixer will produce final corrected JSON

DELEGATION RULES:
- Each specialist is an expert in their domain
- Pass complete context to each specialist
- Generator needs: source_text
- Critic needs: source_text AND generator_output
- Fixer needs: source_text AND generator_output AND critic_feedback

YOUR FINAL OUTPUT:
{{
  "generator_output": <JSON from Generator>,
  "critic_feedback": <rubric from Critic>,
  "final_output": <corrected JSON from Fixer>
}}

IMPORTANT: 
- Let each specialist do their work
- You coordinate, they execute
- Trust their expertise
"""

COORDINATOR_SYSTEM_PROMPT = """
You are the MENA Pipeline Coordinator.

YOUR ROLE: Orchestrate the three specialists to parse catalog entries.

WORKFLOW:
1. Think: Use ThinkTool to plan your approach
2. Generate: Delegate to Generator with source_text
   - Generator will create initial JSON
3. Review: Delegate to Critic with source_text + generator_output
   - Critic will assess coverage and identify missing items
4. Fix: Delegate to Fixer with source_text + generator_output + critic_feedback
   - Fixer will produce final corrected JSON

DELEGATION RULES:
- Each specialist is an expert in their domain
- Pass complete context to each specialist
- Generator needs: source_text
- Critic needs: source_text AND generator_output
- Fixer needs: source_text AND generator_output AND critic_feedback

YOUR FINAL OUTPUT:
{{
  "generator_output": <JSON from Generator>,
  "critic_feedback": <rubric from Critic>,
  "final_output": <corrected JSON from Fixer>
}}

IMPORTANT: 
- Let each specialist do their work
- You coordinate, they execute
- Trust their expertise
"""

# =============================================================================
# 5. FUNCIÓN HELPER PARA CREAR AGENTES CON ESTOS PROMPTS
# =============================================================================

from beeai_framework.memory import TokenMemory

def create_optimized_mena_agents():
    """
    Crea los tres agentes expertos con configuración optimizada.
    
    Returns:
        tuple: (generator_agent, critic_agent, fixer_agent)
    """
    generator_llm = _make_generator_llm()
    generator = RequirementAgent(
        llm=generator_llm,
        tools=[],
        role="MENA Catalog Generator",
        instructions=GENERATOR_SYSTEM_PROMPT,
        memory=TokenMemory(llm = generator_llm, max_tokens=8000),  # Mayor capacidad para schema complejo
    )
    
    critic_llm = _make_critic_llm()
    critic = RequirementAgent(
        llm=critic_llm,
        tools=[],
        role="MENA Catalog Coverage Critic",
        instructions=CRITIC_SYSTEM_PROMPT,
        memory=TokenMemory(llm = critic_llm, max_tokens=6000),
    )
    
    fixer_llm = _make_fixer_llm()
    fixer = RequirementAgent(
        llm=_make_fixer_llm(),
        tools=[],
        role="MENA Catalog Fixer",
        instructions=FIXER_SYSTEM_PROMPT,
        memory=TokenMemory(llm = fixer_llm, max_tokens=8000),
    )
    
    return generator, critic, fixer


def build_coordinator() -> RequirementAgent:
    """
    Coordinador que orquesta Generator → Critic → Fixer usando HandoffTool.
    
    MEJORAS vs. CÓDIGO ORIGINAL:
    1. ✅ HandoffTool con descripciones específicas
    2. ✅ Requirements simplificados con prioridades claras
    3. ✅ Middleware incluye HandoffTool además de Tool
    4. ✅ Coordinador confía en los especialistas
    5. ✅ role definido para el coordinador
    6. ✅ TokenMemory
    """
       
    # Crear agentes expertos
    gen_agent, critic_agent, fixer_agent = create_optimized_mena_agents()
    
    # ✅ HandoffTools con descripciones específicas de CUÁNDO usarlos
    to_generator = HandoffTool(
        gen_agent,
        name="Generator",
        description="""
        Use this to generate the initial JSON from source_text.
        Input: Pass the catalog source_text as context.
        Output: Returns generator_output (JSON object with 8 sections).
        """
    )
    
    to_critic = HandoffTool(
        critic_agent,
        name="Critic",
        description="""
        Use this to review the generator_output for coverage.
        Input: Pass both source_text and generator_output.
        Output: Returns critic_feedback (rubric JSON with scores and missing items).
        """
    )
    
    to_fixer = HandoffTool(
        fixer_agent,
        name="Fixer",
        description="""
        Use this to produce the final corrected JSON.
        Input: Pass source_text, generator_output, and critic_feedback.
        Output: Returns final_output (complete corrected JSON).
        """
    )
    
    # ✅ Prompt del coordinador simplificado - confía en los especialistas
    coord_sys = COORDINATOR_SYSTEM_PROMPT
    
    # ✅ Requirements simplificados pero efectivos con prioridades
    coordinator_llm = _make_coordinator_llm()
    coordinator = RequirementAgent(
        llm=coordinator_llm,
        tools=[to_generator, to_critic, to_fixer, ThinkTool()],
        role="MENA Pipeline Coordinator",  # ✅ Role claro
        instructions=coord_sys,
        memory=TokenMemory(llm = coordinator_llm, max_tokens=8000),  # ✅ Mayor capacidad para coordinar
        
        # ✅ Middleware configurado correctamente para rastrear handoffs
        middlewares=[
            GlobalTrajectoryMiddleware(
                included=[Tool, HandoffTool]  # ✅ Incluye HandoffTool
            )
        ],
        
        requirements=[
            # Paso 1: Pensar primero (siempre)
            ConditionalRequirement(
                ThinkTool,
                force_at_step=1,
                min_invocations=1,
                max_invocations=1,
                priority=10
            ),
            
            # Paso 2: Generator debe ejecutarse después de ThinkTool
            ConditionalRequirement(
                to_generator,
                force_after=[ThinkTool],
                min_invocations=1,
                max_invocations=1,  # Solo una vez
                priority=20
            ),
            
            # Paso 3: Critic debe ejecutarse después de Generator
            ConditionalRequirement(
                to_critic,
                force_after=[to_generator],
                min_invocations=1,
                max_invocations=1,  # Solo una vez
                priority=30
            ),
            
            # Paso 4: Fixer debe ejecutarse después de Critic
            ConditionalRequirement(
                to_fixer,
                force_after=[to_critic],
                min_invocations=1,
                max_invocations=1,  # Solo una vez
                priority=40
            ),
        ]
    )
    
    return coordinator


# =============================================================================
# 6. EJEMPLOS DE USO
# =============================================================================

if __name__ == "__main__":
    """
    Ejemplo de cómo usar estos prompts mejorados.
    """
    
    # Crear agentes
    generator, critic, fixer = create_optimized_mena_agents()
    coordinator = build_coordinator()
    
    # Probar individualmente
    import asyncio
    from beeai_framework.backend import UserMessage
    
    async def test():
        test_text = """
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
        
        # Test Generator
        # gen_response = await generator.run(
        #     prompt=f"Parse this catalog:\n{test_text}", expected_output= MenaCatalogEntry
        # )
        # print("Generator Output:")
        # assembled = json.loads(gen_response.answer.text)
        # print(assembled)
        
        # Test Coordinator
        payload = json.dumps({"source_text": test_text}, ensure_ascii=False)
        gen_response = await coordinator.run(
            prompt=payload
        )
        print("Generator Output:")
        assembled = json.loads(gen_response.answer.text)
        print(assembled)
        catalog_entry = assembled.get("generator_output")
        print(catalog_entry)
    
    asyncio.run(test())
