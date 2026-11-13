"""The two LLM calls: question -> SQL, and results -> plain-English answer."""

import json

import anthropic
import pandas as pd

from config import (DEMO_TODAY, ENABLE_FALLBACKS, EXPLAIN_EFFORT, MAX_ROWS_TO_LLM,
                    MODEL, SQL_EFFORT)
from db import SCHEMA_NOTES, get_schema_ddl


class LLMError(RuntimeError):
    """A friendly, user-facing error from the LLM layer."""


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(max_retries=2, timeout=60)
    return _client


def _call(**params) -> anthropic.types.Message:
    """Call the Messages API and turn every failure into a readable LLMError."""
    if ENABLE_FALLBACKS:
        params["extra_headers"] = {"anthropic-beta": "server-side-fallback-2026-07-01"}
        params["extra_body"] = {"fallbacks": "default"}
    try:
        response = _get_client().messages.create(model=MODEL, **params)
    except anthropic.AuthenticationError:
        raise LLMError("Invalid API key. Check ANTHROPIC_API_KEY.")
    except anthropic.RateLimitError:
        raise LLMError("Rate limited by the API. Wait a few seconds and try again.")
    except anthropic.BadRequestError as e:
        raise LLMError(f"The API rejected the request: {e.message}")
    except anthropic.APIStatusError as e:
        raise LLMError(f"The API returned an error ({e.status_code}). Please try again.")
    except anthropic.APIConnectionError:
        raise LLMError("Could not reach the API. Check your internet connection.")

    if response.stop_reason == "refusal":
        raise LLMError("The model declined to answer this question.")
    if response.stop_reason == "max_tokens":
        raise LLMError("The model's response was cut off. Try a simpler question.")
    return response


def _text_of(response: anthropic.types.Message) -> str:
    return "".join(b.text for b in response.content if b.type == "text").strip()


# --- 1. Question -> SQL ------------------------------------------------------

SQL_SCHEMA = {
    "type": "object",
    "properties": {
        "sql": {
            "type": "string",
            "description": "One SQLite SELECT query, or an empty string if the question can't be answered from this database.",
        },
        "reasoning": {
            "type": "string",
            "description": "One short sentence on how the query answers the question, or why it can't be answered.",
        },
    },
    "required": ["sql", "reasoning"],
    "additionalProperties": False,
}


def _sql_system_prompt() -> str:
    return f"""You translate questions about an online shop into SQLite queries.

Database schema:
{get_schema_ddl()}

{SCHEMA_NOTES}
Rules:
- Write exactly one read-only SQLite query (SELECT, or WITH ... SELECT). Never modify data.
- Today's date is {DEMO_TODAY}. Use this literal date for relative dates such as "last month"; do not use 'now'.
  Example: last calendar month = signup_date >= date('{DEMO_TODAY}', 'start of month', '-1 month')
  AND signup_date < date('{DEMO_TODAY}', 'start of month').
- Use clear column aliases (e.g. total_revenue, order_count). Round money to 2 decimal places.
- Include human-readable columns (names, not just ids) when listing customers or products.
- Add ORDER BY for ranked results, and a LIMIT when the user asks for a top N.
- If the question is not about this data, return an empty sql string and explain why in reasoning."""


def generate_sql(question: str, history: list[dict], previous_error: str | None = None) -> dict:
    """Return {"sql": ..., "reasoning": ...}. `history` gives context for follow-up questions."""
    messages = []
    for turn in history[-3:]:  # last few turns, so "now break that down by city" works
        if turn.get("sql"):
            messages.append({"role": "user", "content": turn["question"]})
            messages.append({"role": "assistant", "content": json.dumps(
                {"sql": turn["sql"], "reasoning": turn.get("reasoning", "")})})

    content = question
    if previous_error:
        content += (f"\n\nYour previous query failed:\n{previous_error['sql']}\n"
                    f"Error: {previous_error['error']}\nWrite a corrected query.")
    messages.append({"role": "user", "content": content})

    response = _call(
        max_tokens=8000,
        system=[{"type": "text", "text": _sql_system_prompt(), "cache_control": {"type": "ephemeral"}}],
        messages=messages,
        output_config={"effort": SQL_EFFORT, "format": {"type": "json_schema", "schema": SQL_SCHEMA}},
    )
    try:
        return json.loads(_text_of(response))
    except json.JSONDecodeError:
        raise LLMError("The model returned an unreadable response. Please try again.")


# --- 2. Results -> answer ----------------------------------------------------

def explain_results(question: str, sql: str, df: pd.DataFrame, truncated: bool) -> str:
    sample = df.head(MAX_ROWS_TO_LLM).to_csv(index=False)
    note = f"(showing the first {MAX_ROWS_TO_LLM} of {len(df)} rows)" if len(df) > MAX_ROWS_TO_LLM else ""
    if truncated:
        note += " (results were capped; more rows exist)"

    response = _call(
        max_tokens=4000,
        system=("You are a friendly data analyst. Answer the user's question in 1-3 short sentences "
                "using only the query results provided. Lead with the direct answer and include the key "
                "numbers. Don't mention SQL or tables. If the result is empty, say no matching data was found. "
                f"Today's date is {DEMO_TODAY}. Money is in USD."),
        messages=[{"role": "user", "content":
                   f"Question: {question}\n\nSQL used:\n{sql}\n\nResults {note}:\n{sample or '(no rows)'}"}],
        output_config={"effort": EXPLAIN_EFFORT},
    )
    return _text_of(response) or "Here are the results."
