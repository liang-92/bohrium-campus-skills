"""Map a case's declared `output_contract` keys onto what we actually computed.

Why this exists
---------------
Each challenge ships its own `case.json` with an `output_contract` object, and the
checker only looks at *those* keys.  Our composers name their slices after the
shape of a paper (`structure`, `content`, `tables`, ...), which will not always
line up with the vocabulary a particular challenge author picked
(`sections`, `paragraphs`, `figures_and_tables`, `references_list`, ...).

A literal `payload.get(field)` therefore produces `null` for every near-miss,
which reads to a reviewer as "the skill produced nothing".  This module bridges
the two vocabularies deterministically:

1. exact key in the composer payload -> use it;
2. exact key in the standard slice bag -> use that slice;
3. keyword match on the field name (English + Chinese) -> use the best slice;
4. nothing matches -> emit a *typed* digest of the document (list for plural
   names, object for singular ones) and record the inference in `uncertainty`,
   so the field is never empty and never silently invented.

No model calls, no randomness: same inputs -> same mapping.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

# Slice name -> field-name tokens that should claim it.  Order matters: the first
# slice whose tokens appear in the field name wins, so the more specific
# vocabularies (table/figure/formula) are listed before the generic text ones.
SLICE_TOKENS: List[Tuple[str, Tuple[str, ...]]] = [
    ("references", ("reference", "bibliograph", "citation", "cited", "参考文献", "文献表", "引用")),
    ("formulas", ("formula", "equation", "math", "公式", "方程")),
    ("tables", ("table", "tabular", "表格", "参数表")),
    ("figures", ("figure", "image", "diagram", "图", "配图")),
    ("entities", ("entit", "node", "concept", "实体", "节点", "概念")),
    ("relations", ("relation", "edge", "triple", "关系", "三元组")),
    ("assertions", ("assertion", "claim", "nanopub", "断言", "主张")),
    ("segments", ("segment", "sentence", "pair", "bilingual", "段落", "句", "对照")),
    ("glossary", ("glossar", "terminolog", "term", "术语", "词表")),
    ("issues", ("issue", "problem", "error", "suggestion", "问题", "建议", "错误")),
    ("structure", ("section", "chapter", "outline", "heading", "toc", "章节", "结构", "目录", "标题")),
    ("blocks", ("block", "paragraph", "content", "body", "text", "段落", "正文", "内容", "全文")),
    ("quality", ("quality", "coverage", "stat", "metric", "count", "覆盖", "质量", "统计")),
    ("meta", ("meta", "title", "author", "abstract", "doi", "keyword", "题目", "作者", "摘要", "元数据")),
]

# Field names that sound plural should receive a list even on the fallback path.
LISTISH = re.compile(
    r"(s$|_list$|list$|items?$|entries$|pairs?$|rows?$|records?$|数组|列表|清单|明细)", re.I)


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", str(name).strip().lower()).strip("_")


def _slice_bag(doc: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """Standard slices, preferring the composer's own version when it has one."""
    d = (doc or {}).get("document") or doc or {}
    bag = {
        "meta": {
            "title": (d.get("meta") or {}).get("title", ""),
            "authors": (d.get("meta") or {}).get("authors", []),
            "abstract": (d.get("meta") or {}).get("abstract", ""),
            "keywords": (d.get("meta") or {}).get("keywords", []),
            "doi": (d.get("meta") or {}).get("doi", ""),
        },
        "structure": [{"level": s.get("level"), "title": s.get("title"),
                       "page": s.get("page"), "block": s.get("block")}
                      for s in d.get("sections", [])],
        "blocks": [{"id": b.get("id"), "page": b.get("page"), "column": b.get("column"),
                    "section": b.get("section_path") or b.get("section"),
                    "type": b.get("type"), "text": b.get("text")}
                   for b in d.get("blocks", [])],
        "tables": d.get("tables", []),
        "figures": d.get("figures", []),
        "formulas": d.get("formulas", []),
        "references": d.get("references", []),
        "quality": (doc or {}).get("quality", {}) or d.get("quality", {}),
        "page_stats": d.get("page_stats", []),
    }
    for key, value in (payload or {}).items():
        if value not in (None, "", [], {}):
            bag[key] = value
    return bag


def _digest(doc: Dict[str, Any], as_list: bool) -> Any:
    """Last resort: a typed, honest view of the document instead of null."""
    d = (doc or {}).get("document") or doc or {}
    blocks = d.get("blocks", [])
    if as_list:
        return [{"id": b.get("id"), "page": b.get("page"),
                 "section": b.get("section_path") or b.get("section"),
                 "text": (b.get("text") or "")[:400]} for b in blocks[:80]]
    return {
        "title": (d.get("meta") or {}).get("title", ""),
        "sections": [s.get("title") for s in d.get("sections", [])][:40],
        "block_count": len(blocks),
        "page_count": (d.get("source") or {}).get("pages"),
        "note": "no exact contract key matched; this is the document digest — "
                "see doc.json / doc.md for the full structure",
    }


def match(field: str, bag: Dict[str, Any]) -> Tuple[Any, str]:
    """Return (value, how) for one declared field name."""
    key = _norm(field)
    if key in bag:
        return bag[key], "exact"
    for slice_name, tokens in SLICE_TOKENS:
        if any(t in key for t in tokens):
            if slice_name in bag:
                return bag[slice_name], f"keyword:{slice_name}"
            break
    # common singular/plural flattening: `sections` -> `section`
    for cand in (key.rstrip("s"), key + "s"):
        if cand in bag:
            return bag[cand], "plural"
    return None, "none"


def adapt(payload: Dict[str, Any], fields: List[str], doc: Dict[str, Any],
          keep_inferred: bool = True) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    """Fill every declared field.

    Returns the filled body plus a list of `{"field", "how"}` records so the
    caller can disclose inferred fields in `uncertainty` (never hide a guess).
    """
    bag = _slice_bag(doc, payload)
    body: Dict[str, Any] = {}
    inferred: List[Dict[str, str]] = []

    for field in fields:
        if payload and payload.get(field) not in (None, "", [], {}):
            body[field] = payload[field]
            continue
        value, how = match(field, bag)
        if how == "none" or value is None:
            value, how = _digest(doc, bool(LISTISH.search(str(field)))), "digest"
        body[field] = value
        # An empty slice is *honest*: the paper really had no tables/figures.
        # Only unmatched names get a digest; substituting unrelated blocks for
        # a name like `figures` would read as fabricated content.
        if how != "exact" and value not in (None, "", [], {}):
            inferred.append({"field": field, "how": how})

    # composer keys the contract never asked for are still useful to a reviewer
    if keep_inferred:
        for k, v in (payload or {}).items():
            if k not in body and v not in (None, "", [], {}):
                body[k] = v
    return body, inferred
