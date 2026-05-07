"""
api/gorules_generator.py
-------------------------
POST /api/generate-gorules

For every rule in data/rules/rules.csv, calls Gemini to compile one or more
GoRules decision-table scripts.  Saves each script as:

    GoRules_rules/rule_{rule_id}/Script_{j}.json

Returns a summary of what was generated.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from google import genai
from google.genai import types

from config import settings
from mcp_server.core.data_loader import load_all_schemas, format_schemas_for_prompt, load_rules_list
from mcp_server.models import RuleRow

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["GoRules Generator"])

OUTPUT_ROOT = Path("GoRules_rules")


# ─────────────────────────────────────────────────────────────
# Response model
# ─────────────────────────────────────────────────────────────

class GeneratedScript(BaseModel):
    rule_id: str
    script_index: int
    path: str


class GenerateGoRulesResponse(BaseModel):
    rules_processed: int
    scripts_generated: int
    output_root: str
    scripts: list[GeneratedScript]
    errors: list[str]


# ─────────────────────────────────────────────────────────────
# Gemini prompt
# ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a GoRules Decision Table Compiler.

For a single business rule, generate one or more GoRules JSON decision-table
documents.  You may split the rule into multiple scripts if it involves
multiple independent checks (e.g. a range check is two rows, but can also be
two separate scripts for clarity).

OUTPUT FORMAT — return a JSON array of GoRules documents:

[
  {
    "contentType": "application/vnd.gorules.decision",
    "nodes": [
      {"id": "input",       "type": "inputNode",         "name": "Input",        "position": {"x": 0,   "y": 0}},
      {
        "id": "rules_table","type": "decisionTableNode",  "name": "RuleCheck",   "position": {"x": 300, "y": 0},
        "content": {
          "hitPolicy": "collect",
          "inputs":  [{"id": "i1", "name": "<field label>", "field": "<input_key>"}],
          "outputs": [
            {"id": "o1", "name": "violated", "field": "violated"},
            {"id": "o2", "name": "rule_id",  "field": "rule_id"},
            {"id": "o3", "name": "reason",   "field": "reason"}
          ],
          "rules": [
            {
              "_id": "r1",
              "i1": "<condition>",
              "o1": "true",
              "o2": "\"<rule_id>\"",
              "o3": "\"<human-readable violation message>\""
            }
          ]
        }
      },
      {"id": "output", "type": "outputNode", "name": "Output", "position": {"x": 600, "y": 0}}
    ],
    "edges": [
      {"id": "e1", "sourceId": "input",       "targetId": "rules_table"},
      {"id": "e2", "sourceId": "rules_table", "targetId": "output"}
    ]
  }
]

STRICT RULES:
1. hitPolicy must be "collect" (lowercase)
2. Each rule row fires when the rule is BROKEN (violation condition)
3. Input cell values are comparisons: "> 20", "< 0", "!= true"
4. Output boolean → "true", string → "\"quoted\""
5. Reply with ONLY the JSON array. No markdown, no explanation.
"""


def _build_user_prompt(rule: RuleRow, schemas_text: str) -> str:
    return f"""TABLE SCHEMAS:
{schemas_text}

RULE TO ENCODE:
  rule_id   : {rule.rule_id}
  category  : {rule.category}
  description: {rule.rule_description}
  field_1   : {rule.field_1}
  operator  : {rule.operator}
  threshold : {rule.field_2_or_value}

Generate GoRules JSON for this rule only.
Return a JSON array (one or more documents)."""


# ─────────────────────────────────────────────────────────────
# Gemini helpers
# ─────────────────────────────────────────────────────────────

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set in .env")
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _call_gemini(user_prompt: str) -> list[dict[str, Any]]:
    """Call Gemini and return a list of GoRules JSON documents."""
    response = _get_client().models.generate_content(
        model=settings.gemini_model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            max_output_tokens=settings.gemini_max_tokens,
            temperature=settings.gemini_temperature,
        ),
    )
    raw = _strip_fences(response.text or "")

    # Gemini should return a JSON array; fall back to wrapping a single object
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", raw)
        if match:
            parsed = json.loads(match.group(0))
        else:
            obj_match = re.search(r"\{[\s\S]*\}", raw)
            if obj_match:
                parsed = [json.loads(obj_match.group(0))]
            else:
                raise ValueError(f"Gemini returned non-JSON: {raw[:300]}")

    if isinstance(parsed, dict):
        parsed = [parsed]  # single document — wrap it

    return parsed


# ─────────────────────────────────────────────────────────────
# Endpoint
# ─────────────────────────────────────────────────────────────

@router.post(
    "/generate-gorules",
    response_model=GenerateGoRulesResponse,
    summary="Generate GoRules scripts for every rule in rules.csv",
    description=(
        "Reads all rules from data/rules/rules.csv and all table schemas, "
        "then calls Gemini once per rule to compile one or more GoRules "
        "decision-table JSON files.  Each file is saved to:\n\n"
        "  GoRules_rules/rule_{rule_id}/Script_{j}.json\n\n"
        "Returns a summary of every file written."
    ),
)
async def generate_gorules():
    # ── Load schemas ──────────────────────────────────────────
    all_schemas = load_all_schemas()
    if not all_schemas:
        raise HTTPException(status_code=500, detail="No table schemas found in data/tables/")
    schemas_text = format_schemas_for_prompt(all_schemas)

    # ── Load rules ────────────────────────────────────────────
    rules = load_rules_list()
    if not rules:
        raise HTTPException(status_code=500, detail="No rules found in data/rules/rules.csv")

    generated: list[GeneratedScript] = []
    errors: list[str] = []

    for rule in rules:
        rule_dir = OUTPUT_ROOT / f"rule_{rule.rule_id}"
        rule_dir.mkdir(parents=True, exist_ok=True)

        try:
            user_prompt = _build_user_prompt(rule, schemas_text)
            scripts = _call_gemini(user_prompt)

            for j, script in enumerate(scripts, start=1):
                out_path = rule_dir / f"Script_{j}.json"
                out_path.write_text(json.dumps(script, indent=2), encoding="utf-8")
                logger.info("Saved %s", out_path)
                generated.append(GeneratedScript(
                    rule_id=rule.rule_id,
                    script_index=j,
                    path=str(out_path),
                ))

        except Exception as exc:
            msg = f"rule_{rule.rule_id}: {exc}"
            logger.error(msg)
            errors.append(msg)

    return GenerateGoRulesResponse(
        rules_processed=len(rules),
        scripts_generated=len(generated),
        output_root=str(OUTPUT_ROOT),
        scripts=generated,
        errors=errors,
    )