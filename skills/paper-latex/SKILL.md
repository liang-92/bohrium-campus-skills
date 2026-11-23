---
name: paper-latex
description: Turn a parsed paper into a compilable LaTeX project: escaped body, section hierarchy, booktabs tables, equation environments, thebibliography, and a real compile attempt with error lines. Use when a task asks to produce or fix LaTeX source, migrate a manuscript into a template, or make a build reproducible.
version: 1.0.0
license: MIT
---

# Paper LaTeX — 写作13 LaTeX 写作与编译

## 用途

Turn a parsed paper into a compilable LaTeX project: escaped body, section hierarchy, booktabs tables, equation environments, thebibliography, and a real compile attempt with error lines. Use when a task asks to produce or fix LaTeX source, migrate a manuscript into a template, or make a build reproducible.

本 Skill 交付的不是一段“看起来像结果”的文本，而是一份**可复核的结构化结果**：
每条结论都带页码与块 id（`p07-b012` 形式），读不出的部分如实标注，而不是猜。

## 触发条件

- 任务要求生成/修复 LaTeX 源码并编译
- 需要把论文结构、表格、公式、参考文献转成 .tex
- 编译报错需要定位到文件与行号

不适用：与文献无关的任务、纯图片问答、需要联网检索的任务。

## 输入

| 位置 | 内容 |
|---|---|
| `/input/case.json` | 案例元信息，可能包含 `output_contract` 字段清单 |
| `/input/task.md` | 本次任务说明 |
| `/input/*.pdf` | 原始论文（无预抽取文本层）|
| `/input/*` | 其他材料：docx / tex / bib / csv / json / md |

## 快速开始

```bash
# 1) 一次跑完解析 + 组包
python3 scripts/run.py --input /input --out /app/output

# 2) 看产物
ls /app/output          # doc.json doc.md coverage.json result.json run.log

# 3) 自检
python3 scripts/verify.py --out /app/output --kind generic
```

`run.py` 是幂等的，可重复执行；`--no-ocr` 可跳过 OCR（更快，但扫描页会空）。

## 处理流程

交付的是源码工程，不是一张 PDF 截图。

1. **结构映射**：章节层级 → `\section/\subsection/\subsubsection`，标题去重，跳过重复 running head。
2. **转义**：`\ & % $ # _ { } ~ ^` 全部转义，避免“一个下划线炸整篇”。
3. **表格**：解析出的表格转 `booktabs`（`\toprule/\midrule/\bottomrule`），列数超 6 时截断并注明。
4. **公式**：公式块进 `equation` 环境，保留原编号文本。
5. **参考文献**：`thebibliography` + `\bibitem`，编号与正文 `[n]` 对齐。
6. **真编译**：检测 `pdflatex/latexmk/xelatex`，编译两次，抓 `!` 开头的错误行；
   引擎缺失时明确写 `compile.attempted: false`，不谎报成功。

## 输出

| 字段 | 内容 |
|---|---|
| `files` | 生成的文件清单（`main.tex`、`latex/main.tex`）|
| `tex` | 源码（截断展示）|
| `compile` | 是否尝试、引擎、是否成功、错误行、是否产出 PDF |
| `structure` | 章节映射结果 |
| `environment` | 引擎与宏包依赖 |

`result.json` 同时保留 `case_id`、`status`、`evidence`、`uncertainty`、`provenance`，
以及 `case.json` 里声明的 `output_contract` 字段（存在则逐项填，缺证据就留 `null` 并说明）。

## 最小调用示例

```bash
python3 scripts/run.py --input /input --out /app/output --profile latex
ls /app/output/latex/main.tex
python3 scripts/verify.py --out /app/output --kind generic
```

示意输出（**示例，非正式案例结果**）：

```json
{"compile": {"attempted": true, "engine": "pdflatex", "ok": true, "pdf": true, "errors": []}}
```

## 异常处理

| 情况 | 处置 |
|---|---|
| 无 TeX 引擎 | `attempted: false`，交付源码 + 所需宏包清单，说明未验证编译 |
| 编译报错 | 保留 `.log`，把首条 `!` 错误与行号写进 `compile.errors` |
| 缺字体/中文 | 提示改用 `xelatex` + `ctex`，不偷偷删内容求编译通过 |

## 适用边界

不追求期刊模板的像素级还原；复杂浮动体排版需人工微调。

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
