"""Higher-level structure: sections, tables, formulas, figures, references, metadata."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .layout import HEADING_NUM, SENT_END, is_heading

CAPTION_TABLE = re.compile(r"^\s*(table|tab\.|表)\s*([0-9]+[a-zA-Z]?|[IVXLC]+)\b[.:：]?", re.I)
CAPTION_FIG = re.compile(r"^\s*(figure|fig\.|图)\s*([0-9]+[a-zA-Z]?|[IVXLC]+)\b[.:：]?", re.I)
EQ_NUMBER = re.compile(r"[\(（]\s*(\d{1,3}[a-zA-Z]?)\s*[\)）]\s*$")
REF_ENTRY = re.compile(r"^\s*(\[(\d{1,3})\]|(\d{1,3})\.)\s+\S")
DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
MATH_CHARS = set("∑∏∫√∞≈≠≤≥±×÷∂∇∈∉⊂⊃∪∩→←↔⇒⇔αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ·∙∗⊕⊗")


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


def normalize_table(rows: List[List[str]], max_rows: int = 200, max_cols: int = 30) -> Dict[str, Any]:
    rows = [[(c or "").replace("\n", " ").strip() for c in r][:max_cols] for r in rows[:max_rows]]
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
        for b in by_page.get(f["page"], []):
            if CAPTION_FIG.match(b["text"]):
                cap = b
                break
        f["caption"] = cap["text"] if cap else ""
        f["caption_block"] = cap["id"] if cap else None


def find_figures(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    figs: List[Dict[str, Any]] = []
    for p in pages:
        for i, bbox in enumerate(p.get("images", []), 1):
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            if w * h < 4000:
                continue
            figs.append({"id": f"fig-p{p['number']}-{i}", "page": p["number"], "bbox": bbox,
                         "width": round(w, 1), "height": round(h, 1),
                         # raster = bitmap placed on the page. Vector drawings are
                         # not captured by the engine's image list, so a page that
                         # only holds a chart will show up empty here rather than
                         # being guessed at.
                         "kind": "raster", "area": round(w * h, 1)})
    return figs


def _mathy(text: str) -> bool:
    if len(text) < 3 or len(text) > 400:
        return False
    strong = sum(1 for ch in text if ch in STRONG_MATH)
    weak = sum(1 for ch in text if ch in MATH_CHARS)
    has_eq = "=" in text or "≈" in text
    words = len(text.split())
    if strong >= 2 and words <= 30:
        return True
    if has_eq and weak >= 1 and words <= 30:
        return True
    if words <= 8 and re.search(r"(^|\s)[A-Za-z]\s*[=<>≈]\s*[A-Za-z0-9(]", text):
        return True
    return False


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
            for b in cur:
                mm = EQ_NUMBER.search(b["text"])
                if mm:
                    num = mm.group(1)
                    break
        out.append({"id": f"eq-{cur[0]['id']}", "page": cur[0]["page"], "block": cur[0]["id"],
                    "blocks": [b["id"] for b in cur], "number": num, "text": text})
        cur = []

    for b in blocks:
        text = b["text"].strip()
        mathy = _mathy(text)
        eqnum = bool(EQ_NUMBER.search(text)) and len(text) < 60
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
    # authors: lines between title and abstract, split names from affiliations
    if meta["title_block"]:
        idx = next(i for i, b in enumerate(first) if b["id"] == meta["title_block"])
        affil = re.compile(r"(universit|institut|department|dept\.|school|college|laborator|"
                           r"academy|research|inc\.|ltd|corp|brain|google|microsoft|facebook|"
                           r"@|https?://|\d{4})", re.I)
        for b in first[idx + 1: idx + 14]:
            t = b["text"].strip()
            if re.match(r"^(abstract|摘要)", t, re.I):
                break
            if affil.search(t) or len(t) > 120:
                continue
            words = t.replace(",", " ").split()
            if 1 < len(words) <= 8 and sum(1 for w in words if w[:1].isupper()) >= max(1, len(words) - 1):
                meta["authors"].append(re.sub(r"\s*[∗†‡§¶]\s*", "", t))
        if not meta["authors"]:
            # names glued to their affiliation: cut the string at the affiliation
            cut = re.compile(r"\s+(?=(?:[A-Z][\w&.-]*\s+){0,3}(?:Universit|Institut|Department|Dept|School|"
                             r"College|Laborator|Academy|Research|Inc\b|Ltd\b|Corp\b))", re.I)
            for b in first[idx + 1: idx + 14]:
                t = b["text"].split("@")[0]
                head = cut.split(t)[0].strip()
                words = head.replace(",", " ").split()
                if 1 < len(words) <= 6 and all(w[:1].isupper() for w in words if w[:1].isalpha()):
                    meta["authors"].append(head)
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
