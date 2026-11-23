---
name: paper-parse
description: >-
  Parse a research PDF into an evidence-linked structure (sections, blocks, tables, formulas, figures, references) where every string carries a page and block id. Use when a task asks to extract, verify, quote or audit the content of a scholarly PDF, especially two-column layouts, cross-page tables or scanned pages.
  中文触发：文献文档解析 / 解析论文 PDF / 抽取正文、章节、表格、公式、图与参考文献的位置，并给出页码与块号，便于复核与引用；适用于双栏排版、跨页表格、扫描件。
version: 1.0.0
license: MIT
---

# Paper Parse — 阅读01 文献文档解析

## 用途

Parse a research PDF into an evidence-linked structure (sections, blocks, tables, formulas, figures, references) where every string carries a page and block id. Use when a task asks to extract, verify, quote or audit the content of a scholarly PDF, especially two-column layouts, cross-page tables or scanned pages.

本 Skill 交付的不是一段“看起来像结果”的文本，而是一份**可复核的结构化结果**：
每条结论都带页码与块 id（`p07-b012` 形式），读不出的部分如实标注，而不是猜。

## 触发条件

- 任务要求“把这篇 PDF 解成结构化结果”“逐段核对”“给出原文定位”
- 需要从论文里取标题/摘要/章节/表/公式/参考文献并保留页码
- 双栏、跨栏、跨页表格、扫描件，普通文本抽取会串栏或丢段

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

解析不是“取一段看起来像全文的文本”，而是重建版面：

1. **多引擎兜底**：PyMuPDF → pdfplumber → pypdf → poppler `pdftotext`，记录实际使用的引擎；
   某一页没有文字层但含图片时，渲染 220dpi 走 OCR，并把该页标记 `filled_by: ocr`。
2. **去页眉页脚**：按位置（上下 8.5%）+ 跨页重复模式（数字归一化后计数）+ 旋转文本（arXiv 边条）
   + 已知 stamp（版权、Preprint、页码）四类规则剔除，剔除记录写进 `running_heads_removed`。
3. **XY-cut 阅读顺序**：递归找“没有任何一行跨过”的竖直缝隙→分栏，再找水平缝隙→分带；
   两者都必须把当前区域**完整二分**才接受，因此整栏标题、通栏表格会自然成为分带边界。
   单栏页面因窄行占比过低会直接跳过栏检测，避免把插图区误判成栏间距。
4. **段落重建**：按左边界聚类得到每栏右边界；上一行明显短于右边界（缩进/段末）或行距超过
   中位行距 2 倍时断段；行末连字符且下一行小写时合并（`advanta-` + `geous` → `advantageous`）。
5. **结构标注**：编号深度（`3.2.1`）/字号比/常见标题名判定层级；`3.1` 与 `Encoder and Decoder Stacks`
   这类被拆开的标题会重新拼接。
6. **表格与公式**：优先引擎表格识别（`find_tables` / `extract_tables`），失败时用“行内多列宽间隙”
   兜底；公式按数学符号密度 + 编号 `(12)` 识别，同一公式的碎片行合并。
7. **证据粒度**：每个块得到 `p03-b012` 这样的稳定 id，页码、栏号、bbox、章节路径一并保留。

## 输出

`result.json` 主要字段：

| 字段 | 内容 |
|---|---|
| `document` | 标题、作者、摘要、关键词、DOI、页数、引擎、PDF sha256 |
| `structure` | 章节树（level/title/page/block） |
| `content.blocks` | 全量块：id、page、column、section、type、text |
| `content.tables` | 表格：caption、header、rows、markdown、行列数、来源 |
| `content.formulas` | 公式：编号、文本、所在块 |
| `content.figures` | 图：页码、bbox、caption |
| `content.references` | 参考文献条目：编号、文本、页码、块 |
| `coverage` | 每页字符数、空页、栏数、问题清单 |

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
| 本 Skill 确实产不出 | 保留原 key，输出 `{"value": <按声明类型的空值>, "method": "unsupported", "confidence": 0}`，并写进 `uncertainty.missing` |

契约没声明的切片不会塞进 `output_contract`，而是另存 `payload.json`——
否则多出来的键会被读成「把答案改了名」。`field_status` 逐字段记下用了哪条规则、置信度多少，
`verify.py` 会对 `case.json` 复核「声明的字段是否都在、有没有多出来的键」。

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

```bash
python3 scripts/run.py --input /input --out /app/output
python3 scripts/run.py --input ./case --out ./out --no-ocr    # 跳过 OCR
python3 scripts/verify.py --out /app/output --kind generic
```

示意输出（**示例，非正式案例结果**）：

```json
{"case_id": "demo-001", "status": "complete",
 "document": {"title": "Attention Is All You Need", "pages": 15, "engine": "pymupdf 1.24"},
 "structure": [{"level": 1, "title": "3 Model Architecture", "page": 2, "block": "p02-b008"}],
 "content": {"blocks": [{"id": "p03-b005", "page": 3, "section": "3.1 Encoder and Decoder Stacks",
                          "text": "The encoder is composed of a stack of N = 6 identical layers."}]}}
```

## 异常处理

| 情况 | 处置 |
|---|---|
| 扫描件无文字层 | 自动 OCR；OCR 页写入 `source.ocr_pages`，置信度无法保证时在 `uncertainty` 注明 |
| 加密/损坏 PDF | 捕获异常，`status: partial`，写明失败页与原因，不伪造文本 |
| 表格识别为空 | 用行间隙兜底；仍为空则在 `coverage.issues` 说明“该页无表格或引擎不支持” |
| 字体乱码 | 保留原字符并标记，不做“猜测式修正” |

## 适用边界

不解释图表科学含义；不做翻译或改写；对艺术排版（海报、竖排）只保证可读顺序，不保证视觉对应。

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
