"""PDF engines behind one interface.

Each backend returns::

    {
      "backend": "pymupdf 1.24.9",
      "pages": [ {"number": 1, "width": 595.3, "height": 841.9,
                  "rotation": 0, "chars": 1234, "images": [bbox, ...],
                  "blocks": [ {"bbox": [...], "lines": [ {"text","bbox","size","bold","italic","font"} ] } ]} ]
    }

The first backend that yields text for at least one page wins; the rest are
consulted only for pages where the winner produced nothing (mixed scans).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List

MIN_PAGE_CHARS = 40


def _bbox(seq) -> List[float]:
    vals = [float(v) for v in seq[:4]]
    return [round(v, 2) for v in vals]


# --------------------------------------------------------------------------- #
# PyMuPDF
# --------------------------------------------------------------------------- #
def _fitz_version() -> str:
    try:
        import fitz  # type: ignore
    except Exception:
        return ""
    return "pymupdf " + getattr(fitz, "__version__", getattr(fitz, "VersionBind", "?"))


def _extract_fitz(path: str) -> Dict[str, Any] | None:
    try:
        import fitz  # type: ignore
    except Exception:
        return None
    doc = fitz.open(path)
    pages: List[Dict[str, Any]] = []
    try:
        for pno in range(doc.page_count):
            page = doc.load_page(pno)
            data = page.get_text("dict")
            blocks: List[Dict[str, Any]] = []
            images: List[List[float]] = []
            # Vector paths are how charts and diagrams are actually drawn in most
            # papers -- they never appear in `page.get_images()`.  Geometry only:
            # [x0, y0, x1, y1, n_items]; `structure.find_figures` clusters them.
            drawings: List[List[float]] = []
            try:
                for d in page.get_drawings():
                    r = d.get("rect")
                    if r is None:
                        continue
                    if r.width < 0.4 and r.height < 0.4:
                        continue
                    drawings.append([round(r.x0, 2), round(r.y0, 2),
                                     round(r.x1, 2), round(r.y1, 2),
                                     len(d.get("items", [])) or 1])
            except Exception:
                drawings = []
            for raw in data.get("blocks", []):
                if raw.get("type") == 1:
                    images.append(_bbox(raw.get("bbox", [0, 0, 0, 0])))
                    continue
                lines = []
                for line in raw.get("lines", []):
                    spans = line.get("spans", [])
                    text = "".join(s.get("text", "") for s in spans)
                    if not text:
                        continue
                    sizes = [s.get("size", 0) for s in spans if s.get("text", "").strip()]
                    fonts = [s.get("font", "") for s in spans]
                    lines.append({
                        "text": text,
                        "bbox": _bbox(line.get("bbox", raw.get("bbox", [0, 0, 0, 0]))),
                        "size": round(max(sizes) if sizes else 0.0, 2),
                        "bold": any("bold" in f.lower() or "black" in f.lower() for f in fonts),
                        "italic": any(("italic" in f.lower()) or f.lower().endswith("-it") for f in fonts),
                        "font": fonts[0] if fonts else "",
                    })
                if lines:
                    blocks.append({"bbox": _bbox(raw.get("bbox", [0, 0, 0, 0])), "lines": lines})
            chars = sum(len(l["text"]) for b in blocks for l in b["lines"])
            pages.append({
                "number": pno + 1,
                "width": round(float(page.rect.width), 2),
                "height": round(float(page.rect.height), 2),
                "rotation": int(page.rotation or 0),
                "chars": chars,
                "images": images,
                "drawings": drawings,
                "blocks": blocks,
            })
    finally:
        doc.close()
    return {"backend": _fitz_version() or "pymupdf", "pages": pages}


def _lines_in(page, box) -> List[Dict[str, Any]]:
    """Text lines inside `box`, each with its baseline.

    The baseline is what defines a table row.  The engine's own cell rectangles
    sit on *text-line boundaries*, so a cell box overlaps the neighbouring row
    and any box-based read (``get_textbox``, ``get_text(clip=...)``) pulls that
    row in -- which is how tables come back with every data row duplicated.
    """
    out: List[Dict[str, Any]] = []
    try:
        d = page.get_text("dict")
    except Exception:
        return out
    for blk in d.get("blocks", []):
        for ln in blk.get("lines", []):
            spans = ln.get("spans", [])
            if not spans:
                continue
            txt = "".join(s.get("text", "") for s in spans)
            if not txt.strip():
                continue
            b = ln.get("bbox", (0, 0, 0, 0))
            if b[1] > box[3] + 1 or b[3] < box[1] - 1:
                continue
            base = spans[0].get("origin", (0, b[3]))[1]
            out.append({"y": float(base), "x0": float(b[0]), "x1": float(b[2]),
                        "text": re.sub(r"[ \t]+", " ", txt).strip()})
    return out


def _column_spans(box, t) -> List[tuple]:
    xs: List[float] = []
    for row in getattr(t, "rows", []) or []:
        for cell in getattr(row, "cells", []) or []:
            if cell is None:
                continue
            x0 = float(cell[0])
            if not any(abs(x0 - x) < 3.0 for x in xs):
                xs.append(x0)
    xs.sort()
    edges = [box[0]] + [x for x in xs if x > box[0] + 1]
    if len(edges) < 2:
        return []
    return [(edges[i], edges[i + 1] if i + 1 < len(edges) else box[2])
            for i in range(len(edges))]


def _table_rows_mapped(page, t, engine_rows: List[List[str]]) -> List[List[str]]:
    """Re-read each engine row from the text line sitting on its baseline.

    The engine's cell text loses spaces ("LayerType") and splits decimals
    ("241\\n."), but its row *count* matches the number of physical text lines.
    When the two counts agree, row i is the line i, so the cell text can be
    replaced by the raw line text -- spaces and decimal points intact.
    """
    box = tuple(t.bbox)
    lines = _lines_in(page, box)
    if not lines:
        return []
    bases: List[float] = []
    for ln in sorted(lines, key=lambda l: l["y"]):
        if not bases or abs(ln["y"] - bases[-1]) > 1.6:
            bases.append(ln["y"])
    if len(bases) != len(engine_rows):
        return []
    spans = _column_spans(box, t)
    if not spans:
        return []
    rows: List[List[str]] = [["" for _ in spans] for _ in bases]
    for ln in lines:
        ri = min(range(len(bases)), key=lambda i: abs(bases[i] - ln["y"]))
        best, best_ov = 0, -1e9
        for i, (a, b) in enumerate(spans):
            ov = min(ln["x1"], b) - max(ln["x0"], a)
            if ov > best_ov:
                best, best_ov = i, ov
        prev = rows[ri][best]
        rows[ri][best] = (prev + "\n" + ln["text"]).strip("\n") if prev else ln["text"]
    return rows


def _table_rows(page, t) -> List[List[str]]:
    """Rebuild a table's rows from text baselines and column spans."""
    box = tuple(t.bbox)
    lines = _lines_in(page, box)
    if len(lines) < 4:
        return []
    spans = _column_spans(box, t)
    if not spans:
        return []

    # rows: cluster baselines, tolerance below one line height.
    lines.sort(key=lambda l: (l["y"], l["x0"]))
    clusters: List[List[Dict[str, Any]]] = []
    for ln in lines:
        if clusters and abs(ln["y"] - clusters[-1][-1]["y"]) <= 1.6:
            clusters[-1].append(ln)
        else:
            clusters.append([ln])
    if len(clusters) < 2:
        return []

    rows: List[List[str]] = []
    for cl in clusters:
        cells: List[List[str]] = [[] for _ in spans]
        for ln in cl:
            best, best_ov = 0, -1.0
            for i, (a, b) in enumerate(spans):
                ov = min(ln["x1"], b) - max(ln["x0"], a)
                if ov > best_ov:
                    best, best_ov = i, ov
            cells[best].append(ln["text"])
        rows.append(["\n".join(c) for c in cells])
    return rows


