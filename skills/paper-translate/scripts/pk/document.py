"""Orchestration: a PDF (plus its folder) becomes an evidence-linked document model."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from typing import Any, Dict, List

from . import backends, layout, sources, structure
from .evidence import locator, quote

# Private Use Area + the replacement character: what a font without a usable
# `toUnicode` map produces.  See `garbled_pages`.
PUA_CHAR = re.compile("[\ue000-\uf8ff\ufffd]")
CAPTION_TABLE = structure.CAPTION_TABLE


def _flatten(extracted: Dict[str, Any]) -> List[Dict[str, Any]]:
    pages = []
    for p in extracted["pages"]:
        lines: List[Dict[str, Any]] = []
        for b in p["blocks"]:
            for ln in b["lines"]:
                if not ln["text"].strip():
                    continue
                lines.append({
                    "text": ln["text"],
                    "bbox": [round(v, 2) for v in ln["bbox"]],
                    "size": ln.get("size", 0.0),
                    "bold": bool(ln.get("bold")),
                    "italic": bool(ln.get("italic")),
                })
        pages.append({
            "number": p["number"], "width": p["width"], "height": p["height"],
            "rotation": p.get("rotation", 0), "chars": p["chars"],
            "images": p.get("images", []), "filled_by": p.get("filled_by"),
            "drawings": p.get("drawings", []),
            "lines": lines,
        })
    return pages


def _ocr_pages(pdf_path: str, pages: List[Dict[str, Any]], lang: str = "eng",
               force: set | None = None) -> List[int]:
    """OCR pages that have almost no text layer but do carry images.

    A page that needed OCR and did not get it is marked `ocr_failed`, so the
    report can say "OCR was required here but no engine was available" instead
    of silently returning an empty page.  `force` re-OCRs pages whose text layer
    exists but is garbage (a font without a usable `toUnicode` map).
    """
    done: List[int] = []
    force = force or set()
    for p in pages:
        if p["number"] in force:
            pass
        elif p["chars"] >= backends.MIN_PAGE_CHARS or not p["images"]:
            continue
        png = backends.render_page(pdf_path, p["number"], dpi=220)
        if not png:
            p["ocr_failed"] = "page could not be rendered"
            continue
        text = backends.ocr_image(png, lang=lang)
        if not text or len(text.strip()) < 20:
            p["ocr_failed"] = "OCR engine returned no text (tesseract missing or failed)"
            continue
        lines = []
        y = 20.0
        for ln in text.splitlines():
            if not ln.strip():
                y += 8
                continue
            lines.append({"text": ln, "bbox": [0, round(y, 2), p["width"], round(y + 10, 2)],
                          "size": 10.0, "bold": False, "italic": False})
            y += 11
        p["lines"] = lines
        p["chars"] = len(text)
        p["filled_by"] = "ocr"
        done.append(p["number"])
    return done


def _unreadable(pdf_path: str, extracted: Dict[str, Any]) -> Dict[str, Any]:
    """Same schema as a normal result, but empty and with the reason attached.

    Downstream code (composers, contract adapter, verify) then keeps working and
    the output says "encrypted, no password" instead of a traceback.
    """
    info = extracted.get("error") or {"kind": "unreadable", "detail": "no pages extracted"}
    exists = os.path.exists(pdf_path)
    return {
        "schema": "paperkit/document@1",
        "source": {
            "path": os.path.abspath(pdf_path), "name": os.path.basename(pdf_path),
            "bytes": os.path.getsize(pdf_path) if exists else None,
            "sha256": sources.sha256(pdf_path) if exists else None,
            "pages": info.get("pages") or 0,
            "backend": extracted.get("backend", "none"),
            "attempts": extracted.get("attempts", []),
            "ocr_pages": [], "has_text_layer": False, "error": info,
            "encrypted": bool(info.get("encrypted")), "decryption": "",
            "decrypted": False,
        },
        "meta": {"title": "", "authors": [], "abstract": "", "keywords": [], "doi": ""},
        "sections": [], "blocks": [], "tables": [], "figures": [], "formulas": [],
        "references": [], "page_stats": [], "running_heads_removed": 0, "header_footer": [],
        "verbatim_text": "", "verbatim_chars": 0,
        "verbatim": {"chars_in_layer": 0, "chars_in_blocks": 0, "chars_in_header_footer": 0,
                     "matched": 0, "ratio": 0.0, "missing": 0, "extra": 0,
                     "hyphen_merged_blocks": 0, "sample_missing": "", "sample_extra": ""},
        "quality": {"pages": info.get("pages") or 0, "chars": 0, "chars_per_page": 0.0,
                    "blocks": 0, "tables": 0, "formulas": 0, "references": 0,
                    "empty_pages": [],
                    "verbatim": {"ratio": 0.0, "missing": 0, "extra": 0,
                                 "hyphen_merged_blocks": 0},
                    "issues": [f"{info.get('kind')}: {info.get('detail')}"]},
    }


def analyze_path(pdf_path: str, ocr: bool = True) -> Dict[str, Any]:
    extracted = backends.extract(pdf_path)
    pages = _flatten(extracted)
    if not pages:
        return _unreadable(pdf_path, extracted)
    # Remember whether any page had a real text layer *before* OCR: after OCR
    # every scanned page has chars, but the evidence is still OCR, not a layer.
    had_text_layer = any(p["chars"] >= backends.MIN_PAGE_CHARS for p in pages)
    # A page whose text layer is font garbage must be OCR'd, not trusted: the
    # PUA code points look like text and would poison every downstream field.
    garbled = garbled_pages(pages)
    force = set(garbled["pages"]) if ocr else set()
    ocr_done = _ocr_pages(pdf_path, pages, force=force) if ocr else []
    if garbled["pages"]:
        for p in pages:
            if p["number"] in garbled["pages"] and p.get("filled_by") == "ocr":
                p["text_layer_garbled"] = True
    garbled = garbled_pages(pages)     # recount after OCR

    # Snapshot the engine's own text before any cleaning.  Reviewers can diff
    # this against the PDF text layer to check "逐字一致" instead of trusting us.
    verbatim = "\n".join(l["text"] for p in pages for l in p["lines"])

    # Read the printed page numbers *before* the running-head stripper runs: it
    # normalises digits, so a footer "1", "2", "3" counts as a repeated line and
    # would be removed -- taking the pagination evidence with it.
    order = page_order(pages)
    heads = layout.strip_running_heads(pages)
    body = layout.body_font_size(pages)
    for p in pages:
        layout.order_page(p)

    blocks = layout.build_blocks(pages, body)
    # `Abstract The structure ...` is a heading the size test cannot see.
    blocks = structure.split_inline_headings(blocks, body)
    blocks = structure.split_tail_headings(blocks)
    # Every block says which engine produced it: a page that needed OCR is not
    # the same evidence as a born-digital text layer, and a reviewer cannot
    # tell them apart from `bbox` alone.
    page_engine = {p["number"]: (p.get("filled_by") or extracted["backend"]) for p in pages}
    for b in blocks:
        b.setdefault("engine", page_engine.get(b["page"], extracted["backend"]))
    blocks = structure.split_ocr_sections(blocks)
    sections, blocks = structure.build_sections(blocks, body)
    # Rejoin visual-line fragments before captions/tables attach: "0.9" and
    # "percent" separated by a line break are one measurement, not two blocks.
    blocks = structure.merge_line_fragments(blocks, body)
    sections, blocks = structure.build_sections(blocks, body)

    raw_tables = backends.tables(pdf_path)
    if not raw_tables:
        raw_tables = structure.detect_tables_from_lines(pages)
    tables: List[Dict[str, Any]] = []
    for i, t in enumerate(raw_tables, 1):
        norm = structure.normalize_table(t["rows"])
        if norm["n_rows"] < 2 or norm["n_cols"] < 2:
            continue
        tables.append({"id": f"t{i}", "page": t["page"], "bbox": t.get("bbox"),
                       "caption": "", "caption_block": None,
                       "header": norm["header"], "header_rows": norm.get("header_rows") or [],
                       "rows": norm.get("data_rows") or norm["rows"],
                       "rows_all": norm["rows"],
                       "data_rows": norm.get("data_rows") or [],
                       "markdown": norm["markdown"], "n_rows": norm["n_rows"],
                       "n_cols": norm["n_cols"],
                       "multi_level_header": norm.get("multi_level_header", False),
                       "source": t.get("source", "engine")})
    tables = structure.merge_continuations(tables)

    figures = structure.find_figures(pages, tables=tables, blocks=blocks)
    structure.attach_captions(blocks, tables, figures)
    figures, figures_dropped = structure.prune_figures(figures)
    table_region_blocks = structure.mark_table_blocks(blocks, tables)
    footnotes, margin_notes = structure.mark_notes(blocks, pages)
    # Section detection ran before the table regions were known, so a cell that
    # happens to look like "3.0 Contact" had already become a heading.  Rebuild
    # now that those blocks carry `type=table` and are skipped.
    sections, blocks = structure.build_sections(blocks, body)
    image_tables = find_image_tables(pages, blocks, tables, pdf_path=pdf_path)

    formulas = structure.find_formulas(blocks)
    references = structure.find_references(blocks)
    meta = structure.extract_metadata(pages, blocks, body)

    for b in blocks:
        b["locator"] = locator(b)

    empty_pages = [p["number"] for p in pages if p["chars"] < backends.MIN_PAGE_CHARS]
    doc = {
        "schema": "paperkit/document@1",
        "source": {
            "path": os.path.abspath(pdf_path),
            "name": os.path.basename(pdf_path),
            "bytes": os.path.getsize(pdf_path) if os.path.exists(pdf_path) else None,
            "sha256": sources.sha256(pdf_path) if os.path.exists(pdf_path) else None,
            "pages": len(pages),
            "backend": extracted["backend"],
            "attempts": extracted.get("attempts", []),
            "ocr_pages": ocr_done,
            "has_text_layer": had_text_layer,
            # A permissions-locked PDF (owner password, empty user password) is
            # readable; saying so keeps "encrypted" from being read as "failed".
            "encrypted": bool(extracted.get("encryption")
                              or extracted.get("decrypted_with")),
            "decryption": extracted.get("encryption")
                          or (f"password {extracted['decrypted_with']}"
                              if extracted.get("decrypted_with") else ""),
            "decrypted": bool(extracted.get("encryption")
                              or extracted.get("decrypted_with"))
                          and sum(p["chars"] for p in pages) > 0,
        },
        "meta": meta,
        "sections": sections,
        "footnotes": footnotes,
        "margin_notes": margin_notes,
        "blocks": blocks,
        "tables": tables,
        "figures": figures,
        "figures_dropped": figures_dropped,
        "image_tables": image_tables,
        "page_order": order,
        "garbled": garbled,
        "formulas": formulas,
        "references": references,
        "page_stats": [{"page": p["number"], "chars": p["chars"], "lines": len(p["lines"]),
                        "w": p.get("width"), "h": p.get("height"),
                        "columns": p.get("columns", 1), "bands": p.get("bands", 1),
                        "gutters": p.get("gutters", []), "filled_by": p.get("filled_by"),
                        "ocr_failed": p.get("ocr_failed"),
                        "order_rule": p.get("order_rule", "naive-y")}
                       for p in pages],
        "running_heads_removed": heads["count"],
        # every dropped running head / page number / stamp, with its bbox:/n        # marking instead of silently deleting is what makes the verbatim
        # claim checkable
        "header_footer": heads.get("removed", []),
        "verbatim_text": verbatim,
        "verbatim_chars": len(verbatim),
        # What the untouched layer had vs. what the blocks carry.  This is the
        # "逐字一致" number, computed here so it also ships in coverage.json;
        # verify.py --pdf recomputes it from the PDF itself.
        "verbatim": _verbatim_ledger(verbatim, blocks, heads.get("removed") or []),
        "quality": _quality(pages, blocks, tables, formulas, references, empty_pages,
                            figures, figures_dropped, table_region_blocks,
                            garbled, order, image_tables),
    }
    # Surface the ledger where a reviewer looks first (coverage.json), not only
    # in the full doc.json.
    v = doc["verbatim"]
    doc["quality"]["verbatim"] = {"ratio": v["ratio"], "missing": v["missing"],
                                  "extra": v["extra"],
                                  "hyphen_merged_blocks": v["hyphen_merged_blocks"]}
    if v["ratio"] < 0.995 or v["extra"] > max(20, v["chars_in_blocks"] * 0.002):
        doc["quality"]["issues"].append(
            f"verbatim ledger: {v['missing']} char(s) in the text layer are not in the "
            f"blocks, {v['extra']} char(s) in the blocks are not in the layer "
            f"(coverage {v['ratio']:.3f}); see doc.json verbatim")
    return doc


def _verbatim_ledger(raw: str, blocks: List[Dict[str, Any]],
                     removed: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Character-multiset audit: the raw layer vs. what the blocks deliver.

    `missing` is text the PDF had and the deliverable lost; `extra` is text the
    deliverable invented.  Running heads are counted as *explained* removals
    (they are listed in `header_footer`), ligature expansion and line-break
    hyphens are expected single-character transforms.  On a born-digital paper
    both numbers should be tiny; a large `missing` means the cleaner ate text.
    """
    from collections import Counter

    def pack(s: str) -> Counter:
        for k, v in layout.LIGATURES.items():
            s = s.replace(k, v)
        return Counter(c for c in s if not c.isspace())

    layer = pack(raw)
    body = pack("".join(b.get("text_raw") or b.get("text") or "" for b in blocks))
    heads = pack("".join(h.get("text") or "" for h in removed))
    kept = layer & (body + heads)
    missing = layer - body - heads
    extra = body - layer
    total = sum(layer.values()) or 1
    return {
        "chars_in_layer": sum(layer.values()),
        "chars_in_blocks": sum(body.values()),
        "chars_in_header_footer": sum(heads.values()),
        "matched": sum(kept.values()),
        "ratio": round(sum(kept.values()) / total, 4),
        "missing": sum(missing.values()),
        "extra": sum(extra.values()),
        "hyphen_merged_blocks": sum(1 for b in blocks if b.get("hyphen_merged")),
        "sample_missing": "".join(c for c, _ in missing.most_common(12)),
        "sample_extra": "".join(c for c, _ in extra.most_common(12)),
    }


