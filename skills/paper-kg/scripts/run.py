"""Shared runtime for every weekly-skill in this repo.

`run.py` does the deterministic 90% so the agent can spend its request budget on
judgement instead of plumbing:

    python3 scripts/run.py --input /input --out /app/output

It writes, under the output directory:

    doc.json        full parsed document (blocks + ids + tables + sections)
    doc.md          human/agent readable rendering with [pNN-bNNN] anchors
    coverage.json   what was found / what is missing on this PDF
    result.json     the case's `output_contract` shape + evidence + status
    run.log         environment, timings, engine choices, warnings

Profiles live next to this file as `compose_<slug>.py` and expose
`build(doc, case, task) -> (payload, evidence, uncertainty, status, notes)`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pk import document as pk_doc          # noqa: E402
from pk import evidence as pk_ev           # noqa: E402
from pk import result as pk_result         # noqa: E402
import compose_all                          # noqa: E402


def _case_id(case: Dict[str, Any], doc: Dict[str, Any], fallback: str) -> str:
    for key in ("case_id", "id", "caseId", "task_id"):
        if isinstance(case, dict) and case.get(key):
            return str(case[key])
    return fallback


def _default_profile() -> str:
    """The package decides its own profile; --profile still wins."""
    p = os.path.join(HERE, "profile.txt")
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as fh:
            val = fh.read().strip()
        if val:
            return val
    return os.environ.get("SKILL_PROFILE", "parse")


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="run a weekly-skill on one case")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--profile", default=_default_profile())
    ap.add_argument("--no-ocr", action="store_true")
    ap.add_argument("--max-blocks", type=int, default=1200)
    args = ap.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    t0 = time.time()
    log: List[str] = []

    def say(msg: str) -> None:
        log.append(f"[{time.time() - t0:6.1f}s] {msg}")
        print(msg, file=sys.stderr)

    say(f"profile={args.profile} input={args.input} out={args.out}")
    doc = pk_doc.analyze(args.input, ocr=not args.no_ocr)
    d = doc.get("document") or {}
    say(f"parsed {d.get('source', {}).get('pages')} pages with {d.get('source', {}).get('backend')}")
    if d:
        say(f"blocks={len(d.get('blocks', []))} tables={len(d.get('tables', []))} "
            f"formulas={len(d.get('formulas', []))} refs={len(d.get('references', []))}")

    with open(os.path.join(args.out, "doc.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(args.out, "doc.md"), "w", encoding="utf-8") as fh:
        fh.write(pk_doc.to_markdown(doc, max_blocks=args.max_blocks))
    with open(os.path.join(args.out, "coverage.json"), "w", encoding="utf-8") as fh:
        json.dump({"quality": doc.get("quality", {}),
                   "page_stats": d.get("page_stats", []),
                   "removed_running_heads": doc.get("document", {}).get("running_heads_removed"),
                   "files": doc.get("files", []),
                   "materials": {k: v["chars"] for k, v in (doc.get("materials") or {}).items()}},
                  fh, ensure_ascii=False, indent=1)

    status, payload, evidence, uncertainty, notes = "partial", {}, [], {"notes": [], "missing": []}, []
    try:
        payload, evidence, uncertainty, status, notes = compose_all.build(
            args.profile, doc, doc.get("case") or {}, doc.get("task") or "", out_dir=args.out)
        say(f"compose ok: status={status} payload_keys={list(payload)[:8]} evidence={len(evidence)}")
    except Exception as exc:
        status = "partial"
        notes.append(f"composer failed: {type(exc).__name__}: {exc}")
        uncertainty["notes"].append("Composer raised; only the parsed document is available.")
        log.append(traceback.format_exc())
        say(f"composer error: {exc}")

    case_id = _case_id(doc.get("case") or {}, doc, os.path.basename(os.path.abspath(args.input)))
    res = pk_result.build_result(case_id=case_id, doc=doc, case=doc.get("case") or {},
                                 payload=payload, status=status,
                                 evidence=evidence, uncertainty=uncertainty, notes=notes)
    res["run"] = {"profile": args.profile, "seconds": round(time.time() - t0, 1),
                  "blocks": len(d.get("blocks", [])), "tables": len(d.get("tables", [])),
                  "formulas": len(d.get("formulas", [])), "references": len(d.get("references", []))}
    pk_result.write(res, os.path.join(args.out, "result.json"))

    check = pk_result.validate_result(res, doc)
    with open(os.path.join(args.out, "run.log"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(log + [json.dumps(check, ensure_ascii=False)]))
    print(json.dumps({"ok": True, "result": os.path.join(args.out, "result.json"),
                      "status": status, "validate": check,
                      "seconds": res["run"]["seconds"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
