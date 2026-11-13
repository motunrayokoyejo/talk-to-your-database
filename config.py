"""Central settings for the demo. Override any of these with environment variables."""

import os
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
DB_PATH = Path(os.getenv("DB_PATH", PROJECT_DIR / "shop.db"))

# Claude model used for SQL generation and explanations.
MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")

# Effort controls how hard the model thinks: "low" | "medium" | "high".
SQL_EFFORT = os.getenv("SQL_EFFORT", "medium")
EXPLAIN_EFFORT = os.getenv("EXPLAIN_EFFORT", "low")

# Server-side refusal fallback (re-routes a declined request to another model).
ENABLE_FALLBACKS = os.getenv("ENABLE_FALLBACKS", "1") == "1"

# The seeded data ends on 2026-10-31. We pin "today" so relative questions
# ("last month") always give the same answer, no matter when you run the demo.
DEMO_TODAY = os.getenv("DEMO_TODAY", "2026-11-15")

# Guardrails
MAX_ROWS = int(os.getenv("MAX_ROWS", "200"))            # rows returned to the UI
MAX_ROWS_TO_LLM = int(os.getenv("MAX_ROWS_TO_LLM", "50"))  # rows sent for explanation
QUERY_TIMEOUT_SECONDS = float(os.getenv("QUERY_TIMEOUT_SECONDS", "5"))
MAX_SQL_ATTEMPTS = 2  # one retry: if the SQL fails, the error is sent back to the model


def has_api_key() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))
