"""Run five-dataset external policy stress tests by epistemic function."""

from __future__ import annotations

import json
from pathlib import Path

from themegraph.external_validation import run_external_validation

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "external_validation.json"


if __name__ == "__main__":
    result = run_external_validation(ROOT)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="ascii"
    )
    print(f"Wrote {OUTPUT}")
