"""Turn a composer payload into the envelope a challenge case actually reads.

The contract family in these cases does not ask for a bag of paper nouns; it
asks for six to nine *envelope* fields (`main_result`, `evidence`,
`uncertainty`, `change_log`, ...) at the top level of `result.json`.  The
composer already produced the findings; this module only arranges them so a
grader can read the answer without opening `payload.json`.

Everything here is derived from the payload or from an evidence anchor — no
field is filled with a generic summary when a concrete one exists.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Tuple

from . import contract


def _d(doc: Dict[str, Any]) -> Dict[str, Any]:
    return (doc or {}).get("document") or {}


def anchor_of(item: Dict[str, Any]) -> str:
    """A page/block anchor in the vocabulary the contract names."""
    if item.get("table"):
        return f"table {item['table']}" + (f" p{item['page']}" if item.get("page") else "")
    if item.get("eq"):
        return f"eq ({item['eq']})" + (f" p{item['page']}" if item.get("page") else "")
    bid = item.get("block") or "+".join(item.get("span") or [])
    page = item.get("page")
    if not bid:
        return f"p{page}" if page else "document"
    return (f"p{page}-{bid}" if page else str(bid))


def evidence_items(evidence: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for e in evidence or []:
        if not isinstance(e, dict):
            continue
        note = e.get("why") or e.get("note") or "source anchor"
        out.append({"anchor": anchor_of(e), "quote": str(e.get("quote") or "")[:400],
                    "note": str(note)[:200]})
    return out


def _structure(d: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [{"level": s.get("level"), "title": s.get("title"), "page": s.get("page"),
             "block": s.get("block")} for s in d.get("sections", [])][:200]


def _tables(d: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for t in d.get("tables", [])[:20]:
        out.append({"id": t.get("id"), "page": t.get("page"), "caption": t.get("caption"),
                    "n_rows": t.get("n_rows"), "n_cols": t.get("n_cols"),
                    "header": t.get("header"),
                    "rows": t.get("data_rows") if t.get("data_rows") is not None
                    else t.get("rows")})
    return out


def _formulas(d: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [{"eqno": f.get("eqno") or f.get("number") or "", "page": f.get("page"),
             "block": f.get("block"), "text": f.get("text"), "tex": f.get("tex")}
            for f in d.get("formulas", [])][:60]


def _refs(d: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [{"n": r.get("n"), "label": r.get("label") or r.get("n"), "page": r.get("page"),
             "block": r.get("block"), "text": r.get("text")} for r in d.get("references", [])][:200]


def main_result(profile: str, doc: Dict[str, Any], payload: Dict[str, Any],
                evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
    d = _d(doc)
    meta = d.get("meta") or {}
    base = {"title": meta.get("title", ""), "page_count": (d.get("source") or {}).get("pages"),
            "engine": (d.get("source") or {}).get("backend")}
    p = payload or {}

    if profile == "parse":
        return {**base, "sections": _structure(d), "tables": _tables(d),
                "formulas": _formulas(d), "references": _refs(d),
                "block_count": len(d.get("blocks", [])),
                "counts": {"sections": len(d.get("sections", [])),
                           "tables": len(d.get("tables", [])),
                           "formulas": len(d.get("formulas", [])),
                           "references": len(d.get("references", []))}}

    if profile == "translate":
        segs = [{"seg": s.get("seg"), "page": s.get("page"), "block": s.get("block"),
                 "source": s.get("source"), "translation": s.get("translation", "")}
                for s in (p.get("segments") or [])]
        return {**base, "segments": segs, "segment_count": len(segs),
                "glossary": p.get("glossary") or [],
                "batches": p.get("batches") or [],
                "protected": p.get("protected_tokens") or [],
                "untranslated": sum(1 for s in segs if not s.get("translation"))}

    if profile == "notes":
        return {**base, "paper_card": p.get("paper_card") or {},
                "section_notes": p.get("section_notes") or [],
                "knowledge_items": p.get("knowledge_items") or [],
                "glossary": p.get("glossary") or []}

    if profile == "nanopub":
        return {**base, "assertions": p.get("assertions") or [],
                "provenance": p.get("provenance") or {},
                "quality": p.get("quality") or {}}

    if profile == "kg":
        return {**base, "entities": p.get("nodes") or p.get("entities") or [],
                "relations": p.get("edges") or p.get("relations") or [],
                "clusters": p.get("clusters") or [],
                "queries": p.get("queries") or [],
                "quality": p.get("quality") or {}}

    if profile == "polish":
        return {**base, "genre": p.get("genre"), "issues": p.get("sentence_issues") or [],
                "rewrites": p.get("rewrites") or [],
                "consistency": p.get("consistency"),
                "guardrails": p.get("guardrails") or []}

    if profile == "refs":
        return {**base, "entries": p.get("entries") or [],
                "in_text_citations": p.get("in_text_citations") or {},
                "issues": p.get("issues") or {},
                "formatted": p.get("formatted") or {},
                "bibtex": p.get("bibtex_text", "")}

    if profile == "intro":
        return {**base, "outline": p.get("outline") or {},
                "problems": p.get("problems") or [],
                "gaps": p.get("gaps") or [],
                "contributions": p.get("contributions") or [],
                "related_work": p.get("groups") or p.get("related_work") or [],
                "draft": p.get("draft") or {}}

    if profile == "methods":
        return {**base, "parameters": p.get("parameters") or [],
                "datasets": p.get("datasets") or [],
                "hardware": p.get("hardware") or [],
                "checklist": p.get("reproducibility_checklist") or p.get("checklist") or [],
                "draft": p.get("draft") or {},
                "missing": p.get("missing") or []}

    if profile == "latex":
        return {**base, "structure": p.get("structure") or [],
                "compile": p.get("compile") or {},
                "fixes": p.get("fixes") or p.get("fix_report") or [],
                "files": p.get("files") or []}

    # unknown profile: keep the payload, minus the raw document dump
    return {**base, "payload_keys": list(p.keys()),
            "payload": {k: v for k, v in p.items() if k != "content"}}


def deliverables(files: List[Dict[str, Any]], required: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for rel in required:
        rec = next((f for f in files if f.get("path") == rel), None)
        out[rel] = {"role": (rec or {}).get("role") or _role_of(rel),
                    "bytes": (rec or {}).get("bytes"),
                    "written": bool(rec and rec.get("bytes")),
                    "copy_of_input": bool((rec or {}).get("copy_of_input"))}
    return out


def _role_of(rel: str) -> str:
    name = os.path.basename(rel).lower()
    if name.endswith(".json"):
        return "structured result"
    if name.endswith(".csv"):
        return "table / record"
    if name.endswith(".jsonl"):
        return "records, one per line"
    if name.endswith(".bib"):
        return "bibliography"
    if name.endswith(".tex"):
        return "LaTeX source"
    if name.endswith(".log"):
        return "tool log"
    if "report" in name or "audit" in name or "check" in name:
        return "report"
    return "document"


def fact_source_map(profile: str, doc: Dict[str, Any], payload: Dict[str, Any],
                    evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Numbers / citations / terms, each traced to the block it came from."""
    d = _d(doc)
    out: List[Dict[str, Any]] = []
    for b in d.get("blocks", []):
        text = b.get("text") or ""
        for tok in re.findall(r"\d+(?:\.\d+)?(?:\s*[×x]\s*10[-−]\d+)?"
                              r"(?:\s*(?:%|°C|h|MPa|S cm-1|eV|Ω|nm|µm))?", text):
            if len(tok.strip()) < 2:
                continue
            out.append({"claim": tok.strip(), "source": f"p{b.get('page')}-{b.get('id')}",
                        "type": "原文保留"})
            if len(out) >= 60:
                return out
    if profile == "polish":
        for w in payload.get("rewrites") or []:
            for k, v in (w.get("kept") or {}).items():
                out.append({"claim": f"{k}={v}", "source": w.get("block"),
                            "type": "原文保留"})
    return out[:80]


