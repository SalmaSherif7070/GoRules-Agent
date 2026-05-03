#!/usr/bin/env python
"""
validation_client_mock.py
--------------------------
Client library for validation requests (mock version - no API calls).

This version uses simulated rule checking to demonstrate the system
without depending on Gemini API availability.

Run: python validation_client_mock.py
"""

import json
from typing import Any, Optional
from pathlib import Path
import csv

from mcp_server.core.data_loader import (
    load_rules_list,
    get_table_info,
    infer_changed_fields,
)


class MockRulesCompilerClient:
    """High-level client for the GoRules Compiler validation system (mock)."""
    
    def __init__(self):
        """Initialize the client and load rules."""
        self.rules = load_rules_list()
        self.rules_list = [
            f"{r.rule_id}. {r.category}: {r.rule_description}"
            for r in self.rules
        ]
    
    def get_row_from_table(self, table_name: str, key_field: str, key_value: Any) -> Optional[dict]:
        """Fetch a row from a CSV table by key."""
        csv_path = Path("data") / f"{table_name}.csv"
        if not csv_path.exists():
            return None
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get(key_field) == str(key_value):
                    return row
        return None
    
    def validate_salary_increase(
        self,
        employee_id: int,
        new_salary: float,
        old_salary: Optional[float] = None,
    ) -> dict:
        """
        Validate a salary increase for an employee (mock version).
        
        Args:
            employee_id: Employee ID
            new_salary: Proposed new salary
            old_salary: Current salary (fetched if not provided)
        
        Returns:
            Validation result
        """
        # Fetch current employee data
        emp_row = self.get_row_from_table("employees", "employee_id", employee_id)
        if not emp_row:
            return {
                "operation_valid": False,
                "error": f"Employee {employee_id} not found",
                "rules_evaluated": len(self.rules_list),
            }
        
        # Use old salary from CSV if not provided
        if old_salary is None:
            old_salary = float(emp_row.get("salary", 0))
        
        # Calculate increase percentage
        increase_pct = ((new_salary - old_salary) / old_salary * 100) if old_salary > 0 else 0
        
        # Check rules
        violated_rules = []
        
        # Rule 1: Salary increase cannot exceed 20%
        if increase_pct > 20:
            violated_rules.append({
                "rule_id": "1",
                "reason": f"Salary increase ({increase_pct:.1f}%) exceeds maximum 20% of previous salary ({old_salary} → {new_salary})"
            })
        
        # Rule 3: Salary must be >= 3000
        if new_salary < 3000:
            violated_rules.append({
                "rule_id": "3",
                "reason": f"Salary {new_salary} is below minimum 3000"
            })
        
        # Rule 2: Employee salary cannot exceed manager salary
        # (Skip for now as we'd need manager lookup)
        
        result = {
            "operation_valid": len(violated_rules) == 0,
            "violated_rules": violated_rules,
            "changed_fields": ["salary"],
            "rules_evaluated": len(self.rules_list),
            "summary": {
                "employee_id": employee_id,
                "old_salary": old_salary,
                "new_salary": new_salary,
                "increase_percent": increase_pct,
                "max_allowed": old_salary * 1.20,
            }
        }
        
        return result
    
    def validate_leave_request(
        self,
        employee_id: int,
        days_requested: int,
        leave_type: str = "annual",
    ) -> dict:
        """Validate a leave request (mock version)."""
        emp_row = self.get_row_from_table("employees", "employee_id", employee_id)
        if not emp_row:
            return {
                "operation_valid": False,
                "error": f"Employee {employee_id} not found",
                "rules_evaluated": len(self.rules_list),
            }
        
        current_balance = int(emp_row.get("leave_balance", 0))
        violated_rules = []
        
        # Rule 14: Annual leave request cannot exceed leave balance
        if days_requested > current_balance:
            violated_rules.append({
                "rule_id": "14",
                "reason": f"Leave request ({days_requested} days) exceeds balance ({current_balance} days)"
            })
        
        # Rule 15: Sick leave cannot exceed 14 consecutive days
        if leave_type == "sick" and days_requested > 14:
            violated_rules.append({
                "rule_id": "15",
                "reason": f"Sick leave request ({days_requested} days) exceeds maximum 14 consecutive days"
            })
        
        result = {
            "operation_valid": len(violated_rules) == 0,
            "violated_rules": violated_rules,
            "changed_fields": ["leave_balance"],
            "rules_evaluated": len(self.rules_list),
            "summary": {
                "employee_id": employee_id,
                "leave_type": leave_type,
                "days_requested": days_requested,
                "current_balance": current_balance,
                "new_balance": current_balance - days_requested,
            }
        }
        
        return result
    
    def validate_bonus_award(
        self,
        employee_id: int,
        bonus_amount: float,
    ) -> dict:
        """Validate awarding a bonus to an employee (mock version)."""
        emp_row = self.get_row_from_table("employees", "employee_id", employee_id)
        if not emp_row:
            return {
                "operation_valid": False,
                "error": f"Employee {employee_id} not found",
                "rules_evaluated": len(self.rules_list),
            }
        
        salary = float(emp_row.get("salary", 0))
        rating = int(emp_row.get("performance_rating", 0))
        
        violated_rules = []
        
        # Rule 5: Bonus cannot exceed 15% of annual salary
        max_bonus = salary * 0.15
        if bonus_amount > max_bonus:
            violated_rules.append({
                "rule_id": "5",
                "reason": f"Bonus amount ({bonus_amount}) exceeds maximum 15% of salary ({max_bonus:.0f})"
            })
        
        # Rule 20: Employees with rating below 2 cannot receive bonus
        if rating < 2:
            violated_rules.append({
                "rule_id": "20",
                "reason": f"Employee with rating {rating} (below 2) cannot receive bonus"
            })
        
        result = {
            "operation_valid": len(violated_rules) == 0,
            "violated_rules": violated_rules,
            "changed_fields": ["bonus_amount"],
            "rules_evaluated": len(self.rules_list),
            "summary": {
                "employee_id": employee_id,
                "employee_rating": rating,
                "salary": salary,
                "bonus_amount": bonus_amount,
                "max_allowed": max_bonus,
                "pct_of_salary": (bonus_amount / salary * 100) if salary > 0 else 0,
            }
        }
        
        return result
    
    def print_result(self, result: dict, title: str = "Validation Result"):
        """Pretty-print a validation result."""
        print(f"\n{'='*80}")
        print(f"{title}")
        print(f"{'='*80}")
        
        if "error" in result:
            print(f"❌ ERROR: {result['error']}")
            return
        
        # Decision
        decision = "✓ VALID" if result.get("operation_valid") else "✗ INVALID"
        print(f"\nDECISION: {decision}")
        
        # Summary
        if "summary" in result:
            print(f"\nSUMMARY:")
            for key, value in result["summary"].items():
                if isinstance(value, float):
                    print(f"  {key}: {value:.2f}")
                else:
                    print(f"  {key}: {value}")
        
        # Rules evaluated
        print(f"\nRules evaluated: {result.get('rules_evaluated', 0)}")
        
        # Changed fields
        if result.get("changed_fields"):
            print(f"Changed fields: {', '.join(result.get('changed_fields', []))}")
        
        # Violations
        if result.get("violated_rules"):
            print(f"\n⚠️  VIOLATED RULES ({len(result['violated_rules'])}):")
            for violation in result.get("violated_rules", []):
                rule_id = violation.get("rule_id", "?")
                reason = violation.get("reason", "Unknown")
                print(f"  Rule {rule_id}: {reason}")
        else:
            if result.get("operation_valid"):
                print(f"\n✓ All rules passed!")
        
        print(f"{'='*80}\n")


