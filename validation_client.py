#!/usr/bin/env python
"""
validation_client.py
--------------------
Client library for making validation requests to the GoRules Compiler Agent.

Usage:
  from validation_client import RulesCompilerClient
  
  client = RulesCompilerClient()
  
  # Validate a salary increase
  result = client.validate_salary_increase(
      employee_id=4,
      new_salary=8500,
      old_salary=7000,
  )
  print(result)
"""

import json
from typing import Any, Optional
from pathlib import Path
import csv
import io

from mcp_server.core.data_loader import (
    load_rules_list,
    get_table_info,
    infer_changed_fields,
)


class RulesCompilerClient:
    """High-level client for the GoRules Compiler validation system."""
    
    def __init__(self):
        """Initialize the client and load rules."""
        self.rules = load_rules_list()
        self.rules_list = [
            f"{r.rule_id}. {r.category}: {r.rule_description}"
            for r in self.rules
        ]
    
    def get_row_from_table(self, table_name: str, key_field: str, key_value: Any) -> Optional[dict]:
        """Fetch a row from a CSV table by key."""
        info = get_table_info(table_name)
        if not info or not info.sample_rows:
            return None
        
        # Read full table
        csv_path = Path("data") / f"{table_name}.csv"
        if not csv_path.exists():
            return None
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get(key_field) == str(key_value):
                    return row
        return None
    
    def validate_operation(
        self,
        operation: str,
        target_table: str,
        target_row: dict[str, Any],
        previous_row: Optional[dict[str, Any]] = None,
        related_context: Optional[dict[str, Any]] = None,
    ) -> dict:
        """
        Validate a data operation against business rules.
        
        Args:
            operation: "INSERT" or "UPDATE"
            target_table: Name of table being modified
            target_row: New/inserted row values
            previous_row: Existing row before UPDATE
            related_context: Pre-fetched lookups/aggregates
        
        Returns:
            Validation result with decision and violations
        """
        from mcp_server.core.gemini_compiler import compile_and_validate
        
        try:
            result = compile_and_validate(
                operation=operation,
                target_table=target_table,
                target_row=target_row,
                previous_row=previous_row,
                related_context=related_context,
                rules=self.rules_list,
            )
            return result.model_dump()
        except Exception as e:
            return {
                "operation_valid": False,
                "error": str(e),
                "rules_evaluated": len(self.rules_list),
            }
    
    def validate_salary_increase(
        self,
        employee_id: int,
        new_salary: float,
        old_salary: Optional[float] = None,
    ) -> dict:
        """
        Validate a salary increase for an employee.
        
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
            return {"error": f"Employee {employee_id} not found"}
        
        # Use old salary from CSV if not provided
        if old_salary is None:
            old_salary = float(emp_row.get("salary", 0))
        
        # Build target and previous rows
        target_row = emp_row.copy()
        target_row["salary"] = new_salary
        
        previous_row = emp_row.copy()
        previous_row["salary"] = old_salary
        
        # Validate
        result = self.validate_operation(
            operation="UPDATE",
            target_table="employees",
            target_row=target_row,
            previous_row=previous_row,
        )
        
        # Add human-readable summary
        result["summary"] = {
            "employee_id": employee_id,
            "old_salary": old_salary,
            "new_salary": new_salary,
            "increase_percent": ((new_salary - old_salary) / old_salary * 100) if old_salary > 0 else 0,
            "max_allowed": old_salary * 1.20,
        }
        
        return result
    
    def validate_leave_request(
        self,
        employee_id: int,
        days_requested: int,
        leave_type: str = "annual",
    ) -> dict:
        """
        Validate a leave request.
        
        Args:
            employee_id: Employee ID
            days_requested: Number of days requested
            leave_type: "annual" or "sick"
        
        Returns:
            Validation result
        """
        # Fetch current employee data
        emp_row = self.get_row_from_table("employees", "employee_id", employee_id)
        if not emp_row:
            return {"error": f"Employee {employee_id} not found"}
        
        # Build target row with updated leave balance
        target_row = emp_row.copy()
        current_balance = int(emp_row.get("leave_balance", 0))
        target_row["leave_balance"] = current_balance - days_requested
        
        # Validate
        result = self.validate_operation(
            operation="UPDATE",
            target_table="employees",
            target_row=target_row,
            previous_row=emp_row,
        )
        
        # Add human-readable summary
        result["summary"] = {
            "employee_id": employee_id,
            "leave_type": leave_type,
            "days_requested": days_requested,
            "current_balance": current_balance,
            "new_balance": current_balance - days_requested,
        }
        
        return result
    
    def validate_bonus_award(
        self,
        employee_id: int,
        bonus_amount: float,
    ) -> dict:
        """
        Validate awarding a bonus to an employee.
        
        Args:
            employee_id: Employee ID
            bonus_amount: Bonus amount to award
        
        Returns:
            Validation result
        """
        # Fetch current employee data
        emp_row = self.get_row_from_table("employees", "employee_id", employee_id)
        if not emp_row:
            return {"error": f"Employee {employee_id} not found"}
        
        salary = float(emp_row.get("salary", 0))
        rating = int(emp_row.get("performance_rating", 0))
        
        # Build bonus row
        bonus_row = {
            "bonus_id": "new",
            "employee_id": employee_id,
            "bonus_amount": bonus_amount,
        }
        
        # Validate against bonus rules
        result = self.validate_operation(
            operation="INSERT",
            target_table="bonuses",
            target_row=bonus_row,
            related_context={
                "employee_salary": salary,
                "employee_rating": rating,
                "max_bonus": salary * 0.15,
            },
        )
        
        # Add human-readable summary
        result["summary"] = {
            "employee_id": employee_id,
            "employee_rating": rating,
            "salary": salary,
            "bonus_amount": bonus_amount,
            "max_allowed": salary * 0.15,
            "pct_of_salary": (bonus_amount / salary * 100) if salary > 0 else 0,
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
            print(f"\n⚠️  VIOLATED RULES:")
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
    client = RulesCompilerClient()
    
    print("\n" + "="*80)
    print("GORULES COMPILER CLIENT - EXAMPLES")
    print("="*80)
    
    # Example 1: Valid salary increase (15%)
    print("\n📊 Example 1: Valid Salary Increase (15%)")
    result = client.validate_salary_increase(
        employee_id=4,
        new_salary=8050,
        old_salary=7000,
    )
    client.print_result(result, "Salary Increase - 15% (should be VALID)")
    
    # Example 2: Invalid salary increase (21.4%)
    print("\n📊 Example 2: Invalid Salary Increase (21.4%)")
    result = client.validate_salary_increase(
        employee_id=4,
        new_salary=8500,
        old_salary=7000,
    )
    client.print_result(result, "Salary Increase - 21.4% (should be INVALID)")
    
    # Example 3: Leave request
    print("\n📊 Example 3: Leave Request Validation")
    result = client.validate_leave_request(
        employee_id=4,
        days_requested=5,
        leave_type="annual",
    )
    client.print_result(result, "Leave Request - 5 days (employee has 8)")
    
    # Example 4: Bonus award
    print("\n📊 Example 4: Bonus Award Validation")
    result = client.validate_bonus_award(
        employee_id=2,  # Manager_A with rating 4, salary 10000
        bonus_amount=1200,  # 12% of salary
    )
    client.print_result(result, "Bonus Award - 1200 (12% of 10000)")
    
    # Example 5: Bonus for low-rating employee
    print("\n📊 Example 5: Bonus for Low-Rating Employee")
    result = client.validate_bonus_award(
        employee_id=7,  # Emp_4 with rating 1, salary 5500
        bonus_amount=500,
    )
    client.print_result(result, "Bonus Award - Low Rating (should be INVALID)")


if __name__ == "__main__":
    main()
