# Local benchmark

Public PDFs, default settings, one run each; `fingerprint` is a hash of block ids, pages and the first 80 characters, so an unchanged fingerprint across runs means deterministic output.

| file | pages | engine | chars/page | blocks | sections | depth | tables (captioned) | formulas | refs | figures | sec. inversions | block inversions | s | deterministic |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1706.03762v7.pdf | 15 | pymupdf 2.1 | 2566 | 268 | 27 | 3 | 4 (4) | 7 | 41 | 3 | 0 | 0 | 10.2 | yes |
| 1810.04805v2.pdf | 16 | pymupdf 2.1 | 3910 | 799 | 27 | 2 | 6 (6) | 1 | 58 | 6 | 0 | 0 | 11.03 | yes |
| acl2020.pdf | 6 | pymupdf 2.1 | 4046 | 174 | 17 | 2 | 3 (3) | 0 | 23 | 0 | 0 | 0 | 4.64 | yes |

## How to read this

- `block inversions` counts blocks whose page number goes backwards; 0 means the reading order never jumps between pages.
- `sec. inversions` counts section headings out of page order; non-zero means the heading detector mistook a running head or a caption for a section.
- Determinism matters because the platform runs each case three times per condition.

Regenerate with `python3 bench/run_bench.py`.
