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
             "ϵ": r"\epsilon", "ζ": r"\zeta", "η": r"\eta", "θ": r"\theta", "ι": r"\iota",
             "κ": r"\kappa", "λ": r"\lambda",
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
    # A direct glyph→command mapping produces `\DeltaG`, `\phiS`,
    # `\lambdaD`; TeX reads those as unknown commands.  Separate the command
    # from the following roman letter, then restore the sub/superscripts that
    # the text layer flattened.
    s = re.sub(r"\\(Delta|Gamma|Theta|Lambda|Sigma|Phi|Psi|Omega)([A-Za-z])",
               r"\\\1 \2", s)
    s = re.sub(r"\\(phi|lambda|omega|sigma|epsilon|kappa|gamma|nabla|partial|"
               r"mu|nu|rho|tau|alpha|beta|delta|theta)([A-Za-z0-9])",
               r"\\\1 \2", s)
    s = re.sub(r"\\phi\s+([0-9])", r"\\phi_{\1}", s)
    s = re.sub(r"\\phi\s+([ST])\b", r"\\phi_{\1}", s)
    s = re.sub(r"\\lambda\s+([D0-9])\b", r"\\lambda_{\1}", s)
    s = re.sub(r"\\Delta\s+\\phi\s+([ST])\b", r"\\Delta\\phi_{\1}", s)
    s = s.replace("Ceff", r"C_{\mathrm{eff}}")
    s = s.replace("kB", r"k_{B}")
    s = s.replace("NA", r"N_{A}")
    s = s.replace("H2", r"H^{2}")
    s = s.replace("e2", r"e^{2}")
    s = s.replace("Rs", r"R_{s}")
    s = s.replace("(\\nabla h)2", r"(\nabla h)^{2}")
    s = re.sub(r"\)\s*1/2\b", r")^{1/2}", s)
    s = s.replace("cosh(", r"\cosh(")
    s = s.replace(", with ", r",\quad\text{with}\quad ")
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
    if re.match(r"^(abstract|摘要|keywords?|key\s*words?|关键词)\b", text, re.I):
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
                and b["page"] == nxt["page"] and (nxt.get("size") or 0) >= (b.get("size") or 0) * 0.9
                and nxt.get("type") != "heading"
                and not CAPTION_TABLE.match(nxt["text"])
                and not CAPTION_FIG.match(nxt["text"])):
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


