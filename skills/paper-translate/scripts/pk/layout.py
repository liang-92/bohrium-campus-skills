"""Layout analysis: header/footer stripping, column detection, reading order.

The ordering method is a light XY-cut specialised for scholarly pages:

1. drop running heads, footers, page numbers and marginal line numbers;
2. find vertical gutters (fully whitespace columns) inside the text body;
3. walk the page top-to-bottom; a line that spans the gutters ends the current
   band, lines inside a band are emitted column by column;
4. glue consecutive lines of the same column into paragraphs and undo end-of-line
   hyphenation.

Every emitted block keeps its page and bbox so answers can point back to it.
"""

from __future__ import annotations

import re
import statistics
from typing import Any, Dict, List, Sequence, Tuple

LIGATURES = {
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl",
    "\ufb05": "st", "\ufb06": "st",
}
SOFT_HYPHEN = "\u00ad"
SENT_END = re.compile(r"[.!?。！？:：;；]\s*$")
PAGE_NUMBER = re.compile(r"^\s*(?:page\s*)?[-–—]?\s*[ivxlcdm]{1,7}\s*[-–—]?\s*$|^\s*\d{1,4}\s*$", re.I)
HEADING_NUM = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+[A-Z\u4e00-\u9fff]")


def clean_text(s: str) -> str:
    for k, v in LIGATURES.items():
        s = s.replace(k, v)
    s = s.replace(SOFT_HYPHEN, "")
    s = s.replace("\u00a0", " ").replace("\u2009", " ").replace("\u202f", " ")
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()


def _line_width(ln: Dict[str, Any]) -> float:
    b = ln["bbox"]
    return max(0.0, b[2] - b[0])


def _median(values: Sequence[float], default: float = 0.0) -> float:
    vals = [v for v in values if v > 0]
    return statistics.median(vals) if vals else default


def _norm_pattern(text: str) -> str:
    t = re.sub(r"\d+", "#", text.strip().lower())
    t = re.sub(r"\s+", " ", t)
    return t[:80]


BOILERPLATE = [
    re.compile(r"^\s*arxiv:\s*\d{4}\.\d{4,5}", re.I),
    re.compile(r"^\s*provided proper attribution", re.I),
    re.compile(r"^\s*reproduce the tables and figures", re.I),
    re.compile(r"^\s*(scholarly works?|journalistic)\b", re.I),
    re.compile(r"^\s*(preprint|under review|submitted to|to appear in)\b", re.I),
    re.compile(r"^\s*(copyright|©)\s*", re.I),
    re.compile(r"^\s*all rights reserved", re.I),
    re.compile(r"^\s*downloaded from\b", re.I),
    re.compile(r"^\s*(https?://|www\.)\S+$", re.I),
    re.compile(r"^\s*page \d+ of \d+", re.I),
]


