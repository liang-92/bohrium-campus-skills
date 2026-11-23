"""Post-checks the agent runs after it fills the parts only a model can write.

    python3 scripts/verify.py --out /app/output [--kind translate]

It never rewrites the deliverable; it reports what still breaks the contract so
the agent can fix exactly those items instead of re-reading the whole paper.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def load(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def check_translate(result: Dict[str, Any], doc: Dict[str, Any]) -> List[str]:
    problems: List[str] = []
    segs = result.get("segments") or []
    if not segs:
        return ["no segments in result.json"]
    filled = 0
    gloss: Dict[str, set] = {}
    for s in segs:
        zh = (s.get("translation") or "").strip()
        if not zh:
            continue
        filled += 1
        src = s.get("source", "")
        prot = s.get("protected") or {}
        for num in prot.get("numbers", [])[:20]:
            if num not in zh and num.replace(".", "") not in zh:
                problems.append(f"{s['seg']}: number {num} missing from translation")
        for cite in prot.get("citations", [])[:10]:
            core = re.sub(r"[\[\]()]", "", cite).split(",")[0].strip()
            if core and core not in zh:
                problems.append(f"{s['seg']}: citation {cite} missing")
        if len(zh) < max(10, len(src) * 0.25):
            problems.append(f"{s['seg']}: translation suspiciously short ({len(zh)} vs {len(src)})")
    if filled == 0:
        problems.append("no segment has a translation yet")
    for t in result.get("glossary") or []:
        zh = (t.get("zh") or "").strip()
        if zh:
            gloss.setdefault(t["term"].lower(), set()).add(zh)
    for term, vals in gloss.items():
        if len(vals) > 1:
            problems.append(f"glossary term '{term}' has conflicting renderings: {sorted(vals)}")
    return problems


def check_generic(result: Dict[str, Any], doc: Dict[str, Any]) -> List[str]:
    problems: List[str] = []
    if not result.get("case_id"):
        problems.append("case_id is empty")
    if result.get("status") not in {"complete", "partial", "unable", "refused"}:
        problems.append("status must be complete|partial|unable|refused")
    if result.get("status") == "complete" and not result.get("evidence"):
        problems.append("status=complete but evidence is empty")
    contract = result.get("output_contract") or {}
    empty = [k for k, v in contract.items() if v in (None, "", [], {})]
    if empty:
        problems.append("output_contract fields still empty: " + ", ".join(empty[:12]))
    d = (doc or {}).get("document") or {}
    ids = {b["id"] for b in d.get("blocks", [])}
    for i, item in enumerate(result.get("evidence") or []):
        b = item.get("block")
        if b and b.split("+")[0] not in ids:
            problems.append(f"evidence[{i}] unknown block {b}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--kind", default="translate")
    args = ap.parse_args()
    res = load(os.path.join(args.out, "result.json"))
    doc = load(os.path.join(args.out, "doc.json")) if os.path.exists(os.path.join(args.out, "doc.json")) else {}
    problems = check_translate(res, doc) if args.kind == "translate" else check_generic(res, doc)
    report = {"ok": not problems, "problems": problems[:60], "checked": args.kind}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
