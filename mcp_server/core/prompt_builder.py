"""
mcp_server/core/prompt_builder.py
----------------------------------
Builds TWO prompts for the two Gemini calls:

Phase 1 — PLANNING prompt
  Gemini decides which tables are needed and compiles the GoRules JSON.
  Input:  table SCHEMAS only  (column names + types, no row values)
  Output: { needed_tables: [...], gorules_json: {...}, input_mappings: {...} }

Phase 2 does NOT use Gemini.
  The caller fetches actual rows for needed_tables, builds input_context,
  and passes it straight to Zen. Gemini is done after Phase 1.

Key design rules baked into the system prompt:
  - Gemini is a COMPILER not a VALIDATOR — it must never output operation_valid
  - Gemini sees schemas, not data — all values come from input_context at runtime
  - Every condition cell must reference an input field key, not a hardcoded value
  - input_mappings tells the caller exactly how to wire row data → input_context keys
"""

import json
from typing import Any


# ─────────────────────────────────────────────────────────────
# System prompt — sent once as the Gemini system instruction
# ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a GoRules Decision Table Compiler.

YOUR ROLE
---------
You are a COMPILER. You translate business rules into an executable GoRules
decision table. You do NOT validate data. You do NOT output operation_valid.
The Zen engine runs your output and determines the result.

WHAT YOU RECEIVE
----------------
- Table schemas: column names and types ONLY (no row data)
- The operation: INSERT or UPDATE
- The target row: the new/updated values being validated
- The previous row: the before-state (UPDATE only)
- The changed fields: which fields are different
- The business rules: plain English statements to encode

WHAT YOU MUST OUTPUT
--------------------
A single JSON object with three keys:

{
  "needed_tables": ["employees", "departments"],
  "gorules_json":  { ...complete GoRules decision document... },
  "input_mappings": {
    "salary":              { "source": "target_row",  "field": "salary" },
    "previous_salary":     { "source": "previous_row", "field": "salary" },
    "manager_salary":      { "source": "lookup",      "table": "employees", "match_field": "employee_id", "match_from": "target_row.manager_id", "value_field": "salary" },
    "salary_increase_pct": { "source": "computed",    "formula": "(salary - previous_salary) / previous_salary * 100" }
  }
}

needed_tables
  List ONLY the tables required to validate this operation.
  Do NOT list tables that are not referenced by any rule.
  The target table is always implicitly available — only list EXTRA tables.

input_mappings
  A precise map of every input field key used in the decision table to
  its data source. Four source types:
    "target_row"   — field comes directly from the new row being validated
    "previous_row" — field comes from the row before UPDATE
    "lookup"       — field must be fetched from another table at runtime:
                     match_field: the column to filter on
                     match_from:  dot-path into target_row or previous_row
                     value_field: the column to extract as the value
    "computed"     — derived at runtime from other mapped values
                     formula uses the keys of other input_mappings entries

gorules_json FORMAT
-------------------
{
  "contentType": "application/vnd.gorules.decision",
  "nodes": [
    {
      "id": "input",
      "type": "inputNode",
      "name": "Input",
      "position": {"x": 0, "y": 0}
    },
    {
      "id": "rules_table",
      "type": "decisionTableNode",
      "name": "BusinessRules",
      "position": {"x": 300, "y": 0},
      "content": {
        "hitPolicy": "collect",
        "inputs": [
          {"id": "i1", "name": "Salary increase %", "field": "salary_increase_pct"},
          {"id": "i2", "name": "New salary",         "field": "salary"}
        ],
        "outputs": [
          {"id": "o1", "name": "violated", "field": "violated"},
          {"id": "o2", "name": "rule_id",  "field": "rule_id"},
          {"id": "o3", "name": "reason",   "field": "reason"}
        ],
        "rules": [
          {
            "_id": "rule_1",
            "i1": "> 20",
            "i2": "",
            "o1": "true",
            "o2": "\"1\"",
            "o3": "\"Salary increase exceeds 20% cap\""
          }
        ]
      }
    },
    {
      "id": "output",
      "type": "outputNode",
      "name": "Output",
      "position": {"x": 600, "y": 0}
    }
  ],
  "edges": [
      {"id": "e1", "type": "edge", "sourceId": "input",       "targetId": "rules_table"},
      {"id": "e2", "type": "edge", "sourceId": "rules_table", "targetId": "output"}
  ]
}

