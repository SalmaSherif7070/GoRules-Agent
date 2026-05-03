# GoRules Compiler - Quick Start Guide

## What This System Does

This system validates business data modifications against 20 predefined business rules. It uses AI to:
1. Understand natural language requests (e.g., "Increase employee 4 salary")
2. Compile rules into executable GoRules format
3. Check if the modification violates any rule
4. Report VALID or INVALID with detailed explanations

## Example Requests

### ✅ Valid Requests (Should Pass)

**Request 1**: Update salary by 15% (within 20% limit)
```
"Increase employee 4 salary from 7000 to 8050"
→ VALID ✓
(8050 - 7000) / 7000 = 15% < 20% limit
```

**Request 2**: Add a bonus within 15% of salary
```
"Add bonus of 900 for employee 2 with salary 10000"
→ VALID ✓
900 / 10000 = 9% < 15% limit
```

**Request 3**: Assign employee to 2nd project (≤3 limit)
```
"Add employee 4 to project 102"
→ VALID ✓ (currently has 2 projects, this makes 3)
```

### ❌ Invalid Requests (Should Fail)

**Request 1**: Exceed 20% salary increase limit
```
"Increase employee 4 salary from 7000 to 8500"
→ INVALID ❌
(8500 - 7000) / 7000 = 21.4% > 20% limit
Violation: Rule 1 - Salary increase cannot exceed 20%
```

**Request 2**: Salary exceeds manager's salary
```
"Update employee 4 salary to 11000 (manager earns 10000)"
→ INVALID ❌
Violation: Rule 2 - Employee salary cannot exceed manager salary
```

**Request 3**: Bonus exceeds 15% of salary
```
"Add bonus of 2000 for employee 2 with salary 10000"
→ INVALID ❌
2000 / 10000 = 20% > 15% limit
Violation: Rule 5 - Bonus cannot exceed 15% of salary
```

**Request 4**: Employee with low rating cannot get bonus
```
"Add bonus for employee 7 (rating=1)"
→ INVALID ❌
Violation: Rule 20 - Employees with rating < 2 cannot receive bonus
```

**Request 5**: Exceeds manager's supervision limit
```
"Assign new employee to manager who already supervises 10"
→ INVALID ❌
Violation: Rule 9 - Manager can supervise at most 10 employees
```

**Request 6**: Leave request exceeds balance
```
"Employee 4 requests 10 days leave (balance=8)"
→ INVALID ❌
Violation: Rule 14 - Annual leave cannot exceed balance
```

**Request 7**: Project timeline invalid
```
"Create project with start=2026-06-30, end=2026-01-01"
→ INVALID ❌
Violation: Rule 18 - End date must be after start date
```

## How to Use

### Step 1: Describe What You Want to Change

Use natural language, e.g.:
- "Increase employee 4 salary to 8500"
- "Add a new employee in Engineering"
- "Update employee 5 leave balance to 3"
- "Assign employee 4 to project 102"

### Step 2: Agent Validates

The system will:
1. Load your current data from CSV files
2. Identify what table and row you're modifying
3. Load all 20 business rules
4. Check if the change violates any rule
5. Report the decision

### Step 3: Receive Validation Result

Example response for salary increase:
```
OPERATION: UPDATE employees
TARGET: employee_id=4
DECISION: INVALID ❌

VIOLATED RULES:
  Rule 1 (Salary): Salary increase cannot exceed 20%
    - Current salary: 7000
    - Proposed salary: 8500
    - Increase: 21.4%
    - Maximum allowed: 20% = 8400

RECOMMENDATION: Reduce new salary to ≤ 8400
```

## Current Data Summary

### Tables Loaded
- **employees** (8 records) — salary, department, manager, leave balance, rating
- **departments** (2) — budget allocation and usage
- **projects** (3) — timeline and budget
- **project_assignments** (6) — active project assignments
- **leave_requests** (4) — pending leave requests
- **bonuses** (4) — approved bonuses
- **attendance** (5) — daily attendance logs

### Sample Data
**Employees**:
- 1: CEO (Eng, salary=15000)
- 2: Manager_A (Eng, salary=10000, reports to CEO)
- 3: Manager_B (Mkt, salary=9500, reports to CEO)
- 4-8: Individual contributors (salary 5000-7000)

## Rules Quick Reference

| # | Category | Rule | Impact |
|---|----------|------|--------|
| 1 | Salary | Max 20% increase | e.g., 7000 → max 8400 |
| 2 | Salary | ≤ manager salary | Emp must earn less than mgr |
| 3 | Salary | ≥ 3000 minimum | Lowest allowed salary |
| 4 | Budget | Usage ≤ allocated | Department spending limit |
| 5 | Bonus | ≤ 15% of salary | max bonus = salary × 0.15 |
| 6 | Employee | Must have department | dept_id required |
| 7 | Hierarchy | CEO exception only | All others need manager |
| 8 | Hierarchy | Same department as mgr | Emp and mgr in same dept |
| 9 | Hierarchy | Manager ≤ 10 direct | Supervision limit |
| 10 | Hierarchy | Not self-managed | Emp ≠ mgr_id |
| 11 | Attendance | ≤ 12 hours/day | Max working hours |
| 12 | Attendance | ≥ 5 days/week | Minimum work days |
| 13 | Leave | Balance ≥ 0 | No negative balances |
| 14 | Leave | Request ≤ balance | Can't exceed available |
| 15 | Leave | Sick ≤ 14 days | Consecutive limit |
| 16 | Project | ≤ 3 active | Max concurrent projects |
| 17 | Project | Spend ≤ budget | Project budget limit |
| 18 | Project | end > start | Valid timeline |
| 19 | Performance | 1-5 rating | Rating range |
| 20 | Bonus | Rating ≥ 2 for bonus | Low rating = no bonus |

## Common Scenarios

**Scenario A: Promotion**
- Employee 4 gets 10% raise (OK, < 20%)
- Moved to different department (check Rule 8 if manager changes)
- Bonus approved if rating ≥ 2 (Rule 20)

**Scenario B: New Hire**
- Department assigned (Rule 6)
- Manager assigned from same department (Rule 8)
- Salary ≥ 3000 (Rule 3)

**Scenario C: Leave Request**
- Cannot exceed balance (Rule 14)
- Sick leave ≤ 14 consecutive (Rule 15)

**Scenario D: Project Assignment**
- Current projects ≤ 2 (can add 1 more, Rule 16)
- Project has budget room (Rule 17)

## Troubleshooting

**"I think the result is wrong"**
→ Check the `changed_fields` in the response. Only fields listed were evaluated. Other fields weren't checked.

**"Why was a field not checked?"**
→ For UPDATE, only changed fields trigger rule evaluation. For INSERT, all fields are checked.

**"Can I modify the rules?"**
→ Yes! Edit `data/rules.csv` and the system will use new rules on next validation.

**"Can I update the CSV files?"**
→ Not directly through this system. This validates changes but doesn't apply them. You would need to manually update the CSV files or use a separate persistence layer.

## Contact

For questions about rules, data, or validation results, refer to the AGENT_INSTRUCTIONS.md file or the system logs.