def _rows_quality(rows: List[List[str]], lines: List[Dict[str, Any]] | None = None) -> int:
    """Lower is better: duplicated rows, near-empty rows and lost spaces."""
    flat: List[List[str]] = []
    for r in rows:
        cols = [(c or "").split("\n") for c in r]
        counts = [len(c) for c in cols if any(x.strip() for x in c)]
        k = counts[0] if counts and len(set(counts)) == 1 else 1
        if 2 <= k <= 8 and len(counts) >= 2:
            for i in range(k):
                flat.append([(c[i] if i < len(c) else "") for c in cols])
        else:
            flat.append(["\n".join(c) for c in cols])
    dups = sum(1 for i in range(1, len(flat)) if flat[i] == flat[i - 1])
    sparse = sum(1 for r in flat if sum(1 for c in r if c.strip()) <= 1)
    mangled = sum(1 for r in flat for c in r if re.match(r"^\d+\.$", c.strip()))
    gap = 0
    if lines:
        cell_spaces = sum(c.count(" ") for r in flat for c in r)
        line_spaces = sum(l["text"].count(" ") for l in lines)
        gap = max(0, line_spaces - cell_spaces)
    return dups * 3 + sparse + mangled * 3 + gap


def _engine_rows(page, t) -> List[List[str]]:
    """Cell text read per engine cell box; spaces survive, rows may repeat."""
    try:
        import fitz  # type: ignore
    except Exception:
        return []
    rows: List[List[str]] = []
    try:
        for row in getattr(t, "rows", []) or []:
            cells: List[str] = []
            for cell in getattr(row, "cells", []) or []:
                if cell is None:
                    cells.append("")
                    continue
                txt = page.get_textbox(fitz.Rect(cell))
                cells.append(re.sub(r"[ \t]+", " ", txt).strip())
            rows.append(cells)
    except Exception:
        return []
    return rows if any(any(c for c in r) for r in rows) else []