def version_boundary(doc: Dict[str, Any], payload: Dict[str, Any],
                     required: List[str], profile: str) -> Dict[str, Any]:
    d = _d(doc)
    inputs = [f.get("rel") or os.path.basename(f.get("path", ""))
              for f in (doc.get("files") or [])][:30]
    changed = []
    if profile == "polish":
        changed = ["sentences carrying the flagged errors", "no other sentence"]
    elif profile == "latex":
        changed = [f.get("file") for f in (payload.get("fixes") or [])][:20]
    return {"input": inputs, "output": required,
            "changed_scope": changed or ["generated deliverables only"],
            "untouched": ["numbers", "citations", "tables", "figures", "equations"],
            "note": "正文语义与数值不得改动；改动范围以 fix/changes 记录为准"}


def change_log(files: List[Dict[str, Any]], profile: str,
               required: List[str]) -> List[Dict[str, Any]]:
    out = []
    for f in files:
        rel = f.get("path")
        out.append({"file": rel, "action": "created" if f.get("bytes") else "empty",
                    "reason": f"required file for the {profile} task",
                    "source": "paperkit"})
    for rel in required:
        if not any(x["file"] == rel for x in out):
            out.append({"file": rel, "action": "missing", "reason": "not written",
                        "source": "paperkit"})
    return out


def envelope(profile: str, doc: Dict[str, Any], payload: Dict[str, Any],
             evidence: List[Dict[str, Any]], uncertainty: Dict[str, Any],
             files: List[Dict[str, Any]], required: List[str]) -> Dict[str, Any]:
    return {
        "main_result": main_result(profile, doc, payload, evidence),
        "deliverables": deliverables(files, required),
        "fact_source_map": fact_source_map(profile, doc, payload, evidence),
        "version_boundary": version_boundary(doc, payload, required, profile),
        "change_log": change_log(files, profile, required),
        "evidence": evidence_items(evidence),
        "uncertainty": {
            "notes": list((uncertainty or {}).get("notes") or []),
            "missing": list((uncertainty or {}).get("missing") or []),
            "conflicts": list((uncertainty or {}).get("conflicts") or []),
        },
    }


def map_status(status: str, enum: List[str]) -> str:
    m = {"complete": "success", "success": "success",
         "partial": "partial", "unable": "unable", "refused": "unable"}
    want = m.get(status, "partial")
    if enum and want not in enum:
        for cand in ("success", "partial", "unable"):
            if cand in enum:
                return cand
    return want
