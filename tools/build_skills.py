"""Stamp the ten skill packages from one core.

    python3 tools/build_skills.py            # write every package
    python3 tools/build_skills.py --check     # verify size/file limits only

Each package is self-contained: the platform installs only the submitted
directory, so `scripts/pk` is a vendored copy of `core/paperkit`.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from skills_manifest import SKILLS, COMMON_ENV  # noqa: E402

SKILL_MD = """---
name: {name}
description: {description}
version: 1.0.0
license: MIT
---

# {title} — {challenge}

## 用途

{description}

本 Skill 交付的不是一段“看起来像结果”的文本，而是一份**可复核的结构化结果**：
每条结论都带页码与块 id（`p07-b012` 形式），读不出的部分如实标注，而不是猜。

## 触发条件

{when}

不适用：与文献无关的任务、纯图片问答、需要联网检索的任务。

## 输入

| 位置 | 内容 |
|---|---|
| `/input/case.json` | 案例元信息，可能包含 `output_contract` 字段清单 |
| `/input/task.md` | 本次任务说明 |
| `/input/*.pdf` | 原始论文（无预抽取文本层）|
| `/input/*` | 其他材料：docx / tex / bib / csv / json / md |

## 快速开始

**先定位本 Skill 的安装目录**。评测环境把它装在 `/skills/weekly-skill`，本地可能在别处，
所以不要假设当前工作目录：脚本按 `SKILL.md` 所在目录相对定位。

```bash
# 0) 定位：官方安装在 /skills/weekly-skill，找不到再就近搜索
SKILL_DIR=/skills/weekly-skill
[ -f "$SKILL_DIR/SKILL.md" ] || SKILL_DIR="$(
  find /skills /app /workspace /opt -maxdepth 5 -name SKILL.md 2>/dev/null | head -1 | xargs -r dirname
)"
cd "$SKILL_DIR" || exit 1

# 1) 一次跑完解析 + 组包
python3 scripts/run.py --input /input --out /app/output

# 2) 看产物
ls /app/output          # doc.json doc.md coverage.json result.json run.log

# 3) 自检
python3 scripts/verify.py --out /app/output --kind {verify_kind}
```

只依赖 Python 标准库；有 PyMuPDF 时用它做主力引擎，没有则自动退化到 pdfplumber / pypdf /
poppler，缺什么会在 `run.log` 和 `coverage.json` 里写明，不会静默降级。

`run.py` 是幂等的，可重复执行；`--no-ocr` 可跳过 OCR（更快，但扫描页会空）。

## 处理流程

{method}

## 输出

{output}

`result.json` 同时保留 `case_id`、`status`、`evidence`、`uncertainty`、`provenance`，
以及 `case.json` 里声明的 `output_contract` 字段。字段名与内部切片对不上时按语义匹配回填，
**仍为空才留 `null`**，并在 `uncertainty.inferred_fields` 里逐项说明是怎么推出来的。

## 最小调用示例

{example}

## 异常处理

{failure}

## 适用边界

{limits}

## 文件清单

```
SKILL.md
environment/resources.yaml     # 依赖与预置运行时说明
scripts/run.py                 # 入口
scripts/compose_all.py         # 题型组装
scripts/verify.py              # 事后核验
scripts/pk/                    # paperkit 内核（解析、版面、证据、结果）
examples/case.example.json     # 最小输入示例（示例，非正式案例）
examples/result.example.json   # 示意输出（示例，非正式案例）
GITHUB_URL.txt                 # 公开仓库链接
```

## 版本与依赖

