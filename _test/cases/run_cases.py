"""Run every self-test case against the skill it belongs to and check the answer.

Usage
    python run_cases.py                # all cases
    python run_cases.py p01 p08        # only cases whose name starts with these
    python run_cases.py --skill paper-parse

Each case directory holds `gold.json` with the expected values; a case passes
only when every expectation holds.  Results land in `_out/<skill>/<case>/` and
the summary in `report.md` / `report.json`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SKILLS = os.path.join(ROOT, "skills")

TOPIC_MAP = [
    ("解析", "paper-parse"),
    ("翻译", "paper-translate"),
    ("笔记", "paper-notes"),
    ("纳米", "paper-nanopub"),
    ("知识图谱", "paper-kg"),
    ("润色", "paper-polish"),
    ("参考文献", "paper-refs"),
    ("引言", "paper-intro"),
    ("方法", "paper-methods"),
    ("LaTeX", "paper-latex"),
]


def skill_for(case: dict) -> str:
    topic = case.get("topic") or ""
    for key, slug in TOPIC_MAP:
        if key.lower() in topic.lower():
            return slug
    return "paper-parse"


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default if default is not None else {}


def dig(obj, key):
    """First value stored under `key` anywhere in `obj`."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            got = dig(v, key)
            if got is not None:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = dig(v, key)
            if got is not None:
                return got
    return None


def flat_text(obj) -> str:
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        return "\n".join(flat_text(v) for v in obj)
    if isinstance(obj, dict):
        return "\n".join(flat_text(v) for v in obj.values())
    return str(obj)


def run_one(slug: str, case_dir: str) -> dict:
    out = os.path.join(HERE, "_out", slug, os.path.basename(case_dir))
    os.makedirs(out, exist_ok=True)
    cmd = [sys.executable, os.path.join(SKILLS, slug, "scripts", "run.py"),
           "--input", case_dir, "--out", out]
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    res = load(os.path.join(out, "result.json"))
    pay = load(os.path.join(out, "payload.json"))
    return {"slug": slug, "case": os.path.basename(case_dir), "out": out,
            "rc": proc.returncode, "stderr": (proc.stderr or "")[-600:],
            "result": res, "payload": pay, "seconds": round(time.time() - t0, 1),
            "has_result": os.path.exists(os.path.join(out, "result.json"))}


def as_list(v):
    """Contract fields arrive as a bare list or wrapped as {"items"/"value": [...]}."""
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        for k in ("items", "value"):
            if isinstance(v.get(k), list):
                return v[k]
    return []


