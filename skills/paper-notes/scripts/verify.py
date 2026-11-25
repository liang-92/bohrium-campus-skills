"""Post-checks the agent runs after it fills the parts only a model can write.

    python3 scripts/verify.py --out /app/output [--kind translate] [--pdf x.pdf]

It never rewrites the deliverable.  Three kinds of answer come out of it:

* `problems` -- things that break the contract, to fix one by one;
* `checks`   -- numbers a reviewer can re-run to audit the parse itself:
  reading-order inversions, blocks whose bbox falls outside its declared column,
  evidence pages outside the document, and how much of the lossless layer
  survives;
* `independent` -- a second opinion that does **not** read doc.json: it reopens
  the PDF, re-extracts its text layer, and compares characters and table cells
  against what the deliverable claims.  Everything else here is
  self-consistency; this section is the one that can disagree with us.
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

LIGATURES = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi",
             "\ufb04": "ffl", "\ufb05": "st", "\ufb06": "st"}


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
    for b in blocks:
        bb = b.get("bbox")
        if not bb or len(bb) != 4:
            continue
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
            "bbox_out_of_page": out_of_page[:10],
            "column_mismatch": column_mismatch[:10],
            "reading_order_inversions": inversions[:10],
            "reading_order_inversion_count": len(inversions),
            "column_mismatch_count": len(column_mismatch),
            "bbox_out_of_page_count": len(out_of_page)}


def audit_decisions(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Replay the per-block decision trace against the blocks themselves.

    Each block records *why* it ended where it did (`para_break_reason`), which
    pass read the page (`engine`), and whether a line-break hyphen was joined
    (`hyphen_merged` + `hyphen_pair`).  Two of those claims are decidable, so
    they are replayed instead of trusted:

    * `vertical-gap 10.7pt > 6.0pt` -- the block stores the two line coordinates
      that triggered the break (`break_at`); they must reproduce 10.7pt and the
      gap must really exceed its limit;
    * `hyphen_merged` -- both halves named in `hyphen_pair` must appear in the
      merged text.

    `short-line` needs the raw line widths, which doc.json does not keep, and
    `caption-start` / `block-size-cap` depend on the *flush* order, which is
    re-cut when heading fragments merge; all three are counted but not replayed,
    and the report says so instead of pretending they were checked.
    """
    d = (doc or {}).get("document") or {}
    blocks = d.get("blocks") or []
    reasons: Dict[str, int] = {}
    engines: Dict[str, int] = {}
    rules: Dict[str, int] = {}
    failures: List[str] = []
    gap_re = re.compile(r"vertical-gap ([\d.]+)pt > ([\d.]+)pt")
    merged = 0
    checked = 0
    missing_reason = 0
    missing_at = 0
    for b in blocks:
        bid = b.get("id") or "?"
        reason = b.get("para_break_reason") or b.get("break_reason") or ""
        if not reason:
            missing_reason += 1
        else:
            head = reason.split(" ")[0]
            reasons[head] = reasons.get(head, 0) + 1
        eng = str(b.get("engine") or "unknown")
        engines[eng] = engines.get(eng, 0) + 1
        rule = b.get("order_rule") or "unset"
        rules[rule] = rules.get(rule, 0) + 1
        if b.get("hyphen_merged"):
            merged += 1
            pair = b.get("hyphen_pair") or []
            joined = (b.get("text") or "").replace(" ", "")
            halves = [p for p in pair if p and p.replace(" ", "")]
            checked += 1
            if not halves or not all(h.replace(" ", "") in joined for h in halves):
                failures.append(f"{bid}: hyphen_merged but the pair is not in the text")
        m = gap_re.match(reason)
        if m and b.get("break_at"):
            claimed, limit = float(m.group(1)), float(m.group(2))
            at = b["break_at"]
            gap = round(_float(at.get("next_line_top")) - _float(at.get("prev_line_bottom")), 1)
            checked += 1
            # the two coordinates the block recorded must reproduce the number
            # printed in the reason, and the gap must really exceed its limit
            if abs(gap - claimed) > 0.2 or abs(_float(at.get("gap_pt")) - claimed) > 0.2 \
                    or not claimed > limit:
                failures.append(f"{bid}: claims a {claimed}pt gap, recorded lines say {gap}pt")
        if reason and not reason.startswith("page-start") and not b.get("break_at"):
            missing_at += 1
    return {"blocks": len(blocks),
            "missing_break_reason": missing_reason,
            "pages_covered": len({b.get("page") for b in blocks}),
            "reasons": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
            "engines": engines,
            "order_rules": rules,
            "claims_replayed": checked,
            "hyphen_merged_blocks": merged,
            "breaks_without_coordinates": missing_at,
            "not_replayable": [
                "short-line (needs line widths, not in doc.json)",
                "caption-start / block-size-cap (block order is re-cut when heading "
                "fragments merge, so list adjacency is not the flush adjacency)",
            ],
            "replay_failures": failures[:10],
            "replay_failure_count": len(failures)}


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