- paperkit 1.0.0（纯标准库；按可用性依次使用 PyMuPDF / pdfplumber / pypdf / poppler）
- 无网络依赖；不下载模型；OCR 仅在系统存在 `tesseract` 或 `ocr-tool` 时启用
- 资源约束：≤50 个 UTF-8 文本文件，单文件 ≤500KB，合计 ≤2MB，无符号链接
"""


def render_md(skill: dict) -> str:
    return SKILL_MD.format(
        name=skill["name"],
        description=skill["description"],
        title=skill["title"],
        challenge=skill["challenge"],
        when="\n".join(f"- {w}" for w in skill["when"]),
        method=skill["method"],
        output=skill["output"],
        example=skill["example"],
        failure=skill["failure"],
        limits=skill["limits"],
        verify_kind="translate" if skill["mode"] == "translate" else "generic",
    )


def write_examples(dest: str, skill: dict, root: str) -> None:
    os.makedirs(dest, exist_ok=True)
    case = {
        "case_id": "example-not-a-real-case",
        "note": "最小输入示例；正式案例由平台提供，此处仅说明接口，不代表真实评测数据。",
        "topic": skill["challenge"],
        "output_contract": {
            "document": "parsed structure",
            "evidence": "list of block-level anchors",
            "status": "complete|partial|unable",
        },
    }
    with open(os.path.join(dest, "case.example.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(case, fh, ensure_ascii=False, indent=2)
    result = {
        "case_id": "example-not-a-real-case",
        "status": "partial",
        "output_contract": {"document": None, "evidence": [], "status": "partial"},
        "evidence": [{"block": "p01-b001", "page": 1, "quote": "（示例引用，非正式案例结果）"}],
        "uncertainty": {"notes": ["这是接口示意，不是任何真实案例的答案"], "missing": []},
        "provenance": {"pdf": "example.pdf", "pages": 0, "engine": "paperkit 1.0.0"},
    }
    with open(os.path.join(dest, "result.example.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)


def write_resources(dest: str) -> None:
    os.makedirs(dest, exist_ok=True)
    with open(os.path.join(dest, "resources.yaml"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# Declared runtime for this skill. Bundled paths are relative to this directory.\n")
        fh.write(COMMON_ENV)


def build_one(skill: dict, root: str) -> dict:
    out = os.path.join(root, "skills", skill["slug"])
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "scripts"), exist_ok=True)

    shutil.copytree(os.path.join(root, "core", "paperkit"), os.path.join(out, "scripts", "pk"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(os.path.join(root, "core", "run.py"), os.path.join(out, "scripts", "run.py"))
    shutil.copy2(os.path.join(root, "core", "compose_all.py"), os.path.join(out, "scripts", "compose_all.py"))
    shutil.copy2(os.path.join(root, "core", "verify.py"), os.path.join(out, "scripts", "verify.py"))

    with open(os.path.join(out, "SKILL.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_md(skill))
    with open(os.path.join(out, "GITHUB_URL.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("https://github.com/liang-92/bohrium-campus-skills/tree/main/skills/%s\n" % skill["slug"])
        fh.write("SKILL.md\n")
    write_resources(os.path.join(out, "environment"))
    write_examples(os.path.join(out, "examples"), skill, root)

    # the package carries its own profile so `run.py` needs no flags
    with open(os.path.join(out, "scripts", "profile.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(skill["mode"] + "\n")

    files, total, biggest = 0, 0, ("", 0)
    for dirpath, _, filenames in os.walk(out):
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            size = os.path.getsize(p)
            files += 1
            total += size
            if size > biggest[1]:
                biggest = (os.path.relpath(p, out), size)
    return {"slug": skill["slug"], "files": files, "bytes": total, "biggest": biggest}


def check_limits(rows) -> list:
    problems = []
    for r in rows:
        if r["files"] > 50:
            problems.append(f"{r['slug']}: {r['files']} files > 50")
        if r["biggest"][1] > 500 * 1024:
            problems.append(f"{r['slug']}: {r['biggest'][0]} {r['biggest'][1]}B > 500KB")
        if r["bytes"] > 2 * 1024 * 1024:
            problems.append(f"{r['slug']}: total {r['bytes']}B > 2MB")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    rows = []
    for s in SKILLS:
        if not args.check:
            rows.append(build_one(s, ROOT))
        else:
            out = os.path.join(ROOT, "skills", s["slug"])
            files, total, biggest = 0, 0, ("", 0)
            for dirpath, _, filenames in os.walk(out):
                for fn in filenames:
                    p = os.path.join(dirpath, fn)
                    size = os.path.getsize(p)
                    files += 1
                    total += size
                    if size > biggest[1]:
                        biggest = (os.path.relpath(p, out), size)
            rows.append({"slug": s["slug"], "files": files, "bytes": total, "biggest": biggest})
    problems = check_limits(rows)
    for r in rows:
        print(f"{r['slug']:16s} files={r['files']:3d} total={r['bytes']/1024:7.1f}KB "
              f"biggest={r['biggest'][0]} {r['biggest'][1]/1024:.0f}KB")
    if problems:
        print("\nLIMIT PROBLEMS:")
        for p in problems:
            print(" -", p)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
