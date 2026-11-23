"""Building and validating the `result.json` the platform reads.

The runtime contract names `output_contract` but the concrete field list lives in
each case's `case.json`.  So we never guess: we read the declared fields, keep
their names verbatim, fill what we can prove, and say plainly which ones nothing
in this skill answers — instead of inventing values or renaming keys.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple

from . import contract

REQUIRED = ["case_id", "status"]


def contract_fields(case: Dict[str, Any], doc: Dict[str, Any] | None = None) -> List[str]:
    """Declared field names, in declaration order (kept for callers that only
    want the names; `contract.spec` gives the full description/type)."""
    return contract.names(contract.spec(case, doc))


def skeleton(fields: List[str]) -> Dict[str, Any]:
    return {f: None for f in fields}


def build_result(case_id: str, doc: Dict[str, Any] | None = None,
                 case: Dict[str, Any] | None = None,
                 payload: Dict[str, Any] | None = None,
                 status: str = "complete",
                 evidence: List[Dict[str, Any]] | None = None,
                 uncertainty: Dict[str, Any] | None = None,
                 notes: List[str] | None = None
                 ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return `(result, leftover_payload)`.

    The second element is what the composer produced beyond the contract; it is
    written to `payload.json` by the caller so `output_contract` stays exactly
    as wide as the case asked for.
    """
    case = case or (doc or {}).get("case") or {}
    fields = contract.spec(case, doc)
    payload = payload or {}

    if fields:
        body, field_status, leftover = contract.adapt(
            payload, fields, doc or {}, evidence=evidence, status=status)
    else:
        # No declared contract: the composer's payload is the result.  An empty
        # `output_contract` here would look like a failed run.
        body, field_status, leftover = dict(payload), {}, {}

    inferred = [{"field": k, "how": v["method"]} for k, v in field_status.items()
                if v["method"] not in {"exact", "slice", "runtime"}]
    unsupported = [k for k, v in field_status.items() if v["method"] == "unsupported"]
    if inferred:
        uncertainty = dict(uncertainty or {})
        uncertainty.setdefault("notes", [])
        uncertainty["inferred_fields"] = inferred
        uncertainty["notes"] = list(uncertainty["notes"]) + [
            f"{len(inferred)} contract field(s) were routed by name/description "
            f"rather than an exact key: " + ", ".join(i["field"] for i in inferred[:12])]
    if unsupported:
        uncertainty = dict(uncertainty or {})
        uncertainty.setdefault("missing", [])
        uncertainty["missing"] = list(uncertainty["missing"]) + [
            f"output_contract.{k}: this skill produces nothing for it "
            f"(see field_status.{k})" for k in unsupported]

    d = (doc or {}).get("document") or {}
    result = {
        "case_id": case_id,
        "status": status,
        # The declared fields live in exactly one place, under their own names,
        # in the order the case declared them.
        "output_contract": body,
        "field_status": field_status,
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
    if not fields:
        result["notes"] = list(result["notes"]) + [
            "case.json declared no output_contract; the full composer payload is in "
            "output_contract and payload.json"]
    return result, leftover


def validate_result(result: Dict[str, Any] | str, doc: Dict[str, Any] | None = None,
                    case: Dict[str, Any] | None = None) -> Dict[str, Any]:
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
        if case:
            declared = contract.names(contract.spec(case, doc))
            missing = [k for k in declared if k not in body]
            if missing:
                problems.append("declared contract field(s) absent from result.json: "
                                + ", ".join(missing[:8]))
            renamed = [k for k in body if k not in declared]
            if declared and renamed:
                problems.append("output_contract carries undeclared key(s): "
                                + ", ".join(renamed[:8]))
    return {"ok": not problems, "problems": problems, "evidence_items": len(ev),
            "contract_fields": len(body) if isinstance(body, dict) else 0}


def write(result: Dict[str, Any], path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