def check(gold: dict, run: dict) -> list[tuple[str, bool, str]]:
    res, pay = run["result"], run["payload"]
    oc = res.get("output_contract") or {}
    blob = flat_text([oc, pay])
    checks: list[tuple[str, bool, str]] = []
    slug = run["slug"]

    def add(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    status = res.get("status", "")
    if "expect_status" in gold:
        add("status", status in gold["expect_status"], f"status={status}")
    if gold.get("result_must_exist"):
        add("result.json 存在", run["has_result"])
    if gold.get("must_not_have_text"):
        body = flat_text(oc.get("content") or {})
        add("未编造正文", "Sparse Routing" not in body)

    if "pages" in gold:
        got = (oc.get("document") or {}).get("pages")
        add("页数", got == gold["pages"], f"{got} != {gold['pages']}")

    if "authors" in gold:
        got = (oc.get("document") or {}).get("authors") or []
        want = gold["authors"]
        add("作者", [a.strip() for a in got] == want, f"got={got}")

    if "title_words" in gold:
        title = (oc.get("document") or {}).get("title") or ""
        add("标题", all(w in title for w in gold["title_words"]), title[:60])

    if "sections" in gold:
        structure = oc.get("structure") or []
        titles = json.dumps(structure, ensure_ascii=False)
        missing = [s for s in gold["sections"] if s.split(" ", 1)[-1][:18] not in titles]
        add("章节", not missing, f"missing={missing[:3]}")

    if "tables" in gold:
        val = as_list(dig(oc, "content.tables"))
        ok = False
        detail = f"{len(val)} tables"
        for t in val:
            t = t if isinstance(t, dict) else {}
            if t.get("n_rows") == gold["tables"][0]["n_rows"] and \
                    t.get("n_cols") == gold["tables"][0]["n_cols"]:
                body = json.dumps(t, ensure_ascii=False)
                if all(v in body for v in gold["tables"][0]["must_contain"]):
                    ok = True
                    break
                detail = f"dims ok but values missing in {body[:120]}"
        add("表格", ok, detail)

    if "formulas" in gold:
        val = as_list(dig(oc, "content.formulas"))
        add("公式", len(val) >= gold["formulas"]["at_least"],
            f"count={len(val)} number={(val[0] or {}).get('number') if val else None}")

    if "reading_order" in gold:
        blocks = as_list(dig(oc, "content.blocks"))
        joined = "\n".join(b.get("text", "") for b in blocks if isinstance(b, dict))
        a, b = gold["reading_order"][0], gold["reading_order"][1]
        add("阅读顺序", joined.find(a) < joined.find(b) and a in joined,
            "left column must precede right column")

    if "hyperparameters" in gold and slug == "paper-methods":
        params = as_list(dig(oc, "parameters")) or as_list(dig(pay, "parameters"))
        got = {(p.get("name") or "").lower(): str(p.get("value") or "") for p in params
               if isinstance(p, dict)}
        missing = [f"{n}={w}" for n, w in gold["hyperparameters"].items()
                   if not any(n in k and w in v for k, v in got.items())]
        add("超参数", not missing, f"missing={missing}")

    if "datasets" in gold and slug == "paper-methods":
        ds = as_list(dig(oc, "datasets")) or as_list(dig(pay, "datasets"))
        body = json.dumps(ds, ensure_ascii=False)
        add("数据集", all(d in body for d in gold["datasets"]), body[:100])

    if "seeds_reported" in gold and gold["seeds_reported"] is False and slug == "paper-methods":
        missing = as_list(dig(oc, "missing")) or as_list(dig(pay, "missing"))
        add("种子缺口", any("seed" in str(m).lower() for m in missing), str(missing)[:80])

    if "citations_without_entry" in gold and slug == "paper-refs":
        issues = dig(oc, "issues") or dig(pay, "issues") or {}
        got = [str(x) for x in (issues.get("citations_without_entry") or [])]
        add("缺失条目", set(got) == set(gold["citations_without_entry"]), f"got={got}")
    if "entries_never_cited" in gold and slug == "paper-refs":
        issues = dig(oc, "issues") or dig(pay, "issues") or {}
        got = [str(x) for x in (issues.get("entries_never_cited") or [])]
        add("未被引用", set(got) == set(gold["entries_never_cited"]), f"got={got}")
    if "duplicate_pair" in gold and slug == "paper-refs":
        issues = dig(oc, "issues") or dig(pay, "issues") or {}
        dups = issues.get("duplicates") or []
        pairs = {tuple(sorted((str(d.get("a")), str(d.get("b"))))) for d in dups if isinstance(d, dict)}
        add("重复条目", tuple(sorted(gold["duplicate_pair"])) in pairs, f"got={sorted(pairs)[:3]}")
    if gold.get("bibtex_has_inproceedings") and slug == "paper-refs":
        add("BibTeX 类型", "@inproceedings" in blob, blob[blob.find("@inproceedings"):][:60]
            if "@inproceedings" in blob else "not found")
    if gold.get("gbt_has_type_marker") and slug == "paper-refs":
        add("GB/T 类型标记", "[C]" in blob or "[J]" in blob)

    if "kg_must_have" in gold and slug == "paper-kg":
        nodes = as_list(dig(oc, "nodes")) or as_list(dig(pay, "nodes"))
        labels = " ".join(str(n.get("label")) for n in nodes if isinstance(n, dict)).lower()
        miss = [x for x in gold["kg_must_have"] if x.lower() not in labels]
        add("图谱实体", not miss, f"missing={miss}")
    if "min_edges" in gold and slug == "paper-kg":
        edges = as_list(dig(oc, "edges")) or as_list(dig(pay, "edges"))
        add("图谱边数", len(edges) >= gold["min_edges"], f"{len(edges)} >= {gold['min_edges']}")

    if "draft_paragraphs" in gold:
        draft = dig(oc, "draft") or dig(pay, "draft") or {}
        paras = draft.get("paragraphs") or []
        add("草稿骨架", len(paras) == gold["draft_paragraphs"], f"{len(paras)} 段")

    if gold.get("requires_files") and slug == "paper-latex":
        files = as_list(dig(oc, "files")) or as_list(dig(pay, "files"))
        add("产出文件", any(f in json.dumps(files) for f in gold["requires_files"]), str(files)[:60])
    if gold.get("requires_static_check") and slug == "paper-latex":
        comp = dig(oc, "compile") or dig(pay, "compile") or {}
        add("静态自检", "static_check" in comp, str(list(comp.keys()))[:60])

    if "max_segments" in gold and slug == "paper-translate":
        segs = as_list(dig(oc, "segments")) or as_list(dig(pay, "segments"))
        add("分段上限", len(segs) <= gold["max_segments"], f"{len(segs)} <= {gold['max_segments']}")
    if "batch_size" in gold and slug == "paper-translate":
        batches = as_list(dig(oc, "batches")) or as_list(dig(pay, "batches"))
        ok = bool(batches) and max(len(b) for b in batches) <= gold["batch_size"]
        add("分批 ≤20", ok, f"{len(batches)} batches")
    if "skip_sections" in gold and slug == "paper-translate":
        segs = as_list(dig(oc, "segments")) or as_list(dig(pay, "segments"))
        secs = {(s.get("section") or "") for s in segs if isinstance(s, dict)}
        add("跳过参考文献", not any("Refer" in s for s in secs), str(sorted(secs))[:80])
    if "protected_examples" in gold and slug == "paper-translate":
        segs = as_list(dig(oc, "segments")) or as_list(dig(pay, "segments"))
        body = json.dumps(segs, ensure_ascii=False)
        miss = [p for p in gold["protected_examples"] if p not in body]
        add("保护令牌", not miss, f"missing={miss}")

    if "expect_ocr_or_unable" in gold:
        cov = dig(oc, "coverage") or {}
        pages = cov.get("chars_per_page") if isinstance(cov, dict) else None
        add("OCR/诚实状态", status == "unable" or bool(pages), f"status={status} pages={pages}")

    if "must_answer" in gold and slug == "paper-notes":
        card = dig(oc, "note") or dig(pay, "paper_card") or {}
        body = json.dumps(card, ensure_ascii=False).lower()
        miss = [w for w in gold["must_answer"] if w.lower() not in body]
        add("笔记要点", not miss, f"missing={miss}")
    if "limitations_from_text" in gold and slug == "paper-notes":
        card = dig(oc, "note") or dig(pay, "paper_card") or {}
        body = json.dumps(card, ensure_ascii=False).lower()
        miss = [w for w in gold["limitations_from_text"] if w.lower() not in body]
        add("局限来自原文", not miss, f"missing={miss}")

    if "assertion_count_min" in gold and slug == "paper-nanopub":
        val = as_list(dig(oc, "assertion")) or as_list(dig(pay, "assertion"))
        add("断言数", len(val) >= gold["assertion_count_min"], f"{len(val)} 条")
    if "must_include" in gold and slug == "paper-nanopub":
        val = as_list(dig(oc, "assertion")) or as_list(dig(pay, "assertion"))
        body = json.dumps(val, ensure_ascii=False)
        add("关键数字保留", gold["must_include"] in body, gold["must_include"])

    if "keep_numbers" in gold and slug == "paper-polish":
        rw = as_list(dig(oc, "rewrites")) or as_list(dig(pay, "rewrites"))
        body = json.dumps(rw, ensure_ascii=False)
        miss = [n for n in gold["keep_numbers"] if n not in body]
        add("改写照抄原数字", not miss, f"missing={miss}")
    if "keep_citations" in gold and slug == "paper-polish":
        rw = as_list(dig(oc, "rewrites")) or as_list(dig(pay, "rewrites"))
        body = json.dumps(rw, ensure_ascii=False)
        miss = [c for c in gold["keep_citations"] if c not in body]
        add("改写照抄引用", not miss, f"missing={miss}")

    return checks


def main(argv):
    pick = [a for a in argv if not a.startswith("--")]
    only_skill = None
    for a in argv:
        if a.startswith("--skill="):
            only_skill = a.split("=", 1)[1]

    cases = sorted(d for d in os.listdir(HERE)
                   if os.path.isdir(os.path.join(HERE, d)) and not d.startswith("_"))
    if pick:
        cases = [c for c in cases if any(c.startswith(p) for p in pick)]

    rows, fails = [], 0
    for name in cases:
        cdir = os.path.join(HERE, name)
        case = load(os.path.join(cdir, "case.json"))
        gold = load(os.path.join(cdir, "gold.json"))
        slug = skill_for(case)
        if only_skill and slug != only_skill:
            continue
        run = run_one(slug, cdir)
        checks = check(gold, run) if gold else []
        bad = [c for c in checks if not c[1]]
        fails += len(bad)
        rows.append({"case": name, "skill": slug, "status": run["result"].get("status"),
                     "rc": run["rc"], "seconds": run["seconds"],
                     "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks],
                     "passed": len(checks) - len(bad), "total": len(checks)})
        flag = "OK " if not bad else "FAIL"
        print(f"{flag} {name:22s} {slug:18s} status={run['result'].get('status','-'):9s} "
              f"{len(checks)-len(bad)}/{len(checks)} checks  {run['seconds']}s")
        for n, o, d in bad:
            print(f"       - {n}: {d}")

    with open(os.path.join(HERE, "report.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated": time.strftime("%Y-%m-%d %H:%M"),
                   "cases": rows, "failed_checks": fails}, fh, ensure_ascii=False, indent=2)

    lines = ["# 自建用例回归结果", "",
             f"生成时间：{time.strftime('%Y-%m-%d %H:%M')}　用例数：{len(rows)}　失败检查项：{fails}", "",
             "| 用例 | 技能 | status | 通过 | 用时 |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['case']} | {r['skill']} | {r['status']} | "
                     f"{r['passed']}/{r['total']} | {r['seconds']}s |")
    bad_rows = [(r["case"], c) for r in rows for c in r["checks"] if not c["ok"]]
    if bad_rows:
        lines += ["", "## 未通过项", "", "| 用例 | 检查 | 实际 |", "|---|---|---|"]
        for case, c in bad_rows:
            lines.append(f"| {case} | {c['name']} | {c['detail'][:120]} |")
    with open(os.path.join(HERE, "report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"\n{len(rows)} cases, {fails} failed checks -> report.md")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
