#!/usr/bin/env python
"""
test_validation.py
-------------------
Test the validation workflow with concrete examples.

Run: python test_validation.py
"""

import json
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from mcp_server.core.gemini_compiler import compile_and_validate
from mcp_server.core.data_loader import load_rules_list, get_table_info


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
    
    try:
        result = compile_and_validate(
            operation="UPDATE",
            target_table="employees",
            target_row=target_row,
            previous_row=previous_row,
            rules=rules,
        )
        
        print(f"\n{'='*80}")
        print(f"DECISION: {'VALID ✓' if result.operation_valid else 'INVALID ✗'}")
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
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None


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
    
    try:
        result = compile_and_validate(
            operation="UPDATE",
            target_table="employees",
            target_row=target_row,
            previous_row=previous_row,
            rules=rules,
        )
        
        print(f"\n{'='*80}")
        print(f"DECISION: {'VALID ✓' if result.operation_valid else 'INVALID ✗'}")
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
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None


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
    print("GORULES VALIDATION SYSTEM - TEST SUITE")
    print("="*80)
    
    # Inspect available data
    inspect_tables()
    
    # Run tests
    result1 = test_salary_increase_21_percent()
    result2 = test_salary_increase_15_percent()
    
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Test 1 (21% increase): {'✓ PASSED' if result1 and not result1.operation_valid else '✗ FAILED'}")
    print(f"Test 2 (15% increase): {'✓ PASSED' if result2 and result2.operation_valid else '✗ FAILED'}")
    print("="*80 + "\n")
