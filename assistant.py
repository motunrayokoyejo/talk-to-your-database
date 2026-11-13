"""The full pipeline: question -> SQL -> validate -> execute -> explain.

Also contains an offline mode (canned SQL for the example questions) so the
demo still works if the conference Wi-Fi dies.
"""

import sqlite3
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

import llm
from config import MAX_SQL_ATTEMPTS
from db import UnsafeSQLError, run_query

EXAMPLE_QUESTIONS = [
    "How many customers signed up last month?",
    "Which five products generated the most revenue?",
    "Which customers have placed more than five completed orders?",
    "What is the average order value for completed orders?",
    "Which product category generated the most revenue?",
]

# Hand-written SQL for offline mode.
OFFLINE_SQL = {
    EXAMPLE_QUESTIONS[0]: """SELECT COUNT(*) AS new_customers
FROM customers
WHERE signup_date >= date('2026-11-15', 'start of month', '-1 month')
  AND signup_date <  date('2026-11-15', 'start of month')""",
    EXAMPLE_QUESTIONS[1]: """SELECT p.name AS product, p.category,
       ROUND(SUM(oi.quantity * oi.unit_price), 2) AS total_revenue
FROM order_items oi
JOIN orders o   ON o.id = oi.order_id
JOIN products p ON p.id = oi.product_id
WHERE o.status = 'completed'
GROUP BY p.id
ORDER BY total_revenue DESC
LIMIT 5""",
    EXAMPLE_QUESTIONS[2]: """SELECT c.first_name || ' ' || c.last_name AS customer, c.city,
       COUNT(*) AS completed_orders
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = 'completed'
GROUP BY c.id
HAVING COUNT(*) > 5
ORDER BY completed_orders DESC, customer""",
    EXAMPLE_QUESTIONS[3]: """WITH order_totals AS (
    SELECT o.id, SUM(oi.quantity * oi.unit_price) AS order_value
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.id
    WHERE o.status = 'completed'
    GROUP BY o.id
)
SELECT ROUND(AVG(order_value), 2) AS average_order_value,
       COUNT(*) AS completed_orders
FROM order_totals""",
    EXAMPLE_QUESTIONS[4]: """SELECT p.category,
       ROUND(SUM(oi.quantity * oi.unit_price), 2) AS total_revenue
FROM order_items oi
JOIN orders o   ON o.id = oi.order_id
JOIN products p ON p.id = oi.product_id
WHERE o.status = 'completed'
GROUP BY p.category
ORDER BY total_revenue DESC""",
}


@dataclass
class Turn:
    question: str
    answer: str = ""
    sql: str = ""
    reasoning: str = ""
    df: pd.DataFrame | None = None
    truncated: bool = False
    error: str = ""
    attempts: int = 0
    offline: bool = False
    events: list[str] = field(default_factory=list)


def ask(question: str, history: list[dict], offline: bool = False,
        on_step: Callable[[str], None] = lambda _msg: None) -> Turn:
    """Answer one question. Never raises: errors are returned on the Turn."""
    turn = Turn(question=question, offline=offline)
    try:
        if offline:
            _ask_offline(turn, on_step)
        else:
            _ask_llm(turn, history, on_step)
    except llm.LLMError as e:
        turn.error = str(e)
    except UnsafeSQLError as e:
        turn.error = f"Blocked unsafe SQL: {e}"
    except Exception as e:  # last-resort safety net for a live demo
        turn.error = f"Something went wrong: {e}"
    return turn


def _ask_llm(turn: Turn, history: list[dict], on_step) -> None:
    previous_error = None
    for attempt in range(1, MAX_SQL_ATTEMPTS + 1):
        turn.attempts = attempt
        on_step("Generating SQL…" if attempt == 1 else "Query failed, asking the model to fix it…")
        result = llm.generate_sql(turn.question, history, previous_error)
        turn.sql, turn.reasoning = result.get("sql", "").strip(), result.get("reasoning", "")

        if not turn.sql:
            turn.answer = turn.reasoning or "I can't answer that from this database."
            return

        on_step("Validating and running the query (read-only)…")
        try:
            qr = run_query(turn.sql)
        except UnsafeSQLError:
            raise  # never retry around the safety check
        except (sqlite3.Error, TimeoutError) as e:
            previous_error = {"sql": turn.sql, "error": str(e)}
            if attempt == MAX_SQL_ATTEMPTS:
                turn.error = f"The generated query failed: {e}"
                return
            continue

        turn.df, turn.truncated = qr.df, qr.truncated
        on_step("Explaining the results…")
        turn.answer = llm.explain_results(turn.question, turn.sql, qr.df, qr.truncated)
        return


def _ask_offline(turn: Turn, on_step) -> None:
    sql = OFFLINE_SQL.get(turn.question)
    if sql is None:
        turn.error = ("Offline mode only answers the example questions. "
                      "Set ANTHROPIC_API_KEY to ask anything.")
        return
    turn.sql, turn.attempts = sql, 1
    on_step("Running the query (read-only)…")
    qr = run_query(sql)
    turn.df, turn.truncated = qr.df, qr.truncated
    turn.answer = _offline_summary(qr.df)


def _offline_summary(df: pd.DataFrame) -> str:
    if df.empty:
        return "No matching data was found."
    def fmt(col):
        return f"{col.replace('_', ' ')}: **{df[col].iloc[0]}**"
    if len(df) == 1:
        return "Result: " + ", ".join(fmt(c) for c in df.columns) + "."
    return f"Found {len(df)} rows. Top result: " + ", ".join(fmt(c) for c in df.columns) + "."
