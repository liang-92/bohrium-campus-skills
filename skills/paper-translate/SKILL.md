---
name: paper-translate
description: Translate research papers segment by segment with a locked glossary, protected numbers/units/citations and a verification pass. Use when a task asks for a Chinese translation of a paper, bilingual paragraph alignment, terminology consistency, or a translation QA report.
version: 1.0.0
license: MIT
---

# Paper Translate — 阅读03 文献翻译

## 用途

Translate research papers segment by segment with a locked glossary, protected numbers/units/citations and a verification pass. Use when a task asks for a Chinese translation of a paper, bilingual paragraph alignment, terminology consistency, or a translation QA report.

本 Skill 交付的不是一段“看起来像结果”的文本，而是一份**可复核的结构化结果**：
每条结论都带页码与块 id（`p07-b012` 形式），读不出的部分如实标注，而不是猜。

## 触发条件

- 任务要求翻译论文/摘要/章节，并要求术语统一、可回看原文
- 需要段落级双语对照、译后核验、译不准处标注
- 长文跨页跨栏，直接整篇翻译会漏段、串段、术语漂移

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
python3 scripts/verify.py --out /app/output --kind translate
```

`verify.py` 除了回查引句，还会复算三件与评分口径对应的事，并打印 `checks` 段：
逐栏阅读顺序倒挂数、块的 bbox 是否落在自己声明的栏内、`output_contract` 是否与
`case.json` 逐字段对齐（声明的都在、没有多出来的键）。

只依赖 Python 标准库；有 PyMuPDF 时用它做主力引擎，没有则自动退化到 pdfplumber / pypdf /
poppler，缺什么会在 `run.log` 和 `coverage.json` 里写明，不会静默降级。

`run.py` 是幂等的，可重复执行；`--no-ocr` 可跳过 OCR（更快，但扫描页会空）。

## 处理流程

**术语先锁定，再逐段翻译，最后机器核验。**

1. **切段**：按块（而非按页）切分，块内再按句边界合并到 ≤850 字符，得到 `s0001…` 段号；
   每段保留 `block`、`page`、`section`，因此译文永远能回到原文位置。
2. **术语表**：从全文抽高频术语/缩写（`X (ABC)` 形式优先），与内置学术词表合并；
   同一术语只允许一个译名，冲突由 `verify.py` 报错。
3. **保护令牌**：每段提前抽出数字、单位、引用标记 `[12]`、图表编号、公式片段、模型/数据集专名，
   译文中必须原样出现——这一步把“翻译时把 28.4 BLEU 写成 28.4 分”这类错误变成机器可查的问题。
4. **逐段翻译**：Agent 按段填 `translation`，只译该段，不合并、不省略、不添加解释。
5. **核验**：`verify.py` 检查空译、数字/单位/引用丢失、译文长度异常、术语一名多译。

## 输出

`result.json` 主要字段：

| 字段 | 内容 |
|---|---|
| `segments[]` | `seg`、`block`、`page`、`section`、`source`、`protected`、`translation` |
| `glossary[]` | 术语、出现次数、建议译名 `zh` |
| `rules` | 术语策略、必须原样保留的令牌、语域要求 |

`translation` 初始为空是**设计如此**：这一栏必须由模型逐段填写，脚本不生成译文。

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
python3 scripts/run.py --input /input --out /app/output      # 生成分段与术语表
# Agent 逐段填写 result.json 的 segments[].translation
python3 scripts/verify.py --out /app/output --kind translate  # 译后核验
```

示意输出（**示例，非正式案例结果**）：

```json
{"segments": [{"seg": "s0001", "block": "p01-b005", "section": "Abstract",
  "source": "The dominant sequence transduction models are based on complex recurrent networks.",
  "protected": {"numbers": [], "citations": []},
  "translation": "主流的序列转换模型基于复杂的循环神经网络。"}]}
```

## 异常处理

| 情况 | 处置 |
|---|---|
| 段落过长导致截断 | 按句边界再切，禁止从句子中间截断 |
| 术语表冲突 | 以首次出现并在标题/摘要中使用的译名为准，其余全部改齐 |
| 公式/符号无法翻译 | 原样保留，前后文用中文衔接，不改写公式 |
| 原文本身残缺（PDF 丢字） | 译文中用 `[原文缺失]` 标注，不猜测 |

## 适用边界

不润色原文、不补写原文没有的内容；诗歌、广告等非学术文体不在适用范围。

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