def _fitz_tables(path: str, pages: List[int] | None = None) -> List[Dict[str, Any]]:
    try:
        import fitz  # type: ignore
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    try:
        doc = fitz.open(path)
    except Exception:
        return []
    try:
        wanted = set(pages) if pages else None
        for pno in range(doc.page_count):
            if wanted and (pno + 1) not in wanted:
                continue
            page = doc.load_page(pno)
            try:
                # Borderless academic tables line their columns up by text, not
                # by rules.  `strategy="text"` finds those columns (13 instead of
                # 3 on the Transformer variation table); the default strategy is
                # kept as a fallback for older PyMuPDF builds that reject the kw.
                try:
                    finder = page.find_tables(strategy="text")
                    if not getattr(finder, "tables", None):
                        finder = page.find_tables()
                except TypeError:
                    finder = page.find_tables()
            except Exception:
                continue
            for t in getattr(finder, "tables", []) or []:
                # Two candidate readings: the engine's own cells (good when the
                # table has aligned rows) and a baseline rebuild (good when the
                # engine's row boxes straddle two text lines and duplicate every
                # row).  Score both and keep the cleaner one.
                engine_rows = _engine_rows(page, t)
                mapped = _table_rows_mapped(page, t, engine_rows) if engine_rows else []
                base_rows = _table_rows(page, t)
                # 1) rows that line up one-to-one with text baselines: spaces and
                #    decimals both survive.  2) the engine's own cells, which the
                #    normaliser expands when several values are stacked in one
                #    cell.  3) plain baseline rebuild, only when the engine gave
                #    nothing usable.
                if mapped:
                    rows = mapped
                elif engine_rows:
                    rows = engine_rows
                else:
                    rows = base_rows
                rows = [r for r in rows if any(c for c in r)]
                if len(rows) < 2:
                    continue
                out.append({"page": pno + 1, "bbox": _bbox(t.bbox), "rows": rows})
    finally:
        doc.close()
    return out


