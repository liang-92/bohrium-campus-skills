"""Higher-level structure: sections, tables, formulas, figures, references, metadata."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .layout import HEADING_NUM, SENT_END, is_heading

CAPTION_TABLE = re.compile(r"^\s*(table|tab\.|表)\s*([0-9]+[a-zA-Z]?|[IVXLC]+)\b[.:：]?", re.I)
CAPTION_FIG = re.compile(r"^\s*(figure|fig\.|图)\s*([0-9]+[a-zA-Z]?|[IVXLC]+)\b[.:：]?", re.I)
EQ_NUMBER = re.compile(r"[\(（]\s*(\d{1,3}[a-zA-Z]?)\s*[\)）]\s*$")
# some extractors put the equation number first ("(1) L = ...") because it is a
# separate text object at the right margin
EQ_LEAD = re.compile(r"^\s*[\(（]\s*(\d{1,3}[a-zA-Z]?)\s*[\)）]\s*")
ASCII_OPS = set("=+-*/^_[]<>≤≥")
REF_ENTRY = re.compile(r"^\s*(\[(\d{1,3})\]|(\d{1,3})\.)\s+\S")
DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
MATH_CHARS = set("∑∏∫√∞≈≠≤≥±×÷∂∇∈∉⊂⊃∪∩→←↔⇒⇔αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ·∙∗⊕⊗")

GREEK_TEX = {"α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta", "ε": r"\epsilon",
             "ϵ": r"\epsilon", "ζ": r"\zeta", "η": r"\eta", "θ": r"\theta", "λ": r"\lambda",
             "μ": r"\mu", "ν": r"\nu", "ξ": r"\xi", "π": r"\pi", "ρ": r"\rho", "σ": r"\sigma",
             "τ": r"\tau", "φ": r"\phi", "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega",
             "Γ": r"\Gamma", "Δ": r"\Delta", "Θ": r"\Theta", "Λ": r"\Lambda", "Σ": r"\Sigma",
             "Φ": r"\Phi", "Ψ": r"\Psi", "Ω": r"\Omega"}
SYM_TEX = {"×": r"\times", "·": r"\cdot", "∙": r"\cdot", "−": "-", "–": "-", "≤": r"\le",
           "≥": r"\ge", "≠": r"\neq", "≈": r"\approx", "∈": r"\in", "∉": r"\notin",
           "∑": r"\sum", "∏": r"\prod", "∫": r"\int", "∞": r"\infty", "∂": r"\partial",
           "±": r"\pm", "→": r"\to", "←": r"\leftarrow", "⇒": r"\Rightarrow",
           "∇": r"\nabla", "∝": r"\propto", "∼": r"\sim", "∪": r"\cup", "∩": r"\cap",
           "⊂": r"\subset", "∗": "*"}


def formula_to_tex(text: str) -> Tuple[str, int]:
    """Turn the extracted glyph string into compilable LaTeX.

    Sub/superscript fidelity is not recoverable from the text layer alone, so
    the result is marked low confidence; what this guarantees is that every
    character left in `tex` is ASCII and math-safe, so a formula can never
    break the whole LaTeX build.
    """
    s = re.sub(r"√\s*\(?\s*([A-Za-z0-9]+)\s*\)?", lambda m: r"\sqrt{%s}" % m.group(1), text)
    for k, v in {**GREEK_TEX, **SYM_TEX}.items():
        s = s.replace(k, v)
    s = s.replace("\\", "\x00")
    s = re.sub(r"([&%$#_{}])", r"\\\1", s)
    s = s.replace("\x00", "\\")
    dropped = 0
    out = []
    for ch in s:
        if ord(ch) < 128:
            out.append(ch)
        else:
            dropped += 1
    return "".join(out), dropped


def section_level(block: Dict[str, Any], body_size: float) -> int:
    text = block["text"].strip()
    m = HEADING_NUM.match(text)
    if m:
        return min(6, m.group(1).count(".") + 1)
    if re.match(r"^(abstract|摘要)\b", text, re.I):
        return 1
    if re.match(r"^(references|bibliography|参考文献|acknowledg)", text, re.I):
        return 1
    size = block.get("size") or body_size
    ratio = size / body_size if body_size else 1.0
    if ratio >= 1.45:
        return 1
    if ratio >= 1.25:
        return 2
    if ratio >= 1.10:
        return 3
    return 2


STRONG_MATH = set("∑∏∫√∞≈≠≤≥±×÷∂∇∈∉⊂⊃∪∩→←↔⇒⇔⊕⊗")
BARE_NUMBER = re.compile(r"^\s*\d{1,2}(?:\.\d{1,2}){0,3}\.?\s*$")


def merge_heading_fragments(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Join '3.1' + 'Encoder and Decoder Stacks' and similar split headings."""
    out: List[Dict[str, Any]] = []
    i = 0
    while i < len(blocks):
        b = blocks[i]
        nxt = blocks[i + 1] if i + 1 < len(blocks) else None
        if (nxt and BARE_NUMBER.match(b["text"]) and len(nxt["text"]) < 100
                and b["page"] == nxt["page"] and (nxt.get("size") or 0) >= (b.get("size") or 0) * 0.9):
            merged = dict(nxt)
            merged["text"] = b["text"].strip() + " " + nxt["text"].strip()
            merged["bbox"] = [min(b["bbox"][0], nxt["bbox"][0]), min(b["bbox"][1], nxt["bbox"][1]),
                              max(b["bbox"][2], nxt["bbox"][2]), max(b["bbox"][3], nxt["bbox"][3])]
            out.append(merged)
            i += 2
            continue
        out.append(b)
        i += 1
    return out


