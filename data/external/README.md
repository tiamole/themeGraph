# External Evaluation Data

The external validation package uses five datasets organized by epistemic
function: equivalence, directional entailment, prerequisite direction, and
event temporal precedence. Raw sentence pairs, concept pairs, passages, and
questions remain local and are never copied into publication artifacts.
`results/external_validation.json` contains aggregate counts, policy
transitions, source URLs, immutable revisions, and checksums only.

## Microsoft Research Paraphrase Corpus (MRPC)

- Purpose: natural paraphrase and non-paraphrase judgments for semantic
 equivalence policy transitions.
- Mirror: [GLUE MRPC Parquet files](https://huggingface.co/datasets/nyu-mll/glue/tree/refs%2Fconvert%2Fparquet/mrpc)
- Local files: `mrpc_train.parquet`, `mrpc_validation.parquet`, and
 `mrpc_test.parquet`.
- Records: 5,801 across all three GLUE splits.
- SHA-256: train `61fd41301e0e244b0420c4350a170c8e7cf64740335fc875a4af2d79af0df0af`;
 validation `33c007dbf5bfa8463d87a13e6226df8c0fcf2596c2cd39d0f3bb79754e00f50f`;
 test `a623ed1cbdf445b11f8e249acbf649d7d3a5ee58c918554c40cbd8307e488693`.
- License boundary: the maintained GLUE mirror does not state MRPC terms.
 Consequently, only aggregate statistics are redistributed by this project.

## PAWS-Wiki Labeled Final

- Purpose: adversarial high-overlap paraphrase and non-paraphrase judgments.
- Mirror: [PAWS Parquet files](https://huggingface.co/datasets/google-research-datasets/paws/tree/refs%2Fconvert%2Fparquet/labeled_final)
- Local files: `paws_train.parquet`, `paws_validation.parquet`, and
 `paws_test.parquet`.
- Records: 65,401 across all three labeled-final splits.
- SHA-256: train `8dc9ad3e5f30ad9a86b290fe236d528ef23a5751fec9a35d99cbacf68ba277cf`;
 validation `7760d829453764ba342a6f562809a8ed21c2c3eec3fd9ffa544089f145d42f6d`;
 test `ae342ff12bb84b84b95f468abf5db6cb7c7bd578271299fe9c99be75b8132f4d`.
- Terms: the repository license permits use for any purpose, requests
 acknowledgement of Google as the data source, and provides the dataset as-is
 without warranty. Publication artifacts contain aggregates only.

## Stanford Natural Language Inference (SNLI) 1.0

- Purpose: directional premise-to-hypothesis entailment judgments.
- Source: [Stanford SNLI project](https://nlp.stanford.edu/projects/snli/)
- Local file: `snli_1.0.zip`.
- Records: 569,033 labeled examples after excluding unlabeled consensus rows.
- SHA-256: `afb3d70a5af5d8de0d9d81e2637e0fb8c22d1235c2749d83125ca43dab0dbd3e`.
- License: [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
- Direction boundary: the label applies from premise to hypothesis. Reversal
 is refused unless independently annotated in the reversed direction.

## AL-CPL Concept Prerequisite Learning

- Purpose: expert-corrected directed prerequisite and non-prerequisite labels
 for Data Mining, Geometry, Physics, and Precalculus concepts.
- Source: [AL-CPL repository](https://github.com/harrylclc/AL-CPL-dataset).
- Pinned revision: `11397eaa3ea01c5e06fefcfc1c02a84f21164081`.
- Local file: `al_cpl_11397eaa.zip`.
- Records: 6,529 candidate pairs, including 2,002 positive prerequisite pairs.
- Domain counts: Data Mining 826/292, Geometry 1,681/524, Physics 1,962/487,
 and Precalculus 2,060/699 candidate/positive pairs.
- Orientation: in each source CSV row, the second column is a prerequisite of
 the first. ThemeGraph normalizes this to prerequisite source -> target concept.
- Preprocessing provenance: the repository README states that strict-partial-
 order properties were checked, labels were manually corrected where needed,
 reversed negatives were added for positives, and transitive positives were
 added. These are source preprocessing claims, not new judgments collected by
 this study.
- SHA-256: `de6a387d787469ecb54e42f95117b02bd617a7a76e7ac14ed75ee81523d4f161`.
- License: the repository README specifies
 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
 Publication artifacts contain aggregates and source hashes only.

## TORQUE Temporal Ordering Questions

- Purpose: adjudicated event-order evidence from explicit before/after
 questions, distinguished from textual mention order.
- Source: [TORQUE repository](https://github.com/qiangning/TORQUE-dataset).
- Pinned revision: `ab27019cc6a317fde3c879900499f02acce8b16d`.
- Local file: `torque_ab27019c.zip`.
- Evaluated split: adjudicated `dev.json` only, containing 145 passages and
 1,483 questions. The parser found 849 explicit before/after questions and
 1,928 usable answer-to-focus event relations; 184 directional questions had
 no answer indices and were not converted into positive relations.
- Test-label boundary: the public test split has annotations removed. It is not
 evaluated, inferred, or reconstructed.
- SHA-256: `5b3b1b2589e5da6067833d74da85e469be305f018bf7f12c4593e2d90ed6a503`.
- License: repository code and data are distributed under
 [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).
 Publication artifacts contain counts and hashes, not passages or questions.

## Rebuild

Install the external-validation dependency and regenerate aggregate results:

```powershell
pip install -e ".[external-validation]"
python scripts/run_external_validation.py
```

MRPC and PAWS labels cannot license entailment, temporal, prerequisite,
causal, theme, or analyst-benefit claims. SNLI labels cannot license temporal,
prerequisite, causal, theme, or analyst-benefit claims. AL-CPL labels cannot
license temporal, causal, entailment, theme, or analyst-benefit claims. TORQUE
labels cannot license prerequisite, causal, entailment, theme, or analyst-
benefit claims.

## O*NET 30.3 Database

- Source: [O*NET 30.3 Database](https://www.onetcenter.org/database.html)
- Archive: `db_30_3_text.zip`
- Downloaded: 2026-08-24
- Responsible organization: U.S. Department of Labor, Employment and Training Administration
- License: [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)
- License details: [O*NET 30.3 Database Content License](https://www.onetcenter.org/license_db.html)
- Local use: occupation descriptions and task statements are joined by O*NET-SOC code for cross-domain structural evaluation.

Required attribution for redistributed derived artifacts:

> This work includes information from the O*NET 30.3 Database by the U.S. Department of Labor, Employment and Training Administration. Used under the CC BY 4.0 license. O*NET is a trademark of USDOL/ETA. The ThemeGraph analysis modifies the source information by tokenizing it and deriving aggregate graph structures. USDOL/ETA has not approved, endorsed, or tested these modifications.

The electrical engineering job advertisement workbook is not stored in this directory. Its provenance and redistribution permission remain unverified, so it must not be redistributed with an artifact until those questions are resolved.
