"""Streamlit chat interface.  Run:  streamlit run app.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import streamlit as st

from atm.answer import ask

st.set_page_config(page_title="Ask the Manual", page_icon="🔧")
st.title("Ask the Manual")
st.caption("Answers come only from the indexed equipment manuals, with the page each fact came from.")

if "history" not in st.session_state:
    st.session_state.history = []

for role, content in st.session_state.history:
    with st.chat_message(role):
        st.markdown(content)

if question := st.chat_input("Ask about a procedure, spec, or alarm"):
    st.session_state.history.append(("user", question))
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Searching the manuals..."):
            result = ask(question)
        sources = "\n".join(f"{i}. {h.citation}" for i, h in enumerate(result.sources, start=1))
        reply = f"{result.text}\n\n**Sources**\n\n{sources}" if result.found else result.text
        st.markdown(reply)
        if result.found:
            with st.expander("Show the excerpts"):
                for i, h in enumerate(result.sources, start=1):
                    st.markdown(f"**[{i}] {h.citation}**")
                    st.text(h.text)
    st.session_state.history.append(("assistant", reply))
