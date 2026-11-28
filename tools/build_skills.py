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

# 0.6) LaTeX：默认检测到 TeX 引擎就编译；只做静态检查时显式关闭
#      PK_TEX_COMPILE=0 python3 scripts/run.py --input /input --out /app/output

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

每个块同时留四样东西，方便复核而不是只能相信结论：

| 字段 | 用途 |
|---|---|
| `text` | 清洗后的可读文本（合并了行末连字符、去掉了页眉页脚） |
| `text_raw` | **该块对应的引擎原始行**：未合并、未删除，可与 PDF 文本层逐字 diff |
| `raw_text.txt` | 全篇原始文字层快照，在清洗之前导出，用于整篇比对 |
| `engine` | 这一块由哪个引擎读到（如 `pymupdf 1.24` / `ocr`），OCR 页与文字层页可区分 |
| `order_rule` | 该页用 XY-cut 分栏，还是按 y 排序（`xy-cut` / `naive-y`） |
| `para_break_reason` + `break_at` | 为什么在这里断开，以及触发断段的两行 y 坐标（可回放） |
| `hyphen_merged` + `hyphen_pair` | 是否合并了行末连字符、被合并的两半是什么 |
| `evidence[]` | 块 id + 页码 + 原文引句；`verify.py` 会回查引句是否真在该块里 |

图表位置也在 `doc.json` 里，`doc.md` 末尾有一张速查表：

| 字段 | 用途 |
|---|---|
| `figures[].kind` | `raster`（位图）/ `chart`（矢量图表，≥8 条路径聚类）/ `vector`（矢量插图）|
| `figures[].bbox` / `area_ratio` | 位置与占页比例；判断「是图还是装饰」 |
| `figures[].caption` / `caption_block` / `caption_bbox` | 图注原文、图注块 id、图注位置（`below`/`above`）|
| `figures_dropped[]` | 被判定为子图或装饰的块，附 bbox 与理由（不静默丢弃）|
| `tables[].rows` / `n_rows` / `n_cols` | 单元格内容与行列数，`in_table` 标出正文块属于哪张表 |
| `image_tables[]` | 只有图片、没有文字层的表格：给出页码与图注，明确「单元格不在 `tables[]` 里，不要补写」|

`coverage.json` 把异常单独记下来，而不是让它们影响正文而不留痕：

| 键 | 含义 |
|---|---|
| `page_order.warning` | 页脚打印页码非单调/重复（重排过的 PDF），下游「见第 N 页」可能错位 |
| `garbled_text_layer.pages` | 字体缺 `toUnicode`、文字层是私用区码点的页；已尝试对这几页改走 OCR |
| `image_tables` | 有 `Table N` 图注但区域内无文字层 → 表格是图片，未抽取 |
| `figures_dropped` | 被判定为子图/装饰的块及理由 |
| `verbatim` | 字符账本：文字层字符数 / 块内字符数 / 丢失 / 多出 / 覆盖率；覆盖率低于 0.995 会写进 `issues` |
| `header_footer[]` | 被剔除的页眉页脚逐条保留（页码、文本、bbox）——是标记，不是销毁 |

`result.json` 的 `output_contract` **逐字照抄 `case.json` 声明的字段名**，一个不改、不加：

| 情形 | 落地方式 |
|---|---|
| 字段在 composer 的切片里有同名键 | 原值输出，`field_status.<字段>.method = "exact"` |
| 字段名是普通文献名词（`equations`/`citations`/`full_text_blocks`） | 路由到对应切片，`method = "alias:formulas"` 等，**路由规则写在结果里** |
| 字段的 `items` 里写着 `cells`/`header`/`rows` 这类形状词 | 按**契约自己的 schema** 路由到表格切片，`method = "items-shape:tables"` |
| 字段是任务型输出（`answers`/`summary`） | 用本 Skill 的发现兜底，`method = "fallback:…"`，置信度 0.5 |
| 本 Skill 确实产不出 | 保留原 key，输出 `{{"value": <按声明类型的空值>, "method": "unsupported", "confidence": 0}}`，并写进 `uncertainty.missing` |

契约没声明的切片不会塞进 `output_contract`，而是另存 `payload.json`——
否则多出来的键会被读成「把答案改了名」。`field_status` 逐字段记下用了哪条规则、置信度多少，
`verify.py` 会对 `case.json` 复核「声明的字段是否都在、有没有多出来的键」。

空值要分清两种：**真的没有**（这篇论文就没有公式 → `[]`，置信度照旧）
和**没读到**（文档没解析出来 → 也降为 `0` 并写 `"why_empty"`）。
判据在 `field_status.<字段>`：`"empty": true` 表示这个字段是空的；
若同时 `confidence` 为 0，说明不是没找到，是根本没读到——别把它当成结论。

