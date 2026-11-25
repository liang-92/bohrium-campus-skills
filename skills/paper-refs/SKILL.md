---
name: paper-refs
description: >-
  Audit and rebuild reference lists: parse entries, map in-text citations, detect missing/uncited/duplicate items, check numbering and emit GB/T 7714 / APA / BibTeX. Use when a task involves citation management, bibliography cleanup, reference verification or citation-text consistency.
  中文触发：参考文献管理 / 引用核对 / 文献表整理 / 去重 / GB-T 7714 / APA / BibTeX；解析条目、映射正文引用、找出缺失未引用与重复项。
version: 1.0.0
license: MIT
---

# Paper References — 写作04 参考文献与引用管理

## 用途

Audit and rebuild reference lists: parse entries, map in-text citations, detect missing/uncited/duplicate items, check numbering and emit GB/T 7714 / APA / BibTeX. Use when a task involves citation management, bibliography cleanup, reference verification or citation-text consistency.

本 Skill 交付的不是一段“看起来像结果”的文本，而是一份**可复核的结构化结果**：
每条结论都带页码与块 id（`p07-b012` 形式），读不出的部分如实标注，而不是猜。

## 触发条件

- 任务要求检查/整理参考文献、正文引用与文末列表是否一致
- 需要编号更新、去重、格式转换（GB/T 7714、APA、BibTeX）
- 怀疑条目并不存在、重复、引用错位

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

引用管理的核心是“集合运算 + 字段核对”。

1. **条目解析**：编号、作者串、年份、标题（引号内优先）、DOI、原文串；
   进一步分出 `venue`（期刊/会议/出版社）、`volume`、`issue`、`pages`、`type`（J/C/M/EB-OL）。
   会议名、卷期页是 GB/T 7714 与 BibTeX 的必填项，缺了就只能输出残缺条目——所以先抽字段再排版。
2. **正文引用抽取**：`[12]`、`[3–5]` 区间展开、`(Author, 2020)` 作者-年制；记录每处出现的 block。
3. **一致性**：`citations_without_entry`（引了但列表没有）、`entries_never_cited`（列了但没引）、
   `numbering_gaps`（编号缺号/重号）。
4. **去重**：DOI 相同 → 同一条；无 DOI 时用标题归一化（去标点、小写、截断）比对，
   只报告“疑似”，不自动合并。
5. **格式化**：同时输出 GB/T 7714、APA 与 BibTeX 三种写法。
   **按类型分支**：期刊 `[J]` 出卷(期): 页；会议 `[C]` 用 `//会议名` 前缀；
   图书 `[M]`、电子资源 `[EB/OL]` 各自成式；BibTeX 对应 `@article/@inproceedings/@book/@misc`，
   `booktitle` 与 `journal` 不混用。BibTeX citation key 由「第一作者姓氏 + 年份 + 标题首个实词」生成，稳定可复现。
   字段缺失处留空，不补写。
6. **可疑条目**：无年份、无 venue、标题异常、DOI 形态不合法，单独列出待人工核验。

## 输出

| 字段 | 内容 |
|---|---|
| `entries[]` | n、authors、year、title、venue、volume、issue、pages、type、doi、page、block |
| `in_text_citations` | 编号 → 出现的 block 列表 |
| `issues` | 缺条目、未被引、重复、编号缺口 |
| `formatted` | `gbt`（GB/T 7714）、`apa`、`bibtex` 三套文本 |
| `stats` | 条目数、被引编号数 |

每个块同时留四样东西，方便复核而不是只能相信结论：

| 字段 | 用途 |
|---|---|
| `text` | 清洗后的可读文本（合并了行末连字符、去掉了页眉页脚） |
| `text_raw` | **该块对应的引擎原始行**：未合并、未删除，可与 PDF 文本层逐字 diff |
| `raw_text.txt` | 全篇原始文字层快照，在清洗之前导出，用于整篇比对 |
| `engine` | 这一块由哪个引擎读到（如 `pymupdf 1.24` / `ocr`），OCR 页与文字层页可区分 |
| `order_rule` | 该页用 XY-cut 分栏，还是按 y 排序（`xy-cut` / `naive-y`） |
| `para_break_reason` + `break_at` | 为什么在这里断开，以及触发断段的两行 y 坐标（可回放） |
| `hyphen_merged` + `hyphen_pair` | 是否合并了行末连字符、被合并的两半是什么 |
| `evidence[]` | 块 id + 页码 + 原文引句；`verify.py` 会回查引句是否真在该块里 |

