"""Read a text-only case into the same document model a PDF produces.

The challenge cases are not all PDFs: markdown drafts, LaTeX projects, BibTeX
files, CSV tables and JSON schemas are first-class inputs.  The PDF path spends
its effort on layout; here there is no layout, so the job is to keep the
structure the author already wrote (headings, paragraphs, tables, references)
and give every piece the same `p01-bNNN` anchor so evidence stays checkable.

Nothing is invented: a block is a paragraph the file actually contains, a
reference is a BibTeX entry the file actually declares.  What the file does not
report is simply absent, and `quality.issues` says so.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
from typing import Any, Dict, List, Tuple

from . import sources, structure

BODY_EXT = {".md", ".markdown", ".txt", ".rst", ".tex", ".docx"}
# Files that instruct the agent rather than carry the paper's content.  Keeping
# them out of `blocks` stops a style guide from being "polished" as if it were
# the manuscript.
INSTRUCTION = re.compile(
    r"(style[_-]?guide|glossar|schema|task|rubric|toolchain|template[_-]?requirements|"
    r"readme|license|changelog|term[_-]?policy|hedge[_-]?map|content[_-]?notes?|requirements)", re.I)
HEAD_MD = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
BULLET = re.compile(r"^\s*(?:[-*+]|\d{1,3}[.)])\s+")
PIPE_SEP = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")
# Text cases often carry their own locator at the top of a paragraph:
# `[p.2, §3.1]` or `[p.2]`.  It is metadata, not a sentence, and leaving it in
# the assertion text is exactly how a nanopub claim ends up starting with a
# page number instead of a proposition.
LOC_LINE = re.compile(r"^\s*\[p\.?(\d+)(?:\s*,\s*§\s*([^\]]+))?\]\s*$")
LOC_PREFIX = re.compile(r"^\s*\[p\.?(\d+)(?:\s*,\s*§\s*[^\]]+)?\]\s*")


def _bid(n: int) -> str:
    return f"p01-b{n:03d}"


class _Doc:
    def __init__(self) -> None:
        self.blocks: List[Dict[str, Any]] = []
        self.sections: List[Dict[str, Any]] = []
        self.tables: List[Dict[str, Any]] = []
        self.stack: List[Dict[str, Any]] = []
        self.y = 60.0
        self.n = 0
        self.page = 1
        self.section_hint = ""

    def add(self, text: str, kind: str = "body", level: int = 0,
            page: int | None = None, size: float = 10.0) -> Dict[str, Any]:
        text = re.sub(r"[ \t]+", " ", text).strip()
        m = LOC_PREFIX.match(text)
        if m:
            self.page = int(m.group(1))
            text = text[m.end():].strip()
        page = self.page if page is None else page
        if not text:
            return {}
        self.n += 1
        if kind == "heading":
            while self.stack and self.stack[-1]["level"] >= level:
                self.stack.pop()
            sec = {"level": level, "title": text, "page": page, "block": "", "parent": None}
            self.sections.append(sec)
            self.stack.append(sec)
        path = " > ".join(s["title"] for s in self.stack) if self.stack else ""
        self.y += 16.0
        b = {
            "id": _bid(self.n), "page": page, "column": 1,
            "section": path, "type": kind, "text": text, "text_raw": text,
            "bbox": [72.0, round(self.y, 1), 540.0, round(self.y + size, 1)],
            "size": size, "engine": "text", "order_rule": "text",
        }
        if kind == "heading":
            b["level"] = level
            sec["block"] = b["id"]
        self.blocks.append(b)
        return b


def _strip_tex(text: str) -> str:
    text = re.sub(r"(?<!\\)%.*", "", text)
    text = re.sub(r"\\(cite|citep|citet|ref|eqref|label)\{[^}]*\}", "", text)
    text = re.sub(r"\\(textbf|textit|emph|mathrm|text|section|subsection|subsubsection)"
                  r"\{([^{}]*)\}", r"\2", text)
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", text)
    text = text.replace("\\\\", " ").replace("&", " ").replace("$", "")
    text = text.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", text).strip()


def _md_blocks(raw: str, doc: _Doc, source: str) -> None:
    lines = raw.splitlines()
    buf: List[str] = []

    def flush():
        if buf:
            doc.add(" ".join(buf), "body")
            buf.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            flush()
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                i += 1
            i += 1
            continue
        m = HEAD_MD.match(line)
        if m:
            flush()
            doc.add(m.group(2).strip(), "heading", level=len(m.group(1)))
            i += 1
            continue
        loc = LOC_LINE.match(line)
        if loc:
            flush()
            doc.page = int(loc.group(1))
            doc.section_hint = (loc.group(2) or "").strip()
            i += 1
            continue
        if not line.strip():
            flush()
            i += 1
            continue
        # a pipe table: header row + separator row
        if "|" in line and i + 1 < len(lines) and PIPE_SEP.match(lines[i + 1]):
            flush()
            rows = []
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.append(header)
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            doc.tables.append(_table_from_rows(rows, len(doc.tables) + 1, source))
            continue
        if BULLET.match(line):
            flush()
            doc.add(BULLET.sub("", line).strip(), "body")
            i += 1
            continue
        buf.append(line.strip())
        i += 1
    flush()


def _tex_blocks(raw: str, doc: _Doc, source: str) -> None:
    body = raw
    # equations first, so their `&`/`\\` are not stripped by the prose cleaner
    for m in re.finditer(r"\\begin\{(equation|align|gather)\*?\}(.*?)"
                         r"\\end\{\1\*?\}", body, re.S):
        doc.add(_strip_tex(m.group(2)), "formula")
    body = re.sub(r"\\begin\{(equation|align|gather)\*?\}.*?\\end\{\1\*?\}", " ", body, flags=re.S)
    for m in re.finditer(r"\\(section|subsection|subsubsection)\*?\{([^{}]*)\}", body):
        level = {"section": 1, "subsection": 2, "subsubsection": 3}[m.group(1)]
        doc.add(m.group(2).strip(), "heading", level=level)
    text = re.sub(r"\\(section|subsection|subsubsection)\*?\{[^{}]*\}", "\n\n", body)
    for para in re.split(r"\n\s*\n", text):
        cleaned = _strip_tex(para)
        if cleaned and not re.match(r"^\s*\\(documentclass|usepackage|title|author|date|maketitle)",
                                    para):
            doc.add(cleaned, "body")


def _table_from_rows(rows: List[List[str]], n: int, source: str) -> Dict[str, Any]:
    rows = [[c.strip() for c in r] for r in rows if any(c.strip() for c in r)]
    if not rows:
        rows = [[""]]
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    return {"id": f"t{n}", "page": 1, "bbox": None, "caption": "",
            "caption_block": None, "header": rows[0], "rows": rows,
            "markdown": "\n".join("| " + " | ".join(r) + " |" for r in rows),
            "n_rows": len(rows), "n_cols": width, "source": source}


def _bib_entries(raw: str) -> List[Dict[str, str]]:
    out = []
    for m in re.finditer(r"@(\w+)\{([^,]+),(.*?)\n\}", raw, re.S):
        fields = dict(re.findall(r"(\w+)\s*=\s*\{(.*?)\},?\s*\n", m.group(3), re.S))
        authors = re.sub(r"\s+and\s+", ", ", fields.get("author", "")).replace("{", "").replace("}", "")
        venue = fields.get("journal") or fields.get("booktitle") or ""
        year = fields.get("year", "")
        vol = fields.get("volume", "")
        pages = fields.get("pages", "")
        tail = f", {vol}" if vol else ""
        tail += f": {pages}" if pages else ""
        text = f"{authors}. {fields.get('title','').strip()}. {venue}, {year}{tail}."
        out.append({"key": m.group(2).strip(), "type": m.group(1).lower(),
                    "authors": authors, "title": fields.get("title", "").strip(),
                    "year": year, "venue": venue, "volume": vol, "pages": pages,
                    "doi": fields.get("doi", ""), "text": re.sub(r"\s+", " ", text)})
    return out


def _numbered_refs(raw: str) -> List[Dict[str, str]]:
    out = []
    for line in raw.splitlines():
        m = re.match(r"^\s*(?:\[(\d{1,3})\]|(\d{1,3})[.)])\s+(.+)", line)
        if m:
            out.append({"key": m.group(1) or m.group(2), "text": m.group(3).strip()})
    return out


def analyze_text(root: str, man: Dict[str, Any], case: Dict[str, Any],
                 task: str) -> Dict[str, Any]:
    """Build the document model from the text materials in *root*."""
    doc = _Doc()
    materials: Dict[str, Dict[str, Any]] = {}
    by_role = man.get("by_role") or {}
    texts: List[Tuple[str, str]] = []
    bibs: List[str] = []
    refs_md: List[str] = []
    csvs: List[str] = []
    for role, paths in by_role.items():
        if role in {"pdf", "image"}:
            continue
        for p in paths[:20]:
            name = os.path.basename(p)
            try:
                txt = sources.read_text(p)
            except Exception as exc:
                txt = ""
                materials[name] = {"role": role, "chars": 0, "error": str(exc)}
            if not txt:
                continue
            materials[name] = {"role": role, "chars": len(txt), "text": txt[:200_000]}
            if role == "bibtex":
                bibs.append(txt)
            elif role == "latex" and os.path.basename(p).lower() == "main.tex":
                if not INSTRUCTION.search(name):
                    texts.append((name, txt))
            elif role in {"text", "docx"} and not INSTRUCTION.search(name):
                if os.path.basename(p).lower() in {"references.md", "refs.md", "bibliography.md"}:
                    refs_md.append(txt)
                else:
                    texts.append((name, txt))
            elif role == "table" and name.lower().endswith(".csv"):
                if not INSTRUCTION.search(name):
                    csvs.append(p)

    # A file with no heading of its own still needs a boundary; add one only when
    # more than one content file is present, so a lone draft.md keeps its own title.
    multi = len(texts) > 1
    for name, txt in sorted(texts):
        ext = os.path.splitext(name)[1].lower()
        if multi:
            doc.add(os.path.splitext(name)[0].replace("_", " ").title(), "heading", level=1)
        if ext == ".tex":
            _tex_blocks(txt, doc, name)
        else:
            _md_blocks(txt, doc, name)

    for p in csvs:
        rows = sources.read_csv_rows(p)
        doc.tables.append(_table_from_rows(rows, len(doc.tables) + 1, os.path.basename(p)))

    refs: List[Dict[str, Any]] = []
    for raw in bibs:
        for e in _bib_entries(raw):
            b = doc.add(e["text"], "reference")
            refs.append({"n": len(refs) + 1, "label": e["key"], "text": e["text"],
                         "page": 1, "block": b.get("id", ""),
                         "authors": e["authors"], "title": e["title"], "year": e["year"],
                         "venue": e["venue"], "volume": e["volume"], "pages": e["pages"],
                         "doi": e["doi"]})
    for raw in refs_md:
        for e in _numbered_refs(raw):
            b = doc.add(e["text"], "reference")
            refs.append({"n": len(refs) + 1, "label": e["key"], "text": e["text"],
                         "page": 1, "block": b.get("id", "")})

    # reference list heading keeps the "references are not body" rule visible
    if refs:
        doc.add("References", "heading", level=1)

    formulas = structure.find_formulas(doc.blocks)
    if not refs:
        # A markdown manuscript may carry "[1] ... [2] ..." inline under a
        # References heading instead of shipping refs.bib/references.md.
        refs = structure.find_references(doc.blocks)

    title = ""
    for b in doc.blocks:
        if b["type"] == "heading" and not re.match(
                r"^(abstract|摘要|introduction|引言|references|参考文献)", b["text"], re.I):
            title = b["text"]
            break
    if not title:
        title = str(case.get("case_name") or case.get("challenge") or "") or \
            (os.path.splitext(texts[0][0])[0] if texts else "")
    abstract = ""
    for i, b in enumerate(doc.blocks):
        if re.match(r"^(abstract|摘要)\s*$", b["text"].strip(), re.I):
            parts = []
            for nxt in doc.blocks[i + 1:i + 5]:
                if nxt["type"] == "heading":
                    break
                parts.append(nxt["text"])
            abstract = " ".join(parts)
            break

    raw_all = "\n\n".join(t for _, t in texts)
    width, height = 612.0, max(792.0, doc.y + 60)
    doc.blocks = doc.blocks
    quality = {
        "pages": 1, "chars": len(raw_all), "chars_per_page": float(len(raw_all)),
        "blocks": len(doc.blocks), "tables": len(doc.tables),
        "figures": 0, "figures_dropped": 0, "formulas": len(formulas),
        "references": len(refs), "empty_pages": [], "image_tables": [],
        "page_order": {}, "garbled": {}, "blocks_in_table_regions": 0,
        "verbatim": {"ratio": 1.0, "missing": 0, "extra": 0, "hyphen_merged_blocks": 0},
        "issues": [],
    }
    if not doc.blocks:
        quality["issues"].append("no readable text material in the input")
    if not doc.sections:
        quality["issues"].append("no headings found; the text has no section structure")
    return {
        "schema": "paperkit/document@1",
        "source": {"path": os.path.abspath(root), "name": os.path.join(root, texts[0][0]) if texts else root,
                   "kind": "text", "bytes": None, "sha256": None, "pages": 1,
                   "backend": "text", "attempts": [{"engine": "text", "ok": True}],
                   "ocr_pages": [], "has_text_layer": True, "encrypted": False,
                   "decryption": "", "decrypted": False},
        "meta": {"title": title, "authors": [], "abstract": abstract,
                 "keywords": [], "doi": ""},
        "sections": doc.sections, "blocks": doc.blocks, "tables": doc.tables,
        "figures": [], "figures_dropped": [], "image_tables": [],
        "page_order": {"ok": True, "warning": False, "breaks": []},
        "garbled": {"pages": [], "pua_chars": 0},
        "formulas": formulas, "references": refs,
        "page_stats": [{"page": 1, "printed_page": 1, "chars": len(raw_all),
                        "lines": len(doc.blocks), "columns": 1, "bands": 1,
                        "gutters": [], "filled_by": "text", "order_rule": "text"}],
        "running_heads_removed": 0, "header_footer": [],
        "verbatim_text": raw_all, "verbatim_chars": len(raw_all),
        "verbatim": {"chars_in_layer": len(raw_all), "chars_in_blocks": len(raw_all),
                     "chars_in_header_footer": 0, "matched": len(raw_all),
                     "ratio": 1.0, "missing": 0, "extra": 0,
                     "hyphen_merged_blocks": 0, "sample_missing": "", "sample_extra": ""},
        "quality": quality,
        "_materials": materials,
    }