`verify.py` 打印三段：`checks`（读自己的 `doc.json`：几何、决策回放、契约对齐）、
`independent`（**重开 PDF** 重抽文字层做字符多重集比对、逐格核对表格单元格是否在该页、
再用 pypdf 这个第二实现交叉验证字符量）、`problems`（要逐条修）。前者是自洽，后者才可能与结论矛盾。

## 怎么证明它比不加载更好（对照协议）

评分项要的是「加载 Skill 的 Agent vs 不加载的 Agent」。本 Skill 不含模型调用，
能离线做的那一半已经做了，脚本与结果都在仓库里：

{bench}

来源 `bench/base_agent.py` + `bench/base_vs_skill.json`，**离线对照，不是平台成绩**。
`base` 是「不加载 Skill」的下界代理：只给引擎的 `page.get_text("text")` 纯文本转储，
没有块 id、没有分栏、没有表格/图/公式，也没有证据。真实的多模态模型会比这个代理强，
所以 delta 只会更小——这也是为什么这里给的是**下界**而不是宣传数字。

真正的模型对照仍需评测方执行：同一批 case、只差是否安装本 Skill、用同一个打分器逐字段打分、
每条件重复取中位数；平台记录的真实轨迹为准，本 Skill 不填这些数字。

主张范围写在这里，避免被读成更大的声明：

| 主张 | 可复现的检查 |
|---|---|
| 契约字段名逐字对上、类型对得上、填不出的如实标 `unsupported` | `verify.py` 的 `checks.contract` |
| 每条结论能回到页码 + 块 id + 原文引句 | `verify.py` 回查引句 + `checks.geometry` |
| 版面判断可复核（为何在此断段、该页用哪种读序） | `checks.decisions`：回放 `caption-start` / `vertical-gap` / `block-size-cap` / `hyphen_merged` |
| 字符不丢不增（逐字一致） | `independent`：重开 PDF、重抽文字层、字符多重集比对（含页眉页脚去重） |
| 表格单元格确实在该页 | `independent.table_cells`：逐格在该页文字层里查找 |
| 加密/扫描/空白/乱码/页码错乱不崩，降级留痕 | `coverage.json` 的异常字段 + 状态位 |

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


DEFAULT_BENCH = """本 Skill 的固定用例还不进离线对照：它的产出要由 Agent 用 `fill.json` 写入
译文 / 改写 / 成稿后才完整，纯脚本跑分只会低估，给数字反而误导。
协议与脚本在 `bench/base_agent.py`，评测方按同一 case 跑两遍即可复现。"""


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
        bench=skill.get("bench") or DEFAULT_BENCH,
        output=skill["output"],
        example=skill["example"],
        failure=skill["failure"],
        limits=skill["limits"],
        verify_kind="translate" if skill["mode"] == "translate" else "generic",
    )


EXAMPLE_PAYLOAD = {
    "parse": {"document": {"title": "Attention Is All You Need", "pages": 15, "engine": "pymupdf"},
              "structure": [{"level": 1, "title": "3 Model Architecture", "page": 2, "block": "p02-b008"}],
              "content": {"blocks": [{"id": "p03-b005", "page": 3, "column": 0,
                                      "section": "3.1 Encoder and Decoder Stacks",
                                      "text": "The encoder is composed of a stack of N = 6 identical layers."}]}},
    "translate": {"segments": [{"seg": "s0001", "block": "p01-b005", "page": 1, "section": "Abstract",
                                "source": "The dominant sequence transduction models are based on recurrent networks.",
                                "protected": {"numbers": [], "citations": []},
                                "translation": "主流的序列转换模型基于循环神经网络。"}],
                  "glossary": [{"term": "attention", "count": 42, "zh": "注意力"}]},
    "notes": {"paper_card": {"title": "Attention Is All You Need",
                             "research_question": [{"text": "Can attention alone replace recurrence?",
                                                    "block": "p01-b013", "page": 1}],
                             "findings": [{"text": "28.4 BLEU on WMT 2014 En-De", "block": "p01-b013"}]},
              "section_notes": [{"section": "3 Model Architecture", "page": 2, "block": "p02-b008"}]},
    "nanopub": {"assertions": [{"id": "a1", "claim": "self-attention replaces recurrence",
                                "type": "method", "quote": "dispensing with recurrence and convolutions entirely",
                                "block": "p01-b013", "page": 1}],
                "provenance": {"pdf": "1706.03762v7.pdf", "block": "p01-b013"}},
    "kg": {"nodes": [{"id": "n001", "label": "Transformer", "type": "method",
                      "evidence": [{"block": "p01-b013", "page": 1}]}],
           "edges": [{"source": "n001", "target": "n002", "relation": "uses",
                      "evidence": {"block": "p05-b013", "quote": "The Transformer uses multi-head attention"}}]},
    "polish": {"genre": "journal-article",
               "sentence_issues": [{"block": "p02-b014", "sentence": "This paper proposes a very novel method.",
                                    "flags": ["hedging", "intensifier"], "words": 8}],
               "guardrails": ["do not change numbers, units or citation keys"]},
    "refs": {"entries": [{"n": 1, "authors": "Jimmy Lei Ba, Jamie Ryan Kiros, Geoffrey E Hinton",
                          "title": "Layer normalization", "year": "2016", "venue": "arXiv",
                          "type": "EB/OL", "doi": ""}],
             "issues": {"citations_without_entry": [], "entries_never_cited": ["40"],
                        "duplicates": [], "numbering_gaps": []}},
    "intro": {"problem_statements": [{"text": "Recurrent models preclude parallelization within a sequence.",
                                      "block": "p01-b013", "page": 1}],
              "gap_statements": [{"text": "Attention had not been used without recurrence.",
                                  "block": "p01-b014", "page": 1}],
              "draft": {"status": "written",
                        "paragraphs": [{"role": "context", "text": "（示例段落）", "citations": ["1"]}]}},
    "methods": {"parameters": [{"name": "N", "value": "6", "block": "p02-b020", "page": 2}],
                "datasets": [{"name": "WMT 2014 English-German", "block": "p07-b006", "page": 7}],
                "reproducibility_checklist": [{"item": "random seeds", "found": False}]},
    "latex": {"files": ["main.tex", "latex/main.tex"],
              "compile": {"attempted": True, "engine": "pdflatex", "ok": True, "pdf": True,
                          "passes": 2, "errors": []},
              "tex": "\\documentclass{article}\\begin{document}...\\end{document}"},
}


