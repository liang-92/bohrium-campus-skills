"""Post-checks the agent runs after it fills the parts only a model can write.

    python3 scripts/verify.py --out /app/output [--kind translate]

It never rewrites the deliverable.  Two kinds of answer come out of it:

* `problems` -- things that break the contract, to fix one by one;
* `checks`   -- numbers a reviewer can re-run to audit the parse itself:
  reading-order inversions, blocks whose bbox falls outside its declared column,
  evidence pages outside the document, and how much of the lossless layer
  survives.  These are *not* self-referential: each one re-reads doc.json's own
  geometry, which was produced by a different pass than the one being checked.
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


def check_translate(result: Dict[str, Any], doc: Dict[str, Any],
                    payload: Dict[str, Any] | None = None) -> List[str]:
    problems: List[str] = []
    # Slices the contract never asked for live in payload.json; look in both so
    # a declared contract does not hide the segments from the checker.
    payload = payload or {}
    body = result.get("output_contract") or {}
    segs = (result.get("segments") or body.get("segments")
            or payload.get("segments") or [])
    if isinstance(segs, dict):
        # the contract wraps declared arrays as {"items": [...], "count": n}
        segs = segs.get("items") or []
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
    for t in (result.get("glossary") or payload.get("glossary") or []):
        zh = (t.get("zh") or "").strip()
        if zh:
            gloss.setdefault(t["term"].lower(), set()).add(zh)
    for term, vals in gloss.items():
        if len(vals) > 1:
            problems.append(f"glossary term '{term}' has conflicting renderings: {sorted(vals)}")
    return problems


def _float(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def audit_geometry(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Re-read the parse's own geometry and report what does not add up."""
    d = (doc or {}).get("document") or {}
    blocks = d.get("blocks") or []
    stats = {p.get("page"): p for p in (d.get("page_stats") or [])}
    out_of_page, column_mismatch, inversions = [], [], []
    by_page: Dict[int, List[Dict[str, Any]]] = {}
    in_table = 0
    in_table = 0
    for b in blocks:
        bb = b.get("bbox")
        if not bb or len(bb) != 4:
            continue
        if b.get("in_table"):
            in_table += 1
            continue          # a table region is read column-wise on purpose
        if b.get("in_table"):
            in_table += 1
            continue          # a table region is read column-wise on purpose
        x0, y0, x1, y1 = (_float(v) for v in bb)
        st = stats.get(b.get("page")) or {}
        w, h = _float(st.get("w")), _float(st.get("h"))
        if not (x0 < x1 and y0 < y1) or (w and (x0 < -2 or x1 > w + 2)) \
                or (h and (y0 < -2 or y1 > h + 2)):
            out_of_page.append(b.get("id"))
        gutters = st.get("gutters") or []
        col = b.get("column")
        if gutters and col is not None and int(st.get("columns") or 1) > 1:
            g = gutters[0]
            if isinstance(g, (list, tuple)) and len(g) >= 2:
                g = (_float(g[0]) + _float(g[1])) / 2.0
            else:
                g = _float(g)
            centre = (x0 + x1) / 2
            if col == 0 and centre > g + 12:
                column_mismatch.append(b.get("id"))
            elif col == 1 and centre < g - 12:
                column_mismatch.append(b.get("id"))
            # A block that straddles the gutter (a full-width figure, a banner)
            # starts a new band, so its y cannot be compared to column content.
            if w and (x1 - x0) > 0.55 * w:
                continue
        by_page.setdefault(int(b.get("page") or 0), []).append(
            {"id": b.get("id"), "y": y0, "col": col})
    for page, items in by_page.items():
        prev: Dict[Any, float] = {}
        for it in items:
            key = it["col"]
            if key in prev and it["y"] < prev[key] - 5:
                inversions.append(it["id"])
            prev[key] = it["y"]
    return {"blocks_with_bbox": sum(1 for b in blocks if b.get("bbox")),
            "blocks_in_table_regions": in_table,
            "blocks_in_table_regions": in_table,
            "bbox_out_of_page": out_of_page[:10],
            "column_mismatch": column_mismatch[:10],
            "reading_order_inversions": inversions[:10],
            "reading_order_inversion_count": len(inversions),
            "column_mismatch_count": len(column_mismatch),
            "bbox_out_of_page_count": len(out_of_page)}


