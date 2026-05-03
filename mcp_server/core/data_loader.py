"""
mcp_server/core/data_loader.py
-------------------------------
Two strict responsibilities:

1. SCHEMA loading  — column names + inferred types only.
   This is what gets sent to Gemini. Never full row data.

2. ROW fetching — load actual rows from ONLY the tables Gemini says it needs.
   This is what gets passed to the Zen engine as input_context.

Keeping these two paths separate is the core scalability fix:
  Gemini sees:  schema  (tiny, always fast)
  Zen sees:     rows    (only the tables that matter, fetched at runtime)
"""

import csv
import io
import logging
from pathlib import Path
from typing import Any

from config import settings
from mcp_server.models import TableInfo, RuleRow

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Schema helpers — sent to Gemini
# ─────────────────────────────────────────────────────────────

def _infer_type(values: list[str]) -> str:
    """Infer the SQL-ish type of a column from its sample values."""
    non_empty = [v for v in values if v.strip()]
    if not non_empty:
        return "text"
    for v in non_empty:
        try:
            int(v)
        except ValueError:
            break
    else:
        return "integer"
    for v in non_empty:
        try:
            float(v)
        except ValueError:
            break
    else:
        return "decimal"
    return "text"


def _csv_to_schema(path: Path) -> dict[str, Any]:
    """
    Return a lightweight schema dict for one CSV:
      { "columns": [{"name": ..., "type": ...}, ...], "row_count": N }
    Does NOT return any row data.
    """
    text = path.read_text(encoding="utf-8")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        return {"columns": [], "row_count": 0}

    columns = []
    for col in rows[0].keys():
        sample_values = [r.get(col, "") for r in rows[:20]]
        columns.append({"name": col.strip(), "type": _infer_type(sample_values)})

    return {"columns": columns, "row_count": len(rows)}


def load_all_schemas() -> dict[str, dict]:
    """
    Return a dict of  { table_name: schema }  for every CSV in TABLES_DIR.
    This is the ONLY table data that Gemini ever sees.

    Example output:
      {
        "employees": {
          "columns": [
            {"name": "employee_id", "type": "integer"},
            {"name": "salary",      "type": "decimal"},
            ...
          ],
          "row_count": 42
        },
        "departments": { ... }
      }
    """
    tables_path = settings.tables_path
    if not tables_path.exists():
        logger.warning("Tables directory not found: %s", tables_path)
        return {}

    schemas: dict[str, dict] = {}
    for csv_file in sorted(tables_path.glob("*.csv")):
        schemas[csv_file.stem] = _csv_to_schema(csv_file)
        logger.debug("Loaded schema: %s (%d cols)", csv_file.stem,
                     len(schemas[csv_file.stem]["columns"]))

    if not schemas:
        logger.warning("No CSV files found in %s", tables_path)
    return schemas


def format_schemas_for_prompt(schemas: dict[str, dict]) -> str:
    """
    Render schemas as a human-readable block for the Gemini prompt.
    Each table shows column names and types only — no row values.

    Example:
      TABLE: employees  (42 rows)
        employee_id  integer
        name         text
        salary       decimal
        ...
    """
    if not schemas:
        return "(no tables loaded)"

    lines: list[str] = []
    for table_name, schema in schemas.items():
        lines.append(f"TABLE: {table_name}  ({schema['row_count']} rows)")
        for col in schema["columns"]:
            lines.append(f"  {col['name']:<28} {col['type']}")
        lines.append("")
    return "\n".join(lines).rstrip()


# ─────────────────────────────────────────────────────────────
# Row fetching — data for Zen engine input_context only
# ─────────────────────────────────────────────────────────────

