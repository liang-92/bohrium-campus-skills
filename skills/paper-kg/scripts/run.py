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
import re
import shutil
import sys
import time
import traceback
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pk import contract as pk_contract  # noqa: E402
from pk import deliver as pk_deliver    # noqa: E402
from pk import document as pk_doc          # noqa: E402
from pk import evidence as pk_ev           # noqa: E402
from pk import report as pk_report        # noqa: E402
from pk import result as pk_result         # noqa: E402
from pk import quality as pk_quality      # noqa: E402
import compose_all                          # noqa: E402

# Notes composers write when a field is a placeholder.  Once --fill supplies the
# text they are no longer true, and a stale "still empty" note next to a filled
# field is the kind of contradiction a reviewer catches first.
_STALE_EMPTY = re.compile(
    r"(intentionally empty|left empty|to be filled|awaiting|not yet translated)",
    re.IGNORECASE | re.UNICODE)


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


def _load_fill(explicit: str | None, out_dir: str, in_dir: str) -> tuple:
    """Find the agent's fill file: `--fill`, else fill.json next to the output/input."""
    cands = [explicit] if explicit else []
    cands += [os.path.join(out_dir, "fill.json"), os.path.join(in_dir, "fill.json")]
    for path in cands:
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    return data, path
            except Exception as exc:
                print(f"fill file ignored ({path}): {exc}", file=sys.stderr)
    return {}, ""


def _apply_fill(payload: Dict[str, Any], fill: Dict[str, Any]) -> Dict[str, Any]:
    """Merge text the agent wrote back into the payload.

    The scripts cannot translate or write prose; the agent can.  Without this,
    `segments[].translation` stays empty and `result.json` ships an empty
    deliverable -- the single biggest way a translation task loses points.
    Every applied value is counted, and `run.fill` records where it came from,
    so agent-written text is never mistaken for extracted text.
    """
    applied = 0
    segs = fill.get("segments") or {}
    # both shapes are documented: {"s0001": "译文"} and [{"seg": "s0001", "translation": "译文"}]
    if isinstance(segs, list):
        segs = {str(x.get("seg")): x.get("translation")
                for x in segs if isinstance(x, dict) and x.get("seg")}
    if segs and isinstance(payload.get("segments"), list):
        for s in payload["segments"]:
            value = segs.get(str(s.get("seg")))
            if isinstance(value, str) and value.strip():
                s["translation"] = value.strip()
                applied += 1
    gloss = {str(k).lower(): v for k, v in (fill.get("glossary") or {}).items()}
    if gloss and isinstance(payload.get("glossary"), list):
        for t in payload["glossary"]:
            value = gloss.get(str(t.get("term") or "").lower())
            if isinstance(value, str) and value.strip():
                t["zh"] = value.strip()
                applied += 1
    for key, value in (fill.get("replace") or {}).items():
        if value not in (None, "", [], {}):
            payload[key] = value
            applied += 1
    segs_all = payload.get("segments") or []
    left = sum(1 for s in segs_all if not (s.get("translation") or "").strip())
    return {"applied": applied, "segments": len(segs_all), "untranslated": left}


def gate_status(res: Dict[str, Any], status: str, doc: Dict[str, Any],
                case: Dict[str, Any]) -> tuple:
    """Should this result still be allowed to call itself `complete`?

    Returns `(ok, problems)`.  Kept separate from `main` so the rule can be
    tested on a doctored result without building a PDF that fails on purpose.
    """
    check = pk_result.validate_result(res, doc, case=case)
    return bool(check.get("ok")), check.get("problems", [])


DEFAULT_REQUIRED: Dict[str, List[str]] = {
    "parse": ["structure.md", "body.md", "refs.md", "page_map.csv"],
    "translate": ["bilingual_parallel.md", "terms_used.csv", "untranslated.csv"],
    "notes": ["section_summary.md", "outline.md", "notes.md", "cards.jsonl"],
    "nanopub": ["nanopubs.json", "decomposition.md"],
    "kg": ["entities.csv", "edges.csv", "type_summary.md", "graph.json",
           "clusters.json", "ambiguity.md"],
    "polish": ["revised.md", "changes.csv"],
    "refs": ["manuscript_cited.md", "citation_placement.csv", "references_gbt.md"],
    "intro": ["background.md", "related_work.md", "gap.md", "contributions.md",
              "intro_cited.md", "citation_map.csv"],
    "methods": ["methods.md", "params.csv", "repro_checklist.md", "materials_equipment.csv"],
    "latex": ["project/main.tex", "project/compile.log", "fix_report.md"],
}


