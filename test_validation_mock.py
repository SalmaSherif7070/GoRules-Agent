#!/usr/bin/env python
"""
test_validation_mock.py
------------------------
Test the validation workflow using mock Gemini responses (no API calls).

This demonstrates the system logic without depending on Gemini API availability.

Run: python test_validation_mock.py
"""

import json
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from mcp_server.core.data_loader import load_rules_list, get_table_info, infer_changed_fields
from mcp_server.models import ValidationResult, ViolatedRule


def mock_evaluate_rules(
    operation: str,
    target_table: str,
    target_row: dict,
    previous_row: dict | None,
    rules: list[str],
) -> ValidationResult:
    """
    Mock rule evaluation without calling Gemini API.
    
    This demonstrates the expected output format and business logic.
    """
    changed_fields = infer_changed_fields(target_row, previous_row)
    violated = []
    
    # Example: Check salary rules
    if target_table == "employees":
        # Rule 1: Salary increase cannot exceed 20%
        if "salary" in changed_fields and previous_row:
            old_salary = float(previous_row.get("salary", 0))
            new_salary = float(target_row.get("salary", 0))
            if old_salary > 0:
                increase_pct = (new_salary - old_salary) / old_salary * 100
                if increase_pct > 20:
                    violated.append(
                        ViolatedRule(
                            rule_id="1",
                            reason=f"Salary increase ({increase_pct:.1f}%) exceeds maximum 20% of previous salary ({old_salary} → {new_salary})"
                        )
                    )
        
        # Rule 3: Salary must be >= 3000
        if "salary" in changed_fields:
            salary = float(target_row.get("salary", 0))
            if salary < 3000:
                violated.append(
                    ViolatedRule(
                        rule_id="3",
                        reason=f"Salary {salary} is below minimum 3000"
                    )
                )
    
    return ValidationResult(
        operation_valid=len(violated) == 0,
        violated_rules=violated,
        gorules_code="",
        execution_dependencies=[],
        changed_fields=changed_fields,
        rules_evaluated=len(rules),
    )


def test_salary_increase_21_percent():
    """Test INVALID case: Salary increase exceeds 20% limit."""
    print("\n" + "="*80)
    print("TEST 1: Salary increase of 21.4% (exceeds 20% limit)")
    print("="*80)
    
    # Load rules
    rules_list = load_rules_list()
    rules = [f"{r.rule_id}. {r.category}: {r.rule_description}" for r in rules_list]
    
    print(f"\n✓ Loaded {len(rules)} business rules")
    
    # Prepare data
    target_row = {
        "employee_id": "4",
        "name": "Emp_1",
        "department_id": "1",
        "manager_id": "2",
        "salary": 8500,  # New salary
        "previous_salary": 7000,
        "leave_balance": "8",
        "performance_rating": "3"
    }
    
    previous_row = {
        "employee_id": "4",
        "name": "Emp_1",
        "department_id": "1",
        "manager_id": "2",
        "salary": 7000,  # Old salary
        "previous_salary": 6500,
        "leave_balance": "8",
        "performance_rating": "3"
    }
    
    print(f"\nTarget row (new salary): {target_row['salary']}")
    print(f"Previous row (old salary): {previous_row['salary']}")
    print(f"Increase: {((target_row['salary'] - previous_row['salary']) / previous_row['salary'] * 100):.1f}%")
    
    result = mock_evaluate_rules(
        operation="UPDATE",
        target_table="employees",
        target_row=target_row,
        previous_row=previous_row,
        rules=rules,
    )
    
    print(f"\n{'='*80}")
    print(f"DECISION: {'✓ VALID' if result.operation_valid else '✗ INVALID'}")
    print(f"{'='*80}")
    print(f"Rules evaluated: {result.rules_evaluated}")
    print(f"Changed fields: {result.changed_fields}")
    
    if result.violated_rules:
        print(f"\n⚠️  VIOLATED RULES ({len(result.violated_rules)}):")
        for violation in result.violated_rules:
            print(f"  Rule {violation.rule_id}: {violation.reason}")
    else:
        print("\n✓ All rules passed!")
        
    return result