def _pack(text: str):
    from collections import Counter
    for k, v in LIGATURES.items():
        text = text.replace(k, v)
    return Counter(c for c in text if not c.isspace())


def _cross_engine(path: str) -> Dict[str, Any]:
    """Read the same file with a second, independent engine.

    If two engines disagree on how many characters a page carries, one of them
    is wrong -- and a deliverable built on the wrong one should not claim
    `complete`.  pypdf is pure Python, so it fails differently from PyMuPDF
    (different parser, different font handling), which is exactly what makes the
    comparison worth printing.
    """
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return {"name": "pypdf", "available": False, "note": "pypdf not installed"}
    try:
        reader = PdfReader(path)
        if getattr(reader, "is_encrypted", False):
            return {"name": "pypdf", "available": False, "note": "encrypted"}
        per_page = []
        for page in reader.pages:
            try:
                per_page.append(len(re.sub(r"\s+", "", page.extract_text() or "")))
            except Exception:
                per_page.append(0)
        return {"name": "pypdf", "available": True, "pages": len(per_page),
                "chars": sum(per_page)}
    except Exception as exc:
        return {"name": "pypdf", "available": False, "note": type(exc).__name__}


def audit_independent(doc: Dict[str, Any], pdf_path: str = "") -> Dict[str, Any]:
    """Reopen the PDF and compare its own text layer with the deliverable.

    This is the only check here that can contradict our own output: it does not
    trust blocks, it re-extracts the page text with a fresh engine pass and asks
    (a) are the claimed characters really on the page, and (b) is each table
    cell really on the page it names.  Skipped -- with a reason, not silently --
    when the PDF or PyMuPDF is unavailable.
    """
    d = (doc or {}).get("document") or {}
    src_meta = d.get("source") or {}
    path = pdf_path or src_meta.get("path") or ""
    out: Dict[str, Any] = {"source": "pdf-reopen", "available": False,
                           "pdf": os.path.basename(path) if path else ""}
    if not path or not os.path.exists(path):
        out["note"] = "PDF not reachable from the output; independent check skipped"
        return out
    try:
        import fitz  # type: ignore
    except Exception:
        out["note"] = "PyMuPDF not installed; independent check skipped"
        return out
    try:
        src = fitz.open(path)
    except Exception as exc:
        out["note"] = f"PDF could not be reopened: {type(exc).__name__}"
        return out
    try:
        if getattr(src, "needs_pass", False):
            out["note"] = "PDF is encrypted; text layer not readable without the password"
            return out
        stats = {p.get("page"): p for p in (d.get("page_stats") or [])}
        delivered: Dict[Any, List[str]] = {}
        removed: Dict[Any, List[str]] = {}
        for b in d.get("blocks") or []:
            delivered.setdefault(b.get("page"), []).append(
                b.get("text_raw") or b.get("text") or "")
        for h in d.get("header_footer") or []:
            removed.setdefault(h.get("page"), []).append(h.get("text") or "")
        layer_all, body_all, head_all = _pack(""), _pack(""), _pack("")
        compared, skipped = 0, []
        for i, page in enumerate(src):
            no = i + 1
            st = stats.get(no) or {}
            if st.get("filled_by") == "ocr":
                skipped.append(no)        # no text layer to compare against
                continue
            text = page.get_text("text") or ""
            if len(text.strip()) < 20:
                skipped.append(no)
                continue
            layer_all += _pack(text)
            body_all += _pack(" ".join(delivered.get(no, [])))
            head_all += _pack(" ".join(removed.get(no, [])))
            compared += 1
        total = sum(layer_all.values())
        missing = layer_all - body_all - head_all
        extra = body_all - layer_all
        out.update({
            "available": True,
            "pages_compared": compared,
            "pages_skipped": skipped[:12],
            "chars_in_pdf": total,
            "chars_in_blocks": sum(body_all.values()),
            "chars_in_header_footer": sum(head_all.values()),
            "chars_missing": sum(missing.values()),
            "chars_extra": sum(extra.values()),
            "verbatim_ratio": round((total - sum(missing.values())) / total, 4) if total else None,
            "missing_top": missing.most_common(8),
        })
        # table cells: every cell must be locatable on the page it claims.
        # A merged cell ("BLEU EN-DE EN-FR") is several columns joined, so the
        # whole string need not appear contiguously; the fair test is that every
        # token is on the page.  The strict, contiguous count is kept separately
        # so the weaker test cannot hide a cell that is not on the page.
        cells = strict = located = 0
        bad: List[str] = []
        for t in d.get("tables") or []:
            no = int(t.get("page") or 0)
            if not 1 <= no <= src.page_count:
                continue
            hay = re.sub(r"\s+", "", (src.load_page(no - 1).get_text("text") or "")).lower()
            for row in (t.get("rows") or []):
                for cell in row:
                    cell = (cell or "").strip()
                    if len(cell) < 2:
                        continue
                    cells += 1
                    flat = re.sub(r"\s+", "", cell).lower()
                    if flat in hay:
                        strict += 1
                        located += 1
                        continue
                    toks = [x for x in re.split(r"\s+", cell) if len(x) >= 2]
                    if toks and all(re.sub(r"\s+", "", x).lower() in hay for x in toks):
                        located += 1
                    elif len(bad) < 8:
                        bad.append(f"{t.get('id')}: {cell[:24]}")
        out["table_cells"] = {
            "checked": cells,
            "found_all_tokens": located,
            "found_verbatim": strict,
            "rate": round(located / cells, 4) if cells else None,
            "verbatim_rate": round(strict / cells, 4) if cells else None,
            "not_found": bad,
            "note": "rate = every token of the cell is on that page; "
                    "verbatim_rate = the whole cell string appears contiguously",
        }
        cross = _cross_engine(path)
        if cross.get("available") and total:
            cross["ratio_vs_pymupdf"] = round(cross["chars"] / total, 4)
            if cross["chars"] and cross["ratio_vs_pymupdf"] < 0.9:
                out["engine_disagreement"] = (
                    f"pypdf reads {cross['chars']} chars, PyMuPDF {total}; "
                    f"the two engines disagree on this file")
        out["cross_engine"] = cross
        return out
    except Exception as exc:      # never let the checker be the thing that crashes
        out["note"] = f"independent check failed: {type(exc).__name__}: {exc}"
        return out
    finally:
        try:
            src.close()
        except Exception:
            pass


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
    ap.add_argument("--pdf", default="", help="PDF to reopen; defaults to doc.json's source path")
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
        "decisions": audit_decisions(doc),
        "contract": audit_contract(res, doc),
        "content": {"pages": d.get("source", {}).get("pages"),
                    "blocks": len(d.get("blocks") or []),
                    "tables": len(d.get("tables") or []),
                    "figures": len(d.get("figures") or []),
                    "formulas": len(d.get("formulas") or []),
                    "references": len(d.get("references") or []),
                    "verbatim_chars": d.get("verbatim_chars")},
    }
    independent = audit_independent(doc, args.pdf)
    report = {"ok": not problems, "problems": problems[:60], "checked": args.kind,
              "checks": checks, "independent": independent}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
