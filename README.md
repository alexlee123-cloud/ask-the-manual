# Ask the Manual

**An AI assistant that answers maintenance questions from equipment manuals and cites the exact page each answer came from.**

A technician asks *"What's the torque spec for the impeller nut?"* and gets the value, the steps around it, and a citation like *CP-200 Service Manual, section: Mechanical Seal Replacement*. When the manuals don't cover a question, the assistant says so instead of guessing, because a made-up spec on a shop floor can hurt someone.

> Status: working prototype over Haas mill/lathe operator's manuals and OSHA lockout/tagout documents (course project for CSC5015 Advanced AI, Concordia University Wisconsin). Evaluation and a demo are in progress.

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
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
cp .env.example .env    # add ANTHROPIC_API_KEY, and ATM_MANUALS_DIR = the folder with your manual PDFs
streamlit run app.py    # opens in the browser; click "Build index" the first time
```

If `streamlit` isn't found or runs from the wrong Python (common when Anaconda's `base` environment is active), make sure `.venv` is activated and run `python -m streamlit run app.py` instead.

If an answer comes back "not found", open **Show the excerpts** under it to see what search returned, and check that the sidebar lists your manuals rather than the CP-200 sample.

The first index build reads about 1,100 PDF pages and downloads the embedding model (about 80 MB), so it takes a few minutes. After that the index is saved in `index/` and the app starts right away. Click **Rebuild index** after adding or removing manuals.

Command-line versions of the same steps:

```bash
python -m atm.ingest                                 # build the index from ATM_MANUALS_DIR
python -m atm.cli "How often should I grease the lathe chuck?"
python -m atm.ingest --samples                       # or index only the small fictional sample manual
```

## Manuals

The prototype answers from four documents (official links in `manuals.yaml`):

| Manual | Machine | Pages |
| --- | --- | --- |
| Haas Mill Operator's Manual (NGC, 2022) | Haas mill | 544 |
| Haas Lathe Operator's Manual (NGC, 2023) | Haas lathe | 532 |
| OSHA 3120: Control of Hazardous Energy (Lockout/Tagout) | Safety | 45 |
| 29 CFR 1910.147: The Control of Hazardous Energy | Safety | 13 |

Manuals are copyrighted, so this repo stores links to them, never the files. Download them, put them in one folder, and set `ATM_MANUALS_DIR` in `.env`. Any file names work: `manuals.yaml` recognizes each manual by words in its file name (`match`) and gives it a proper title and machine family. `python scripts/download_manuals.py` can also fetch them into `data/manuals/` where the publisher allows it.

Citations use the **page of the PDF file** ("PDF p. 126"), so typing that number into a PDF viewer jumps to the source. The number printed on the manual page can differ.

The sidebar can limit a search to one machine (for example only the lathe manual), since the Haas mill and lathe manuals share many sections.

## Evaluation

```bash
python eval/run_eval.py --retrieval-only   # free, search quality only
python eval/run_eval.py                    # full run with Claude
```

`eval/questions-manuals.csv` is a starter set of questions about the real manuals (7 answerable, 2 not covered); it will grow to 40-50.

```bash
python eval/run_eval.py --retrieval-only --questions eval/questions-manuals.csv
```

Baseline on the starter set (vector search only, 1,500-character chunks, 2026-11-16): hit rate 29% at k=3, 57% at k=5, 86% at k=10. The app sends Claude the top 8 excerpts by default. Misses come mostly from the mill and lathe manuals having near-identical sections, which is what the planned keyword search and re-ranking experiments target.

| Metric | What it measures | Result |
| --- | --- | --- |
| Retrieval hit rate @5 | Correct page/section is in the top 5 excerpts | 57% (starter set) |
| Answer accuracy | Answer contains the expected spec or step | TBD |
| Correct abstentions | Says "not found" for questions the manuals don't cover | TBD |

Planned experiments: chunk size, top-k, hybrid keyword + vector search, re-ranking, and adding a second machine without code changes.

## Tests

```bash
pytest
```

The tests run offline with a stand-in embedding and a fake API client.

## Configuration

Environment variables (or `.env`): `ANTHROPIC_API_KEY`, `ATM_MODEL` (default `claude-opus-5-5`), `ATM_EFFORT` (default `low`), `ATM_MANUALS_DIR` (default `data/manuals/`), `ATM_TOP_K` (default 8), `ATM_CHUNK_CHARS`, `ATM_CHUNK_OVERLAP`.

The first index build downloads Chroma's default embedding model (all-MiniLM-L6-v2, about 80 MB), which then runs locally.

## Tech

Python, Chroma, sentence-embedding model (all-MiniLM-L6-v2), Anthropic Claude API, Streamlit, pytest.

## License

MIT for the code. Manuals belong to their publishers. The sample CP-200 manual in `samples/` is fictional and written for testing.
