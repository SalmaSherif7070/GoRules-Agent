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
    schemas_text = load_all_tables_text()
    if not schemas_text:
        raise RuntimeError("No table CSVs found in data/. Ensure tables are loaded.")

    changed_fields = infer_changed_fields(target_row, previous_row)
    logger.info("op=%s table=%s changed=%s rules=%d",
                operation, target_table, changed_fields, len(rules))

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

    data = _parse_response(response.text or "")

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
        rules_evaluated=len(rules),
    )