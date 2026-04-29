"""
tests/test_data_loader.py
--------------------------
Unit tests for the data_loader module.
No network calls — runs fully offline.
"""

import csv
import io
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from mcp_server.core.data_loader import infer_changed_fields


# ---------------------------------------------------------------------------
# infer_changed_fields
# ---------------------------------------------------------------------------

class TestInferChangedFields:
    def test_no_previous_row_returns_all_fields(self):
        target = {"salary": 8500, "name": "Emp_1", "dept": 1}
        result = infer_changed_fields(target, None)
        assert set(result) == {"salary", "name", "dept"}

    def test_unchanged_row_returns_empty(self):
        row = {"salary": 7000, "name": "Emp_1"}
        assert infer_changed_fields(row, row.copy()) == []

    def test_detects_single_change(self):
        target = {"salary": 8500, "name": "Emp_1"}
        prev   = {"salary": 7000, "name": "Emp_1"}
        assert infer_changed_fields(target, prev) == ["salary"]

    def test_detects_multiple_changes(self):
        target = {"salary": 8500, "name": "Emp_New", "dept": 2}
        prev   = {"salary": 7000, "name": "Emp_1",   "dept": 1}
        changed = set(infer_changed_fields(target, prev))
        assert changed == {"salary", "name", "dept"}

    def test_type_coercion_string_vs_int(self):
        # target has int, prev has str representation of same value
        target = {"salary": 7000}
        prev   = {"salary": "7000"}
        assert infer_changed_fields(target, prev) == []

    def test_new_field_in_target_detected(self):
        target = {"salary": 7000, "bonus": 500}
        prev   = {"salary": 7000}
        assert "bonus" in infer_changed_fields(target, prev)