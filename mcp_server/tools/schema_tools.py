"""
mcp_server/tools/schema_tools.py
----------------------------------
MCP tools for managing table schemas and rules CSVs.

Tools:
  list_tables      — list all loaded table names
  get_table        — preview a table (columns + sample rows)
  upload_table     — upload a new table CSV (base64 encoded)
  list_rules       — list all loaded business rules
  upload_rules     — upload a new rules CSV (base64 encoded)
"""

import base64
import json
import logging

from mcp_server.core.data_loader import (
    list_table_names,
    get_table_info,
    save_table_csv,
    load_rules_list,
    save_rules_csv,
)

logger = logging.getLogger(__name__)


async def list_tables() -> str:
    """Return a JSON list of all available table names."""
    names = list_table_names()
    return json.dumps({"tables": names, "count": len(names)})


async def get_table(table_name: str, max_rows: int = 10) -> str:
    """
    Return schema and sample rows for a named table.

    Args:
        table_name: Name of the table (without .csv extension)
        max_rows:   Max number of sample rows to return (default 10)
    """
    info = get_table_info(table_name)
    if info is None:
        return json.dumps({"error": f"Table '{table_name}' not found"})
    # Honour max_rows
    result = info.model_dump()
    result["sample_rows"] = result["sample_rows"][:max_rows]
    return json.dumps(result, indent=2)


async def upload_table(filename: str, csv_content_base64: str) -> str:
    """
    Upload a new table CSV, replacing any existing file with the same name.

    Args:
        filename:            e.g. "employees.csv"
        csv_content_base64:  base64-encoded CSV content
    """
    if not filename.endswith(".csv"):
        return json.dumps({"error": "filename must end with .csv"})
    try:
        content = base64.b64decode(csv_content_base64)
    except Exception as exc:
        return json.dumps({"error": f"Invalid base64: {exc}"})

    table_name = save_table_csv(filename, content)
    return json.dumps({"message": f"Table '{table_name}' uploaded successfully"})


async def list_rules() -> str:
    """Return all business rules as a JSON array."""
    rules = load_rules_list()
    return json.dumps(
        {"rules": [r.model_dump() for r in rules], "count": len(rules)},
        indent=2,
    )


async def upload_rules(csv_content_base64: str) -> str:
    """
    Upload a new rules CSV, replacing the existing rules.csv.

    Args:
        csv_content_base64: base64-encoded rules CSV content
    """
    try:
        content = base64.b64decode(csv_content_base64)
    except Exception as exc:
        return json.dumps({"error": f"Invalid base64: {exc}"})

    count = save_rules_csv(content)
    return json.dumps({"message": f"Rules uploaded successfully ({count} rules)"})