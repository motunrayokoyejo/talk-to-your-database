"""Quick checks for the SQL guardrails and the offline pipeline.

Run:  python test_safety.py
"""

from assistant import EXAMPLE_QUESTIONS, ask
from db import UnsafeSQLError, run_query, validate_sql

ALLOWED = [
    "SELECT COUNT(*) FROM customers",
    "select * from products;",
    "WITH t AS (SELECT 1 AS x) SELECT x FROM t",
    "SELECT 'please delete; drop table' AS s",            # keywords inside a string
    "SELECT replace(name, 'Pro', 'Max') FROM products",    # replace() function is fine
    "```sql\nSELECT 1\n```",                               # markdown fences stripped
    "SELECT 1 -- trailing comment; with semicolon",
]

BLOCKED = [
    "DELETE FROM customers",
    "DROP TABLE orders",
    "UPDATE products SET price = 0",
    "INSERT INTO customers VALUES (1)",
    "SELECT 1; DROP TABLE customers",
    "SELECT 1; SELECT 2",
    "WITH x AS (SELECT 1) DELETE FROM orders",
    "WITH x AS (SELECT 1) REPLACE INTO products VALUES (1,'a','b',1)",
    "PRAGMA table_info(customers)",
    "ATTACH DATABASE 'evil.db' AS evil",
    "CREATE TABLE t (x)",
    "",
]


def main() -> None:
    for sql in ALLOWED:
        validate_sql(sql)
    print(f"✓ {len(ALLOWED)} safe queries accepted")

    for sql in BLOCKED:
        try:
            validate_sql(sql)
        except UnsafeSQLError:
            continue
        raise AssertionError(f"Should have been blocked: {sql!r}")
    print(f"✓ {len(BLOCKED)} unsafe queries blocked")

    # Even if validation were bypassed, the connection itself is read-only.
    import db
    conn = db._connect()
    try:
        conn.execute("DELETE FROM customers")
        raise AssertionError("Read-only connection allowed a write!")
    except Exception as e:
        assert "not authorized" in str(e) or "readonly" in str(e), e
    finally:
        conn.close()
    print("✓ Read-only connection rejects writes")

    assert len(run_query("SELECT * FROM order_items").df) == db.MAX_ROWS
    print("✓ Result rows are capped")

    for q in EXAMPLE_QUESTIONS:
        turn = ask(q, history=[], offline=True)
        assert not turn.error, (q, turn.error)
        print(f"\nQ: {q}\nA: {turn.answer}\n{turn.df.head(5).to_string(index=False)}")


if __name__ == "__main__":
    main()
