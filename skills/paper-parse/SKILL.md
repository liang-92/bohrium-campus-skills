---
name: paper-parse
description: Parse a research PDF into an evidence-linked structure (sections, blocks, tables, formulas, figures, references) where every string carries a page and block id. Use when a task asks to extract, verify, quote or audit the content of a scholarly PDF, especially two-column layouts, cross-page tables or scanned pages.
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

# 1) 一次跑完解析 + 组包
python3 scripts/run.py --input /input --out /app/output

# 2) 看产物
ls /app/output          # doc.json doc.md coverage.json result.json run.log

# 3) 自检
python3 scripts/verify.py --out /app/output --kind generic
```

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

`result.json` 同时保留 `case_id`、`status`、`evidence`、`uncertainty`、`provenance`，
以及 `case.json` 里声明的 `output_contract` 字段。字段名与内部切片对不上时按语义匹配回填，
**仍为空才留 `null`**，并在 `uncertainty.inferred_fields` 里逐项说明是怎么推出来的。

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
