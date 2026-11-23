"""Run all ten packages against the two real papers and the post-check.

    python run_matrix.py                 # 10 skills x 2 papers + verify.py
    python run_matrix.py --papers 1      # only the single-column paper

The point is regression coverage: every package carries the same core, so a
change in the core must leave all ten still parsing, still validating and still
deterministic.  `verify.py` is run as a second, independent check because a
package can produce a well-formed result.json that still fails its own contract.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SKILLS = os.path.join(ROOT, "skills")
PAPERS = {
    "single": os.path.join(ROOT, "_test", "selftest", "case-single"),
    "twocol": os.path.join(ROOT, "_test", "selftest", "case-twocol"),
}
KIND = {
    "paper-parse": "generic", "paper-translate": "translate", "paper-notes": "generic",
    "paper-nanopub": "generic", "paper-kg": "kg", "paper-polish": "generic",
    "paper-refs": "refs", "paper-intro": "generic", "paper-methods": "generic",
    "paper-latex": "generic",
}


def main(argv):
    which = ["single", "twocol"]
    if "--papers" in argv:
        n = argv[argv.index("--papers") + 1]
        which = ["single"] if n == "1" else ["single", "twocol"]

    slugs = sorted(d for d in os.listdir(SKILLS) if d.startswith("paper-"))
    rows, bad = [], 0
    for slug in slugs:
        for pname in which:
            out = os.path.join(HERE, "_matrix", slug, pname)
            os.makedirs(out, exist_ok=True)
            t0 = time.time()
            r1 = subprocess.run([sys.executable, os.path.join(SKILLS, slug, "scripts", "run.py"),
                                 "--input", PAPERS[pname], "--out", out],
                                capture_output=True, text=True, timeout=600)
            secs = round(time.time() - t0, 1)
            res = {}
            try:
                with open(os.path.join(out, "result.json"), encoding="utf-8") as fh:
                    res = json.load(fh)
            except Exception:
                pass
            r2 = subprocess.run([sys.executable, os.path.join(SKILLS, slug, "scripts", "verify.py"),
                                 "--out", out, "--kind", KIND.get(slug, "generic")],
                                capture_output=True, text=True, timeout=300)
            vok = False
            vpending = False
            try:
                vjson = json.loads(r2.stdout)
                vok = bool(vjson.get("ok"))
                # translate leaves `translation` empty on purpose until the agent
                # fills it; that is a pending step, not a defect of the package
                vpending = any("no segment has a translation" in p
                               for p in (vjson.get("problems") or []))
            except Exception:
                vok = r2.returncode == 0
            ok = r1.returncode == 0 and bool(res) and (vok or vpending)
            bad += 0 if ok else 1
            rows.append({"skill": slug, "paper": pname, "rc": r1.returncode,
                         "status": res.get("status"), "verify": vok, "pending": vpending,
                         "seconds": secs})
            vtxt = "ok" if vok else ("pending" if vpending else "FAIL")
            print(f"{'OK ' if ok else 'FAIL'} {slug:16s} {pname:7s} status={str(res.get('status')):9s} "
                  f"verify={vtxt:8s}{secs}s")

    with open(os.path.join(HERE, "matrix.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated": time.strftime("%Y-%m-%d %H:%M"), "rows": rows, "failed": bad},
                  fh, ensure_ascii=False, indent=2)
    lines = ["# 十包 × 两篇真实论文回归", "",
             f"生成时间：{time.strftime('%Y-%m-%d %H:%M')}　组合数：{len(rows)}　失败：{bad}", "",
             "| 技能 | 论文 | status | verify.py | 用时 |", "|---|---|---|---|---|"]
    for r in rows:
        vtxt = "ok" if r["verify"] else ("pending（译文待填）" if r.get("pending") else "FAIL")
        lines.append(f"| {r['skill']} | {r['paper']} | {r['status']} | {vtxt} | {r['seconds']}s |")
    with open(os.path.join(HERE, "matrix.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"\n{len(rows)} runs, {bad} failing")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