def load_table_rows(table_name: str) -> list[dict[str, Any]]:
    """
    Load all rows from a single table as a list of dicts.
    Values are cast to int/float where possible.
    Called ONLY for tables Gemini identifies as needed — not all tables.
    """
    path = settings.tables_path / f"{table_name}.csv"
    if not path.exists():
        logger.warning("Table not found for row fetch: %s", table_name)
        return []

    text = path.read_text(encoding="utf-8")
    rows: list[dict[str, Any]] = []
    for raw in csv.DictReader(io.StringIO(text)):
        row: dict[str, Any] = {}
        for k, v in raw.items():
            k = k.strip()
            v = v.strip()
            try:
                row[k] = int(v)
            except ValueError:
                try:
                    row[k] = float(v)
                except ValueError:
                    row[k] = v
        rows.append(row)

    logger.debug("Fetched %d rows from table '%s'", len(rows), table_name)
    return rows


def load_tables_for_context(table_names: list[str]) -> dict[str, list[dict]]:
    """
    Load rows for a specific list of table names only.
    Returns { table_name: [row_dicts, ...] }

    This is the data that feeds Zen — not Gemini.
    """
    result: dict[str, list[dict]] = {}
    for name in table_names:
        rows = load_table_rows(name)
        if rows:
            result[name] = rows
        else:
            logger.warning("Skipping empty / missing table: %s", name)
    return result


# ─────────────────────────────────────────────────────────────
# Diff helper
# ─────────────────────────────────────────────────────────────

def infer_changed_fields(
    target_row: dict[str, Any],
    previous_row: dict[str, Any] | None,
) -> list[str]:
    """
    Return field names whose values differ between target_row and previous_row.
    For INSERT (previous_row=None) every field is considered 'changed'.
    """
    if previous_row is None:
        return list(target_row.keys())
    return [
        field
        for field in target_row
        if str(target_row.get(field)) != str(previous_row.get(field))
    ]


# ─────────────────────────────────────────────────────────────
# Convenience helpers used by API routes and MCP tools
# ─────────────────────────────────────────────────────────────

def list_table_names() -> list[str]:
    """Return sorted list of available table names (no .csv extension)."""
    if not settings.tables_path.exists():
        return []
    return sorted(p.stem for p in settings.tables_path.glob("*.csv"))


def get_table_info(table_name: str) -> TableInfo | None:
    """Return TableInfo (schema + sample rows) for a named table, or None."""
    path = settings.tables_path / f"{table_name}.csv"
    if not path.exists():
        return None
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))
    if not rows:
        return TableInfo(name=table_name, columns=[], row_count=0, sample_rows=[])
    return TableInfo(
        name=table_name,
        columns=list(rows[0].keys()),
        row_count=len(rows),
        sample_rows=rows[:5],
    )


def save_table_csv(filename: str, content: bytes) -> str:
    """Persist uploaded CSV to tables directory. Returns table name."""
    settings.tables_path.mkdir(parents=True, exist_ok=True)
    dest = settings.tables_path / filename
    dest.write_bytes(content)
    logger.info("Saved table: %s", dest)
    return Path(filename).stem


# ─────────────────────────────────────────────────────────────
# Rules loading — from data/rules/rules.csv
# ─────────────────────────────────────────────────────────────

def load_rules_list() -> list[RuleRow]:
    """Return parsed rules as a list of RuleRow objects."""
    if not settings.rules_path.exists():
        logger.warning("Rules file not found: %s", settings.rules_path)
        return []
    text = settings.rules_path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    reader = csv.DictReader(io.StringIO(text))
    rules: list[RuleRow] = []
    for row in reader:
        try:
            rules.append(RuleRow(**{k.strip(): v.strip() for k, v in row.items()}))
        except Exception as exc:
            logger.warning("Skipping malformed rule row %s: %s", row, exc)
    return rules


def load_rules_text() -> str:
    """Return raw rules CSV text."""
    if not settings.rules_path.exists():
        logger.warning("Rules file not found: %s", settings.rules_path)
        return ""
    return settings.rules_path.read_text(encoding="utf-8").strip()


def save_rules_csv(content: bytes) -> int:
    """Persist uploaded rules CSV. Returns number of rules parsed."""
    settings.rules_path.parent.mkdir(parents=True, exist_ok=True)
    settings.rules_path.write_bytes(content)
    logger.info("Saved rules file: %s", settings.rules_path)
    reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
    return sum(1 for _ in reader)