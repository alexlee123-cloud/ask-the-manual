"""Offline tests: no API key or embedding-model download needed."""

import hashlib
from types import SimpleNamespace

import pytest

from atm import config
from atm.answer import NOT_FOUND, ask, build_user_message
from atm.ingest import Page, build_index, chunk_page, load_file
from atm.retrieve import search


class HashEmbedding:
    """Deterministic bag-of-words embedding so tests run without downloading a model."""

    DIM = 256

    def __call__(self, input):
        out = []
        for text in input:
            vec = [0.0] * self.DIM
            for word in text.lower().split():
                word = word.strip(".,:;()[]")
                vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.DIM] += 1.0
            out.append(vec)
        return out

    def embed_query(self, input):
        return self(input)

    @staticmethod
    def name():
        return "hash-test"

    def is_legacy(self):
        return False

    def get_config(self):
        return {}

    @staticmethod
    def build_from_config(config):
        return HashEmbedding()


SAMPLE = config.SAMPLES_DIR / "cp200-pump-manual.md"


def test_markdown_sections_keep_their_heading():
    pages = load_file(SAMPLE)
    locations = [p.location for p in pages]
    assert "section: Mechanical Seal Replacement" in locations
    assert pages[0].title.startswith("CP-200")


def test_chunks_overlap_and_keep_location():
    page = Page("doc", "Doc", "p. 3", "word " * 1000)
    chunks = chunk_page(page, size=500, overlap=100)
    assert len(chunks) > 1
    assert all(c.location == "p. 3" for c in chunks)
    assert len({c.id for c in chunks}) == len(chunks)


@pytest.fixture
def collection(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INDEX_DIR", tmp_path / "index")
    emb = HashEmbedding()
    build_index(config.SAMPLES_DIR, embedding_function=emb)
    from atm.retrieve import get_collection

    return get_collection(embedding_function=emb)


def test_search_finds_the_right_section(collection):
    hits = search("impeller nut torque ft-lb", k=3, collection=collection)
    assert any(h.location == "section: Mechanical Seal Replacement" for h in hits)


class FakeClient:
    def __init__(self, reply):
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self.reply = reply

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            stop_reason="end_turn",
            model=kwargs["model"],
            content=[SimpleNamespace(type="text", text=self.reply)],
        )


def test_ask_sends_numbered_excerpts_and_returns_sources(collection):
    client = FakeClient("Torque it to 45 ft-lb [1].")
    result = ask("impeller nut torque", k=3, client=client, collection=collection)
    sent = client.calls[0]["messages"][0]["content"]
    assert "[1] (" in sent and "Question: impeller nut torque" in sent
    assert result.found and len(result.sources) == 3


def test_not_found_is_detected(collection):
    result = ask("warranty period", k=2, client=FakeClient(NOT_FOUND), collection=collection)
    assert not result.found


def test_user_message_format():
    from atm.retrieve import Hit

    msg = build_user_message("q?", [Hit("text", "Manual", "p. 2", "m", 0.1)])
    assert "[1] (Manual, p. 2)\ntext" in msg