def build_sections(blocks: List[Dict[str, Any]], body_size: float) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Annotate blocks with section paths; return (sections, blocks)."""
    blocks = merge_heading_fragments(blocks)
    sections: List[Dict[str, Any]] = []
    stack: List[Dict[str, Any]] = []
    for b in blocks:
        if is_heading(b, body_size):
            level = section_level(b, body_size)
            b["type"] = "heading"
            b["level"] = level
            while stack and stack[-1]["level"] >= level:
                stack.pop()
            sec = {"level": level, "title": b["text"].strip(), "page": b["page"],
                   "block": b["id"], "parent": stack[-1]["block"] if stack else None}
            sections.append(sec)
            stack.append(sec)
        path = " > ".join(s["title"] for s in stack) if stack else ""
        b["section"] = path
    return sections, blocks


def detect_tables_from_lines(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fallback table reader: consecutive lines with 2+ wide x-gaps."""
    out: List[Dict[str, Any]] = []
    for p in pages:
        lines = sorted(p["lines"], key=lambda l: (l["bbox"][1], l["bbox"][0]))
        rows: List[Dict[str, Any]] = []
        group: List[Dict[str, Any]] = []

        def flush():
            nonlocal group
            if len(group) >= 2:
                cells = []
                for ln in group:
                    parts = re.split(r"\s{2,}", ln["text"].strip())
                    cells.append([c for c in parts if c])
                if sum(len(c) for c in cells) >= 4:
                    out.append({"page": p["number"], "bbox": [
                        min(l["bbox"][0] for l in group), min(l["bbox"][1] for l in group),
                        max(l["bbox"][2] for l in group), max(l["bbox"][3] for l in group)],
                        "rows": cells, "source": "line-gap"})
            group = []

        for ln in lines:
            parts = re.split(r"\s{2,}", ln["text"].strip())
            wide = len(parts) >= 2 and (ln["bbox"][2] - ln["bbox"][0]) > p["width"] * 0.25
            if wide:
                group.append(ln)
            else:
                flush()
        flush()
    return out


_CELL_PUNCT = {".", ",", "-", "–", "/", ")", "(", "%", ":", ";"}


