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
               "section": sec_of(b), "type": b["type"], "text": b["text"],
               # decision evidence, so a reviewer can see *why* a block starts here
               "bbox": b.get("bbox"), "order_rule": b.get("order_rule"),
               "break_reason": b.get("break_reason"),
               "hyphen_merged": bool(b.get("hyphen_merged")),
               "text_raw_ref": "raw_text.txt"}
              for b in d["blocks"]]
    for b in d["blocks"][:12]:
        add_evidence(evidence, ev(b, "structure sample"))
    for t in d["tables"][:6]:
        add_evidence(evidence, {"table": t["id"], "page": t["page"], "quote": t["caption"][:200],
                                "why": "table with caption", "block": t.get("caption_block")})
    payload = {
        # A contract field called `document` (or `full structure`) is asking for
        # the document as a whole, so this slice carries the outline and the
        # counts as well as the bibliographic head -- not just the metadata.
        "document": {
            "title": d["meta"].get("title", ""), "authors": d["meta"].get("authors", []),
            "abstract": d["meta"].get("abstract", ""), "keywords": d["meta"].get("keywords", []),
            "doi": d["meta"].get("doi", ""), "pages": d["source"]["pages"],
            "engine": d["source"]["backend"], "sha256": d["source"]["sha256"],
            "section_count": len(d["sections"]),
            "sections": [{"level": s["level"], "title": s["title"], "page": s["page"]}
                         for s in d["sections"]],
            "block_count": len(d["blocks"]),
            "counts": {"tables": len(d["tables"]), "figures": len(d["figures"]),
                       "formulas": len(d["formulas"]), "references": len(d["references"])},
        },
        "structure": [{"level": s["level"], "title": s["title"], "page": s["page"], "block": s["block"]}
                      for s in d["sections"]],
        "content": {"blocks": blocks, "tables": d["tables"], "figures": d["figures"],
                    "formulas": d["formulas"], "references": d["references"]},
        "coverage": d["quality"],
        "page_map": d["page_stats"],
        "verbatim": {"file": "raw_text.txt", "chars": d.get("verbatim_chars"),
                     "note": "engine text before cleaning; diff against the PDF text layer "
                             "to audit 逐字一致, then use content.blocks[].text for structure"},
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


MAX_SEGMENTS = 120
SEG_CHARS = 700
SKIP_SECTION = re.compile(r"(references|bibliography|参考文献|acknowledg|appendix|supplementary)", re.I)


def _seg_priority(section: str) -> int:
    s = (section or "").lower()
    if "abstract" in s or "摘要" in s:
        return 0
    if "introduction" in s or "引言" in s:
        return 1
    if any(k in s for k in ("method", "approach", "model", "方法", "模型")):
        return 2
    if any(k in s for k in ("experiment", "result", "evaluation", "实验", "结果")):
        return 3
    if any(k in s for k in ("conclusion", "discussion", "结论", "讨论")):
        return 4
    return 5


def build_translate(doc: Dict[str, Any], case: Dict[str, Any], task: str):
    d = doc["document"]
    evidence: List[Dict[str, Any]] = []
    segments: List[Dict[str, Any]] = []
    seg_id = 0
    buf, buf_meta = "", None

    def flush():
        nonlocal buf, buf_meta, seg_id
        if not buf.strip() or not buf_meta:
            buf, buf_meta = "", None
            return
        seg_id += 1
        segments.append({"seg": f"s{seg_id:04d}", "block": buf_meta["block"], "page": buf_meta["page"],
                         "section": buf_meta["section"], "type": buf_meta["type"], "source": buf.strip(),
                         "protected": protected_tokens(buf), "translation": ""})
        add_evidence(evidence, ev(buf_meta["raw"], "segment source"))
        buf, buf_meta = "", None

    for b in d["blocks"]:
        if b["type"] not in {"body", "heading", "caption"}:
            continue
        if b.get("in_table"):
            continue
        if SKIP_SECTION.search(b.get("section") or ""):
            continue
        text = b["text"].strip()
        if len(text) < 2 or re.match(r"^\s*\[\d{1,3}\]", text):
            continue
        same_flow = buf_meta and buf_meta["page"] == b["page"] and buf_meta["section"] == b.get("section")
        if same_flow and len(buf) + len(text) <= SEG_CHARS:
            buf = (buf + " " + text).strip()
            continue
        flush()
        if len(text) <= SEG_CHARS:
            buf, buf_meta = text, {"block": b["id"], "page": b["page"], "section": sec_of(b),
                                   "type": b["type"], "raw": b}
        else:
            for ch in [text[i:i + SEG_CHARS] for i in range(0, len(text), SEG_CHARS)]:
                buf, buf_meta = ch, {"block": b["id"], "page": b["page"], "section": sec_of(b),
                                     "type": b["type"], "raw": b}
                flush()
    flush()

    deferred = 0
    if len(segments) > MAX_SEGMENTS:
        ranked = sorted(range(len(segments)), key=lambda i: (_seg_priority(segments[i]["section"]), i))
        keep = set(ranked[:MAX_SEGMENTS])
        deferred = len(segments) - len(keep)
        segments = [s for i, s in enumerate(segments) if i in keep]

    terms = keyphrases(d, top=60)
    for t in terms:
        t["zh"] = SEED_GLOSSARY.get(t["term"].lower(), "")
        if not t["zh"]:
            for k, v in SEED_GLOSSARY.items():
                if k in t["term"].lower():
                    t["zh"] = v
                    break
    ids = [s["seg"] for s in segments]
    batches = [ids[i:i + 20] for i in range(0, len(ids), 20)]
    payload = {
        "document": {"title": d["meta"].get("title", ""), "pages": d["source"]["pages"]},
        "segments": segments,
        "batches": batches,
        "deferred_segments": deferred,
        "glossary": terms,
        "rules": {
            "unit_of_translation": "segment",
            "term_policy": "one rendering per glossary term across all segments",
            "keep_verbatim": ["numbers", "units", "citation markers", "figure/table numbers",
                              "formulas", "model/dataset proper names", "URLs", "DOIs"],
            "register": "academic Chinese, no added claims, no dropped hedges",
            "batch_size": 20,
            "how_to_fill": "translate one batch per request, write fill.json, rerun run.py --fill",
        },
    }
    status = "partial"
    notes = [f"{len(segments)} segments in {len(batches)} batches of <=20; translations are empty "
             f"until the agent fills fill.json and reruns with --fill"]
    if deferred:
        notes.append(f"{deferred} low-priority segments were deferred to stay inside the request budget")
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
            if re.search(r"\b(limitation|limitations|limited|limited to|caveat|future work|"
                         r"do not|does not|cannot|scope of the claim|only (?:one|two|single))\b", low):
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
    "dataset": r"\b([A-Z][A-Za-z0-9-]*(?:\s+[A-Z][A-Za-z0-9-]*){0,3}\s+(?:dataset|corpus|benchmark))\b"
               r"|\b(WMT\s?\d{2,4}(?:\s+[A-Z][a-z]+-[A-Z][a-z]+)?|IWSLT\s?\d{2,4}|"
               r"CoNLL[-\s]?\d{2,4}|SQuAD(?:\s?2\.0)?|GLUE|ImageNet|MS-?COCO|WikiText-\d+|"
               r"LibriSpeech|Multi30k|Penn Treebank)\b",
    "metric": r"\b(accuracy|precision|recall|f1|bleu|rouge|perplexity|auc|mse|mae|rmse|map)\b",
    "tool": r"\b(fairseq|pytorch|tensorflow|jax|spacy|opennmt|moses|kenlm|huggingface|"
            r"transformers|scikit-learn|xgboost|lightgbm)\b",
    "task": r"\b(classification|translation|summarization|question answering|segmentation|"
            r"detection|generation|retrieval|regression|clustering)\b",
}
# the capitalised-entity patterns must stay case sensitive: with re.I they match
# ordinary lowercase prose ("of the corpus") and pollute the graph
CASE_SENSITIVE_KINDS = {"dataset", "tool"}
REL_PATTERNS = [
    ("uses", r"([A-Z][\w-]{2,}(?:\s+[A-Z][\w-]{2,}){0,2})\s+(?:uses?|employs?|leverages?|is based on|relies on)\s+([A-Za-z][\w-]{2,}(?:\s+[A-Za-z][\w-]{2,}){0,2})"),
    ("evaluated_on", r"([A-Za-z][\w-]{2,})\s+(?:is|was|are|were)?\s*(?:evaluated|tested|benchmarked|trained|fine-tuned)\s+(?:on|with|using)\s+([A-Za-z0-9][\w-]{2,})"),
    ("outperforms", r"([A-Z][\w-]{2,}(?:\s+[A-Z][\w-]{2,}){0,2})\s+(?:outperforms?|surpasses?|beats?)\s+([A-Z][\w-]{2,}(?:\s+[A-Z][\w-]{2,}){0,2})"),
    ("improves", r"([A-Za-z][\w-]{2,})\s+(?:improves?|increases?|reduces?)\s+([A-Za-z][\w-]{2,})"),
]


