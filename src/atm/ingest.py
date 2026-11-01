"""Turn manuals (PDF, HTML, Markdown/text) into page-tagged chunks and index them.

Every chunk keeps where it came from (document title + page or section), which
is what lets the assistant cite its sources.

Usage:
    python -m atm.ingest            # index data/manuals/ (falls back to samples/)
    python -m atm.ingest --samples  # index only the bundled sample manual
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from atm import config


@dataclass
class Page:
    doc_id: str
    title: str
    location: str  # "p. 12" for PDFs, "section: Spindle" for HTML/Markdown
    text: str


@dataclass
class Chunk:
    id: str
    doc_id: str
    title: str
    location: str
    text: str


# ---------- loading ----------


def load_pdf(path: Path, title: str) -> list[Page]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(Page(path.stem, title, f"p. {i}", text))
    return pages


def _split_by_headings(doc_id: str, title: str, text: str) -> list[Page]:
    """Split Markdown-style text on '#'/'##' headings; each heading is a section."""
    pages, heading, buf = [], "Introduction", []
    for line in text.splitlines():
        m = re.match(r"^#{1,3}\s+(.*)", line)
        if m:
            if "".join(buf).strip():
                pages.append(Page(doc_id, title, f"section: {heading}", "\n".join(buf)))
            heading, buf = m.group(1).strip(), []
        else:
            buf.append(line)
    if "".join(buf).strip():
        pages.append(Page(doc_id, title, f"section: {heading}", "\n".join(buf)))
    return pages


def load_html(path: Path, title: str) -> list[Page]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    # Convert headings to Markdown markers so we can reuse the heading splitter.
    for level in (1, 2, 3):
        for h in soup.find_all(f"h{level}"):
            h.replace_with(f"\n{'#' * level} {h.get_text(' ', strip=True)}\n")
    return _split_by_headings(path.stem, title, soup.get_text("\n"))


def load_text(path: Path, title: str) -> list[Page]:
    return _split_by_headings(path.stem, title, path.read_text(encoding="utf-8"))


def _manifest_titles() -> dict[str, str]:
    """Titles from manuals.yaml, keyed by id (the downloaded file's name)."""
    path = config.ROOT / "manuals.yaml"
    if not path.exists():
        return {}
    import yaml

    entries = (yaml.safe_load(path.read_text()) or {}).get("manuals") or []
    return {m["id"]: m["title"] for m in entries if "id" in m and "title" in m}


def title_for(path: Path) -> str:
    """Title from manuals.yaml, else the first Markdown heading, else the file name."""
    titles = _manifest_titles()
    if path.stem in titles:
        return titles[path.stem]
    if path.suffix in {".md", ".txt"}:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    return path.stem.replace("-", " ").replace("_", " ").title()


def load_file(path: Path) -> list[Page]:
    title = title_for(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return load_pdf(path, title)
    if suffix in {".html", ".htm"}:
        return load_html(path, title)
    if suffix in {".md", ".txt"}:
        return load_text(path, title)
    return []


# ---------- chunking ----------


def clean(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_page(page: Page, size: int = config.CHUNK_CHARS, overlap: int = config.CHUNK_OVERLAP) -> list[Chunk]:
    """Split one page into overlapping chunks, preferring paragraph breaks."""
    text = clean(page.text)
    chunks, start, n = [], 0, 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            # Back up to the nearest paragraph or sentence break, if one is close.
            for sep in ("\n\n", ". ", "\n"):
                cut = text.rfind(sep, start + size // 2, end)
                if cut != -1:
                    end = cut + len(sep)
                    break
        piece = text[start:end].strip()
        if piece:
            loc_slug = re.sub(r"[^a-z0-9]+", "-", page.location.lower()).strip("-")
            chunks.append(Chunk(f"{page.doc_id}:{loc_slug}:{n}", page.doc_id, page.title, page.location, piece))
            n += 1
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def chunk_pages(pages: list[Page]) -> list[Chunk]:
    return [c for p in pages for c in chunk_page(p)]


# ---------- indexing ----------


def build_index(source_dir: Path, embedding_function=None) -> int:
    from atm.retrieve import get_collection

    files = sorted(p for p in source_dir.rglob("*") if p.is_file())
    chunks = chunk_pages([pg for f in files for pg in load_file(f)])
    if not chunks:
        raise SystemExit(f"No readable manuals found in {source_dir}")

    collection = get_collection(reset=True, embedding_function=embedding_function)
    batch = 200
    for i in range(0, len(chunks), batch):
        part = chunks[i : i + batch]
        collection.add(
            ids=[c.id for c in part],
            documents=[c.text for c in part],
            metadatas=[{"doc_id": c.doc_id, "title": c.title, "location": c.location} for c in part],
        )
    return len(chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--samples", action="store_true", help="index the bundled sample manual only")
    args = parser.parse_args()

    if args.samples or not config.MANUALS_DIR.exists() or not any(config.MANUALS_DIR.iterdir()):
        source = config.SAMPLES_DIR
        if not args.samples:
            print(f"No manuals in {config.MANUALS_DIR}; indexing the sample manual instead.")
    else:
        source = config.MANUALS_DIR
    n = build_index(source)
    print(f"Indexed {n} chunks from {source}")


if __name__ == "__main__":
    main()
