"""Database access: schema description, SQL validation, and safe read-only execution.

Safety is layered (defence in depth):
  1. validate_sql()   - static checks: one statement, SELECT/WITH only, no write keywords
  2. read-only URI    - the SQLite file is opened with mode=ro
  3. authorizer       - SQLite itself denies anything that is not a read
  4. limits           - capped row count and a query timeout
"""

import re
import sqlite3
import time
from dataclasses import dataclass

import pandas as pd

from config import DB_PATH, MAX_ROWS, QUERY_TIMEOUT_SECONDS


class UnsafeSQLError(ValueError):
    """The SQL failed validation and was not executed."""


# Extra context the LLM can't infer from the DDL alone.
SCHEMA_NOTES = """\
Relationships:
- orders.customer_id -> customers.id   (a customer has many orders)
- order_items.order_id -> orders.id    (an order has many line items)
- order_items.product_id -> products.id

Business rules:
- Revenue = SUM(order_items.quantity * order_items.unit_price).
- Unless the user says otherwise, revenue and order value only count orders with status = 'completed'.
- Order value = the revenue of a single order (sum of its line items).
- orders.status is one of: 'completed', 'shipped', 'pending', 'cancelled', 'refunded'.
- products.category is one of: 'Electronics', 'Home & Kitchen', 'Fashion', 'Sports & Outdoors', 'Beauty'.
- Dates are stored as TEXT in 'YYYY-MM-DD' format. All money is in USD.
"""


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH} not found. Run `python seed_db.py` first.")
    conn = sqlite3.connect(f"{DB_PATH.resolve().as_uri()}?mode=ro", uri=True)
    conn.set_authorizer(_read_only_authorizer)
    return conn


_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),  # recursive CTEs
}


def _read_only_authorizer(action, *_args):
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def get_schema_ddl() -> str:
    """CREATE TABLE statements, read straight from the database."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND sql IS NOT NULL ORDER BY name"
        ).fetchall()
    return "\n\n".join(r[0].strip() + ";" for r in rows)


def get_table_counts() -> dict[str, int]:
    with _connect() as conn:
        return {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("customers", "products", "orders", "order_items")
        }


# --- validation --------------------------------------------------------------

_FORBIDDEN = {
    "insert", "update", "delete", "drop", "alter", "create", "attach", "detach",
    "pragma", "vacuum", "reindex", "truncate", "begin", "commit", "rollback",
    "savepoint", "release", "grant", "revoke", "load_extension",
}


def validate_sql(sql: str) -> str:
    """Return cleaned SQL if it is a single read-only query, else raise UnsafeSQLError."""
    if not sql or not sql.strip():
        raise UnsafeSQLError("The model did not return any SQL.")

    cleaned = sql.strip()
    cleaned = re.sub(r"^```(?:sql)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE).strip()

    # Build an "analysis" copy with string literals, quoted identifiers and
    # comments blanked out, so keywords inside them don't cause false alarms.
    masked = re.sub(r"'(?:[^']|'')*'", "''", cleaned)
    masked = re.sub(r'"(?:[^"]|"")*"', '""', masked)
    masked = re.sub(r"--[^\n]*", " ", masked)
    masked = re.sub(r"/\*.*?\*/", " ", masked, flags=re.DOTALL)
    masked = masked.strip().rstrip(";").strip()

    if not masked:
        raise UnsafeSQLError("The SQL is empty.")
    if ";" in masked:
        raise UnsafeSQLError("Only a single SQL statement is allowed.")

    first_word = re.match(r"\w+", masked)
    if not first_word or first_word.group(0).lower() not in {"select", "with"}:
        raise UnsafeSQLError("Only SELECT queries (optionally starting with WITH) are allowed.")

    words = set(re.findall(r"[a-z_]+", masked.lower()))
    bad = sorted(words & _FORBIDDEN)
    if bad:
        raise UnsafeSQLError(f"Write or admin keyword not allowed: {', '.join(bad).upper()}.")
    if re.search(r"\breplace\s+into\b", masked, re.IGNORECASE):
        raise UnsafeSQLError("Write keyword not allowed: REPLACE INTO.")

    # Return the original text minus the trailing semicolon.
    return re.sub(r";\s*$", "", cleaned)


# --- execution ---------------------------------------------------------------

@dataclass
class QueryResult:
    df: pd.DataFrame
    truncated: bool  # True if more than MAX_ROWS rows matched


def run_query(sql: str) -> QueryResult:
    """Validate and run a query on a read-only connection. Raises on any problem."""
    safe_sql = validate_sql(sql)
    conn = _connect()
    deadline = time.monotonic() + QUERY_TIMEOUT_SECONDS
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    try:
        cursor = conn.execute(safe_sql)
        rows = cursor.fetchmany(MAX_ROWS + 1)
        columns = [d[0] for d in cursor.description] if cursor.description else []
    except sqlite3.OperationalError as e:
        if "interrupted" in str(e):
            raise TimeoutError(f"Query took longer than {QUERY_TIMEOUT_SECONDS:.0f}s and was stopped.") from e
        raise
    finally:
        conn.close()

    truncated = len(rows) > MAX_ROWS
    return QueryResult(pd.DataFrame(rows[:MAX_ROWS], columns=columns), truncated)
