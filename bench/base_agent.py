"""Base-agent proxy vs paperkit, scored on the same contract.

The rubric hands 25 points to "gain over a baseline agent", 5 of them to
*proving* it.  A model-with-no-skill run cannot be executed here (this repo
makes no model calls), so this script builds the next-closest thing: what an
agent gets when it only has the engine's plain text dump and no layout logic.

    base     `page.get_text("text")` per page, concatenated in file order.
             No block ids, no columns, no tables/figures/formulas, no page map.
    skill    the package output for the same case.

Both are scored by the same function against the same `gold.json`, so the delta
is a property of the pipeline, not of the scorer.

    python3 bench/base_agent.py                      # 默认跑 _test/cases/p01
    python3 bench/base_agent.py --case _test/cases/p01-parse-single
    python3 bench/base_agent.py --json

Caveat, stated up front because it changes how the numbers should be read: a
multimodal model that opens the PDF itself will beat this proxy on tables and
figures.  The proxy is a *lower bound* on "no skill", so the real delta is
smaller than the table below.  It still answers the question the rubric asks --
does the skill add anything a text dump cannot -- without pretending to be a
model run.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, "skills")


# --------------------------------------------------------------------------- #
# the base-agent proxy
# --------------------------------------------------------------------------- #
def base_result(case_dir: str) -> dict:
    import fitz

    pdf = None
    for name in sorted(os.listdir(case_dir)):
        if name.lower().endswith(".pdf"):
            pdf = os.path.join(case_dir, name)
            break
    contract = {}
    try:
        with open(os.path.join(case_dir, "case.json"), encoding="utf-8") as fh:
            contract = json.load(fh).get("output_contract") or {}
    except Exception:
        pass
    if not pdf:
        return {"output_contract": {}, "status": "unable"}

    doc = fitz.open(pdf)
    pages = []
    for i, page in enumerate(doc):
        # the only thing a text dump gives you: characters, in engine order
        pages.append({"page": i + 1, "text": page.get_text("text")})
    doc.close()

    first = next((p["text"].strip().splitlines()[0] for p in pages if p["text"].strip()), "")
    body = "\n".join(p["text"] for p in pages)
    # a text dump has no ids, no columns, no structure: everything below is what
    # such a pipeline can honestly claim
    blocks = [{"id": "", "page": p["page"], "text": p["text"].strip()} for p in pages]
    out = {
        "document": {"title": first[:200], "authors": [], "pages": len(pages),
                     "engine": "text-dump", "section_count": 0},
        "structure": [],
        "content": {"blocks": blocks, "tables": [], "figures": [],
                    "formulas": [], "references": [], "header_footer": []},
        "coverage": {"pages": len(pages), "chars": len(body),
                     "issues": ["no layout pass: columns are concatenated in file order"]},
        "status": "partial",
    }
    if contract:
        # fill exactly the declared keys, so the comparison is key-for-key
        filled = {}
        for key in contract:
            node = out
            parts = key.split(".")
            for part in parts[:-1]:
                node = node.get(part, {}) if isinstance(node, dict) else {}
            filled[key] = node.get(parts[-1], None) if isinstance(node, dict) else None
        out = {"output_contract": filled, "status": "partial"}
    return out


# --------------------------------------------------------------------------- #
# one scorer for both sides
# --------------------------------------------------------------------------- #
def _oc(run: dict) -> dict:
    return run.get("output_contract") or run


def field(oc: dict, name: str):
    """Look a declared key up literally first, then as a nested path."""
    if name in oc:
        return oc[name]
    cur = oc
    for part in name.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _un(v):
    if isinstance(v, dict) and isinstance(v.get("items"), list):
        return v["items"]
    if isinstance(v, dict) and "value" in v:
        return v["value"]
    return v


def _deep(v, key: str):
    """First value stored under `key` anywhere in the result."""
    if isinstance(v, dict):
        if key in v:
            return v[key]
        for item in v.values():
            got = _deep(item, key)
            if got is not None:
                return got
    elif isinstance(v, list):
        for item in v:
            got = _deep(item, key)
            if got is not None:
                return got
    return None


def _slice(oc: dict, key: str):
    """A content slice, wherever the contract happened to put it."""
    for path in (f"content.{key}", key):
        got = field(oc, path)
        if got is not None:
            return _un(got)
    return _un(_deep(oc, key))


def _ordered_text(oc: dict) -> str:
    """The deliverable's own reading order, as one string."""
    blocks = _slice(oc, "blocks")
    if isinstance(blocks, list) and blocks:
        return "\n".join(str(b.get("text") or "") for b in blocks if isinstance(b, dict))
    doc = oc.get("document") if isinstance(oc.get("document"), dict) else {}
    return str(doc.get("full_text") or "")


