"""
mcp_server/core/zen_executor.py
---------------------------------
Executes GoRules decision tables via the zen-engine Python package.

The zen engine is the Zen / GoRules execution runtime.
Package: zen-engine (imports as `zen`)
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def execute_decision(gorules_json: dict | str, input_context: dict[str, Any]) -> list[dict]:
    """
    Execute a GoRules decision table and return all fired violation rows.

    Args:
        gorules_json:  Full GoRules document (dict or JSON string).
                       Must contain a `decisionTableNode` with COLLECT hit policy.
        input_context: Pre-computed flat input values (e.g. salary_increase_pct=21.4).

    Returns:
        List of violation dicts with keys: rule_id, reason, violated.
        Empty list means all rules passed.
    """
    try:
        import zen
    except ImportError:
        raise RuntimeError(
            "zen-engine not installed. Run: pip install zen-engine --break-system-packages"
        )

    json_str = json.dumps(gorules_json) if isinstance(gorules_json, dict) else gorules_json

    try:
        engine = zen.ZenEngine()
        content = zen.ZenDecisionContent(json_str)
        decision = engine.create_decision(content)
        result = decision.evaluate(input_context)
        rows = result.get("result", [])
        # COLLECT returns all matched rows; each row is a violation
        violations = [r for r in rows if r.get("violated") is True]
        logger.info(
            "Zen engine executed: %d violation(s) from %d matched rows",
            len(violations), len(rows),
        )
        return violations
    except Exception as exc:
        logger.error("Zen engine execution failed: %s", exc)
        raise RuntimeError(f"GoRules execution error: {exc}") from exc