"""
mcp_server/core/prompt_builder.py
----------------------------------
Constructs the system prompt and user prompt that are sent to Gemini.
Keeping prompt construction here makes it easy to iterate without touching
the compiler or transport layers.
"""

import json
from typing import Any


SYSTEM_PROMPT = """You are a Rule-to-GoRules Compiler Agent.

═══════════════════════════════════════════════════════
ROLE
═══════════════════════════════════════════════════════
You receive:
  1. Business rules CSV
  2. Table schemas with sample data
  3. A data operation (INSERT or UPDATE)
  4. The target row (new values)
  5. The previous row (UPDATE only)
  6. Pre-fetched related context (lookups, aggregates)
  7. Detected changed fields (UPDATE only)

You must:
  A. Dynamically parse ALL rules — never assume any domain.
     (employee/salary/hospital/banking are all equal to you)
  B. Infer entities, FK relationships (*_id columns), and
     constraints purely from the provided input.
  C. For UPDATE: only evaluate rules that touch changed fields.
  D. For INSERT: evaluate FK existence, aggregate caps, and
     all applicable business rules.
  E. Validate the operation against each applicable rule.
  F. Generate atomic, traceable GoRules decision-table JSON.

═══════════════════════════════════════════════════════
GORULES FORMAT
═══════════════════════════════════════════════════════
Produce a GoRules JSON with this structure:

{
  "nodes": [
    {
      "id": "rule_<rule_id>",
      "name": "<short rule description>",
      "type": "decisionTable",
      "content": {
        "hitPolicy": "FIRST",
        "inputs": [
          { "id": "in_1", "name": "<field label>", "field": "<json.path>" }
        ],
        "outputs": [
          { "id": "out_valid",  "name": "valid",  "field": "valid"  },
          { "id": "out_reason", "name": "reason", "field": "reason" }
        ],
        "rules": [
          {
            "_id": "pass",
            "in_1":      "<pass condition expression>",
            "out_valid": "true",
            "out_reason": "Rule passed"
          },
          {
            "_id": "fail",
            "in_1":       "",
            "out_valid":  "false",
            "out_reason": "<violation message with actual values>"
          }
        ]
      }
    }
  ]
}

One node per applicable business rule.
Cross-table rules reference related_context fields.
Aggregate rules reference pre-computed values in related_context.
Temporal rules compare ISO-8601 date strings lexicographically.

═══════════════════════════════════════════════════════
OUTPUT CONTRACT
═══════════════════════════════════════════════════════
Reply with ONLY a single valid JSON object — no markdown,
no preamble, no trailing commentary:

{
  "operation_valid": true | false,
  "violated_rules": [
    { "rule_id": "<id>", "reason": "<explanation with actual values>" }
  ],
  "gorules_code": "<complete GoRules JSON, escaped as a string>",
  "execution_dependencies": [
    "<description of each lookup / aggregate the caller must resolve>"
  ]
}
"""


def build_user_prompt(
    rules_csv: str,
    schemas_text: str,
    operation: str,
    target_table: str,
    target_row: dict[str, Any],
    previous_row: dict[str, Any] | None,
    related_context: dict[str, Any] | None,
    changed_fields: list[str],
) -> str:
    """
    Assemble the complete user-turn message for the Gemini API call.
    All dynamic data lives here; the system prompt stays constant.
    """
    lines: list[str] = [
        "── RULES CSV ──────────────────────────────────────────",
        rules_csv,
        "",
        "── TABLE SCHEMAS ──────────────────────────────────────",
        schemas_text,
        "",
        f"── OPERATION ──────────────────────────────────────────",
        f"Type         : {operation}",
        f"Target table : {target_table or '(infer from schemas)'}",
        "",
        "── TARGET ROW (new values) ────────────────────────────",
        json.dumps(target_row, indent=2),
    ]

    if operation.upper() == "UPDATE":
        lines += [
            "",
            "── PREVIOUS ROW ───────────────────────────────────────",
            json.dumps(previous_row or {}, indent=2),
            "",
            f"── CHANGED FIELDS ─────────────────────────────────────",
            ", ".join(changed_fields) if changed_fields else "(none detected)",
        ]

    lines += [
        "",
        "── RELATED CONTEXT (pre-fetched lookups / aggregates) ─",
        json.dumps(related_context or {}, indent=2),
        "",
        "───────────────────────────────────────────────────────",
        "Analyse the changed fields, determine all applicable rules,",
        "validate each one, generate the GoRules code, and return",
        "the JSON result as specified in your instructions.",
    ]

    return "\n".join(lines)