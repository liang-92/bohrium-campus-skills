---
name: paper-kg
description: Build a small, evidence-bound knowledge graph from a paper: entities (methods, datasets, metrics, tasks), typed relations, alias groups and answerable queries. Use when a task asks for entity/relation extraction, a literature knowledge graph, or graph export with provenance.
version: 1.0.0
license: MIT
---

# Paper Knowledge Graph — 阅读15 文献知识图谱构建

## 用途

Build a small, evidence-bound knowledge graph from a paper: entities (methods, datasets, metrics, tasks), typed relations, alias groups and answerable queries. Use when a task asks for entity/relation extraction, a literature knowledge graph, or graph export with provenance.

本 Skill 交付的不是一段“看起来像结果”的文本，而是一份**可复核的结构化结果**：
每条结论都带页码与块 id（`p07-b012` 形式），读不出的部分如实标注，而不是猜。

## 触发条件

- 任务要求从论文抽实体与关系、建知识图谱
- 需要别名归一、关系方向与条件、来源绑定
- 要导出可查询的图（JSON/Cypher/DOT）

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

只建有证据的边，宁可少建，不可猜建。

1. **实体**：方法（transformer/bert/attention…）、数据集（`X dataset/corpus`）、指标（BLEU/F1/AUC…）、
   任务（translation/classification…）、章节标题作为 concept 节点。
2. **关系**：`uses`、`evaluated_on`、`outperforms`、`improves` 四类句式模板匹配；
   每条边必须带 `evidence.block` 与匹配到的原句片段。
3. **别名归一**：小写、去连字符、去复数后聚类；同一 canonical 下多个节点进 `alias_groups`，
   保留原始写法，不做不可逆合并。
4. **查询**：按关系类型各给一组示例查询及答案子图，并显式列出“无法确定的关系”。
5. **导出**：JSON（nodes/edges）+ Cypher `MERGE` 语句，便于导入 Neo4j。

## 输出

| 字段 | 内容 |
|---|---|
| `nodes[]` | id、label、type、evidence（block/page/section）|
| `edges[]` | source、target、relation、evidence（含原句）|
| `alias_groups[]` | 归一后的同义节点 |
| `queries[]` | 查询语句 + 结果子图 |
| `stats` | 节点数、边数 |

`result.json` 同时保留 `case_id`、`status`、`evidence`、`uncertainty`、`provenance`，
以及 `case.json` 里声明的 `output_contract` 字段（存在则逐项填，缺证据就留 `null` 并说明）。

## 最小调用示例

```bash
python3 scripts/run.py --input /input --out /app/output --profile kg
```

示意输出（**示例，非正式案例结果**）：

```json
{"nodes": [{"id": "n001", "label": "Transformer", "type": "method"}],
 "edges": [{"source": "n001", "target": "n004", "relation": "evaluated_on",
            "evidence": {"block": "p08-b012", "page": 8, "quote": "We evaluate on WMT 2014 English-to-German."}}]}
```

## 异常处理

| 情况 | 处置 |
|---|---|
| 共现但无关系句 | 不建边，记入“未确定关系” |
| 同名不同物 | 保留为两个节点，`alias_groups` 不合并，注明冲突 |
| 代词指代不清 | 丢弃该边，避免把 it/this 错误连到实体 |

## 适用边界

不引入论文外的常识实体；不做跨论文融合（单篇建图）。

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
