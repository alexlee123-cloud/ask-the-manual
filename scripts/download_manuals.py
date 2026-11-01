"""Download the manuals listed in manuals.yaml into data/manuals/.

Manuals are copyrighted, so they are downloaded locally and never committed.

    python scripts/download_manuals.py
"""

import sys
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "manuals"


def main() -> None:
    entries = yaml.safe_load((ROOT / "manuals.yaml").read_text())["manuals"]
    OUT.mkdir(parents=True, exist_ok=True)
    failed = 0
    for m in entries:
        url = m["url"]
        try:
            r = requests.get(url, timeout=60, headers={"User-Agent": "ask-the-manual/0.1 (student project)"})
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"FAILED  {m['id']}: {e}")
            failed += 1
            continue
        is_pdf = "pdf" in r.headers.get("content-type", "") or url.lower().endswith(".pdf")
        path = OUT / f"{m['id']}{'.pdf' if is_pdf else '.html'}"
        path.write_bytes(r.content)
        print(f"saved   {path.relative_to(ROOT)} ({len(r.content) // 1024} KB)")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