GENERIC_HEADINGS = re.compile(
    r"^\s*(\d+\.?\s*)?(abstract|introduction|related work|background|conclusion|conclusions|"
    r"references|bibliography|acknowledg\w*|appendix|supplementary|keywords?)\s*$", re.I)
CUE_VERBS = [
    ("uses", r"\b(uses?|employs?|leverages?|relies on|is based on)\b"),
    # the preposition is part of the pattern: "practical to train [3]" is not a
    # trained_on relation, "trained on WMT 2014" is
    ("trained_on", r"\b(?:trained|trains?|train|fine-tuned|pre-trained|pretrained)\s+(?:on|with|using)\b"),
    ("evaluated_on", r"\b(?:evaluated|evaluates?|tested|tests?|benchmarked|benchmarks?)\s+(?:on|with|using)\b"),
    ("outperforms", r"\b(outperforms?|surpasses?|beats?|improves? (?:up)?on)\b"),
    ("improves", r"\b(improves?|reduces?|increases?|achieves?)\b"),
    ("proposes", r"\b(proposes?|introduces?|presents?|describes?)\b"),
]
STOP_OBJ = {"the", "a", "an", "this", "that", "these", "those", "its", "their", "our", "we",
            "it", "they", "on", "in", "of", "to", "for", "with", "by", "and", "or", "as"}


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

    def add_edge(a: str, c: str, rel: str, sentence: str, b: Dict[str, Any]) -> None:
        if not a or not c or a == c:
            return
        for e in edges:
            if e["source"] == a and e["target"] == c and e["relation"] == rel:
                return
        edges.append({"source": a, "target": c, "relation": rel,
                      "evidence": {"block": b["id"], "page": b["page"],
                                   "quote": sentence.strip()[:300]}})
        add_evidence(evidence, ev(b, f"relation {rel}"))

    # 1) seed nodes: substantive headings + typed entities
    # the title often arrives as two heading blocks ("… Neural Machine" +
    # "Translation"); both are title text, not concepts
    title = (d["meta"].get("title") or "").lower().strip()
    zone = [title]
    for b in d["blocks"][:6]:
        if b["type"] == "heading":
            zone.append(b["text"].lower().strip())
        elif zone[-1] != title:
            break
    title_zone = " ".join(z for z in zone if z)
    for b in d["blocks"]:
        if b["type"] == "heading" and not GENERIC_HEADINGS.match(b["text"]):
            h = b["text"].strip()
            is_title_part = bool(title_zone) and h.lower() in title_zone and len(h.split()) <= 12
            if not is_title_part and (b.get("level") or 1) <= 3 and 3 < len(h) < 90:
                node(h, "concept", b)
        for kind, rx in ENTITY_HINTS.items():
            flags = 0 if kind in CASE_SENSITIVE_KINDS else re.I
            for m in re.finditer(rx, b["text"], flags):
                if 2 < len(m.group(0)) < 70:
                    node(m.group(0), kind, b)

    # 2) relation pass over sentences: co-mention + cue verb
    for b in d["blocks"]:
        if b["type"] not in ("body", "heading"):
            continue
        for sentence in sentences(b["text"], 400):
            if len(sentence) < 40:
                continue
            s_low = sentence.lower()
            hits = []
            for label, nid in list(keymap.items()):
                if len(label) < 4:
                    continue
                if label in s_low and not any(h[0] == nid for h in hits):
                    hits.append((nid, label))
            hits = hits[:6]
            if len(hits) >= 2:
                base = hits[0][0]
                for nid, _ in hits[1:]:
                    add_edge(base, nid, "related_to", sentence, b)
                continue
            if len(hits) == 1:
                for rel, rx in CUE_VERBS:
                    m = re.search(rx, sentence, re.I)
                    if not m:
                        continue
                    tail = sentence[m.end():].strip(" ,.;:")
                    words = [w for w in tail.split()[:5] if w.lower().strip(",.()") not in STOP_OBJ]
                    if len(words) < 1:
                        continue
                    obj = " ".join(words[:4]).strip(" ,.;:()")
                    if 2 < len(obj) < 60 and not re.match(r"^(the|a|an|this|that)\b", obj, re.I):
                        add_edge(hits[0][0], node(obj, "entity", b), rel, sentence, b)
                    break

    # 2b) section -> entity: an entity mentioned inside a section is linked to
    # that section's node.  The evidence is the block that carries both, so the
    # edge is as checkable as any other -- it is not a co-occurrence guess.
    section_nodes = {n["label"].lower().strip(): n["id"]
                     for n in nodes.values() if n["type"] == "concept"}
    if section_nodes:
        for b in d["blocks"]:
            if b["type"] not in ("body", "heading"):
                continue
            hid = section_nodes.get((sec_of(b) or "").lower().strip())
            if not hid:
                continue
            low = b["text"].lower()
            added = 0
            for label, nid in list(keymap.items()):
                if added >= 5:
                    break
                if nid == hid or len(label) < 4 or nodes.get(label, {}).get("type") == "concept":
                    continue
                if label in low:
                    add_edge(hid, nid, "mentions", b["text"][:300], b)
                    added += 1

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
    for rel in ("uses", "trained_on", "evaluated_on", "outperforms", "related_to"):
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
    # a graph where every node is isolated is not a graph: gate on density
    enough = len(nodes) >= 8 and len(edges) >= max(10, int(len(nodes) * 0.4))
    status = "complete" if enough else "partial"
    notes = [f"{len(edges)} edges over {len(nodes)} nodes; relations come from cue verbs "
             f"and sentence-level co-mention, each with its supporting sentence"]
    if not enough:
        notes.append("edge density below the completeness gate (nodes*0.4); treat as partial")
    return payload, evidence, {"notes": notes, "missing": []}, status, \
        [f"{len(nodes)} nodes, {len(edges)} edges"]


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
                issues.append({"block": b["id"], "page": b["page"], "sentence": s[:300],
                               "flags": flags, "protected": protected_tokens(s)})
                add_evidence(evidence, ev(b, "style issue"))
            elif re.search(r"\d", s) or CITE_BRACKET.search(s):
                # sentences carrying numbers or citations enter the rewrite queue
                # even without a style flag: they are the ones a rewrite can corrupt
                issues.append({"block": b["id"], "page": b["page"], "sentence": s[:300],
                               "flags": ["numeric"], "protected": protected_tokens(s)})
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
        # one empty edit record per flagged sentence: the agent fills `revised`
        # and `reason`, so "what is still unchanged" is visible instead of implied
        "rewrites": [{"block": i["block"], "page": i["page"], "original": i["sentence"],
                      "revised": "", "type": "", "reason": "",
                      "kept": i.get("protected") or {}} for i in issues[:40]],
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
    """Split one reference line into the fields a citation style needs.

    Two shapes dominate: "Author A, Author B. Title[C]//Venue. 2017: 1-10." and
    "Author A, Author B. Title. Venue, 2017, 12(3): 1-10."  The authors end at
    the first sentence break, the title ends at the type marker (``[C]``), at
    ``//`` or at the next sentence break, and nothing is invented when a field
    is absent.
    """
    year = re.search(r"\b(19|20)\d{2}[a-z]?\b", text)
    doi = re.search(r"10\.\d{4,9}/[^\s,;]+", text)
    body = re.sub(r"^\s*\[\d{1,3}\]\s*", "", text).strip()

    kind = ""
    tm = re.search(r"\[(EB/OL|C|J|M|D|R|S|N)\]", body)
    if tm:
        kind = tm.group(1)

    head = body.split(".")[0].strip(" .,")
    if 5 <= len(head) <= 180 and not re.search(r"\b(19|20)\d{2}\b", head):
        authors, rest = head, body[len(head):].lstrip(". ")
    else:
        authors, rest = body.split("(")[0].strip(" .,"), body

    cut = len(rest)
    for pat in (r"\[(?:EB/OL|[A-Z/]{1,4})\]", r"\s//", r"\.\s"):
        m = re.search(pat, rest)
        if m and m.start() < cut:
            cut = m.start()
    title = re.sub(r"\s+", " ", rest[:cut]).strip(" .,")
    tail = rest[cut:]

    venue = ""
    vm = re.search(r"//\s*([^.;]{2,90})", tail)
    if vm:
        venue = vm.group(1).strip(" ,.")
    else:
        vm = re.search(r"((?:Proceedings|Proc\.|Conference|Workshop|Journal|Transactions|Letters|"
                       r"Review|Magazine|arXiv[^\s,]*|Symposium|NeurIPS|ACL|NAACL|EMNLP|ICLR|ICML|"
                       r"AAAI|CVPR|ICCV)[^,.;]{0,80})", tail, re.I)
        if vm:
            venue = re.sub(r"\s+", " ", vm.group(1)).strip(" ,.;")

    volume = issue = pages = ""
    pm = re.search(r"(\d{1,4})\s*[–-]\s*(\d{1,4})", tail)
    if pm:
        pages = f"{pm.group(1)}-{pm.group(2)}"
    vim = re.search(r"\b(\d{1,4})\s*(?:\((\d{1,3})\))?\s*(?=[,:])", tail)
    if vim and not (year and vim.group(1) == year.group(0)):
        volume = vim.group(1)
        issue = vim.group(2) or ""

    if not kind:
        hint = f"{venue} {tail}"
        if re.search(r"proceedings|conference|workshop|symposium|proc\.|neurips|acl|emnlp|iclr|icml",
                     hint, re.I):
            kind = "C"
        elif re.search(r"arxiv|preprint|corr\b", hint, re.I):
            kind = "EB/OL"
        elif re.search(r"\bed\.|edited|press\b", tail, re.I):
            kind = "M"
        else:
            kind = "J"
    return {
        "authors": authors[:200], "year": year.group(0) if year else "",
        "title": title[:180], "venue": venue[:160], "volume": volume, "issue": issue,
        "pages": pages, "type": kind, "doi": doi.group(0).rstrip(".") if doi else "",
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
        kind = e.get("type") or "J"
        tail = ""
        if e.get("volume"):
            tail = f", {e['volume']}"
            if e.get("issue"):
                tail += f"({e['issue']})"
        if e.get("pages"):
            tail += f": {e['pages']}"
        if kind == "C":
            venue = f"//{e['venue']}" if e.get("venue") else ""
            return f"{e['authors']}. {e['title']}[C]{venue}. {e['year']}{tail}."
        if kind == "EB/OL":
            return f"{e['authors']}. {e['title']}[EB/OL]. {e.get('venue') or 'arXiv'}, {e['year']}."
        if kind == "M":
            return f"{e['authors']}. {e['title']}[M]. {e.get('venue') or ''}, {e['year']}."
        venue = f"{e['venue']}, " if e.get("venue") else ""
        return f"{e['authors']}. {e['title']}[J]. {venue}{e['year']}{tail}."

    def apa(e):
        tail = ""
        if e.get("volume"):
            tail = f", {e['volume']}"
            if e.get("issue"):
                tail += f"({e['issue']})"
        if e.get("pages"):
            tail += f", {e['pages']}"
        venue = f"{e['venue']}{tail}. " if e.get("venue") else ""
        return f"{e['authors']} ({e['year']}). {e['title']}. {venue}".strip()

    def bkey(e):
        """A stable, readable BibTeX key: familyname + year + first long word."""
        first = (e["authors"] or "anon").split(",")[0].split()
        fam = re.sub(r"[^A-Za-z]", "", first[-1]) if first else "anon"
        word = next((w.lower() for w in re.findall(r"[A-Za-z]{4,}", e["title"] or "")), "")
        return (fam.lower() or "anon") + (e["year"] or "nd") + word

    def bibtex(e):
        kind = {"C": "inproceedings", "M": "book", "EB/OL": "misc"}.get(e.get("type") or "J", "article")
        fields = [("author", e["authors"]), ("title", e["title"]), ("year", e["year"])]
        if e.get("venue"):
            fields.append(("booktitle" if kind == "inproceedings" else "journal", e["venue"]))
        if e.get("volume"):
            fields.append(("volume", e["volume"]))
        if e.get("pages"):
            fields.append(("pages", e["pages"]))
        if e["doi"]:
            fields.append(("doi", e["doi"]))
        body = ",\n  ".join(f"{k} = {{{v}}}" for k, v in fields if v)
        return "@%s{%s,\n  %s\n}" % (kind, bkey(e), body)

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
        "draft": {
            "status": "to_be_written",
            "paragraphs": [
                {"role": "context", "text": "", "must_use": "problem_statements", "citations": []},
                {"role": "prior_work", "text": "", "must_use": "related_work_groups", "citations": []},
                {"role": "gap", "text": "", "must_use": "gap_statements", "citations": []},
                {"role": "contributions", "text": "", "must_use": "contributions", "citations": []},
                {"role": "scope", "text": "", "must_use": "outline", "citations": []},
            ],
            "rules": {"min_words_per_paragraph": 120,
                      "citations": "only [n] keys that exist in the reference list",
                      "no_new_claims": "every factual claim must trace to evidence[]",
                      "how_to_fill": "write fill.json {\"replace\": {\"draft\": {...}}} and rerun run.py --fill"},
        },
    }
    status = "partial"   # prose is missing until the agent writes it
    notes = [f"{len(gaps)} gaps, {len(contributions)} contributions; draft has 5 empty paragraphs "
             f"that the agent must write (fill.json replace.draft), then pass --fill"]
    return payload, evidence, {"notes": ["prose is written by the agent from these evidence-bound claims",
                                        "status stays partial until draft paragraphs are filled"],
                               "missing": []}, status, notes


