"""Fill the case's declared `output_contract` — verbatim keys, declared types.

Why this exists
---------------
The runtime contract says `result.json` must carry *all original
`output_contract` fields*.  The case author writes those fields, we do not, so
the only correct behaviour is:

* the key is what the case declared, character for character, never renamed;
* the value conforms to what the case declared (`list` -> array, `object` ->
  object, `complete|partial|unable` -> one of those three strings);
* a field nothing in this skill can answer stays under its own key and is
  *visibly* unanswered — `{"value": …, "method": "unsupported",
  "confidence": 0}` — instead of being dropped or quietly replaced by unrelated
  text.

Contract shapes seen in the wild, all normalised to one `Field`:

    {"tables": "list"}                                # description string
    {"tables": {"type": "array", "items": {...}}}     # JSON-schema-ish
    {"sections": ["a", "b"]}                          # example value
    [{"name": "tables", "type": "array", ...}]        # list of objects
    null                                              # no contract at all

Routing uses the *contract's own* words — the declared description and the
declared type decide which published slice may answer.  The one piece of
vocabulary involved is a table of ordinary document nouns
(`equations` -> `formulas`, `citations` -> `references`, `full_text` ->
`blocks`); it is generic to papers rather than specific to a challenge, and
whichever rule fired is printed in `field_status[field].method` so the mapping
is auditable instead of invisible.

No model calls, no randomness: same inputs -> same mapping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional, Tuple

ARRAY, OBJECT, STRING, NUMBER, BOOLEAN, UNKNOWN = (
    "array", "object", "string", "number", "boolean", "unknown")

# Keywords a case author may use inside the contract key itself.
CONTRACT_KEYS = {"output_contract", "outputContract", "output_schema",
                 "outputs", "contract", "expected_output"}


# --------------------------------------------------------------------------- #
# 1. read the contract
# --------------------------------------------------------------------------- #
@dataclass
class Field:
    name: str
    kind: str = UNKNOWN
    description: str = ""
    enum: List[str] = dc_field(default_factory=list)
    items: Optional[Dict[str, Any]] = None
    example: Any = None


def _has(text: str, *words: str) -> bool:
    """Whole-word (or CJK-substring) test, so `str` does not match `abstract`."""
    for w in words:
        if re.fullmatch(r"[a-z0-9 ]+", w):
            if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", text):
                return True
        elif w in text:
            return True
    return False


def _kind_of_text(text: str) -> str:
    t = (text or "").strip().lower()
    if not t:
        return UNKNOWN
    if "|" in t and len([p for p in t.split("|") if p.strip()]) >= 2:
        return STRING          # an enumeration of strings: complete|partial|unable
    if _has(t, "list", "array", "[", "数组", "列表"):
        return ARRAY
    if _has(t, "object", "dict", "map", "json", "结构", "report"):
        return OBJECT
    if _has(t, "bool", "boolean"):
        return BOOLEAN
    if _has(t, "int", "integer", "number", "float", "count", "score", "数量", "个数"):
        return NUMBER
    if "/" in t:
        return OBJECT          # "title/authors/abstract"
    if _has(t, "string", "text", "str", "name", "字符串", "全文"):
        return STRING
    if "structure" in t:
        return OBJECT
    return UNKNOWN


def _field_from(name: str, spec: Any) -> Field:
    f = Field(name=str(name))
    if isinstance(spec, str):
        f.description = spec
        f.kind = _kind_of_text(spec)
        if "|" in spec:
            f.enum = [p.strip() for p in spec.split("|") if p.strip()]
        return f
    if isinstance(spec, dict):
        f.kind = str(spec.get("type") or "").lower() or _kind_of_text(
            " ".join(str(spec.get(k, "")) for k in ("description", "title", "doc")))
        m = {"list": ARRAY, "array": ARRAY, "object": OBJECT, "dict": OBJECT,
             "string": STRING, "str": STRING, "number": NUMBER, "integer": NUMBER,
             "float": NUMBER, "boolean": BOOLEAN, "bool": BOOLEAN}
        f.kind = m.get(f.kind, f.kind if f.kind in
                       {ARRAY, OBJECT, STRING, NUMBER, BOOLEAN} else UNKNOWN)
        f.description = str(spec.get("description") or spec.get("title") or "")
        f.items = spec.get("items") if isinstance(spec.get("items"), dict) else None
        f.example = spec.get("example", spec.get("examples"))
        if isinstance(spec.get("enum"), list):
            f.enum = [str(x) for x in spec["enum"]]
        if f.kind == ARRAY and f.items:
            it = str(f.items.get("type") or "")
            f.description = (f.description + " items:" + it).strip()
        return f
    if isinstance(spec, list):
        f.kind = ARRAY
        f.example = spec
        if spec and isinstance(spec[0], dict):
            f.items = spec[0]
        return f
    return f


def spec(case: Dict[str, Any], doc: Dict[str, Any] | None = None) -> List[Field]:
    """Every field the case declares, in declaration order."""
    out: Dict[str, Field] = {}

    def walk(node: Any, depth: int = 0):
        if depth > 5 or node is None:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                if k in CONTRACT_KEYS:
                    if isinstance(v, dict):
                        for fname, fspec in v.items():
                            if not isinstance(fname, str):
                                continue
                            prev = out.get(fname)
                            cand = _field_from(fname, fspec)
                            # keep the richer of two declarations of one name
                            if prev is None or (prev.kind == UNKNOWN
                                                and cand.kind != UNKNOWN):
                                out[fname] = cand
                    elif isinstance(v, list):
                        for item in v:
                            if isinstance(item, str):
                                out.setdefault(item, _field_from(item, ""))
                            elif isinstance(item, dict) and item.get("name"):
                                out[str(item["name"])] = _field_from(
                                    str(item["name"]), item)
                walk(v, depth + 1)
        elif isinstance(node, list):
            for item in node:
                walk(item, depth + 1)

    walk(case or {})
    if doc and isinstance(doc, dict):
        walk(doc.get("case") if isinstance(doc.get("case"), dict) else None)
    return list(out.values())


def names(fields: List[Field]) -> List[str]:
    return [f.name for f in fields]


# --------------------------------------------------------------------------- #
# 2. our own slices, keyed by the nouns a paper is made of
# --------------------------------------------------------------------------- #
ALIASES: Dict[str, str] = {
    # front matter
    "metadata": "meta", "paper_metadata": "meta", "document_metadata": "meta",
    "meta": "meta", "front_matter": "meta", "frontmatter": "meta",
    "paper_info": "meta", "bibliographic_info": "meta",
    "title_authors_abstract": "meta", "header_info": "meta",
    # structure
    "structure": "structure", "document_structure": "structure",
    "full_structure": "structure", "sections": "structure",
    "section_list": "structure", "outline": "structure", "toc": "structure",
    "table_of_contents": "structure", "headings": "structure", "chapters": "structure",
    # body text
    "blocks": "blocks", "block_list": "blocks", "content_blocks": "blocks",
    "full_text": "blocks", "fulltext": "blocks", "full_text_blocks": "blocks",
    "body_text": "blocks", "body_blocks": "blocks", "text_blocks": "blocks",
    "plain_text": "blocks", "body": "blocks", "paragraphs": "blocks",
    # tables / figures / formulas
    "tables": "tables", "table_list": "tables", "table_blocks": "tables",
    "figures": "figures", "figure_list": "figures", "images": "figures",
    "illustrations": "figures", "charts": "figures",
    "formulas": "formulas", "formula_list": "formulas", "equations": "formulas",
    "equation_list": "formulas", "math": "formulas", "maths": "formulas",
    # references
    "references": "references", "reference_list": "references", "refs": "references",
    "citations": "references", "citation_list": "references",
    "bibliography": "references", "cited_works": "references",
    "works_cited": "references",
    # quality / coverage
    "quality": "quality", "coverage": "quality", "coverage_report": "quality",
    "quality_report": "quality", "metrics": "quality", "audit": "quality",
    # pages
    "pages": "page_map", "page_map": "page_map", "page_stats": "page_map",
    # proof
    "evidence": "evidence", "evidences": "evidence", "anchors": "evidence",
    "evidence_anchors": "evidence", "evidence_list": "evidence",
    # run state
    "status": "status", "run_status": "status", "result_status": "status",
    # lossless layer
    "verbatim": "verbatim", "raw_text": "verbatim", "text_layer": "verbatim",
}

# Second chance: read the declared *description* (not the name) for a noun.
# Deliberately short — only nouns that name a slice we actually produce.
DESC_HINTS: List[Tuple[str, Tuple[str, ...]]] = [
    ("tables", ("table", "表格")),
    ("figures", ("figure", "image", "插图", "配图")),
    ("formulas", ("equation", "formula", "公式")),
    ("references", ("citation", "reference", "文献")),
    ("meta", ("title", "author", "abstract", "标题", "作者", "摘要")),
    ("structure", ("structure", "section", "heading", "章节", "大纲")),
    ("evidence", ("anchor", "evidence", "证据", "定位")),
    ("quality", ("coverage", "quality", "覆盖")),
    ("blocks", ("full text", "text block", "body text", "正文", "全文")),
]

LISTISH = re.compile(r"(s$|_list$|list$|items?$|entries$|pairs?$|rows?$|records?$"
                     r"|数组|列表|清单|明细)", re.I)

# Third chance, for fields that name a *task output* rather than a paper part:
# whatever the profile produced as its findings can stand in, at low confidence
# and with the substitution printed in `field_status`.
FALLBACK_CHAINS: Dict[str, Tuple[str, ...]] = {
    "answers": ("knowledge_items", "section_notes", "assertions", "qa"),
    "answer": ("knowledge_items", "section_notes", "assertions", "qa"),
    "qa": ("knowledge_items", "questions", "section_notes"),
    "questions": ("knowledge_items", "section_notes"),
    "summary": ("section_notes", "abstract", "paper_card"),
    "findings": ("knowledge_items", "assertions", "sentence_issues"),
    "translation": ("segments",),
    "translated_text": ("segments",),
    "rewrites": ("sentence_issues", "edit_record_schema"),
}


def _chain(key: str) -> Tuple[str, ...]:
    if key in FALLBACK_CHAINS:
        return FALLBACK_CHAINS[key]
    for stem, chain in FALLBACK_CHAINS.items():
        if key.startswith(stem):
            return chain
    return ()


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", str(name).strip().lower()).strip("_")


def _empty(kind: str) -> Any:
    return {"array": [], "object": {}, "string": "", "number": 0,
            "boolean": False}.get(kind)


def _bag(payload: Dict[str, Any], doc: Dict[str, Any],
         evidence: List[Dict[str, Any]] | None, status: str | None) -> Dict[str, Any]:
    """Every slice this skill produces, under its own name."""
    d = (doc or {}).get("document") or doc or {}
    meta = d.get("meta") or {}
    content = payload.get("content") if isinstance(payload.get("content"), dict) else {}
    body_blocks = content.get("blocks")
    if not body_blocks:
        body_blocks = [{"id": b.get("id"), "page": b.get("page"),
                        "column": b.get("column"),
                        "section": b.get("section_path") or b.get("section"),
                        "type": b.get("type"), "text": b.get("text")}
                       for b in d.get("blocks", [])]
    bag: Dict[str, Any] = {
        "meta": {"title": meta.get("title", ""), "authors": meta.get("authors", []),
                 "abstract": meta.get("abstract", ""),
                 "keywords": meta.get("keywords", []), "doi": meta.get("doi", "")},
        "structure": [{"level": s.get("level"), "title": s.get("title"),
                       "page": s.get("page"), "block": s.get("block")}
                      for s in d.get("sections", [])],
        "blocks": body_blocks,
        "tables": content.get("tables") or d.get("tables", []),
        "figures": content.get("figures") or d.get("figures", []),
        "formulas": content.get("formulas") or d.get("formulas", []),
        "references": content.get("references") or d.get("references", []),
        "quality": payload.get("coverage") or (doc or {}).get("quality") or d.get("quality", {}),
        "page_map": d.get("page_stats", []),
        "evidence": evidence or [],
        "status": status,
        "document": payload.get("document") if isinstance(payload.get("document"), dict) else None,
    }
    # a slice the composer names itself always wins over our derived version
    for k, v in (payload or {}).items():
        if v not in (None, "", [], {}):
            bag[k] = v
    if bag.get("document") is None:
        bag["document"] = {
            "title": meta.get("title", ""), "authors": meta.get("authors", []),
            "abstract": meta.get("abstract", ""),
            "pages": (d.get("source") or {}).get("pages"),
            "sections": [s.get("title") for s in d.get("sections", [])],
            "block_count": len(d.get("blocks", [])),
        }
    return bag


# --------------------------------------------------------------------------- #
# 3. resolve one field
# --------------------------------------------------------------------------- #
@dataclass
class Resolution:
    value: Any
    method: str
    confidence: float
    type_ok: bool = True


def _coerce(value: Any, kind: str) -> Tuple[Any, bool]:
    """Make `value` look like the declared type where that is lossless."""
    if kind == UNKNOWN or value is None:
        return value, True
    if kind == ARRAY:
        if isinstance(value, list):
            return value, True
        if isinstance(value, dict) and value:
            return list(value.values()), True      # a map of items is a list of them
        return value, False
    if kind == OBJECT:
        if isinstance(value, dict):
            return value, True
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return {"items": value, "count": len(value)}, True
        return value, False
    if kind == STRING:
        if isinstance(value, str):
            return value, True
        if isinstance(value, (int, float, bool)):
            return str(value), True
        return value, False
    if kind == NUMBER:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value, True
        return value, False
    if kind == BOOLEAN:
        if isinstance(value, bool):
            return value, True
        return value, False
    return value, True


def _unsupported(f: Field, why: str) -> Any:
    """Answered by nobody: keep the key, say so, stay type-correct."""
    out: Dict[str, Any] = {"value": _empty(f.kind), "method": "unsupported",
                           "confidence": 0, "declared_type": f.kind}
    if why:
        out["note"] = why
    return out


def _is_empty(value: Any, depth: int = 0) -> bool:
    """An answer with no content -- distinct from an answer we could not route.

    A shaped-but-blank object (`{"title": "", "authors": []}`) counts as empty:
    the keys are placeholders, not findings.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple)):
        return not value
    if isinstance(value, dict):
        if not value:
            return True
        return depth < 3 and all(_is_empty(v, depth + 1) for v in value.values())
    return False