def main():
    """Example usage of the validation client."""
    client = MockRulesCompilerClient()
    
    print("\n" + "="*80)
    print("GORULES COMPILER CLIENT - REAL-WORLD EXAMPLES")
    print("="*80)
    
    # Example 1: Valid salary increase (15%)
    print("\n📊 SCENARIO 1: Salary Increase within limits")
    result = client.validate_salary_increase(
        employee_id=4,
        new_salary=8050,
        old_salary=7000,
    )
    client.print_result(result, "Employee 4 Salary: 7000 → 8050 (+15%)")
    
    # Example 2: Invalid salary increase (21.4%)
    print("\n📊 SCENARIO 2: Salary Increase exceeds 20% limit")
    result = client.validate_salary_increase(
        employee_id=4,
        new_salary=8500,
        old_salary=7000,
    )
    client.print_result(result, "Employee 4 Salary: 7000 → 8500 (+21.4%)")
    
    # Example 3: Valid leave request
    print("\n📊 SCENARIO 3: Leave Request within balance")
    result = client.validate_leave_request(
        employee_id=4,
        days_requested=5,
        leave_type="annual",
    )
    client.print_result(result, "Employee 4 Leave Request: 5 days (balance: 8)")
    
    # Example 4: Invalid leave request (exceeds balance)
    print("\n📊 SCENARIO 4: Leave Request exceeds balance")
    result = client.validate_leave_request(
        employee_id=4,
        days_requested=10,
        leave_type="annual",
    )
    client.print_result(result, "Employee 4 Leave Request: 10 days (balance: 8)")
    
    # Example 5: Valid bonus award
    print("\n📊 SCENARIO 5: Bonus award within limits")
    result = client.validate_bonus_award(
        employee_id=2,  # Manager_A: rating 4, salary 10000
        bonus_amount=1200,  # 12% of salary
    )
    client.print_result(result, "Employee 2 Bonus: 1200 (12% of 10000)")
    
    # Example 6: Invalid bonus (exceeds 15% limit)
    print("\n📊 SCENARIO 6: Bonus exceeds 15% of salary")
    result = client.validate_bonus_award(
        employee_id=2,  # Manager_A: salary 10000
        bonus_amount=2000,  # 20% of salary
    )
    client.print_result(result, "Employee 2 Bonus: 2000 (20% of 10000)")
    
    # Example 7: Invalid bonus for low-rating employee
    print("\n📊 SCENARIO 7: Bonus for low-rating employee")
    result = client.validate_bonus_award(
        employee_id=7,  # Emp_4: rating 1, salary 5500
        bonus_amount=500,
    )
    client.print_result(result, "Employee 7 Bonus: 500 (rating too low)")
    
    # Summary table
    print("\n" + "="*80)
    print("SCENARIO SUMMARY")
    print("="*80)
    scenarios = [
        ("Salary +15% (within limit)", "✓ VALID"),
        ("Salary +21.4% (exceeds limit)", "✗ INVALID"),
        ("Leave 5 days (has 8 balance)", "✓ VALID"),
        ("Leave 10 days (has 8 balance)", "✗ INVALID"),
        ("Bonus 12% of salary", "✓ VALID"),
        ("Bonus 20% of salary", "✗ INVALID"),
        ("Bonus to rating=1 employee", "✗ INVALID"),
    ]
    
    for scenario, result in scenarios:
        print(f"  {result:10s} | {scenario}")
    
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
