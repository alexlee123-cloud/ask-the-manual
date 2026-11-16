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
    location: str  # "PDF p. 12" (page of the PDF file, not the printed number) for PDFs, "section: Spindle" for HTML/Markdown
    text: str


@dataclass
class Chunk:
    id: str
    doc_id: str
    title: str
    location: str
    text: str
    machine: str = "other"


# ---------- loading ----------


def load_pdf(path: Path, title: str) -> list[Page]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(Page(path.stem, title, f"PDF p. {i}", text))
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


def _manifest() -> list[dict]:
    path = config.ROOT / "manuals.yaml"
    if not path.exists():
        return []
    import yaml

    return (yaml.safe_load(path.read_text()) or {}).get("manuals") or []


def manifest_entry(path: Path) -> dict | None:
    """The manuals.yaml entry for a file: by id, else by a `match` word in the file name."""
    name = path.name.lower()
    for m in _manifest():
        if m.get("id") == path.stem:
            return m
    for m in _manifest():
        if any(word.lower() in name for word in m.get("match") or []):
            return m
    return None


def title_for(path: Path) -> str:
    """Title from manuals.yaml, else the first Markdown heading, else the file name."""
    entry = manifest_entry(path)
    if entry and entry.get("title"):
        return entry["title"]
    if path.suffix in {".md", ".txt"}:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    return path.stem.replace("-", " ").replace("_", " ").title()


def machine_for(path: Path) -> str:
    entry = manifest_entry(path)
    return (entry or {}).get("machine") or "other"


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


def is_table_of_contents(text: str) -> bool:
    """Contents pages ("Spindle ........ 104") match many questions but answer none."""
    return len(re.findall(r"\.{5,}", text)) >= 4


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
        if piece and not is_table_of_contents(piece):
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


SUPPORTED = {".pdf", ".html", ".htm", ".md", ".txt"}


def manual_files(source_dir: Path) -> list[Path]:
    return sorted(
        p for p in source_dir.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED and not p.name.startswith(".")
    )


def build_index(source_dir: Path, embedding_function=None, progress=print) -> int:
    from atm.retrieve import get_collection

    chunks = []
    for f in manual_files(source_dir):
        pages = load_file(f)
        machine = machine_for(f)
        file_chunks = chunk_pages(pages)
        for c in file_chunks:
            c.machine = machine
        chunks.extend(file_chunks)
        progress(f"Read {f.name}: {len(pages)} pages, {len(file_chunks)} chunks")
    if not chunks:
        raise SystemExit(f"No readable manuals found in {source_dir}")

    collection = get_collection(reset=True, embedding_function=embedding_function)
    batch = 200
    for i in range(0, len(chunks), batch):
        part = chunks[i : i + batch]
        collection.add(
            ids=[c.id for c in part],
            documents=[c.text for c in part],
            metadatas=[
                {"doc_id": c.doc_id, "title": c.title, "location": c.location, "machine": c.machine} for c in part
            ],
        )
        progress(f"Embedded {min(i + batch, len(chunks))}/{len(chunks)} chunks")
    return len(chunks)


def default_source() -> Path:
    """The manuals folder if it has manuals in it, else the bundled sample manual."""
    if config.MANUALS_DIR.is_dir() and manual_files(config.MANUALS_DIR):
        return config.MANUALS_DIR
    return config.SAMPLES_DIR


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--samples", action="store_true", help="index the bundled sample manual only")
    args = parser.parse_args()

    source = config.SAMPLES_DIR if args.samples else default_source()
    if source == config.SAMPLES_DIR and not args.samples:
        print(f"No manuals in {config.MANUALS_DIR}; indexing the sample manual instead.")
    n = build_index(source)
    print(f"Indexed {n} chunks from {source}")


if __name__ == "__main__":
    main()