def _quality(pages, blocks, tables, formulas, references, empty_pages,
             figures=(), figures_dropped=(), table_region_blocks=0,
             garbled=None, order=None, image_tables=()) -> Dict[str, Any]:
    total_chars = sum(p["chars"] for p in pages)
    issues: List[str] = []
    if empty_pages:
        issues.append(f"{len(empty_pages)} page(s) without a text layer: {empty_pages[:10]}")
    failed = [p["number"] for p in pages if p.get("ocr_failed")]
    if failed:
        issues.append(f"OCR was required but produced nothing on page(s) {failed[:10]}: "
                      f"install tesseract (`apt-get install -y tesseract-ocr`) to fill them")
    if not tables:
        issues.append("no tables detected (either none in the paper or engine lacks table support)")
    if not references:
        issues.append("no reference list detected")
    if not figures:
        issues.append("no figures detected (raster images and vector chart clusters both "
                      "came up empty)")
    if garbled and garbled.get("pua_chars"):
        pages_hit = garbled.get("pages") or []
        issues.append(
            f"{garbled['pua_chars']} private-use/replacement character(s) suggest a font "
            f"without a usable toUnicode map"
            + (f"; OCR replaced the text layer on page(s) {pages_hit[:8]}" if pages_hit
               else "; install tesseract so those pages can be re-OCR'd"))
    if order and order.get("warning"):
        issues.append("printed page numbers are not in order: "
                      + str(order.get("breaks")[:5])
                      + " — page references in downstream answers may be off")
    if image_tables:
        issues.append(f"{len(image_tables)} table(s) look like images (caption present, no "
                      f"text layer in the region): pages "
                      + str(sorted({t['page'] for t in image_tables})[:8])
                      + "; their cells are NOT in tables[] and must not be invented")
    return {
        "pages": len(pages),
        "chars": total_chars,
        "chars_per_page": round(total_chars / max(1, len(pages)), 1),
        "blocks": len(blocks),
        "tables": len(tables),
        "figures": len(figures),
        "figures_dropped": len(figures_dropped),
        "blocks_in_table_regions": table_region_blocks,
        "image_tables": len(image_tables),
        "page_order_warning": bool(order and order.get("warning")),
        "garbled_chars": (garbled or {}).get("pua_chars", 0),
        "formulas": len(formulas),
        "references": len(references),
        "empty_pages": empty_pages,
        "issues": issues,
    }


