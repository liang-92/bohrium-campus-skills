---
name: paper-notes
description: Turn a paper into a structured reading note: research question, data, methods, findings, limitations, per-section gists and knowledge items, each linked to a page and block. Use when a task asks for a paper summary, reading card, literature note or structured extraction that must stay traceable to the source.
version: 1.0.0
license: MIT
---

# Paper Notes — 阅读10 文献总结与结构化笔记

## 用途

Turn a paper into a structured reading note: research question, data, methods, findings, limitations, per-section gists and knowledge items, each linked to a page and block. Use when a task asks for a paper summary, reading card, literature note or structured extraction that must stay traceable to the source.

本 Skill 交付的不是一段“看起来像结果”的文本，而是一份**可复核的结构化结果**：
每条结论都带页码与块 id（`p07-b012` 形式），读不出的部分如实标注，而不是猜。

## 触发条件

- 任务要求“总结这篇论文”“做阅读笔记/论文卡片/结构化摘要”
- 需要按论文章节而不是通用模板组织内容
- 笔记要能回到原文位置，供后续写作或复核

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

笔记的骨架跟随论文本身，而不是套模板。

1. **先建骨架**：用解析出的章节树作为笔记目录，章节缺失时才回退到“摘要/方法/结果/讨论”。
2. **按论证功能取句**：研究问题（`we study/investigate/address`）、方法（`we use/train/apply`）、
   发现（`we find/show/observe/outperform`）、局限（`limitation/future work/only/cannot`）、
   贡献（`we propose/introduce`）、数据（含数字的 dataset/corpus 句）。
3. **每节一条 gist**：取该节首段首句作为入口，并记录该节前 8 个块 id，方便展开。
4. **知识点**：抽 `X is/refers to/means …` 型定义，形成可检索条目。
5. **可核验**：卡片每个字段都是 `{text, block, page, section}`，不是纯字符串。

## 输出

| 字段 | 内容 |
|---|---|
| `paper_card` | 研究问题、数据、方法、发现、局限、贡献（均带 block/page）|
| `section_notes[]` | 每节 gist + 入口块 + 覆盖块列表 |
| `knowledge_items[]` | 定义型知识点 |
| `glossary[]` | 高频术语 |

`status` 在“无发现句或无章节笔记”时为 `partial`。

`result.json` 同时保留 `case_id`、`status`、`evidence`、`uncertainty`、`provenance`，
以及 `case.json` 里声明的 `output_contract` 字段（存在则逐项填，缺证据就留 `null` 并说明）。

## 最小调用示例

```bash
python3 scripts/run.py --input /input --out /app/output --profile notes
```

示意输出（**示例，非正式案例结果**）：

```json
{"paper_card": {"research_question": [{"text": "This study explores the effect of child-directed speech.",
   "block": "p01-b012", "page": 1, "section": "Abstract"}],
  "findings": [{"text": "We find that CDS helps in the initial stages of learning.", "block": "p01-b014"}]}}
```

## 异常处理

| 情况 | 处置 |
|---|---|
| 论文无显式局限段 | 留空并在 `uncertainty` 说明“原文未报告”，不臆造局限 |
| 结论分散在讨论中 | 允许跨节取句，但必须记录来源节 |
| 摘要与正文冲突 | 两条都保留，标注冲突点，交人工判断 |

## 适用边界

不评价论文质量、不做领域外推；单篇论文笔记，不做多篇综述。

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