图表位置也在 `doc.json` 里，`doc.md` 末尾有一张速查表：

| 字段 | 用途 |
|---|---|
| `figures[].kind` | `raster`（位图）/ `chart`（矢量图表，≥8 条路径聚类）/ `vector`（矢量插图）|
| `figures[].bbox` / `area_ratio` | 位置与占页比例；判断「是图还是装饰」 |
| `figures[].caption` / `caption_block` / `caption_bbox` | 图注原文、图注块 id、图注位置（`below`/`above`）|
| `figures_dropped[]` | 被判定为子图或装饰的块，附 bbox 与理由（不静默丢弃）|
| `tables[].rows` / `n_rows` / `n_cols` | 单元格内容与行列数，`in_table` 标出正文块属于哪张表 |
| `image_tables[]` | 只有图片、没有文字层的表格：给出页码与图注，明确「单元格不在 `tables[]` 里，不要补写」|

`coverage.json` 把异常单独记下来，而不是让它们影响正文而不留痕：

| 键 | 含义 |
|---|---|
| `page_order.warning` | 页脚打印页码非单调/重复（重排过的 PDF），下游「见第 N 页」可能错位 |
| `garbled_text_layer.pages` | 字体缺 `toUnicode`、文字层是私用区码点的页；已尝试对这几页改走 OCR |
| `image_tables` | 有 `Table N` 图注但区域内无文字层 → 表格是图片，未抽取 |
| `figures_dropped` | 被判定为子图/装饰的块及理由 |
| `verbatim` | 字符账本：文字层字符数 / 块内字符数 / 丢失 / 多出 / 覆盖率；覆盖率低于 0.995 会写进 `issues` |
| `header_footer[]` | 被剔除的页眉页脚逐条保留（页码、文本、bbox）——是标记，不是销毁 |

`result.json` 的 `output_contract` **逐字照抄 `case.json` 声明的字段名**，一个不改、不加：

| 情形 | 落地方式 |
|---|---|
| 字段在 composer 的切片里有同名键 | 原值输出，`field_status.<字段>.method = "exact"` |
| 字段名是普通文献名词（`equations`/`citations`/`full_text_blocks`） | 路由到对应切片，`method = "alias:formulas"` 等，**路由规则写在结果里** |
| 字段的 `items` 里写着 `cells`/`header`/`rows` 这类形状词 | 按**契约自己的 schema** 路由到表格切片，`method = "items-shape:tables"` |
| 字段是任务型输出（`answers`/`summary`） | 用本 Skill 的发现兜底，`method = "fallback:…"`，置信度 0.5 |
| 本 Skill 确实产不出 | 保留原 key，输出 `{"value": <按声明类型的空值>, "method": "unsupported", "confidence": 0}`，并写进 `uncertainty.missing` |

契约没声明的切片不会塞进 `output_contract`，而是另存 `payload.json`——
否则多出来的键会被读成「把答案改了名」。`field_status` 逐字段记下用了哪条规则、置信度多少，
`verify.py` 会对 `case.json` 复核「声明的字段是否都在、有没有多出来的键」。

空值要分清两种：**真的没有**（这篇论文就没有公式 → `[]`，置信度照旧）
和**没读到**（文档没解析出来 → 也降为 `0` 并写 `"why_empty"`）。
判据在 `field_status.<字段>`：`"empty": true` 表示这个字段是空的；
若同时 `confidence` 为 0，说明不是没找到，是根本没读到——别把它当成结论。

