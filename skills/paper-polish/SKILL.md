---
name: paper-polish
description: >-
  Diagnose academic prose before rewriting it: long sentences, passive stacking, hedging strength, absolute claims, terminology drift and abbreviation first use. Use when a task asks to polish, edit or proofread academic English/Chinese while preserving meaning, numbers and citations.
  中文触发：学术润色 / 语言修改 / 论文校对 / 中式英语；先做句级诊断（长句、被动堆叠、断言强度、术语漂移、缩写首现），再给出改写，保留数字与引用。
version: 1.0.0
license: MIT
---

# Paper Polish — 写作02 学术语言润色

## 用途

Diagnose academic prose before rewriting it: long sentences, passive stacking, hedging strength, absolute claims, terminology drift and abbreviation first use. Use when a task asks to polish, edit or proofread academic English/Chinese while preserving meaning, numbers and citations.

本 Skill 交付的不是一段“看起来像结果”的文本，而是一份**可复核的结构化结果**：
每条结论都带页码与块 id（`p07-b012` 形式），读不出的部分如实标注，而不是猜。

## 触发条件

- 任务要求润色/校对/改写学术文本，且不能改变原意与结论强度
- 需要逐条修改记录（原文/改文/类型/理由）
- 担心润色时丢限定词、改数字、术语漂移

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

# 1.5) 需要模型自己写文字时（翻译 / 润色 / 写作类）：写进 fill.json 再跑一遍
#      翻译：{"segments": {"s0001": "译文…", "s0002": "译文…"}}
#      术语：{"glossary": {"attention": "注意力"}}
#      其它成稿：{"replace": {"draft": "…"}}
python3 scripts/run.py --input /input --out /app/output --fill /app/output/fill.json

# 2) 看产物
ls /app/output          # doc.json doc.md coverage.json result.json payload.json raw_text.txt run.log

# 3) 自检
python3 scripts/verify.py --out /app/output --kind generic
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

先诊断，再改写，最后用规则守住“没改坏”。

1. **句级体检**：长句（>38 词）、被动堆叠、强化词（very/significantly）、绝对化（all/never/prove）、
   缩写（don't）、名词化过重，逐句给 `flags` 与 block id。
2. **术语一致性**：`X (ABC)` 首次定义、`dataset` vs `data set` 等拼写变体、缩写重复定义。
3. **文体判定**：期刊论文 / 学位论文 / 基金申请 / 审稿回复，语气与主语策略不同。
4. **改写（Agent 执行）**：按 `edit_record_schema` 逐条产出，一条记录只改一处，
   `kept` 字段列出该句必须保留的数字、单位与引用。
5. **守住语义**：数字、单位、引用编号、否定范围、限定词强度、因果/相关措辞不得变化；
   违反时宁可少改。

## 输出

| 字段 | 内容 |
|---|---|
| `genre` | 判定出的文体 |
| `sentence_issues[]` | block、原句、flags |
| `consistency[]` | 术语/拼写/缩写不一致 |
| `edit_record_schema` | 修改记录的字段约定 |
| `guardrails` | 改写红线 |

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

空值要分清两种：**真的没有**（这篇论文就没有公式 → `[]`，置信度照旧）
和**没读到**（文档没解析出来 → 也降为 `0` 并写 `"why_empty"`）。
判据在 `field_status.<字段>`：`"empty": true` 表示这个字段是空的；
若同时 `confidence` 为 0，说明不是没找到，是根本没读到——别把它当成结论。

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
python3 scripts/run.py --input /input --out /app/output --profile polish
# Agent 按 schema 产出 edits[]，再自查 guardrails
```

示意输出（**示例，非正式案例结果**）：

```json
{"sentence_issues": [{"block": "p02-b004", "page": 2,
  "sentence": "It is very clear that all models are always better with more data.",
  "flags": ["intensifier", "absolute-claim"]}]}
```

## 异常处理

| 情况 | 处置 |
|---|---|
| 原句本身语法正确但风格不合 | 标注 `register` 而非 `grammar`，改写幅度最小 |
| 改写后数字/引用丢失 | 直接判为失败，回到原句重写 |
| 中文稿件夹英文术语 | 保留术语原形，只改连接与语序 |

## 适用边界

不代替作者判断学术观点；不做降重、不做翻译（翻译用 paper-translate）。

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
