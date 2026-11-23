---
name: paper-intro
description: Assemble an evidence-bound introduction and related-work outline from a paper: problem statements, grouped prior work, gaps derived from those groups, contributions mapped to results, plus citation coverage. Use when a task asks to write or revise an introduction, related work section or research-gap statement.
version: 1.0.0
license: MIT
---

# Paper Introduction — 写作08 引言与相关工作写作

## 用途

Assemble an evidence-bound introduction and related-work outline from a paper: problem statements, grouped prior work, gaps derived from those groups, contributions mapped to results, plus citation coverage. Use when a task asks to write or revise an introduction, related work section or research-gap statement.

本 Skill 交付的不是一段“看起来像结果”的文本，而是一份**可复核的结构化结果**：
每条结论都带页码与块 id（`p07-b012` 形式），读不出的部分如实标注，而不是猜。

## 触发条件

- 任务要求写/改引言、相关工作、研究空白与贡献表述
- 需要“按问题分组比较”而不是逐篇罗列
- 要保证每条断言都有引用或明确标注为作者判断

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

引言不是背景铺垫，是一条从“问题”到“空白”到“贡献”的论证链。

1. **问题句**：抽取 problem/challenge/costly/bottleneck 语境句，区分“领域重要性”与“具体困难”。
2. **相关工作分组**：以章节为初始分组，按问题设定/方法路线/数据与评价三个维度归并，
   每组给出代表工作与该组共同限制。
3. **空白推导**：`however/remains/few studies/has not been` 句作为空白证据，必须来自已引文献。
4. **贡献映射**：`we propose/introduce/show` 句作为贡献条目，并要求每条能指向正文的图/表/结果块。
5. **引用覆盖**：统计引言中出现的引用编号与参考文献条目数，标出“引了但没在引言出现”的关键工作。

## 输出

| 字段 | 内容 |
|---|---|
| `problem_statements[]` | 具体困难句 + block |
| `related_work_groups[]` | 分组、代表条目、gist |
| `gap_statements[]` | 空白句 + block |
| `contributions[]` | 贡献句 + block |
| `citation_coverage` | 引用编号数 vs 条目数 |
| `outline` | 建议的五段式论证骨架 |

`result.json` 同时保留 `case_id`、`status`、`evidence`、`uncertainty`、`provenance`，
以及 `case.json` 里声明的 `output_contract` 字段（存在则逐项填，缺证据就留 `null` 并说明）。

## 最小调用示例

```bash
python3 scripts/run.py --input /input --out /app/output --profile intro
```

示意输出（**示例，非正式案例结果**）：

```json
{"gap_statements": [{"text": "However, how much of this advantage comes from linguistic vs acoustic properties remains unclear.",
  "block": "p02-b007", "page": 2}]}
```

## 异常处理

| 情况 | 处置 |
|---|---|
| 论文没有显式 gap 句 | 用“共同限制”归纳，并标注为推论而非原文 |
| 贡献与结果对不上 | 在 `uncertainty` 标出“贡献无对应证据” |
| 相关工作节缺失 | 只用引言内的引用构建分组，并说明来源受限 |

## 适用边界

不代替作者提出新贡献；不做跨论文综述（只围绕单篇）。

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
