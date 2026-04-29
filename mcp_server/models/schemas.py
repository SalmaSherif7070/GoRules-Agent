"""
mcp_server/models/schemas.py
-----------------------------
All Pydantic models used across MCP tools, the compiler, and the client.
"""

from typing import Any, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Inbound
# ---------------------------------------------------------------------------

class ValidateRequest(BaseModel):
    """Payload for the validate_operation MCP tool."""

    operation: str = Field(
        ...,
        description="Data operation type: INSERT or UPDATE",
        pattern="^(INSERT|UPDATE)$",
    )
    target_table: str = Field(
        ...,
        description="Name of the table being modified (e.g. 'employees')",
    )
    target_row: dict[str, Any] = Field(
        ...,
        description="The new / inserted row values as a flat JSON object",
    )
    previous_row: Optional[dict[str, Any]] = Field(
        default=None,
        description="The existing row values before UPDATE (required for UPDATE)",
    )
    related_context: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "Pre-fetched lookup data the caller has already resolved "
            "(e.g. manager row, department row, aggregate counts). "
            "Minimises DB round-trips inside the validation engine."
        ),
    )


# ---------------------------------------------------------------------------
# Outbound
# ---------------------------------------------------------------------------

class ViolatedRule(BaseModel):
    rule_id: str = Field(..., description="ID from the rules CSV")
    reason: str  = Field(..., description="Human-readable violation explanation")


class ValidationResult(BaseModel):
    operation_valid: bool
    violated_rules: list[ViolatedRule] = Field(default_factory=list)
    gorules_code: str = Field(
        default="",
        description="Executable GoRules decision-table JSON string",
    )
    execution_dependencies: list[str] = Field(
        default_factory=list,
        description="Lookups / aggregates the caller must resolve before calling validate",
    )
    changed_fields: list[str] = Field(
        default_factory=list,
        description="Fields detected as changed (UPDATE only)",
    )
    rules_evaluated: int = Field(
        default=0,
        description="Number of business rules checked",
    )


# ---------------------------------------------------------------------------
# Table preview (for list/get tools)
# ---------------------------------------------------------------------------

class TableInfo(BaseModel):
    name: str
    columns: list[str]
    row_count: int
    sample_rows: list[dict[str, Any]]


class RuleRow(BaseModel):
    rule_id: str
    category: str
    rule_description: str
    field_1: str
    operator: str
    field_2_or_value: str