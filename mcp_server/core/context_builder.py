"""
mcp_server/core/context_builder.py
------------------------------------
Resolves Gemini's input_mappings into a flat dict that the Zen engine can
evaluate directly.

This module is the bridge between:
  - Gemini's output  (what fields are needed and where they come from)
  - Real data        (actual rows fetched from CSVs)
  - Zen's input      (a flat {key: value} context)

Four source types Gemini can declare:

  "target_row"    key comes directly from the new row being validated
  "previous_row"  key comes from the row before UPDATE
  "lookup"        key must be fetched by scanning a table for a matching row
  "computed"      key is derived from other resolved keys via a formula

Computed formulas are evaluated safely — only arithmetic on resolved numeric
keys is permitted. No exec(), no eval() on arbitrary strings.
"""

import logging
import operator
import re
from typing import Any

logger = logging.getLogger(__name__)

# Safe arithmetic operators for computed formulas
_OPS = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
}


def _resolve_dot_path(path: str, target_row: dict, previous_row: dict | None) -> Any:
    """
    Resolve a dot-path like "target_row.manager_id" or "previous_row.salary"
    against the actual row dicts.
    """
    parts = path.split(".", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid dot-path in input_mappings: '{path}'")

    root, field = parts
    if root == "target_row":
        return target_row.get(field)
    if root == "previous_row":
        if previous_row is None:
            raise ValueError(
                f"Mapping references previous_row.{field} but no previous_row provided"
            )
        return previous_row.get(field)
    raise ValueError(f"Unknown root in dot-path: '{root}' (expected target_row or previous_row)")


def _evaluate_formula(formula: str, resolved: dict[str, Any]) -> float:
    """
    Safely evaluate a simple arithmetic formula like:
      "(salary - previous_salary) / previous_salary * 100"

    Only references keys already present in `resolved`.
    Supports: +  -  *  /  parentheses  numeric literals.
    Raises ValueError for any unrecognised token.
    """
    # Replace key references with their numeric values
    expr = formula
    for key, value in resolved.items():
        if isinstance(value, (int, float)):
            expr = re.sub(rf"\b{re.escape(key)}\b", str(float(value)), expr)

    # Validate: only digits, spaces, parens, and arithmetic operators remain
    if re.search(r"[^0-9\s\.\+\-\*\/\(\)]", expr):
        raise ValueError(
            f"Unsafe computed formula after substitution: '{expr}'\n"
            f"Original: '{formula}'"
        )

    try:
        # Use Python's ast-safe eval alternative: parse as arithmetic only
        result = _safe_arith_eval(expr)
        return float(result)
    except Exception as exc:
        raise ValueError(f"Failed to evaluate formula '{formula}': {exc}") from exc


def _safe_arith_eval(expr: str) -> float:
    """
    Evaluate a purely numeric arithmetic expression without eval().
    Handles: numbers, +, -, *, /, parentheses.
    Raises ValueError on anything unexpected.
    """
    import ast
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid expression: {expr}") from exc

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            ops = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.Div: operator.truediv,
            }
            op_fn = ops.get(type(node.op))
            if op_fn is None:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
            return op_fn(left, right)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -_eval(node.operand)
        raise ValueError(f"Unsupported AST node: {type(node).__name__}")

    return _eval(tree)


def _lookup(
    mapping: dict[str, Any],
    table_data: dict[str, list[dict]],
    target_row: dict,
    previous_row: dict | None,
) -> Any:
    """
    Resolve a lookup mapping:
      {
        "source":      "lookup",
        "table":       "employees",
        "match_field": "employee_id",
        "match_from":  "target_row.manager_id",
        "value_field": "salary"
      }
    """
    table_name = mapping.get("table")
    match_field = mapping.get("match_field")
    match_from = mapping.get("match_from")
    value_field = mapping.get("value_field")

    if not all([table_name, match_field, match_from, value_field]):
        raise ValueError(f"Incomplete lookup mapping: {mapping}")

    match_value = _resolve_dot_path(match_from, target_row, previous_row)
    rows = table_data.get(table_name, [])

    if not rows:
        logger.warning("Lookup table '%s' has no rows — returning None", table_name)
        return None

    for row in rows:
        row_val = row.get(match_field)
        # Cast both sides to string for loose comparison (CSV types vary)
        if str(row_val) == str(match_value):
            result = row.get(value_field)
            logger.debug(
                "Lookup %s.%s where %s=%s → %s=%s",
                table_name, value_field, match_field, match_value, value_field, result,
            )
            return result

    logger.warning(
        "Lookup found no match in %s where %s=%s",
        table_name, match_field, match_value,
    )
    return None