def garbled_pages(pages: List[Dict[str, Any]], threshold: float = 0.02) -> Dict[str, Any]:
    """Pages whose text layer is font garbage rather than text.

    A PDF font without a `toUnicode` map yields Private Use Area code points
    (U+E000-U+F8FF) or U+FFFD.  That text looks non-empty, so a naive pipeline
    silently returns mojibake -- which would break "逐字一致" in the worst way.
    Counted per page so the caller can OCR just those pages.
    """
    total = bad = 0
    hits: List[int] = []
    per_page: Dict[int, int] = {}
    for p in pages:
        n = 0
        for l in p.get("lines", []):
            text = l.get("text") or ""
            total += len(text)
            n += sum(1 for ch in text if PUA_CHAR.match(ch))
        if n:
            per_page[p["number"]] = n
            bad += n
        if p.get("chars") and n / max(1, p["chars"]) > threshold:
            hits.append(p["number"])
    return {"pua_chars": bad, "chars": total,
            "ratio": round(bad / total, 4) if total else 0.0,
            "pages": hits, "per_page": per_page}


def page_order(pages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Read the printed page numbers and say whether they run in order.

    Scanned books and re-assembled PDFs are sometimes paginated out of order,
    which makes every "see page N" claim in the result wrong.  Only stand-alone
    numbers in the top/bottom margin are treated as page numbers.
    """
    numbers: List[Any] = []
    for p in pages:
        h = float(p.get("height") or 0)
        hit = None
        for l in p.get("lines", []):
            text = (l.get("text") or "").strip()
            if not re.fullmatch(r"[-–—]?\s*\d{1,4}\s*[-–—]?", text):
                continue
            y0, y1 = float(l["bbox"][1]), float(l["bbox"][3])
            if h and (y1 < h * 0.1 or y0 > h * 0.9):
                hit = int(re.sub(r"\D", "", text))
                break
        numbers.append(hit)
    found = [n for n in numbers if n is not None]
    dups = sorted({n for n in found if found.count(n) > 1})
    breaks = [(a, b) for a, b in zip(found, found[1:]) if b != a + 1]
    return {"printed_numbers": numbers, "found": len(found),
            "in_order": not breaks, "duplicates": dups[:10],
            "breaks": breaks[:10],
            "warning": bool(found and len(found) >= 3 and breaks)}


def _vgap(a: List[float], b: List[float]) -> float:
    """Vertical distance between two boxes; 0 when they overlap."""
    if a[3] < b[1]:
        return b[1] - a[3]
    if b[3] < a[1]:
        return a[1] - b[3]
    return 0.0


def find_image_tables(pages: List[Dict[str, Any]], blocks: List[Dict[str, Any]],
                      tables: List[Dict[str, Any]],
                      pdf_path: str = "") -> List[Dict[str, Any]]:
    """Tables that exist only as a picture.

    A `Table N` caption with no extracted table beside it means the table is an
    image: there is no text layer to fall back on, so the honest answer is to
    say so rather than report "no tables".  Only pages that carry images are
    considered, so a born-digital paper never triggers this.
    """
    out: List[Dict[str, Any]] = []
    for p in pages:
        if not p.get("images"):
            continue
        for b in blocks:
            if b.get("page") != p["number"] or not CAPTION_TABLE.match(b.get("text") or ""):
                continue
            if any(t.get("page") == p["number"] and t.get("bbox")
                   and _vgap(t["bbox"], b["bbox"]) < 120 for t in tables):
                continue      # this caption already belongs to an extracted table
            near = [img for img in p["images"] if _vgap(img, b["bbox"]) < 220]
            if near:
                out.append({"page": p["number"], "caption": b["text"][:160],
                            "caption_block": b.get("id"), "image_bbox": near[0],
                            "ocr_text": "", "ocr_engine": "",
                            "note": "table exists only as an image; no text layer to read"})
    if out:
        # If an OCR engine happens to be installed, try the crop.  Without one the
        # entry stays as a marker, which is the honest outcome -- the alternative
        # is reporting "no tables", which is worse than reporting "a table I
        # could not read".
        engine = _ocr_engine()
        for item in out:
            item["ocr_engine"] = engine or ""
            if engine:
                item["ocr_text"] = _ocr_region(pdf_path, item)
            item["note"] = ("table exists only as an image; OCR text below is approximate"
                            if item["ocr_text"] else
                            "table exists only as an image; no OCR engine available")
    return out


def _ocr_engine() -> str:
    for name in ("tesseract",):
        try:
            import shutil
            if shutil.which(name):
                return name
        except Exception:
            pass
    try:
        import pytesseract  # type: ignore  # noqa: F401
        return "pytesseract"
    except Exception:
        return ""


def _ocr_region(pdf_path: str, item: Dict[str, Any]) -> str:
    """OCR one image region. Any failure returns "" rather than raising."""
    try:
        import fitz  # type: ignore
    except Exception:
        return ""
    try:
        if not pdf_path or not os.path.exists(pdf_path):
            return ""
        doc = fitz.open(pdf_path)
        src = doc.load_page(int(item["page"]) - 1)
        clip = fitz.Rect(item["image_bbox"])
        pix = src.get_pixmap(clip=clip, dpi=200)
        tmp = os.path.join(tempfile.gettempdir(), f"imgtable-{item['page']}.png")
        pix.save(tmp)
        if item["ocr_engine"] == "tesseract":
            out = subprocess.run(["tesseract", tmp, "stdout", "--psm", "6"],
                                 capture_output=True, text=True, timeout=60)
            return (out.stdout or "").strip()[:4000]
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
        return (pytesseract.image_to_string(Image.open(tmp)) or "").strip()[:4000]
    except Exception:
        return ""
    finally:
        try:
            doc.close()  # type: ignore[name-defined]
        except Exception:
            pass


def analyze(input_dir: str, ocr: bool = True) -> Dict[str, Any]:
    """Analyse a whole case directory: primary PDF + every supporting material."""
    man = sources.discover(input_dir)
    case = sources.load_case(man["case_json"])
    task = sources.read_text(man["task_md"]) if man["task_md"] else ""
    doc: Dict[str, Any] = {
        "schema": "paperkit/case@1",
        "input": {k: man[k] for k in ("root", "primary_pdf", "case_json", "task_md")},
        "files": man["files"],
        "case": case,
        "task": task,
        "document": None,
        "materials": {},
        "extra_pdfs": [],
        "quality": {},
    }
    if man.get("problem"):
        doc["input"]["problem"] = man["problem"]
    if man["primary_pdf"]:
        doc["document"] = analyze_path(man["primary_pdf"], ocr=ocr)
        doc["quality"] = doc["document"]["quality"]
        for other in man["pdfs"]:
            if other == man["primary_pdf"]:
                continue
            try:
                sub = analyze_path(other, ocr=ocr)
                doc["extra_pdfs"].append({"path": other, "pages": sub["source"]["pages"],
                                          "chars": sub["quality"]["chars"],
                                          "title": sub["meta"].get("title", ""),
                                          "sha256": sub["source"]["sha256"]})
            except Exception as exc:
                doc["extra_pdfs"].append({"path": other, "error": f"{type(exc).__name__}: {exc}"})
    elif man.get("primary_text"):
        # No PDF, but the case is not empty: markdown, LaTeX, BibTeX, CSV and
        # JSON are first-class inputs.  They become the same `document` model
        # (blocks + sections + tables + references), so every composer works
        # unchanged and evidence keeps its p01-bNNN anchors.
        from . import textdoc
        doc["document"] = textdoc.analyze_text(input_dir, man, case, task)
        doc["quality"] = doc["document"]["quality"]
    if doc["document"]:
        doc["materials"] = dict(doc["document"].pop("_materials", {}) or {})
    for role, paths in man["by_role"].items():
        if role in {"pdf", "image"}:
            continue
        for p in paths[:12]:
            name = os.path.basename(p)
            if name in doc["materials"]:
                continue
            try:
                txt = sources.read_text(p)
            except Exception as exc:
                txt = f"<unreadable: {exc}>"
            doc["materials"][name] = {"role": role, "chars": len(txt),
                                      "text": txt[:200_000]}
    return doc


def to_markdown(doc: Dict[str, Any], max_blocks: int = 400) -> str:
    d = doc.get("document") or {}
    if not d:
        return "# (no document parsed)\n"
    out = [f"# {d['meta'].get('title') or d['source']['name']}", ""]
    out.append(f"*backend*: {d['source']['backend']} · *pages*: {d['source']['pages']} · "
               f"*blocks*: {len(d['blocks'])} · *tables*: {len(d['tables'])} · "
               f"*figures*: {len(d.get('figures', []))} · "
               f"*formulas*: {len(d.get('formulas', []))} · "
               f"*references*: {len(d.get('references', []))}")
    out.append("")
    for b in d["blocks"][:max_blocks]:
        tag = b["type"]
        if tag == "table":
            # already rendered cell-by-cell in the table section below; keeping
            # the raw cells here duplicates text and breaks reading order
            continue
        head = f"[{b['id']} p{b['page']}]"
        if tag == "heading":
            out.append(f"\n{'#' * min(4, max(1, b.get('level', 1)))} {b['text'].strip()}  {head}")
        else:
            out.append(f"{head} {b['text']}")
    figs = d.get("figures") or []
    tabs = d.get("tables") or []
    if figs or tabs:
        out.extend(["", "## 图表位置（figure / table positions）", ""])
        if figs:
            out.append("| id | page | kind | bbox (x0,y0,x1,y1) | area% | caption |")
            out.append("|---|---|---|---|---|---|")
            for f in figs:
                cap = (f.get("caption") or "").replace("|", "\\|")[:80]
                bb = ",".join(str(round(v)) for v in (f.get("bbox") or []))
                out.append(f"| {f['id']} | {f['page']} | {f.get('kind','')} | {bb} | "
                           f"{round(100 * (f.get('area_ratio') or 0), 1)} | {cap} |")
        if tabs:
            out.append("")
            out.append("| id | page | rows×cols | bbox | caption |")
            out.append("|---|---|---|---|---|")
            for t in tabs:
                cap = (t.get("caption") or "").replace("|", "\\|")[:80]
                bb = ",".join(str(round(v)) for v in (t.get("bbox") or []))
                out.append(f"| {t['id']} | {t['page']} | {t.get('n_rows')}×{t.get('n_cols')} | "
                           f"{bb} | {cap} |")
            for t in tabs:
                md = (t.get("markdown") or "").strip()
                if not md:
                    continue
                out.extend(["", f"**{t['id']}** · p{t['page']}", "", "```markdown", md, "```"])
    return "\n".join(out)


def dump(doc: Dict[str, Any], out_path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