def score(gold: dict, run: dict) -> dict:
    oc = _oc(run)
    items: dict[str, tuple[bool, str]] = {}

    doc = oc.get("document") or {}
    if not isinstance(doc, dict):
        doc = {}

    if "pages" in gold:
        items["页数"] = (doc.get("pages") == gold["pages"], f"{doc.get('pages')}")
    if "authors" in gold:
        got = [a.strip() for a in (doc.get("authors") or []) if isinstance(a, str)]
        items["作者"] = (got == gold["authors"], f"{len(got)}/{len(gold['authors'])}")
    if "title_words" in gold:
        t = doc.get("title") or ""
        items["标题"] = (all(w in t for w in gold["title_words"]), t[:40])
    if "sections" in gold:
        st = oc.get("structure") or []
        st = _un(st) if not isinstance(st, list) else st
        blob = json.dumps(st, ensure_ascii=False)
        hit = sum(1 for s in gold["sections"] if s.split(" ", 1)[-1][:16] in blob)
        items["章节"] = (hit == len(gold["sections"]), f"{hit}/{len(gold['sections'])}")
    if "tables" in gold:
        tabs = _slice(oc, "tables")
        tabs = tabs if isinstance(tabs, list) else []
        want = gold["tables"][0]
        ok = any(isinstance(t, dict) and t.get("n_rows") == want["n_rows"]
                 and t.get("n_cols") == want["n_cols"]
                 and all(v in json.dumps(t, ensure_ascii=False) for v in want["must_contain"])
                 for t in tabs)
        items["表格"] = (ok, f"{len(tabs)} 张")
    if "formulas" in gold:
        fs = _slice(oc, "formulas")
        fs = fs if isinstance(fs, list) else []
        items["公式"] = (len(fs) >= gold["formulas"]["at_least"], f"{len(fs)} 条")
    if "refs" in gold:
        refs = _slice(oc, "references")
        refs = refs if isinstance(refs, list) else []
        items["参考文献"] = (len(refs) >= gold["refs"]["entries"], f"{len(refs)} 条")
    if "entries" in gold:
        ents = _slice(oc, "entries")
        ents = ents if isinstance(ents, list) else []
        items["参考文献"] = (len(ents) >= gold["entries"], f"{len(ents)} 条")
    if "reading_order" in gold:
        # the rubric's own metric: do the headings appear in reading order?
        order_text = _ordered_text(oc)
        pos = [order_text.find(s) for s in gold["reading_order"]]
        ok = all(p >= 0 for p in pos) and pos == sorted(pos)
        items["阅读顺序"] = (ok, "positions " + str(pos))
    if "kg_must_have" in gold:
        blob = json.dumps(oc, ensure_ascii=False)
        hit = sum(1 for e in gold["kg_must_have"] if e in blob)
        items["实体"] = (hit == len(gold["kg_must_have"]),
                         f"{hit}/{len(gold['kg_must_have'])}")
    iss = oc.get("issues") if isinstance(oc.get("issues"), dict) else {}
    if "citations_without_entry" in gold:
        got = sorted({str(x) for x in (iss.get("citations_without_entry") or [])})
        items["缺失条目"] = (got == sorted(gold["citations_without_entry"]), str(got))
    if "entries_never_cited" in gold:
        got = sorted({str(x) for x in (iss.get("entries_never_cited") or [])})
        items["未被引用"] = (got == sorted(gold["entries_never_cited"]), str(got))
    if "duplicate_pair" in gold:
        pairs = {tuple(sorted((str(d.get("a")), str(d.get("b")))))
                 for d in (iss.get("duplicates") or []) if isinstance(d, dict)}
        want = tuple(sorted(gold["duplicate_pair"]))
        items["重复对"] = (want in pairs, f"{len(pairs)} 对")
    fmt = oc.get("formatted") if isinstance(oc.get("formatted"), dict) else {}
    if gold.get("gbt_has_type_marker"):
        gbt = json.dumps(fmt.get("gb_t_7714") or [], ensure_ascii=False)
        items["GB/T 类型标记"] = (re.search(r"\[[JCMDR]\]", gbt) is not None,
                                 f"{len(fmt.get('gb_t_7714') or [])} 条")
    if gold.get("bibtex_has_inproceedings"):
        bib = json.dumps(fmt.get("bibtex") or [], ensure_ascii=False)
        items["BibTeX 类型"] = ("@inproceedings" in bib,
                                f"{len(fmt.get('bibtex') or [])} 条")

    # contract hygiene: every declared key present, block ids usable, evidence kept
    blocks = _slice(oc, "blocks")
    blocks = blocks if isinstance(blocks, list) else []
    if blocks:
        with_id = sum(1 for b in blocks
                      if isinstance(b, dict) and str(b.get("id") or "").strip())
        items["块锚点"] = (with_id == len(blocks), f"{with_id}/{len(blocks)}")
    ev = run.get("evidence") or []
    items["证据"] = (len(ev) > 0, f"{len(ev)} 条")

    parts = {}
    parts["完整度"] = 100.0 * sum(1 for k, (ok, _) in items.items() if ok) / max(1, len(items))
    hard = [k for k in items if k in ("页数", "作者", "标题", "章节", "表格", "公式",
                                      "参考文献", "阅读顺序", "实体", "缺失条目",
                                      "未被引用", "重复对", "GB/T 类型标记", "BibTeX 类型")]
    parts["正确性"] = 100.0 * sum(1 for k in hard if items[k][0]) / max(1, len(hard))
    has_ids = bool(items.get("块锚点", (False,))[0])
    has_ev = bool(items.get("证据", (False,))[0])
    parts["可核验"] = 100.0 if has_ids and has_ev else (50.0 if (has_ids or has_ev) else 0.0)
    parts["总分"] = round(0.4 * parts["完整度"] + 0.4 * parts["正确性"] + 0.2 * parts["可核验"], 1)
    return {"items": {k: {"ok": ok, "detail": d} for k, (ok, d) in items.items()},
            "scores": {k: round(v, 1) for k, v in parts.items()}}


