"""
api/routes.py
--------------
FastAPI REST endpoints for testing the GoRules Compiler Agent.

These endpoints call the same underlying functions as the MCP tools,
but are accessible via standard HTTP requests (Postman, browser, curl).
Swagger docs available at /docs.
"""

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mcp_server.core.gemini_compiler import compile_and_validate
from mcp_server.core.data_loader import (
    list_table_names,
    get_table_info,
    load_rules_list,
)
from mcp_server.models import ValidationResult, ViolatedRule

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["GoRules Compiler"])


# ---------------------------------------------------------------------------
# Request / Response models for REST
# ---------------------------------------------------------------------------

class ValidateRequest(BaseModel):
    """Request body for the /api/validate endpoint."""

    operation: str = Field(
        ...,
        description="Data operation type: INSERT or UPDATE",
        examples=["UPDATE"],
    )
    target_table: str = Field(
        ...,
        description="Name of the table being modified (e.g. 'employees')",
        examples=["employees"],
    )
    target_row: dict[str, Any] = Field(
        ...,
        description="The new / inserted row values as a flat JSON object",
        examples=[{
            "employee_id": 4, "name": "Emp_1",
            "department_id": 1, "manager_id": 2,
            "salary": 8500, "previous_salary": 7000,
            "leave_balance": 8, "performance_rating": 3,
        }],
    )
    previous_row: Optional[dict[str, Any]] = Field(
        default=None,
        description="The existing row values before UPDATE (required for UPDATE)",
        examples=[{
            "employee_id": 4, "name": "Emp_1",
            "department_id": 1, "manager_id": 2,
            "salary": 7000, "previous_salary": 6500,
            "leave_balance": 8, "performance_rating": 3,
        }],
    )
    related_context: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "Pre-fetched lookup data the caller has already resolved "
            "(e.g. manager row, department row, aggregate counts)."
        ),
        examples=[{
            "manager": {"employee_id": 2, "salary": 10000, "department_id": 1},
            "department": {"department_id": 1, "budget_allocated": 200000, "budget_used": 150000},
            "active_projects_count": 2,
            "subordinate_count": 3,
        }],
    )


class ValidateResponse(BaseModel):
    """Response body for the /api/validate endpoint."""

    operation_valid: bool
    violated_rules: list[ViolatedRule] = Field(default_factory=list)
    gorules_code: str = Field(default="")
    execution_dependencies: list[str] = Field(default_factory=list)
    changed_fields: list[str] = Field(default_factory=list)
    rules_evaluated: int = Field(default=0)


class TableListResponse(BaseModel):
    tables: list[str]
    count: int


class TableDetailResponse(BaseModel):
    name: str
    columns: list[str]
    row_count: int
    sample_rows: list[dict[str, Any]]


class RuleItem(BaseModel):
    rule_id: str
    category: str
    rule_description: str
    field_1: str
    operator: str
    field_2_or_value: str


class RulesListResponse(BaseModel):
    rules: list[RuleItem]
    count: int


class HealthResponse(BaseModel):
    status: str
    tables_loaded: int
    rules_loaded: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Check that the server is running and data files are loaded.",
)
async def health():
    tables = list_table_names()
    rules = load_rules_list()
    return HealthResponse(
        status="ok",
        tables_loaded=len(tables),
        rules_loaded=len(rules),
    )


@router.post(
    "/validate",
    response_model=ValidateResponse,
    summary="Validate a data operation",
    description=(
        "Compile business rules from the loaded rules.csv and table schemas, "
        "then validate whether an INSERT or UPDATE operation is permitted. "
        "Returns which rules were violated and the generated GoRules JSON."
    ),
)
async def validate(req: ValidateRequest):
    if req.operation.upper() not in ("INSERT", "UPDATE"):
        raise HTTPException(status_code=400, detail="operation must be INSERT or UPDATE")

    try:
        result = compile_and_validate(
            operation=req.operation,
            target_table=req.target_table,
            target_row=req.target_row,
            previous_row=req.previous_row,
            related_context=req.related_context,
        )
        return result
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("validate endpoint failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/tables",
    response_model=TableListResponse,
    summary="List all tables",
    description="List all table CSV files currently loaded in the data/tables/ directory.",
)
async def tables():
    names = list_table_names()
    return TableListResponse(tables=names, count=len(names))


@router.get(
    "/tables/{table_name}",
    response_model=TableDetailResponse,
    summary="Get table details",
    description="Preview the schema and sample rows of a named table.",
)
async def table_detail(table_name: str, max_rows: int = 10):
    info = get_table_info(table_name)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")
    result = info.model_dump()
    result["sample_rows"] = result["sample_rows"][:max_rows]
    return result


@router.get(
    "/rules",
    response_model=RulesListResponse,
    summary="List all business rules",
    description="List all business rules currently loaded from rules.csv.",
)
async def rules():
    rule_list = load_rules_list()
    return RulesListResponse(
        rules=[r.model_dump() for r in rule_list],
        count=len(rule_list),
    )
