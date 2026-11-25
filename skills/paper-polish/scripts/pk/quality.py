"""Content gates: a file being present is not the task being done.

These checks run after the deliverables are written and before `result.json`
is built.  They are deliberately about the task's own acceptance criteria
(numbers preserved, citations actually inserted, each note compressed to 80
characters, a translation actually present), not about the shape of the JSON.
A failure downgrades `complete` to `partial`; it never fabricates a success.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List

NOT_REPORTED = "not_reported"


def _d(doc: Dict[str, Any]) -> Dict[str, Any]:
    return (doc or {}).get("document") or {}


def _text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except Exception:
        return ""


def _file(out_dir: str, rel: str) -> str:
    return _text(os.path.join(out_dir, *rel.split("/")))


def issues(profile: str, doc: Dict[str, Any], payload: Dict[str, Any],
           out_dir: str, required: List[str], files: List[Dict[str, Any]]) -> List[str]:
    d = _d(doc)
    p = payload or {}
    out: List[str] = []

    # A file that was copied from the input (or created empty just to satisfy a
    # manifest) is not a deliverable.  `write_required` records both flags.
    for f in files or []:
        if f.get("empty") or f.get("bytes") == 0:
            out.append(f"{f.get('path')}: empty file")
        elif f.get("copy_of_input"):
            out.append(f"{f.get('path')}: byte-for-byte copy of input")

    if profile == "parse":
        if not d.get("blocks"):
            out.append("no text blocks recovered")
        elif len(d["blocks"]) < 3 and not (d.get("tables") or d.get("references")):
            out.append(f"only {len(d['blocks'])} block(s) recovered")
        if d.get("source", {}).get("error"):
            out.append("source could not be read")
        return out

    if profile == "translate":
        segs = p.get("segments") or []
        if not segs:
            out.append("no segments produced")
        for s in segs:
            t = (s.get("translation") or "").strip()
            if not t:
                out.append(f"{s.get('seg')}: translation is empty")
            elif len(t) < 3:
                out.append(f"{s.get('seg')}: translation is a placeholder")
        return out

    if profile == "notes":
        notes = p.get("section_notes") or []
        if not notes:
            out.append("no section notes produced")
        for n in notes:
            for key in ("purpose", "evidence", "result", "conclusion"):
                if not isinstance(n.get(key), dict):
                    out.append(f"{n.get('section')}: missing {key}")
            sm = (n.get("summary") or {}).get("text") or ""
            if not sm or sm == NOT_REPORTED:
                out.append(f"{n.get('section')}: missing compressed summary")
            elif len(sm) > 80:
                out.append(f"{n.get('section')}: summary is {len(sm)} chars (>80)")
        if not (p.get("paper_card") or {}).get("findings"):
            out.append("paper card has no findings")
        return out

    if profile == "nanopub":
        claims = p.get("assertions") or []
        task = (doc or {}).get("task") or ""
        m = re.search(r"(?:N|A)\s*(\d+)\s*[–—\-~至到]\s*(?:N|A)?\s*(\d+)", task, re.I)
        target = max(int(m.group(1)), int(m.group(2))) if m else 0
        if not target:
            target = int((p.get("nanopublication") or {}).get("target_count") or 0)
        if not target and re.search(r"N\s*1\s*[–-]\s*N\s*8|八条|8\s*条", task, re.I):
            target = 8
        need = target or 3
        if len(claims) < need:
            out.append(f"only {len(claims)} assertions (need >={need})")
        for a in claims:
            text = (a.get("assertion") or "").strip()
            if re.match(r"^\[\s*p\.?\s*\d", text, re.I):
                out.append(f"{a.get('id')}: assertion starts with a page locator")
            ev = a.get("evidence") or {}
            if not ev.get("block") or not ev.get("quote"):
                out.append(f"{a.get('id')}: missing evidence block/quote")
        return out

    if profile == "kg":
        clusters = p.get("clusters") or []
        if clusters:
            if len(clusters) < 3:
                out.append(f"only {len(clusters)} entity clusters")
            for c in clusters:
                if not c.get("members"):
                    out.append(f"{c.get('cluster_id')}: cluster has no member evidence")
            return out
        nodes = p.get("nodes") or p.get("entities") or []
        edges = p.get("edges") or p.get("relations") or []
        if len(nodes) < 5:
            out.append(f"only {len(nodes)} entities")
        if any("graph_updated" in str(r) for r in (required or [])) and nodes:
            return out
        if len(edges) < 3:
            out.append(f"only {len(edges)} relations")
        return out

    if profile == "polish":
        rewritten = (p.get("revised_text") or "").strip()
        if not rewritten and not _file(out_dir, "revised.md").strip():
            out.append("revised text is empty")
        changes = p.get("rewrites") or []
        if len(changes) < 1:
            out.append("no rewrite records")
        if rewritten:
            # A headline-only rewrite is caught by comparing the body to input.
            src = ""
            for name, meta in (doc.get("materials") or {}).items():
                if re.search(r"draft|manuscript|正文", str(name), re.I):
                    src = str(meta.get("text") or "")
                    break
            if src and re.sub(r"\s+", " ", rewritten).strip() == re.sub(r"\s+", " ", src).strip():
                out.append("revised text is identical to the input draft")
        return out

    if profile == "refs":
        req = [str(r).lower() for r in (required or [])]
        has_bib = any("refs.bib" in str(k).lower() for k in (d.get("materials") or {}))
        if "references_gbt.md" in req and has_bib:
            text = _file(out_dir, "references_gbt.md")
            n_typed = len(re.findall(r"\[[JC]\]", text))
            if n_typed < 3:
                out.append("references_gbt.md has fewer than 3 typed entries ([J]/[C])")
            if "{BERT}" in text or re.search(r"\[J\]\.\s*,", text):
                out.append("references_gbt.md has malformed GB/T entries")
        if "audit.csv" in req:
            text = _file(out_dir, "audit.csv")
            corpus = "\n".join(str(m.get("text") or "") for m in (doc.get("materials") or {}).values())
            if "li2023" in corpus and not re.search(r"li2023.*fabricated", text, re.I):
                out.append("audit.csv does not flag li2023 as fabricated")
            if "chen2022" in corpus and not re.search(r"chen2022.*fabricated", text, re.I):
                out.append("audit.csv does not flag chen2022 as fabricated")
            if "zhang2018" in corpus and not re.search(r"zhang2018.*mismatch", text, re.I):
                out.append("audit.csv does not flag zhang2018 volume mismatch")
        if "claim_support.csv" in req:
            text = _file(out_dir, "claim_support.csv")
            corpus = "\n".join(str(m.get("text") or "") for m in (doc.get("materials") or {}).values())
            for cid in ("C4", "C5"):
                if cid in corpus and not re.search(cid + r".*unsupported", text, re.I):
                    out.append(f"claim_support.csv does not mark {cid} unsupported")
        required_manuscript = any("manuscript" in str(r) for r in (required or []))
        if not required_manuscript:
            # A bibliography-maintenance case (dedup / style conversion) has no
            # manuscript deliverable; judge the .bib it actually asked for.
            bibs = [r for r in (required or []) if str(r).lower().endswith((".bib", ".bibtex"))]
            for rel in bibs:
                body = _file(out_dir, rel)
                if not body.strip():
                    out.append(f"{rel}: empty bibliography")
                elif body.count("@") < 2:
                    out.append(f"{rel}: fewer than two bibliography entries")
            return out
        manuscript = _file(out_dir, "manuscript_cited.md") or \
            _file(out_dir, "manuscript_renumbered.md")
        if not manuscript.strip():
            out.append("manuscript_cited.md / manuscript_renumbered.md is empty")
        else:
            n_marks = len(re.findall(r"\[\d+\]", manuscript))
            if n_marks == 0 and not re.search(r"\([A-Z][A-Za-z-]+(?:\s+et al\.)?\s*,\s*(?:19|20)\d{2}\)", manuscript):
                out.append("no in-text citation markers inserted")
        if not (p.get("entries") or []):
            out.append("no reference entries parsed")
        return out

    if profile == "intro":
        draft = p.get("draft") or {}
        paras = draft.get("paragraphs") if isinstance(draft, dict) else []
        if not paras and not _file(out_dir, "intro_cited.md").strip():
            out.append("no intro draft produced")
        if paras and not all((x.get("text") or "").strip() for x in paras):
            out.append("intro draft has empty paragraphs")
        return out

    if profile == "methods":
        draft = p.get("draft") or {}
        paras = draft.get("paragraphs") if isinstance(draft, dict) else []
        has_named = any(_file(out_dir, n).strip() for n in
                        ("methods.md", "comparison.md", "dataset.md"))
        if not paras and not has_named:
            out.append("no methods draft produced")
        body = _file(out_dir, "methods.md") or "\n".join(
            (x.get("text") or "") for x in paras if isinstance(x, dict))
        task = (doc or {}).get("task") or ""
        if ("1150" in task or "1160" in task) and not re.search(r"1150|1160", body):
            out.append("methods.md does not preserve the 1150/1160 conflict")
        return out

    if profile == "latex":
        main = _file(out_dir, "project/main.tex")
        if not main.strip():
            out.append("project/main.tex is empty")
        elif main.count("{") != main.count("}"):
            out.append("project/main.tex has unbalanced braces")
        comp = p.get("compile") or {}
        if not comp.get("attempted"):
            out.append("LaTeX compilation was not attempted (no TeX engine)")
        elif not comp.get("ok"):
            out.append("LaTeX compilation failed")
        return out

    return out
