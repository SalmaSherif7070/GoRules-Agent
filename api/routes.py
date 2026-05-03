"""
api/routes.py
--------------
REST API layer. Thin — no business logic here.

Key behaviours:
  - rules are auto-loaded from data/rules/rules.csv if not supplied in body
  - response model is ValidationResult directly (no duplicate schema)
  - operation must be INSERT or UPDATE
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mcp_server.core.gemini_compiler import compile_and_validate
from mcp_server.core.data_loader import list_table_names, get_table_info, load_rules_list
from mcp_server.models import ValidationResult

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["GoRules Compiler"])


# ─────────────────────────────────────────────────────────────
# Request / response models
# ─────────────────────────────────────────────────────────────

class ValidateRequest(BaseModel):
    operation: str = Field(..., description="INSERT or UPDATE")
    target_table: str = Field(..., description="Table name matching a loaded CSV")
    target_row: dict[str, Any] = Field(..., description="Row values to insert/update")
    previous_row: Optional[dict[str, Any]] = Field(
        default=None,
        description="Existing row before UPDATE (required for UPDATE operations)",
    )
    related_context: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "Optional pre-fetched lookup data the caller already has. "
            "When provided, skips fetching those values from CSV at runtime. "
            "Example: {'manager': {'salary': 10000}}"
        ),
    )
    rules: Optional[list[str]] = Field(
        default=None,
        description=(
            "Business rules in plain English. "
            "If omitted, rules are loaded automatically from data/rules/rules.csv."
        ),
        examples=[["Salary increase cannot exceed 20% of previous salary"]],
    )


class HealthResponse(BaseModel):
    status: str
    tables_loaded: int
    rules_loaded: int


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
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
    response_model=ValidationResult,
    summary="Validate an INSERT or UPDATE operation against business rules",
    description=(
        "Compiles business rules into an executable GoRules decision table (via Gemini), "
        "then runs it through the Zen engine to determine whether the operation is valid. "
        "Gemini sees table schemas only — no row data — keeping the system scalable. "
        "Actual row data is fetched only for the tables Gemini identifies as needed, "
        "then passed to Zen for evaluation."
    ),
)
async def validate(req: ValidateRequest):
    op = req.operation.upper()
    if op not in ("INSERT", "UPDATE"):
        raise HTTPException(status_code=400, detail="operation must be INSERT or UPDATE")

    # Resolve rules: caller-supplied takes priority, else load from CSV
    if req.rules:
        rules = req.rules
        logger.info("Using %d caller-supplied rules", len(rules))
    else:
        rules_rows = load_rules_list()
        rules = [
            f"{r.rule_id}. {r.category}: {r.rule_description}"
            for r in rules_rows
        ]
        logger.info("Auto-loaded %d rules from rules.csv", len(rules))

    if not rules:
        raise HTTPException(
            status_code=400,
            detail=(
                "No rules provided and none found in data/rules/rules.csv. "
                "Either supply rules in the request body or populate the rules file."
            ),
        )

    try:
        result: ValidationResult = compile_and_validate(
            operation=op,
            target_table=req.target_table,
            target_row=req.target_row,
            previous_row=req.previous_row,
            related_context=req.related_context,
            rules=rules,
        )
        return result

    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Unhandled error in /api/validate")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/tables", summary="List all loaded table names")
async def tables():
    names = list_table_names()
    return {"tables": names, "count": len(names)}


@router.get("/tables/{table_name}", summary="Preview a table's schema and sample rows")
async def table_detail(table_name: str):
    info = get_table_info(table_name)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")
    return info


@router.get("/rules", summary="List all loaded business rules")
async def rules():
    rules_rows = load_rules_list()
    return {
        "rules": [r.model_dump() for r in rules_rows],
        "count": len(rules_rows),
    }