---
name: paper-latex
description: >-
  Turn a parsed paper into a compilable LaTeX project: escaped body, section hierarchy, booktabs tables, equation environments, thebibliography, and a real compile attempt with error lines. Use when a task asks to produce or fix LaTeX source, migrate a manuscript into a template, or make a build reproducible.
  中文触发：LaTeX 写作 / 生成 tex / 编译论文 / 模板迁移；转义正文、生成章节层级与 booktabs 表格、公式环境、参考文献，并真实编译并回填报错行。
version: 1.0.0
license: MIT
---

# Paper LaTeX — 写作13 LaTeX 写作与编译

## 用途

Turn a parsed paper into a compilable LaTeX project: escaped body, section hierarchy, booktabs tables, equation environments, thebibliography, and a real compile attempt with error lines. Use when a task asks to produce or fix LaTeX source, migrate a manuscript into a template, or make a build reproducible.

本 Skill 交付的不是一段“看起来像结果”的文本，而是一份**可复核的结构化结果**：
每条结论都带页码与块 id（`p07-b012` 形式），读不出的部分如实标注，而不是猜。

## 触发条件

- 任务要求生成/修复 LaTeX 源码并编译
- 需要把论文结构、表格、公式、参考文献转成 .tex
- 编译报错需要定位到文件与行号

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

交付的是源码工程，不是一张 PDF 截图。

1. **结构映射**：章节层级 → `\section/\subsection/\subsubsection`，标题去重，跳过重复 running head。
2. **转义**：`\ & % $ # _ { } ~ ^` 全部转义，避免“一个下划线炸整篇”。
3. **表格**：解析出的表格转 `booktabs`（`\toprule/\midrule/\bottomrule`），列数超 6 时截断并注明。
4. **公式**：公式块进 `equation` 环境，保留原编号文本。
5. **参考文献**：`thebibliography` + `\bibitem`，编号与正文 `[n]` 对齐。
6. **真编译**：检测 `pdflatex/latexmk/xelatex`，编译**两遍**（第二遍让 `ef`/目录稳定），
   抓 `!` 开头的错误行；引擎缺失时明确写 `compile.attempted: false`，不谎报成功。
7. **先静态自检**：没有引擎也要能查错——`compile.static_check` 做环境配对（`\begin/\end` 是否成对）
   与花括号配平，把“根本编译不过”的源码在提交前就拦下来，而不是等评委编译失败。
8. **公式可核**：`formula_to_tex` 把 √、希腊字母、上下标映射成 LaTeX 命令并转义 `&%$#_{}`；
   含非 ASCII 字符被丢掉的公式记进 `formula_review`，明确标“需人工复核”，不假装全都转对了。

## 输出

| 字段 | 内容 |
|---|---|
| `files` | 实际写出的文件清单（`main.tex`、`latex/main.tex`）|
| `tex` | 源码（截断展示）|
| `compile` | `attempted`、`engine`、`ok`、`errors[]`、`pdf`、`passes: 2`、`static_check` |
| `formula_review[]` | 低置信度公式（block、page、编号），需人工确认 |
| `structure` | 章节映射结果 |
| `environment` | 引擎与宏包依赖 |

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

本 Skill 的固定用例还不进离线对照：它的产出要由 Agent 用 `fill.json` 写入
译文 / 改写 / 成稿后才完整，纯脚本跑分只会低估，给数字反而误导。
协议与脚本在 `bench/base_agent.py`，评测方按同一 case 跑两遍即可复现。

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
python3 scripts/run.py --input /input --out /app/output --profile latex
ls /app/output/latex/main.tex
python3 scripts/verify.py --out /app/output --kind generic
```

示意输出（**示例，非正式案例结果**）：

```json
{"files": ["main.tex", "latex/main.tex"],
 "compile": {"attempted": false, "engine": "", "ok": false, "passes": 0,
             "static_check": {"env_balanced": true, "braces_balanced": true, "ok": true},
             "errors": []},
 "formula_review": []}
```

## 异常处理

| 情况 | 处置 |
|---|---|
| 无 TeX 引擎 | `attempted: false`，交付源码 + 静态自检结果 + 所需宏包清单，说明未验证编译 |
| 编译报错 | 保留 `.log`，把首条 `!` 错误与行号写进 `compile.errors` |
| 静态自检不过 | `static_check.ok: false` 并列出未闭合的环境/括号，状态降为 `partial` |
| 公式含无法映射的符号 | 记进 `formula_review`，标“需人工复核”，不静默丢字符 |
| 缺字体/中文 | 提示改用 `xelatex` + `ctex`，不偷偷删内容求编译通过 |

## 适用边界

不追求期刊模板的像素级还原；复杂浮动体排版需人工微调。

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
