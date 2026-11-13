"""Streamlit UI. Run:  streamlit run app.py"""

import streamlit as st

from assistant import EXAMPLE_QUESTIONS, ask
from config import DB_PATH, DEMO_TODAY, MAX_ROWS, MODEL, has_api_key
from db import SCHEMA_NOTES, get_schema_ddl, get_table_counts

st.set_page_config(page_title="Talk to Your Database", page_icon="🗄️", layout="wide")

if not DB_PATH.exists():
    st.error("Database not found. Run `python seed_db.py` first, then refresh.")
    st.stop()

st.session_state.setdefault("history", [])
st.session_state.setdefault("pending", None)


def md(text: str) -> str:
    """Escape $ so Streamlit doesn't render money amounts as LaTeX."""
    return text.replace("$", "\\$")


# --- sidebar -----------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Settings")
    offline = st.toggle(
        "Offline mode",
        value=not has_api_key(),
        disabled=not has_api_key(),
        help="Uses prewritten SQL for the example questions, with no API calls. "
             "Turned on automatically when ANTHROPIC_API_KEY isn't set.",
    )
    st.caption(f"Model: `{MODEL}`" if not offline else "Model: offline (canned SQL)")
    st.caption(f"Demo date: {DEMO_TODAY}")

    if st.button("🗑️ Clear conversation", width="stretch"):
        st.session_state.history = []
        st.session_state.pending = None
        st.rerun()

    st.divider()
    st.subheader("📦 Database")
    for table, n in get_table_counts().items():
        st.write(f"`{table}`: {n:,} rows")
    with st.expander("Schema"):
        st.code(get_schema_ddl(), language="sql")
        st.markdown(md(SCHEMA_NOTES))
    st.caption(f"🔒 Read-only · SELECT only · max {MAX_ROWS} rows")


# --- header ------------------------------------------------------------------
st.title("🗄️ Talk to Your Database")
st.markdown(
    "Ask questions about a fictional online shop in plain English. An LLM turns your "
    "question into SQL, the query is checked and run against a **read-only** SQLite "
    "database, and the results are explained back to you."
)

st.markdown("**Try an example:**")
cols = st.columns(len(EXAMPLE_QUESTIONS))
for col, q in zip(cols, EXAMPLE_QUESTIONS):
    if col.button(q, width="stretch"):
        st.session_state.pending = q


# --- conversation ------------------------------------------------------------
def render_turn(turn: dict) -> None:
    with st.chat_message("user"):
        st.markdown(md(turn["question"]))
    with st.chat_message("assistant"):
        if turn["error"]:
            st.error(turn["error"])
        if turn["answer"]:
            st.markdown(md(turn["answer"]))
        if turn["sql"]:
            label = "Generated SQL" + (f" (fixed on attempt {turn['attempts']})" if turn["attempts"] > 1 else "")
            with st.expander(label):
                st.code(turn["sql"], language="sql")
                if turn["reasoning"]:
                    st.caption(md(turn["reasoning"]))
        if turn["df"] is not None:
            st.dataframe(turn["df"], width="stretch", hide_index=True)
            note = f"{len(turn['df'])} row(s)"
            if turn["truncated"]:
                note += f": capped at {MAX_ROWS}; refine your question to see fewer rows"
            st.caption(note)


for past in st.session_state.history:
    render_turn(past)

typed = st.chat_input("Ask a question about customers, products, or orders…")
question = typed or st.session_state.pending
st.session_state.pending = None

if question:
    with st.chat_message("user"):
        st.markdown(md(question))
    with st.status("Working on it…", expanded=True) as status:
        result = ask(
            question,
            history=st.session_state.history,
            offline=offline,
            on_step=lambda msg: status.write(msg),
        )
        status.update(label="Failed" if result.error else "Done",
                      state="error" if result.error else "complete", expanded=False)
    st.session_state.history.append(vars(result))
    st.rerun()  # redraw so the new turn renders like the rest of the history