def audit_contract(result: Dict[str, Any], doc: Dict[str, Any]) -> Dict[str, Any]:
    case = (doc or {}).get("case") or {}
    declared: List[str] = []
    node = case.get("output_contract")
    if isinstance(node, dict):
        declared = list(node)
    elif isinstance(node, list):
        declared = [str(x) if isinstance(x, str) else str(x.get("name"))
                    for x in node]
    body = result.get("output_contract") or {}
    status = result.get("field_status") or {}
    unsupported = [k for k, v in status.items()
                   if isinstance(v, dict) and v.get("method") == "unsupported"]
    return {"declared": declared,
            "missing": [k for k in declared if k not in body],
            "undeclared": [k for k in body if declared and k not in declared],
            "unsupported": unsupported,
            "null_values": [k for k, v in body.items() if v is None]}


def check_generic(result: Dict[str, Any], doc: Dict[str, Any]) -> List[str]:
    problems: List[str] = []
    if not result.get("case_id"):
        problems.append("case_id is empty")
    if result.get("status") not in {"complete", "partial", "unable", "refused"}:
        problems.append("status must be complete|partial|unable|refused")
    if result.get("status") == "complete" and not result.get("evidence"):
        problems.append("status=complete but evidence is empty")
    contract = result.get("output_contract") or {}
    # Only `null` is a hole. An empty list means "looked, there is none", which
    # is a real answer -- flagging it would push an agent to invent content.
    nulls = [k for k, v in contract.items() if v is None]
    if nulls:
        problems.append("output_contract fields left null: " + ", ".join(nulls[:12]))
    c = audit_contract(result, doc)
    if c["missing"]:
        problems.append("declared contract field(s) absent: " + ", ".join(c["missing"][:12]))
    if c["undeclared"]:
        problems.append("output_contract has keys the case never declared: "
                        + ", ".join(c["undeclared"][:12]))
    d = (doc or {}).get("document") or {}
    ids = {b["id"] for b in d.get("blocks", [])}
    for i, item in enumerate(result.get("evidence") or []):
        b = item.get("block")
        if b and b.split("+")[0] not in ids:
            problems.append(f"evidence[{i}] unknown block {b}")
        page = item.get("page")
        if page and d.get("source", {}).get("pages") and \
                not 1 <= int(page) <= int(d["source"]["pages"]):
            problems.append(f"evidence[{i}] page {page} outside 1..{d['source']['pages']}")
    g = audit_geometry(doc)
    if g["bbox_out_of_page_count"]:
        problems.append(f"{g['bbox_out_of_page_count']} block(s) have a bbox outside the "
                        f"page: {g['bbox_out_of_page'][:6]}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--kind", default="translate")
    args = ap.parse_args()
    res = load(os.path.join(args.out, "result.json"))
    docp = os.path.join(args.out, "doc.json")
    doc = load(docp) if os.path.exists(docp) else {}
    payp = os.path.join(args.out, "payload.json")
    payload = load(payp) if os.path.exists(payp) else {}
    d = (doc or {}).get("document") or {}
    problems = (check_translate(res, doc, payload) if args.kind == "translate"
                else check_generic(res, doc))
    checks = {
        "geometry": audit_geometry(doc),
        "contract": audit_contract(res, doc),
        "content": {"pages": d.get("source", {}).get("pages"),
                    "blocks": len(d.get("blocks") or []),
                    "tables": len(d.get("tables") or []),
                    "figures": len(d.get("figures") or []),
                    "formulas": len(d.get("formulas") or []),
                    "references": len(d.get("references") or []),
                    "verbatim_chars": d.get("verbatim_chars")},
    }
    report = {"ok": not problems, "problems": problems[:60], "checked": args.kind,
              "checks": checks}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
