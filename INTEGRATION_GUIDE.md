# GoRules Compiler Agent - Integration & Usage Guide

## Quick Start

### For End Users

The system validates business data modifications in real-time. Simply describe what you want to change:

```
"Increase employee 4 salary to 8500"
→ System validates against 20 business rules
→ Returns: INVALID - Increase exceeds 20% limit
```

### For Developers

Use the Python client library:

```python
from validation_client_mock import MockRulesCompilerClient

client = MockRulesCompilerClient()

result = client.validate_salary_increase(
    employee_id=4,
    new_salary=8500,
    old_salary=7000,
)

client.print_result(result)
```

## Integration Methods

### Method 1: Direct Python Import

For applications written in Python:

```python
from validation_client_mock import MockRulesCompilerClient

client = MockRulesCompilerClient()
result = client.validate_salary_increase(employee_id=4, new_salary=8500)

if result['operation_valid']:
    print("✓ Valid - proceed with update")
else:
    for violation in result['violated_rules']:
        print(f"❌ {violation['reason']}")
```

### Method 2: REST API

Start the FastAPI server:

```bash
venv\Scripts\python.exe main.py
```

Then POST to `http://localhost:8000/api/validate`:

```bash
curl -X POST http://localhost:8000/api/validate \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "UPDATE",
    "target_table": "employees",
    "target_row": {
      "employee_id": "4",
      "salary": 8500,
      ...
    },
    "previous_row": {
      "employee_id": "4",
      "salary": 7000,
      ...
    },
    "rules": [
      "1. Salary: Salary increase cannot exceed 20%",
      ...
    ]
  }'
```

### Method 3: MCP (Model Context Protocol)

For Claude Desktop integration, the system provides MCP tools:

- `validate_operation` — Compile and validate
- `list_tables` — List available tables
- `get_table` — Preview schema and data
- `list_rules` — List active rules

### Method 4: Command-Line

Run pre-built test scenarios:

```bash
# Mock validation (no API calls)
venv\Scripts\python.exe validation_client_mock.py

# Full validation tests
venv\Scripts\python.exe test_validation_mock.py
```

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   USER REQUEST                          │
│  "Increase employee 4 salary to 8500"                  │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│              PARSE REQUEST                              │
│  Operation: UPDATE                                      │
│  Table: employees                                       │
│  Target: employee_id=4, salary=8500                    │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│           FETCH CURRENT DATA                            │
│  From CSV: employee 4 current salary = 7000             │
│  Build: previous_row, target_row                        │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│           LOAD BUSINESS RULES                           │
│  From data/rules.csv: 20 rules                          │
│  Parse into rule objects                               │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│         COMPILE TO GORULES (via Gemini)                 │
│  Generate decision tables in GoRules format             │
│  Deterministic rule execution plan                      │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│             EVALUATE RULES                              │
│  Check each applicable rule against data                │
│  Identify violations                                    │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│          RETURN DECISION                                │
│  ✗ INVALID                                              │
│  Violated: Rule 1 (Increase exceeds 20%)                │
│  Max allowed: 8400                                      │
└─────────────────────────────────────────────────────────┘
```

## Real-World Examples

### Example 1: Salary Increase
**Input**: "Increase employee 4 salary from 7000 to 8050"
- Increase: 15% ✓
- Result: **VALID** ✓

**Input**: "Increase employee 4 salary from 7000 to 8500"
- Increase: 21.4% ✗
- Result: **INVALID** ✗
- Violation: Rule 1 (exceeds 20% limit)

### Example 2: Leave Request
**Input**: "Employee 4 requests 5 days leave (balance: 8)"
- Request: 5 days, Balance: 8 ✓
- Result: **VALID** ✓

**Input**: "Employee 4 requests 10 days leave (balance: 8)"
- Request: 10 days, Balance: 8 ✗
- Result: **INVALID** ✗
- Violation: Rule 14 (exceeds balance)

### Example 3: Bonus Award
**Input**: "Award 1200 bonus to employee 2 (salary: 10000, rating: 4)"
- Bonus: 12% of salary ✓
- Rating: 4 (≥2) ✓
- Result: **VALID** ✓

**Input**: "Award 500 bonus to employee 7 (rating: 1)"
- Bonus: acceptable amount
- Rating: 1 (<2) ✗
- Result: **INVALID** ✗
- Violation: Rule 20 (low rating cannot receive bonus)

## Modifying Business Rules

Business rules are stored in `data/rules.csv`. To modify:

1. **Edit the CSV file** directly
2. **Add new rules** by adding rows with:
   - `rule_id`: Unique number
   - `category`: Type of rule (Salary, Bonus, Leave, etc.)
   - `rule_description`: Natural language rule
   - `field_1`: Field being checked
   - `operator`: Comparison operator (<=, >=, !=, etc.)
   - `field_2_or_value`: Value or field to compare against

3. **Rules apply immediately** on next validation

### Example: Add New Rule

To add a rule "Maximum salary is 50000":

```csv
rule_id,category,rule_description,field_1,operator,field_2_or_value
21,Salary,Maximum salary is 50000,salary,<=,50000
```

## Adding New Tables

To add a new data table:

1. Create a CSV file in `data/` directory
2. Include column headers as first row
3. Add data rows
4. System automatically discovers schema on next validation

Example (`data/training_logs.csv`):
```
training_id,employee_id,course_name,completion_date,hours_completed
1,4,Python Advanced,2026-04-20,40
2,5,Leadership 101,2026-04-15,20
```

## Validation Response Format

All validation responses include:

```json
{
  "operation_valid": true|false,
  "violated_rules": [
    {
      "rule_id": "1",
      "reason": "Salary increase (21.4%) exceeds maximum 20%..."
    }
  ],
  "changed_fields": ["salary"],
  "rules_evaluated": 20,
  "gorules_code": "...",
  "execution_dependencies": []
}
```

## Key Concepts

### Changed Fields Detection

For **UPDATE** operations:
- Only fields that actually changed are evaluated
- Reduces rule checking to relevant rules
- Example: Changing salary only triggers salary rules

For **INSERT** operations:
- All fields are evaluated
- All applicable rules are checked
- Example: New employee triggers all employee rules

### Baseline Tracking

For **UPDATE** operations, always use `previous_row` to calculate changes:

```
Old salary = previous_row.salary = 7000
New salary = target_row.salary = 8500
Increase % = (8500 - 7000) / 7000 = 21.4%
```

❌ WRONG: Never use target_row to calculate the delta
```
Increase = 8500 - target_row.previous_salary  # INCORRECT
```

### Related Context

Pre-fetch related data to minimize lookups:

```python
related_context = {
  "manager_salary": 10000,
  "manager_direct_reports": 8,
  "department_budget_remaining": 50000,
}
```

## Testing

### Run All Tests

```bash
# Mock tests (no API calls)
venv\Scripts\python.exe test_validation_mock.py

