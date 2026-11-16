"""Streamlit chat interface.  Run:  streamlit run app.py"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import streamlit as st

from atm import config
from atm.answer import ask
from atm.ingest import build_index, default_source
from atm.retrieve import get_collection, indexed_manuals

MACHINE_LABELS = {
    "haas-mill": "Haas mill",
    "haas-lathe": "Haas lathe",
    "general-safety": "Lockout/tagout (OSHA)",
    "other": "Other",
}

st.set_page_config(page_title="Ask the Manual", page_icon="🔧")
st.title("Ask the Manual")
st.caption("Answers come only from the indexed equipment manuals, with the manual and page each fact came from.")


def load_manuals() -> dict:
    try:
        return indexed_manuals(get_collection())
    except Exception:
        return {}


# ---------- sidebar: what's indexed, rebuild, filter ----------

with st.sidebar:
    st.header("Manuals")
    manuals = load_manuals()
    if manuals:
        for title, info in sorted(manuals.items()):
            st.markdown(f"- {title}")
    else:
        st.info("No manuals indexed yet. Click **Build index** below.")

    source = default_source()
    st.caption(f"Manuals folder: `{source}`")
    if st.button("Rebuild index" if manuals else "Build index", use_container_width=True):
        log = st.empty()
        with st.spinner("Reading and indexing the manuals. The first run takes a few minutes..."):
            n = build_index(source, progress=lambda msg: log.caption(msg))
        log.empty()
        st.success(f"Indexed {n} chunks.")
        st.rerun()

    machines_available = sorted({info["machine"] for info in manuals.values()})
    chosen = st.multiselect(
        "Search only these manuals",
        machines_available,
        format_func=lambda m: MACHINE_LABELS.get(m, m),
        placeholder="All manuals",
    )

if not os.getenv("ANTHROPIC_API_KEY"):
    st.warning("No API key found. Add `ANTHROPIC_API_KEY=...` to the `.env` file in this folder, then restart the app.")

# ---------- chat ----------

if "history" not in st.session_state:
    st.session_state.history = []

for role, content in st.session_state.history:
    with st.chat_message(role):
        st.markdown(content)

if question := st.chat_input("Ask about a procedure, spec, or safety step", disabled=not manuals):
    st.session_state.history.append(("user", question))
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Searching the manuals..."):
                result = ask(question, machines=chosen or None)
        except Exception as e:  # show API problems (bad key, no credit) in the chat instead of a stack trace
            if type(e).__name__ == "AuthenticationError":
                reply = "Claude rejected the API key. Check `ANTHROPIC_API_KEY` in `.env`, then restart the app."
            else:
                reply = f"Something went wrong calling Claude: {e}"
            st.error(reply)
        else:
            sources = "\n".join(f"{i}. {h.citation}" for i, h in enumerate(result.sources, start=1))
            reply = f"{result.text}\n\n**Sources**\n\n{sources}" if result.found else result.text
            st.markdown(reply)
            with st.expander("Show the excerpts the answer was based on"):
                for i, h in enumerate(result.sources, start=1):
                    st.markdown(f"**[{i}] {h.citation}**")
                    st.text(h.text)
    st.session_state.history.append(("assistant", reply))
