# Rule-to-GoRules Compiler Agent (MCP + Gemini)

Converts business rules + table schemas into executable GoRules validation
logic using Gemini as the compiler engine, exposed as an MCP server.

```
Rules CSV ──► Schema Inference ──► Gemini Compiler ──► GoRules JSON ──► Validation Result
                                         ▲
                                     MCP Tools
```

---

## Project Structure

```
gorules-mcp/
│
├── main.py                          ← Entry point (SSE or stdio)
├── .env                             ← Your secrets (not committed)
├── .env.example                     ← Template to copy
├── requirements.txt
│
├── config/
│   ├── __init__.py
│   └── settings.py                  ← All settings via pydantic-settings
│
├── mcp_server/
│   ├── __init__.py
│   ├── server.py                    ← FastMCP server + tool registrations
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py               ← All Pydantic request/response models
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── data_loader.py           ← CSV I/O, schema loading, field diff
│   │   ├── prompt_builder.py        ← Gemini prompt construction
│   │   └── gemini_compiler.py       ← Gemini API call + response parsing
│   │
│   └── tools/
│       ├── __init__.py
│       ├── validate_tool.py         ← validate_operation MCP tool
│       └── schema_tools.py          ← list/get/upload table & rules tools
│
├── client/
│   └── mcp_client.py               ← Python MCP client (test runner)
│
├── tests/
│   ├── test_data_loader.py
│   ├── test_prompt_builder.py
│   └── test_schemas.py
│
└── data/
    ├── rules/
    │   └── rules.csv               ← 20 business rules (sample)
    └── tables/
        ├── employees.csv
        ├── departments.csv
        ├── attendance.csv
        ├── leave_requests.csv
        ├── projects.csv
        ├── project_assignments.csv
        └── bonuses.csv
```

---

## Setup

```bash
# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — set GEMINI_API_KEY
```

### .env reference

| Variable            | Default              | Description                          |
|---------------------|----------------------|--------------------------------------|
| `GEMINI_API_KEY`    | *(required)*         | Google AI Studio key                 |
| `GEMINI_MODEL`      | `gemini-2.0-flash`   | Gemini model name                    |
| `GEMINI_MAX_TOKENS` | `4096`               | Max output tokens                    |
| `GEMINI_TEMPERATURE`| `0.1`                | Low = deterministic compilation      |
| `MCP_TRANSPORT`     | `sse`                | `sse` (HTTP) or `stdio`              |
| `MCP_SERVER_HOST`   | `0.0.0.0`            | SSE bind host                        |
| `MCP_SERVER_PORT`   | `8000`               | SSE bind port                        |
| `TABLES_DIR`        | `data/tables`        | Path to table CSV directory          |
| `RULES_FILE`        | `data/rules/rules.csv` | Path to rules CSV                |
| `LOG_LEVEL`         | `INFO`               | Logging verbosity                    |

---

## Running the server

### SSE transport (HTTP — default)
```bash
python main.py
# Server at http://localhost:8000
```

### stdio transport (Claude Desktop / MCP CLI)
```bash
python main.py --stdio
```

---

## MCP Tools

| Tool                    | Description                                              |
|-------------------------|----------------------------------------------------------|
| `validate_operation_tool` | Compile rules + validate INSERT or UPDATE            |
| `list_tables_tool`      | List all loaded table names                              |
| `get_table_tool`        | Preview schema + sample rows for a table                 |
| `upload_table_tool`     | Upload a new table CSV (base64)                          |
| `list_rules_tool`       | List all business rules                                  |
| `upload_rules_tool`     | Upload a new rules CSV (base64)                          |

### validate_operation_tool — input

```json
{
  "operation": "UPDATE",
  "target_table": "employees",
  "target_row": "{\"employee_id\":4,\"salary\":8500,\"performance_rating\":3}",
  "previous_row": "{\"employee_id\":4,\"salary\":7000,\"performance_rating\":3}",
  "related_context": "{\"manager\":{\"salary\":10000},\"active_projects_count\":2}"
}
```

### validate_operation_tool — output

```json
{
  "operation_valid": false,
  "violated_rules": [
    {
      "rule_id": "1",
      "reason": "Salary 8500 exceeds 120% of previous salary 7000 (max: 8400)"
    }
  ],
  "gorules_code": "{ ... GoRules JSON ... }",
  "execution_dependencies": ["Fetch manager row by manager_id"],
  "changed_fields": ["salary"],
  "rules_evaluated": 1
}
```

---

## Running the client test runner

```bash
# Server must be running first
python client/mcp_client.py
# or
python client/mcp_client.py --url http://localhost:8000
```

Runs 3 scenarios automatically:
1. UPDATE salary 21.4% over cap → **INVALID**
2. UPDATE salary 11.4% increase → **VALID**
3. INSERT new employee → **VALID**

---

## Running tests

```bash
pytest tests/ -v
# 22 tests — all offline, no API calls
```

---

## Claude Desktop integration

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "gorules-compiler": {
      "command": "python",
      "args": ["/absolute/path/to/gorules-mcp/main.py", "--stdio"],
      "env": {
        "GEMINI_API_KEY": "your_key_here"
      }
    }
  }
}
```

---

## Adding a new domain

1. Drop your domain CSVs into `data/tables/`
2. Replace `data/rules/rules.csv` with your domain rules
3. Call `validate_operation_tool` — the agent adapts automatically

No code changes needed.