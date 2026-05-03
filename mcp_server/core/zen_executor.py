"""
mcp_server/core/zen_executor.py
---------------------------------
Executes GoRules decision tables via the zen-engine Python package.

This module is intentionally thin — it does exactly one thing:
  take a compiled GoRules JSON document + a flat input_context dict,
  run the decision table, and return every row that fired (violations).

It never calls Gemini. It never touches CSV files.
All data preparation happens upstream in context_builder.py.

Install: pip install zen-engine --break-system-packages
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def execute_decision(gorules_json: dict | str, input_context: dict[str, Any]) -> list[dict]:
    """
    Execute a GoRules COLLECT decision table and return all fired violation rows.

    Args:
        gorules_json:  Full GoRules document (dict or JSON string).
                       Must contain a decisionTableNode with hitPolicy: "collect".
        input_context: Flat dict of pre-resolved values.
                       Example: {"salary_increase_pct": 21.4, "salary": 8500}

    Returns:
        List of violation dicts, each with keys: rule_id, reason, violated.
        An empty list means all rules passed — operation is valid.

    Raises:
        RuntimeError: if zen-engine is not installed or the document is malformed.
    """
    try:
        import zen
    except ImportError:
        raise RuntimeError(
            "zen-engine is not installed.\n"
            "Run: pip install zen-engine --break-system-packages"
        )

    json_str = (
        json.dumps(gorules_json)
        if isinstance(gorules_json, dict)
        else gorules_json
    )

    try:
        engine = zen.ZenEngine()
        content = zen.ZenDecisionContent(json_str)
        decision = engine.create_decision(content)
        result = decision.evaluate(input_context)

        all_rows: list[dict] = result.get("result", [])

        # COLLECT hit policy returns every row whose conditions matched.
        # We only care about rows where violated == True.
        violations = [r for r in all_rows if r.get("violated") is True]

        logger.info(
            "Zen engine: %d row(s) matched, %d violation(s)",
            len(all_rows), len(violations),
        )
        return violations

    except Exception as exc:
        logger.error("Zen engine execution failed: %s", exc)
        raise RuntimeError(f"GoRules execution error: {exc}") from exc