"""Generate the controlled claim-admissibility benchmark artifact."""

import json
from pathlib import Path

from themegraph.benchmark import complete_benchmark

ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    output = ROOT / "results" / "claim_admissibility_benchmark.json"
    output.write_text(
        json.dumps(complete_benchmark(), indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )