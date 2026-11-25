"""Evidence anchors: stable block ids, quotations and human-readable locators.

An anchor is either one block (`p07-b012`) or a **span** of blocks joined by `+`
(`p11-b005+p11-b006`).  Spans are unavoidable: a reference entry, a caption or a
sentence routinely continues across a page break, and pretending otherwise would
mean either pointing at the wrong block or inventing a block id that resolves to
nothing.  Every anchor form must be resolvable and re-checkable, which is what
`verify` does.

`verify` is deliberately strict: a quote has to be a verbatim span of the text
the anchor names (after whitespace/case/ligature normalisation), with `…`
marking text elided *between* fragments and at either end.  A token-overlap
score was the earlier rule and it accepted `dog` -> `cat` edits at 0.89, i.e. it
answered "are these mostly the same words" when the question is "is this what
the paper says".
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple


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


SPAN = re.compile(r"\s*\+\s*")
# `…` marks text the quote deliberately left out.  Inside the quote it separates
# fragments that must each be verbatim; at either end it only marks truncation.
ELLIPSIS = re.compile(r"\s*(?:…|\.\.\.|⋯|\[\s*\.\.\.\s*\]|\[\s*…\s*\])\s*")


def components(block_id: str) -> List[str]:
    return [c for c in SPAN.split(str(block_id or "").strip()) if c]


def bare(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Accept either the run wrapper (`{"document": {...}}`) or the document.

    Both shapes reach this module depending on the caller, and silently reading
    `doc["blocks"]` off the wrapper returns nothing -- every anchor then looks
    unknown, which is the one failure mode a verifier must never have.
    """
    d = (doc or {}).get("document")
    return d if isinstance(d, dict) else (doc or {})


def index(doc: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    doc = bare(doc)
    idx = {}
    for b in doc.get("blocks", []):
        idx[b["id"]] = b
    for t in doc.get("tables", []):
        if t.get("caption_block"):
            idx.setdefault(t["caption_block"], {"id": t["caption_block"], "page": t["page"],
                                                "text": t.get("caption", ""), "type": "table-caption"})
    return idx


def text_of(doc: Dict[str, Any], block_id: str,
            idx: Dict[str, Dict[str, Any]] | None = None) -> Tuple[str, List[str]]:
    """The text an anchor names, plus the components that do not exist.

    A span's text is the concatenation of its blocks in the order written, which
    is how a composer quoting a multi-block reference builds the quote.  Blocks
    already carry their own de-hyphenated, de-run-on text, so no extra cleaning
    happens here -- cleaning would create a second, different normalisation and
    a quote that verified against one but not the other.
    """
    idx = idx if idx is not None else index(doc)
    texts: List[str] = []
    missing: List[str] = []
    for c in components(block_id):
        b = idx.get(c)
        if b is None:
            missing.append(c)
        else:
            texts.append(b.get("text") or "")
    return " ".join(texts), missing


def fragments(text: str) -> List[str]:
    """Normalised pieces of a quote, split where the quote elides text."""
    return [f for f in (norm(x) for x in ELLIPSIS.split(text or "")) if f]


def verify(doc: Dict[str, Any], block_id: str, text: str) -> Dict[str, Any]:
    """Is *text* really a quote of *block_id*?

    Returns `{"ok", "reason", "anchor", ...}`.  The anchor is echoed back so a
    failure names the block that failed instead of a list index nobody can map.
    """
    idx = index(doc)
    comps = components(block_id)
    if not comps:
        return {"ok": False, "reason": "empty block id", "anchor": block_id}
    missing = [c for c in comps if c not in idx]
    if missing:
        return {"ok": False, "reason": "unknown block id: " + ", ".join(missing[:3]),
                "anchor": block_id, "missing_blocks": missing}
    hay, _ = text_of(doc, block_id, idx)
    hay = norm(hay)
    needle = norm(text)
    if not needle:
        return {"ok": True, "reason": "block exists", "anchor": block_id, "exact": False}
    if needle in hay:
        return {"ok": True, "reason": "verbatim span" if len(comps) > 1 else "verbatim substring",
                "anchor": block_id, "exact": True}
    parts = fragments(text)
    # A trailing `…` only marks truncation and leaves one fragment, so the test
    # has to be "does this quote elide anything", not "did the split produce
    # more than one piece".
    if parts and (len(parts) > 1 or ELLIPSIS.search(text or "")):
        # Ellipsis means "text omitted here", not "these words occur somewhere".
        # Match each fragment in order and after the previous one; otherwise a
        # reversed quotation, or two invented one-letter fragments, would pass.
        pos = 0
        for fragment in parts:
            found = hay.find(fragment, pos)
            if found < 0:
                return {"ok": False, "reason": "fragment not in the named block in quote order: "
                        + repr(fragment[:60]), "anchor": block_id}
            pos = found + len(fragment)
        return {"ok": True, "reason": f"verbatim across {len(parts)} ordered fragment(s)",
                "anchor": block_id, "exact": True}
    # Everything else is a paraphrase.  Report where it first diverges instead of
    # turning that into a similarity score that looks like a pass.
    return {"ok": False, "reason": "quote is not a verbatim span of the block"
            + _first_divergence(needle, hay), "anchor": block_id}


def _first_divergence(needle: str, hay: str) -> str:
    words = needle.split()
    for k in range(len(words), 0, -1):
        if " ".join(words[:k]) in hay:
            rest = " ".join(words[k:])
            if rest:
                return f" (matches the first {k} word(s), then diverges at {rest[:40]!r})"
            return ""
    return " (its first words do not appear)"



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


def cite(block: Dict[str, Any], max_chars: int = 240) -> Dict[str, Any]:
    return {"block": block["id"], "page": block["page"], "locator": locator(block),
            "quote": quote(block, max_chars)}


def span_cite(blocks: List[Dict[str, Any]], max_chars: int = 240) -> Dict[str, Any]:
    """Anchor for a passage that runs across several blocks (a page break, a
    reference entry, a caption continued below a table)."""
    ids = [b["id"] for b in blocks if b.get("id")]
    if not ids:
        return {}
    pages = sorted({b.get("page") for b in blocks if b.get("page")})
    text = re.sub(r"\s+", " ", " ".join(b.get("text") or "" for b in blocks)).strip()
    if len(text) > max_chars:
        cut = text[:max_chars]
        if " " in cut:
            cut = cut[: cut.rfind(" ")]
        text = cut + "…"
    where = "p" + "-p".join(str(p) for p in pages) if pages else "?"
    return {"block": "+".join(ids), "page": blocks[0].get("page"),
            "locator": f"{where} · {'+'.join(ids)}", "quote": text,
            "span": ids}



def table_anchor(table: Dict[str, Any]) -> Dict[str, Any]:
    return {"table": table["id"], "page": table["page"], "caption": table.get("caption", ""),
            "locator": f"p{table['page']} · {table['id']}"}


def collect_uncertainty(notes: List[str], missing: Optional[List[str]] = None) -> Dict[str, Any]:
    return {"notes": list(dict.fromkeys(notes)), "missing": list(dict.fromkeys(missing or []))}
