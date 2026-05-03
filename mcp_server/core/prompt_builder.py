import json
from typing import Any


SYSTEM_PROMPT = """You are a Rule-to-GoRules Compiler Agent.

ROLE
----
You receive:
  1. Table schemas (CSV format) — discover all field names and types from these
  2. A data operation: INSERT or UPDATE
  3. The target row (new values)
  4. The previous row (UPDATE only)
  5. Pre-fetched related context (lookups, aggregates)
  6. Natural language business rules to enforce

You must:
  - Discover field names entirely from the provided schemas — never assume them
  - For UPDATE: only evaluate rules touching changed fields
  - For INSERT: evaluate all applicable rules
  - Validate the operation against each rule
  - Generate GoRules decision-table JSON

GORULES FORMAT
--------------
{
  "nodes": [
    {
      "id": "rule_<n>",
      "name": "<rule summary>",
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
          { "_id": "pass", "in_1": "<pass condition>", "out_valid": "true",  "out_reason": "Rule passed" },
          { "_id": "fail", "in_1": "",                 "out_valid": "false", "out_reason": "<violation with actual values>" }
        ]
      }
    }
  ]
}

One node per applicable rule.

OUTPUT CONTRACT
---------------
Reply with ONLY a single valid JSON object — no markdown, no preamble:

{
  "operation_valid": true | false,
  "violated_rules": [
    { "rule_id": "<n>", "reason": "<explanation with actual values>" }
  ],
  "gorules_code": "<complete GoRules JSON escaped as string>",
  "execution_dependencies": ["<any lookups the caller must resolve>"]
}
"""


def build_user_prompt(
    schemas_text: str,
    operation: str,
    target_table: str,
    target_row: dict[str, Any],
    previous_row: dict[str, Any] | None,
    related_context: dict[str, Any] | None,
    changed_fields: list[str],
    rules: list[str],
) -> str:
    numbered_rules = "\n".join(f"{i+1}. {r}" for i, r in enumerate(rules))

    lines: list[str] = [
        "── TABLE SCHEMAS (discover all field names from here) ─────",
        schemas_text,
        "",
        "── BUSINESS RULES (natural language) ──────────────────────",
        numbered_rules,
        "",
        f"── OPERATION ───────────────────────────────────────────────",
        f"Type         : {operation}",
        f"Target table : {target_table}",
        "",
        "── TARGET ROW ──────────────────────────────────────────────",
        json.dumps(target_row, indent=2),
    ]

    if operation.upper() == "UPDATE":
        lines += [
            "",
            "── PREVIOUS ROW ────────────────────────────────────────────",
            json.dumps(previous_row or {}, indent=2),
            "",
            "── CHANGED FIELDS ──────────────────────────────────────────",
            ", ".join(changed_fields) if changed_fields else "(none)",
        ]

    lines += [
        "",
        "── RELATED CONTEXT ─────────────────────────────────────────",
        json.dumps(related_context or {}, indent=2),
        "",
        "Discover field names from the schemas above, evaluate each rule, "
        "and return the JSON result as specified.",
    ]

    return "\n".join(lines)