def strip_running_heads(pages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Remove repeated top/bottom lines, page numbers, stamps and rotated margin text."""
    counts: Dict[str, int] = {}
    for p in pages:
        seen = set()
        h = p["height"]
        for ln in p["lines"]:
            top, bottom = ln["bbox"][1], ln["bbox"][3]
            if bottom < h * 0.085 or top > h * 0.925:
                key = _norm_pattern(ln["text"])
                if key and key not in seen:
                    seen.add(key)
                    counts[key] = counts.get(key, 0) + 1
    threshold = max(2, int(len(pages) * 0.3))
    repeated = {k for k, c in counts.items() if c >= threshold and len(k) > 1}

    removed: List[Dict[str, Any]] = []
    for p in pages:
        h = p["height"]
        keep = []
        for ln in p["lines"]:
            top, bottom = ln["bbox"][1], ln["bbox"][3]
            bw, bh = ln["bbox"][2] - ln["bbox"][0], ln["bbox"][3] - ln["bbox"][1]
            vertical = bh > 0 and bw > 0 and bh > bw * 2.5 and bh > 25
            in_margin = bottom < h * 0.085 or top > h * 0.925
            key = _norm_pattern(ln["text"])
            stamp = any(rx.match(ln["text"]) for rx in BOILERPLATE)
            # A vertical line in the outer margin is a margin note, not a
            # running head.  Only a rotated line that also sits in the top/bottom
            # margin (or matches a boilerplate stamp) is removed.
            rotated_stamp = vertical and (in_margin or stamp)
            is_footer = stamp or rotated_stamp or (in_margin and (key in repeated or PAGE_NUMBER.match(ln["text"])))
            if is_footer:
                # the line is taken out of the flow but never thrown away: text,
                # page and bbox all survive in header_footer[], so "the header is
                # gone" is a claim a reader can check against the PDF
                removed.append({"page": p["number"], "text": ln["text"].strip(),
                                "bbox": [round(float(v), 1) for v in ln["bbox"]],
                                "why": "stamp" if stamp else ("rotated" if vertical else
                                                             ("page-number" if PAGE_NUMBER.match(ln["text"])
                                                              else "repeated-margin"))})
            else:
                keep.append(ln)
        p["lines"] = keep
    return {"removed": removed[:800], "count": len(removed)}


def find_gutters(page: Dict[str, Any]) -> List[Tuple[float, float]]:
    """Return x-ranges that no *column* line crosses inside the body.

    Spanning elements (titles, full-width captions, wide tables) are excluded
    from the profile; otherwise one wide line erases the gutter of the page.
    """
    lines = page["lines"]
    if len(lines) < 6:
        return []
    x0 = min(l["bbox"][0] for l in lines)
    x1 = max(l["bbox"][2] for l in lines)
    span = x1 - x0
    if span < page["width"] * 0.35:
        return []
    narrow = [l for l in lines if (l["bbox"][2] - l["bbox"][0]) < span * 0.72]
    # On a single-column page almost every line is full width: no gutter to find.
    if len(narrow) < max(6, int(len(lines) * 0.4)):
        return []
    step = 1.5
    n = max(1, int(span / step))
    cover = [0] * (n + 1)
    for ln in narrow:
        a = int(max(0.0, (ln["bbox"][0] - x0)) / step)
        b = int(min(float(n), (ln["bbox"][2] - x0) / step))
        if b <= a:
            b = min(n, a + 1)
        for i in range(a, b + 1):
            cover[i] += 1
    body_lo = x0 + span * 0.15
    body_hi = x0 + span * 0.85
    thresholds = max(1, int(len(narrow) * 0.05))
    runs: List[Tuple[float, float]] = []
    run_start = None
    for i, c in enumerate(cover):
        x = x0 + i * step
        is_empty = c <= thresholds and body_lo <= x <= body_hi
        if is_empty and run_start is None:
            run_start = x
        elif not is_empty and run_start is not None:
            runs.append((round(run_start, 1), round(x, 1)))
            run_start = None
    if run_start is not None:
        runs.append((round(run_start, 1), round(x0 + n * step, 1)))

    y_lo = min(l["bbox"][1] for l in lines)
    y_hi = max(l["bbox"][3] for l in lines)
    y_span = max(1.0, y_hi - y_lo)
    gutters: List[Tuple[float, float]] = []
    for a, b in runs:
        if not (8 <= (b - a) <= 46):
            continue
        left = [l for l in narrow if l["bbox"][2] <= a + 2]
        right = [l for l in narrow if l["bbox"][0] >= b - 2]
        if len(left) < len(narrow) * 0.2 or len(right) < len(narrow) * 0.2:
            continue
        left_cov = (max(l["bbox"][3] for l in left) - min(l["bbox"][1] for l in left)) / y_span
        right_cov = (max(l["bbox"][3] for l in right) - min(l["bbox"][1] for l in right)) / y_span
        if left_cov < 0.35 or right_cov < 0.35:
            continue
        gutters.append((a, b))
    return sorted(gutters)


def _column_of(ln: Dict[str, Any], gutters: List[Tuple[float, float]]) -> int:
    cx = (ln["bbox"][0] + ln["bbox"][2]) / 2
    idx = 0
    for a, b in gutters:
        if cx > (a + b) / 2:
            idx += 1
    return idx


def _spans_gutters(ln: Dict[str, Any], gutters: List[Tuple[float, float]]) -> bool:
    a, b = ln["bbox"][0], ln["bbox"][2]
    return any(a < g0 and b > g1 for g0, g1 in gutters)


def _flatten_intervals(pairs: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    merged: List[Tuple[float, float]] = []
    for a, b in sorted(pairs):
        if b <= a:
            continue
        if merged and a <= merged[-1][1] + 0.6:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def _gaps(intervals: List[Tuple[float, float]], min_width: float) -> List[Tuple[float, float]]:
    flat = _flatten_intervals(intervals)
    out = []
    for (a1, b1), (a2, b2) in zip(flat, flat[1:]):
        if a2 - b1 >= min_width:
            out.append((b1, a2))
    return out


def _order_rec(lines: List[Dict[str, Any]], depth: int = 0) -> List[Dict[str, Any]]:
    """Recursive XY-cut: columns first, then bands, then plain y-order."""
    if len(lines) <= 1 or depth > 12:
        return sorted(lines, key=lambda l: (round(l["bbox"][1], 1), l["bbox"][0]))

    vgaps = _gaps([(l["bbox"][0], l["bbox"][2]) for l in lines], 6.0)
    hgaps = _gaps([(l["bbox"][1], l["bbox"][3]) for l in lines], 5.0)

    def try_v(g):
        left = [l for l in lines if l["bbox"][2] <= g[0] + 0.6]
        right = [l for l in lines if l["bbox"][0] >= g[1] - 0.6]
        if len(left) + len(right) != len(lines) or len(left) < 2 or len(right) < 2:
            return None
        return left, right

    def try_h(g):
        top = [l for l in lines if l["bbox"][3] <= g[0] + 0.6]
        bot = [l for l in lines if l["bbox"][1] >= g[1] - 0.6]
        if len(top) + len(bot) != len(lines) or len(top) < 1 or len(bot) < 1:
            return None
        return top, bot

    best_v = None
    for g in sorted(vgaps, key=lambda g: -(g[1] - g[0])):
        parts = try_v(g)
        if parts:
            best_v = (g, parts)
            break
    best_h = None
    for g in sorted(hgaps, key=lambda g: -(g[1] - g[0])):
        parts = try_h(g)
        if parts:
            best_h = (g, parts)
            break

    vw = (best_v[0][1] - best_v[0][0]) if best_v else -1
    hw = (best_h[0][1] - best_h[0][0]) if best_h else -1
    if best_v and (vw >= 8 or vw >= hw * 0.8):
        left, right = best_v[1]
        return _order_rec(left, depth + 1) + _order_rec(right, depth + 1)
    if best_h:
        top, bot = best_h[1]
        return _order_rec(top, depth + 1) + _order_rec(bot, depth + 1)
    if best_v:
        left, right = best_v[1]
        return _order_rec(left, depth + 1) + _order_rec(right, depth + 1)
    return sorted(lines, key=lambda l: (round(l["bbox"][1], 1), l["bbox"][0]))


def order_page(page: Dict[str, Any]) -> Dict[str, Any]:
    """Sort one page's lines into reading order; return details for the report."""
    lines = page["lines"]
    gutters = find_gutters(page)
    ordered = _order_rec(lines)
    # Some pages mix full-width headings with two body columns.  A gutter that
    # cuts through the heading makes `find_gutters` reject the whole page and
    # falls back to naive y-order, which interleaves the columns.  Detect the
    # two dominant left margins and order left column first.
    x0s = sorted(l["bbox"][0] for l in lines)
    groups = []
    for x in x0s:
        if not groups or x - groups[-1][-1] > 12:
            groups.append([x])
        else:
            groups[-1].append(x)
    if len(groups) >= 2:
        left_x, right_x = groups[0][0], groups[-1][0]
        n_left = len([x for x in x0s if abs(x - left_x) <= 6])
        n_right = len([x for x in x0s if abs(x - right_x) <= 6])
        if n_left >= 4 and n_right >= 4 and right_x - left_x > page["width"] * 0.3:
            mid = (left_x + right_x) / 2
            left = [l for l in lines if l["bbox"][0] < mid]
            right = [l for l in lines if l["bbox"][0] >= mid]
            ordered = (sorted(left, key=lambda l: (round(l["bbox"][1], 1), l["bbox"][0])) +
                       sorted(right, key=lambda l: (round(l["bbox"][1], 1), l["bbox"][0])))
            page["columns"] = 2
            page["order_rule"] = "column-split"
    for i, ln in enumerate(ordered):
        ln["col"] = 0 if ln["bbox"][0] < (page["width"] / 2 if page.get("columns") == 2 else 1e9) else 1
        ln["seq"] = i
    page["lines"] = ordered
    page["gutters"] = [[a, b] for a, b in gutters]
    page["columns"] = page.get("columns") or (len(gutters) + 1 if gutters else 1)
    page["bands"] = 1
    if page.get("order_rule") != "column-split":
        page["order_rule"] = "xy-cut" if gutters else "naive-y"
    return page


def _join(prev: str, nxt: str) -> str:
    if not prev:
        return nxt
    if prev.endswith(("-", "\u2010", "\u2011")):
        return prev[:-1] + nxt
    return prev + " " + nxt


def _left_edges(lines: List[Dict[str, Any]]) -> List[Tuple[float, float, float]]:
    """Cluster lines by left margin -> (x0, right_edge, count)."""
    clusters: List[List[Dict[str, Any]]] = []
    for ln in sorted(lines, key=lambda l: l["bbox"][0]):
        placed = False
        for c in clusters:
            if abs(c[-1]["bbox"][0] - ln["bbox"][0]) <= 6:
                c.append(ln)
                placed = True
                break
        if not placed:
            clusters.append([ln])
    out = []
    for c in clusters:
        xs = sorted(l["bbox"][0] for l in c)
        out.append((xs[len(xs) // 2], max(l["bbox"][2] for l in c), len(c)))
    return out


def _right_edge(x0: float, edges: List[Tuple[float, float, float]], fallback: float) -> float:
    best = None
    for ex0, ex1, cnt in edges:
        if abs(ex0 - x0) <= 8:
            if best is None or cnt > best[1]:
                best = (ex1, cnt)
    return best[0] if best else fallback


def _pitch(lines: List[Dict[str, Any]], edges) -> float:
    gaps = []
    for a, b in zip(lines, lines[1:]):
        if b["bbox"][1] > a["bbox"][1] and abs(a["bbox"][0] - b["bbox"][0]) <= 8:
            g = b["bbox"][1] - a["bbox"][3]
            if -2 < g < 30:
                gaps.append(max(0.0, g))
    if not gaps:
        return 3.0
    gaps.sort()
    return gaps[len(gaps) // 2]


# A caption is its own paragraph.  Without this guard a caption sitting directly
# under a paragraph gets merged into it, and then nothing can attribute it to the
# table or figure it belongs to -- which is exactly how an image-only table ends
# up reported as "no tables".
CAPTION_START = re.compile(r"^\s*(table|tab\.|figure|fig\.|algorithm|listing|scheme)\s*"
                           r"[\dIVXLC]+\s*[:.\uff1a]", re.I)


def build_blocks(pages: List[Dict[str, Any]], body_size: float) -> List[Dict[str, Any]]:
    """Group ordered lines into paragraph-level blocks with stable ids."""
    blocks: List[Dict[str, Any]] = []
    for p in pages:
        lines = p["lines"]
        edges = _left_edges(lines)
        pitch = _pitch(lines, edges)
        gap_limit = max(6.0, pitch * 2.0 + 2.0)
        current: List[Dict[str, Any]] = []
        counter = 0

        def flush(reason: str = "page-start", at: Dict[str, Any] | None = None):
            nonlocal current, counter
            if not current:
                return
            counter += 1
            text = ""
            for ln in current:
                text = _join(text, clean_text(ln["text"])) if text else clean_text(ln["text"])
            bbox = [min(l["bbox"][0] for l in current), min(l["bbox"][1] for l in current),
                    max(l["bbox"][2] for l in current), max(l["bbox"][3] for l in current)]
            sizes = [l["size"] for l in current if l["size"]]
            blocks.append({
                "id": f"p{p['number']:02d}-b{counter:03d}",
                "page": p["number"],
                "bbox": [round(v, 1) for v in bbox],
                "column": current[0].get("col", 0),
                "type": "body",
                "text": text,
                # Verbatim layer: the engine's own line strings, hyphen kept and
                # spacing untouched, so a reviewer can diff against the PDF text
                # layer character by character.  `text` is the cleaned view.
                "text_raw": "\n".join(l["text"] for l in current),
                "size": round(max(sizes) if sizes else body_size, 2),
                "bold": any(l.get("bold") for l in current),
                "lines": len(current),
                # Decision evidence: why this block starts where it does.
                # `break_reason` is kept for older readers; `para_break_reason`
                # is the name the review asked for, same value.
                "order_rule": p.get("order_rule", "naive-y"),
                "columns_on_page": p.get("columns", 1),
                "break_reason": reason,
                "para_break_reason": reason,
                # The exact line pair that caused the break.  Without it the
                # reason string is a claim; with it, the two y coordinates can
                # be re-measured on the page.
                "break_at": at or {},
                "hyphen_merged": False,
            })
            current = []

        for ln in lines:
            if not clean_text(ln["text"]):
                continue
            if not current:
                current = [ln]
                continue
            prev = current[-1]
            gap = ln["bbox"][1] - prev["bbox"][3]
            size_prev = prev.get("size") or body_size
            size_now = ln.get("size") or body_size
            same_style = abs(size_prev - size_now) < max(0.8, body_size * 0.08)
            right = _right_edge(prev["bbox"][0], edges, p["width"] * 0.5)
            # `right` is the column edge, but justified text often stops a
            # few points short of it.  Measure the column's own longest line:
            # a 16 pt shortfall is ordinary justification, not a paragraph end.
            same_col = [l for l in lines
                        if abs(l["bbox"][0] - prev["bbox"][0]) <= 8]
            column_right = max([l["bbox"][2] for l in same_col] or [right])
            short_prev = prev["bbox"][2] < column_right - max(12.0, size_prev * 1.8)
            big_block = len(current) >= 12 or sum(len(l["text"]) for l in current) > 1200
            reason = ""
            if CAPTION_START.match(clean_text(ln["text"])):
                reason = "caption-start"
            elif gap > gap_limit:
                reason = f"vertical-gap {gap:.1f}pt > {gap_limit:.1f}pt"
            elif short_prev:
                reason = "short-line (paragraph end)"
            elif not same_style:
                reason = f"font-size-change {size_prev:.1f}->{size_now:.1f}"
            elif big_block:
                reason = "block-size-cap"
            elif bool(prev.get("bold")) != bool(ln.get("bold")):
                reason = "weight-change"
            if not reason:
                current.append(ln)
            else:
                flush(reason, {"prev_line_bottom": round(prev["bbox"][3], 1),
                               "next_line_top": round(ln["bbox"][1], 1),
                               "gap_pt": round(gap, 1)})
                current = [ln]
        flush("page-start")
    return _merge_hyphen_continuations(blocks)


def _merge_hyphen_continuations(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Join a paragraph that was split in the middle of a hyphenated word."""
    out: List[Dict[str, Any]] = []
    for b in blocks:
        if out:
            prev = out[-1]
            tail = prev["text"].rstrip()
            head = b["text"].lstrip()
            cont = (tail.endswith(("-", "\u2010", "\u2011")) and head[:1].islower()
                    and prev["page"] == b["page"])
            if cont:
                kept = tail[:-1]
                prev["text"] = kept + head
                prev["text_raw"] = prev.get("text_raw", tail) + "\n" + b.get("text_raw", head)
                prev["hyphen_merged"] = True
                # The two halves, so a reviewer can see which real hyphen the
                # merge removed: `state-of-the-` + `art` -> `state-of-theart`
                # would be wrong, and this pair is what exposes it.
                prev["hyphen_pair"] = [kept.split()[-1][-14:] if kept.split() else "",
                                       (head.split() or [""])[0][:14]]
                prev["lines"] += b.get("lines", 0)
                prev["bbox"] = [min(prev["bbox"][0], b["bbox"][0]), min(prev["bbox"][1], b["bbox"][1]),
                                max(prev["bbox"][2], b["bbox"][2]), max(prev["bbox"][3], b["bbox"][3])]
                continue
        out.append(b)
    return out


def body_font_size(pages: List[Dict[str, Any]]) -> float:
    sizes: List[float] = []
    for p in pages:
        for ln in p["lines"]:
            if ln.get("size") and len(ln["text"].strip()) > 25:
                sizes.append(round(ln["size"], 1))
    if not sizes:
        return 10.0
    counts: Dict[float, int] = {}
    for s in sizes:
        counts[s] = counts.get(s, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


def is_heading(block: Dict[str, Any], body_size: float) -> bool:
    text = block["text"].strip()
    if block.get("type") in {"table", "reference", "formula"}:
        return False
    if not text or len(text) > 140:
        return False
    if block["lines"] > 3:
        return False
    size = block.get("size") or body_size
    bigger = size >= body_size * 1.12
    numbered = bool(HEADING_NUM.match(text))
    # A table cell such as `0.7 C` is numbered but is not a section heading.
    if numbered and re.match(r"^\d+(?:\.\d+)?\s+[A-Za-z]{1,2}$", text):
        return False
    # A caption can begin with a stray section number (`2 Table 1. ...`).
    if numbered and re.match(r"^\d+(?:\.\d+)?\s+(?:table|figure|fig\.)", text, re.I):
        return False
    # `3.0 Error bars come from ...` is a table cell + body sentence that the
    # two-column order joined; it is not a section title.
    if numbered and len(text.split()) > 4 and re.search(
            r"\b(come|comes|came|was|were|is|are|reported|measured|obtained|shown|from)\b",
            text, re.I):
        return False
    named = bool(re.match(r"^(abstract|摘要|keywords?|key\s*words?|关键词|introduction|related work|"
                          r"background|method(s|ology)?|experiments?|results?|discussion|conclusions?|"
                          r"references|acknowledg(e)?ments?|appendix|supplementary)\b", text, re.I))
    short_line = SENT_END.search(text) is None and len(text) < 90
    return bool((bigger and short_line) or numbered or named) and not text.endswith(",")
