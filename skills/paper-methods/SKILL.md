---
name: paper-methods
description: Extract experimental setup into a checkable parameter table: hyperparameters, datasets and splits, hardware, seeds, metrics, plus a reproducibility checklist with explicit gaps. Use when a task asks to write or audit a methods/experimental section, or to make an experiment reproducible.
version: 1.0.0
license: MIT
---

# Paper Methods — 写作09 方法与实验章节写作

## 用途

Extract experimental setup into a checkable parameter table: hyperparameters, datasets and splits, hardware, seeds, metrics, plus a reproducibility checklist with explicit gaps. Use when a task asks to write or audit a methods/experimental section, or to make an experiment reproducible.

本 Skill 交付的不是一段“看起来像结果”的文本，而是一份**可复核的结构化结果**：
每条结论都带页码与块 id（`p07-b012` 形式），读不出的部分如实标注，而不是猜。

## 触发条件

- 任务要求写方法与实验章节、整理参数表、检查可复现性
- 需要把散落在正文/配置/日志里的参数对齐
- 要明确“哪些条件原文没报告”而不是补一个合理值

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

实验章节的价值在于“别人能照着做”。

1. **参数抽取**：`learning rate / batch size / epochs / layers / hidden size / dropout / optimizer …`
   连同上下文片段一起抽出，值可能在同一句后半段，取不到就留空。
2. **数据集**：`X dataset/corpus` 命名实体 + 规模、划分比例、预处理描述句。
3. **环境**：GPU/TPU 型号、框架与版本、随机种子、重复次数。
4. **可复现清单**：8 项逐条判定 found/missing（代码版本、环境、超参、数据版本、种子、硬件、指标、重复）。
5. **缺口显式化**：missing 项写进 `uncertainty.missing`，并给出“需要作者确认”的具体问题。

## 输出

| 字段 | 内容 |
|---|---|
| `parameters[]` | 名称、值、上下文、block、page |
| `datasets[]` | 名称、描述句、block |
| `hardware[]` / `seeds[]` | 环境与随机性证据 |
| `reproducibility_checklist[]` | 8 项 found/missing |
| `missing[]` | 原文未报告项 |
| `limitations[]` | 限制条件句 |

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
python3 scripts/run.py --input /input --out /app/output --profile methods
```

示意输出（**示例，非正式案例结果**）：

```json
{"parameters": [{"name": "layers", "value": "6", "context": "a stack of N = 6 identical layers",
  "block": "p03-b005", "page": 3}],
 "reproducibility_checklist": [{"item": "random seeds", "found": false}]}
```

## 异常处理

| 情况 | 处置 |
|---|---|
| 参数只在图/表中 | 从表格行取，标注来源为表格而非正文 |
| 正文与配置冲突 | 两条都记录并标 `conflict`，不擅自取舍 |
| 值缺失 | 留空 + 进 missing，禁止用“常见默认值”填充 |

## 适用边界

不执行实验、不推断未报告的超参；不做结果显著性判断。

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
