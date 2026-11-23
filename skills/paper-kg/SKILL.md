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
ls /app/output          # doc.json doc.md coverage.json result.json payload.json raw_text.txt run.log

# 3) 自检
python3 scripts/verify.py --out /app/output --kind generic
```

`verify.py` 除了回查引句，还会复算三件与评分口径对应的事，并打印 `checks` 段：
逐栏阅读顺序倒挂数、块的 bbox 是否落在自己声明的栏内、`output_contract` 是否与
`case.json` 逐字段对齐（声明的都在、没有多出来的键）。

只依赖 Python 标准库；有 PyMuPDF 时用它做主力引擎，没有则自动退化到 pdfplumber / pypdf /
poppler，缺什么会在 `run.log` 和 `coverage.json` 里写明，不会静默降级。

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

`result.json` 的 `output_contract` **逐字照抄 `case.json` 声明的字段名**，一个不改、不加：

| 情形 | 落地方式 |
|---|---|
| 字段在 composer 的切片里有同名键 | 原值输出，`field_status.<字段>.method = "exact"` |
| 字段名是普通文献名词（`equations`/`citations`/`full_text_blocks`） | 路由到对应切片，`method = "alias:formulas"` 等，**路由规则写在结果里** |
| 字段是任务型输出（`answers`/`summary`） | 用本 Skill 的发现兜底，`method = "fallback:…"`，置信度 0.5 |
| 本 Skill 确实产不出 | 保留原 key，输出 `{"value": <按声明类型的空值>, "method": "unsupported", "confidence": 0}`，并写进 `uncertainty.missing` |

契约没声明的切片不会塞进 `output_contract`，而是另存 `payload.json`——
否则多出来的键会被读成「把答案改了名」。`field_status` 逐字段记下用了哪条规则、置信度多少，
`verify.py` 会对 `case.json` 复核「声明的字段是否都在、有没有多出来的键」。

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