def resolve(f: Field, bag: Dict[str, Any], payload: Dict[str, Any]) -> Resolution:
    key = _norm(f.name)

    # (a) the composer named this field itself
    if payload and payload.get(f.name) not in (None, "", [], {}):
        v, ok = _coerce(payload[f.name], f.kind)
        return Resolution(v, "exact", 1.0, ok)

    # (b) one of our standard slices carries exactly this name
    if key in bag and bag[key] is not None:
        v, ok = _coerce(bag[key], f.kind)
        return Resolution(v, "slice", 0.95, ok)

    # (c) ordinary document noun -> slice
    target = ALIASES.get(key)
    if target and bag.get(target) is not None:
        v, ok = _coerce(bag[target], f.kind)
        return Resolution(v, f"alias:{target}", 0.9, ok)

    # (d) the declared description names a noun we produce
    desc = (f.description or "").lower()
    for slice_name, tokens in DESC_HINTS:
        if any(t in desc for t in tokens) and bag.get(slice_name) is not None:
            v, ok = _coerce(bag[slice_name], f.kind)
            return Resolution(v, f"description:{slice_name}", 0.7, ok)

    # (e) a task-output field the profile answers with its own findings
    for slice_name in _chain(key):
        if bag.get(slice_name) not in (None, "", [], {}):
            v, ok = _coerce(bag[slice_name], f.kind)
            return Resolution(v, f"fallback:{slice_name}", 0.5, ok)

    # (f) singular/plural flip on the composer's own keys
    for cand in (key.rstrip("s"), key + "s"):
        if payload.get(cand) not in (None, "", [], {}):
            v, ok = _coerce(payload[cand], f.kind)
            return Resolution(v, "plural", 0.8, ok)

    # (g) nothing: say so under the declared key
    return Resolution(_unsupported(
        f, "no slice of this skill answers this field; left empty on purpose "
           "instead of being filled with unrelated text"),
        "unsupported", 0.0, True)


