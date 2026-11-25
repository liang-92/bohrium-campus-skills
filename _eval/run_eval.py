"""Run the local test set against the current skills and score what can be scored.

What this harness refuses to do
-------------------------------
* It never asks a model to judge another model's prose.  Every check is either a
  set comparison against ground truth or a presence test on a literal string.
* It never scores ``使用增益`` (25 pts): that dimension is defined against a
  base-agent control run on the platform's fixed cases.  Reporting a number here
  would be inventing evidence, so it is reported as NOT MEASURED.

What it does measure
--------------------
    实际效果 40 = 完成度 15 + 正确性 15 + 完整性 5 + 可核验 5
    可靠体验 10 = 调用 3 + 稳定 4 + 异常 3
so 50 of the official 100 points are mechanically checkable, and the report says
so on the first line instead of hiding it.

Run:  python _eval/run_eval.py [--only A_R01_parse] [--repeat 2]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CASES = os.path.join(HERE, "cases")
RUNS = os.path.join(HERE, "runs")        # overridable with --runs
SKILLS = os.path.join(ROOT, "skills")   # overridable with --skills

sys.path.insert(0, HERE)
from spec import DELIVERABLES, DELIVERABLE_ALIASES, META_KEYS  # noqa: E402


# --------------------------------------------------------------------------- #
# running one case
# --------------------------------------------------------------------------- #
def stage(case: str, tag: str = "", force_nested: bool = False) -> str:
    src = os.path.join(CASES, case)
    dst = os.path.join(RUNS, case + tag, "work")
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    for junk in ("expected.json",):
        p = os.path.join(dst, junk)
        if os.path.exists(p):
            os.remove(p)
    if force_nested:
        # Give every skill its best case: an explicit required_files list.  The
        # difference against the mixed run is the cost of the contract shape.
        p = os.path.join(dst, "case.json")
        case_obj = json.load(open(p, encoding="utf-8"))
        oc = case_obj.get("output_contract") or {}
        if not any(isinstance(v, dict) and "required_fields" in v for v in oc.values()):
            fields = [k for k in oc if k not in META_KEYS]
            enum = (oc.get("status") or {}).get("enum") if isinstance(
                oc.get("status"), dict) else None
            task = (json.load(open(os.path.join(src, "expected.json"), encoding="utf-8"))
                    ["expect"]["task"])
            case_obj["output_contract"] = {
                "result_json": {"required_fields": fields,
                                "status_enum": enum or ["success", "partial", "unable"]},
                "rules": ["main_result 覆盖任务要求", "evidence 可回原文"],
                "required_files": ["result.json"] + DELIVERABLES.get(task, []),
            }
            json.dump(case_obj, open(p, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
    return dst


def run_skill(skill: str, work: str, out: str, timeout: int = 600,
              skills_dir: str | None = None) -> Dict[str, Any]:
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out, exist_ok=True)
    base = skills_dir or SKILLS
    entry = os.path.join(base, skill, "scripts", "run.py")
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, entry, "--input", work, "--out", out],
                           capture_output=True, text=True, timeout=timeout,
                           cwd=os.path.join(base, skill))
        code, err, so = p.returncode, p.stderr, p.stdout
    except subprocess.TimeoutExpired:
        code, err, so = -9, f"timeout after {timeout}s", ""
    return {"exit": code, "stderr": err[-4000:], "stdout": so[-2000:],
            "seconds": round(time.time() - t0, 2)}


def collect(out: str) -> Dict[str, Any]:
    """Everything we know about one run, without believing any of it yet."""
    res, files = None, []
    rp = os.path.join(out, "result.json")
    if os.path.exists(rp):
        try:
            res = json.load(open(rp, encoding="utf-8"))
        except Exception as exc:
            res = {"__parse_error__": f"{type(exc).__name__}: {exc}"}
    for r, _, fs in os.walk(out):
        for f in fs:
            full = os.path.join(r, f)
            files.append(os.path.relpath(full, out).replace("\\", "/"))
    doc = None
    dp = os.path.join(out, "doc.json")
    if os.path.exists(dp):
        try:
            doc = json.load(open(dp, encoding="utf-8"))
        except Exception:
            doc = None
    return {"result": res, "files": sorted(files), "doc": doc}


# --------------------------------------------------------------------------- #
# contract check -- the official rule, not our own invention
# --------------------------------------------------------------------------- #
VOLATILE = {"seconds", "elapsed", "duration", "duration_s", "timestamp",
            "generated_at", "started_at", "wall_time_s", "took"}


def _canon(node, depth: int = 0):
    """Drop what changes between two runs of the same input: clocks and paths."""
    if depth > 12:
        return node
    if isinstance(node, dict):
        return {k: _canon(v, depth + 1) for k, v in sorted(node.items())
                if k not in VOLATILE}
    if isinstance(node, list):
        return [_canon(v, depth + 1) for v in node]
    if isinstance(node, str):
        s = re.sub(r"_r\d+", "_rN", node)
        s = re.sub(r"[A-Za-z]:\\[^\s\"]+|/[^\s\"]*/_eval/runs/\S*", "<path>", s)
        return s
    return node


def fingerprint(collected: Dict[str, Any]) -> str:
    h = hashlib.sha256()
    h.update(json.dumps(_canon(collected["result"]), sort_keys=True,
                        ensure_ascii=False).encode())
    h.update("|".join(sorted(collected["files"])).encode())
    return h.hexdigest()[:16]


def declared_fields(case: Dict[str, Any]) -> List[str]:
    oc = case.get("output_contract") or {}
    if not isinstance(oc, dict):
        return []
    # nested shape: {result_json: {required_fields: [...]}}
    for v in oc.values():
        if isinstance(v, dict) and isinstance(v.get("required_fields"), list):
            return [str(x) for x in v["required_fields"]]
    return [k for k in oc if isinstance(k, str) and k not in META_KEYS]


def declared_enum(case: Dict[str, Any]) -> List[str]:
    oc = case.get("output_contract") or {}
    for v in oc.values():
        if isinstance(v, dict):
            if isinstance(v.get("status_enum"), list):
                return [str(x) for x in v["status_enum"]]
    st = oc.get("status")
    if isinstance(st, dict) and isinstance(st.get("enum"), list):
        return [str(x) for x in st["enum"]]
    return ["success", "partial", "unable"]


def check_contract(case: Dict[str, Any], result: Dict[str, Any] | None) -> Dict[str, Any]:
    """Official rule: result.json carries case_id and every declared field.

    The runtime text does not say *where*.  Both readings are checked, because a
    grader written against one of them will silently see an empty answer on the
    other -- the ambiguity is itself the finding.
    """
    if not isinstance(result, dict):
        return {"ok": False, "reason": "no result.json", "missing": [], "extra": []}
    want = declared_fields(case)
    enum = declared_enum(case)
    nested = result.get("output_contract") if isinstance(
        result.get("output_contract"), dict) else {}
    top_missing = [f for f in want if f not in result]
    nested_missing = [f for f in want if f not in nested]
    status = result.get("status")
    return {
        "ok": (not top_missing or not nested_missing) and status in enum,
        "top_ok": not top_missing,
        "nested_ok": not nested_missing,
        "where": "top" if not top_missing else ("output_contract" if not nested_missing
                                                else "nowhere"),
        "case_id_ok": result.get("case_id") == case.get("case_id"),
        "status": status,
        "status_in_enum": status in enum,
        "enum": enum,
        "missing": top_missing,
        "nested_missing": nested_missing,
        "declared": want,
    }


# --------------------------------------------------------------------------- #
# content: text the run produced, flattened
# --------------------------------------------------------------------------- #
def flat_text(result: Dict[str, Any] | None, doc: Dict[str, Any] | None,
              out: str, kind: str = "produce") -> str:
    """Text a run *produced*, so literal checks cannot pass on quoted source.

    ``kind="parse"``: the extracted text is the deliverable, so doc blocks count.
    ``kind="produce"``: the deliverable is a new artifact; evidence quotes and the
    parsed source are excluded on purpose -- otherwise "did it remove the word
    proves?" passes because the evidence still quotes the original sentence.
    """
    chunks: List[str] = []
    if isinstance(result, dict):
        oc = result.get("output_contract")
        if isinstance(oc, dict):
            keep = {k: v for k, v in oc.items()
                    if k not in {"evidence", "uncertainty", "provenance", "change_log"}}
            chunks.append(json.dumps(keep, ensure_ascii=False))
        for k in ("main_result", "deliverables", "revised_text", "target"):
            if result.get(k) not in (None, "", [], {}):
                chunks.append(json.dumps(result[k], ensure_ascii=False))
    if kind == "parse" and isinstance(doc, dict):
        d = doc.get("document") or {}
        for b in d.get("blocks") or []:
            chunks.append(b.get("text") or "")
        for t in d.get("tables") or []:
            chunks.append(" ".join(" ".join(r) for r in (t.get("rows") or [])))
    for f in ("structure.md", "body.md", "refs.md", "section_summary.md",
              "outline.md", "revised.md", "background.md", "methods.md",
              "bilingual_parallel.md", "decomposition.md", "main.tex",
              "fix_report.md", "type_summary.md", "manuscript_cited.md",
              "intro_cited.md", "related_work.md", "gap.md", "contributions.md",
              "entities.csv", "edges.csv", "notes.md"):
        p = os.path.join(out, f)
        if os.path.exists(p):
            try:
                chunks.append(open(p, encoding="utf-8").read())
            except Exception:
                pass
    return "\n".join(chunks)


def has(text: str, needle: str) -> bool:
    return needle.lower() in text.lower()


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


# --------------------------------------------------------------------------- #
# per-topic content checks
# --------------------------------------------------------------------------- #
def doc_sections(doc: Dict[str, Any] | None) -> List[str]:
    d = (doc or {}).get("document") or {}
    return [s.get("title") or "" for s in d.get("sections") or []]


def doc_tables(doc: Dict[str, Any] | None) -> List[Dict[str, Any]]:
    d = (doc or {}).get("document") or {}
    return d.get("tables") or []


def score_r01(exp: Dict[str, Any], result, doc, out, text) -> List[Dict[str, Any]]:
    checks = []
    e = exp
    if e.get("honesty_only"):
        status = (result or {}).get("status")
        notes = json.dumps((result or {}).get("uncertainty") or {}, ensure_ascii=False)
        checks.append({"id": "status_not_success", "w": 3,
                       "ok": status in {"partial", "unable"},
                       "detail": f"status={status}"})
        checks.append({"id": "says_no_text_layer", "w": 2,
                       "ok": any(has(notes, k) for k in
                                 ("text layer", "文字层", "ocr", "扫描", "scan")),
                       "detail": "uncertainty 是否说明没有文字层"})
        return checks

    if e.get("title_contains"):
        checks.append({"id": "title", "w": 2,
                       "ok": has(text, e["title_contains"]),
                       "detail": e["title_contains"]})
    secs = e.get("sections") or []
    if secs:
        got = [norm(s) for s in doc_sections(doc)]
        hit = [s for s in secs if any(norm(s) in g or g in norm(s) for g in got if g)]
        checks.append({"id": "sections", "w": 5, "ok": len(hit) == len(secs),
                       "detail": f"{len(hit)}/{len(secs)} 命中；缺 "
                                 f"{[s for s in secs if s not in hit]}"})
    t = (e.get("table") or {})
    if t:
        tabs = doc_tables(doc)
        if t.get("merged_pages"):
            ok = len(tabs) == 1
            rows = sum(len(x.get("rows") or []) for x in tabs)
            checks.append({"id": "table_merged", "w": 3, "ok": ok,
                           "detail": f"{len(tabs)} 张表，合计 {rows} 行"})
            checks.append({"id": "table_rows", "w": 2,
                           "ok": any(len(x.get("rows") or []) == t["rows"] for x in tabs),
                           "detail": f"期望单表 {t['rows']} 行，实得 "
                                     f"{[len(x.get('rows') or []) for x in tabs]}"})
        else:
            best = max(tabs, key=lambda x: len(x.get("rows") or []), default=None)
            if best:
                rows = len(best.get("rows") or [])
                cols = best.get("n_cols") or len((best.get("header") or []))
                # `rows` may or may not include the header row; both are honest
                ok_rows = rows in {t["rows"], t["rows"] + 1}
                checks.append({"id": "table_shape", "w": 3,
                               "ok": ok_rows and cols == t["cols"],
                               "detail": f"{rows}×{cols} vs 期望 {t['rows']}(+表头)×{t['cols']}"})
                heads = t.get("header_cells") or []
                if heads:
                    hd = " ".join(best.get("header") or [])
                    got = sum(1 for h in heads if has(hd, h))
                    checks.append({"id": "table_header", "w": 3,
                                   "ok": got == len(heads),
                                   "detail": f"表头 {got}/{len(heads)}：{hd[:90]}"})
            else:
                checks.append({"id": "table_shape", "w": 3, "ok": False,
                               "detail": "没有识别到表格"})
    if e.get("references") is not None:
        d = (doc or {}).get("document") or {}
        n = len(d.get("references") or [])
        checks.append({"id": "references", "w": 3, "ok": n == e["references"],
                       "detail": f"{n} 条 vs 期望 {e['references']}"})
    if e.get("equations") is not None:
        d = (doc or {}).get("document") or {}
        n = len(d.get("formulas") or [])
        checks.append({"id": "equations", "w": 2, "ok": n >= e["equations"],
                       "detail": f"{n} 个 vs 期望 ≥{e['equations']}"})
    for k in e.get("must_keep") or []:
        checks.append({"id": f"keep:{k}", "w": 1, "ok": has(text, k), "detail": k})
    return checks


def score_r03(exp, result, doc, out, text) -> List[Dict[str, Any]]:
    e = exp
    checks = []
    n = e.get("paragraphs", 0)
    got = len(set(re.findall(r"\bP0[1-9]\b", text)))
    checks.append({"id": "paragraphs", "w": 5, "ok": got >= n,
                   "detail": f"{got}/{n} 个段落编号"})
    terms = e.get("glossary_terms") or []
    hit = sum(1 for t in terms if has(text, t))
    checks.append({"id": "glossary", "w": 5, "ok": hit == len(terms),
                   "detail": f"{hit}/{len(terms)} 个锁定译名出现"})
    for k in e.get("must_keep") or []:
        checks.append({"id": f"keep:{k}", "w": 1, "ok": has(text, k), "detail": k})
    return checks


def score_sections(exp, result, doc, out, text) -> List[Dict[str, Any]]:
    e = exp
    checks = []
    secs = e.get("sections") or []
    if secs:
        hit = sum(1 for s in secs if has(text, s))
        checks.append({"id": "sections", "w": 5, "ok": hit == len(secs),
                       "detail": f"{hit}/{len(secs)} 节"})
    for k in e.get("must_keep") or []:
        checks.append({"id": f"keep:{k}", "w": 2, "ok": has(text, k), "detail": k})
    return checks


def score_nanopub(exp, result, doc, out, text) -> List[Dict[str, Any]]:
    e = exp
    checks = []
    n = e.get("min_assertions", 0)
    got = 0
    p = os.path.join(out, "nanopubs.json")
    if os.path.exists(p):
        try:
            got = len(json.load(open(p, encoding="utf-8")))
        except Exception:
            got = 0
    if not got:
        got = len(re.findall(r"assertion", text, re.I))
    checks.append({"id": "assertions", "w": 5, "ok": got >= n,
                   "detail": f"{got} 条断言 vs 期望 ≥{n}"})
    for f in e.get("must_flag") or []:
        checks.append({"id": f"flag:{f}", "w": 2, "ok": has(text, f), "detail": f})
    for k in e.get("must_keep") or []:
        checks.append({"id": f"keep:{k}", "w": 1, "ok": has(text, k), "detail": k})
    return checks


def score_entities(exp, result, doc, out, text) -> List[Dict[str, Any]]:
    e = exp
    checks = []
    n = e.get("min_entities", 0)
    got = 0
    for f in ("entities.csv", "entity.csv", "graph_nodes.csv"):
        p = os.path.join(out, f)
        if os.path.exists(p):
            try:
                got = max(got, sum(1 for _ in open(p, encoding="utf-8")) - 1)
            except Exception:
                pass
    checks.append({"id": "entities", "w": 5, "ok": got >= n,
                   "detail": f"{got} 个实体 vs 期望 ≥{n}"})
    for k in e.get("must_keep") or []:
        checks.append({"id": f"keep:{k}", "w": 2, "ok": has(text, k), "detail": k})
    return checks


def score_polish(exp, result, doc, out, text) -> List[Dict[str, Any]]:
    e = exp
    checks = []
    for bad in e.get("must_not_contain") or []:
        checks.append({"id": f"drop:{bad}", "w": 2, "ok": not has(text, bad),
                       "detail": f"不应保留 {bad}"})
    for k in e.get("must_keep") or []:
        checks.append({"id": f"keep:{k}", "w": 2, "ok": has(text, k), "detail": k})
    n = e.get("min_changes", 0)
    got = 0
    p = os.path.join(out, "changes.csv")
    if os.path.exists(p):
        try:
            got = sum(1 for _ in open(p, encoding="utf-8")) - 1
        except Exception:
            pass
    checks.append({"id": "changes", "w": 3, "ok": got >= n,
                   "detail": f"{got} 条修改记录 vs 期望 ≥{n}"})
    return checks


def score_cites(exp, result, doc, out, text) -> List[Dict[str, Any]]:
    e = exp
    checks = []
    cites = re.findall(r"\[(\d+)\]|\\cite[a-z]*\{([^}]+)\}", text)
    got = len(cites)
    checks.append({"id": "citations", "w": 5, "ok": got >= e.get("min_citations", 0),
                   "detail": f"{got} 处引用 vs 期望 ≥{e.get('min_citations', 0)}"})
    for k in e.get("must_keep") or []:
        checks.append({"id": f"keep:{k}", "w": 2, "ok": has(text, k), "detail": k})
    return checks


def score_methods(exp, result, doc, out, text) -> List[Dict[str, Any]]:
    e = exp
    checks = []
    steps = len(re.findall(r"(?m)^\s*(?:\d+[.)]|[-*])\s+\S", text))
    checks.append({"id": "steps", "w": 3, "ok": steps >= e.get("min_steps", 0),
                   "detail": f"{steps} 个步骤 vs 期望 ≥{e.get('min_steps', 0)}"})
    for k in e.get("must_keep") or []:
        checks.append({"id": f"keep:{k}", "w": 2, "ok": has(text, k), "detail": k})
    for f in e.get("must_flag") or []:
        checks.append({"id": f"flag:{f}", "w": 2, "ok": has(text, f), "detail": f})
    return checks


def score_latex(exp, result, doc, out, text) -> List[Dict[str, Any]]:
    e = exp
    checks = []
    tex = ""
    for cand in ("main.tex", "project/main.tex"):
        p = os.path.join(out, cand)
        if os.path.exists(p):
            tex = open(p, encoding="utf-8").read()
            break
    has_text = bool(tex.strip())
    checks.append({"id": "project_copied", "w": 3, "ok": has_text,
                   "detail": "输出里是否有一份**非空**的 main.tex"})
    if not has_text:
        # An empty placeholder must not let the sub-checks pass by absence.
        for name in ("fix:amsmath", "fix:undefined_cite", "fix:duplicate_label",
                     "body:preserved", "no:[TODO]"):
            checks.append({"id": name, "w": 2, "ok": False,
                           "detail": "main.tex 为空，无法判定"})
        return checks
    for f in e.get("must_fix") or []:
        if f == "amsmath":
            ok = "amsmath" in tex
            checks.append({"id": "fix:amsmath", "w": 2, "ok": ok, "detail": f})
        elif f == "li2022":
            bib = ""
            bp = os.path.join(out, "project/refs.bib")
            if os.path.exists(bp):
                bib = open(bp, encoding="utf-8").read()
            # Either add a verifiable entry or remove the unsupported citation;
            # inventing an entry to satisfy this check is exactly what P0 forbids.
            ok = ("li2022" in tex) or ("li2022" in bib) or ("li2022" not in tex)
            checks.append({"id": "fix:undefined_cite", "w": 2, "ok": bool(ok),
                           "detail": "缺 bib 条目是否补上或引用是否移除"})
        elif f == "duplicate_label":
            ok = tex.count("\\label{sec:res}") <= 1
            checks.append({"id": "fix:duplicate_label", "w": 2, "ok": ok,
                           "detail": "重复章节是否合并"})
    for k in e.get("must_keep_body") or []:
        checks.append({"id": f"body:{k}", "w": 2, "ok": has(tex, k),
                       "detail": f"正文是否保留：{k}"})
    for bad in e.get("must_not") or []:
        checks.append({"id": f"no:{bad}", "w": 2, "ok": not has(tex, bad),
                       "detail": f"不应出现 {bad}"})
    return checks


SCORERS = {
    "R01": score_r01,
    "R03": score_r03,
    "R10": score_sections,
    "R14": score_nanopub,
    "R15": score_entities,
    "W02": score_polish,
    "W04": score_cites,
    "W08": score_cites,
    "W09": score_methods,
    "W13": score_latex,
}


def score_nanopub_shared(exp, result, doc, out, text):
    return score_nanopub(exp, result, doc, out, text)


# --------------------------------------------------------------------------- #
# evidence quality
# --------------------------------------------------------------------------- #
def evidence_score(result: Dict[str, Any] | None, doc: Dict[str, Any] | None) -> Dict[str, Any]:
    """An anchor is only worth something if it resolves to a real block/page."""
    if not isinstance(result, dict):
        return {"ok": False, "detail": "没有 result", "ratio": 0.0}
    ev = result.get("evidence")
    if not isinstance(ev, list) or not ev:
        return {"ok": False, "detail": "evidence 为空", "ratio": 0.0}
    d = (doc or {}).get("document") or {}
    pages = {p.get("number") for p in (d.get("pages") or [])}
    block_ids = {b.get("id") for b in (d.get("blocks") or [])}
    good = 0
    for item in ev:
        if not isinstance(item, dict):
            continue
        blob = json.dumps(item, ensure_ascii=False)
        ok = False
        m = re.search(r"p(\d{2})-b\d{3}", blob)
        if m and block_ids:
            ok = any(str(i) in blob for i in block_ids)
        if not ok:
            pg = re.search(r'"(?:page|anchor)"\s*:\s*"?(\d+)', blob)
            if pg and pages:
                ok = int(pg.group(1)) in pages
        if not ok:
            q = item.get("quote") or ""
            ok = bool(q) and norm(q)[:40] in norm(
                " ".join(b.get("text") or "" for b in (d.get("blocks") or [])))
        good += 1 if ok else 0
    return {"ok": good > 0, "detail": f"{good}/{len(ev)} 条证据可回到原文",
            "ratio": good / max(len(ev), 1)}


# --------------------------------------------------------------------------- #
# one case
# --------------------------------------------------------------------------- #
def evaluate(case_name: str, repeat: int = 2, force_nested: bool = False,
             skills_dir: str | None = None) -> Dict[str, Any]:
    cdir = os.path.join(CASES, case_name)
    case = json.load(open(os.path.join(cdir, "case.json"), encoding="utf-8"))
    exp = json.load(open(os.path.join(cdir, "expected.json"), encoding="utf-8"))
    skill = exp["skill"]
    e = exp.get("expect") or {}

    runs = []
    for i in range(max(1, repeat)):
        work = stage(case_name, f"_r{i}", force_nested=force_nested)
        out = os.path.join(RUNS, case_name + f"_r{i}", "out")
        r = run_skill(skill, work, out, skills_dir=skills_dir)
        c = collect(out)
        runs.append({"run": r, "collected": c, "out": out})

    first = runs[0]
    result, doc, files = first["collected"]["result"], first["collected"]["doc"], \
        first["collected"]["files"]
    text = flat_text(result, doc, first["out"],
                     kind="parse" if e.get("task") == "R01" else "produce")

    contract = check_contract(case, result)
    checks = SCORERS.get(e.get("task", ""), lambda *a: [])(e, result, doc, first["out"], text)

    # deliverable completeness
    want = DELIVERABLES.get(e.get("task", ""), [])
    present, missing = [], []
    for f in want:
        cands = DELIVERABLE_ALIASES.get(f, [f])
        got = None
        for c in cands:
            hit = next((x for x in files if x == c or x.endswith("/" + c)), None)
            if not hit:
                continue
            try:
                raw = open(os.path.join(first["out"], hit), encoding="utf-8",
                           errors="replace").read()
            except OSError:
                continue
            # A lone newline is not a deliverable: require a real line of content.
            if len(raw.strip()) >= 20:
                got = hit
                break
        (present if got else missing).append(f)

    # content reachability: did the skill read the material at all?
    d = (doc or {}).get("document") or {}
    reachable = bool(d.get("blocks")) or bool(
        isinstance(result, dict) and result.get("main_result")) or \
        bool(result and result.get("output_contract") and
             any(v not in (None, "", [], {}) for v in
                 (result.get("output_contract") or {}).values()))

    # stability: same fingerprint across repeats
    fps = [fingerprint(r["collected"]) for r in runs]
    stable = len(set(fps)) == 1

    ev = evidence_score(result, doc)

    # ---- points ----
    total_w = sum(c["w"] for c in checks) or 1
    hit_w = sum(c["w"] for c in checks if c["ok"])
    correct_ratio = hit_w / total_w

    completion = 15 * (1.0 if reachable else 0.0)
    if reachable and checks:
        completion = 15 * min(1.0, correct_ratio + 0.25)
    correctness = 15 * correct_ratio
    completeness = 5 * (len(present) / len(want) if want else 0.0)
    verifiable = 5 * ev["ratio"]

    call_ok = first["run"]["exit"] == 0 and isinstance(result, dict)
    usability = 3 if call_ok else (1 if first["run"]["exit"] == 0 else 0)
    stability = 4 if stable else 2
    exception = 3 if (isinstance(result, dict) and
                      (result.get("uncertainty") or result.get("status") in
                       {"partial", "unable"})) else 0
    # Claiming success while the content checks disagree is the one failure mode
    # the rubric names explicitly ("无法判断不被写成事实"), so it costs points here.
    status_val = (result or {}).get("status")
    if status_val in {"success", "complete"} and (not reachable or correct_ratio < 0.8):
        exception = min(exception, 1)

    effect = completion + correctness + completeness + verifiable
    reliability = usability + stability + exception

    return {
        "case": case_name, "skill": skill, "task": e.get("task"),
        "exit": first["run"]["exit"], "seconds": first["run"]["seconds"],
        "status": (result or {}).get("status"),
        "contract": contract, "checks": checks,
        "correct_ratio": round(correct_ratio, 3),
        "deliverables_want": want, "deliverables_ok": present,
        "deliverables_missing": missing,
        "reachable": reachable, "stable": stable, "fingerprints": fps,
        "evidence": ev, "files": files,
        "points": {"completion": round(completion, 1),
                   "correctness": round(correctness, 1),
                   "completeness": round(completeness, 1),
                   "verifiable": round(verifiable, 1),
                   "effect": round(effect, 1),
                   "usability": usability, "stability": stability,
                   "exception": exception,
                   "reliability": reliability,
                   "measurable_total": round(effect + reliability, 1)},
        "stderr_tail": first["run"]["stderr"][-600:],
    }


def main():
    global RUNS
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="",
                    help="case-name filter, comma separated")
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--json", default=os.path.join(HERE, "results.json"))
    ap.add_argument("--runs", default="",
                    help="staging root (default _eval/runs); a fresh directory "
                         "keeps earlier results instead of overwriting them")
    ap.add_argument("--skills", default="",
                    help="score a pinned copy instead of ./skills")
    ap.add_argument("--force-nested", action="store_true",
                    help="declare required_files for every case (best-case condition)")
    a = ap.parse_args()

    if a.runs:
        RUNS = os.path.abspath(a.runs)
        os.makedirs(RUNS, exist_ok=True)

    names = sorted(os.listdir(CASES))
    if a.only:
        want = [w.strip().lower() for w in a.only.split(",") if w.strip()]
        names = [n for n in names if any(w in n.lower() for w in want)]

    out = []
    for n in names:
        if not os.path.isdir(os.path.join(CASES, n)):
            continue
        r = evaluate(n, repeat=a.repeat, force_nested=a.force_nested,
                     skills_dir=os.path.abspath(a.skills) if a.skills else None)
        out.append(r)
        p = r["points"]
        print(f"{n:22s} {r['skill']:16s} status={str(r['status']):8s} "
              f"effect={p['effect']:5.1f} rel={p['reliability']:2d} "
              f"contract={'ok' if r['contract'].get('ok') else 'FAIL'} "
              f"content={r['correct_ratio']:.0%}")

    json.dump(out, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n{len(out)} cases -> {a.json}")


if __name__ == "__main__":
    main()
