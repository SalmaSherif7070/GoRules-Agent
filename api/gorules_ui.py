"""
api/gorules_ui.py
------------------
REST endpoints expected by the GoRules localhost UI / JDM editor.

The editor (https://github.com/gorules/editor) talks to:
  GET  /api/decisions            → list all decision files
  GET  /api/decisions/{key}      → load one decision JSON
  PUT  /api/decisions/{key}      → save edits back to disk
  POST /api/decisions/{key}/simulate → run Zen on it with custom input

Keys use slash-encoded paths, e.g. "rule_1/Script_1"

CORS is open so the editor (served on a different port) can reach this server.
"""

import json
import logging
import urllib.parse
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from mcp_server.core.zen_executor import execute_decision

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/decisions", tags=["GoRules UI"])

GORULES_ROOT = Path("GoRules_rules")


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _all_json_files() -> list[Path]:
    if not GORULES_ROOT.exists():
        return []
    return sorted(GORULES_ROOT.rglob("*.json"))


def _key_to_path(key: str) -> Path:
    """Convert URL key → file path.  key = 'rule_1/Script_1'"""
    decoded = urllib.parse.unquote(key)
    return GORULES_ROOT / f"{decoded}.json"


def _path_to_key(path: Path) -> str:
    """Convert file path → URL key without extension."""
    return str(path.relative_to(GORULES_ROOT)).replace("\\", "/").removesuffix(".json")


# ─────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────

class SimulateRequest(BaseModel):
    context: dict[str, Any]   # flat input dict the editor sends


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────

@router.get("", summary="List all decision files")
async def list_decisions():
    files = _all_json_files()
    return [
        {
            "key":   _path_to_key(f),
            "name":  f.stem,
            "folder": f.parent.name,
        }
        for f in files
    ]


@router.get("/{key:path}", summary="Load a decision JSON")
async def get_decision(key: str):
    path = _key_to_path(key)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Decision '{key}' not found")
    return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))


@router.put("/{key:path}", summary="Save edits from the editor back to disk")
async def put_decision(key: str, request: Request):
    path = _key_to_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = await request.json()
    path.write_text(json.dumps(body, indent=2), encoding="utf-8")
    logger.info("Saved decision: %s", path)
    return {"saved": True, "key": key}


@router.post("/{key:path}/simulate", summary="Evaluate a decision with test input")
async def simulate_decision(key: str, req: SimulateRequest):
    path = _key_to_path(key)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Decision '{key}' not found")

    gorules_json = json.loads(path.read_text(encoding="utf-8"))

    try:
        violations = execute_decision(gorules_json, req.context)
        return {
            "result":     violations,
            "violations": len(violations),
            "valid":      len(violations) == 0,
        }
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))