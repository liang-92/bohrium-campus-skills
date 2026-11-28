"""Content gates: a file being present is not the task being done.

These checks run after the deliverables are written and before `result.json`
is built.  They are deliberately about the task's own acceptance criteria
(numbers preserved, citations actually inserted, each note compressed to 80
characters, a translation actually present), not about the shape of the JSON.
A failure downgrades `complete` to `partial`; it never fabricates a success.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
from typing import Any, Dict, List

NOT_REPORTED = "not_reported"


def _csv_rows(text: str) -> List[Dict[str, str]]:
    try:
        return list(csv.DictReader(io.StringIO(text or "")))
    except Exception:
        return []


def _req(required: List[str], name: str) -> bool:
    return any(os.path.basename(str(r)).lower() == name.lower() for r in (required or []))


def _task(doc: Dict[str, Any]) -> str:
    return str((doc or {}).get("task") or "")


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

    critical_csv = {
        "term_table.csv", "term_decisions.csv", "table_header.csv",
        "knowledge_points.csv", "strength_map.csv", "qc_report.csv",
        "change_log.csv", "setup_table.csv", "params.csv", "split_table.csv",
        "citation_placement.csv", "id_map.csv", "coverage.csv", "gap_map.csv",
        "materials_equipment.csv", "field_report.csv",
    }
    for rel in required or []:
        base = os.path.basename(str(rel)).lower()
        if base in critical_csv:
            rows = _csv_rows(_file(out_dir, rel))
            if not rows:
                out.append(f"{rel}: header only / no data rows")

    if profile == "parse":
        if not d.get("blocks"):
            out.append("no text blocks recovered")
        elif len(d["blocks"]) < 3 and not (d.get("tables") or d.get("references")):
            out.append(f"only {len(d['blocks'])} block(s) recovered")
        if d.get("source", {}).get("error"):
            out.append("source could not be read")
        if _req(required, "page_map.csv"):
            rows = _csv_rows(_file(out_dir, "page_map.csv"))
            want_printed = re.search(r"印刷页|printed[ _]page|页眉|页脚|3、4、2", _task(doc), re.I)
            if rows and want_printed and any(not r.get("printed_page") for r in rows):
                out.append("page_map.csv has empty printed_page values")
        for rel in required or []:
            base = os.path.basename(str(rel)).lower()
            if re.match(r"table_\d+\.md", base):
                txt = _file(out_dir, rel)
                if re.search(r"No table|未提取|not extracted", txt, re.I):
                    out.append(f"{rel}: table is declared missing")
        table_files = [f for f in (files or [])
                       if re.match(r"tables?/table_\d+\.md$", str(f.get("path") or ""), re.I)]
        tables = (p.get("content") or {}).get("tables") or d.get("tables") or []
        if table_files and len(table_files) != len(tables):
            out.append(f"main_result.tables has {len(tables)} item(s) but "
                       f"{len(table_files)} table file(s) were written")
        for i, t in enumerate(tables, 1):
            rel = f"tables/table_{i}.md"
            txt = _file(out_dir, rel)
            if not txt:
                continue
            header = next((line for line in txt.splitlines()
                           if line.strip().startswith("|")), "")
            cells = [c.strip() for c in header.strip().strip("|").split("|")]
            want = [str(c or "").strip() for c in (t.get("header") or [])]
            if want and cells and cells[:len(want)] != want[:len(cells)]:
                out.append(f"{rel}: table header does not match main_result.tables[{i - 1}]")
        sections = (p.get("structure") or [])
        if sections:
            if any(re.match(r"^(table|figure)\s*\d+", str(s.get("title") or ""), re.I)
                   for s in sections):
                out.append("structure contains table/figure captions as sections")
            nums = [int(re.match(r"(\d+)", str(s.get("title") or "")).group(1))
                    for s in sections if re.match(r"\d+\s+", str(s.get("title") or ""))]
            if nums and nums != sorted(nums):
                out.append("structure section numbering is out of order")
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
        task = _task(doc)
        if "bilingual_captions.md" in [os.path.basename(str(x)).lower() for x in required or []]:
            want = len(re.findall(r"C\d{2}", task))
            labels = {str(s.get("seg")) for s in segs if str(s.get("seg", "")).startswith("C")}
            if want >= 3 and len(labels) < want:
                out.append(f"bilingual_captions.md covers {len(labels)}/{want} labeled captions")
            cap_text = _file(out_dir, "bilingual_captions.md")
            if "材料中没有带题注的图表" in cap_text:
                out.append("bilingual_captions.md claims there are no captions although captions.md exists")
        if _req(required, "table_header.csv"):
            rows = _csv_rows(_file(out_dir, "table_header.csv"))
            if len(rows) < 6 and "6" in task:
                out.append(f"table_header.csv has {len(rows)} of 6 header fields")
        if _req(required, "term_table.csv"):
            rows = _csv_rows(_file(out_dir, "term_table.csv"))
            m = re.search(r"(?:至少|不少于|≥|>=)\s*(\d+)\s*(?:条|个)?\s*(?:术语|term)", task, re.I)
            need = int(m.group(1)) if m else 1
            if len(rows) < need:
                out.append(f"term_table.csv has {len(rows)}/{need} terms")
        if _req(required, "term_decisions.csv"):
            if not _csv_rows(_file(out_dir, "term_decisions.csv")):
                out.append("term_decisions.csv has no data rows")
        if _req(required, "hedge_map.csv"):
            rows = _csv_rows(_file(out_dir, "hedge_map.csv"))
            want = 8 if re.search(r"P0[1-8]|8\s*条|八个", _task(doc), re.I) else 0
            if want and len(rows) < want:
                out.append(f"hedge_map.csv has {len(rows)}/{want} cue rows")
            for r in rows:
                if not (r.get("paragraph") and r.get("original_hedge")
                        and r.get("translation") and r.get("strength")):
                    out.append("hedge_map.csv has a row with a missing field")
        if _req(required, "abbreviations.md"):
            text = _file(out_dir, "abbreviations.md")
            if re.search(r"未发现|没有显式|no explicit", text, re.I):
                out.append("abbreviations.md says no abbreviation was found")
        return out

    if profile == "notes":
        notes = p.get("section_notes") or []
        if not notes:
            out.append("no section notes produced")
        if not p.get("evidence_chains"):
            for n in notes:
                for key in ("purpose", "evidence", "result", "conclusion"):
                    if not isinstance(n.get(key), dict):
                        out.append(f"{n.get('section')}: missing {key}")
                sm = (n.get("summary") or {}).get("text") or ""
                if not sm or sm == NOT_REPORTED:
                    out.append(f"{n.get('section')}: missing compressed summary")
                elif len(sm) > 80:
                    out.append(f"{n.get('section')}: summary is {len(sm)} chars (>80)")
        else:
            for r in p.get("evidence_chains") or []:
                if not str(r.get("quote") or "").strip():
                    out.append(f"{r.get('claim')}/{r.get('study')}: evidence chain has no quote")
                if str(r.get("anchor") or "").strip() in {"", "document", "sources.md"}:
                    out.append(f"{r.get('claim')}/{r.get('study')}: evidence anchor is too coarse")
            if not p.get("knowledge_items"):
                out.append("evidence-chain case has empty knowledge_items")
            u = p.get("uncertainty") or {}
            if not (u.get("notes") and u.get("missing") and u.get("conflicts")):
                out.append("evidence-chain case has an empty uncertainty class")
        if not (p.get("paper_card") or {}).get("findings") and not p.get("evidence_chains"):
            out.append("paper card has no findings")
        task = _task(doc)
        if re.search(r"Paper\s+A.*Paper\s+B|两篇|multi", task, re.I | re.S):
            cards_text = _file(out_dir, "cards.jsonl")
            ncards = len([l for l in cards_text.splitlines() if l.strip()])
            if ncards < 2:
                out.append(f"cards.jsonl has {ncards} cards; two papers need two independent cards")
            comp = _file(out_dir, "comparison.md")
            if comp and not ("Paper A" in comp and "Paper B" in comp):
                out.append("comparison.md lacks separate Paper A / Paper B columns")
        if _req(required, "knowledge_points.csv"):
            rows = _csv_rows(_file(out_dir, "knowledge_points.csv"))
            if len(rows) < 15:
                out.append(f"knowledge_points.csv has {len(rows)}/15 knowledge points")
            items = p.get("knowledge_items") or []
            if rows and len(items) != len(rows):
                out.append(f"main_result.knowledge_items has {len(items)} items "
                           f"but knowledge_points.csv has {len(rows)} rows")
        card = p.get("paper_card") or {}
        # A multi-paper comparison has each card under paper_cards[], and a
        # review-evidence case has no paper card at all; the single-paper
        # field contract applies to the single-paper profile.
        if not p.get("evidence_chains") and not p.get("paper_cards"):
            for key in ("data", "methods", "contributions"):
                value = card.get(key) or []
                if not value:
                    out.append(f"paper_card.{key} is empty")
                elif isinstance(value, list) and all(
                        str((x or {}).get("text") or "").strip() in {"", NOT_REPORTED}
                        for x in value if isinstance(x, dict)):
                    out.append(f"paper_card.{key} contains only not_reported")
        if _req(required, "conflicts.md"):
            text = _file(out_dir, "conflicts.md")
            for token in ("R1", "R2", "S1", "S2", "S3"):
                if token not in text:
                    out.append(f"conflicts.md lacks {token} evidence chain")
        # Searchable-note contract: count, tags, links and confidence are
        # deliverables, not optional decoration on the section skeleton.
        searchable = p.get("notes") or []
        if searchable:
            need = 12 if re.search(r"(?:至少|不少于|≥|>=)?\s*12\s*条", task) else 0
            if need and len(searchable) < need:
                out.append(f"notes.jsonl has {len(searchable)}/{need} searchable notes")
            for n in searchable:
                if not (n.get("tags") or []):
                    out.append(f"{n.get('note_id')}: note has no tags")
                if not (n.get("links") or []):
                    out.append(f"{n.get('note_id')}: note has no links")
                if not n.get("confidence"):
                    out.append(f"{n.get('note_id')}: note has no confidence")
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
            # A deliberately missing independent source is documented with
            # `why_missing`; that is different from an empty evidence slot.
            if not ev.get("block") or (not ev.get("quote") and not ev.get("why_missing")):
                out.append(f"{a.get('id')}: missing evidence block/quote")
        if _req(required, "qc_report.csv"):
            rows = _csv_rows(_file(out_dir, "qc_report.csv"))
            ids = {str(r.get("id") or "") for r in rows}
            if len(rows) < 8 or not all(f"N{i}" in ids for i in range(1, 9)):
                out.append(f"qc_report.csv covers {len(rows)}/8 rows and ids {sorted(ids)}")
            for r in rows:
                if not (r.get("verdict") and r.get("rule") and r.get("reason")
                        and r.get("evidence") and r.get("revised_assertion")):
                    out.append(f"qc_report.csv row {r.get('id')} has a missing field")
        if _req(required, "provenance.md"):
            text = _file(out_dir, "provenance.md")
            for token in ("S1", "S2", "S3", "preprint", "published"):
                if token not in text:
                    out.append(f"provenance.md lacks {token}")
            if not p.get("provenance", {}).get("sources"):
                out.append("provenance has no structured sources[]")
        if _req(required, "evidence_audit.csv"):
            rows = _csv_rows(_file(out_dir, "evidence_audit.csv"))
            if not rows:
                out.append("evidence_audit.csv has no data rows")
            for r in rows:
                verdict = str(r.get("verdict") or "").strip().lower()
                direct = str(r.get("directness") or "").strip().lower()
                if not r.get("evidence_quote"):
                    out.append(f"{r.get('assertion_id')}: evidence_audit has no quote")
                if not r.get("anchor"):
                    out.append(f"{r.get('assertion_id')}: evidence_audit has no anchor")
                if verdict in {"unsupported", "indirect"} and direct == "direct":
                    out.append(f"{r.get('assertion_id')}: {verdict} is labeled direct")
                if verdict == "unsupported" and direct not in {"unsupported", "indirect"}:
                    out.append(f"{r.get('assertion_id')}: unsupported claim has directness={direct!r}")
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
        if _req(required, "graph_updated.json"):
            base = (d.get("base_graph") or {})
            try:
                base = base or json.loads(_file(out_dir, "base_graph.json"))
            except Exception:
                base = {}
            try:
                updated = json.loads(_file(out_dir, "graph_updated.json"))
            except Exception:
                updated = {}
            if base:
                if len(updated.get("nodes") or []) <= len(base.get("nodes") or []):
                    out.append("graph_updated.json has no new nodes")
                if len(updated.get("edges") or []) <= len(base.get("edges") or []):
                    out.append("graph_updated.json has no new edges")
                meta = updated.get("meta") or {}
                if len(meta.get("paper_ids") or []) <= len((base.get("meta") or {}).get("paper_ids") or []):
                    out.append("graph_updated.json meta.paper_ids was not extended with the new paper")
                for n in (updated.get("nodes") or [])[len(base.get("nodes") or []):]:
                    if re.fullmatch(r"[+\-−]?\d+(?:\.\d+)?\s*(?:%|h|min|s|K|°C|mA cm-2|Ω|eV)?",
                                    str(n.get("label") or "").strip(), re.I):
                        out.append(f"graph node {n.get('id')} is a bare value, not an entity")
                    for ev in n.get("evidence") or []:
                        if str(ev.get("anchor") or "").strip() in {"", "new-paper", "new_paper"}:
                            out.append(f"graph node {n.get('id')} has a placeholder anchor")
                for e in (updated.get("edges") or [])[len(base.get("edges") or []):]:
                    for ev in e.get("evidence") or []:
                        if str(ev.get("anchor") or "").strip() in {"", "new-paper", "new_paper"}:
                            out.append(f"graph edge {e.get('id')} has a placeholder anchor")
                conflicts = updated.get("conflicts") or []
                if re.search(r"冲突|conflict", _task(doc), re.I) and not conflicts:
                    out.append("graph_updated.json has no conflict record")
            log_rows = _csv_rows(_file(out_dir, "change_log.csv"))
            if len(log_rows) < 2:
                out.append("change_log.csv has no per-item node/edge evidence")
            return out
        if len(edges) < 3:
            out.append(f"only {len(edges)} relations")
        for e in edges:
            if not str(e.get("paper_id") or "").strip() or not str(e.get("anchor") or "").strip() \
                    or not str(e.get("quote") or "").strip():
                out.append(f"edge {e.get('id')}: missing paper_id/anchor/quote")
        for n in nodes:
            label = str(n.get("label") or n.get("surface") or "").strip()
            if str(n.get("type") or "").strip().lower() in {"value", "measurement", "number"}:
                continue
            if re.fullmatch(r"(?:[+\-−]?\d+(?:\.\d+)?\s*)?"
                            r"(?:cm-?\d|GPa|MPa|K|°C|S cm-?\d|Ω cm2|%|h|min|s)", label, re.I):
                out.append(f"node {n.get('id')}: unit/value fragment `{label}`")
            elif re.search(r"\bas grain size\b|\bconclude that\b|^from\b|^to\b", label, re.I):
                out.append(f"node {n.get('id')}: clause fragment `{label}`")
        return out

    if profile == "polish":
        rewritten = (p.get("revised_text") or "").strip()
        if not rewritten and not _file(out_dir, "revised.md").strip():
            out.append("revised text is empty")
        changes = p.get("rewrites") or []
        if len(changes) < 1:
            out.append("no rewrite records")
        task = _task(doc)
        body = _file(out_dir, "revised.md")
        if body:
            if re.search(r"With the rapid development of the society|societal development|"
                         r"make a contribution to the development", body, re.I):
                out.append("revised text retains social-boilerplate sentences")
            if re.search(r"A series of pellets was\b", body, re.I):
                out.append("revised text still has subject-verb disagreement: pellets ... was")
            if re.match(r"^\s*[,;:]", body):
                out.append("revised text begins with stray punctuation")
        if _req(required, "term_table.csv"):
            rows = _csv_rows(_file(out_dir, "term_table.csv"))
            if len(rows) < 1:
                out.append("term_table.csv has no data rows")
            if "术语统一" in task and len(rows[0]) and "count" in rows[0]:
                try:
                    total = sum(int(r.get("count") or 0) for r in rows)
                    if total < 7:
                        out.append("term_table.csv count is <7")
                except Exception:
                    pass
        if _req(required, "strength_map.csv"):
            rows = _csv_rows(_file(out_dir, "strength_map.csv"))
            if len(rows) < 4:
                out.append(f"strength_map.csv has {len(rows)}/4 cue rows")
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
            body = re.split(r"(?im)^\s*#{0,3}\s*(?:references|参考文献)\s*$", manuscript)[0]
            marks = [int(x) for g in re.findall(r"\[([0-9,]+)\]", body)
                     for x in g.split(",") if x.strip().isdigit()]
            n_marks = len(marks)
            if n_marks == 0 and not re.search(r"\([A-Z][A-Za-z-]+(?:\s+et al\.)?\s*,\s*(?:19|20)\d{2}\)", manuscript):
                out.append("no in-text citation markers inserted")
            elif marks and re.search(r"顺序编码|首次出现顺序", _task(doc), re.I):
                if marks[0] != 1:
                    out.append(f"first citation is [{marks[0]}], not [1]")
                for i, n in enumerate(marks, 1):
                    if n > i:
                        out.append(f"citation order jumps to [{n}] at position {i}")
                        break
            ref_lines = [l.strip() for l in manuscript.splitlines()
                         if re.match(r"^\s*\[\d+\]\s+", l)]
            seen = {}
            for line in ref_lines:
                key = re.sub(r"^\s*\[\d+\]\s*", "", line).lower()
                key = re.sub(r"\s+", " ", key)[:90]
                if key in seen:
                    out.append(f"reference list duplicates [{seen[key]}] and the same record again")
                    break
                seen[key] = re.match(r"\[\d+\]", line).group(0)
        if _req(required, "citation_placement.csv"):
            rows = _csv_rows(_file(out_dir, "citation_placement.csv"))
            if any(re.match(r"^\s*\[\d+\]", str(r.get("sentence") or "")) for r in rows):
                out.append("citation_placement.csv treats reference-list entries as sentences")
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
        task = _task(doc)
        if ("1150" in task or "1160" in task) and not re.search(r"1150|1160", body):
            out.append("methods.md does not preserve the 1150/1160 conflict")
        # A methods section that reports findings blurs the method/result
        # boundary the task is grading.  Allow a "results" pointer only when
        # the task itself asks for one.
        if re.search(r"\b(?:we|our results?|the results?|results)\b.{0,30}"
                     r"\b(?:observe|observed|find|found|show|showed|demonstrate|"
                     r"demonstrated)\b", body, re.I) and \
                not re.search(r"结果|results?", _task(doc), re.I):
            out.append("methods.md contains result sentences that belong to a results section")
        if _req(required, "params.csv"):
            rows = _csv_rows(_file(out_dir, "params.csv"))
            if len(rows) < 10:
                out.append(f"params.csv has {len(rows)}/10 parameter rows")
            for r in rows:
                for key in ("name", "value", "unit", "target", "source", "conflict"):
                    if key not in r:
                        out.append(f"params.csv missing column {key}")
                        break
            # Only the conflict-audit case (task names the 1150/1160 or a
            # config-vs-log conflict) requires a positive conflict flag.  A
            # clean methods case must not be downgraded just because its
            # authoritative config has no disputed value.
            if re.search(r"1150|1160|learning.?(?:rate|rate)|学习率|lr\s*冲突", task, re.I) and \
                    re.search(r"conflict|冲突", task, re.I) and \
                    not any(str(r.get("conflict", "")).lower() == "yes" for r in rows):
                out.append("params.csv does not mark the learning-rate conflict")
        if _req(required, "experiment_setup.md"):
            text = _file(out_dir, "experiment_setup.md")
            for token in ("9984", "1248", "1240", "20240301"):
                if token not in text:
                    out.append(f"experiment_setup.md missing {token}")
            if not re.search(r"A100|torch|CUDA|11\.8", text, re.I):
                out.append("experiment_setup.md missing hardware/software versions")
        if _req(required, "dataset.md") and re.search(r"12,?472|数量自洽|去除\s*12", task, re.I):
            text = _file(out_dir, "dataset.md")
            if "12,460" not in text and "12460" not in text:
                out.append("dataset.md does not show the post-removal total 12,460")
            if not re.search(r"count_note|差额|未分配|子集计数合计|12,460", text, re.I):
                out.append("dataset.md does not explain the 12,472/12,460 split arithmetic")
        if _req(required, "methods_params.md"):
            text = _file(out_dir, "methods_params.md")
            if "1.5e-3" not in text and "1.5×10" not in text:
                out.append("methods_params.md does not use the authoritative learning rate 1.5e-3")
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
        log = _file(out_dir, "project/compile.log")
        if re.search(r"Overfull|无\s*Overfull|overfull", _task(doc), re.I) and \
                re.search(r"Overfull\s+\\hbox", log, re.I):
            out.append("compile.log still has Overfull hbox warnings")
        abstract = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", main, re.S)
        if abstract and re.search(r"150|40\s*词|words", _task(doc), re.I):
            n = len(re.findall(r"\b\w+\b", abstract.group(1)))
            if not 150 <= n <= 250:
                out.append(f"abstract is {n} words, outside 150–250")
        return out

    return out
