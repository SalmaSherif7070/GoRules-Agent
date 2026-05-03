import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mcp_server.core.gemini_compiler import compile_and_validate
from mcp_server.core.data_loader import list_table_names, get_table_info
from mcp_server.models import ValidationResult, ViolatedRule

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["GoRules Compiler"])


class ValidateRequest(BaseModel):
    operation: str = Field(..., description="INSERT or UPDATE")
    target_table: str = Field(..., description="Table name matching a loaded CSV")
    target_row: dict[str, Any] = Field(..., description="Row values to insert/update")
    previous_row: Optional[dict[str, Any]] = Field(
        default=None, description="Existing row before UPDATE"
    )
    related_context: Optional[dict[str, Any]] = Field(
        default=None, description="Pre-fetched lookups or aggregate counts"
    )
    rules: list[str] = Field(
        ...,
        description="Natural language business rules to validate against",
        examples=[["Salary increase cannot exceed 20% of previous salary",
                   "Employee salary cannot exceed manager salary"]],
    )


class ValidateResponse(BaseModel):
    operation_valid: bool
    violated_rules: list[ViolatedRule] = Field(default_factory=list)
    gorules_code: str = Field(default="")
    execution_dependencies: list[str] = Field(default_factory=list)
    changed_fields: list[str] = Field(default_factory=list)
    rules_evaluated: int = Field(default=0)


class HealthResponse(BaseModel):
    status: str
    tables_loaded: int


@router.get("/health", response_model=HealthResponse)
async def health():
    tables = list_table_names()
    return HealthResponse(status="ok", tables_loaded=len(tables))


@router.post("/validate", response_model=ValidateResponse)
async def validate(req: ValidateRequest):
    if req.operation.upper() not in ("INSERT", "UPDATE"):
        raise HTTPException(status_code=400, detail="operation must be INSERT or UPDATE")
    if not req.rules:
        raise HTTPException(status_code=400, detail="rules list cannot be empty")
    try:
        result = compile_and_validate(
            operation=req.operation,
            target_table=req.target_table,
            target_row=req.target_row,
            previous_row=req.previous_row,
            related_context=req.related_context,
            rules=req.rules,
        )
        return result
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("validate endpoint failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/tables")
async def tables():
    names = list_table_names()
    return {"tables": names, "count": len(names)}


@router.get("/tables/{table_name}")
async def table_detail(table_name: str):
    info = get_table_info(table_name)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")
    return info