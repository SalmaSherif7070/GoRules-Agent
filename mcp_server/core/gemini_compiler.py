"""
mcp_server/core/gemini_compiler.py
------------------------------------
Orchestrates:
  1. Gemini → generates GoRules decision table JSON + input_context
  2. Zen Engine → executes the decision table
  3. Returns ValidationResult from engine output

Gemini is the COMPILER. Zen Engine is the EXECUTOR.
"""

import json
import logging
import re
from typing import Any

from google import genai
from google.genai import types

from config import settings
from mcp_server.models import ValidationResult, ViolatedRule
from mcp_server.core.prompt_builder import SYSTEM_PROMPT, build_user_prompt
from mcp_server.core.data_loader import load_all_tables_text, infer_changed_fields
from mcp_server.core.zen_executor import execute_decision

logger = logging.getLogger(__name__)
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


def _parse_response(raw: str) -> dict[str, Any]:
    clean = _strip_fences(raw)
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", clean)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"Gemini returned non-JSON:\n{raw[:500]}")


def compile_and_validate(
    operation: str,
    target_table: str,
    target_row: dict[str, Any],
    rules: list[str],
    previous_row: dict[str, Any] | None = None,
    related_context: dict[str, Any] | None = None,
) -> ValidationResult:
    """
    Compile business rules into GoRules via Gemini, then execute with Zen Engine.

    Flow:
      Gemini  → gorules_json + input_context
      Zen     → list of violations (from COLLECT decision table)
      Return  → ValidationResult
    """
    schemas_text = load_all_tables_text()
    if not schemas_text:
        raise RuntimeError("No table CSVs found in data/. Ensure tables are loaded.")

    changed_fields = infer_changed_fields(target_row, previous_row)
    logger.info(
        "Compiling: op=%s table=%s changed=%s rules=%d",
        operation, target_table, changed_fields, len(rules),
    )

    # ── Step 1: Ask Gemini to compile rules → GoRules JSON ──────────────────
    user_prompt = build_user_prompt(
        schemas_text=schemas_text,
        operation=operation.upper(),
        target_table=target_table,
        target_row=target_row,
        previous_row=previous_row,
        related_context=related_context,
        changed_fields=changed_fields,
        rules=rules,
    )

    response = _get_client().models.generate_content(
        model=settings.gemini_model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=settings.gemini_max_tokens,
            temperature=settings.gemini_temperature,
        ),
    )

    compiled = _parse_response(response.text or "")
    gorules_json: dict = compiled.get("gorules_json", {})
    input_context: dict = compiled.get("input_context", {})

    if not gorules_json:
        raise RuntimeError("Gemini did not return a gorules_json in its response")

    logger.info(
        "Gemini compiled GoRules: %d nodes, input_context keys=%s",
        len(gorules_json.get("nodes", [])),
        list(input_context.keys()),
    )

    # ── Step 2: Execute via Zen Engine ───────────────────────────────────────
    violations_raw = execute_decision(gorules_json, input_context)

    # ── Step 3: Build ValidationResult ──────────────────────────────────────
    violated_rules = [
        ViolatedRule(
            rule_id=str(v.get("rule_id", "?")),
            reason=str(v.get("reason", "Rule violated")),
        )
        for v in violations_raw
    ]

    gorules_code = json.dumps(gorules_json, indent=2)

    return ValidationResult(
        operation_valid=len(violated_rules) == 0,
        violated_rules=violated_rules,
        gorules_code=gorules_code,
        execution_dependencies=[],        # zen engine handles all lookups via input_context
        changed_fields=changed_fields,
        rules_evaluated=len(rules),
    )