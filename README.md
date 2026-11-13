# Talk to Your Database

A small demo for the DevFest talk **"Talk to Your Database: Building AI-Powered Data Assistants."**

You ask a question in plain English. Claude writes the SQL, the app checks it and runs it against a read-only SQLite database, and Claude explains the results.

```
question ──► LLM (schema + rules) ──► SQL ──► validate ──► read-only SQLite ──► rows ──► LLM ──► answer
                    ▲                                            │
                    └───────────── error (one retry) ◄───────────┘
```

## Quick start

```bash
cd talk-to-your-database
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python seed_db.py                       # creates shop.db (same data every time)
export ANTHROPIC_API_KEY=sk-ant-...     # get one at https://platform.claude.com
streamlit run app.py
```

If `ANTHROPIC_API_KEY` isn't set, the app runs in **offline mode**: the five example questions still work using prewritten SQL. Keep this as a backup in case the venue Wi-Fi fails.

Run the safety checks with `python test_safety.py`.

## Files

| File | What it does |
|---|---|
| `seed_db.py` | Builds the fictional shop: 250 customers, 40 products, orders, and order items (fixed seed) |
| `db.py` | Schema for the prompt, **SQL validation**, read-only execution |
| `llm.py` | The two Claude calls: question → SQL (structured JSON output), results → answer |
| `assistant.py` | The pipeline, including the retry-on-error loop and offline mode |
| `app.py` | The Streamlit UI |
| `config.py` | Model, effort, row limits, timeout, demo date |

## Safety layers

1. **Prompt:** the model is told to write only read-only SQLite.
2. **Validation (`validate_sql`):** allows a single statement starting with `SELECT` or `WITH`. Rejects write and admin keywords (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `PRAGMA`, `ATTACH`, …) and multiple statements. String literals and comments are masked first, so `'drop'` inside a string doesn't cause a false alarm.
3. **Read-only connection:** the file is opened with `mode=ro`.
4. **SQLite authorizer:** the engine denies every action except reads, so writes fail even if validation is bypassed.
5. **Limits:** at most 200 rows go to the UI and 50 to the LLM, and queries time out after 5 seconds.

Never trust the LLM's SQL. Each layer assumes the one before it can fail.

## Things to know for the demo

- **Pinned "today":** the data ends on 2026-10-31 and the app treats today as **2026-11-15**, so "last month" always means October 2026. Change it with `DEMO_TODAY`.
- **Revenue rule:** revenue counts only `completed` orders unless the question says otherwise. This rule lives in `SCHEMA_NOTES` in `db.py` and shows how much business context matters.
- **Follow-ups work:** the last three turns are sent as context, so after "top five products" you can ask "now just for Lagos customers".
- **Self-correction:** if a query errors, the error goes back to the model for one more try. The SQL panel shows when this happened.
- **Questions to show the guardrails:** "Delete all cancelled orders" (the model declines, or validation blocks it) and "What's the weather in Lagos?" (out of scope).

## Configuration (environment variables)

| Variable | Default | |
|---|---|---|
| `CLAUDE_MODEL` | `claude-opus-5-5` | e.g. `claude-sonnet-5-5` or `claude-haiku-5-5` for faster or cheaper answers |
| `SQL_EFFORT` / `EXPLAIN_EFFORT` | `medium` / `low` | Lower means faster |
| `ENABLE_FALLBACKS` | `1` | Server-side refusal fallback (beta); set to `0` to turn it off |
| `MAX_ROWS`, `QUERY_TIMEOUT_SECONDS`, `DEMO_TODAY` | `200`, `5`, `2026-11-15` | |
