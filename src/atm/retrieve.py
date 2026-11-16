"""Vector search over the indexed manual chunks (Chroma, stored on disk)."""

from __future__ import annotations

from dataclasses import dataclass

from atm import config


@dataclass
class Hit:
    text: str
    title: str
    location: str
    doc_id: str
    distance: float
    machine: str = ""

    @property
    def citation(self) -> str:
        return f"{self.title}, {self.location}"


def get_collection(reset: bool = False, embedding_function=None):
    """Open (or create) the Chroma collection.

    Chroma's default embedding model (all-MiniLM-L6-v2, run locally) is used
    unless another embedding_function is passed in; swapping it is one of the
    experiments planned for Week 6.
    """
    import chromadb

    client = chromadb.PersistentClient(path=str(config.INDEX_DIR))
    if reset:
        try:
            client.delete_collection(config.COLLECTION)
        except Exception:  # collection did not exist yet
            pass
    kwargs = {"metadata": {"hnsw:space": "cosine"}}
    if embedding_function is not None:
        kwargs["embedding_function"] = embedding_function
    return client.get_or_create_collection(config.COLLECTION, **kwargs)


def search(question: str, k: int = config.TOP_K, collection=None, machines: list[str] | None = None) -> list[Hit]:
    """Top-k chunks closest to the question, optionally only from some machine families."""
    collection = collection or get_collection()
    where = None
    if machines:
        where = {"machine": machines[0]} if len(machines) == 1 else {"machine": {"$in": list(machines)}}
    res = collection.query(query_texts=[question], n_results=k, where=where)
    hits = []
    for text, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        hits.append(Hit(text, meta["title"], meta["location"], meta["doc_id"], dist, meta.get("machine", "")))
    return hits


def indexed_manuals(collection=None) -> dict[str, dict]:
    """Manuals in the index, keyed by title: their machine family and chunk count."""
    collection = collection or get_collection()
    out: dict[str, dict] = {}
    metas = collection.get(include=["metadatas"])["metadatas"] or []
    for m in metas:
        entry = out.setdefault(m["title"], {"machine": m.get("machine", "other"), "chunks": 0})
        entry["chunks"] += 1
    return out
