"""Command line entry point: `python -m paperkit.cli <command>`.

Commands are intentionally small and scriptable, because the agent that runs a
case has a limited request budget and should spend it on reading, not plumbing.

    analyze   case dir -> doc.json (+ doc.md)
    result    doc.json + payload -> result.json conforming to output_contract
    validate  check result.json against doc.json
    cite      quote text -> block id / page
    info      which PDF engines are importable
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

from . import document, evidence, result as result_mod, sources


def _load(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def cmd_analyze(args: argparse.Namespace) -> int:
    doc = document.analyze(args.input, ocr=not args.no_ocr)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    document.dump(doc, args.out)
    if args.md:
        with open(args.md, "w", encoding="utf-8") as fh:
            fh.write(document.to_markdown(doc, max_blocks=args.max_blocks))
    q = doc.get("quality", {})
    print(json.dumps({"ok": True, "out": args.out, "quality": q}, ensure_ascii=False, indent=2))
    return 0


def cmd_result(args: argparse.Namespace) -> int:
    doc = _load(args.doc)
    payload: Dict[str, Any] = {}
    if args.payload:
        payload = _load(args.payload)
    case_id = args.case_id or str((doc.get("case") or {}).get("case_id")
                                  or (doc.get("case") or {}).get("id")
                                  or os.path.basename(os.path.dirname(os.path.abspath(args.doc))))
    res, leftover = result_mod.build_result(
        case_id=case_id, doc=doc, payload=payload, status=args.status,
        evidence=payload.pop("evidence", []) if isinstance(payload, dict) else [],
        uncertainty=payload.pop("uncertainty", None) if isinstance(payload, dict) else None,
        notes=payload.pop("notes", []) if isinstance(payload, dict) else [])
    result_mod.write(res, args.out)
    if leftover:
        side = os.path.join(os.path.dirname(os.path.abspath(args.out)), "payload.json")
        with open(side, "w", encoding="utf-8") as fh:
            json.dump(leftover, fh, ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "out": args.out,
                      "fields": list(res["output_contract"].keys()),
                      "payload_sidecar": bool(leftover)},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    doc = _load(args.doc) if args.doc else None
    res = _load(args.result)
    report = result_mod.validate_result(res, doc, case=(doc or {}).get("case") or {})
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


def cmd_cite(args: argparse.Namespace) -> int:
    doc = _load(args.doc)
    hits = []
    if args.quote:
        hit = evidence.find_quote(doc.get("document") or doc, args.quote)
        if hit:
            hits.append(hit)
    if args.block:
        idx = evidence.index(doc.get("document") or doc)
        b = idx.get(args.block)
        if b:
            hits.append(evidence.cite(b))
    print(json.dumps({"hits": hits}, ensure_ascii=False, indent=2))
    return 0 if hits else 1


def cmd_info(_: argparse.Namespace) -> int:
    from . import backends
    print(json.dumps({
        "version": "1.0.0",
        "backends_available": backends.available_backends(),
        "python": sys.version.split()[0],
    }, ensure_ascii=False, indent=2))
    return 0


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="paperkit", description="PDF -> evidence-linked structure")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="analyse a case directory")
    a.add_argument("--input", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--md")
    a.add_argument("--max-blocks", type=int, default=400)
    a.add_argument("--no-ocr", action="store_true")
    a.set_defaults(func=cmd_analyze)

    r = sub.add_parser("result", help="build result.json")
    r.add_argument("--doc", required=True)
    r.add_argument("--payload")
    r.add_argument("--out", required=True)
    r.add_argument("--case-id")
    r.add_argument("--status", default="complete", choices=["complete", "partial", "unable", "refused"])
    r.set_defaults(func=cmd_result)

    v = sub.add_parser("validate", help="validate result.json")
    v.add_argument("--doc")
    v.add_argument("--result", required=True)
    v.set_defaults(func=cmd_validate)

    c = sub.add_parser("cite", help="locate a quote")
    c.add_argument("--doc", required=True)
    c.add_argument("--quote")
    c.add_argument("--block")
    c.set_defaults(func=cmd_cite)

    i = sub.add_parser("info", help="environment info")
    i.set_defaults(func=cmd_info)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