STRICT RULES FOR gorules_json
------------------------------
1. Node type is exactly `decisionTableNode` (not `decisionTable`)
2. hitPolicy is exactly `collect` (lowercase)
3. Every ROW in `rules` represents ONE violation — it fires ONLY when a rule is BROKEN
4. Input cell values are comparisons: "> 20", "< 0", "== true", "!= 1"
5. Leave unused input cells as empty string ""
6. Output values are JSON strings inside the cell:
   - boolean → "true" or "false"
   - string  → "\"text in quotes\""
7. reason strings must describe the violation clearly
8. Only encode rules that apply to the current operation type and changed fields
9. NEVER put operation_valid, NEVER put a final judgment — only violation rows

RULES FOR input_mappings
-------------------------
- Every `field` value in the `inputs` array MUST have a corresponding
  entry in input_mappings with the same key
- For "computed" sources, the formula must only reference other keys
  that are also in input_mappings (no undefined symbols)
- For "lookup" sources, specify enough info for the caller to do:
    table[row where row[match_field] == resolve(match_from)][value_field]

OUTPUT FORMAT
-------------
Reply with ONLY a valid JSON object. No markdown. No preamble. No explanation.
"""


# ─────────────────────────────────────────────────────────────
# User prompt — built per request
# ─────────────────────────────────────────────────────────────

def build_compile_prompt(
    schemas_text: str,
    operation: str,
    target_table: str,
    target_row: dict[str, Any],
    previous_row: dict[str, Any] | None,
    changed_fields: list[str],
    rules: list[str],
) -> str:
    """
    Build the user-facing prompt for Gemini Phase 1.

    Note: related_context is intentionally NOT passed here.
    The caller will provide lookup data to Zen, not to Gemini.
    Gemini only needs to know what lookups are required (via input_mappings).
    """
    numbered_rules = "\n".join(
        f"  Rule {i + 1}: {rule}" for i, rule in enumerate(rules)
    )

    sections: list[str] = [
        "═══ TABLE SCHEMAS (column names and types only — no row data) ═══",
        schemas_text,
        "",
        "═══ BUSINESS RULES TO ENCODE ═══",
        numbered_rules,
        "",
        "═══ OPERATION ═══",
        f"  Type         : {operation.upper()}",
        f"  Target table : {target_table}",
        "",
        "═══ TARGET ROW (new / inserted values) ═══",
        json.dumps(target_row, indent=2),
    ]

    if operation.upper() == "UPDATE" and previous_row:
        sections += [
            "",
            "═══ PREVIOUS ROW (values before UPDATE) ═══",
            json.dumps(previous_row, indent=2),
            "",
            "═══ CHANGED FIELDS ═══",
            "  " + (", ".join(changed_fields) if changed_fields else "(none)"),
        ]

    sections += [
        "",
        "═══ YOUR TASKS ═══",
        "  1. Identify which tables (beyond the target table) are needed to",
        "     evaluate the rules — list them in needed_tables.",
        "  2. For every input field the decision table uses, add an entry to",
        "     input_mappings describing exactly where the value comes from.",
        "  3. Build a GoRules decisionTableNode where each ROW is one violation",
        "     condition (fires when the rule is BROKEN, not when it passes).",
        "  4. Return { needed_tables, gorules_json, input_mappings }.",
        "",
        "  IMPORTANT:",
        "  - Do NOT compute or hardcode any actual values in condition cells.",
        "    All values come from input_context at Zen execution time.",
        "  - Do NOT output operation_valid — that is Zen's job.",
        "  - Only encode rules relevant to this operation and changed fields.",
    ]

    return "\n".join(sections)