def test_salary_increase_15_percent():
    """Test VALID case: Salary increase of 15% (within 20% limit)."""
    print("\n" + "="*80)
    print("TEST 2: Salary increase of 15% (within 20% limit)")
    print("="*80)
    
    # Load rules
    rules_list = load_rules_list()
    rules = [f"{r.rule_id}. {r.category}: {r.rule_description}" for r in rules_list]
    
    # Prepare data
    target_row = {
        "employee_id": "4",
        "name": "Emp_1",
        "department_id": "1",
        "manager_id": "2",
        "salary": 8050,  # 15% increase
        "previous_salary": 7000,
        "leave_balance": "8",
        "performance_rating": "3"
    }
    
    previous_row = {
        "employee_id": "4",
        "name": "Emp_1",
        "department_id": "1",
        "manager_id": "2",
        "salary": 7000,
        "previous_salary": 6500,
        "leave_balance": "8",
        "performance_rating": "3"
    }
    
    print(f"\nTarget row (new salary): {target_row['salary']}")
    print(f"Previous row (old salary): {previous_row['salary']}")
    print(f"Increase: {((target_row['salary'] - previous_row['salary']) / previous_row['salary'] * 100):.1f}%")
    
    result = mock_evaluate_rules(
        operation="UPDATE",
        target_table="employees",
        target_row=target_row,
        previous_row=previous_row,
        rules=rules,
    )
    
    print(f"\n{'='*80}")
    print(f"DECISION: {'✓ VALID' if result.operation_valid else '✗ INVALID'}")
    print(f"{'='*80}")
    print(f"Rules evaluated: {result.rules_evaluated}")
    print(f"Changed fields: {result.changed_fields}")
    
    if result.violated_rules:
        print(f"\n⚠️  VIOLATED RULES ({len(result.violated_rules)}):")
        for violation in result.violated_rules:
            print(f"  Rule {violation.rule_id}: {violation.reason}")
    else:
        print("\n✓ All rules passed!")
        
    return result


def test_salary_below_minimum():
    """Test INVALID case: Salary below 3000 minimum."""
    print("\n" + "="*80)
    print("TEST 3: Salary below 3000 minimum")
    print("="*80)
    
    # Load rules
    rules_list = load_rules_list()
    rules = [f"{r.rule_id}. {r.category}: {r.rule_description}" for r in rules_list]
    
    # Prepare data
    target_row = {
        "employee_id": "8",
        "name": "Emp_5",
        "department_id": "2",
        "manager_id": "3",
        "salary": 2500,  # Below 3000 minimum
        "previous_salary": 4500,
        "leave_balance": "10",
        "performance_rating": "3"
    }
    
    previous_row = {
        "employee_id": "8",
        "name": "Emp_5",
        "department_id": "2",
        "manager_id": "3",
        "salary": 4500,
        "previous_salary": 4000,
        "leave_balance": "10",
        "performance_rating": "3"
    }
    
    print(f"\nTarget row (new salary): {target_row['salary']}")
    print(f"Previous row (old salary): {previous_row['salary']}")
    
    result = mock_evaluate_rules(
        operation="UPDATE",
        target_table="employees",
        target_row=target_row,
        previous_row=previous_row,
        rules=rules,
    )
    
    print(f"\n{'='*80}")
    print(f"DECISION: {'✓ VALID' if result.operation_valid else '✗ INVALID'}")
    print(f"{'='*80}")
    print(f"Rules evaluated: {result.rules_evaluated}")
    print(f"Changed fields: {result.changed_fields}")
    
    if result.violated_rules:
        print(f"\n⚠️  VIOLATED RULES ({len(result.violated_rules)}):")
        for violation in result.violated_rules:
            print(f"  Rule {violation.rule_id}: {violation.reason}")
    else:
        print("\n✓ All rules passed!")
        
    return result


def inspect_tables():
    """Display available tables and sample data."""
    print("\n" + "="*80)
    print("AVAILABLE TABLES")
    print("="*80)
    
    table_names = [
        "employees", "departments", "projects", 
        "project_assignments", "leave_requests", "bonuses", "attendance"
    ]
    
    for table_name in table_names:
        info = get_table_info(table_name)
        if info:
            print(f"\n📊 {info.name.upper()}")
            print(f"   Columns: {', '.join(info.columns)}")
            print(f"   Total rows: {info.row_count}")
            if info.sample_rows:
                print(f"   Sample: {info.sample_rows[0]}")


if __name__ == "__main__":
    print("\n" + "="*80)
    print("GORULES VALIDATION SYSTEM - MOCK TEST SUITE")
    print("(No Gemini API calls - demonstrates system logic)")
    print("="*80)
    
    # Inspect available data
    inspect_tables()
    
    # Run tests
    result1 = test_salary_increase_21_percent()
    result2 = test_salary_increase_15_percent()
    result3 = test_salary_below_minimum()
    
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Test 1 (21% increase - should be INVALID): {'✓ PASSED' if not result1.operation_valid else '✗ FAILED'}")
    print(f"Test 2 (15% increase - should be VALID):   {'✓ PASSED' if result2.operation_valid else '✗ FAILED'}")
    print(f"Test 3 (<3000 salary - should be INVALID): {'✓ PASSED' if not result3.operation_valid else '✗ FAILED'}")
    print("="*80 + "\n")
