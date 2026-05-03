"""
mcp_server/tools/validate_tool.py
-----------------------------------
MCP tool: validate_operation
Compiles business rules and validates a data operation (INSERT / UPDATE).
"""

import json
import logging
from typing import Any

from mcp_server.core.gemini_compiler import compile_and_validate
from mcp_server.core.data_loader import load_rules_list

logger = logging.getLogger(__name__)


async def validate_operation(
    operation: str,
    target_table: str,
    target_row: str,
    previous_row: str | None = None,
    related_context: str | None = None,
) -> str:
    """
    Compile GoRules from loaded schemas + rules and validate a data operation.

    Args:
        operation:       "INSERT" or "UPDATE"
        target_table:    Name of the table being modified (e.g. "employees")
        target_row:      JSON string — new / inserted row values
        previous_row:    JSON string — existing row before UPDATE (UPDATE only)
        related_context: JSON string — pre-fetched lookups / aggregate counts

    Returns:
        JSON string matching the ValidationResult schema.
    """
    # MCP tools receive everything as strings; parse JSON args here
    try:
        target_dict: dict[str, Any] = json.loads(target_row)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"target_row is not valid JSON: {exc}"})

    prev_dict: dict[str, Any] | None = None
    if previous_row:
        try:
            prev_dict = json.loads(previous_row)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"previous_row is not valid JSON: {exc}"})

    ctx_dict: dict[str, Any] | None = None
    if related_context:
        try:
            ctx_dict = json.loads(related_context)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"related_context is not valid JSON: {exc}"})

    if operation.upper() not in ("INSERT", "UPDATE"):
        return json.dumps({"error": "operation must be INSERT or UPDATE"})

    try:
        # Load rules from rules.csv automatically
        rules_list = load_rules_list()
        # Extract rule descriptions in format: "<rule_id>. <category>: <description>"
        rules = [
            f"{r.rule_id}. {r.category}: {r.rule_description}"
            for r in rules_list
        ]
        
        if not rules:
            return json.dumps({"error": "No business rules found in data/rules.csv"})
        
        result = compile_and_validate(
            operation=operation,
            target_table=target_table,
            target_row=target_dict,
            previous_row=prev_dict,
            related_context=ctx_dict,
            rules=rules,
        )
        return result.model_dump_json(indent=2)
    except Exception as exc:
        logger.exception("validate_operation failed")
        return json.dumps({"error": str(exc)})