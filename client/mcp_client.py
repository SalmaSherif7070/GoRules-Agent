"""
client/mcp_client.py
----------------------
Async Python client that connects to the running MCP server via SSE
and calls tools directly.

Usage (standalone):
    python client/mcp_client.py
    python client/mcp_client.py --url http://localhost:8000

This is useful for:
  - Integration testing
  - Calling the agent from another Python service
  - Scripting bulk validations
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pretty_result(label: str, raw: str):
    """Pretty-print a validation result to stdout."""
    sep = "═" * 62
    try:
        data = json.loads(raw)
    except Exception:
        print(f"\n{sep}\n  {label}\n{sep}\n{raw}\n")
        return

    valid = data.get("operation_valid", "?")
    colour = "\033[32m" if valid else "\033[31m"
    reset  = "\033[0m"

    print(f"\n{sep}")
    print(f"  {label}")
    print(sep)
    print(f"  operation_valid   : {colour}{valid}{reset}")
    print(f"  changed_fields    : {', '.join(data.get('changed_fields', []))}")

    violated = data.get("violated_rules", [])
    if violated:
        print(f"\n  VIOLATED RULES ({len(violated)}):")
        for v in violated:
            print(f"    [{v['rule_id']}] {v['reason']}")
    else:
        print("  No violations — operation allowed.")

    deps = data.get("execution_dependencies", [])
    if deps:
        print(f"\n  Execution dependencies ({len(deps)}):")
        for d in deps:
            print(f"    • {d}")

    gorules = data.get("gorules_code", "")
    print(f"\n  GoRules code  ({len(gorules)} chars) — preview:")
    print("  " + gorules[:300].replace("\n", "\n  "))
    print()


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

SCENARIO_UPDATE_FAIL = {
    "operation": "UPDATE",
    "target_table": "employees",
    "target_row": json.dumps({
        "employee_id": 4, "name": "Emp_1",
        "department_id": 1, "manager_id": 2,
        "salary": 8500,           # 21.4% increase — violates Rule 1
        "previous_salary": 7000,
        "leave_balance": 8, "performance_rating": 3,
    }),
    "previous_row": json.dumps({
        "employee_id": 4, "name": "Emp_1",
        "department_id": 1, "manager_id": 2,
        "salary": 7000, "previous_salary": 6500,
        "leave_balance": 8, "performance_rating": 3,
    }),
    "related_context": json.dumps({
        "manager": {"employee_id": 2, "salary": 10000, "department_id": 1},
        "department": {"department_id": 1, "budget_allocated": 200000, "budget_used": 150000},
        "active_projects_count": 2,
        "subordinate_count": 3,
    }),
}

SCENARIO_UPDATE_PASS = {
    **SCENARIO_UPDATE_FAIL,
    "target_row": json.dumps({
        "employee_id": 4, "name": "Emp_1",
        "department_id": 1, "manager_id": 2,
        "salary": 7800,           # 11.4% increase — within cap
        "previous_salary": 7000,
        "leave_balance": 8, "performance_rating": 3,
    }),
}

SCENARIO_INSERT = {
    "operation": "INSERT",
    "target_table": "employees",
    "target_row": json.dumps({
        "employee_id": 9, "name": "New_Hire",
        "department_id": 1, "manager_id": 2,
        "salary": 5000, "previous_salary": 5000,
        "leave_balance": 10, "performance_rating": 3,
    }),
    "related_context": json.dumps({
        "manager": {"employee_id": 2, "salary": 10000, "department_id": 1},
        "department": {"department_id": 1, "budget_allocated": 200000, "budget_used": 150000},
        "subordinate_count": 3,
    }),
}


# ---------------------------------------------------------------------------
# Main async runner
# ---------------------------------------------------------------------------

async def run(base_url: str):
    sse_url = f"{base_url}/sse"
    print(f"Connecting to MCP server at {sse_url} …")

    async with sse_client(sse_url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # -- List tools
            tools_resp = await session.list_tools()
            tool_names = [t.name for t in tools_resp.tools]
            print(f"Available tools: {', '.join(tool_names)}\n")

            # -- List tables
            r = await session.call_tool("list_tables_tool", {})
            tables = json.loads(r.content[0].text)
            print(f"Loaded tables: {tables['tables']}")

            # -- List rules
            r = await session.call_tool("list_rules_tool", {})
            rules_data = json.loads(r.content[0].text)
            print(f"Loaded rules : {rules_data['count']} rules\n")

            # -- Scenario 1: UPDATE salary above cap → INVALID
            print("Running Scenario 1 — UPDATE salary above 20% cap (expect INVALID) …")
            r = await session.call_tool("validate_operation_tool", SCENARIO_UPDATE_FAIL)
            _pretty_result("Scenario 1: salary 7000 → 8500 (21.4% — over cap)", r.content[0].text)

            # -- Scenario 2: UPDATE salary within cap → VALID
            print("Running Scenario 2 — UPDATE salary within 20% cap (expect VALID) …")
            r = await session.call_tool("validate_operation_tool", SCENARIO_UPDATE_PASS)
            _pretty_result("Scenario 2: salary 7000 → 7800 (11.4% — within cap)", r.content[0].text)

            # -- Scenario 3: INSERT new employee → VALID
            print("Running Scenario 3 — INSERT new employee (expect VALID) …")
            r = await session.call_tool("validate_operation_tool", SCENARIO_INSERT)
            _pretty_result("Scenario 3: INSERT employee salary=5000 rating=3", r.content[0].text)


def main():
    parser = argparse.ArgumentParser(description="GoRules MCP client test runner")
    parser.add_argument("--url", default="http://localhost:8000", help="MCP server base URL")
    args = parser.parse_args()
    asyncio.run(run(args.url))


if __name__ == "__main__":
    main()