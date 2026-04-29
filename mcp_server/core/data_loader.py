"""
mcp_server/core/data_loader.py
-------------------------------
Responsible for loading CSV files from disk and building the text
representations that are injected into the Gemini prompt.

No business logic here — pure I/O.
"""

import csv
import io
import logging
from pathlib import Path
from typing import Any

from config import settings
from mcp_server.models import TableInfo, RuleRow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Table loading
# ---------------------------------------------------------------------------

def load_table_text(path: Path) -> str:
    """Return raw CSV text of a single file."""
    return path.read_text(encoding="utf-8").strip()


def load_all_tables_text() -> str:
    """
    Read every *.csv from TABLES_DIR and concatenate them as:
        TABLE:<name>
        <csv content>

    Returns an empty string if the directory doesn't exist or has no CSVs.
    """
    tables_path = settings.tables_path
    if not tables_path.exists():
        logger.warning("Tables directory not found: %s", tables_path)
        return ""

    blocks: list[str] = []
    for csv_file in sorted(tables_path.glob("*.csv")):
        content = load_table_text(csv_file)
        blocks.append(f"TABLE:{csv_file.stem}\n{content}")
        logger.debug("Loaded table: %s (%d bytes)", csv_file.stem, len(content))

    if not blocks:
        logger.warning("No CSV files found in %s", tables_path)
    return "\n\n".join(blocks)


def get_table_info(table_name: str) -> TableInfo | None:
    """Return TableInfo for a named table, or None if not found."""
    path = settings.tables_path / f"{table_name}.csv"
    if not path.exists():
        return None

    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))
    if not rows:
        return TableInfo(name=table_name, columns=[], row_count=0, sample_rows=[])

    return TableInfo(
        name=table_name,
        columns=list(rows[0].keys()),
        row_count=len(rows),
        sample_rows=rows[:5],
    )


def list_table_names() -> list[str]:
    """Return sorted list of available table names (without .csv extension)."""
    if not settings.tables_path.exists():
        return []
    return sorted(p.stem for p in settings.tables_path.glob("*.csv"))


def save_table_csv(filename: str, content: bytes) -> str:
    """Persist uploaded CSV to the tables directory. Returns table name."""
    settings.tables_path.mkdir(parents=True, exist_ok=True)
    dest = settings.tables_path / filename
    dest.write_bytes(content)
    logger.info("Saved table: %s", dest)
    return Path(filename).stem


# ---------------------------------------------------------------------------
# Rules loading
# ---------------------------------------------------------------------------

def load_rules_text() -> str:
    """Return raw rules CSV text."""
    if not settings.rules_path.exists():
        logger.warning("Rules file not found: %s", settings.rules_path)
        return ""
    return settings.rules_path.read_text(encoding="utf-8").strip()


def load_rules_list() -> list[RuleRow]:
    """Return parsed rules as a list of RuleRow objects."""
    text = load_rules_text()
    if not text:
        return []
    reader = csv.DictReader(io.StringIO(text))
    rules: list[RuleRow] = []
    for row in reader:
        try:
            rules.append(RuleRow(**{k.strip(): v.strip() for k, v in row.items()}))
        except Exception as exc:
            logger.warning("Skipping malformed rule row %s: %s", row, exc)
    return rules


def save_rules_csv(content: bytes) -> int:
    """Persist uploaded rules CSV. Returns number of rules parsed."""
    settings.rules_path.parent.mkdir(parents=True, exist_ok=True)
    settings.rules_path.write_bytes(content)
    logger.info("Saved rules file: %s", settings.rules_path)
    reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
    return sum(1 for _ in reader)


# ---------------------------------------------------------------------------
# Field diff helper
# ---------------------------------------------------------------------------

def infer_changed_fields(
    target_row: dict[str, Any],
    previous_row: dict[str, Any] | None,
) -> list[str]:
    """
    Return the list of field names whose values differ between
    target_row and previous_row.

    For INSERT (previous_row=None) every field is considered 'changed'.
    """
    if previous_row is None:
        return list(target_row.keys())

    return [
        field
        for field in target_row
        if str(target_row.get(field)) != str(previous_row.get(field))
    ]