def _infer_required(profile: str, task: str, doc: Dict[str, Any],
                    stage_required: List[str]) -> tuple:
    """Files named by the case, then by task.md, then the profile's own set.

    `required_files` is optional in the official contract.  Treating its absence
    as "no deliverables" was the single point of failure in the 12-case report:
    a flat contract lost every writing score even when the composer had the
    content.
    """
    if stage_required:
        return list(stage_required), "case.json.required_files"
    names: List[str] = []
    text = task or ""
    # Backticked names are the explicit ones; bare `output/xxx` forms are the
    # other common authoring style.
    for pat in (r"`([^`\n]+\.(?:md|csv|json|jsonl|bib|tex|log))`",
                r"(?<![/\w])((?:output/)?[A-Za-z0-9_.-]+\.(?:md|csv|json|jsonl|bib|tex|log))"):
        for m in re.finditer(pat, text, re.I):
            name = m.group(1).strip().lstrip("./")
            if name and name not in names:
                names.append(name)
    inputs = {os.path.basename(str(f.get("rel") or f.get("name") or ""))
              for f in (doc.get("files") or [])}
    inputs |= {str(f.get("rel") or "") for f in (doc.get("files") or [])}
    names = [n for n in names if os.path.basename(n) not in inputs
             and not n.startswith("input/") and n != "result.json"]
    if names:
        return names, "task.md filenames"
    fallback = DEFAULT_REQUIRED.get(profile, [])
    return list(fallback), f"default {profile} deliverable set"


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="run a weekly-skill on one case")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--profile", default=_default_profile())
    ap.add_argument("--no-ocr", action="store_true")
    ap.add_argument("--max-blocks", type=int, default=1200)
    ap.add_argument("--fill", help="json with the agent-written text to merge "
                                   "(default: fill.json in --out or --input)")
    ap.add_argument("--probe", action="store_true",
                    help="report which engines exist, then exit (no case needed)")
    args = ap.parse_args(argv)

    if args.probe:
        # Step 0 of the SKILL.md: know what is installed before promising quality.
        from pk import backends as pk_backends
        import importlib.util as _ilu
        info = {
            "engines": pk_backends.available_backends(),
            "ocr": {"tesseract": bool(_ilu.find_spec("pytesseract") or shutil.which("tesseract")),
                    "ocrmypdf": bool(shutil.which("ocrmypdf")),
                    "cli": bool(shutil.which("tesseract"))},
            "poppler": bool(shutil.which("pdftotext")),
            "python": sys.version.split()[0],
            "profile": args.profile,
            "note": "missing engines degrade quality; nothing is assumed to exist",
        }
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0

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

    # The verbatim layer is written as its own file: a reviewer can diff it
    # against the PDF text layer, and doc.json stays free of the duplicate.
    verbatim = d.pop("verbatim_text", "")
    # Keep the raw layer available to composers (KG quote audit) without
    # writing a duplicate field into doc.json.
    doc["verbatim_text"] = verbatim
    if verbatim:
        with open(os.path.join(args.out, "raw_text.txt"), "w",
                  encoding="utf-8", newline="\n") as fh:
            fh.write(verbatim)
        say(f"verbatim layer: {len(verbatim)} chars -> raw_text.txt")

    with open(os.path.join(args.out, "doc.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(args.out, "doc.md"), "w", encoding="utf-8") as fh:
        fh.write(pk_doc.to_markdown(doc, max_blocks=args.max_blocks))
    raw_total = sum(len(b.get("text_raw") or "") for b in d.get("blocks", []))
    with open(os.path.join(args.out, "coverage.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"quality": doc.get("quality") or {},
                   "page_stats": d.get("page_stats", []),
                   # `d` is already normalised from a possibly-null `document`:
                   # dict.get's default never fires for an explicit null.
                   "removed_running_heads": d.get("running_heads_removed"),
                   # rubric-named failure modes: each one is reported instead of
                   # being silently smoothed over
                   "page_order": d.get("page_order"),
                   "garbled_text_layer": d.get("garbled"),
                   "image_tables": d.get("image_tables"),
                   "figures_dropped": d.get("figures_dropped"),
                   "engine_attempts": (d.get("source") or {}).get("attempts"),
                   "verbatim": {"chars": d.get("verbatim_chars"),
                                "ratio": ((d.get("quality") or {}).get("verbatim") or {}).get("ratio"),
                                "missing": ((d.get("quality") or {}).get("verbatim") or {}).get("missing"),
                                "block_raw_chars": raw_total,
                                "raw_text_file": "raw_text.txt" if verbatim else None,
                                "note": "raw_text.txt is the engine text before cleaning; "
                                        "diff it against the PDF text layer to audit 逐字一致"},
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

    fill, fill_path = _load_fill(args.fill, args.out, args.input)
    fill_info: Dict[str, Any] = {"applied": 0, "segments": 0, "untranslated": 0}
    if fill:
        fill_info = _apply_fill(payload, fill)
        say(f"fill: {fill_info['applied']} value(s) merged from {fill_path}")
        if fill_info["applied"]:
            notes.append(f"{fill_info['applied']} field(s) carry agent-written text from "
                         f"{os.path.basename(fill_path)} (not extracted from the PDF)")
            # `complete` only when nothing is left blank: a half-filled
            # translation is still partial, and saying otherwise is a lie.
            if status == "partial" and fill_info["segments"] and \
                    not fill_info["untranslated"]:
                status = "complete"
                # The composer's note says the field is still empty; after a
                # complete fill that sentence is false, so it must go.
                uncertainty["notes"] = [n for n in uncertainty.get("notes", [])
                                        if not _STALE_EMPTY.search(n)]
                uncertainty["notes"].append(
                    "every field the composer left blank was filled from "
                    f"{os.path.basename(fill_path)}; the wording is the agent's, "
                    "not the PDF's")
            # Fill can also complete a prose draft (intro/methods) or a polish
            # payload.  The old code only upgraded translation segments, so a
            # fully written intro still shipped as partial.
            if status == "partial" and args.profile in {"intro", "methods"}:
                draft = (payload or {}).get("draft") or {}
                paras = draft.get("paragraphs") or []
                if paras and all((p.get("text") or "").strip() for p in paras):
                    status = "complete"
                    uncertainty["notes"] = [n for n in uncertainty.get("notes", [])
                                            if not _STALE_EMPTY.search(n)]
            if status == "partial" and args.profile == "polish":
                if (payload or {}).get("revised_text") and (payload or {}).get("rewrites"):
                    status = "complete"

    case_id = _case_id(doc.get("case") or {}, doc, os.path.basename(os.path.abspath(args.input)))
    stage = pk_contract.stage(doc.get("case") or {})
    required, required_source = _infer_required(
        args.profile, doc.get("task") or "", doc,
        list(stage["required_files"]) if stage else [])
    if required and not (stage and stage["required_files"]):
        uncertainty.setdefault("notes", []).append(
            f"deliverable list inferred from {required_source}; "
            "the case did not declare required_files")
    # An input we could not read at all is `unable`, not `partial`: partial would
    # suggest we read some of it.  The reason travels with the result.
    err = (d.get("source") or {}).get("error")
    if err and not d.get("blocks"):
        if err.get("kind") in {"encrypted", "unreadable", "empty"}:
            status = "unable"
        uncertainty.setdefault("notes", []).append(
            f"input could not be read: {err.get('kind')} — {err.get('detail')}")
        say(f"unreadable input: {err.get('kind')}")

    # Nothing to read at all: a mount pointing at the wrong path, a directory
    # with no PDF, an empty directory.  Same rule as above -- `unable`, never
    # `partial`, because partial would claim we read part of it.
    problem = (doc.get("input") or {}).get("problem")
    if problem and not d.get("blocks"):
        status = "unable"
        uncertainty.setdefault("notes", []).append(
            f"no document to read: {problem.get('kind')} — {problem.get('detail')}")
        say(f"no document: {problem.get('kind')} — {problem.get('detail')}")

    # A real PDF that yielded no text at all: a scan with no OCR engine, or a
    # file whose pages are blank.  Nothing was recovered, so `partial` would
    # overstate it -- `unable` plus the reason.  A `complete` from --fill is
    # left alone: the agent wrote that text, and it did not come from the PDF.
    if status == "partial" and not any(d.get(k) for k in ("blocks", "tables", "references")):
        ocr_missing = "ocr" in " ".join(log).lower()
        status = "unable"
        uncertainty.setdefault("notes", []).append(
            "nothing was extracted: the PDF has no usable text layer"
            + (" and no OCR engine is installed (--probe lists what is available)"
               if ocr_missing else ""))
        say("status=unable: zero blocks, zero tables, zero references")

    # Quantity is part of honesty: four blocks out of a scanned page is not a
    # complete parse, even though `status` from the composer said so.
    q = d.get("quality") or {}
    failed_pages = [p.get("page") for p in (d.get("page_stats") or [])
                    if p.get("ocr_failed")]
    text_engine = str((d.get("source") or {}).get("backend") or "").startswith("text")
    if status == "complete" and not text_engine:
        ocr_sections = len([b for b in (d.get("blocks") or [])
                            if (b.get("type") or "") == "heading"])
        ocr_ok = bool(d.get("blocks")) and ocr_sections >= 3 and \
            int((d.get("quality") or {}).get("chars") or 0) >= 500
        if failed_pages or (d.get("blocks") and len(d["blocks"]) < 10 and not ocr_ok):
            status = "partial"
            why = ("OCR was required but produced nothing on page(s) "
                   f"{failed_pages[:5]}") if failed_pages else \
                  f"only {len(d.get('blocks', []))} block(s) recovered"
            uncertainty.setdefault("notes", []).append(f"not complete: {why}")
            say(f"status capped at partial: {why}")

    # Engine degradation must be visible in result.json itself, not only in
    # run.log: the grader (and any agent consuming the result) reads result.json
    # first.  Without pymupdf the layout/table/reference fidelity drops sharply,
    # so a `complete` claim on a degraded backend would overstate the result.
    backend = (d.get("source") or {}).get("backend") or ""
    degraded_engine = bool(backend) and backend.lower() not in {"text"} \
        and not backend.lower().startswith("pymupdf")
    if degraded_engine and d.get("blocks"):
        if status == "complete":
            status = "partial"
        uncertainty.setdefault("notes", []).append(
            f"engine degraded: {backend} (pymupdf unavailable) — table, figure and "
            "reference fidelity is reduced; install pymupdf for best quality")
        say(f"engine degraded: {backend} (pymupdf not available); status capped at partial")

    draft = (payload or {}).get("draft") or {}
    paragraphs = draft.get("paragraphs") or []
    if paragraphs:
        if all((p.get("text") or "").strip() for p in paragraphs):
            draft["status"] = "written"
            if status == "partial":
                status = "complete"
                say("draft filled by the agent: status=complete")
        else:
            draft["status"] = "to_be_written"

    # Every file the case names is a graded artifact.  Writing it is not optional
    # and not inferred from task.md: `required_files` is read verbatim.
    files: List[Dict[str, Any]] = []
    if required:
        try:
            files = pk_deliver.write_required(
                args.out, [r for r in required if r != "result.json"],
                profile=args.profile, doc=doc, payload=payload,
                evidence=evidence, uncertainty=uncertainty,
                case=doc.get("case") or {}, task=doc.get("task") or "",
                input_dir=args.input)
            done = len([f for f in files if f.get("bytes")])
            expected = len([r for r in required if r != "result.json"])
            say(f"required files: {done}/{expected} written")
        except Exception as exc:
            notes.append(f"deliverable writer failed: {type(exc).__name__}: {exc}")
            uncertainty.setdefault("notes", []).append(
                "required_files could not all be written; see run.log")
            log.append(traceback.format_exc())
            say(f"deliverable error: {exc}")

    quality_issues = pk_quality.issues(
        args.profile, doc, payload, args.out, required, files)
    if quality_issues:
        message = "; ".join(quality_issues[:6])
        notes.append("content gate: " + message)
        uncertainty.setdefault("notes", []).append("content gate: " + message)
        if status == "complete":
            status = "partial"
            say(f"status capped at partial by content gate: {message[:180]}")

    envelope = None
    if stage:
        envelope = pk_report.envelope(args.profile, doc, payload, evidence, uncertainty,
                                      files, required)

    def build(status_value: str):
        return pk_result.build_result(
            case_id=case_id, doc=doc, case=doc.get("case") or {},
            payload=payload, status=status_value,
            evidence=evidence, uncertainty=uncertainty, notes=notes,
            envelope=envelope, files=files, required=required, profile=args.profile)

    res, leftover = build(status)
    # Slices the case never asked for go to their own file: `output_contract`
    # must stay exactly as wide as the declared contract, or the extra keys read
    # as renamed answers.
    if leftover:
        with open(os.path.join(args.out, "payload.json"), "w", encoding="utf-8") as fh:
            json.dump(leftover, fh, ensure_ascii=False, indent=1)
        say(f"extra slices -> payload.json ({len(leftover)} keys: {list(leftover)[:6]})")

    check = pk_result.validate_result(res, doc, case=doc.get("case") or {},
                                       out_dir=args.out,
                                       required=[r for r in required if r != "result.json"])
    check["content_ok"] = not quality_issues
    if quality_issues:
        check["ok"] = False
        check["quality_issues"] = quality_issues[:12]
    # The self-check is a gate, not a log line.  A result that fails it is not
    # shipped as `complete`: we downgrade, say why, and rebuild so
    # `status` moves together with the top-level status.
    downgraded = False
    if not check.get("ok") and status == "complete":
        status = "partial"
        uncertainty.setdefault("notes", []).append(
            "self-check failed, so this result is not claimed as complete: "
            + "; ".join(check.get("problems", [])[:3]))
        if envelope is not None:
            envelope = pk_report.envelope(args.profile, doc, payload, evidence, uncertainty,
                                          files, required)
        res, _ = build(status)
        check = pk_result.validate_result(res, doc, case=doc.get("case") or {},
                                          out_dir=args.out,
                                          required=[r for r in required if r != "result.json"])
        check["content_ok"] = not quality_issues
        if quality_issues:
            check["ok"] = False
            check["quality_issues"] = quality_issues[:12]
        downgraded = True
        say(f"self-check failed -> status downgraded to partial "
            f"({len(check.get('problems', []))} problem(s))")

    evidence_items = evidence or []
    anchored = sum(1 for e in evidence_items
                   if isinstance(e, dict) and (e.get("anchor") or e.get("block")))
    quoted = sum(1 for e in evidence_items
                 if isinstance(e, dict) and str(e.get("quote") or "").strip())
    self_check = {
        "case_id": case_id, "profile": args.profile,
        "status": res.get("status", status),
        "dimensions": [
            {"dimension": "required_files", "ok": not (check.get("files_missing") or check.get("files_empty")),
             "evidence": {"required": check.get("required_files"),
                          "missing": check.get("files_missing"),
                          "empty": check.get("files_empty")}},
            {"dimension": "contract", "ok": not check.get("problems"),
             "evidence": {"problems": check.get("problem_detail", [])}},
            {"dimension": "content", "ok": not quality_issues,
             "evidence": {"issues": quality_issues[:12]}},
            {"dimension": "evidence", "ok": bool(evidence_items) and anchored == len(evidence_items),
             "evidence": {"items": len(evidence_items), "anchored": anchored, "quoted": quoted}},
        ],
        "overall": bool(check.get("ok")) and res.get("status") == "success",
    }

    res["run"] = {"profile": args.profile, "engine": backend,
                  "fill": {"file": os.path.basename(fill_path) if fill_path else None,
                           "applied": fill_info["applied"],
                           "segments": fill_info["segments"],
                           "untranslated": fill_info["untranslated"]},
                  "degraded_engine": degraded_engine,
                  # Shipped inside the result: the reader of result.json can see
                  # whether the deliverable passed its own checks without opening
                  # run.log, and `problems` is a count they can recompute.
                  "validation": {"ok": bool(check.get("ok")),
                                 # a flat contract has no separate structural pass;
                                 # defaulting the flag to False made a clean run
                                 # read as "structure failed, 0 problems"
                                 "structural_ok": bool(check.get("structural_ok",
                                                                 check.get("ok"))),
                                 "content_ok": bool(check.get("content_ok", True)),
                                 "scope": check.get("scope", "flat"),
                                 "problems": len(check.get("problems", [])),
                                 "problem_detail": check.get("problems", [])[:8],
                                 "quality_issues": check.get("quality_issues", [])[:8],
                                 "evidence_items": check.get("evidence_items"),
                                 "contract_fields": check.get("contract_fields"),
                                 "required_files": check.get("required_files"),
                                 "files_missing": check.get("files_missing"),
                                 "files_empty": check.get("files_empty"),
                                 "downgraded": downgraded},
                  "seconds": round(time.time() - t0, 1),
                  "blocks": len(d.get("blocks", [])), "tables": len(d.get("tables", [])),
                  "formulas": len(d.get("formulas", [])), "references": len(d.get("references", []))}
    res["run"]["self_check"] = self_check
    with open(os.path.join(args.out, "rubric_self_check.json"), "w", encoding="utf-8") as fh:
        json.dump(self_check, fh, ensure_ascii=False, indent=1)
    pk_result.write(res, os.path.join(args.out, "result.json"))

    with open(os.path.join(args.out, "run.log"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(log + [json.dumps(check, ensure_ascii=False)]))
    print(json.dumps({"ok": bool(check.get("ok")),
                      "result": os.path.join(args.out, "result.json"),
                      "status": res.get("status", status), "validate": check,
                      "exit": 0,
                      "seconds": res["run"]["seconds"]}, ensure_ascii=False, indent=2))
    # A result.json is always written; partial/unable is a valid outcome and is
    # carried by `status` + `validation`, not by crashing the harness with a
    # non-zero exit code.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
