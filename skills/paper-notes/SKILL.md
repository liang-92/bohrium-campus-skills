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