# --------------------------------------------------------------------------- #
# pdfplumber
# --------------------------------------------------------------------------- #
def _extract_plumber(path: str) -> Dict[str, Any] | None:
    try:
        import pdfplumber  # type: ignore
    except Exception:
        return None
    pages: List[Dict[str, Any]] = []
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            words = page.extract_words(extra_attrs=["size", "fontname"], keep_blank_chars=False)
            lines_map: Dict[tuple, List[Dict[str, Any]]] = {}
            for w in words:
                key = (round(float(w["top"]), 1), round(float(w.get("size", 0)), 1))
                lines_map.setdefault(key, []).append(w)
            blocks: List[Dict[str, Any]] = []
            for key in sorted(lines_map, key=lambda k: k[0]):
                ws = sorted(lines_map[key], key=lambda w: float(w["x0"]))
                text = " ".join(w["text"] for w in ws)
                if not text.strip():
                    continue
                bbox = [min(float(w["x0"]) for w in ws), min(float(w["top"]) for w in ws),
                        max(float(w["x1"]) for w in ws), max(float(w["bottom"]) for w in ws)]
                fonts = [str(w.get("fontname", "")) for w in ws]
                blocks.append({"bbox": _bbox(bbox), "lines": [{
                    "text": text,
                    "bbox": _bbox(bbox),
                    "size": round(float(key[1] or 0), 2),
                    "bold": any("bold" in f.lower() or "black" in f.lower() for f in fonts),
                    "italic": any("italic" in f.lower() or "oblique" in f.lower() for f in fonts),
                    "font": fonts[0] if fonts else "",
                }]})
            chars = sum(len(b["lines"][0]["text"]) for b in blocks)
            images = [[round(float(o["x0"]), 2), round(float(o["top"]), 2),
                       round(float(o["x1"]), 2), round(float(o["bottom"]), 2)]
                      for o in page.images]
            # pdfplumber exposes the same vector geometry under three lists
            drawings: List[List[float]] = []
            try:
                for key in ("rects", "lines", "curves"):
                    for o in getattr(page, key, []) or []:
                        try:
                            drawings.append([round(float(o["x0"]), 2), round(float(o["top"]), 2),
                                             round(float(o["x1"]), 2), round(float(o["bottom"]), 2), 1])
                        except Exception:
                            continue
            except Exception:
                drawings = []
            pages.append({
                "number": pno,
                "width": round(float(page.width), 2),
                "height": round(float(page.height), 2),
                "rotation": int(page.rotation or 0),
                "chars": chars,
                "images": images,
                "drawings": drawings,
                "blocks": blocks,
            })
    import pdfplumber  # type: ignore
    return {"backend": "pdfplumber " + getattr(pdfplumber, "__version__", "?"), "pages": pages}


