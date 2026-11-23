"""Input discovery and readers for the non-PDF half of a case.

A case directory usually looks like::

    /input/case.json
    /input/task.md
    /input/*.pdf          (the scientific material)
    /input/*.docx|tex|bib|csv|json|md|txt

`discover` returns a manifest of every file with its role guessed from
extension and name, so the caller never has to assume "paper.pdf" exists.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from typing import Any, Dict, Iterable, List

TEXT_EXT = {".txt", ".md", ".markdown", ".rst", ".tex", ".bib", ".csv", ".tsv",
            ".json", ".yaml", ".yml", ".xml", ".html", ".htm", ".log", ".srt"}
DOC_EXT = {".docx"}
SHEET_EXT = {".xlsx", ".xlsm"}
PDF_EXT = {".pdf"}


def sha256(path: str, limit: int = 64 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        remaining = limit
        while remaining > 0:
            chunk = fh.read(min(1 << 20, remaining))
            if not chunk:
                break
            h.update(chunk)
            remaining -= len(chunk)
    return h.hexdigest()


def _role(path: str) -> str:
    name = os.path.basename(path).lower()
    ext = os.path.splitext(name)[1]
    if ext in PDF_EXT:
        return "pdf"
    if ext in DOC_EXT:
        return "docx"
    if ext in SHEET_EXT:
        return "spreadsheet"
    if name.endswith(".bib"):
        return "bibtex"
    if name.endswith(".tex"):
        return "latex"
    if ext in {".csv", ".tsv"}:
        return "table"
    if ext in {".json"}:
        return "json"
    if ext in {".md", ".markdown", ".txt", ".rst", ".log"}:
        return "text"
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}:
        return "image"
    return "other"


def discover(root: str, max_files: int = 200) -> Dict[str, Any]:
    """Walk *root* and describe every regular file we can read."""
    root = os.path.abspath(root)
    files: List[Dict[str, Any]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in sorted(dirnames)
                       if not d.startswith(".") and d not in {"__pycache__", "node_modules"}]
        for fn in sorted(filenames):
            if fn.startswith("."):
                continue
            full = os.path.join(dirpath, fn)
            if not os.path.isfile(full):
                continue
            try:
                size = os.path.getsize(full)
            except OSError:
                size = -1
            files.append({
                "path": full,
                "rel": os.path.relpath(full, root).replace("\\", "/"),
                "name": fn,
                "ext": os.path.splitext(fn)[1].lower(),
                "role": _role(full),
                "bytes": size,
            })
            if len(files) >= max_files:
                break
        if len(files) >= max_files:
            break

    by_role: Dict[str, List[str]] = {}
    for f in files:
        by_role.setdefault(f["role"], []).append(f["path"])

    return {
        "root": root,
        "files": files,
        "by_role": by_role,
        "pdfs": by_role.get("pdf", []),
        "primary_pdf": _pick_primary(by_role.get("pdf", [])),
        "case_json": _first_named(files, {"case.json"}),
        "task_md": _first_named(files, {"task.md", "task.markdown", "prompt.md"}),
    }


def _first_named(files: Iterable[Dict[str, Any]], names: set) -> str | None:
    for f in files:
        if f["name"].lower() in names:
            return f["path"]
    return None


def _pick_primary(pdfs: List[str]) -> str | None:
    if not pdfs:
        return None
    if len(pdfs) == 1:
        return pdfs[0]

    def rank(p: str):
        n = os.path.basename(p).lower()
        score = 0
        if re.search(r"(paper|article|main|manuscript|fulltext|full_text)", n):
            score -= 10
        if re.search(r"(supp|support|appendix|si|som|cover|license)", n):
            score += 10
        return (score, -os.path.getsize(p) if os.path.exists(p) else 0, p)

    return sorted(pdfs, key=rank)[0]


def load_case(case_path: str | None) -> Dict[str, Any]:
    if not case_path or not os.path.exists(case_path):
        return {}
    try:
        with open(case_path, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {"value": data}
    except Exception as exc:  # pragma: no cover - defensive
        return {"_error": f"case.json could not be parsed: {exc}"}


def read_text(path: str, limit: int = 2_000_000) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        return read_docx(path)
    if ext in {".xlsx", ".xlsm"}:
        return read_xlsx(path)
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read(limit)
        except (UnicodeDecodeError, LookupError):
            continue
    with open(path, "rb") as fh:
        return fh.read(limit).decode("utf-8", "replace")


def read_docx(path: str) -> str:
    try:
        import docx  # type: ignore
    except Exception:
        return _read_docx_zip(path)
    d = docx.Document(path)
    out: List[str] = []
    for p in d.paragraphs:
        out.append(p.text)
    for t in d.tables:
        for row in t.rows:
            out.append(" | ".join(c.text.strip() for c in row.cells))
    return "\n".join(out)


def _read_docx_zip(path: str) -> str:
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
        xml = re.sub(r"</w:p>", "\n", xml)
        return re.sub(r"<[^>]+>", "", xml)
    except Exception:
        return ""


def read_xlsx(path: str) -> str:
    try:
        import openpyxl  # type: ignore
    except Exception:
        return ""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    out: List[str] = []
    for ws in wb.worksheets:
        out.append(f"# sheet: {ws.title}")
        for row in ws.iter_rows(values_only=True):
            cells = ["" if c is None else str(c) for c in row]
            if any(cells):
                out.append(" | ".join(cells))
    return "\n".join(out)


def read_csv_rows(path: str, limit: int = 5000) -> List[List[str]]:
    raw = read_text(path)
    sample = raw[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except Exception:
        dialect = csv.excel
    rows: List[List[str]] = []
    with io.StringIO(raw) as fh:
        reader = csv.reader(fh, dialect)
        for i, row in enumerate(reader):
            if i >= limit:
                break
            rows.append(row)
    return rows
