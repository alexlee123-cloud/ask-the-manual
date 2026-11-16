"""Settings, read from environment variables (or a .env file)."""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional
    pass

ROOT = Path(__file__).resolve().parents[2]
MANUALS_DIR_SET = bool(os.getenv("ATM_MANUALS_DIR", "").strip())
MANUALS_DIR = Path(os.getenv("ATM_MANUALS_DIR", "").strip() or ROOT / "data" / "manuals").expanduser()
SAMPLES_DIR = ROOT / "samples"
INDEX_DIR = Path(os.getenv("ATM_INDEX_DIR", ROOT / "index"))
COLLECTION = os.getenv("ATM_COLLECTION", "manuals")

MODEL = os.getenv("ATM_MODEL", "claude-opus-5-5")
EFFORT = os.getenv("ATM_EFFORT", "low")
TOP_K = int(os.getenv("ATM_TOP_K", "8"))

# Chunking: roughly 200-300 words per chunk, with overlap so a step that
# spans a boundary still lands whole in at least one chunk.
CHUNK_CHARS = int(os.getenv("ATM_CHUNK_CHARS", "1500"))
CHUNK_OVERLAP = int(os.getenv("ATM_CHUNK_OVERLAP", "200"))
