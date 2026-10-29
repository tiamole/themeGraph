"""Build publication figures, tables, and their provenance manifest."""

from pathlib import Path

from themegraph.publication import build_publication_artifacts

if __name__ == "__main__":
    build_publication_artifacts(Path(__file__).resolve().parents[1])