# --------------------------------------------------------------------------- #
# 9. methods
# --------------------------------------------------------------------------- #
HYPER_NAME = re.compile(r"\b(learning rate|batch size|epochs?|steps?|layers?|hidden (?:size|dimension|units?)|"
                        r"dropout|weight decay|momentum|warmup|heads?|temperature|seed|patience|"
                        r"optimizer|activation|kernel|window size|embedding (?:size|dimension))\b",
                        re.I)
HYPER = re.compile(HYPER_NAME.pattern + r"[^;]{0,40}", re.I)
# "learning rate of 0.0003" must keep the decimal: stopping the context window at
# the first "." truncated the value to "0"
DS_NAMED = re.compile(r"\b(WMT\s?\d{2,4}(?:\s+[A-Z][a-z]+-[A-Z][a-z]+)?|IWSLT\s?\d{2,4}|"
                      r"CoNLL[-\s]?\d{2,4}|SQuAD(?:\s?2\.0)?|GLUE|ImageNet|MS-?COCO|WikiText-\d+|"
                      r"LibriSpeech|Multi30k|Penn Treebank)\b")


def build_methods(doc: Dict[str, Any], case: Dict[str, Any], task: str):
    d = doc["document"]
    evidence: List[Dict[str, Any]] = []
    params: List[Dict[str, Any]] = []
    datasets: List[Dict[str, Any]] = []
    hardware = []
    seeds = []
    for b in d["blocks"]:
        for s in sentences(b["text"]):
            # scan names independently of the 40-char context window: matching
            # "learning rate ... dropout" as one span used to swallow the other
            # parameter names in the same sentence
            for m in HYPER_NAME.finditer(s):
                seg = s[m.start(): m.end() + 45].strip()
                val = re.search(r"(\d+(?:\.\d+)?\s*" + UNIT + r"?|true|false|adam\w*|sgd|relu|gelu)",
                                seg[m.end() - m.start():], re.I) or \
                    re.search(r"(\d+(?:\.\d+)?)", seg, re.I)
                name = m.group(1).lower()
                value = val.group(1).strip() if val else ""
                if any(p["name"] == name and p["value"] == value for p in params):
                    continue
                params.append({"name": name, "value": value, "context": seg[:120],
                               "block": b["id"], "page": b["page"]})
                add_evidence(evidence, ev(b, "parameter"))
            if re.search(r"\b(GPU|TPU|CPU|A100|V100|H100|RTX|memory|VRAM)\b", s):
                hardware.append({"text": s[:200], "block": b["id"], "page": b["page"]})
            if re.search(r"\bseed\b", s, re.I):
                seeds.append({"text": s[:200], "block": b["id"], "page": b["page"]})
            m = re.search(r"\b([A-Z][A-Za-z0-9-]*(?:\s+[A-Z0-9][A-Za-z0-9-]*){0,3})\s+(?:dataset|corpus)\b", s)
            m2 = DS_NAMED.search(s)
            if m or m2:
                nm = m.group(1) if m else m2.group(1)
                if not any(x["name"].lower() == nm.lower() for x in datasets):
                    datasets.append({"name": nm, "text": s[:220], "block": b["id"], "page": b["page"]})
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
        "draft": {
            "status": "to_be_written",
            "paragraphs": [
                {"role": "data", "text": "", "must_use": "datasets"},
                {"role": "model", "text": "", "must_use": "parameters"},
                {"role": "training", "text": "", "must_use": "parameters"},
                {"role": "evaluation", "text": "", "must_use": "reproducibility_checklist"},
            ],
            "rules": {"min_words_per_paragraph": 100,
                      "no_invented_values": "only report numbers that appear in parameters/datasets",
                      "report_missing": "list what the paper does not report under missing[]",
                      "how_to_fill": "write fill.json {\"replace\": {\"draft\": {...}}} and rerun run.py --fill"},
        },
    }
    status = "partial"   # the section text is missing until the agent writes it
    notes = [f"{len(params)} parameter mentions, {len(datasets)} dataset mentions; "
             f"draft has 4 empty paragraphs the agent must write"]
    return payload, evidence, {"notes": notes, "missing": payload["missing"]}, status, \
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
    formula_tex: Dict[str, Dict[str, Any]] = {}
    for f in d.get("formulas") or []:
        for bid in (f.get("blocks") or [f.get("block")]):
            if bid:
                formula_tex[bid] = f
    formula_review: List[Dict[str, Any]] = []
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
            f = formula_tex.get(b["id"]) or {}
            math = f.get("tex") or tex_escape(b["text"].strip())
            body.append("\\begin{equation}\n  " + math + "\n\\end{equation}\n")
            if f.get("tex_confidence") == "low":
                formula_review.append({"block": b["id"], "page": b["page"], "number": f.get("number", "")})

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
        "\\usepackage[utf8]{inputenc}\\usepackage[T1]{fontenc}\\usepackage{lmodern}",
        "\\usepackage{booktabs}\\usepackage{amsmath}\\usepackage{amsfonts}\\usepackage{graphicx}",
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

    def static_check(src: str) -> Dict[str, Any]:
        problems: List[str] = []
        begins = re.findall(r"\\begin\{([^}]+)\}", src)
        ends = re.findall(r"\\end\{([^}]+)\}", src)
        for env in sorted(set(begins) | set(ends)):
            if begins.count(env) != ends.count(env):
                problems.append(f"env {env}: {begins.count(env)} begin vs {ends.count(env)} end")
        if src.count("{") != src.count("}"):
            problems.append(f"unbalanced braces: {src.count('{')} vs {src.count('}')}")
        return {"ok": not problems, "problems": problems[:10]}

    compile_info: Dict[str, Any] = {"attempted": False, "static_check": static_check(tex)}
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
            errors: List[str] = []
            ok = True
            for _ in range(2):   # second pass resolves refs / TOC
                try:
                    proc = subprocess.run(cmd, cwd=tex_dir, capture_output=True, timeout=240)
                    log = (proc.stdout or b"").decode("utf-8", "replace")
                    ok = ok and proc.returncode == 0
                    errors = [l for l in log.splitlines() if l.startswith("!")][:10]
                except Exception as exc:
                    ok = False
                    errors = [f"{type(exc).__name__}: {exc}"]
                    break
            compile_info["ok"] = ok
            compile_info["errors"] = errors
            compile_info["pdf"] = os.path.exists(os.path.join(tex_dir, "main.pdf"))
            compile_info["passes"] = 2

    for b in d["blocks"][:6]:
        add_evidence(evidence, ev(b, "section source"))
    payload = {
        "files": ["main.tex", "latex/main.tex"] if out_dir else ["main.tex"],
        "tex": tex[:20000],
        "compile": compile_info,
        "formula_review": formula_review,
        "structure": [{"level": s["level"], "title": s["title"]} for s in d["sections"]],
        "environment": {"engine": compile_info.get("engine", "not found"),
                        "packages": ["booktabs", "amsmath", "amsfonts", "graphicx", "hyperref", "lmodern"]},
    }
    if compile_info.get("ok"):
        status, notes = "complete", []
    elif not compile_info.get("attempted"):
        status = "partial"
        notes = ["no TeX engine on this machine: source + static_check delivered, compile not verified"]
    else:
        status = "partial"
        notes = ["compile failed: see compile.errors; source kept as-is rather than deleting content"]
    if formula_review:
        notes.append(f"{len(formula_review)} formula(s) have low-confidence LaTeX (sub/superscripts "
                     f"need review); listed in formula_review[]")
    return payload, evidence, {"notes": notes, "missing": []}, status, [f"main.tex {len(tex)} chars"]


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
    # Every builder reads doc["document"]["..."].  When nothing was parsed there
    # is nothing to compose, and raising here would leave the caller with no
    # result.json at all -- the one outcome that is strictly worse than an
    # honest empty answer.  Say "nothing to work with" and return.
    if not doc.get("document"):
        problem = (doc.get("input") or {}).get("problem") or {}
        why = problem.get("detail") or "no document was parsed from the input"
        return ({}, [],
                {"notes": ["nothing to compose: no document was parsed"],
                 "missing": [], "inferred_fields": []},
                "unable", [f"composer skipped: {why}"])
    fn = MODES[mode]
    if mode == "latex":
        return fn(doc, case, task, out_dir=out_dir)
    return fn(doc, case, task)
