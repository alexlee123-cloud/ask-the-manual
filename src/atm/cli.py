"""Ask a question from the command line.

    python -m atm.cli "What is the lockout/tagout sequence?"
"""

import sys

from atm.answer import ask


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    result = ask(" ".join(sys.argv[1:]))
    print(result.text)
    print("\nSources:")
    for i, hit in enumerate(result.sources, start=1):
        print(f"  [{i}] {hit.citation}")


if __name__ == "__main__":
    main()
