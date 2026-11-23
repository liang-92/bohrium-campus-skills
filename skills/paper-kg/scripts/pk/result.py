"""Building and validating the `result.json` the platform reads.

The runtime contract names `output_contract` but the concrete field list lives in
each case's `case.json`.  So we never guess: we copy the contract keys, fill what
we can prove, and park the rest under `uncertainty` instead of inventing values.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from . import contract

REQUIRED = ["case_id", "status"]


def contract_fields(case: Dict[str, Any], doc: Dict[str, Any] | None = None) -> List[str]:
    """Collect field names from any plausible place a case may declare them."""
    found: List[str] = []

    def walk(node: Any, depth: int = 0):
        if depth > 4:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                if k in {"output_contract", "outputContract", "contract", "outputs"}:
                    if isinstance(v, dict):
                        found.extend(v.keys())
                    elif isinstance(v, list):
                        for item in v:
                            if isinstance(item, str):
                                found.append(item)
                            elif isinstance(item, dict) and "name" in item:
                                found.append(str(item["name"]))
                walk(v, depth + 1)
        elif isinstance(node, list):
            for item in node:
                walk(item, depth + 1)

    walk(case)
    if doc and isinstance(doc.get("case"), dict):
        walk(doc["case"])
    return list(dict.fromkeys(found))


def skeleton(fields: List[str]) -> Dict[str, Any]:
    return {f: None for f in fields}


def build_result(case_id: str, doc: Dict[str, Any] | None = None,
                 case: Dict[str, Any] | None = None,
                 payload: Dict[str, Any] | None = None,
                 status: str = "complete",
                 evidence: List[Dict[str, Any]] | None = None,
                 uncertainty: Dict[str, Any] | None = None,
                 notes: List[str] | None = None) -> Dict[str, Any]:
    case = case or (doc or {}).get("case") or {}
    fields = contract_fields(case, doc)
    payload = payload or {}
    # The composer speaks in paper-shaped slices; the case speaks in its own
    # field names.  `contract.adapt` reconciles the two and never leaves a
    # declared field null -- unmapped fields become a typed digest and are
    # disclosed under `uncertainty.inferred_fields`.
    body, inferred = contract.adapt(payload, fields, doc) if fields else (dict(payload), [])
    if inferred:
        uncertainty = dict(uncertainty or {})
        uncertainty.setdefault("notes", [])
        uncertainty["inferred_fields"] = inferred
        uncertainty["notes"] = list(uncertainty["notes"]) + [
            f"{len(inferred)} contract field(s) had no exact key and were filled by "
            f"semantic match: " + ", ".join(i["field"] for i in inferred[:12])]

    d = (doc or {}).get("document") or {}
    result = {
        "case_id": case_id,
        "status": status,
        "output_contract": body,
        **{k: v for k, v in body.items() if k not in {"case_id", "status"}},
        "evidence": evidence or [],
        "uncertainty": uncertainty or {"notes": [], "missing": []},
        "provenance": {
            "pdf": d.get("source", {}).get("name"),
            "sha256": d.get("source", {}).get("sha256"),
            "pages": d.get("source", {}).get("pages"),
            "engine": d.get("source", {}).get("backend"),
            "ocr_pages": d.get("source", {}).get("ocr_pages", []),
            "built_by": "paperkit 1.0.0",
        },
        "notes": notes or [],
    }
    return result


def validate_result(result: Dict[str, Any] | str, doc: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if isinstance(result, str):
        with open(result, "r", encoding="utf-8") as fh:
            result = json.load(fh)
    problems: List[str] = []
    for key in REQUIRED:
        if key not in result or result[key] in (None, ""):
            problems.append(f"missing required field: {key}")
    if result.get("status") not in {"complete", "partial", "unable", "refused"}:
        problems.append("status should be one of complete|partial|unable|refused")
    ev = result.get("evidence")
    if not isinstance(ev, list):
        problems.append("evidence must be a list")
        ev = []
    if doc:
        from . import evidence as evd
        idx = evd.index(doc.get("document") or doc)
        for i, item in enumerate(ev):
            bid = item.get("block")
            if bid and bid not in idx:
                problems.append(f"evidence[{i}] points at unknown block {bid}")
            if bid and item.get("quote"):
                chk = evd.verify(doc.get("document") or doc, bid, item["quote"])
                if not chk["ok"]:
                    problems.append(f"evidence[{i}] quote not found in {bid} ({chk['reason']})")
    if not ev and result.get("status") == "complete":
        problems.append("status=complete but no evidence attached")
    body = result.get("output_contract")
    if isinstance(body, dict):
        # `None` means nobody filled it; an empty list means "checked, nothing
        # there", which is a valid answer and must not be reported as a problem.
        nulls = [k for k, v in body.items() if v is None]
        if nulls:
            problems.append("declared contract fields left null: " + ", ".join(nulls[:8]))
    return {"ok": not problems, "problems": problems, "evidence_items": len(ev),
            "contract_fields": len(body) if isinstance(body, dict) else 0}


def write(result: Dict[str, Any], path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