def _join_cell(text: str) -> str:
    """Join the lines of one cell without breaking decimals or hyphenated words.

    PyMuPDF hands back "0\\n.\\n1" for 0.1 and "state-of-the-\\nart" for a wrapped
    word; a blind space-join turns those into "0 . 1" and "state-of-the- art".
    """
    out = ""
    for line in (text or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        if not out:
            out = line
        elif line in _CELL_PUNCT or out.endswith("-"):
            out += line
        else:
            out += " " + line
    return out


def split_multiline_rows(rows: List[List[str]], max_split: int = 8) -> List[List[str]]:
    """Expand a row whose every cell holds N stacked values into N rows.

    Borderless tables come back from the engine as one row per *row group*:
    the Transformer layer table is 2 rows instead of 5, and every cell of the
    data row contains the four layer names stacked on top of each other.  When
    two or more non-empty cells share the same line count, that is a row group,
    not a single row.
    """
    out: List[List[str]] = []
    for r in rows:
        cols = [(c or "").split("\n") for c in r]
        counts = [len(c) for c in cols if any(x.strip() for x in c)]
        k = counts[0] if counts and len(set(counts)) == 1 else 1
        if 2 <= k <= max_split and len(counts) >= 2:
            for i in range(k):
                out.append([(c[i] if i < len(c) else "") for c in cols])
        else:
            out.append(["\n".join(c) for c in cols])
    return out


def normalize_table(rows: List[List[str]], max_rows: int = 200, max_cols: int = 30) -> Dict[str, Any]:
    rows = split_multiline_rows([r[:max_cols] for r in rows[:max_rows]])
    rows = [[_join_cell(c).strip() for c in r] for r in rows][:max_rows]
    width = max((len(r) for r in rows), default=0)
    rows = [r + [""] * (width - len(r)) for r in rows]
    header = rows[0] if rows else []

    def esc(s: str) -> str:
        return s.replace("|", "\\|")

    md = []
    if rows:
        md.append("| " + " | ".join(esc(c) for c in header) + " |")
        md.append("|" + "|".join(["---"] * width) + "|")
        for r in rows[1:]:
            md.append("| " + " | ".join(esc(c) for c in r) + " |")
    return {"header": header, "rows": rows, "markdown": "\n".join(md), "n_rows": len(rows), "n_cols": width}


def attach_captions(blocks: List[Dict[str, Any]], tables: List[Dict[str, Any]],
                    figures: List[Dict[str, Any]]) -> None:
    by_page: Dict[int, List[Dict[str, Any]]] = {}
    for b in blocks:
        by_page.setdefault(b["page"], []).append(b)
    for t in tables:
        cap = None
        for b in by_page.get(t["page"], []):
            if CAPTION_TABLE.match(b["text"]):
                if t.get("bbox"):
                    if b["bbox"][1] < t["bbox"][1] and t["bbox"][1] - b["bbox"][3] < 90:
                        cap = b
                    elif cap is None and abs(b["bbox"][1] - t["bbox"][3]) < 90:
                        cap = b
                elif cap is None:
                    cap = b
        t["caption"] = cap["text"] if cap else ""
        t["caption_block"] = cap["id"] if cap else None
    for f in figures:
        cap = None
        best = None
        for b in by_page.get(f["page"], []):
            if not CAPTION_FIG.match(b["text"]):
                continue
            bb, fb = b.get("bbox"), f.get("bbox")
            if not bb or not fb:
                if cap is None:
                    cap = b
                continue
            # horizontal overlap is what distinguishes "the caption of this
            # figure" from "the caption of the figure in the other column"
            overlap = min(bb[2], fb[2]) - max(bb[0], fb[0])
            if bb[2] > bb[0] and overlap / (bb[2] - bb[0]) < 0.3:
                continue
            below = bb[1] - fb[3]
            above = fb[1] - bb[3]
            gap = below if 0 <= below <= 90 else (above if 0 <= above <= 90 else None)
            if gap is None:
                continue
            if best is None or gap < best:
                best, cap = gap, b
        f["caption"] = cap["text"] if cap else ""
        f["caption_block"] = cap["id"] if cap else None
        f["caption_bbox"] = cap.get("bbox") if cap else None
        f["caption_position"] = ("below" if cap and f.get("bbox")
                                 and cap["bbox"][1] >= f["bbox"][3] else
                                 "above" if cap else None)


def _iou(a: List[float], b: List[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def _contained(inner: List[float], outer: List[float], frac: float = 0.6) -> bool:
    ix = max(0.0, min(inner[2], outer[2]) - max(inner[0], outer[0]))
    iy = max(0.0, min(inner[3], outer[3]) - max(inner[1], outer[1]))
    area = (inner[2] - inner[0]) * (inner[3] - inner[1])
    return area > 0 and (ix * iy) / area >= frac


def _cluster_paths(paths: List[List[float]], pad: float = 8.0) -> List[Dict[str, Any]]:
    """Merge touching vector paths into one shape. A chart is dozens of paths
    (axes, ticks, bars, legend swatches) that touch; a table rule is one path."""
    boxes = [p[:4] for p in paths]
    n = len(boxes)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        ax0, ay0, ax1, ay1 = boxes[i]
        for j in range(i + 1, n):
            bx0, by0, bx1, by1 = boxes[j]
            if (ax0 - pad <= bx1 and bx0 - pad <= ax1
                    and ay0 - pad <= by1 and by0 - pad <= ay1
                    and not (ax1 < bx0 - pad or bx1 < ax0 - pad)):
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri
    groups: Dict[int, List[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    out = []
    for members in groups.values():
        xs0 = min(boxes[i][0] for i in members)
        ys0 = min(boxes[i][1] for i in members)
        xs1 = max(boxes[i][2] for i in members)
        ys1 = max(boxes[i][3] for i in members)
        out.append({"bbox": [round(xs0, 2), round(ys0, 2), round(xs1, 2), round(ys1, 2)],
                    "paths": len(members),
                    "ink": sum(int(paths[i][4]) if len(paths[i]) > 4 else 1 for i in members)})
    return out


def find_figures(pages: List[Dict[str, Any]],
                 tables: List[Dict[str, Any]] | None = None,
                 blocks: List[Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
    """Locate figures: raster images *and* vector charts.

    Vector charts never show up in the engine's image list, yet they are most of
    the figures in a scientific PDF, so the rubric's "图表位置" would silently be
    empty without clustering the drawing paths. Clusters that are really table
    rules or a box drawn around text are rejected instead of reported as figures.
    """
    table_boxes: Dict[int, List[List[float]]] = {}
    for t in (tables or []):
        if t.get("bbox") and t.get("page"):
            table_boxes.setdefault(int(t["page"]), []).append(t["bbox"])
    block_boxes: Dict[int, List[List[float]]] = {}
    for b in (blocks or []):
        if b.get("bbox") and b.get("page"):
            block_boxes.setdefault(int(b["page"]), []).append(b["bbox"])
    figs: List[Dict[str, Any]] = []

    for p in pages:
        page_area = float(p.get("width") or 0) * float(p.get("height") or 0) or 1.0
        page_no = int(p.get("number") or 0)
        p_tables = table_boxes.get(page_no, [])
        # Blocks that merely *pass over* the figure (a full-page text block) must
        # not veto it; only a small frame drawn around a paragraph should.
        p_blocks = block_boxes.get(page_no, [])
        raster: List[List[float]] = []
        for bbox in p.get("images", []):
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            if w * h < 4000:
                continue
            if h > 0 and not (0.02 <= w / h <= 50):
                continue
            raster.append(list(bbox))
            figs.append({"id": "", "page": p["number"], "bbox": list(bbox),
                         "width": round(w, 1), "height": round(h, 1),
                         "kind": "raster", "area": round(w * h, 1),
                         "area_ratio": round(w * h / page_area, 4),
                         "paths": 0, "detected_by": "image-block"})

        paths = p.get("drawings") or []
        if not paths or len(paths) > 400:
            continue          # empty page, or a path soup we refuse to guess at
        for c in _cluster_paths(paths):
            bbox = c["bbox"]
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            if c["paths"] < 2 or w < 40 or h < 25:
                continue
            if h > 0 and not (0.08 <= w / h <= 12):
                continue
            area = w * h
            if area < max(5000.0, 0.004 * page_area):
                continue
            if any(_contained(bbox, tb, 0.6) for tb in p_tables):
                continue      # table rules / cell borders
            if any(_contained(bbox, bb, 0.92)
                   and (bb[2] - bb[0]) * (bb[3] - bb[1]) < 3 * area
                   for bb in p_blocks):
                continue      # a small frame drawn around a paragraph
            if any(_iou(bbox, rb) > 0.5 for rb in raster):
                continue      # the same picture already counted as raster
            figs.append({"id": "", "page": p["number"], "bbox": bbox,
                         "width": round(w, 1), "height": round(h, 1),
                         # >=8 touching paths with a real plot area reads as a chart
                         "kind": "chart" if c["paths"] >= 8 else "vector",
                         "area": round(area, 1),
                         "area_ratio": round(area / page_area, 4),
                         "paths": c["paths"], "detected_by": "vector-cluster"})
    for i, f in enumerate(figs, 1):
        f["id"] = f"fig{i:02d}"
    return figs


def mark_table_blocks(blocks: List[Dict[str, Any]], tables: List[Dict[str, Any]]) -> int:
    """Tag body blocks that really live inside a table.

    A table is read column-by-column by XY-cut, so its cells look like reading-
    order inversions and duplicate text that is already in `tables[]`.  Tagging
    them (`type="table"`, `in_table=<id>`) keeps the text for the verbatim layer
    while letting a reader -- and `verify.py` -- treat the region as one object.
    """
    by_page: Dict[int, List[Dict[str, Any]]] = {}
    for t in tables:
        if t.get("bbox") and t.get("page"):
            by_page.setdefault(int(t["page"]), []).append(t)
    marked = 0
    for b in blocks:
        bb = b.get("bbox")
        if not bb:
            continue
        for t in by_page.get(int(b.get("page") or 0), []):
            if _contained(bb, t["bbox"], 0.6):
                b["type"] = "table"
                b["in_table"] = t["id"]
                marked += 1
                break
    return marked


def prune_figures(figures: List[Dict[str, Any]], min_ratio: float = 0.02
                  ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Separate whole figures from sub-panels and decorative marks.

    A diagram is often assembled from small embedded bitmaps (arrow glyphs,
    brackets, [CLS] boxes) that the engine reports as images; counting those as
    figures would fill "图表位置" with noise.  A figure survives if it is not
    nested inside a bigger one on the same page and either carries a caption or
    covers at least 2% of the page.  Everything dropped keeps its bbox and a
    reason, so the decision is auditable rather than silent.
    """
    kept: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []
    for f in figures:
        fb = f.get("bbox") or [0, 0, 0, 0]
        area = (fb[2] - fb[0]) * (fb[3] - fb[1])
        host = None
        for g in figures:
            if g is f or g.get("page") != f.get("page"):
                continue
            gb = g.get("bbox") or [0, 0, 0, 0]
            if (gb[2] - gb[0]) * (gb[3] - gb[1]) > area * 1.5 and _contained(fb, gb, 0.85):
                host = g
                break
        if host is not None:
            hb = host.get("bbox") or [0, 0, 0, 0]
            dropped.append({"page": f.get("page"), "bbox": fb, "kind": f.get("kind"),
                            "reason": "sub-panel inside the figure at "
                                      + str([round(v) for v in hb])})
        elif not f.get("caption") and f.get("area_ratio", 1.0) < min_ratio:
            dropped.append({"page": f.get("page"), "bbox": fb, "kind": f.get("kind"),
                            "area_ratio": f.get("area_ratio", 0),
                            "reason": "no caption and below 2% of the page"})
        else:
            kept.append(f)
    for i, f in enumerate(kept, 1):
        f["id"] = f"fig{i:02d}"
    return kept, dropped



def _ascii_mathy(text: str) -> bool:
    """Math written with plain ASCII, which is what a poor text layer yields.

    "L = sqrt(1/T) * SUM_t [ -log p(y_t) ]" carries no Greek or ∑, so the
    symbol-density rule alone misses it.  Operator density plus a prose guard
    separates it from a sentence that happens to contain "=".
    """
    ops = sum(1 for ch in text if ch in ASCII_OPS)
    words = text.split()
    if ops < 3 or len(words) > 22:
        return False
    low = " " + text.lower() + " "
    prose = sum(low.count(" " + w + " ") for w in
                ("the", "we", "of", "that", "is", "are", "and", "in", "to", "with",
                 "for", "this", "our", "was", "were", "which", "as"))
    if prose >= 2:
        return False
    return ops / max(1, len(text)) >= 0.08


def _mathy(text: str) -> bool:
    if len(text) < 3 or len(text) > 400:
        return False
    strong = sum(1 for ch in text if ch in STRONG_MATH)
    weak = sum(1 for ch in text if ch in MATH_CHARS)
    has_eq = "=" in text or "≈" in text
    words = len(text.split())
    # prose that happens to contain "=" is not an equation: real display maths
    # carries a much higher punctuation/symbol ratio
    symbols = sum(1 for ch in text if not ch.isalnum() and not ch.isspace())
    if not (EQ_NUMBER.search(text) or EQ_LEAD.match(text)) and symbols / max(1, len(text)) < 0.10:
        return False
    if strong >= 2 and words <= 30:
        return True
    if has_eq and weak >= 1 and words <= 30:
        return True
    if words <= 8 and re.search(r"(^|\s)[A-Za-z]\s*[=<>≈]\s*[A-Za-z0-9(]", text):
        return True
    return _ascii_mathy(text)


def find_formulas(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect display equations and glue the fragments of one equation together."""
    out: List[Dict[str, Any]] = []
    cur: List[Dict[str, Any]] = []

    def flush():
        nonlocal cur
        if not cur:
            return
        text = " ".join(b["text"].strip() for b in cur).strip()
        m = EQ_NUMBER.search(text)
        num = m.group(1) if m else ""
        if not num:
            lead = EQ_LEAD.match(text)
            if lead:
                num = lead.group(1)
                text = text[lead.end():].strip()
        if not num:
            for b in cur:
                mm = EQ_NUMBER.search(b["text"]) or EQ_LEAD.match(b["text"])
                if mm:
                    num = mm.group(1)
                    break
        tex, dropped = formula_to_tex(text)
        out.append({"id": f"eq-{cur[0]['id']}", "page": cur[0]["page"], "block": cur[0]["id"],
                    "blocks": [b["id"] for b in cur], "number": num, "text": text,
                    "tex": tex, "tex_confidence": "low" if dropped else "medium",
                    "tex_dropped_chars": dropped})
        cur = []

    for b in blocks:
        text = b["text"].strip()
        mathy = _mathy(text)
        eqnum = bool(EQ_NUMBER.search(text) or EQ_LEAD.match(text)) and len(text) < 60
        if mathy or eqnum:
            b["type"] = "formula"
            if cur and cur[-1]["page"] == b["page"] and (b["bbox"][1] - cur[-1]["bbox"][3]) < 26:
                cur.append(b)
            else:
                flush()
                cur = [b]
        else:
            flush()
    flush()
    return out


def find_references(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    start = None
    for i, b in enumerate(blocks):
        if re.match(r"^\s*(references|bibliography|参考文献)\s*$", b["text"].strip(), re.I):
            start = i
    if start is None:
        return []
    entries: List[Dict[str, Any]] = []
    n = 0
    for b in blocks[start + 1:]:
        if re.match(r"^\s*(appendix|supplementary)", b["text"].strip(), re.I):
            break
        text = b["text"].strip()
        if not text:
            continue
        m = REF_ENTRY.match(text)
        if m:
            n += 1
            entries.append({"n": n, "label": m.group(1), "text": text, "page": b["page"], "block": b["id"]})
        elif entries and not re.search(r"\b(19|20)\d{2}\b", text[:120]):
            entries[-1]["text"] += " " + text
            entries[-1]["block"] += f"+{b['id']}"
        else:
            n += 1
            entries.append({"n": n, "label": f"[{n}]", "text": text, "page": b["page"], "block": b["id"]})
    return entries


AFFIL_WORDS = {
    "university", "universitat", "université", "universidad", "institute", "institut",
    "department", "dept", "school", "college", "laboratory", "lab", "academy", "faculty",
    "research", "center", "centre", "science", "sciences", "engineering", "technology",
    "google", "brain", "microsoft", "facebook", "meta", "deepmind", "openai", "amazon",
    "apple", "nvidia", "ibm", "intel", "adobe", "baidu", "tencent", "alibaba", "huawei",
    "inc", "ltd", "corp", "corporation", "gmbh", "hospital", "clinic", "group", "labs",
    # cities that sit between a name and its affiliation ("… Tilburg University")
    "toronto", "tilburg", "amsterdam", "utrecht", "nijmegen", "leuven", "ghent", "zurich",
    "geneva", "lausanne", "berlin", "munich", "heidelberg", "paris", "grenoble", "lyon",
    "london", "cambridge", "oxford", "edinburgh", "dublin", "copenhagen", "stockholm",
    "helsinki", "oslo", "prague", "warsaw", "beijing", "shanghai", "hangzhou", "shenzhen",
    "tokyo", "kyoto", "seoul", "singapore", "sydney", "melbourne", "seattle", "boston",
    "pittsburgh", "austin", "atlanta", "chicago", "montreal", "stanford", "berkeley",
    "york", "francisco", "angeles", "diego", "ann", "arbor", "college", "station",
}
NAME_MARKERS = re.compile(r"[∗†‡§¶#*✝♠♣♥♦]")
NAME_TOKEN = re.compile(r"^[A-ZÀ-ÖØ-ÞŁŚŻŹĆŃ][\w'’.-]*$|^[A-Z]\.$")


def names_from_author_line(text: str) -> List[str]:
    """Pull person names out of "Name∗ Affiliation email Name∗ Affilation ...".

    The author region is one of the messiest parts of a PDF: names, markers,
    affiliations and emails are glued into a single line.  Emails and
    affiliation vocabulary act as separators; what remains in runs of 2-4
    capitalised tokens is a name.
    """
    text = re.sub(r"\S+@\S+", " ", text)
    text = NAME_MARKERS.sub(" ", text)
    text = re.sub(r"\b(and|&)\b", " ", text)
    names: List[str] = []
    run: List[str] = []

    def flush():
        nonlocal run
        if 2 <= len(run) <= 4 and all(len(w) > 1 for w in run):
            names.append(" ".join(run))
        run = []

    for raw in text.split():
        trail = raw[-1] if raw else ""
        tok = re.sub(r"\d+$", "", raw.strip(",;:.")) if not raw.endswith(".") else raw.strip(",;:")
        if not tok:
            flush()
            continue
        low = tok.lower().strip(".")
        if low in AFFIL_WORDS or low in {"the", "of", "at", "in", "for"}:
            flush()
            continue
        if NAME_TOKEN.match(tok) and not re.search(r"\d", tok):
            run.append(tok)
            # a comma ends a name: "Mira Kovacs, Daniel Osei" is two people, not
            # one long run of capitalised tokens
            if trail in ",;":
                flush()
        else:
            flush()
    flush()
    seen, out = set(), []
    for n in names:
        key = n.lower()
        if key not in seen:
            seen.add(key)
            out.append(n)
    return out[:24]


def extract_metadata(pages: List[Dict[str, Any]], blocks: List[Dict[str, Any]], body_size: float) -> Dict[str, Any]:
    meta: Dict[str, Any] = {"title": "", "authors": [], "abstract": "", "keywords": [], "doi": ""}
    first = [b for b in blocks if b["page"] == pages[0]["number"]]
    if not first:
        return meta
    sized = sorted(first, key=lambda b: (-(b.get("size") or 0), b["bbox"][1]))
    if sized:
        cand = None
        top_limit = pages[0]["height"] * 0.45
        for b in sized:
            t = b["text"].strip()
            if b["bbox"][1] > top_limit or not (6 < len(t) < 250):
                continue
            if re.match(r"^(provided|copyright|licensed|arxiv|https?://|doi|preprint|under review)", t, re.I):
                continue
            if "@" in t or re.match(r"^[\d\W]+$", t):
                continue
            cand = b
            break
        if cand is None:
            cand = sized[0]
        if (cand.get("size") or 0) <= 0.01:
            for b in first[:8]:
                t = b["text"].strip()
                if 8 < len(t) < 200 and not re.match(r"^(provided|copyright|licensed|arxiv|https?://|doi)", t, re.I):
                    cand = b
                    break
        if len(cand["text"]) > 6:
            meta["title"] = cand["text"].strip()
            meta["title_block"] = cand["id"]
    # authors: everything between the title and the abstract is one author region
    if meta["title_block"]:
        idx = next(i for i, b in enumerate(first) if b["id"] == meta["title_block"])
        region: List[str] = []
        # a long title wraps into a second heading block ("… Machine" / "Translation");
        # consuming it here keeps it out of the author run
        start = idx + 1
        while (start < len(first) and first[start]["type"] == "heading"
               and not re.match(r"^(abstract|摘要)", first[start]["text"], re.I)):
            start += 1
        for b in first[start: start + 16]:
            t = b["text"].strip()
            if re.match(r"^(abstract|摘要)\b", t, re.I):
                break
            if re.match(r"^(keywords?|关键词|CCS Concepts|ACM Reference)", t, re.I):
                break
            region.append(t)
        if region:
            # Names come first on their line; the affiliation follows.  Cutting
            # each line at the first affiliation word keeps "Institute of
            # Computational Linguistics" from being read as a person's name,
            # while "Ashish Vaswani∗ Google Brain" still yields the name.
            heads = []
            for line in region:
                low = line.lower()
                cut = len(line)
                for w in AFFIL_WORDS:
                    m = re.search(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])", low)
                    if m and m.start() < cut:
                        cut = m.start()
                heads.append(line[:cut].strip())
            meta["authors"] = names_from_author_line(" ".join(h for h in heads if h))
            if not meta["authors"]:
                meta["authors"] = names_from_author_line(" ".join(region))
            # a single-line paper header ("A. Author, B. Author") has no markers
            if not meta["authors"]:
                meta["authors"] = [n.strip() for n in re.split(r",|;| and ", " ".join(region))
                                   if 2 <= len(n.split()) <= 4][:16]
        if len(meta["authors"]) < 2:
            meta["authors_uncertain"] = True
    # abstract
    for i, b in enumerate(blocks):
        if re.match(r"^\s*(abstract|摘要)\b[.:：]?\s*", b["text"], re.I):
            same = re.sub(r"^\s*(abstract|摘要)\b[.:：]?\s*", "", b["text"], flags=re.I)
            parts = [same] if same else []
            for nxt in blocks[i + 1:i + 6]:
                if is_heading(nxt, body_size) or re.match(r"^\s*(keywords?|关键词|1\.?\s+introduction)", nxt["text"], re.I):
                    break
                parts.append(nxt["text"])
            meta["abstract"] = " ".join(p for p in parts if p).strip()
            meta["abstract_block"] = b["id"]
            break
    for b in blocks[:12]:
        m = re.match(r"^\s*(keywords?|关键词|key words)\s*[:：]?\s*(.+)$", b["text"], re.I)
        if m:
            meta["keywords"] = [k.strip() for k in re.split(r"[;,，；]", m.group(2)) if k.strip()]
            break
    head = " ".join(b["text"] for b in blocks[:8])
    m = DOI.search(head)
    if m:
        meta["doi"] = m.group(0)
    return meta


def match_section(blocks: List[Dict[str, Any]], pattern: str) -> List[Dict[str, Any]]:
    rx = re.compile(pattern, re.I)
    out, on = [], False
    for b in blocks:
        if b["type"] == "heading" and rx.search(b["text"]):
            on = True
            continue
        if on and b["type"] == "heading" and b.get("level", 9) <= 1:
            break
        if on:
            out.append(b)
    return out