def build_input_context(
    input_mappings: dict[str, Any],
    target_row: dict[str, Any],
    previous_row: dict[str, Any] | None,
    table_data: dict[str, list[dict]],
    related_context: dict[str, Any],
) -> dict[str, Any]:
    """
    Resolve all entries in input_mappings into a flat {key: value} dict
    suitable for passing directly to the Zen engine.

    Resolution order:
      1. target_row and previous_row sources  (no dependencies)
      2. lookup sources                       (depend on rows, not on other keys)
      3. computed sources                     (depend on keys resolved in 1 & 2)

    Args:
        input_mappings  : the input_mappings dict from Gemini's response
        target_row      : the new row being validated
        previous_row    : the row before UPDATE (None for INSERT)
        table_data      : { table_name: [row_dicts] } for needed tables
        related_context : optional caller-supplied pre-fetched data
                          (merged in after all mappings are resolved;
                           caller values take priority)

    Returns:
        Flat dict ready for zen_executor.execute_decision()
    """
    resolved: dict[str, Any] = {}

    # ── Pass 1: direct sources (target_row, previous_row) ─────────────────
    for key, mapping in input_mappings.items():
        source = mapping.get("source")
        try:
            if source == "target_row":
                field = mapping.get("field", key)
                resolved[key] = target_row.get(field)

            elif source == "previous_row":
                field = mapping.get("field", key)
                resolved[key] = (previous_row or {}).get(field)

        except Exception as exc:
            logger.warning("Failed to resolve '%s' (%s): %s", key, source, exc)
            resolved[key] = None

    # ── Pass 2: lookups ────────────────────────────────────────────────────
    for key, mapping in input_mappings.items():
        if mapping.get("source") != "lookup":
            continue
        try:
            resolved[key] = _lookup(mapping, table_data, target_row, previous_row)
        except Exception as exc:
            logger.warning("Lookup failed for '%s': %s", key, exc)
            resolved[key] = None

    # ── Pass 3: computed values ────────────────────────────────────────────
    for key, mapping in input_mappings.items():
        if mapping.get("source") != "computed":
            continue
        formula = mapping.get("formula", "")
        if not formula:
            logger.warning("Computed mapping '%s' has no formula", key)
            resolved[key] = None
            continue
        try:
            resolved[key] = _evaluate_formula(formula, resolved)
            logger.debug("Computed '%s' = %s (formula: %s)", key, resolved[key], formula)
        except Exception as exc:
            logger.warning("Computed formula failed for '%s': %s", key, exc)
            resolved[key] = None

    # ── Merge caller-supplied related_context (takes priority) ─────────────
    # Flatten nested related_context dicts one level deep for convenience.
    # E.g. {"manager": {"salary": 10000}} → also adds "manager_salary": 10000
    for ctx_key, ctx_val in related_context.items():
        if isinstance(ctx_val, dict):
            for sub_key, sub_val in ctx_val.items():
                flat_key = f"{ctx_key}_{sub_key}"
                if flat_key not in resolved:
                    resolved[flat_key] = sub_val
        if ctx_key not in resolved:
            resolved[ctx_key] = ctx_val

    # Cast numeric strings to numbers for clean Zen comparisons
    for k, v in resolved.items():
        if isinstance(v, str):
            try:
                resolved[k] = int(v)
                continue
            except ValueError:
                pass
            try:
                resolved[k] = float(v)
            except ValueError:
                pass

    logger.info("input_context resolved: %d keys", len(resolved))
    return resolved