# --------------------------------------------------------------------------- #
# pypdf
# --------------------------------------------------------------------------- #
def _extract_pypdf(path: str) -> Dict[str, Any] | None:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return None
    try:
        reader = PdfReader(path)
    except Exception:
        return None
    pages: List[Dict[str, Any]] = []
    for pno, page in enumerate(reader.pages, 1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        lines = []
        y = 20.0
        for ln in text.splitlines():
            if not ln.strip():
                y += 12
                continue
            lines.append({"text": ln, "bbox": [0, round(y, 2), width, round(y + 11, 2)],
                          "size": 0.0, "bold": False, "italic": False, "font": ""})
            y += 12
        pages.append({
            "number": pno, "width": round(width, 2), "height": round(height, 2),
            "rotation": 0, "chars": len(text), "images": [],
            "blocks": [{"bbox": [0, 0, width, height], "lines": lines}] if lines else [],
        })
    import pypdf  # type: ignore
    return {"backend": "pypdf " + getattr(pypdf, "__version__", "?"), "pages": pages}


# --------------------------------------------------------------------------- #
# poppler / platform CLI
# --------------------------------------------------------------------------- #
def _extract_poppler(path: str) -> Dict[str, Any] | None:
    exe = shutil.which("pdftotext") or shutil.which("pdf-text-tool")
    if not exe:
        return None
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "out.txt")
        cmd = [exe, "-layout", path, out]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=180)
        except Exception:
            return None
        if not os.path.exists(out):
            return None
        with open(out, "r", encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
    pages_raw = raw.split("\f")
    pages: List[Dict[str, Any]] = []
    for pno, chunk in enumerate(pages_raw, 1):
        if chunk == "" and pno == len(pages_raw):
            break
        lines = []
        y = 20.0
        for ln in chunk.splitlines():
            if not ln.strip():
                y += 10
                continue
            lines.append({"text": ln, "bbox": [0, round(y, 2), 600, round(y + 10, 2)],
                          "size": 0.0, "bold": False, "italic": False, "font": ""})
            y += 11
        pages.append({"number": pno, "width": 600.0, "height": max(800.0, y),
                      "rotation": 0, "chars": len(chunk), "images": [],
                      "blocks": [{"bbox": [0, 0, 600, y], "lines": lines}] if lines else []})
    return {"backend": "poppler pdftotext", "pages": pages}


# --------------------------------------------------------------------------- #
# public entry point
# --------------------------------------------------------------------------- #
BACKENDS = [
    ("pymupdf", _extract_fitz),
    ("pdfplumber", _extract_plumber),
    ("pypdf", _extract_pypdf),
    ("poppler", _extract_poppler),
]


def available_backends() -> List[str]:
    names = []
    for name, fn in BACKENDS:
        try:
            if name == "pymupdf":
                import fitz  # noqa: F401
            elif name == "pdfplumber":
                import pdfplumber  # noqa: F401
            elif name == "pypdf":
                import pypdf  # noqa: F401
            elif name == "poppler":
                if not (shutil.which("pdftotext") or shutil.which("pdf-text-tool")):
                    continue
            names.append(name)
        except Exception:
            continue
    return names


def diagnose(path: str, attempts: List[Dict[str, str]]) -> Dict[str, Any]:
    """Say *why* nothing could be read, in words a reviewer can act on.

    The rubric explicitly lists encrypted PDFs, scans without a text layer and
    corrupted files.  Those are results to report, not exceptions to raise.
    """
    info: Dict[str, Any] = {"kind": "unknown", "detail": "", "encrypted": False,
                            "pages": 0, "attempts": attempts}
    try:
        import fitz
        doc = fitz.open(path)
        info["pages"] = doc.page_count
        info["encrypted"] = bool(doc.needs_pass)
        if doc.needs_pass:
            info["kind"] = "encrypted"
            info["detail"] = ("PDF is password protected and no password was supplied; "
                              "text cannot be read without it")
        elif doc.page_count == 0:
            info["kind"] = "empty"
            info["detail"] = "PDF reports zero pages"
        else:
            probe = range(min(3, doc.page_count))
            has_img = any(doc[i].get_images(full=True) for i in probe)
            info["kind"] = "scan_without_text_layer" if has_img else "no_extractable_text"
            info["detail"] = ("pages carry images but no text layer; OCR is required"
                              if has_img else "no extractable text found on the first pages")
        doc.close()
    except Exception as exc:
        info["kind"] = "unreadable"
        info["detail"] = f"{type(exc).__name__}: {exc}"
    return info


def extract(path: str) -> Dict[str, Any]:
    """Extract every page with the best available engine.

    Returns the first successful result plus a `attempts` log.  Pages that came
    back empty are re-tried with the remaining engines (mixed digital/scan PDFs).
    """
    attempts: List[Dict[str, str]] = []
    best: Dict[str, Any] | None = None
    best_score = -1
    for name, fn in BACKENDS:
        try:
            res = fn(path)
        except Exception as exc:
            attempts.append({"backend": name, "status": "error", "detail": f"{type(exc).__name__}: {exc}"})
            continue
        if not res or not res.get("pages"):
            attempts.append({"backend": name, "status": "empty"})
            continue
        good = sum(1 for p in res["pages"] if p["chars"] >= MIN_PAGE_CHARS)
        score = good * 1000 + sum(p["chars"] for p in res["pages"]) / 1000.0
        attempts.append({"backend": name, "status": "ok",
                         "pages_with_text": good, "chars": sum(p["chars"] for p in res["pages"])})
        if score > best_score:
            best, best_score = res, score
        if good == len(res["pages"]):
            break
    if best is None:
        # Never raise: an unreadable PDF (encrypted, truncated, not a PDF) is a
        # *result* the caller must be able to report, not a crash.  The reason is
        # kept so result.json can say why instead of dying with a traceback.
        return {"backend": "none", "pages": [], "attempts": attempts,
                "error": diagnose(path, attempts)}

    # fill empty pages with a secondary engine, if any
    if any(p["chars"] < MIN_PAGE_CHARS for p in best["pages"]):
        for name, fn in BACKENDS:
            if name in best["backend"]:
                continue
            try:
                alt = fn(path)
            except Exception:
                continue
            if not alt:
                continue
            alt_pages = {p["number"]: p for p in alt["pages"]}
            for p in best["pages"]:
                if p["chars"] < MIN_PAGE_CHARS and alt_pages.get(p["number"], {}).get("chars", 0) > p["chars"]:
                    p["blocks"] = alt_pages[p["number"]]["blocks"]
                    p["chars"] = alt_pages[p["number"]]["chars"]
                    p["filled_by"] = alt["backend"]
            if all(p["chars"] >= MIN_PAGE_CHARS for p in best["pages"]):
                break

    best["attempts"] = attempts
    best["path"] = path
    return best


def tables(path: str, pages: List[int] | None = None) -> List[Dict[str, Any]]:
    out = _fitz_tables(path, pages)
    if out:
        return out
    return _plumber_tables(path, pages)


def _plumber_tables(path: str, pages: List[int] | None = None) -> List[Dict[str, Any]]:
    try:
        import pdfplumber  # type: ignore
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    try:
        with pdfplumber.open(path) as pdf:
            for pno, page in enumerate(pdf.pages, 1):
                if pages and pno not in pages:
                    continue
                try:
                    found = page.extract_tables()
                except Exception:
                    continue
                for tbl in found or []:
                    rows = [[(c or "").strip() for c in row] for row in tbl]
                    rows = [r for r in rows if any(r)]
                    if len(rows) < 2:
                        continue
                    out.append({"page": pno, "bbox": None, "rows": rows})
    except Exception:
        return out
    return out


def render_page(path: str, page: int, dpi: int = 200) -> bytes | None:
    """Render one page to PNG bytes for OCR or visual checks."""
    try:
        import fitz  # type: ignore
    except Exception:
        fitz = None
    if fitz is not None:
        try:
            doc = fitz.open(path)
            pg = doc.load_page(page - 1)
            pix = pg.get_pixmap(dpi=dpi)
            data = pix.tobytes("png")
            doc.close()
            return data
        except Exception:
            return None
    exe = shutil.which("pdf-render-tool") or shutil.which("pdftoppm")
    if exe:
        with tempfile.TemporaryDirectory() as td:
            prefix = os.path.join(td, "p")
            cmd = [exe, "-r", str(dpi), "-f", str(page), "-l", str(page), "-png", path, prefix] \
                if exe.endswith("pdftoppm") else [exe, path, "-p", str(page), "-dpi", str(dpi), "-o", prefix]
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=180)
                for fn in sorted(os.listdir(td)):
                    if fn.startswith("p") and fn.endswith(".png"):
                        with open(os.path.join(td, fn), "rb") as fh:
                            return fh.read()
            except Exception:
                return None
    return None


def ocr_image(png: bytes, lang: str = "eng") -> str | None:
    """OCR a PNG through tesseract or the platform ocr-tool, if present."""
    exe = shutil.which("tesseract")
    with tempfile.TemporaryDirectory() as td:
        img = os.path.join(td, "page.png")
        with open(img, "wb") as fh:
            fh.write(png)
        if exe:
            try:
                proc = subprocess.run([exe, img, "stdout", "-l", lang, "--psm", "3"],
                                      capture_output=True, timeout=300)
                if proc.returncode == 0:
                    return proc.stdout.decode("utf-8", "replace")
            except Exception:
                pass
        exe2 = shutil.which("ocr-tool")
        if exe2:
            try:
                proc = subprocess.run([exe2, img], capture_output=True, timeout=300)
                if proc.returncode == 0:
                    return proc.stdout.decode("utf-8", "replace")
            except Exception:
                pass
    return None
