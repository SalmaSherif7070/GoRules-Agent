"""
mcp_server/server.py
---------------------
FastMCP server definition.

This module:
  1. Creates the FastMCP server instance
  2. Registers all tools with their descriptions
  3. Exposes `mcp` for import by main.py

Run via:
    python main.py              (SSE transport — HTTP clients)
    python main.py --stdio      (stdio transport — Claude Desktop / CLI)
"""

import logging
from fastmcp import FastMCP

from mcp_server.tools import (
    validate_operation,
    list_tables,
    get_table,
    upload_table,
    list_rules,
    upload_rules,
)
from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name=settings.mcp_server_name,
    instructions=(
        "You are connected to the GoRules Compiler Agent. "
        "Use validate_operation to check whether an INSERT or UPDATE is allowed "
        "against the loaded business rules. "
        "Use list_tables / get_table to inspect schemas. "
        "Use list_rules to see active rules. "
        "Use upload_table / upload_rules to load new data."
    ),
)

# ---------------------------------------------------------------------------
# Tool registrations
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Compile business rules from the loaded rules.csv and table schemas, "
        "then validate whether an INSERT or UPDATE operation is permitted.\n\n"
        "Returns: operation_valid (bool), violated_rules, gorules_code (executable "
        "GoRules JSON), execution_dependencies, changed_fields."
    )
)
async def validate_operation_tool(
    operation: str,
    target_table: str,
    target_row: str,
    previous_row: str | None = None,
    related_context: str | None = None,
) -> str:
    """
    Args:
        operation:       "INSERT" or "UPDATE"
        target_table:    Table being modified (e.g. "employees")
        target_row:      JSON string of new / inserted row values
        previous_row:    JSON string of existing row (UPDATE only)
        related_context: JSON string of pre-fetched lookups / aggregates
    """
    return await validate_operation(
        operation=operation,
        target_table=target_table,
        target_row=target_row,
        previous_row=previous_row,
        related_context=related_context,
    )


@mcp.tool(description="List all table CSV files currently loaded in the data/tables/ directory.")
async def list_tables_tool() -> str:
    return await list_tables()


@mcp.tool(description="Preview the schema and sample rows of a named table.")
async def get_table_tool(table_name: str, max_rows: int = 10) -> str:
    """
    Args:
        table_name: Table name without .csv extension (e.g. "employees")
        max_rows:   How many sample rows to return (default 10)
    """
    return await get_table(table_name=table_name, max_rows=max_rows)


@mcp.tool(description="Upload a new table CSV, replacing any existing table with the same name.")
async def upload_table_tool(filename: str, csv_content_base64: str) -> str:
    """
    Args:
        filename:            e.g. "employees.csv"
        csv_content_base64:  Base64-encoded CSV file content
    """
    return await upload_table(filename=filename, csv_content_base64=csv_content_base64)


@mcp.tool(description="List all business rules currently loaded from rules/rules.csv.")
async def list_rules_tool() -> str:
    return await list_rules()


@mcp.tool(description="Upload a new rules CSV, replacing the existing rules.")
async def upload_rules_tool(csv_content_base64: str) -> str:
    """
    Args:
        csv_content_base64: Base64-encoded rules CSV file content
    """
    return await upload_rules(csv_content_base64=csv_content_base64)