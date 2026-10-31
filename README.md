# ThemeGraph

Auditable directed evidence graphs for dataset-independent thematic structure analysis.

ThemeGraph builds directed, evidence-bearing graphs over text corpora, extracts strongly
connected components, and ships with a claim-admissibility contract so that any downstream
claim (e.g., "theme," "prerequisite," "temporal order") is only ever shown when the evidence
contract that claim requires is actually satisfied.

## Interactive inspector

A live, in-browser inspector is hosted via GitHub Pages:

**https://tiamole.github.io/themeGraph/prototype/**

It lets researchers adjust confidence/lift thresholds, inspect strongly connected components,
compare against baselines, and trace every displayed relation back to its source evidence
excerpts. Nothing is uploaded: it runs entirely client-side against the pre-computed JSON
corpora in [`results/`](results).

## Repository layout

| Path | Contents |
| --- | --- |
| [`src/themegraph/`](src/themegraph) | Core library: graph construction, SCC extraction, claim-admissibility pipeline |
| [`prototype/`](prototype) | Static HTML/JS/CSS interactive inspector (hosted via GitHub Pages) |
| [`scripts/`](scripts) | Reproducibility scripts that regenerate the artifacts/results below |
| [`tests/`](tests) | Unit tests (`pytest`) |
| [`results/`](results) | Evaluation corpora and benchmark outputs consumed by the inspector |
| [`artifacts/`](artifacts) | Figures, tables, and data backing the manuscript |
| [`manuscript/`](manuscript) | CHI 2027 manuscript source (`.tex`) and compiled PDF |
| [`submission/`](submission) | Accessible-source submission bundle |
| [`data/external/`](data/external) | Public third-party NLP benchmark corpora used for external validation |

## Getting started

```powershell
pip install -e .[dev]
pytest
```

To regenerate the manuscript's core-corpus figures and tables (restricted to the four
corpora the paper claims; see the module docstring for why the job-ad workbook is
excluded), run:

```powershell
python scripts/build_core_corpus_figures.py
```

## Citation

Feyijimi, T., Feyijimi, C., Elesemoyo, I. O., & Brijmohan, Y. (2026). ThemeGraph: Semantic Representation Authorization for Directed Text-Analytic Graphs. Zenodo. [https://doi.org/10.5281/zenodo.23756602](https://doi.org/10.5281/zenodo.23756602)
