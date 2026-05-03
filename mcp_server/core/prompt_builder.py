"""
mcp_server/core/prompt_builder.py
----------------------------------
Builds the Gemini prompt for GoRules COMPILATION only.
Gemini's job: generate a GoRules decision table + pre-compute input values.
Validation is done by the zen engine, not Gemini.
"""

import json
from typing import Any


SYSTEM_PROMPT = """You are a GoRules Decision Table Compiler.

YOUR ONLY JOB
-------------
Given a data operation and business rules, produce:
1. A GoRules decision document (JSON) that encodes all applicable violation checks
2. A flat input_context dict with all pre-computed values the table needs

You do NOT validate. The zen engine executes your output and determines the result.

GORULES DOCUMENT FORMAT
-----------------------
{
  "contentType": "application/vnd.gorules.decision",
  "nodes": [
    {"id": "input", "type": "inputNode", "name": "Input", "position": {"x": 0, "y": 0}},
    {
      "id": "rules_table",
      "type": "decisionTableNode",
      "name": "BusinessRules",
      "position": {"x": 300, "y": 0},
      "content": {
        "hitPolicy": "collect",
        "inputs": [
          {"id": "i1", "name": "<field_label>", "field": "<snake_case_key>"}
        ],
        "outputs": [
          {"id": "o_violated", "name": "violated",  "field": "violated"},
          {"id": "o_rule_id",  "name": "rule_id",   "field": "rule_id"},
          {"id": "o_reason",   "name": "reason",    "field": "reason"}
        ],
        "rules": [
          {
            "_id": "rule_<N>",
            "i1": "<condition e.g. '> 20'>",
            "o_violated": "true",
            "o_rule_id": "\"<N>\"",
            "o_reason": "\"<explanation with actual values>\""
          }
        ]
      }
    },
    {"id": "output", "type": "outputNode", "name": "Output", "position": {"x": 600, "y": 0}}
  ],
  "edges": [
    {"id": "e1", "sourceId": "input", "targetId": "rules_table"},
    {"id": "e2", "sourceId": "rules_table", "targetId": "output"}
  ]
}

CRITICAL RULES
--------------
1. Node type is `decisionTableNode` — NOT `decisionTable`
2. hitPolicy is lowercase `collect`
3. Each row in `rules` represents ONE violation condition (fires ONLY when rule is violated)
4. Leave cells empty string `""` for input columns not used by a rule row
5. All output values must be quoted as JSON strings inside the rule cell:
   - boolean:  "true" or "false"
   - string:   "\"text value\""
   - Include ACTUAL numbers in reason strings (e.g. "Salary increase 21.4% exceeds 20%")
6. Only include applicable rules for the operation type and changed fields

INPUT_CONTEXT RULES
-------------------
- Pre-compute ALL derived values the decision table needs
- For UPDATE salary: compute salary_increase_pct = (new - old) / old * 100
- For bonus: compute bonus_pct = bonus_amount / employee_salary * 100
- For leave: include days_requested and leave_balance separately
- Use snake_case keys matching the `field` values in your inputs array
- Include raw field values too (salary, performance_rating, etc.)

OUTPUT FORMAT
-------------
Reply with ONLY a single valid JSON object — no markdown, no preamble:

{
  "gorules_json": { ...complete GoRules document... },
  "input_context": {
    "salary_increase_pct": 21.4,
    "salary": 8500,
    "previous_salary": 7000,
    ...all other values needed by the table...
  }
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
    numbered_rules = "\n".join(f"{r}" for r in rules)

    lines: list[str] = [
        "── TABLE SCHEMAS ──────────────────────────────────────────",
        schemas_text,
        "",
        "── BUSINESS RULES TO ENCODE ────────────────────────────────",
        numbered_rules,
        "",
        f"── OPERATION ───────────────────────────────────────────────",
        f"Type         : {operation}",
        f"Target table : {target_table}",
        "",
        "── TARGET ROW (new values) ─────────────────────────────────",
        json.dumps(target_row, indent=2),
    ]

    if operation.upper() == "UPDATE" and previous_row:
        lines += [
            "",
            "── PREVIOUS ROW (before UPDATE) ────────────────────────────",
            json.dumps(previous_row, indent=2),
            "",
            "── CHANGED FIELDS ──────────────────────────────────────────",
            ", ".join(changed_fields) if changed_fields else "(none)",
        ]

    lines += [
        "",
        "── RELATED CONTEXT (pre-fetched lookups) ────────────────────",
        json.dumps(related_context or {}, indent=2),
        "",
        "── YOUR TASK ────────────────────────────────────────────────",
        "1. Determine which rules apply to this operation and changed fields",
        "2. Compute input_context values (salary_increase_pct, bonus_pct, etc.)",
        "3. Build a GoRules decisionTableNode where each ROW = one violation condition",
        "4. Return { gorules_json: ..., input_context: ... }",
        "",
        "IMPORTANT: Include actual computed values in reason strings.",
        f"For UPDATE: salary_increase_pct = ({target_row.get('salary', 'N/A')} - {previous_row.get('salary', 'N/A') if previous_row else 'N/A'}) / {previous_row.get('salary', 'N/A') if previous_row else 'N/A'} * 100",
    ]

    return "\n".join(lines)