# --------------------------------------------------------------------------- #
# 4. public entry point
# --------------------------------------------------------------------------- #
def adapt(payload: Dict[str, Any], fields: List[Field] | List[str],
          doc: Dict[str, Any], evidence: List[Dict[str, Any]] | None = None,
          status: str | None = None) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Return `(contract_body, field_status, leftover_payload)`.

    `contract_body` holds exactly the declared keys, in declaration order.
    `leftover_payload` is what the composer produced beyond the contract; the
    caller writes it next to `result.json` instead of padding the contract with
    keys nobody asked for.
    """
    if fields and isinstance(fields[0], str):
        fields = [_field_from(str(n), "") for n in fields]  # type: ignore[list-item]
    bag = _bag(payload or {}, doc or {}, evidence, status)
    body: Dict[str, Any] = {}
    status_map: Dict[str, Any] = {}
    used: List[str] = []
    # With nothing parsed, every field is empty by necessity, not by finding.
    # The routing (method) is still informative, but the confidence must not
    # read as "we checked and the paper really has no figures".
    no_doc = not (doc or {}).get("document")

    for f in fields:
        r = resolve(f, bag, payload or {})
        # `status` is special: the contract wants the run state, and `None`
        # would read as "nobody filled it".
        if r.method == "unsupported" and f.name in {"status", "run_status"} and status:
            r = Resolution(status, "runtime", 1.0, True)
        if f.enum and r.method != "unsupported":
            bad = not isinstance(r.value, str) or r.value not in f.enum
            if bad and status in f.enum:
                r = Resolution(status, r.method + "+enum", r.confidence, True)
        body[f.name] = r.value
        entry = {"method": r.method, "confidence": r.confidence,
                 "declared_type": f.kind}
        if _is_empty(r.value) and r.method != "unsupported":
            entry["empty"] = True
            if no_doc:
                entry["confidence"] = 0.0
                entry["why_empty"] = "no document was parsed from the input"
        if not r.type_ok:
            entry["type_mismatch"] = True
        if f.enum:
            entry["enum"] = f.enum
        status_map[f.name] = entry
        used.append(f.name)

    leftover = {k: v for k, v in (payload or {}).items()
                if k not in used and v not in (None, "", [], {})}
    return body, status_map, leftover
