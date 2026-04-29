"""
mcp_server/core/gemini_compiler.py
------------------------------------
Sends prompts to the Gemini API and parses the structured JSON response
into a ValidationResult.

This module is the only place in the project that touches google-genai.
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
from mcp_server.core.data_loader import (
    load_rules_text,
    load_all_tables_text,
    infer_changed_fields,
)

logger = logging.getLogger(__name__)

# Lazy singleton client
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. "
                "Add it to your .env file or export it as an environment variable."
            )
        _client = genai.Client(api_key=settings.gemini_api_key)
        logger.info("Gemini client initialised (model=%s)", settings.gemini_model)
    return _client


def _strip_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` markdown fences if present."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_response(raw: str) -> dict[str, Any]:
    """
    Try to extract a JSON object from the raw model response.
    Handles fenced code blocks and stray leading/trailing text.
    """
    clean = _strip_fences(raw)
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        # Last resort: find the first { ... } block
        match = re.search(r"\{[\s\S]*\}", clean)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"Gemini returned non-JSON response:\n{raw[:500]}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compile_and_validate(
    operation: str,
    target_table: str,
    target_row: dict[str, Any],
    previous_row: dict[str, Any] | None = None,
    related_context: dict[str, Any] | None = None,
) -> ValidationResult:
    """
    Full pipeline:
      1. Load rules CSV + table schemas from disk
      2. Detect changed fields
      3. Build prompt
      4. Call Gemini
      5. Parse + return ValidationResult

    Raises RuntimeError on config issues, ValueError on bad Gemini output.
    """
    rules_csv    = load_rules_text()
    schemas_text = load_all_tables_text()

    if not rules_csv:
        raise RuntimeError("No rules.csv found. Upload one via the upload_rules tool.")
    if not schemas_text:
        raise RuntimeError("No table CSVs found. Upload schemas via the upload_table tool.")

    changed_fields = infer_changed_fields(target_row, previous_row)
    logger.info(
        "Compiling: op=%s table=%s changed=%s",
        operation, target_table, changed_fields,
    )

    user_prompt = build_user_prompt(
        rules_csv=rules_csv,
        schemas_text=schemas_text,
        operation=operation.upper(),
        target_table=target_table,
        target_row=target_row,
        previous_row=previous_row,
        related_context=related_context,
        changed_fields=changed_fields,
    )

    client = _get_client()

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=settings.gemini_max_tokens,
            temperature=settings.gemini_temperature,
        ),
    )

    raw_text = response.text or ""
    logger.debug("Gemini raw response (%d chars): %s...", len(raw_text), raw_text[:200])

    data = _parse_response(raw_text)

    violated = [
        ViolatedRule(rule_id=str(v["rule_id"]), reason=v["reason"])
        for v in data.get("violated_rules", [])
    ]

    return ValidationResult(
        operation_valid=bool(data.get("operation_valid", False)),
        violated_rules=violated,
        gorules_code=data.get("gorules_code", ""),
        execution_dependencies=data.get("execution_dependencies", []),
        changed_fields=changed_fields,
        rules_evaluated=len(data.get("violated_rules", [])) + (
            # approximate: total applicable = violated + rest
            0
        ),
    )