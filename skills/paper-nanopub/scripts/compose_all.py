"""Ten composers, one deterministic engine.

Each weekly-skill ships a two-line `compose_<slug>.py` that calls
`compose_all.build(mode=...)`.  Everything here is rule-based on purpose: the
agent's model budget should go to judgement (translation, prose, phrasing), not
to re-deriving reading order or citation numbering.

Every payload field that states a fact carries a block id, so the judge can walk
back to the page.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import statistics
import subprocess
from typing import Any, Dict, Iterable, List, Tuple

# --------------------------------------------------------------------------- #
# small text utilities (stdlib only)
# --------------------------------------------------------------------------- #
SENT_SPLIT = re.compile(r"(?<=[.!?。！？])\s+(?=[A-Z(\[\u4e00-\u9fff])")
ABBREV = re.compile(r"\b(?:e\.g|i\.e|et al|vs|Fig|Eq|Sec|No|Dr|Prof|approx)\.$", re.I)
CITE_PAREN = re.compile(r"\([^()]{0,80}?\b(19|20)\d{2}[a-z]?[^()]{0,40}\)")
CITE_BRACKET = re.compile(r"\[(\d{1,3}(?:\s*[,–-]\s*\d{1,3})*)\]")
UNIT = r"(?:%|‰|ms|s|min|h|hr|days?|GB|MB|KB|TB|GHz|MHz|FPS|BLEU|ROUGE|pp|pt|x|×)"
NUM_UNIT = re.compile(r"(\d+(?:[.,]\d+)?)\s*(" + UNIT + r")\b")
NUM = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*(?:[eE][-+]?\d+)?")
ABBR_DEF = re.compile(r"\b([A-Z][A-Za-z-]{2,})\s*\(([A-Z]{2,8})\)")
STOP = set("""a an the of and or in on at to for from with by as is are was were be been being
this that these those it its we our their they them he she his her not no also such can may
may might will would could should do does did have has had than then there here which who whom
whose what when where why how all any both each few more most other some such only own same
so too very just about into over after before under above between during through because while
using used use based on et al fig figure table section eq equation respectively however thus
therefore moreover furthermore although though since due via per among within without across
""".split())


def sentences(text: str, max_len: int = 400) -> List[str]:
    out: List[str] = []
    for part in SENT_SPLIT.split(text.strip()):
        part = part.strip()
        if not part:
            continue
        if len(part) > max_len:
            out.extend(p.strip() for p in re.split(r";\s+", part) if p.strip())
        else:
            out.append(part)
        if len(out) >= 2 and ABBREV.search(out[-1]):
            merged = out[-2] + " " + out[-1]
            out[-2:] = [merged]
    return out


def words(text: str) -> List[str]:
    return re.findall(r"[A-Za-z][A-Za-z'-]{1,}", text)


def keyphrases(doc: Dict[str, Any], top: int = 40) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {}
    first: Dict[str, str] = {}
    for b in doc.get("blocks", []):
        if b.get("type") not in {"body", "heading", "caption"}:
            continue
        text = b["text"]
        for m in re.finditer(r"\b([A-Za-z][A-Za-z-]{2,}(?:\s+[A-Za-z][A-Za-z-]{2,}){0,2})\b", text):
            phrase = m.group(1)
            toks = [t.lower() for t in phrase.split()]
            if toks[0] in STOP or toks[-1] in STOP:
                continue
            if len(toks) == 1 and len(toks[0]) < 6:
                continue
            key = phrase.lower()
            counts[key] = counts.get(key, 0) + 1
            first.setdefault(key, phrase)
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:top]
    return [{"term": first[k], "count": c} for k, c in ranked if c >= 2]


def protected_tokens(text: str) -> Dict[str, List[str]]:
    return {
        "numbers": sorted(set(NUM.findall(text)))[:60],
        "numbers_with_units": sorted(set(f"{a} {b}" for a, b in NUM_UNIT.findall(text)))[:40],
        "citations": sorted(set(CITE_BRACKET.findall(text) + CITE_PAREN.findall(text)))[:40],
        "latex_or_symbols": sorted(set(re.findall(r"[A-Za-z]\s*[=<>≈≤≥]\s*[A-Za-z0-9]+", text)))[:20],
    }


def sec_of(block: Dict[str, Any]) -> str:
    return (block.get("section") or "").split(" > ")[-1]


def blocks_in(doc: Dict[str, Any], pattern: str, limit: int = 200) -> List[Dict[str, Any]]:
    """Section-filtered blocks; accepts either the case wrapper or the document."""
    d = doc.get("document") if isinstance(doc.get("document"), dict) else doc
    rx = re.compile(pattern, re.I)
    return [b for b in d.get("blocks", []) if rx.search(sec_of(b))][:limit]


def ev(b: Dict[str, Any], why: str = "", max_chars: int = 220) -> Dict[str, Any]:
    text = re.sub(r"\s+", " ", b.get("text", "")).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "…"
    return {"block": b["id"], "page": b["page"], "section": sec_of(b),
            "quote": text, "why": why}


def add_evidence(store: List[Dict[str, Any]], item: Dict[str, Any], cap: int = 80) -> None:
    if len(store) >= cap:
        return
    key = (item.get("block"), item.get("why"))
    if any((e.get("block"), e.get("why")) == key for e in store):
        return
    store.append(item)


def _first_block(doc: Dict[str, Any], pattern: str) -> Dict[str, Any] | None:
    rx = re.compile(pattern, re.I)
    for b in doc.get("blocks", []):
        if rx.search(b.get("text", "")):
            return b
    return None


# --------------------------------------------------------------------------- #
# 1. parse
# --------------------------------------------------------------------------- #
def build_parse(doc: Dict[str, Any], case: Dict[str, Any], task: str):
    d = doc["document"]
    evidence: List[Dict[str, Any]] = []
    blocks = [{"id": b["id"], "page": b["page"], "column": b.get("column"),
               "section": sec_of(b), "type": b["type"], "text": b["text"]}
              for b in d["blocks"]]
    for b in d["blocks"][:12]:
        add_evidence(evidence, ev(b, "structure sample"))
    for t in d["tables"][:6]:
        add_evidence(evidence, {"table": t["id"], "page": t["page"], "quote": t["caption"][:200],
                                "why": "table with caption", "block": t.get("caption_block")})
    payload = {
        "document": {
            "title": d["meta"].get("title", ""), "authors": d["meta"].get("authors", []),
            "abstract": d["meta"].get("abstract", ""), "keywords": d["meta"].get("keywords", []),
            "doi": d["meta"].get("doi", ""), "pages": d["source"]["pages"],
            "engine": d["source"]["backend"], "sha256": d["source"]["sha256"],
        },
        "structure": [{"level": s["level"], "title": s["title"], "page": s["page"], "block": s["block"]}
                      for s in d["sections"]],
        "content": {"blocks": blocks, "tables": d["tables"], "figures": d["figures"],
                    "formulas": d["formulas"], "references": d["references"]},
        "coverage": d["quality"],
        "page_map": d["page_stats"],
    }
    status = "complete" if d["blocks"] and d["quality"]["chars_per_page"] > 200 else "partial"
    notes = [f"reading order reconstructed with XY-cut; {d['quality']['tables']} tables, "
             f"{d['quality']['formulas']} formulas, {d['quality']['references']} references"]
    if d["source"]["ocr_pages"]:
        notes.append(f"OCR used on pages {d['source']['ocr_pages']}")
    return payload, evidence, {"notes": d["quality"]["issues"], "missing": []}, status, notes


# --------------------------------------------------------------------------- #
# 2. translate
# --------------------------------------------------------------------------- #
SEED_GLOSSARY = {
    "abstract": "摘要", "introduction": "引言", "related work": "相关工作", "method": "方法",
    "experiment": "实验", "results": "结果", "discussion": "讨论", "conclusion": "结论",
    "dataset": "数据集", "baseline": "基线", "ablation": "消融实验", "benchmark": "基准",
    "attention": "注意力", "transformer": "Transformer", "embedding": "嵌入",
    "encoder": "编码器", "decoder": "解码器", "fine-tuning": "微调", "pre-training": "预训练",
    "loss function": "损失函数", "gradient": "梯度", "hyperparameter": "超参数",
    "generalization": "泛化", "robustness": "鲁棒性", "evaluation metric": "评价指标",
    "state-of-the-art": "当前最优", "limitation": "局限性", "future work": "未来工作",
    "corpus": "语料库", "annotation": "标注", "supervised": "有监督", "unsupervised": "无监督",
    "inference": "推理", "throughput": "吞吐量", "latency": "延迟", "architecture": "架构",
}


def build_translate(doc: Dict[str, Any], case: Dict[str, Any], task: str):
    d = doc["document"]
    evidence: List[Dict[str, Any]] = []
    segments: List[Dict[str, Any]] = []
    seg_id = 0
    for b in d["blocks"]:
        if b["type"] not in {"body", "heading", "caption"}:
            continue
        text = b["text"].strip()
        if len(text) < 2:
            continue
        chunks, cur = [], ""
        for s in sentences(text) or [text]:
            if len(cur) + len(s) > 850 and cur:
                chunks.append(cur.strip())
                cur = s
            else:
                cur = (cur + " " + s).strip()
        if cur:
            chunks.append(cur)
        for ch in chunks:
            seg_id += 1
            segments.append({"seg": f"s{seg_id:04d}", "block": b["id"], "page": b["page"],
                             "section": sec_of(b), "type": b["type"], "source": ch,
                             "protected": protected_tokens(ch), "translation": ""})
        add_evidence(evidence, ev(b, "segment source"))

    terms = keyphrases(d, top=60)
    for t in terms:
        t["zh"] = SEED_GLOSSARY.get(t["term"].lower(), "")
        if not t["zh"]:
            for k, v in SEED_GLOSSARY.items():
                if k in t["term"].lower():
                    t["zh"] = v
                    break
    payload = {
        "document": {"title": d["meta"].get("title", ""), "pages": d["source"]["pages"]},
        "segments": segments,
        "glossary": terms,
        "rules": {
            "unit_of_translation": "segment",
            "term_policy": "one rendering per glossary term across all segments",
            "keep_verbatim": ["numbers", "units", "citation markers", "figure/table numbers",
                              "formulas", "model/dataset proper names", "URLs", "DOIs"],
            "register": "academic Chinese, no added claims, no dropped hedges",
        },
    }
    status = "partial"
    notes = [f"{len(segments)} segments prepared; translations left empty for the agent "
             f"to fill, then run scripts/verify.py"]
    return payload, evidence, {"notes": ["translation field is intentionally empty until the agent fills it"],
                               "missing": []}, status, notes


# --------------------------------------------------------------------------- #
# 3. notes
# --------------------------------------------------------------------------- #
def build_notes(doc: Dict[str, Any], case: Dict[str, Any], task: str):
    d = doc["document"]
    evidence: List[Dict[str, Any]] = []
    card = {
        "title": d["meta"].get("title", ""), "authors": d["meta"].get("authors", []),
        "doi": d["meta"].get("doi", ""), "pages": d["source"]["pages"],
        "research_question": "", "data": [], "methods": [], "findings": [],
        "limitations": [], "contributions": [],
    }
    bullets = {"question": [], "finding": [], "limitation": [], "contribution": [], "method": [], "data": []}
    for b in d["blocks"]:
        for s in sentences(b["text"]):
            low = s.lower()
            if len(s) < 25:
                continue
            if re.search(r"\b(we|this paper|this work|here)\b.{0,40}\b(study|investigate|ask|address|examine|explore|propose)", low):
                bullets["question"].append((s, b))
            if re.search(r"\b(we|results?|experiments?)\b.{0,30}\b(find|show|demonstrate|observe|reveal|achieve|outperform)", low):
                bullets["finding"].append((s, b))
            if re.search(r"\b(limitation|limited to|caveat|future work|do not|does not|cannot)\b", low):
                bullets["limitation"].append((s, b))
            if re.search(r"\b(we|this paper)\b.{0,30}\b(contribute|propose|introduce|present|release)\b", low):
                bullets["contribution"].append((s, b))
            if re.search(r"\b(we|models?)\b.{0,30}\b(use|train|apply|fine-tune|adopt)\b", low):
                bullets["method"].append((s, b))
            if re.search(r"\b(dataset|corpus|benchmark|participants|samples?)\b", low) and re.search(r"\d", s):
                bullets["data"].append((s, b))

    def pack(items, key, cap=8):
        out = []
        for s, b in items[:cap]:
            out.append({"text": s, "block": b["id"], "page": b["page"], "section": sec_of(b)})
            add_evidence(evidence, ev(b, key))
        return out

    card["research_question"] = pack(bullets["question"], "question", 3)
    card["findings"] = pack(bullets["finding"], "finding", 8)
    card["limitations"] = pack(bullets["limitation"], "limitation", 6)
    card["contributions"] = pack(bullets["contribution"], "contribution", 6)
    card["methods"] = pack(bullets["method"], "method", 6)
    card["data"] = pack(bullets["data"], "data", 6)

    section_notes = []
    for s in d["sections"]:
        body = [b for b in d["blocks"] if b.get("section", "").endswith(s["title"]) and b["type"] != "heading"]
        if not body:
            continue
        head = body[0]
        section_notes.append({
            "section": s["title"], "level": s["level"], "page": s["page"], "block": s["block"],
            "gist": (sentences(head["text"]) or [head["text"]])[0][:400],
            "blocks": [b["id"] for b in body[:8]],
        })
        add_evidence(evidence, ev(head, f"section note: {s['title']}"))

    items = []
    for b in d["blocks"]:
        m = re.search(r"\b([A-Z][A-Za-z-]{2,}(?:\s+[A-Za-z-]{2,}){0,3})\s+(?:is|are|refers to|denotes|means)\s+([^.]{15,200})\.", b["text"])
        if m:
            items.append({"kind": "definition", "term": m.group(1), "detail": m.group(2).strip(),
                          "block": b["id"], "page": b["page"]})
    payload = {"paper_card": card, "section_notes": section_notes, "knowledge_items": items[:40],
               "glossary": keyphrases(d, 30)}
    status = "complete" if card["findings"] and section_notes else "partial"
    return payload, evidence, {"notes": [], "missing": []}, status, \
        [f"card built from {len(d['blocks'])} blocks; {len(section_notes)} section notes"]


# --------------------------------------------------------------------------- #
# 4. nanopublication
# --------------------------------------------------------------------------- #
CLAIM_CUES = {
    "empirical": r"\b(we|results?|experiments?|evaluation)\b.{0,40}\b(show|find|demonstrate|observe|achieve|outperform|improve|reduce|increase)\b",
    "method": r"\b(we|this work|this paper)\b.{0,40}\b(propose|introduce|present|describe|develop)\b",
    "causal": r"\b(because|due to|leads? to|causes?|results? in|attributable to)\b",
    "comparative": r"\b(outperform|better than|worse than|compared (?:to|with)|superior|inferior)\b",
    "background": r"\b(has been|have been|is known|are known|previous(?:ly)?)\b",
}


def build_nanopub(doc: Dict[str, Any], case: Dict[str, Any], task: str):
    d = doc["document"]
    evidence: List[Dict[str, Any]] = []
    claims: List[Dict[str, Any]] = []
    n = 0
    focus = blocks_in(doc, r"(abstract|introduction|results?|discussion|conclusion)") or d["blocks"]
    for b in focus:
        for s in sentences(b["text"]):
            if len(s) < 40 or len(s) > 420:
                continue
            kind = None
            for k, rx in CLAIM_CUES.items():
                if re.search(rx, s, re.I):
                    kind = k
                    break
            if not kind:
                continue
            n += 1
            claims.append({
                "id": f"a{n:03d}", "assertion": s, "type": kind,
                "conditions": re.findall(r"\b(?:when|if|for|under|with|on)\s+[^,.;]{3,60}", s)[:3],
                "evidence": {"block": b["id"], "page": b["page"], "section": sec_of(b),
                             "quote": s[:240], "kind": "direct" if kind != "background" else "context"},
                "confidence": "high" if kind in {"empirical", "comparative"} else "medium",
                "flags": ([f for f in ("overbroad",) if re.search(r"\b(all|every|always|never|none)\b", s, re.I)]
                          + (["hedged"] if re.search(r"\b(may|might|could|suggest|appears?)\b", s, re.I) else [])),
            })
            add_evidence(evidence, ev(b, f"claim a{n:03d}"))
            if len(claims) >= 60:
                break
        if len(claims) >= 60:
            break
    prov = {
        "paper": d["meta"].get("title", ""), "authors": d["meta"].get("authors", []),
        "doi": d["meta"].get("doi", ""), "source_sha256": d["source"]["sha256"],
        "pages": d["source"]["pages"], "engine": d["source"]["backend"],
    }
    payload = {
        "provenance": prov,
        "assertions": claims,
        "nanopublication": {
            "template": "assertion + provenance + publication info",
            "assertion_count": len(claims),
            "serialization": "json",
        },
        "quality": {
            "without_evidence": 0,
            "overbroad": sum(1 for c in claims if "overbroad" in c["flags"]),
            "hedged": sum(1 for c in claims if "hedged" in c["flags"]),
        },
    }
    status = "complete" if len(claims) >= 5 else "partial"
    return payload, evidence, {"notes": ["claims are extracted verbatim; interpretation left to the reader"],
                               "missing": []}, status, [f"{len(claims)} assertions bound to source blocks"]


# --------------------------------------------------------------------------- #
# 5. knowledge graph
# --------------------------------------------------------------------------- #
ENTITY_HINTS = {
    "method": r"\b(transformer|bert|gpt|cnn|rnn|lstm|svm|random forest|xgboost|attention|"
              r"encoder|decoder|embedding|fine-tuning|prompting|distillation|quantization)\b",
    "dataset": r"\b([A-Z][A-Za-z0-9-]*(?:\s+[A-Z][A-Za-z0-9-]*){0,3}\s+(?:dataset|corpus|benchmark))\b",
    "metric": r"\b(accuracy|precision|recall|f1|bleu|rouge|perplexity|auc|mse|mae|rmse|map)\b",
    "task": r"\b(classification|translation|summarization|question answering|segmentation|"
            r"detection|generation|retrieval|regression|clustering)\b",
}
REL_PATTERNS = [
    ("uses", r"([A-Z][\w-]{2,}(?:\s+[A-Z][\w-]{2,}){0,2})\s+(?:uses?|employs?|leverages?|is based on|relies on)\s+([A-Za-z][\w-]{2,}(?:\s+[A-Za-z][\w-]{2,}){0,2})"),
    ("evaluated_on", r"([A-Za-z][\w-]{2,})\s+(?:is|was|are|were)?\s*(?:evaluated|tested|benchmarked|trained|fine-tuned)\s+(?:on|with|using)\s+([A-Za-z0-9][\w-]{2,})"),
    ("outperforms", r"([A-Z][\w-]{2,}(?:\s+[A-Z][\w-]{2,}){0,2})\s+(?:outperforms?|surpasses?|beats?)\s+([A-Z][\w-]{2,}(?:\s+[A-Z][\w-]{2,}){0,2})"),
    ("improves", r"([A-Za-z][\w-]{2,})\s+(?:improves?|increases?|reduces?)\s+([A-Za-z][\w-]{2,})"),
]


def build_kg(doc: Dict[str, Any], case: Dict[str, Any], task: str):
    d = doc["document"]
    evidence: List[Dict[str, Any]] = []
    nodes: Dict[str, Dict[str, Any]] = {}
    keymap: Dict[str, str] = {}
    edges: List[Dict[str, Any]] = []

    def node(name: str, kind: str, b: Dict[str, Any]) -> str:
        key = re.sub(r"\s+", " ", name.strip())
        low = key.lower()
        if low in keymap:
            return keymap[low]
        nid = "n" + str(len(nodes) + 1).zfill(3)
        nodes[key] = {"id": nid, "label": key, "type": kind,
                      "evidence": [{"block": b["id"], "page": b["page"], "section": sec_of(b)}]}
        keymap[low] = nid
        return nid

    for b in d["blocks"]:
        if b["type"] == "heading":
            node(b["text"][:80], "concept", b)
        for kind, rx in ENTITY_HINTS.items():
            for m in re.finditer(rx, b["text"], re.I):
                node(m.group(0), kind, b)
        for rel, rx in REL_PATTERNS:
            for m in re.finditer(rx, b["text"]):
                a, c = m.group(1), m.group(2)
                if len(a) < 3 or len(c) < 3:
                    continue
                ia = node(a, "entity", b)
                ic = node(c, "entity", b)
                if ia == ic:
                    continue
                edges.append({"source": ia, "target": ic, "relation": rel,
                              "evidence": {"block": b["id"], "page": b["page"], "quote": m.group(0)[:200]}})
                add_evidence(evidence, ev(b, f"relation {rel}"))

    # alias normalisation: same label ignoring case/plural/hyphen
    def canon(s: str) -> str:
        s = s.lower().replace("-", " ").replace("_", " ")
        s = re.sub(r"\s+", " ", s).strip()
        return s[:-1] if s.endswith("s") and len(s) > 4 else s

    buckets: Dict[str, List[str]] = {}
    for label, n in nodes.items():
        buckets.setdefault(canon(label), []).append(n["id"])
    aliases = [{"canonical": k, "nodes": v} for k, v in buckets.items() if len(v) > 1]

    queries = []
    for rel in ("uses", "evaluated_on", "outperforms"):
        hits = [e for e in edges if e["relation"] == rel][:5]
        queries.append({"q": f"which pairs are linked by '{rel}'?", "answer": hits})

    payload = {
        "nodes": list(nodes.values()),
        "edges": edges[:400],
        "alias_groups": aliases,
        "queries": queries,
        "exports": {"json": "nodes/edges above", "cypher":
                    "\n".join(f"MERGE (:{n['type']} {{name:'{n['label']}'}})" for n in list(nodes.values())[:80])},
        "stats": {"nodes": len(nodes), "edges": len(edges)},
    }
    status = "complete" if len(nodes) >= 8 and edges else "partial"
    return payload, evidence, {"notes": ["relations only where an explicit pattern matched"],
                               "missing": []}, status, [f"{len(nodes)} nodes, {len(edges)} edges"]


# --------------------------------------------------------------------------- #
# 6. polish
# --------------------------------------------------------------------------- #
def build_polish(doc: Dict[str, Any], case: Dict[str, Any], task: str):
    d = doc["document"]
    evidence: List[Dict[str, Any]] = []
    issues: List[Dict[str, Any]] = []
    variants: Dict[str, Dict[str, int]] = {}
    for b in d["blocks"]:
        if b["type"] not in {"body", "heading"}:
            continue
        for s in sentences(b["text"]):
            flags = []
            if len(s.split()) > 38:
                flags.append("long-sentence")
            if re.search(r"\b(is|are|was|were|be|been)\s+\w+ed\b", s):
                flags.append("passive")
            if re.search(r"\b(very|really|quite|extremely|significantly|obviously|clearly)\b", s, re.I):
                flags.append("intensifier")
            if re.search(r"\b(all|every|always|never|none|prove[sd]?)\b", s, re.I):
                flags.append("absolute-claim")
            if re.search(r"\b(don't|doesn't|can't|won't|isn't|aren't)\b", s):
                flags.append("contraction")
            if flags:
                issues.append({"block": b["id"], "page": b["page"], "sentence": s[:300], "flags": flags})
                add_evidence(evidence, ev(b, "style issue"))
            for m in ABBR_DEF.finditer(s):
                variants.setdefault(m.group(2), {"def": 0, "redef": 0})["def"] += 1
        for term in ("dataset", "data set", "datasets", "data sets"):
            if re.search(rf"\b{term}\b", b["text"], re.I):
                variants.setdefault(term.lower(), {"def": 0, "redef": 0})["redef"] += 1

    consistency = []
    for k, v in variants.items():
        if v["redef"] > 0 and k in {"dataset", "data set"}:
            consistency.append({"issue": "spelling-variant", "term": k, "count": v["redef"]})

    payload = {
        "genre": detect_genre(task, d["meta"].get("title", "")),
        "sentence_issues": issues[:120],
        "consistency": consistency,
        "edit_record_schema": {
            "block": "source block id", "original": "verbatim source sentence",
            "revised": "edited sentence", "type": "grammar|terminology|register|clarity|hedging",
            "reason": "why this edit is minimal and meaning-preserving",
            "kept": "numbers/units/citations that must survive unchanged",
        },
        "guardrails": ["do not strengthen or weaken hedges", "keep every number, unit and citation",
                       "no new claims", "keep sentence-level alignment to block ids"],
    }
    status = "partial"
    return payload, evidence, {"notes": ["rewrites are produced by the agent; this payload is the diagnosis"],
                               "missing": []}, status, [f"{len(issues)} sentences flagged"]


def detect_genre(task: str, title: str) -> str:
    t = (task or "").lower()
    if "基金" in t or "grant" in t:
        return "grant-proposal"
    if "审稿" in t or "response" in t:
        return "response-to-reviewers"
    if "学位" in t or "thesis" in t:
        return "thesis"
    return "journal-article"


# --------------------------------------------------------------------------- #
# 7. references
# --------------------------------------------------------------------------- #
def parse_ref_entry(text: str) -> Dict[str, Any]:
    """Split one reference line into the four fields a citation style needs.

    Reference lines arrive in wildly different shapes ("[3] A. Author, B. Author.
    Title. Venue, 2020." / "Author (2020). Title. Journal.").  The author list is
    the part before the first sentence break that does not already contain a
    year, which keeps venue/year out of the `author` field; everything else is
    left empty rather than guessed.
    """
    year = re.search(r"\b(19|20)\d{2}[a-z]?\b", text)
    doi = re.search(r"10\.\d{4,9}/[^\s,;]+", text)
    body = re.sub(r"^\s*\[\d{1,3}\]\s*", "", text).strip()
    head = body.split(".")[0].strip(" .,")
    if 5 <= len(head) <= 180 and not re.search(r"\b(19|20)\d{2}\b", head):
        authors = head
    else:
        authors = body.split("(")[0].strip(" .,")
    title = ""
    m = re.search(r"[\"“](.+?)[\"”]", text)
    if m:
        title = m.group(1)
    else:
        parts = [p.strip() for p in body.split(".") if len(p.strip()) > 12]
        if len(parts) >= 2:
            title = parts[1][:180]
    return {
        "authors": authors[:200], "year": year.group(0) if year else "",
        "title": title, "doi": doi.group(0).rstrip(".") if doi else "",
        "raw": text[:600],
    }


def build_refs(doc: Dict[str, Any], case: Dict[str, Any], task: str):
    d = doc["document"]
    evidence: List[Dict[str, Any]] = []
    entries = []
    for r in d["references"]:
        rec = parse_ref_entry(r["text"])
        rec.update({"n": r["n"], "page": r["page"], "block": r["block"]})
        entries.append(rec)
        add_evidence(evidence, {"block": r["block"], "page": r["page"], "quote": r["text"][:200],
                                "why": f"reference {r['n']}"})
    cited: Dict[str, List[str]] = {}
    for b in d["blocks"]:
        if b["type"] == "heading" and re.match(r"^\s*(references|bibliography)", b["text"], re.I):
            break
        for m in CITE_BRACKET.finditer(b["text"]):
            for part in re.split(r",", m.group(1)):
                rng = re.match(r"\s*(\d+)\s*[–-]\s*(\d+)\s*", part)
                if rng:
                    for k in range(int(rng.group(1)), int(rng.group(2)) + 1):
                        cited.setdefault(str(k), []).append(b["id"])
                elif part.strip().isdigit():
                    cited.setdefault(part.strip(), []).append(b["id"])

    entry_ns = {str(e["n"]) for e in entries}
    missing_entries = sorted(set(cited) - entry_ns, key=lambda x: int(x))
    uncited = sorted(entry_ns - set(cited), key=lambda x: int(x))
    dupes = []
    seen: Dict[str, str] = {}
    for e in entries:
        key = (e["doi"] or re.sub(r"\W+", "", (e["title"] or "").lower())[:60])
        if key and key in seen:
            dupes.append({"a": seen[key], "b": str(e["n"]), "key": key})
        elif key:
            seen[key] = str(e["n"])

    def gbt(e):
        return f"{e['authors']}. {e['title']}[J]. {e['year']}. DOI:{e['doi']}" if e["doi"] else \
               f"{e['authors']}. {e['title']}[J]. {e['year']}."

    def apa(e):
        return f"{e['authors']} ({e['year']}). {e['title']}."

    def bkey(e):
        """A stable, readable BibTeX key: familyname + year + first long word."""
        first = (e["authors"] or "anon").split(",")[0].split()
        fam = re.sub(r"[^A-Za-z]", "", first[-1]) if first else "anon"
        word = next((w.lower() for w in re.findall(r"[A-Za-z]{4,}", e["title"] or "")), "")
        return (fam.lower() or "anon") + (e["year"] or "nd") + word

    def bibtex(e):
        fields = [("author", e["authors"]), ("title", e["title"]), ("year", e["year"])]
        if e["doi"]:
            fields.append(("doi", e["doi"]))
        body = ",\n  ".join(f"{k} = {{{v}}}" for k, v in fields if v)
        return "@article{%s,\n  %s\n}" % (bkey(e), body)

    payload = {
        "entries": entries,
        "in_text_citations": {k: v[:5] for k, v in sorted(cited.items(), key=lambda kv: int(kv[0]))},
        "issues": {
            "citations_without_entry": missing_entries,
            "entries_never_cited": uncited,
            "duplicates": dupes,
            "numbering_gaps": [str(i) for i in range(1, (max([int(n) for n in entry_ns] or [0]) + 1))
                               if str(i) not in entry_ns][:20],
        },
        "formatted": {"gb_t_7714": [gbt(e) for e in entries[:40]],
                      "apa": [apa(e) for e in entries[:40]],
                      "bibtex": [bibtex(e) for e in entries[:40]]},
        "bibtex_text": "\n\n".join(bibtex(e) for e in entries[:40]),
        "stats": {"entries": len(entries), "cited_keys": len(cited)},
    }
    status = "complete" if entries else "partial"
    return payload, evidence, {"notes": ["reference parsing is heuristic; verify DOI strings"],
                               "missing": []}, status, [f"{len(entries)} entries, {len(cited)} citation keys"]


# --------------------------------------------------------------------------- #
# 8. intro
# --------------------------------------------------------------------------- #
def build_intro(doc: Dict[str, Any], case: Dict[str, Any], task: str):
    d = doc["document"]
    evidence: List[Dict[str, Any]] = []
    groups: Dict[str, List[Dict[str, Any]]] = {}
    gaps, contributions, problems = [], [], []
    for b in blocks_in(doc, r"(introduction|related work|background|abstract|conclusion)"):
        for s in sentences(b["text"]):
            low = s.lower()
            if re.search(r"\b(however|remains? (?:un|open|unclear|unknown)|still unclear|not (?:yet )?(?:clear|known)|"
                         r"few (?:studies|works)|little (?:is )?known|rarely|has not been|have not been|"
                         r"limited (?:work|evidence|study|studies)|gap|open question|unknown)\b", low):
                gaps.append({"text": s, "block": b["id"], "page": b["page"]})
                add_evidence(evidence, ev(b, "gap statement"))
            if re.search(r"\b(we|this paper|this work)\b.{0,40}\b(propose|introduce|present|contribute|show|"
                         r"explore|study|investigate|compare|examine|report|provide|release|demonstrate)\b", low):
                contributions.append({"text": s, "block": b["id"], "page": b["page"]})
                add_evidence(evidence, ev(b, "contribution"))
            if re.search(r"\b(problem|challenge|difficult|costly|expensive|bottleneck|hard to|struggle)\b", low):
                problems.append({"text": s, "block": b["id"], "page": b["page"]})
                add_evidence(evidence, ev(b, "problem"))
        topic = sec_of(b)
        groups.setdefault(topic or "unassigned", []).append({"block": b["id"], "page": b["page"],
                                                             "gist": (sentences(b["text"]) or [""])[0][:220]})
    if not gaps:
        # fall back to contrastive/limitation sentences rather than returning nothing
        for b in blocks_in(doc, r"(introduction|related work|background|discussion|conclusion)"):
            for s in sentences(b["text"]):
                if re.search(r"\b(but|although|while|whereas|only|unlike|in contrast)\b", s, re.I):
                    gaps.append({"text": s, "block": b["id"], "page": b["page"], "derived": True})
                    add_evidence(evidence, ev(b, "contrast (derived gap)"))
                    if len(gaps) >= 6:
                        break
            if len(gaps) >= 6:
                break

    cited = set()
    for b in d["blocks"]:
        for m in CITE_BRACKET.finditer(b["text"]):
            cited.add(m.group(1))
    payload = {
        "problem_statements": problems[:8],
        "gap_statements": gaps[:10],
        "contributions": contributions[:10],
        "related_work_groups": [{"section": k, "items": v[:6]} for k, v in groups.items()][:12],
        "citation_coverage": {"distinct_keys": len(cited), "reference_entries": len(d["references"])},
        "outline": ["research context (why now, what is hard)",
                    "grouped prior work (by problem / method / data)",
                    "gap derived from those groups",
                    "this work's contributions, each mapped to a figure/table/result",
                    "scope and limits"],
    }
    status = "complete" if gaps and contributions else "partial"
    return payload, evidence, {"notes": ["prose is written by the agent from these evidence-bound claims"],
                               "missing": []}, status, [f"{len(gaps)} gaps, {len(contributions)} contributions"]


# --------------------------------------------------------------------------- #
# 9. methods
# --------------------------------------------------------------------------- #
HYPER = re.compile(r"\b(learning rate|batch size|epochs?|steps?|layers?|hidden (?:size|dimension|units?)|"
                   r"dropout|weight decay|momentum|warmup|heads?|temperature|seed|patience|"
                   r"optimizer|activation|kernel|window size|embedding (?:size|dimension))\b[^.;]{0,40}",
                   re.I)


def build_methods(doc: Dict[str, Any], case: Dict[str, Any], task: str):
    d = doc["document"]
    evidence: List[Dict[str, Any]] = []
    params: List[Dict[str, Any]] = []
    datasets: List[Dict[str, Any]] = []
    hardware = []
    seeds = []
    for b in d["blocks"]:
        for s in sentences(b["text"]):
            for m in HYPER.finditer(s):
                seg = m.group(0)
                val = re.search(r"(\d+(?:[.,]\d+)?\s*" + UNIT + r"?|true|false|adam\w*|sgd|relu|gelu)", seg, re.I)
                params.append({"name": m.group(1).lower(), "value": val.group(1) if val else "",
                               "context": seg[:120], "block": b["id"], "page": b["page"]})
                add_evidence(evidence, ev(b, "parameter"))
            if re.search(r"\b(GPU|TPU|CPU|A100|V100|H100|RTX|memory|VRAM)\b", s):
                hardware.append({"text": s[:200], "block": b["id"], "page": b["page"]})
            if re.search(r"\bseed\b", s, re.I):
                seeds.append({"text": s[:200], "block": b["id"], "page": b["page"]})
            m = re.search(r"\b([A-Z][A-Za-z0-9-]*(?:\s+[A-Z0-9][A-Za-z0-9-]*){0,3})\s+(?:dataset|corpus)\b", s)
            if m:
                datasets.append({"name": m.group(1), "text": s[:220], "block": b["id"], "page": b["page"]})
                add_evidence(evidence, ev(b, "dataset"))

    checklist = [
        ("code version", bool(re.search(r"\b(github|gitlab|commit|version|release)\b", " ".join(
            b["text"] for b in d["blocks"]), re.I))),
        ("environment", bool(re.search(r"\b(python|cuda|pytorch|tensorflow|jax|version)\b", " ".join(
            b["text"] for b in d["blocks"]), re.I))),
        ("hyperparameters", len(params) >= 3),
        ("dataset version/split", bool(datasets)),
        ("random seeds", bool(seeds)),
        ("hardware", bool(hardware)),
        ("evaluation metric", bool(re.search(r"\b(accuracy|f1|bleu|rouge|auc|rmse)\b", " ".join(
            b["text"] for b in d["blocks"]), re.I))),
        ("repetitions", bool(re.search(r"\b(runs?|trials?|repeats?|fold)\b", " ".join(
            b["text"] for b in d["blocks"]), re.I))),
    ]
    payload = {
        "parameters": params[:60],
        "datasets": datasets[:12],
        "hardware": hardware[:5],
        "seeds": seeds[:5],
        "reproducibility_checklist": [{"item": k, "found": v} for k, v in checklist],
        "missing": [k for k, v in checklist if not v],
        "limitations": [{"text": s, "block": b["id"]} for b in blocks_in(doc, r"(discussion|conclusion|limitation)")
                        for s in sentences(b["text"]) if re.search(r"\blimitation|future work|only\b", s, re.I)][:8],
    }
    status = "complete" if params and datasets else "partial"
    return payload, evidence, {"notes": [], "missing": payload["missing"]}, status, \
        [f"{len(params)} parameter mentions, {len(datasets)} dataset mentions"]


# --------------------------------------------------------------------------- #
# 10. latex
# --------------------------------------------------------------------------- #
LATEX_ESC = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
             "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def tex_escape(s: str) -> str:
    return "".join(LATEX_ESC.get(ch, ch) for ch in s)


def build_latex(doc: Dict[str, Any], case: Dict[str, Any], task: str, out_dir: str | None = None):
    d = doc["document"]
    evidence: List[Dict[str, Any]] = []
    body: List[str] = []
    seen_sections = set()
    for b in d["blocks"]:
        if b["type"] == "heading":
            title = b["text"].strip()
            if title.lower() in seen_sections:
                continue
            seen_sections.add(title.lower())
            cmd = {1: "section", 2: "subsection", 3: "subsubsection"}.get(b.get("level", 2), "paragraph")
            body.append(f"\\{cmd}{{{tex_escape(title)}}}\n")
        elif b["type"] == "body":
            body.append(tex_escape(b["text"]) + "\n")
        elif b["type"] == "formula":
            body.append("\\begin{equation}\n  " + b["text"].strip() + "\n\\end{equation}\n")

    tables_tex = []
    for i, t in enumerate(d["tables"][:8], 1):
        cols = "l" * min(t["n_cols"], 6)
        rows = [" & ".join(tex_escape(c)[:80] for c in r[:6]) + r" \\" for r in t["rows"][:30]]
        tables_tex.append(
            "\\begin{table}[htbp]\n\\centering\n\\caption{%s}\n\\begin{tabular}{%s}\n\\toprule\n%s\n\\bottomrule\n"
            "\\end{tabular}\n\\end{table}\n" % (tex_escape(t.get("caption", f"Table {i}")), cols, "\n".join(rows)))

    bib = "\n".join("\\bibitem{ref%d} %s" % (i, tex_escape(r["text"][:300]))
                    for i, r in enumerate(d["references"], 1))
    tex = "\n".join([
        "\\documentclass[11pt]{article}",
        "\\usepackage[utf8]{inputenc}\\usepackage{booktabs}\\usepackage{amsmath}\\usepackage{graphicx}",
        "\\usepackage{hyperref}",
        f"\\title{{{tex_escape(d['meta'].get('title', 'Untitled'))}}}",
        f"\\author{{{tex_escape('; '.join(d['meta'].get('authors', [])) or 'Author')}}}",
        "\\begin{document}\\maketitle",
        "\\begin{abstract}" + tex_escape(d["meta"].get("abstract", "")) + "\\end{abstract}",
        "\n".join(body),
        "\n".join(tables_tex),
        "\\begin{thebibliography}{99}\n" + bib + "\n\\end{thebibliography}" if bib else "",
        "\\end{document}",
    ])
    files = {"main.tex": tex}

    compile_info = {"attempted": False}
    if out_dir:
        tex_dir = os.path.join(out_dir, "latex")
        os.makedirs(tex_dir, exist_ok=True)
        with open(os.path.join(tex_dir, "main.tex"), "w", encoding="utf-8") as fh:
            fh.write(tex)
        engine = shutil.which("pdflatex") or shutil.which("latexmk") or shutil.which("xelatex")
        if engine:
            compile_info["attempted"] = True
            compile_info["engine"] = os.path.basename(engine)
            cmd = [engine, "-interaction=nonstopmode", "-halt-on-error", "main.tex"] \
                if "latexmk" not in engine else [engine, "-pdf", "-interaction=nonstopmode", "main.tex"]
            try:
                proc = subprocess.run(cmd, cwd=tex_dir, capture_output=True, timeout=240)
                log = (proc.stdout or b"").decode("utf-8", "replace")
                compile_info["ok"] = proc.returncode == 0
                compile_info["errors"] = [l for l in log.splitlines() if l.startswith("!")][:10]
                compile_info["pdf"] = os.path.exists(os.path.join(tex_dir, "main.pdf"))
            except Exception as exc:
                compile_info["ok"] = False
                compile_info["errors"] = [f"{type(exc).__name__}: {exc}"]

    for b in d["blocks"][:6]:
        add_evidence(evidence, ev(b, "section source"))
    payload = {
        "files": list(files),
        "tex": tex[:20000],
        "compile": compile_info,
        "structure": [{"level": s["level"], "title": s["title"]} for s in d["sections"]],
        "environment": {"engine": compile_info.get("engine", "not found"),
                        "packages": ["booktabs", "amsmath", "graphicx", "hyperref"]},
    }
    status = "complete" if compile_info.get("ok") else "partial"
    return payload, evidence, {"notes": [] if compile_info.get("ok") else
                               ["LaTeX engine missing or compile failed; source is still complete"],
                               "missing": []}, status, [f"main.tex {len(tex)} chars"]


# --------------------------------------------------------------------------- #
# dispatcher
# --------------------------------------------------------------------------- #
MODES = {
    "parse": build_parse, "translate": build_translate, "notes": build_notes,
    "nanopub": build_nanopub, "kg": build_kg, "polish": build_polish,
    "refs": build_refs, "intro": build_intro, "methods": build_methods, "latex": build_latex,
}


def build(mode: str, doc: Dict[str, Any], case: Dict[str, Any], task: str, out_dir: str | None = None):
    if mode not in MODES:
        raise KeyError(f"unknown mode {mode}")
    fn = MODES[mode]
    if mode == "latex":
        return fn(doc, case, task, out_dir=out_dir)
    return fn(doc, case, task)
