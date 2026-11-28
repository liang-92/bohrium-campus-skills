# Local benchmark

Public PDFs, default settings, one run each; `fingerprint` is a hash of block ids, pages and the first 80 characters, so an unchanged fingerprint across runs means deterministic output.

| file | pages | engine | chars/page | blocks | sections | depth | tables (captioned) | formulas | refs | figures | sec. inversions | page regressions | column inversions | s | deterministic |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1706.03762v7.pdf | 15 | pymupdf 2.1 | 2587 | 213 | 27 | 3 | 4 (4) | 5 | 40 | 2 | 0 | 0 | 2 | 13.02 | yes |
| 1810.04805v2.pdf | 16 | pymupdf 2.1 | 3922 | 617 | 26 | 2 | 3 (3) | 11 | 87 | 5 | 0 | 0 | 35 | 21.51 | yes |
| acl2020.pdf | 6 | pymupdf 2.1 | 4049 | 156 | 15 | 2 | 3 (3) | 1 | 47 | 2 | 0 | 0 | 9 | 6.2 | yes |

## How to read this

- `page regressions` counts blocks whose page number goes backwards: 0 means the reading order never jumps back to an earlier page. It is a coarse guard, not a quality score — a plain y-sorted dump also scores 0 here.
- `column inversions` is the rubric's reading-order check: within one page and one column, a block that starts above the block before it. Table regions are excluded, because a table is read column-wise on purpose. This is the number to watch; the per-file breakdown with reasons is in `docs/baseline.md`.
- `sec. inversions` counts section headings out of page order; non-zero means the heading detector mistook a running head or a caption for a section.
- `figures` counts whole figures after sub-panels and decorative marks are dropped; vector charts are included, which is why BERT shows 5 rather than 0.
- Determinism matters because the platform runs each case three times per condition.

Regenerate with `python3 bench/run_bench.py`.
