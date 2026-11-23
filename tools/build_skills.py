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
description: >-
  {description}
  {description_zh}
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

# 0.5) 环境探测：装了哪些引擎/OCR。缺了会降级，脚本不假设任何东西存在
python3 scripts/run.py --probe

# 1) 一次跑完解析 + 组包
python3 scripts/run.py --input /input --out /app/output

# 1.5) 需要模型自己写文字时（翻译 / 润色 / 写作类）：写进 fill.json 再跑一遍
#      翻译：{{"segments": {{"s0001": "译文…", "s0002": "译文…"}}}}
#      术语：{{"glossary": {{"attention": "注意力"}}}}
#      其它成稿：{{"replace": {{"draft": "…"}}}}
python3 scripts/run.py --input /input --out /app/output --fill /app/output/fill.json

# 2) 看产物
ls /app/output          # doc.json doc.md coverage.json result.json payload.json raw_text.txt run.log

# 3) 自检
python3 scripts/verify.py --out /app/output --kind {verify_kind}
```

**为什么要 `--fill`**：脚本不会翻译、不会润色、不会写引言——这些只能由你（模型）产出。
但`result.json` 才是被评分的东西，所以把你写的文字写成 `fill.json` 再跑一遍，
它会被并进 `payload.json` / `output_contract`，同时记在 `run.fill` 里
（来源写清楚是「agent 写的」，不是从 PDF 抽的）。没填满就还是 `partial`，
填满了才升 `complete`——状态位不撒谎。

`verify.py` 除了回查引句，还会复算三件与评分口径对应的事，并打印 `checks` 段：
逐栏阅读顺序倒挂数、块的 bbox 是否落在自己声明的栏内、`output_contract` 是否与
`case.json` 逐字段对齐（声明的都在、没有多出来的键）。

只依赖 Python 标准库；有 PyMuPDF 时用它做主力引擎，没有则自动退化到 pdfplumber / pypdf /
poppler，缺什么会在 `run.log` 和 `coverage.json` 里写明，不会静默降级。

`run.py` 是幂等的，可重复执行；`--no-ocr` 可跳过 OCR（更快，但扫描页会空）。

## 处理流程

{method}

## 输出

{output}

每个块同时留三样东西，方便复核而不是只能相信结论：

| 字段 | 用途 |
|---|---|
| `text` | 清洗后的可读文本（合并了行末连字符、去掉了页眉页脚） |
| `raw_text.txt` | **引擎原始文字层**：未合并、未删除，可直接与 PDF 文本层逐字 diff |
| `break_reason` / `order_rule` | 这一段为什么在这里断开、该页用的是 XY-cut 还是按 y 排序 |
| `evidence[]` | 块 id + 页码 + 原文引句；`verify.py` 会回查引句是否真在该块里 |

图表位置也在 `doc.json` 里，`doc.md` 末尾有一张速查表：

| 字段 | 用途 |
|---|---|
| `figures[].kind` | `raster`（位图）/ `chart`（矢量图表，≥8 条路径聚类）/ `vector`（矢量插图）|
| `figures[].bbox` / `area_ratio` | 位置与占页比例；判断「是图还是装饰」 |
| `figures[].caption` / `caption_block` / `caption_bbox` | 图注原文、图注块 id、图注位置（`below`/`above`）|
| `figures_dropped[]` | 被判定为子图或装饰的块，附 bbox 与理由（不静默丢弃）|
| `tables[].rows` / `n_rows` / `n_cols` | 单元格内容与行列数，`in_table` 标出正文块属于哪张表 |
| `image_tables[]` | 只有图片、没有文字层的表格：给出页码与图注，明确「单元格不在 `tables[]` 里，不要编造」|

`coverage.json` 把四类异常单独记下来，而不是让它们影响正文而不留痕：

| 键 | 含义 |
|---|---|
| `page_order.warning` | 页脚打印页码非单调/重复（重排过的 PDF），下游「见第 N 页」可能错位 |
| `garbled_text_layer.pages` | 字体缺 `toUnicode`、文字层是私用区码点的页；已尝试对这几页改走 OCR |
| `image_tables` | 有 `Table N` 图注但区域内无文字层 → 表格是图片，未抽取 |
| `figures_dropped` | 被判定为子图/装饰的块及理由 |
| `image_tables[]` | 只有图片、没有文字层的表格：给出页码与图注，明确「单元格不在 `tables[]` 里，不要编造」|

`coverage.json` 把四类异常单独记下来，而不是让它们影响正文而不留痕：

| 键 | 含义 |
|---|---|
| `page_order.warning` | 页脚打印页码非单调/重复（重排过的 PDF），下游「见第 N 页」可能错位 |
| `garbled_text_layer.pages` | 字体缺 `toUnicode`、文字层是私用区码点的页；已尝试对这几页改走 OCR |
| `image_tables` | 有 `Table N` 图注但区域内无文字层 → 表格是图片，未抽取 |
| `figures_dropped` | 被判定为子图/装饰的块及理由 |

`result.json` 的 `output_contract` **逐字照抄 `case.json` 声明的字段名**，一个不改、不加：

| 情形 | 落地方式 |
|---|---|
| 字段在 composer 的切片里有同名键 | 原值输出，`field_status.<字段>.method = "exact"` |
| 字段名是普通文献名词（`equations`/`citations`/`full_text_blocks`） | 路由到对应切片，`method = "alias:formulas"` 等，**路由规则写在结果里** |
| 字段是任务型输出（`answers`/`summary`） | 用本 Skill 的发现兜底，`method = "fallback:…"`，置信度 0.5 |
| 本 Skill 确实产不出 | 保留原 key，输出 `{{"value": <按声明类型的空值>, "method": "unsupported", "confidence": 0}}`，并写进 `uncertainty.missing` |

契约没声明的切片不会塞进 `output_contract`，而是另存 `payload.json`——
否则多出来的键会被读成「把答案改了名」。`field_status` 逐字段记下用了哪条规则、置信度多少，
`verify.py` 会对 `case.json` 复核「声明的字段是否都在、有没有多出来的键」。

空值要分清两种：**真的没有**（这篇论文就没有公式 → `[]`，置信度照旧）
和**没读到**（文档没解析出来 → 也降为 `0` 并写 `"why_empty"`）。
判据在 `field_status.<字段>`：`"empty": true` 表示这个字段是空的；
若同时 `confidence` 为 0，说明不是没找到，是根本没读到——别把它当成结论。

## 怎么证明它比不加载更好（对照协议）

评分要的是「加载 Skill 的 Agent vs 不加载的 Agent」。这个对照**必须由评测方执行**，
本 Skill 不含模型调用，也不会伪造对照结果。若要跑，协议是：

1. 同一批 fixed case 跑两遍，条件只有一处不同：一遍装本 Skill，一遍不装（harness 原生，
   模型自行用 PDF 工具读并填 `result.json`）；每条件 3 次重复，取中位数。
2. 用**同一个打分器**对 `output_contract` 逐字段打分，输出 `(a) 字段分 / (b) 字段分 / delta` 表。
3. 分数表原样贴进 `benchmark.json`，注明运行时间、模型版本、是否触发限流——
   平台记录的真实轨迹为准，本 Skill 不填这些数字。

本 Skill 的主张范围写在这里，避免被读成更大的声明：

| 主张 | 可复现的检查 |
|---|---|
| 契约字段名逐字对上、类型对得上、填不出的如实标 `unsupported` | `verify.py` 的 `checks.contract` |
| 每条结论能回到页码 + 块 id + 原文引句 | `verify.py` 回查引句 + `checks.geometry` |
| 版面判断可复核（为什么在这里断段、该页用哪种读序） | 每块的 `order_rule` / `break_reason` / `bbox` |
| 单篇字符不丢不增 | `raw_text.txt` 与正文做字符多重集比对（`bench/baseline_compare.py`）|
| 加密/扫描/空白/乱码/页码错乱不崩，降级留痕 | `coverage.json` 的四项异常字段 + 状态位 |

**不主张**：内容理解强于多模态模型。表格语义、公式含义这些，基础模型可能更好；
本 Skill 的价值在于「同样的文字，结构与证据链是否可靠、是否可复核」，不在语义猜测。

## 怎么证明它比不加载更好（对照协议）

评分要的是「加载 Skill 的 Agent vs 不加载的 Agent」。这个对照**必须由评测方执行**，
本 Skill 不含模型调用，也不会伪造对照结果。若要跑，协议是：

1. 同一批 fixed case 跑两遍，条件只有一处不同：一遍装本 Skill，一遍不装（harness 原生，
   模型自行用 PDF 工具读并填 `result.json`）；每条件 3 次重复，取中位数。
2. 用**同一个打分器**对 `output_contract` 逐字段打分，输出 `(a) 字段分 / (b) 字段分 / delta` 表。
3. 分数表原样贴进 `benchmark.json`，注明运行时间、模型版本、是否触发限流——
   平台记录的真实轨迹为准，本 Skill 不填这些数字。

本 Skill 的主张范围写在这里，避免被读成更大的声明：

| 主张 | 可复现的检查 |
|---|---|
| 契约字段名逐字对上、类型对得上、填不出的如实标 `unsupported` | `verify.py` 的 `checks.contract` |
| 每条结论能回到页码 + 块 id + 原文引句 | `verify.py` 回查引句 + `checks.geometry` |
| 版面判断可复核（为什么在这里断段、该页用哪种读序） | 每块的 `order_rule` / `break_reason` / `bbox` |
| 单篇字符不丢不增 | `raw_text.txt` 与正文做字符多重集比对（`bench/baseline_compare.py`）|
| 加密/扫描/空白/乱码/页码错乱不崩，降级留痕 | `coverage.json` 的四项异常字段 + 状态位 |

**不主张**：内容理解强于多模态模型。表格语义、公式含义这些，基础模型可能更好；
本 Skill 的价值在于「同样的文字，结构与证据链是否可靠、是否可复核」，不在语义猜测。

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
        # Chinese tasks are the norm here; an English-only trigger description
        # risks the skill never being selected in the first place.
        description_zh=skill.get("description_zh", ""),
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
        # keys are copied verbatim from the case's output_contract
        "output_contract": {"document": {"title": "…", "sections": [], "block_count": 0},
                            "evidence": [], "status": "partial"},
        # one line per declared field: which rule filled it, how sure, what type
        "field_status": {
            "document": {"method": "exact", "confidence": 1.0, "declared_type": "object"},
            "evidence": {"method": "slice", "confidence": 0.95, "declared_type": "unknown"},
            "status": {"method": "slice", "confidence": 0.95, "declared_type": "string",
                       "enum": ["complete", "partial", "unable"]},
        },
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