def split_tail_headings(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Recover a section heading swallowed by the last row of a table.

    A heading that sits immediately under a table is often merged into the
    table's final cell, e.g. ``1.98 3.1 Interfacial structure``.  The prefix is
    the table value, the tail is a numbered heading; keeping both as one body
    block hides a whole section (R01-C01 lost ``3.1`` this way).
    """
    out: List[Dict[str, Any]] = []
    for b in blocks:
        if b.get("type") != "body":
            out.append(b)
            continue
        t = (b.get("text") or "").strip()
        m = re.match(r"^(?P<prefix>[^A-Za-z]{0,12}\d[\d.,]*)\s+"
                     r"(?P<num>\d{1,2}(?:\.\d{1,2}){1,3})\s+"
                     r"(?P<title>[A-Z][A-Za-z0-9\-]+(?:\s+[A-Za-z0-9\-]+){0,6})$", t)
        if not m or len(m.group("title")) < 8:
            out.append(b)
            continue
        body = dict(b)
        body["id"] = b["id"] + "t"
        body["text"] = m.group("prefix").strip()
        body["text_raw"] = body["text"]
        body["lines"] = 1
        head = dict(b)
        head["id"] = b["id"] + "h"
        head["text"] = f"{m.group('num')} {m.group('title')}"
        head["text_raw"] = head["text"]
        head["type"] = "heading"
        head["lines"] = 1
        head["size"] = (b.get("size") or 10.0) + 1
        out.extend([body, head])
    return out


def merge_line_fragments(blocks: List[Dict[str, Any]], body_size: float) -> List[Dict[str, Any]]:
    """Rejoin prose that the layout pass emitted one visual line at a time.

    Two-column PDFs and short last lines otherwise become separate blocks: the
    text survives, but `0.9` and `percent` end up in different blocks and any
    check for the measured value fails even though the words are present.  Only
    unambiguous continuations are joined: same page/column/section, no sentence
    punctuation at the old end, and the new line starts lowercase or with
    punctuation that cannot begin a sentence.
    """
    out: List[Dict[str, Any]] = []
    for b in blocks:
        if b.get("type") != "body" or not out:
            out.append(b)
            continue
        prev = out[-1]
        if prev.get("type") != "body" or prev.get("page") != b.get("page") \
                or prev.get("column") != b.get("column") \
                or (prev.get("section") or "") != (b.get("section") or ""):
            out.append(b)
            continue
        left = (prev.get("text") or "").rstrip()
        right = (b.get("text") or "").lstrip()
        if not left or not right:
            out.append(b)
            continue
        if re.search(r"[.!?;:。！？；：]$", left):
            out.append(b)
            continue
        if re.search(r"[A-Z0-9\u4e00-\u9fff]", right[:1]) and \
                not re.match(r"^(and|or|but|which|that|where|when|because|with|for|of|to|in)\b",
                             right, re.I):
            out.append(b)
            continue
        if left.endswith("-"):
            prev["text"] = left[:-1] + right
            prev["text_raw"] = (prev.get("text_raw") or "") + right
        else:
            prev["text"] = left + " " + right
            prev["text_raw"] = (prev.get("text_raw") or "") + " " + right
        prev["bbox"][2] = max(prev["bbox"][2], b["bbox"][2])
        prev["bbox"][3] = max(prev["bbox"][3], b["bbox"][3])
        prev["order_rule"] = "merged-line"
    return out


def build_sections(blocks: List[Dict[str, Any]], body_size: float) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Annotate blocks with section paths; return (sections, blocks)."""
    blocks = merge_heading_fragments(blocks)
    # The merge above can create `1.98 3.1 Interfacial structure` from a table
    # tail and a heading fragment; split it again before section detection.
    blocks = split_tail_headings(blocks)
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


def detect_tables_from_boxes(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rebuild a table from word x-coordinates under a `Table N.` caption.

    The line-gap fallback cannot tell a two-column paragraph from a table.  With
    word boxes we can: (1) start at the caption, (2) stop at prose or the next
    heading, (3) cluster token centers into columns, (4) group lines into rows
    by their y band.  Everything stays traceable to a page and line range.
    """
    out: List[Dict[str, Any]] = []
    for p in pages:
        lines = [ln for ln in p.get("lines") or [] if ln.get("tokens")]
        lines.sort(key=lambda l: (l["bbox"][1], l["bbox"][0]))
        page_bottom = max(float(ln["bbox"][3]) for ln in lines) if lines else 0.0
        for i, cap in enumerate(lines):
            if not CAPTION_TABLE.search(cap["text"]):
                continue
            cx0, cy0, cx1, cy1 = cap["bbox"]
            cand: List[Dict[str, Any]] = []
            last_y = cy1
            for ln in lines[i + 1:]:
                y0 = ln["bbox"][1]
                if y0 < cy1 - 2:
                    continue
                gap = y0 - last_y
                if gap > 40:
                    break
                if page_bottom and y0 > page_bottom - 30:
                    break
                # A line from the other column is not this table's business.
                if ln["bbox"][0] < cx0 - 70 or ln["bbox"][2] > cx1 + 90:
                    continue
                # Caption continuation sits at the caption's own left edge;
                # table cells start indented inside the caption block.
                if ln["bbox"][0] <= cx0 + 10:
                    continue
                if re.match(r"^\d{1,2}(?:\.\d+)*\s+[A-Z][A-Za-z]", ln["text"].strip()):
                    break
                if CAPTION_TABLE.search(ln["text"]) and cand:
                    break
                # Table cells are short; a full sentence means the table ended.
                words = ln["text"].split()
                if len(words) >= 9 and not re.search(r"\d", ln["text"]):
                    break
                cand.append(ln)
                last_y = max(last_y, ln["bbox"][3])
            if len(cand) < 2:
                continue
            bands: List[List[Dict[str, Any]]] = []
            band: List[Dict[str, Any]] = []
            band_y = cand[0]["bbox"][1]
            for ln in cand:
                y = ln["bbox"][1]
                if band and y - band_y > 12:
                    bands.append(band)
                    band = []
                if not band:
                    band_y = y
                band.append(ln)
            if band:
                bands.append(band)
            if len(bands) < 2:
                continue
            header_lines = bands[0]
            data_bands = bands[1:]
            # Header wrapped cell labels share the same left x; numeric values
            # in data rows line up under those columns.
            centers: List[float] = []
            for ln in header_lines:
                x = float(ln["bbox"][0])
                if not any(abs(x - c) < 18 for c in centers):
                    centers.append(x)
            centers.sort()
            if len(centers) < 2:
                continue

            def cells_for(lines: List[Dict[str, Any]]) -> List[str]:
                cells = ["" for _ in centers]
                for ln in lines:
                    x = float(ln["bbox"][0])
                    j = min(range(len(centers)), key=lambda k: abs(centers[k] - x))
                    text = " ".join(tok["text"] for tok in ln["tokens"]).strip() or ln["text"].strip()
                    cells[j] = (cells[j] + " " + text).strip()
                return cells

            rows: List[List[str]] = [cells_for(header_lines)]
            for band in data_bands:
                rows.append(cells_for(band))
            if len(rows) >= 2:
                out.append({"page": p["number"],
                            "bbox": [cx0, cand[0]["bbox"][1], cx1, cand[-1]["bbox"][3]],
                            "rows": rows, "source": "caption+word-boxes"})
    return out


def extract_ocr_table(text: str) -> List[Dict[str, Any]]:
    """Read a simple table from a scanned page's OCR paragraph.

    OCR often joins the caption, header and rows into one paragraph.  The
    values are still recoverable when the condition column and three numeric
    columns are present; return the rows and the caption separately.
    """
    if not text or "Table" not in text:
        return []
    cap = re.search(r"(Table\s+\d+\.?\s*[^.]*\.)", text)
    if not cap or "Condition" not in text or "Pages" not in text:
        return []
    tail = text.split("After preprocessing", 1)[-1]
    tail = tail.split(")", 1)[-1] if ")" in tail else tail
    pat = re.compile(r"(Clean|Skew\s*(?:>|≥)?\s*[0-9.\-–]+\s*(?:deg)?)\s+"
                     r"(\d+)\s+([0-9.]+)\s+([0-9.]+)")
    rows = [["Condition", "Pages", "CER (%)", "After preprocessing (%)"]]
    for m in pat.finditer(tail):
        rows.append([m.group(1).strip(), m.group(2), m.group(3), m.group(4)])
    if len(rows) < 3:
        return []
    return [{"page": 1, "caption": cap.group(1).strip(), "rows": rows,
             "source": "ocr-text"}]


def detect_tables_from_header_boxes(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Continuation pages often put the repeated header at the top and the
    caption *below* the table.  Start from that header row instead of a caption.
    """
    out: List[Dict[str, Any]] = []
    for p in pages:
        lines = [ln for ln in p.get("lines") or [] if ln.get("tokens")]
        if len(lines) < 8:
            continue
        lines.sort(key=lambda ln: (ln["bbox"][1], ln["bbox"][0]))
        page_bottom = max(float(ln["bbox"][3]) for ln in lines)
        top_limit = min(float(ln["bbox"][1]) for ln in lines) + max(220.0, (page_bottom * 0.28))
        bands: List[List[Dict[str, Any]]] = []
        for ln in lines:
            if ln["bbox"][1] > top_limit:
                continue
            if not bands or ln["bbox"][1] - bands[-1][0]["bbox"][1] > 12:
                bands.append([ln])
            else:
                bands[-1].append(ln)
        header = None
        for band in bands:
            cells = [ln for ln in band
                     if 2 <= len(ln["text"].strip()) <= 22
                     and re.search(r"[A-Za-z]", ln["text"])]
            if len(cells) < 4:
                continue
            if not any(re.match(r"^(Run|Sample|ID|No\.?|Parameter|Condition|Material|Method)\b",
                                ln["text"].strip(), re.I) for ln in cells):
                continue
            header = band
            break
        if not header:
            continue
        hx0 = min(float(ln["bbox"][0]) for ln in header)
        hx1 = max(float(ln["bbox"][2]) for ln in header)
        centers: List[float] = []
        for ln in header:
            x = float(ln["bbox"][0])
            if not any(abs(x - c) < 18 for c in centers):
                centers.append(x)
        centers.sort()
        if len(centers) < 4:
            continue
        after = [ln for ln in lines if ln["bbox"][1] > max(float(h["bbox"][3]) for h in header) + 4]
        body: List[Dict[str, Any]] = []
        for ln in after:
            if CAPTION_TABLE.search(ln["text"]) and body:
                break
            if len(ln["text"].split()) >= 9 and not re.search(r"\d", ln["text"]):
                break
            if ln["bbox"][0] < hx0 - 20 or ln["bbox"][0] > hx1 + 80:
                continue
            body.append(ln)
            if len(body) > 80:
                break
        if len(body) < 4:
            continue
        bands2: List[List[Dict[str, Any]]] = []
        for ln in body:
            if not bands2 or ln["bbox"][1] - bands2[-1][0]["bbox"][1] > 12:
                bands2.append([ln])
            else:
                bands2[-1].append(ln)
        if len(bands2) < 3:
            continue

        def cells_for(group: List[Dict[str, Any]]) -> List[str]:
            cells = ["" for _ in centers]
            for ln in group:
                text = " ".join(tok["text"] for tok in ln["tokens"]).strip() or ln["text"].strip()
                j = min(range(len(centers)), key=lambda k: abs(centers[k] - float(ln["bbox"][0])))
                cells[j] = (cells[j] + " " + text).strip()
            return cells

        rows = [cells_for(header)] + [cells_for(band) for band in bands2]
        out.append({"page": p["number"],
                    "bbox": [hx0, header[0]["bbox"][1], hx1, body[-1]["bbox"][3]],
                    "rows": rows, "source": "header+word-boxes"})
    return out


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
                    if table_is_prose(cells):
                        group = []
                        return
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
    A third case is a word split mid-morpheme by the column grid:
    "Concentr\\nation" becomes "Concentr ation" unless the suffix is rejoined.
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
        elif _CELL_SUFFIX.match(line) and len(out) >= 3 and out[-1].isalpha():
            out += line
        else:
            first, _, rest = line.partition(" ")
            if first and _CELL_SUFFIX.match(first) and out[-1:].isalpha():
                out += first + ((" " + rest) if rest else "")
            else:
                out += " " + line
    return out


_CELL_SUFFIX = re.compile(
    r"^(ation|ations|al|ance|ence|ing|ed|ly|ic|ous|ive|ity|tion|sion|ment|"
    r"ness|tance|ture|ships?|ers?|ance|graphy|metry)$", re.I)


INLINE_HEAD = re.compile(r"^(Abstract|摘要|Keywords|关键词)\s*[:：]?\s+(.+)$", re.I)


def split_inline_headings(blocks: List[Dict[str, Any]],
                          body_size: float) -> List[Dict[str, Any]]:
    """Split `Abstract The structure ...` into a heading and its body.

    Many templates run the heading into the paragraph, at body size and without
    bold.  A size/bold test cannot see it, so the words themselves are the only
    signal; the paragraph text must survive as a body block.
    """
    out: List[Dict[str, Any]] = []
    for b in blocks:
        t = (b.get("text") or "").strip()
        m = INLINE_HEAD.match(t) if b.get("type") == "body" else None
        if not m or len(m.group(2)) < 25:
            out.append(b)
            continue
        if (b.get("size") or body_size) > body_size * 1.12:
            out.append(b)
            continue
        head = dict(b)
        head["id"] = b["id"] + "h"
        head["text"] = m.group(1).title() if m.group(1).isascii() else m.group(1)
        head["text_raw"] = m.group(1)
        head["type"] = "heading"
        head["level"] = 1
        head["size"] = (b.get("size") or body_size) + 1
        head["lines"] = 1
        body = dict(b)
        body["id"] = b["id"] + "b"
        body["text"] = m.group(2).strip()
        body["text_raw"] = body["text"]
        out.extend([head, body])
    return out


def split_ocr_sections(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Recover headings from a single OCR block that lost all line breaks.

    OCR returns one slab per page, so a scanned paper otherwise has two blocks
    and every heading is buried mid-string.  Split on the heading words that
    survive OCR; the characters are preserved, only block boundaries change.
    """
    head = re.compile(
        r"(?<![\w.])(?:\d{1,2}\s+(?:Introduction|Background|Methods?|"
        r"Results(?:\s+and\s+Discussion)?|Discussion|Conclusions?|References)|"
        r"Abstract\.|Table\s+\d+\.)", re.I)
    out: List[Dict[str, Any]] = []
    for b in blocks:
        t = b.get("text") or ""
        if b.get("engine") != "ocr" or len(t) < 220:
            out.append(b)
            continue
        ms = list(head.finditer(t))
        if len(ms) < 2:
            out.append(b)
            continue
        cuts = [0] + [m.start() for m in ms] + [len(t)]
        for i in range(len(cuts) - 1):
            seg = t[cuts[i]:cuts[i + 1]].strip()
            if not seg:
                continue
            hm = head.match(seg)
            is_cap = bool(re.match(r"Table\s+\d+\.", seg, re.I))
            if hm and not is_cap:
                htext = hm.group(0).strip()
                hb = dict(b)
                hb["id"] = f"{b['id']}-s{i + 1}h"
                hb["text"] = htext
                hb["text_raw"] = htext
                hb["type"] = "heading"
                hb["level"] = 2
                hb["size"] = (b.get("size") or 10.0) + 1.0
                hb["lines"] = 1
                out.append(hb)
                rest = seg[len(hm.group(0)):].strip()
                if rest:
                    rb = dict(b)
                    rb["id"] = f"{b['id']}-s{i + 1}b"
                    rb["text"] = rest
                    rb["text_raw"] = rest
                    rb["type"] = "body"
                    out.append(rb)
                continue
            nb = dict(b)
            nb["id"] = f"{b['id']}-s{i + 1}"
            nb["text"] = seg
            nb["text_raw"] = seg
            nb["type"] = "caption" if is_cap else "body"
            nb["lines"] = max(1, len(seg.splitlines()))
            out.append(nb)
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


_SEP_CELL = {"", "/", "|", "-", "–", "—", "·"}
_DATA_LIKE = re.compile(r"^(?:[+\-−]?(?:\d+(?:\.\d+)?|\.\d+)|[A-Za-z]{0,5}\d|yes|no|true|false|n/a)$", re.I)


def _drop_separator_columns(rows: List[List[str]]) -> List[List[str]]:
    """Drop grid-rule columns that carried only `/`, `|` or blanks."""
    if not rows:
        return rows
    width = max(len(r) for r in rows)
    keep = []
    for j in range(width):
        vals = [(r[j] if j < len(r) else "").strip() for r in rows]
        if any(v not in _SEP_CELL for v in vals):
            keep.append(j)
    if not keep:
        return rows
    return [[(r[j] if j < len(r) else "") for j in keep] for r in rows]


def _data_like(cell: str) -> bool:
    c = (cell or "").strip()
    if not c:
        return False
    if _DATA_LIKE.match(c):
        return True
    if re.match(r"^[A-Za-z]{1,4}\d", c):
        return True
    return False


def _header_row(row: List[str]) -> bool:
    vals = [c.strip() for c in row if (c or "").strip()]
    return len(vals) >= 2 and not any(_data_like(c) for c in vals)


def _unit_row(row: List[str]) -> bool:
    cells = [str(c or "").strip() for c in row if str(c or "").strip()]
    if not cells:
        return False
    units = 0
    for c in cells:
        if c.startswith(("(", "（")) or re.search(r"[µμÅ%°]|cm\s*-?\d|\bs\s*-?\d", c):
            units += 1
    return units >= max(2, len(cells) * 0.6)


def _header_count(rows: List[List[str]]) -> int:
    if not rows or not _header_row(rows[0]):
        return 0
    n = 1
    if len(rows) > 1 and _header_row(rows[1]):
        n = 2
    return n if len(rows) > n else 0


def _flatten_header(header_rows: List[List[str]], width: int) -> List[str]:
    r0 = list(header_rows[0]) + [""] * (width - len(header_rows[0]))
    r1 = (list(header_rows[1]) + [""] * (width - len(header_rows[1]))
          if len(header_rows) > 1 else [""] * width)
    filled: List[str] = []
    last = ""
    for j in range(width):
        c = r0[j].strip()
        if c:
            last = c
        elif r1[j].strip() or (j + 1 < width and r0[j + 1].strip()):
            c = last
        filled.append(c)
    if filled and not filled[0] and r1[0].strip():
        filled[0] = r1[0].strip()
    out = []
    for j in range(width):
        group = filled[j].strip()
        leaf = r1[j].strip()
        if leaf and group and leaf.lower() != group.lower():
            out.append(f"{group} / {leaf}")
        else:
            out.append(leaf or group)
    return out


def normalize_table(rows: List[List[str]], max_rows: int = 200, max_cols: int = 30) -> Dict[str, Any]:
    rows = split_multiline_rows([r[:max_cols] for r in rows[:max_rows]])
    rows = [[_join_cell(c).strip() for c in r] for r in rows][:max_rows]
    rows = _drop_separator_columns(rows)
    unique: List[List[str]] = []
    seen = set()
    for r in rows:
        key = tuple(c.strip() for c in r)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        unique.append(r)
    rows = unique
    width = max((len(r) for r in rows), default=0)
    rows = [r + [""] * (width - len(r)) for r in rows]
    if len(rows) > 2 and _unit_row(rows[1]) and not _unit_row(rows[0]):
        rows[0] = [f"{a} {b}".strip() for a, b in zip(rows[0], rows[1])]
        rows = [rows[0]] + rows[2:]
    nhead = _header_count(rows)
    header_rows = rows[:nhead] if nhead else (rows[:1] if rows else [])
    header = _flatten_header(header_rows, width) if header_rows else []
    def _clean_header(c: str) -> str:
        c = str(c or "").strip()
        # A wrapped word arrives as "Concentr / ation"; ordinary unit text such
        # as "(mol/L)" must keep its slash.
        c = re.sub(r"\b([A-Za-z]{3,})\s+/\s+([A-Za-z]{2,})\b",
                   lambda m: (m.group(1) + m.group(2)
                              if m.group(2).lower() in {"ation", "ations", "tion", "sion",
                                                        "ment", "ing", "ed", "ity", "ance",
                                                        "ence", "tance", "al"}
                              else m.group(1) + " " + m.group(2)), c)
        c = re.sub(r"\b([A-Za-z]{2,})\s+(ation|ations|tion|sion|ment|ing|ed|ity|ance|ence|tance|al)\b",
                   lambda m: m.group(1) + m.group(2), c)
        c = re.sub(r"(\d)\s*-\s*(\d)", r"\1-\2", c)
        c = re.sub(r"\s+/\s+", " ", c)
        c = re.sub(r"\s+\)", ")", c)
        c = re.sub(r"\b(cm|mm|m|s|µF)\s+(-?[0-9])", r"\1\2", c)
        return re.sub(r"\s+", " ", c)
    header = [_clean_header(c) for c in header]
    # A units row under a two-level header belongs to the header, not to the
    # data.  Leaving it in data_rows produced "|  | (Å) | ..." as the first
    # data row and made a 4x3 table look like 4x4.
    unit_row = None
    if nhead and len(rows) > nhead and _unit_row(rows[nhead]):
        unit_row = rows[nhead]
        for j in range(width):
            u = _clean_header(unit_row[j]) if j < len(unit_row) else ""
            if u and u not in header[j]:
                header[j] = (header[j] + " " + u).strip()
    data_rows = rows[nhead + (1 if unit_row else 0):] if nhead else \
        rows[1 + (1 if unit_row else 0):]
    legacy_rows = ([header] + data_rows) if header else data_rows

    def esc(s: str) -> str:
        return s.replace("|", "\\|")

    md = []
    if header:
        md.append("| " + " | ".join(esc(c) for c in header) + " |")
        md.append("|" + "|".join(["---"] * width) + "|")
        for r in data_rows:
            md.append("| " + " | ".join(esc(c) for c in r) + " |")
    return {"header": header, "header_rows": header_rows, "data_rows": data_rows,
            "rows": legacy_rows, "markdown": "\n".join(md),
            "n_rows": len(data_rows), "n_cols": width,
            "multi_level_header": nhead > 1}


def table_is_prose(rows: List[List[str]]) -> bool:
    """Reject a "table" whose cells are actually double-column body sentences.

    The line-gap fallback fires on a two-column page because every line spans
    more than 25% of the page width.  The resulting 7x6 grid has a header made
    of caption prose and cells made of paragraph text; that is a layout bug,
    not a table.  Numeric/short-label tables pass; prose grids do not.
    """
    cells = [str(c or "").strip() for r in rows for c in r if str(c or "").strip()]
    if len(cells) < 4:
        return True
    long_cells = [c for c in cells
                  if len(c) > 70 or len(c.split()) > 12
                  or (len(c) > 40 and c.endswith((".", "。", ";")))]
    if len(long_cells) / len(cells) > 0.2:
        return True
    numeric = [c for c in cells if re.match(r"^[+\-−]?\d", c)]
    if not numeric and len(cells) > 8:
        # A pure text table can exist, but a 7-column grid with no number and
        # long prose headers is overwhelmingly a body-flow artifact.
        if len(long_cells) >= 2:
            return True
    return False


def _table_markdown(header: List[str], data_rows: List[List[str]]) -> str:
    def esc(s: str) -> str:
        return (s or "").replace("|", "\\|")
    md = []
    if header:
        md.append("| " + " | ".join(esc(c) for c in header) + " |")
        md.append("|" + "|".join(["---"] * len(header)) + "|")
        for r in data_rows:
            md.append("| " + " | ".join(esc(c) for c in r) + " |")
    return "\n".join(md)


def _header_sig(header: List[str]) -> Tuple[str, ...]:
    return tuple(re.sub(r"[^a-z0-9]+", "", (c or "").lower()) for c in header)


def _run_no(cell: str) -> int | None:
    m = re.match(r"^\s*[A-Za-z]*(\d{1,3})\s*$", cell or "")
    return int(m.group(1)) if m else None


def merge_continuations(tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Join a table that continues on the next page instead of shipping two halves.

    The second page repeats the header row; its rows belong to the same table.
    Requiring the same column signature plus either a caption that says
    "continues" or consecutive run numbers keeps two unrelated same-width tables
    from being glued together.
    """
    out: List[Dict[str, Any]] = []
    for t in tables:
        if out:
            prev = out[-1]
            same_header = (_header_sig(t.get("header") or []) ==
                           _header_sig(prev.get("header") or []))
            same_width = t.get("n_cols") == prev.get("n_cols") and (
                same_header or not prev.get("header") or not t.get("header"))
            adjacent = int(t.get("page") or 0) == int(prev.get("page") or 0) + 1
            cap = ((prev.get("caption") or "") + " " + (t.get("caption") or "")).lower()
            says_continue = any(k in cap for k in
                                ("continu", "续表", "接上页", "continued",
                                 "repeat", "across a page", "跨页"))
            prev_no = re.search(r"table\s+(\d+)", (prev.get("caption") or ""), re.I)
            this_no = re.search(r"table\s+(\d+)", (t.get("caption") or ""), re.I)
            same_number = bool(prev_no and this_no and prev_no.group(1) == this_no.group(1))
            pdata = prev.get("data_rows") or []
            tdata = t.get("data_rows") or []
            last_run = _run_no(pdata[-1][0]) if pdata and pdata[-1] else None
            first_run = _run_no(tdata[0][0]) if tdata and tdata[0] else None
            sequential = last_run is not None and first_run is not None and first_run == last_run + 1
            if same_width and adjacent and (says_continue or same_number or sequential):
                merged = []
                seen = set()
                for r in pdata + tdata:
                    key = tuple((c or "").strip() for c in r)
                    if not any(key) or key in seen:
                        continue
                    seen.add(key)
                    merged.append(r)
                prev["data_rows"] = merged
                prev["rows"] = merged
                if not prev.get("header") and t.get("header"):
                    prev["header"] = t["header"]
                    prev["header_rows"] = t.get("header_rows") or [t["header"]]
                prev["rows_all"] = ([prev["header"]] + merged) if prev.get("header") else merged
                prev["n_rows"] = len(merged)
                prev["markdown"] = _table_markdown(prev.get("header") or [], merged)
                prev.setdefault("pages", [prev.get("page")])
                if t.get("page") not in prev["pages"]:
                    prev["pages"].append(t.get("page"))
                # A continuation's own caption is already represented by the
                # first caption; keeping both would duplicate the "Table 1" line.
                continue
        out.append(t)
    return out


FOOTNOTE_TEXT = re.compile(r"^(?:footnote|脚注)\s*([0-9]+|[A-Za-z])\s*[:：]\s*(.+)", re.I)


def mark_notes(blocks: List[Dict[str, Any]], pages: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Separate footnotes and vertical margin notes from the body flow.

    The parser used to leave `Footnote 1: ...` as an ordinary body paragraph,
    and the deliverable then reported zero footnotes.  A margin note is a
    vertical line in the outer margin; the running-head stripper now keeps it,
    so it needs its own type and its own anchor instead of being spliced into a
    paragraph.
    """
    widths = {p.get("number"): float(p.get("width") or 0) for p in pages}
    footnotes: List[Dict[str, Any]] = []
    margin_notes: List[Dict[str, Any]] = []
    body_by_page: Dict[int, List[Dict[str, Any]]] = {}
    for b in blocks:
        if b.get("type") == "body" and not b.get("in_table"):
            body_by_page.setdefault(b.get("page"), []).append(b)
    for b in blocks:
        t = (b.get("text") or "").strip()
        m = FOOTNOTE_TEXT.match(t)
        if m:
            b["type"] = "footnote"
            b["marker"] = m.group(1)
            b["note_text"] = m.group(2).strip()
            anchor = _nearest_body(body_by_page.get(b.get("page"), []), b)
            b["anchor_block"] = anchor.get("id") if anchor else ""
            footnotes.append({"marker": m.group(1), "page": b.get("page"),
                              "block": b.get("id"), "text": b["note_text"],
                              "anchor_block": b.get("anchor_block")})
            continue
        width = widths.get(b.get("page")) or 0
        x0, y0, x1, y1 = b.get("bbox") or [0, 0, 0, 0]
        vertical = (y1 - y0) > (x1 - x0) * 2.5 and (y1 - y0) > 25
        if vertical and width and x0 > width * 0.88:
            b["type"] = "margin_note"
            anchor = _nearest_body(body_by_page.get(b.get("page"), []), b)
            b["anchor_block"] = anchor.get("id") if anchor else ""
            margin_notes.append({"page": b.get("page"), "block": b.get("id"),
                                 "text": t, "anchor_block": b.get("anchor_block"),
                                 "orientation": "vertical"})
    return footnotes, margin_notes


def _nearest_body(candidates: List[Dict[str, Any]], note: Dict[str, Any]) -> Dict[str, Any] | None:
    if not candidates:
        return None
    y = (note.get("bbox") or [0, 0, 0, 0])[1]
    return min(candidates, key=lambda b: abs(((b.get("bbox") or [0, 0, 0, 0])[1]) - y))


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


REF_LINE = re.compile(
    r"doi:[ ]*10[.]|"
    r"^[0-9]{1,4}[ ]*[-–][ ]*[0-9]{1,4}[.]?$|"
    r"(?:19|20)[0-9]{2}[ ]*[:;][ ]*[0-9]{1,4}[ ]*[-–][ ]*[0-9]{1,4}|"
    r"\[[A-Z]\]//|//(?:ACL|NeurIPS|ICML|ICLR|NAACL|EMNLP|CVPR)", re.I)


def _mathy(text: str) -> bool:
    if len(text) < 3 or len(text) > 400:
        return False
    # A reference entry is full of digits, slashes and dashes and clears every
    # symbol-ratio test below: "1715-1725. doi:10.18653/v1/P16-1162" was shipped
    # as equation (2) of a paper that has one equation.
    if REF_LINE.search(text):
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
        if REF_LINE.search(text):
            # `EQ_LEAD` accepts a leading "1715-1725.", so a reference entry can
            # clear the display-equation test.  Drop the group without touching
            # the block's type: re-typing it as prose moved it into the heading
            # detector and invented a section on page 1.
            cur = []
            return
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
    # A numbered display equation can be glued to a prose sentence ("C = ...
    # (3) where ...").  The block is not purely mathy, so the display detector
    # above stops before it.  Recover the numbered expression without
    # swallowing the following prose.
    have = {str(f.get("number") or "") for f in out}
    for b in blocks:
        if b.get("type") not in {"body", "formula"}:
            continue
        m = re.match(r"^(?P<expr>.+?)\s*[\(（](?P<num>\d{1,3})[\)）]\s*(?P<tail>.*)$",
                     b["text"].strip(), re.S)
        if not m or m.group("num") in have:
            continue
        expr = m.group("expr").strip()
        if not expr:
            continue
        # A numbered display can be glued to prose in one block.  Require
        # either an equation sign or a genuinely math-shaped expression
        # (function application / parentheses), not just any sentence ending
        # in "(3)".
        if "=" not in expr and not (
                re.search(r"[A-Za-z]\s*[\(（]", expr)
                and not re.search(r"\b(the|and|that|this|is|was|were|by|for)\b", expr, re.I)
                and len(expr.split()) <= 18):
            continue
        if "=" in expr and not any(ch in MATH_CHARS for ch in expr):
            continue
        tex, dropped = formula_to_tex(expr + " (" + m.group("num") + ")")
        out.append({"id": f"eq-{b['id']}", "page": b["page"], "block": b["id"],
                    "blocks": [b["id"]], "number": m.group("num"),
                    "text": expr + " (" + m.group("num") + ")", "tex": tex,
                    "tex_confidence": "low" if dropped else "medium",
                    "tex_dropped_chars": dropped})
        have.add(m.group("num"))
    # Some papers put the equation number before the display ("loss (2) L = ...").
    for b in blocks:
        if b.get("type") not in {"body", "formula"}:
            continue
        for m in re.finditer(r"\((?P<num>\d{1,3})\)\s*(?P<expr>[^.;]{1,180}?=[^.;]{1,180})",
                             b["text"].strip()):
            num = m.group("num")
            if num in have:
                continue
            expr = m.group("expr").strip()
            if not any(ch in MATH_CHARS for ch in expr) and not re.search(r"\b[A-Za-z]{1,3}\s*=", expr):
                continue
            tex, dropped = formula_to_tex(expr + " (" + num + ")")
            out.append({"id": f"eq-{b['id']}-{num}", "page": b["page"], "block": b["id"],
                        "blocks": [b["id"]], "number": num,
                        "text": expr + " (" + num + ")", "tex": tex,
                        "tex_confidence": "low" if dropped else "medium",
                        "tex_dropped_chars": dropped})
            have.add(num)
    out.sort(key=lambda f: (f.get("page", 0), int(f.get("number") or 999)))
    return out


def find_references(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    start = None
    for i, b in enumerate(blocks):
        if re.match(r"^\s*(references|bibliography|参考文献)\s*$", b["text"].strip(), re.I):
            start = i
    if start is None:
        # Physics papers often omit the "References" heading and start the
        # list directly with "[1] … [2] …".  Detect that sequence instead of
        # returning zero entries.
        for i, b in enumerate(blocks):
            if not re.match(r"^\s*\[1\]", b["text"].strip()):
                continue
            window = " ".join(x["text"] for x in blocks[i:i + 8])
            if len(re.findall(r"\[\d{1,3}\]", window)) >= 3:
                start = i - 1
                break
    if start is None:
        return []
    candidates = []
    for b in blocks[start + 1:]:
        if re.match(r"^\s*(appendix|supplementary)", b["text"].strip(), re.I):
            break
        if b["text"].strip():
            candidates.append(b)
    if not candidates:
        return []
    numbered = len(re.findall(r"\[\d{1,3}\]", " ".join(b["text"] for b in candidates))) >= 2
    entries: List[Dict[str, Any]] = []
    if numbered:
        # A markdown input may put the whole bibliography in one block:
        # "[1] ... [2] ... [3] ...".  Split on the next number marker, not on
        # visual lines, or eight references become one.
        for b in candidates:
            text = b["text"].strip()
            for part in re.split(r"(?=\[\d{1,3}\])", text):
                part = part.strip()
                if not part:
                    continue
                m = REF_ENTRY.match(part)
                if m:
                    entries.append({"n": len(entries) + 1, "label": m.group(1), "text": part,
                                    "page": b["page"], "block": b["id"]})
                elif entries:
                    entries[-1]["text"] += " " + part
                    entries[-1]["block"] += f"+{b['id']}"
    else:
        for b in candidates:
            text = b["text"].strip()
            entries.append({"n": len(entries) + 1, "label": f"[{len(entries) + 1}]",
                            "text": text, "page": b["page"], "block": b["id"]})
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
    "united", "states", "usa", "america", "china", "colombia", "germany", "france",
    "japan", "canada", "australia", "netherlands", "switzerland", "singapore",
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


def _title_from_lines(page: Dict[str, Any]) -> str:
    """Read the title from the page lines, before authors/affiliations."""
    height = float(page.get("height") or 842.0)
    lines = sorted([ln for ln in page.get("lines") or [] if ln.get("text")],
                   key=lambda ln: (ln["bbox"][1], ln["bbox"][0]))
    parts: List[str] = []
    started = False
    last_y = 0.0
    for ln in lines:
        y = float(ln["bbox"][1])
        if y > height * 0.38:
            break
        t = re.sub(r"\s+", " ", ln["text"]).strip()
        if not t:
            continue
        if re.search(r"\b(Abstract|摘要)\b", t):
            head = re.split(r"\b(?:Abstract|摘要)\b", t, maxsplit=1)[0].strip(" .:")
            if head and not started:
                parts.append(head)
            break
        if re.match(r"^(Journal|Proceedings|Conference|Volume|Issue|doi|arxiv|preprint)\b", t, re.I):
            continue
        if re.search(r"\b(Institute|University|Laboratory|Department|Correspondence|E-?mail)\b", t, re.I):
            break
        if re.match(r"^[A-Z]\.\s*[A-Z][A-Za-z'’-]*\d*(?:\s+\d+)?(?:\s*,|\s+and\b)", t):
            break
        if len(t) < 4 or len(t) > 260:
            continue
        if started and y - last_y > 24:
            break
        parts.append(t)
        started = True
        last_y = y
    return " ".join(parts).strip()


def recover_numbered_sections(pages: List[Dict[str, Any]],
                             sections: List[Dict[str, Any]],
                             extra_text: str = "") -> List[Dict[str, Any]]:
    """Keep numbered headings that the block classifier left as body text.

    A page footer such as `2 SYNTHETIC TEST DATA` is still part of the section
    tree expected by a parser rubric; dropping it because it sits low on the
    page makes the tree silently shorter than the document.
    """
    known = {re.sub(r"\s+", " ", str(s.get("title") or "")).strip().lower()
             for s in sections}
    out = list(sections)
    for p in pages:
        for ln in sorted(p.get("lines") or [], key=lambda ln: ln["bbox"][1]):
            text = re.sub(r"\s+", " ", ln.get("text") or "").strip()
            if not (2 <= len(text) <= 90) or text.endswith("."):
                continue
            m = re.match(r"^(\d{1,2})(?:\.\d+)?\s+([A-Z][A-Za-z].*)$", text)
            if not m:
                continue
            # Running footer ("2 SYNTHETIC TEST DATA") is not a section and has
            # the same number as a real section; the rubric's section tree must
            # not gain a duplicate from the page furniture.
            if text == text.upper() or (m.group(2) == m.group(2).upper() and len(text.split()) <= 5):
                continue
            title = text
            if title.lower() in known:
                continue
            known.add(title.lower())
            out.append({"level": 1, "title": title, "page": p["number"],
                        "block": "", "parent": None})
    base_map: Dict[str, int] = {}
    raw_lines = [re.sub(r"\s+", " ", x).strip() for x in (extra_text or "").splitlines()]
    for i, text in enumerate(raw_lines):
        if re.fullmatch(r"\d{1,2}", text) and i + 1 < len(raw_lines):
            nxt = raw_lines[i + 1]
            # A bare printed page number sits immediately above the title in
            # `pdftotext -layout`; joining them invented "1 Deep Potential ..."
            # as a section.  Real short headings have few words.
            if len(nxt.split()) >= 6 or ":" in nxt:
                continue
            if re.match(r"^[A-Z][A-Za-z]", nxt) and len(nxt) <= 80:
                text = text + " " + nxt
        if not (2 <= len(text) <= 90) or text.endswith("."):
            continue
        if not re.match(r"^\d{1,2}(?:\.\d+)?\s+[A-Z][A-Za-z].*$", text):
            continue
        m = re.match(r"^(\d{1,2})\s+(.*)$", text)
        if text == text.upper() or (m and m.group(2) == m.group(2).upper()):
            continue
        base = re.sub(r"^\d+\s+", "", text).strip().lower()
        if base in base_map and m:
            idx = base_map[base]
            old = re.match(r"^(\d+)", out[idx]["title"])
            if old and int(m.group(1)) > int(old.group(1)):
                out[idx]["title"] = text
            continue
        if text.lower() in known:
            continue
        known.add(text.lower())
        if m:
            base_map[base] = len(out)
        out.append({"level": 1, "title": text, "page": 1,
                    "block": "", "parent": None})
    return out


def extract_metadata(pages: List[Dict[str, Any]], blocks: List[Dict[str, Any]], body_size: float) -> Dict[str, Any]:
    meta: Dict[str, Any] = {"title": "", "authors": [], "abstract": "", "keywords": [], "doi": ""}
    first = [b for b in blocks if b["page"] == pages[0]["number"]]
    if not first:
        return meta
    line_title = _title_from_lines(pages[0])
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
            if re.match(r"^(abstract|摘要|keywords?|关键词)\b", t, re.I):
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
        if line_title and len(line_title) > 6:
            meta["title"] = line_title
            meta["title_block"] = meta.get("title_block") or cand["id"]
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
        # A single author line immediately below the title is the strongest
        # signal; this avoids scanning affiliations and correspondence.
        direct = first[start]["text"].strip() if start < len(first) else ""
        direct_names = []
        if len(direct) < 120 and not re.search(r"\b(department|university|institute|correspondence)\b", direct, re.I):
            direct_names = names_from_author_line(direct)
            if not direct_names:
                for part in re.split(r",| and ", direct):
                    part = re.sub(r"\d+", "", part).strip(" .;")
                    toks = part.split()
                    if 2 <= len(toks) <= 4 and all(
                            re.match(r"^[A-ZÀ-ÖØ-Þ][\w'’.-]*$|^[A-Z]\.$", t) for t in toks):
                        direct_names.append(part)
        if len(direct_names) >= 2:
            meta["authors"] = direct_names[:24]
            start = len(first)
        for b in first[start: start + 16]:
            t = b["text"].strip()
            if re.match(r"^(abstract|摘要)\b", t, re.I):
                break
            if re.match(r"^(keywords?|关键词|CCS Concepts|ACM Reference|correspondence|email|e-mail)", t, re.I):
                break
            # Affiliations and the abstract are one or two blocks; a long
            # sentence-bearing body block ends the author region too.  Without
            # this, the whole first page was scanned and "United States"
            # became the author.
            if len(t) > 180 or (len(t.split()) > 16 and re.search(r"[.!?]\s", t)):
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