# --------------------------------------------------------------------------- #
def run_skill(case_dir: str, slug: str) -> dict:
    out = os.path.join(ROOT, "_test", "cases", "_base_vs_skill", slug)
    os.makedirs(out, exist_ok=True)
    subprocess.run([sys.executable, os.path.join(SKILLS, slug, "scripts", "run.py"),
                    "--input", case_dir, "--out", out],
                   check=True, capture_output=True, text=True)
    with open(os.path.join(out, "result.json"), encoding="utf-8") as fh:
        return json.load(fh)


CASES = [("p01-parse-single", "paper-parse"),
         ("p02-parse-twocol", "paper-parse"),
         ("p08-refs", "paper-refs"),
         ("p06-kg", "paper-kg")]


def one(case_dir: str, slug: str) -> dict:
    gold = {}
    with open(os.path.join(case_dir, "gold.json"), encoding="utf-8") as fh:
        gold = json.load(fh)
    sb = score(gold, base_result(case_dir))
    ss = score(gold, run_skill(case_dir, slug))
    rows = [{"item": k, "base": sb["items"][k], "skill": ss["items"][k]} for k in sb["items"]]
    return {"case": os.path.basename(case_dir), "skill": slug, "items": rows,
            "base": sb["scores"], "skill": ss["scores"],
            "delta": {k: round(ss["scores"][k] - sb["scores"][k], 1) for k in sb["scores"]}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=os.path.join(ROOT, "_test", "cases", "p01-parse-single"))
    ap.add_argument("--skill", default="paper-parse")
    ap.add_argument("--all", action="store_true",
                    help="run the four fixed comparison cases and aggregate")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.all:
        runs = [one(os.path.join(ROOT, "_test", "cases", c), s) for c, s in CASES]
        agg = {}
        for k in ("完整度", "正确性", "可核验", "总分"):
            agg[k] = {"base": round(sum(r["base"][k] for r in runs) / len(runs), 1),
                      "skill": round(sum(r["skill"][k] for r in runs) / len(runs), 1)}
            agg[k]["delta"] = round(agg[k]["skill"] - agg[k]["base"], 1)
        report = {"cases": runs, "aggregate": agg,
                  "note": "base = engine text dump only; skill = the package output. "
                          "Same scorer, same gold.json. Offline proxy, not a model run."}
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"{'case':<22}{'base':>7}{'skill':>7}{'delta':>8}")
            for r in runs:
                print(f"{r['case']:<22}{r['base']['总分']:>7}{r['skill']['总分']:>7}"
                      f"{r['delta']['总分']:>+8}")
            a = agg["总分"]
            print(f"{'mean':<22}{a['base']:>7}{a['skill']:>7}{a['delta']:>+8}")
        out = os.path.join(ROOT, "bench", "base_vs_skill.json")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(f"\nwritten {out}")
        return 0

    report = one(args.case, args.skill)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"case = {report['case']}\n")
    print(f"{'检查项':<12}{'base(纯文本)':<22}{'skill':<22}")
    for row in report["items"]:
        b, s = row["base"], row["skill"]
        print(f"{row['item']:<12}{('OK ' if b['ok'] else 'MISS ') + b['detail']:<22}"
              f"{('OK ' if s['ok'] else 'MISS ') + s['detail']:<22}")
    print()
    for k in ("完整度", "正确性", "可核验", "总分"):
        print(f"{k:<6} base={report['base'][k]:>6}  skill={report['skill'][k]:>6}  "
              f"delta={report['delta'][k]:>+6}")
    out = os.path.join(ROOT, "bench", "base_vs_skill.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(f"\nwritten {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
