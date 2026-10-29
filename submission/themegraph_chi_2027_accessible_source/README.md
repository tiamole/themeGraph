# ThemeGraph Accessible Manuscript Source

This package contains the anonymous review source for:

ThemeGraph: Semantic Representation Authorization for Directed Text-Analytic Graphs

Identifying author and affiliation metadata is omitted for anonymous review.

## Contents

- `manuscript/themegraph_chi_2027.tex`: primary manuscript source with ACM `\Description` text for all figures.
- `manuscript/references.bib`: bibliography database.
- `manuscript/acmart.cls` and `manuscript/ACM-Reference-Format.bst`: local ACM class and bibliography style.
- `manuscript/LICENSE`: ACM class license.
- `artifacts/figures/` and `artifacts/mappings/`: eight PDF figures referenced by the manuscript plus the supplementary evidence-transition figure.
- `artifacts/tables/`: eight generated TeX fragments required by the manuscript plus two supplementary table fragments.
- `ACCESSIBILITY_DESCRIPTIONS.md`: plain-text descriptions of the main-paper and supplementary figures and tables.

## Build

From the `manuscript` directory, run:

```text
pdflatex -interaction=nonstopmode -halt-on-error themegraph_chi_2027.tex
bibtex themegraph_chi_2027
pdflatex -interaction=nonstopmode -halt-on-error themegraph_chi_2027.tex
pdflatex -interaction=nonstopmode -halt-on-error themegraph_chi_2027.tex
```

The source uses ACM's anonymous review-manuscript format. The included figure descriptions are encoded with the `acmart` `\Description{...}` command.
