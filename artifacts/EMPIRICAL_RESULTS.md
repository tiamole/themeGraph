# Empirical Results for Manuscript Development

## Evidence Boundary

These results were generated from maintained code and machine-readable outputs. The first author attests that the job-ad workbook combines a single cross-sectional scrape from Glassdoor and SimplyHired in June 2023. Embedded workbook metadata supports file authorship in part. Public release under CC BY 4.0 is planned but no public deposit URL is yet recorded. The sampling frame and per-row source platform are unavailable, so the dataset does not support population-level labor-market or platform-comparison inference.

## Workbook Audit

- Rows audited: 18,870.
- Missing Description values: 1 (0.005%).
- Duplicate complete rows beyond the first: 12,349 (65.44%).
- Duplicate Description instances beyond the first: 13,550 (71.81%).
- The workbook does not include a Skills field or a per-row source-platform field.

## Default Structural Results

| Corpus | Documents | Units | Nodes | Edges | SCCs | Largest SCC | Asymmetric edges |
| ------ | ---------: | ----: | ----: | ----: | ---: | ----------: | ---------------: |
| synthetic | 90 | 90 | 13 | 27 | 7 | 3 | 33.3% |
| glassdoor_simplyhired_jobs | 18870 | 826172 | 500 | 363 | 476 | 16 | 51.5% |
| glassdoor_simplyhired_jobs_unique_descriptions | 5317 | 221870 | 500 | 319 | 479 | 15 | 49.8% |
| onet_500 | 500 | 10919 | 500 | 213 | 485 | 8 | 78.4% |
| acmart | 18 | 12879 | 500 | 740 | 422 | 10 | 62.4% |
| python_stdlib_100 | 100 | 41946 | 500 | 233 | 479 | 4 | 77.7% |

## Duplication Sensitivity

Exact normalized-description deduplication retained 5,317 of 18,870 documents (28.2%). Extracted units fell from 826,172 to 221,870, retained edges from 363 to 319, and the default largest SCC from 16 to 15 nodes. This comparison demonstrates that duplicate handling changes measured graph structure and must be reported as an analysis decision.

## Threshold Sensitivity

- synthetic: largest SCC ranges from 3 to 3 nodes; retained edges range from 27 to 39.
- glassdoor_simplyhired_jobs: largest SCC ranges from 11 to 20 nodes; retained edges range from 204 to 564.
- glassdoor_simplyhired_jobs_unique_descriptions: largest SCC ranges from 10 to 20 nodes; retained edges range from 181 to 510.
- onet_500: largest SCC ranges from 3 to 10 nodes; retained edges range from 110 to 411.
- acmart: largest SCC ranges from 9 to 16 nodes; retained edges range from 627 to 1514.
- python_stdlib_100: largest SCC ranges from 4 to 5 nodes; retained edges range from 214 to 314.

## Direction and Claim Boundary

Global edge reversal preserves every SCC partition by graph-theoretic invariance. In the current unordered co-occurrence model, confidence orientation is determined by marginal prevalence. These results support descriptive lexical association and structural sensitivity claims only. They do not establish semantic direction, themes, causality, analyst benefit, or labor-market conditions.

## External Construct-Matched Policy Stress Tests

Five external datasets contribute 648,692 annotated or derived relation records across equivalence, directional entailment, prerequisite direction, and event temporal precedence. AL-CPL contains 6,529 candidate concept pairs with 2,002 positive prerequisite annotations. TORQUE contributes 1,928 usable relations from adjudicated dev annotations; public test answers were excluded. Matched annotations were admitted, while insufficiency, counterevidence, mention order, and unsupported reversal were refused. Cross-construct admission was zero.
PAWS contains 36,492 high-overlap non-paraphrases among 36,497 negative labels (99.986%), directly demonstrating why lexical overlap cannot serve as generic semantic evidence. These are policy-transition results, not predictive-model accuracy, universal relation truth, causal validity, human-benefit evidence, or normative policy validation. No raw sentence pairs, questions, passages, or concept pairs are redistributed.

## Expanded Specification Surface

- acmart: 24 configurations; 15 intersection edges, 9,118 union edges, 8,378 emergent edges; 289 union edges admitted and 8,829 qualified at the 0.80 gate; the default-reference split is 289/451.
- onet_500: 24 configurations; 0 intersection edges, 3,520 union edges, 3,307 emergent edges; 9 union edges admitted and 3,511 qualified at the 0.80 gate; the default-reference split is 9/204.
- python_stdlib_100: 24 configurations; 1 intersection edges, 1,063 union edges, 830 emergent edges; 135 union edges admitted and 928 qualified at the 0.80 gate; the default-reference split is 135/98.
- synthetic: 24 configurations; 27 intersection edges, 147 union edges, 120 emergent edges; 27 union edges admitted and 120 qualified at the 0.80 gate; the default-reference split is 27/0.

## Runtime Boundary

Wall time and traced Python allocation are measurements from the recorded Windows and Python environment. They are descriptive, not hardware-neutral benchmarks.
