"""Orchestration: a PDF (plus its folder) becomes an evidence-linked document model."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from . import backends, layout, sources, structure
from .evidence import locator, quote


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


def _ocr_pages(pdf_path: str, pages: List[Dict[str, Any]], lang: str = "eng") -> List[int]:
    """OCR pages that have almost no text layer but do carry images.

    A page that needed OCR and did not get it is marked `ocr_failed`, so the
    report can say "OCR was required here but no engine was available" instead
    of silently returning an empty page.
    """
    done: List[int] = []
    for p in pages:
        if p["chars"] >= backends.MIN_PAGE_CHARS or not p["images"]:
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
        },
        "meta": {"title": "", "authors": [], "abstract": "", "keywords": [], "doi": ""},
        "sections": [], "blocks": [], "tables": [], "figures": [], "formulas": [],
        "references": [], "page_stats": [], "running_heads_removed": 0,
        "quality": {"pages": info.get("pages") or 0, "chars": 0, "chars_per_page": 0.0,
                    "blocks": 0, "tables": 0, "formulas": 0, "references": 0,
                    "empty_pages": [],
                    "issues": [f"{info.get('kind')}: {info.get('detail')}"]},
    }


def analyze_path(pdf_path: str, ocr: bool = True) -> Dict[str, Any]:
    extracted = backends.extract(pdf_path)
    pages = _flatten(extracted)
    if not pages:
        return _unreadable(pdf_path, extracted)
    ocr_done = _ocr_pages(pdf_path, pages) if ocr else []

    # Snapshot the engine's own text before any cleaning.  Reviewers can diff
    # this against the PDF text layer to check "逐字一致" instead of trusting us.
    verbatim = "\n".join(l["text"] for p in pages for l in p["lines"])

    heads = layout.strip_running_heads(pages)
    body = layout.body_font_size(pages)
    for p in pages:
        layout.order_page(p)

    blocks = layout.build_blocks(pages, body)
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
                       "header": norm["header"], "rows": norm["rows"],
                       "markdown": norm["markdown"], "n_rows": norm["n_rows"],
                       "n_cols": norm["n_cols"], "source": t.get("source", "engine")})

    figures = structure.find_figures(pages, tables=tables, blocks=blocks)
    structure.attach_captions(blocks, tables, figures)
    figures, figures_dropped = structure.prune_figures(figures)
    table_region_blocks = structure.mark_table_blocks(blocks, tables)

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
            "has_text_layer": len(empty_pages) < max(1, len(pages) // 2),
        },
        "meta": meta,
        "sections": sections,
        "blocks": blocks,
        "tables": tables,
        "figures": figures,
        "figures_dropped": figures_dropped,
        "formulas": formulas,
        "references": references,
        "page_stats": [{"page": p["number"], "chars": p["chars"], "lines": len(p["lines"]),
                        "w": p.get("width"), "h": p.get("height"),
                        "columns": p.get("columns", 1), "bands": p.get("bands", 1),
                        "gutters": p.get("gutters", []), "filled_by": p.get("filled_by")}
                       for p in pages],
        "running_heads_removed": heads["count"],
        "verbatim_text": verbatim,
        "verbatim_chars": len(verbatim),
        "quality": _quality(pages, blocks, tables, formulas, references, empty_pages,
                            figures, figures_dropped, table_region_blocks),
    }
    return doc


def _quality(pages, blocks, tables, formulas, references, empty_pages,
             figures=(), figures_dropped=(), table_region_blocks=0) -> Dict[str, Any]:
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
    return {
        "pages": len(pages),
        "chars": total_chars,
        "chars_per_page": round(total_chars / max(1, len(pages)), 1),
        "blocks": len(blocks),
        "tables": len(tables),
        "figures": len(figures),
        "figures_dropped": len(figures_dropped),
        "blocks_in_table_regions": table_region_blocks,
        "formulas": len(formulas),
        "references": len(references),
        "empty_pages": empty_pages,
        "issues": issues,
    }


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
    for role, paths in man["by_role"].items():
        if role in {"pdf", "image"}:
            continue
        for p in paths[:12]:
            try:
                txt = sources.read_text(p)
            except Exception as exc:
                txt = f"<unreadable: {exc}>"
            doc["materials"][os.path.basename(p)] = {"role": role, "chars": len(txt),
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
    return "\n".join(out)


def dump(doc: Dict[str, Any], out_path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