def write_examples(dest: str, skill: dict, root: str) -> None:
    os.makedirs(dest, exist_ok=True)
    example = EXAMPLE_PAYLOAD.get(skill["mode"], {})
    contract = {k: ("example value, see result.example.json" if not isinstance(v, list) else
                    f"list of {k.rstrip('s')}") for k, v in example.items()}
    contract["status"] = "complete|partial|unable"
    case = {
        "case_id": "example-not-a-real-case",
        "note": "最小输入示例；正式案例由平台提供，此处仅说明接口，不代表真实评测数据。",
        "topic": skill["challenge"],
        "output_contract": contract,
    }
    with open(os.path.join(dest, "case.example.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(case, fh, ensure_ascii=False, indent=2)
    result = {
        "case_id": "example-not-a-real-case",
        "status": "complete",
        # keys are copied verbatim from the case's output_contract
        "output_contract": dict(example, status="complete"),
        "field_status": {k: {"method": "example", "confidence": 1.0}
                         for k in list(example) + ["status"]},
        "evidence": [{"block": "p01-b001", "page": 1, "quote": "（示例引用，非正式案例结果）"}],
        "uncertainty": {"notes": ["这是接口示意，字段值不是任何真实案例的答案"], "missing": []},
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
    os.makedirs(os.path.join(out, "scripts"), exist_ok=True)

    # Overwrite in place instead of `rmtree` + `copytree`.  The desktop's
    # safe-delete hook refuses to trash a package directory ("Some operations
    # were aborted"), and the half-finished build left new `compose_all.py`
    # next to a month-old `pk/`.  Copying over the top is idempotent and leaves
    # nothing behind that the purge below does not already sweep.
    src_pk = os.path.join(root, "core", "paperkit")
    dst_pk = os.path.join(out, "scripts", "pk")
    shutil.copytree(src_pk, dst_pk, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for dirpath, _dirs, names in os.walk(dst_pk):
        rel = os.path.relpath(dirpath, dst_pk)
        for name in names:
            src = os.path.join(src_pk, rel, name)
            if not os.path.exists(src):
                try:
                    os.remove(os.path.join(dirpath, name))
                except OSError:
                    pass
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

    # A previous run of the packaged scripts leaves `__pycache__` behind, and
    # those .pyc files are byte-code for *this* interpreter: useless on the
    # evaluator's Linux box, but they still count against the 50-file / 2MB
    # budget.  Ship sources only.
    removed = purge_pycache(out)
    files, total, biggest, stale = bag(out)
    return {"slug": skill["slug"], "files": files, "bytes": total, "biggest": biggest,
            "pycache_removed": removed, "pycache_stale": stale}


def purge_pycache(root: str) -> int:
    removed = 0
    for dirpath, dirnames, _ in os.walk(root):
        for d in list(dirnames):
            if d == "__pycache__":
                for dp, _, fns in os.walk(os.path.join(dirpath, d)):
                    removed += len(fns)
                shutil.rmtree(os.path.join(dirpath, d), ignore_errors=True)
                dirnames.remove(d)
    return removed


def bag(root: str) -> tuple:
    """Count what would actually be submitted: sources, not byte-code."""
    files, total, biggest, pyc = 0, 0, ("", 0), 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            if fn.endswith(".pyc"):
                pyc += 1
                continue
            p = os.path.join(dirpath, fn)
            size = os.path.getsize(p)
            files += 1
            total += size
            if size > biggest[1]:
                biggest = (os.path.relpath(p, root), size)
    return files, total, biggest, pyc


def check_limits(rows) -> list:
    problems = []
    for r in rows:
        if r.get("pycache_stale"):
            problems.append(f"{r['slug']}: {r['pycache_stale']} stale .pyc file(s) in the package "
                            f"(byte-code for this Python, dead weight on the evaluator)")
        if r["files"] > 50:
            problems.append(f"{r['slug']}: {r['files']} files > 50")
        if r["biggest"][1] > 500 * 1024:
            problems.append(f"{r['slug']}: {r['biggest'][0]} {r['biggest'][1]}B > 500KB")
        if r["bytes"] > 2 * 1024 * 1024:
            problems.append(f"{r['slug']}: total {r['bytes']}B > 2MB")
    return problems


def front_matter(path: str) -> dict:
    """Parse the YAML block between the `---` fences of a SKILL.md.

    Uses PyYAML when it is installed and a small strict fallback otherwise, so
    the build never silently skips the check on a machine without PyYAML.  The
    fallback understands exactly what this generator emits: top-level `key:`
    lines, `>-` folded scalars and single-line values.  Anything else is
    reported as unparsed rather than guessed at.
    """
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    if not raw.startswith("---"):
        return {"_error": "does not start with a --- fence"}
    end = raw.find("\n---", 3)
    if end < 0:
        return {"_error": "no closing --- fence"}
    block = raw[3:end].strip("\n")
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(block)
        return data if isinstance(data, dict) else {"_error": "front matter is not a mapping"}
    except ImportError:
        pass
    except Exception as exc:  # a real YAML error: report it, do not fall back
        return {"_error": f"yaml: {type(exc).__name__}: {exc}"}
    out: dict = {}

    def flush(key, buf):
        if key:
            out[key] = " ".join(buf).strip()

    key, buf = None, []
    for line in block.splitlines():
        if not line.strip():
            continue
        if line[:1] in (" ", "\t") and key:      # folded continuation of `>-`
            buf.append(line.strip())
            continue
        flush(key, buf)
        key, buf = None, []
        if ":" not in line:
            return {"_error": f"not a `key: value` line: {line[:40]!r}"}
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if v in (">-", ">", "|", "|-"):
            key = k
            continue
        out[k] = v.strip('"').strip("'")
    flush(key, buf)
    return out


def check_meta(slugs) -> list:
    """Every SKILL.md must parse, and its name must be the directory name.

    The evaluator loads a Skill by reading this block, so a metadata problem is
    not a cosmetic one: an unparseable `---` block means the Skill never loads
    and every point behind it is lost before the code runs.
    """
    problems = []
    for slug in slugs:
        path = os.path.join(ROOT, "skills", slug, "SKILL.md")
        if not os.path.exists(path):
            problems.append(f"{slug}: no SKILL.md")
            continue
        meta = front_matter(path)
        if "_error" in meta:
            problems.append(f"{slug}: front matter unreadable ({meta['_error']})")
            continue
        for field in ("name", "description", "version", "license"):
            if not str(meta.get(field) or "").strip():
                problems.append(f"{slug}: front matter has no {field}")
        if str(meta.get("name") or "").strip() != slug:
            problems.append(f"{slug}: name={meta.get('name')!r} does not match the directory")
        desc = str(meta.get("description") or "")
        if len(desc) < 40:
            problems.append(f"{slug}: description is too short to trigger on ({len(desc)} chars)")
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
            files, total, biggest, pyc = bag(out)
            rows.append({"slug": s["slug"], "files": files, "bytes": total,
                         "biggest": biggest, "pycache_stale": pyc})
    problems = check_limits(rows)
    meta_problems = check_meta([s["slug"] for s in SKILLS])
    for r in rows:
        print(f"{r['slug']:16s} files={r['files']:3d} total={r['bytes']/1024:7.1f}KB "
              f"biggest={r['biggest'][0]} {r['biggest'][1]/1024:.0f}KB")
    if problems:
        print("\nLIMIT PROBLEMS:")
        for p in problems:
            print(" -", p)
    if meta_problems:
        print("\nMETADATA PROBLEMS:")
        for p in meta_problems:
            print(" -", p)
    print(f"\n{len(rows)} packages, {len(problems)} size problem(s), "
          f"{len(meta_problems)} metadata problem(s)")
    return 1 if (problems or meta_problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
