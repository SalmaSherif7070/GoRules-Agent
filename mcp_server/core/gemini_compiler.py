"""
mcp_server/core/gemini_compiler.py
------------------------------------
Two-phase pipeline:

  Phase 1 — COMPILE  (Gemini)
    Input : table schemas only + operation + rules
    Output: needed_tables, gorules_json, input_mappings

  Phase 2 — EXECUTE  (Zen Engine)
    Input : gorules_json + input_context built from real row data
    Output: list of violated rules → ValidationResult

Gemini never sees actual row data.
Zen never sees anything except the compiled decision table + concrete values.
"""

import json
import logging
import re
from typing import Any

from google import genai
from google.genai import types

from config import settings
from mcp_server.models import ValidationResult, ViolatedRule
from mcp_server.core.prompt_builder import SYSTEM_PROMPT, build_compile_prompt
from mcp_server.core.data_loader import (
    load_all_schemas,
    format_schemas_for_prompt,
    load_tables_for_context,
    infer_changed_fields,
)
from mcp_server.core.zen_executor import execute_decision
from mcp_server.core.context_builder import build_input_context

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


def _parse_gemini_response(raw: str) -> dict[str, Any]:
    clean = _strip_fences(raw)
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        # fallback: grab the outermost JSON object
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
    Full pipeline: compile rules with Gemini → execute with Zen → return result.

    Args:
        operation       : "INSERT" or "UPDATE"
        target_table    : the table being written to
        target_row      : new row values
        rules           : plain-English business rules
        previous_row    : old row values (UPDATE only)
        related_context : optional pre-fetched data the caller already has.
                          Merged with Zen input_context so callers can short-
                          circuit lookups they've already done.
    """

    # ── 0. Validate inputs ────────────────────────────────────────────────
    if not rules:
        raise RuntimeError("No business rules provided.")

    changed_fields = infer_changed_fields(target_row, previous_row)
    logger.info(
        "Pipeline start: op=%s table=%s changed=%s rules=%d",
        operation, target_table, changed_fields, len(rules),
    )

    # ── 1. Load ALL schemas (tiny — just column names + types) ───────────
    all_schemas = load_all_schemas()
    if not all_schemas:
        raise RuntimeError(
            "No table schemas found in data/. "
            "Ensure at least one *.csv exists in the tables directory."
        )
    schemas_text = format_schemas_for_prompt(all_schemas)

    # ── 2. Build prompt and call Gemini (schema-only, no row data) ────────
    user_prompt = build_compile_prompt(
        schemas_text=schemas_text,
        operation=operation.upper(),
        target_table=target_table,
        target_row=target_row,
        previous_row=previous_row,
        changed_fields=changed_fields,
        rules=rules,
    )

    logger.debug("Sending compile prompt to Gemini (%d chars)", len(user_prompt))

    response = _get_client().models.generate_content(
        model=settings.gemini_model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=settings.gemini_max_tokens,
            temperature=settings.gemini_temperature,
        ),
    )

    compiled = _parse_gemini_response(response.text or "")

    # ── 3. Extract Gemini's three outputs ─────────────────────────────────
    gorules_json: dict = compiled.get("gorules_json", {})
    input_mappings: dict = compiled.get("input_mappings", {})
    needed_tables: list[str] = compiled.get("needed_tables", [])

    if not gorules_json:
        raise RuntimeError(
            "Gemini did not return a gorules_json. "
            f"Raw response snippet: {response.text[:300]}"
        )

    logger.info(
        "Gemini compiled: %d nodes, needed_tables=%s, mappings=%d",
        len(gorules_json.get("nodes", [])),
        needed_tables,
        len(input_mappings),
    )

    # ── 4. Fetch actual row data for needed tables only ───────────────────
    # This is the scalability win: only load the tables Gemini said it needs.
    table_data = load_tables_for_context(needed_tables)

    # Merge in caller-supplied related_context (optional short-circuit).
    # Caller data takes priority over freshly loaded rows.
    if related_context:
        logger.debug("Merging caller-supplied related_context")

    # ── 5. Build flat input_context for Zen from input_mappings ──────────
    input_context = build_input_context(
        input_mappings=input_mappings,
        target_row=target_row,
        previous_row=previous_row,
        table_data=table_data,
        related_context=related_context or {},
    )

    logger.info("input_context built: keys=%s", list(input_context.keys()))

    # ── 6. Execute with Zen Engine ────────────────────────────────────────
    violations_raw = execute_decision(gorules_json, input_context)

    # ── 7. Build and return ValidationResult ─────────────────────────────
    violated_rules = [
        ViolatedRule(
            rule_id=str(v.get("rule_id", "?")),
            reason=str(v.get("reason", "Rule violated")),
        )
        for v in violations_raw
    ]

    return ValidationResult(
        operation_valid=len(violated_rules) == 0,
        violated_rules=violated_rules,
        gorules_code=json.dumps(gorules_json, indent=2),
        execution_dependencies=needed_tables,
        changed_fields=changed_fields,
        rules_evaluated=len(rules),
    )