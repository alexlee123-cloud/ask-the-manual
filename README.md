# Ask the Manual

**An AI assistant that answers maintenance questions from equipment manuals and cites the exact page each answer came from.**

A technician asks *"What's the torque spec for the impeller nut?"* and gets the value, the steps around it, and a citation like *CP-200 Service Manual, section: Mechanical Seal Replacement*. When the manuals don't cover a question, the assistant says so instead of guessing, because a made-up spec on a shop floor can hurt someone.

> Status: early development (course project for CSC5015 Advanced AI, Concordia University Wisconsin). Results and a demo will be added as the evaluation runs.

## Why

Maintenance teams lose time searching hundred-page PDF manuals for one procedure or spec, and tribal knowledge leaves when experienced techs retire. Ask the Manual applies retrieval-augmented generation (RAG) to that problem and measures how reliable the answers are, rather than just demoing a chatbot.

It pairs with predictive maintenance: a model predicts *which* machine is likely to fail, and this assistant tells the tech *how* to fix it.

## How it works

```
manuals (PDF / HTML)  ->  page-tagged chunks  ->  embeddings in Chroma
                                                        |
question  ->  top-k similar chunks  ->  Claude answers from those excerpts only, citing [1], [2] ...
```

1. **Ingest** (`src/atm/ingest.py`): extracts text page by page (PDF) or section by section (HTML/Markdown), then splits it into overlapping chunks that remember their source page.
2. **Retrieve** (`src/atm/retrieve.py`): embeds the question and finds the closest chunks in a local Chroma vector store.
3. **Answer** (`src/atm/answer.py`): sends the numbered excerpts to Claude with instructions to cite every fact and to say "not found" when the excerpts don't answer the question.
4. **Evaluate** (`eval/run_eval.py`): scores retrieval hit rate, answer accuracy and correct abstentions on a question set with known answers.

## Quick start

```bash
git clone https://github.com/alexlee123-cloud/ask-the-manual
cd ask-the-manual
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
cp .env.example .env        # then add your ANTHROPIC_API_KEY

python -m atm.ingest --samples          # index the bundled sample manual
python -m atm.cli "How often do I grease the bearings?"
streamlit run app.py                    # chat interface in the browser
```

To use real manuals, list them in `manuals.yaml`, then:

```bash
python scripts/download_manuals.py   # saves to data/ (git-ignored)
python -m atm.ingest
```

Manuals are copyrighted, so this repo stores links to them, never the files.

## Evaluation

```bash
python eval/run_eval.py --retrieval-only   # free, search quality only
python eval/run_eval.py                    # full run with Claude
```

| Metric | What it measures | Result |
| --- | --- | --- |
| Retrieval hit rate @5 | Correct page/section is in the top 5 excerpts | TBD |
| Answer accuracy | Answer contains the expected spec or step | TBD |
| Correct abstentions | Says "not found" for questions the manuals don't cover | TBD |

Planned experiments: chunk size, top-k, hybrid keyword + vector search, re-ranking, and adding a second machine without code changes.

## Tests

```bash
pytest
```

The tests run offline with a stand-in embedding and a fake API client.

## Configuration

Environment variables (or `.env`): `ANTHROPIC_API_KEY`, `ATM_MODEL` (default `claude-opus-5-5`), `ATM_EFFORT` (default `low`), `ATM_TOP_K` (default 5), `ATM_CHUNK_CHARS`, `ATM_CHUNK_OVERLAP`.

The first index build downloads Chroma's default embedding model (all-MiniLM-L6-v2, about 80 MB), which then runs locally.

## Tech

Python, Chroma, sentence-embedding model (all-MiniLM-L6-v2), Anthropic Claude API, Streamlit, pytest.

## License

MIT for the code. Manuals belong to their publishers. The sample CP-200 manual in `samples/` is fictional and written for testing.