# Real tests (requires Gemini API)
venv\Scripts\python.exe test_validation.py

# Client examples
venv\Scripts\python.exe validation_client_mock.py
```

### Expected Results

All tests should show:
- ✓ VALID scenarios pass
- ✗ INVALID scenarios fail with detailed violation reasons
- Exact rule IDs and reasons match expectations

## Troubleshooting

### "Employee not found"
- Check: employee_id exists in data/employees.csv
- Verify: CSV file is properly formatted

### "No business rules found"
- Check: data/rules.csv exists and has content
- Verify: CSV has headers and at least one rule row

### "503 Service Unavailable" (when using Gemini)
- **Cause**: Gemini API is temporarily unavailable
- **Solution**: Use mock client instead (`validation_client_mock.py`)
- **Retry**: Wait a few minutes and try again

### Unexpected validation result
- Check: `changed_fields` in response (which fields were evaluated?)
- Verify: `previous_row` accurately reflects current CSV state
- Review: All applicable rules in data/rules.csv

## Performance Notes

- **Schema loading**: ~100ms (happens once on startup)
- **Rule loading**: ~50ms (happens once on startup)
- **Rule evaluation**: 10-100ms per operation (mock)
- **Full compilation** (with Gemini): 1-5 seconds

## Security Notes

- CSV files are read-only from this system (no writes)
- All validation is deterministic and traceable
- Rule changes audit trail: maintain version control on data/rules.csv
- API: Implement authentication if exposed to network

## Next Steps

1. **Test with your data**: Modify CSV files with real employee data
2. **Integrate with your system**: Use REST API or Python client
3. **Customize rules**: Edit data/rules.csv for your business logic
4. **Monitor decisions**: Log all validation results for audit trail
5. **Deploy**: Use Docker or cloud deployment for production

## Support

For issues or questions:
1. Check AGENT_INSTRUCTIONS.md for detailed specifications
2. Review QUICK_START.md for common scenarios
3. Run test_validation_mock.py to verify setup
4. Check data/*.csv for schema accuracy