`verify.py` 打印三段：`checks`（读自己的 `doc.json`：几何、决策回放、契约对齐）、
`independent`（**重开 PDF** 重抽文字层做字符多重集比对、逐格核对表格单元格是否在该页、
再用 pypdf 这个第二实现交叉验证字符量）、`problems`（要逐条修）。前者是自洽，后者才可能与结论矛盾。

## 怎么证明它比不加载更好（对照协议）

评分项要的是「加载 Skill 的 Agent vs 不加载的 Agent」。本 Skill 不含模型调用，
能离线做的那一半已经做了，脚本与结果都在仓库里：

| 用例 | base（纯文本转储） | skill | delta |
|---|---|---|---|
| `p08-refs`：4 条条目，其中 `[5]` 缺条目、`[4]` 未被引、`[2]`/`[4]` 重复 | 0.0 | 90.0 | +90.0 |

base 拿到的是一段纯文本，无法给出条目、缺失/未引用/重复三张问题清单，也排不出
GB/T 7714 与 BibTeX；skill 在这三项上与 `gold.json` 完全一致。

来源 `bench/base_agent.py` + `bench/base_vs_skill.json`，**离线对照，不是平台成绩**。
`base` 是「不加载 Skill」的下界代理：只给引擎的 `page.get_text("text")` 纯文本转储，
没有块 id、没有分栏、没有表格/图/公式，也没有证据。真实的多模态模型会比这个代理强，
所以 delta 只会更小——这也是为什么这里给的是**下界**而不是宣传数字。

真正的模型对照仍需评测方执行：同一批 case、只差是否安装本 Skill、用同一个打分器逐字段打分、
每条件重复取中位数；平台记录的真实轨迹为准，本 Skill 不填这些数字。

主张范围写在这里，避免被读成更大的声明：

| 主张 | 可复现的检查 |
|---|---|
| 契约字段名逐字对上、类型对得上、填不出的如实标 `unsupported` | `verify.py` 的 `checks.contract` |
| 每条结论能回到页码 + 块 id + 原文引句 | `verify.py` 回查引句 + `checks.geometry` |
| 版面判断可复核（为何在此断段、该页用哪种读序） | `checks.decisions`：回放 `caption-start` / `vertical-gap` / `block-size-cap` / `hyphen_merged` |
| 字符不丢不增（逐字一致） | `independent`：重开 PDF、重抽文字层、字符多重集比对（含页眉页脚去重） |
| 表格单元格确实在该页 | `independent.table_cells`：逐格在该页文字层里查找 |
| 加密/扫描/空白/乱码/页码错乱不崩，降级留痕 | `coverage.json` 的异常字段 + 状态位 |

**不主张**：内容理解强于多模态模型。表格语义、公式含义这些，基础模型可能更好；
本 Skill 的价值在于「同样的文字，结构与证据链是否可靠、是否可复核」，不在语义猜测。

## 最小调用示例

```bash
python3 scripts/run.py --input /input --out /app/output --profile refs
```

示意输出（**示例，非正式案例结果**）：

```json
{"issues": {"citations_without_entry": ["27"], "entries_never_cited": ["31"],
            "duplicates": [{"a": "12", "b": "28", "key": "10.18653/v1/2020.acl-main.1"}]},
 "formatted": {"gbt": ["Vaswani A, Shazeer N, Parmar N, et al. Attention is all you need[C]//NeurIPS. 2017: 5998-6008."],
               "bibtex": ["@inproceedings{vaswani2017attention, booktitle={NeurIPS}, ...}"]}}
```

## 异常处理

| 情况 | 处置 |
|---|---|
| 参考文献跨页被拆断 | 解析时按“下一个编号”合并续行 |
| 正文用作者-年制且重名 | 结合年份与标题判定，无法判定则列为待确认 |
| DOI 缺失 | 不做外部检索，标注 `doi: ""`，不虚构 |
| 卷期页缺失 | 该段直接省略（不写 `, : .`），并把条目列入可疑清单 |
| 类型判错（会议写成期刊） | `type` 依据 venue 词形（proceedings/workshop/conference）判定，判不出按 `J` 并标注 |

## 适用边界

不联网核验真实性（评委环境可能无网络）；只做结构一致性与格式，不判断学术相关性。

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
