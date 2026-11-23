"""Local benchmark for paperkit.

Not a leaderboard — a regression harness. It answers four questions on public
PDFs: did we get text, did reading order survive, did structure get found, and
is the output deterministic across runs.

    python3 bench/run_bench.py --pdfs bench/pdfs --out docs/benchmark.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))

from paperkit.document import analyze_path  # noqa: E402


def order_score(doc):
    """Sections should appear in page order; blocks should follow section order."""
    pages = [s["page"] for s in doc["sections"]]
    inversions = sum(1 for a, b in zip(pages, pages[1:]) if b < a)
    blk_pages = [b["page"] for b in doc["blocks"]]
    block_inv = sum(1 for a, b in zip(blk_pages, blk_pages[1:]) if b < a)
    return {"section_inversions": inversions, "block_page_inversions": block_inv}


def run_one(path):
    t0 = time.time()
    doc = analyze_path(path)
    dt = time.time() - t0
    blocks = doc["blocks"]
    text = "".join(b["text"] for b in blocks)
    fingerprint = hashlib.sha256(
        "\n".join(f"{b['id']}|{b['page']}|{b['text'][:80]}" for b in blocks).encode("utf-8")
    ).hexdigest()[:12]
    caps = sum(1 for t in doc["tables"] if t.get("caption"))
    return {
        "file": os.path.basename(path),
        "pages": doc["source"]["pages"],
        "engine": doc["source"]["backend"],
        "chars": len(text),
        "chars_per_page": round(len(text) / max(1, doc["source"]["pages"])),
        "blocks": len(blocks),
        "sections": len(doc["sections"]),
        "max_depth": max([s["level"] for s in doc["sections"]], default=0),
        "tables": len(doc["tables"]),
        "tables_with_caption": caps,
        "formulas": len(doc["formulas"]),
        "references": len(doc["references"]),
        "figures": len(doc["figures"]),
        "running_heads_removed": doc.get("running_heads_removed", 0),
        "seconds": round(dt, 2),
        "fingerprint": fingerprint,
        **order_score(doc),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdfs", default=os.path.join(ROOT, "bench", "pdfs"))
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "benchmark.md"))
    args = ap.parse_args()

    rows = []
    for fn in sorted(os.listdir(args.pdfs)):
        if not fn.lower().endswith(".pdf"):
            continue
        try:
            rows.append(run_one(os.path.join(args.pdfs, fn)))
        except Exception as exc:
            rows.append({"file": fn, "error": f"{type(exc).__name__}: {exc}"})

    # determinism: second pass must produce the same fingerprint
    determined = {}
    for r in rows:
        if "error" in r:
            continue
        again = run_one(os.path.join(args.pdfs, r["file"]))
        determined[r["file"]] = again["fingerprint"] == r["fingerprint"]

    lines = ["# Local benchmark", "",
             "Public PDFs, default settings, one run each; `fingerprint` is a hash of block ids, "
             "pages and the first 80 characters, so an unchanged fingerprint across runs means "
             "deterministic output.", "",
             "| file | pages | engine | chars/page | blocks | sections | depth | tables (captioned) | formulas | refs | figures | sec. inversions | block inversions | s | deterministic |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if "error" in r:
            lines.append(f"| {r['file']} | — | — | — | — | — | — | — | — | — | — | — | — | — | error: {r['error']} |")
            continue
        lines.append("| {file} | {pages} | {engine} | {chars_per_page} | {blocks} | {sections} | {max_depth} | "
                     "{tables} ({tables_with_caption}) | {formulas} | {references} | {figures} | "
                     "{section_inversions} | {block_page_inversions} | {seconds} | {det} |".format(
                         det="yes" if determined.get(r["file"]) else "NO", **r))
    lines += ["", "## How to read this", "",
              "- `block inversions` counts blocks whose page number goes backwards; 0 means the "
              "reading order never jumps between pages.",
              "- `sec. inversions` counts section headings out of page order; non-zero means the "
              "heading detector mistook a running head or a caption for a section.",
              "- Determinism matters because the platform runs each case three times per condition.",
              "", "Regenerate with `python3 bench/run_bench.py`."]
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print(json.dumps({"rows": len(rows), "out": args.out,
                      "deterministic": all(determined.values()) if determined else False}, indent=2))


if __name__ == "__main__":
    main()
