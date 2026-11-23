"""Evidence anchors: stable block ids, quotations and human-readable locators."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("\u00ad", "").replace("\ufb01", "fi").replace("\ufb02", "fl")
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def locator(block: Dict[str, Any]) -> str:
    sec = block.get("section") or ""
    parts = [f"p{block['page']}", block["id"]]
    if sec:
        parts.append(sec.split(" > ")[-1])
    return " · ".join(parts)


def quote(block: Dict[str, Any], max_chars: int = 240) -> str:
    text = re.sub(r"\s+", " ", block.get("text", "")).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut + "…"


def index(doc: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    idx = {}
    for b in doc.get("blocks", []):
        idx[b["id"]] = b
    for t in doc.get("tables", []):
        if t.get("caption_block"):
            idx.setdefault(t["caption_block"], {"id": t["caption_block"], "page": t["page"],
                                                "text": t.get("caption", ""), "type": "table-caption"})
    return idx


def find_quote(doc: Dict[str, Any], text: str, min_overlap: float = 0.55) -> Dict[str, Any] | None:
    """Locate the block that best contains *text* (normalised, order-insensitive to spaces)."""
    needle = norm(text)
    if not needle:
        return None
    best, best_score = None, 0.0
    for b in doc.get("blocks", []):
        hay = norm(b.get("text", ""))
        if not hay:
            continue
        if needle in hay:
            score = 1.0 + min(len(needle) / max(1, len(hay)), 1.0)
        else:
            words = needle.split()
            if len(words) < 4:
                continue
            hit = sum(1 for w in words if w in hay)
            score = hit / len(words) * 0.9
        if score > best_score:
            best, best_score = b, score
    if best and best_score >= min_overlap:
        return {"block": best["id"], "page": best["page"], "score": round(best_score, 3),
                "quote": quote(best), "locator": locator(best)}
    return None


def verify(doc: Dict[str, Any], block_id: str, text: str) -> Dict[str, Any]:
    idx = index(doc)
    b = idx.get(block_id)
    if not b:
        return {"ok": False, "reason": "unknown block id"}
    hay, needle = norm(b.get("text", "")), norm(text)
    if not needle:
        return {"ok": True, "reason": "block exists"}
    if needle in hay:
        return {"ok": True, "reason": "exact substring"}
    words = needle.split()
    hit = sum(1 for w in words if w in hay)
    ratio = hit / max(1, len(words))
    return {"ok": ratio >= 0.8, "reason": f"token overlap {ratio:.2f}"}


def cite(block: Dict[str, Any], max_chars: int = 240) -> Dict[str, Any]:
    return {"block": block["id"], "page": block["page"], "locator": locator(block),
            "quote": quote(block, max_chars)}


def table_anchor(table: Dict[str, Any]) -> Dict[str, Any]:
    return {"table": table["id"], "page": table["page"], "caption": table.get("caption", ""),
            "locator": f"p{table['page']} · {table['id']}"}


def collect_uncertainty(notes: List[str], missing: Optional[List[str]] = None) -> Dict[str, Any]:
    return {"notes": list(dict.fromkeys(notes)), "missing": list(dict.fromkeys(missing or []))}
