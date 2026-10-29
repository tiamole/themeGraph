"""Generate bounded multi-axis specification-surface results."""

import argparse
import json
import sysconfig
from pathlib import Path

from themegraph.adapters import DirectoryTextAdapter, ONetZipAdapter
from themegraph.specification import evaluate_specification_surface
from themegraph.synthetic import planted_cycle_corpus

ROOT = Path(__file__).resolve().parents[1]


def main(selected: set[str] | None = None) -> None:
    synthetic, _ = planted_cycle_corpus()
    corpora = {
        "synthetic": (synthetic, False),
        "onet_500": (
            list(
                ONetZipAdapter(
                    ROOT / "data" / "external" / "db_30_3_text.zip",
                    max_documents=500,
                ).documents()
            ),
            True,
        ),
        "acmart": (
            list(
                DirectoryTextAdapter(
                    ROOT / "acmart-primary", max_documents=100
                ).documents()
            ),
            True,
        ),
        "python_stdlib_100": (
            list(
                DirectoryTextAdapter(
                    Path(sysconfig.get_path("stdlib")), max_documents=100
                ).documents()
            ),
            True,
        ),
    }
    names = selected or set(corpora)
    unknown = names - set(corpora)
    if unknown:
        raise ValueError(f"Unknown corpora: {sorted(unknown)}")
    output = {
        "schema_version": "2.1",
        "corpora": {
            name: evaluate_specification_surface(
                corpora[name][0], name, include_bigrams=corpora[name][1]
            )
            for name in sorted(names)
        },
    }
    path = ROOT / "results" / "specification_surface.json"
    path.write_text(
        json.dumps(output, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", action="append")
    arguments = parser.parse_args()
    main(set(arguments.corpus) if arguments.corpus else None)