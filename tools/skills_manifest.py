"""Metadata + SKILL.md bodies for the ten skills.

Kept as data so the builder can stamp identical scripts into every package while
each SKILL.md stays specific about its own method, output and failure modes.
"""

COMMON_ENV = """runtime: python3
python: ">=3.9"
packages:
  required: []
  optional:
    - name: pymupdf        # fastest, best layout fidelity
      version: ">=1.23"
    - name: pdfplumber     # fallback table extractor
      version: ">=0.10"
    - name: pypdf          # last-resort text layer
      version: ">=3.0"
system_tools:
  - name: pdftotext      # poppler, optional
  - name: tesseract      # OCR, optional
bundled:
  - scripts/pk/          # paperkit core, pure python, no network
  - scripts/run.py       # one-command pipeline
  - scripts/verify.py    # post-check
  - scripts/compose_all.py
limits:
  network: not required
  files: "50 text files, 500KB each, 2MB total, no symlinks"
"""

SKILLS = [
    {
        "slug": "paper-parse",
        "name": "paper-parse",
        "mode": "parse",
        "challenge": "阅读01 文献文档解析",
        "title": "Paper Parse",
        "description": "Parse a research PDF into an evidence-linked structure (sections, blocks, tables, formulas, figures, references) where every string carries a page and block id. Use when a task asks to extract, verify, quote or audit the content of a scholarly PDF, especially two-column layouts, cross-page tables or scanned pages.",
        "description_zh": "中文触发：文献文档解析 / 解析论文 PDF / 抽取正文、章节、表格、公式、图与参考文献的位置，并给出页码与块号，便于复核与引用；适用于双栏排版、跨页表格、扫描件。",
        "when": [
            "任务要求“把这篇 PDF 解成结构化结果”“逐段核对”“给出原文定位”",
            "需要从论文里取标题/摘要/章节/表/公式/参考文献并保留页码",
            "双栏、跨栏、跨页表格、扫描件，普通文本抽取会串栏或丢段",
        ],
        "method": """解析不是“取一段看起来像全文的文本”，而是重建版面：

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
6. **作者抽取**：先定位“标题块之后、Abstract 之前”的作者区，再在区内收 2–4 个大写词组成的连续人名，
   剔除邮箱、`∗` 等标记以及机构词/城市名（Toronto、Tilburg…）；不足 2 人时置 `authors_uncertain`
   ——比“按逗号硬切”可靠得多，也不会把 `Toronto Łukasz Kaiser` 这种跨栏残留当成人名。
7. **表格**：**先试无边框策略** `find_tables(strategy="text")`（学术论文的表多数只有横线，
   默认的 `lines` 策略会把 8×13 的表压成 8×3），失败再退回默认策略。
   行内容不直接取引擎的单元格矩形——那些矩形落在**文字基线**上，会把相邻行整行带进来
   （5 行的表变成 10 行、`24.1` 被拆成 `241` 和 `.`）。改为**按文字基线聚类成行、按水平重叠归列**，
   引擎只提供列边界；行数与基线数一致时直接一一映射，二者不一致才退回引擎单元格 +
   多行行展开。`0.1 | 0.1 | 100K | 4.92 | 25.8 | 65` 这类基线上的 6 个数因此能原样恢复。
8. **公式**：按数学符号密度 + 编号 `(12)` 识别，同一公式的碎片行合并；同时给出 `tex` 字段
   （√→`\\sqrt{}`、希腊字母/上下标映射、`&%$#_{}` 转义），丢字符数记进 `tex_dropped_chars`，
   含非 ASCII 无法映射时 `tex_confidence: low`——让下游能判断“这条公式能不能直接用”。
9. **证据粒度**：每个块得到 `p03-b012` 这样的稳定 id，页码、栏号、bbox、章节路径一并保留。""",
        "output": """`result.json` 主要字段：

| 字段 | 内容 |
|---|---|
| `document` | 标题、作者（含 `authors_uncertain`）、摘要、关键词、DOI、页数、引擎、PDF sha256 |
| `structure` | 章节树（level/title/page/block） |
| `content.blocks` | 全量块：id、page、column、section、type、text（表格单元格不再混进正文流） |
| `content.tables` | 表格：caption、header、rows、markdown、行列数、`n_rows`/`n_cols`、来源策略 |
| `content.formulas` | 公式：编号、文本、所在块、`tex`、`tex_confidence`、`tex_dropped_chars` |
| `content.figures` | 图：页码、bbox、caption |
| `content.references` | 参考文献条目：编号、文本、页码、块 |
| `coverage` | 每页字符数、空页、栏数、问题清单 |""",
        "example": """```bash
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
```""",
        "failure": """| 情况 | 处置 |
|---|---|
| 扫描件无文字层 | 自动 OCR；OCR 页写入 `source.ocr_pages`，置信度无法保证时在 `uncertainty` 注明 |
| 加密/损坏 PDF、目录里没有 PDF | 捕获异常，`status: unable` + `input.problem`，写明原因，不伪造文本，仍写出 `result.json` |
| 有 PDF 但零提取（无文本层且无 OCR） | `status: unable`，不是 `partial`——零提取不宣称「读到了一半」；先跑 `--probe` 看缺哪个引擎 |
| 表格识别为空 | 用行间隙兜底；仍为空则在 `coverage.issues` 说明“该页无表格或引擎不支持” |
| 表格只有横线（无竖线） | 先走 `strategy="text"` 重建列；列仍错位则保留原行文本并标 `table_uncertain`，不输出假的“整齐表格” |
| 作者区被双栏切断 | 用作者区 + 机构词/城市停用词过滤；仍不足 2 人则 `authors_uncertain: true`，不猜 |
| 字体乱码 | 保留原字符并标记，不做“猜测式修正” |""",
        "limits": "不解释图表科学含义；不做翻译或改写；对艺术排版（海报、竖排）只保证可读顺序，不保证视觉对应。",
    },
    {
        "slug": "paper-translate",
        "name": "paper-translate",
        "mode": "translate",
        "challenge": "阅读03 文献翻译",
        "title": "Paper Translate",
        "description": "Translate research papers segment by segment with a locked glossary, protected numbers/units/citations and a verification pass. Use when a task asks for a Chinese translation of a paper, bilingual paragraph alignment, terminology consistency, or a translation QA report.",
        "description_zh": "中文触发：文献翻译 / 中英对照 / 术语一致性 / 翻译质检；逐段翻译并锁定术语表，数字、单位、引用编号原样保留，输出翻译核验报告。",
        "when": [
            "任务要求翻译论文/摘要/章节，并要求术语统一、可回看原文",
            "需要段落级双语对照、译后核验、译不准处标注",
            "长文跨页跨栏，直接整篇翻译会漏段、串段、术语漂移",
        ],
        "method": """**术语先锁定，再按批翻译，最后机器核验。**

1. **切段**：按块（而非按页）切分，同页同节内相邻块合并到 ≤700 字符，得到 `s0001…` 段号；
   每段保留 `block`、`page`、`section`、`type`，因此译文永远能回到原文位置。
   参考文献、附录、致谢整节跳过；表格单元格内的文字不切段（表格另由 parse 通道处理），
   避免把“表 3 的 0.1/4.92/25.8”当成正文句子去译。
2. **控量**：总段数封顶 120 段，超出时按“摘要 > 引言/结论 > 方法 > 讨论”的优先级保留、
   其余计入 `deferred_segments` 并在 `notes` 里报数量——宁可明确少译，也不为了凑满而把
   一次 64 请求的预算花在参考文献上。
3. **分批**：`batches` 把段号切成每批 ≤20 段（对应 `rules.batch_size = 20`），
   一次模型请求译一批，避免单次输出被 16384 token 截断而中途丢失后半段。
4. **术语表**：从全文抽高频术语/缩写（`X (ABC)` 形式优先），与内置学术词表合并；
   同一术语只允许一个译名，冲突由 `verify.py` 报错。
5. **保护令牌**：每段提前抽出数字、单位、引用标记 `[12]`、图表编号、公式片段、模型/数据集专名，
   译文中必须原样出现——这一步把“翻译时把 28.4 BLEU 写成 28.4 分”这类错误变成机器可查的问题。
6. **回灌**：Agent 把译文写进 `fill.json` 的 `segments`（`{seg, translation}` 列表），
   重跑 `run.py --fill` 合并；“译了哪些、还剩哪些”由脚本统计，不靠人记。""",
        "output": """`result.json` / `payload.json` 主要字段：

| 字段 | 内容 |
|---|---|
| `segments[]` | `seg`、`block`、`page`、`section`、`type`、`source`、`protected`、`translation` |
| `batches` | 段号分批，每批 ≤20 段 |
| `deferred_segments` | 因 120 段上限被推迟的段数（0 表示全译） |
| `glossary[]` | 术语、出现次数、建议译名 `zh` |
| `rules` | 术语策略、必须原样保留的令牌、语域、`batch_size`、`how_to_fill` |
| `run.fill` | `--fill` 后回填的段数与仍未译的段数 |

`translation` 初始为空是**设计如此**：这一栏必须由模型逐段填写，脚本不生成译文。""",
        "example": """```bash
python3 scripts/run.py --input /input --out /app/output        # 生成分段、术语表、分批
# Agent 每批 ≤20 段翻译，写 fill.json：{"segments": [{"seg": "s0001", "translation": "..."}]}
python3 scripts/run.py --input /input --out /app/output --fill  # 回灌并统计
python3 scripts/verify.py --out /app/output --kind translate    # 译后核验
```

示意输出（**示例，非正式案例结果**）：

```json
{"segments": [{"seg": "s0001", "block": "p01-b005", "section": "Abstract",
  "source": "The dominant sequence transduction models are based on complex recurrent networks.",
  "protected": {"numbers": [], "citations": []},
  "translation": "主流的序列转换模型基于复杂的循环神经网络。"}],
 "batches": [["s0001", "s0002"]], "deferred_segments": 0,
 "run": {"fill": {"applied": 1, "missing": 0}}}
```""",
        "failure": """| 情况 | 处置 |
|---|---|
| 段落超过 700 字符 | 先按块边界切，再退化为定长切；不从句中截断句子语义 |
| 总段数超过 120 | 按章节优先级截断，`deferred_segments` 如实报数，不假装全译 |
| 术语表冲突 | 以首次出现并在标题/摘要中使用的译名为准，其余全部改齐 |
| 公式/符号无法翻译 | 原样保留，前后文用中文衔接，不改写公式 |
| 原文本身残缺（PDF 丢字） | 译文中用 `[原文缺失]` 标注，不猜测 |
| 扫描件/乱码页无正文 | 该页不进分段，`notes` 说明跳过原因，不编造译文 |""",
        "limits": "不润色原文、不补写原文没有的内容；诗歌、广告等非学术文体不在适用范围。",
    },
    {
        "slug": "paper-notes",
        "name": "paper-notes",
        "mode": "notes",
        "challenge": "阅读10 文献总结与结构化笔记",
        "title": "Paper Notes",
        "description": "Turn a paper into a structured reading note: research question, data, methods, findings, limitations, per-section gists and knowledge items, each linked to a page and block. Use when a task asks for a paper summary, reading card, literature note or structured extraction that must stay traceable to the source.",
        "description_zh": "中文触发：文献总结 / 阅读笔记 / 论文卡片 / 结构化摘要；输出研究问题、数据、方法、结论、局限、分节要点与知识点，每条都能回到原文页码。",
        "when": [
            "任务要求“总结这篇论文”“做阅读笔记/论文卡片/结构化摘要”",
            "需要按论文章节而不是通用模板组织内容",
            "笔记要能回到原文位置，供后续写作或复核",
        ],
        "method": """笔记的骨架跟随论文本身，而不是套模板。

1. **先建骨架**：用解析出的章节树作为笔记目录，章节缺失时才回退到“摘要/方法/结果/讨论”。
2. **按论证功能取句**：研究问题（`we study/investigate/address`）、方法（`we use/train/apply`）、
   发现（`we find/show/observe/outperform`）、局限（`limitation/future work/only/cannot`）、
   贡献（`we propose/introduce`）、数据（含数字的 dataset/corpus 句）。
3. **每节一条 gist**：取该节首段首句作为入口，并记录该节前 8 个块 id，方便展开。
4. **知识点**：抽 `X is/refers to/means …` 型定义，形成可检索条目。
5. **可核验**：卡片每个字段都是 `{text, block, page, section}`，不是纯字符串。""",
        "output": """| 字段 | 内容 |
|---|---|
| `paper_card` | 研究问题、数据、方法、发现、局限、贡献（均带 block/page）|
| `section_notes[]` | 每节 gist + 入口块 + 覆盖块列表 |
| `knowledge_items[]` | 定义型知识点 |
| `glossary[]` | 高频术语 |

`status` 在“无发现句或无章节笔记”时为 `partial`。""",
        "example": """```bash
python3 scripts/run.py --input /input --out /app/output --profile notes
```

示意输出（**示例，非正式案例结果**）：

```json
{"paper_card": {"research_question": [{"text": "This study explores the effect of child-directed speech.",
   "block": "p01-b012", "page": 1, "section": "Abstract"}],
  "findings": [{"text": "We find that CDS helps in the initial stages of learning.", "block": "p01-b014"}]}}
```""",
        "failure": """| 情况 | 处置 |
|---|---|
| 论文无显式局限段 | 留空并在 `uncertainty` 说明“原文未报告”，不臆造局限 |
| 结论分散在讨论中 | 允许跨节取句，但必须记录来源节 |
| 摘要与正文冲突 | 两条都保留，标注冲突点，交人工判断 |""",
        "limits": "不评价论文质量、不做领域外推；单篇论文笔记，不做多篇综述。",
    },
    {
        "slug": "paper-nanopub",
        "name": "paper-nanopub",
        "mode": "nanopub",
        "challenge": "阅读14 Nanopublication",
        "title": "Paper Nanopublication",
        "description": "Split a paper into atomic, checkable assertions and bind each one to its minimal supporting quote, with provenance and machine-readable serialization. Use when a task asks for nanopublications, claim extraction, evidence binding, or machine-checkable statements from a paper.",
        "description_zh": "中文触发：Nanopublication / 原子断言 / 论断抽取 / 证据绑定；把论文拆成可核查的单条断言，并绑定最小支撑引文与出处。",
        "when": [
            "任务要求把结论拆成可判断真假的断言（nanopublication / claim graph）",
            "需要每条断言绑定最小证据片段与原文位置",
            "要输出可被下游程序直接解析的结构",
        ],
        "method": """一条断言只回答一个问题，且必须能被一句话证伪。

1. **候选句**：只在摘要/引言/结果/讨论/结论中取句，长度 40–420 字符，避免图注碎片。
2. **类型判定**：经验（show/find/outperform）、方法（propose/introduce）、因果（because/leads to）、
   比较（better than/outperform）、背景（has been/is known）。类型决定它需要什么证据。
3. **条件抽取**：`when/if/for/under/with/on …` 片段作为 `conditions`，避免断言被过度泛化。
4. **证据绑定**：`evidence.quote` 是原句本身（不是改写），并给 `block/page/section`；
   背景类断言标 `context`，不与直接证据混为一谈。
5. **质量标记**：`all/every/always/never` → `overbroad`；`may/might/suggest` → `hedged`。
6. **来源**：论文标题、作者、DOI、PDF sha256、页数构成 provenance，可据此回原文件。""",
        "output": """| 字段 | 内容 |
|---|---|
| `provenance` | 论文、作者、DOI、sha256、页数、引擎 |
| `assertions[]` | `id`、`assertion`、`type`、`conditions`、`evidence`、`confidence`、`flags` |
| `quality` | 无证据数、过宽泛数、模糊限定数 |

`status` 在断言少于 5 条时为 `partial`（说明材料本身断言密度低，而不是失败）。""",
        "example": """```bash
python3 scripts/run.py --input /input --out /app/output --profile nanopub
```

示意输出（**示例，非正式案例结果**）：

```json
{"assertions": [{"id": "a001", "type": "empirical",
  "assertion": "The Transformer achieves 28.4 BLEU on WMT 2014 English-to-German.",
  "conditions": ["on WMT 2014 English-to-German"],
  "evidence": {"block": "p01-b015", "page": 1, "quote": "Our model achieves 28.4 BLEU on the WMT 2014 English-to-German translation task."},
  "confidence": "high", "flags": []}]}
```""",
        "failure": """| 情况 | 处置 |
|---|---|
| 句子含多个断言 | 拆成多条，各自绑定同一段落的不同片段 |
| 综述转述他人结论 | 标 `type: background`、`confidence: medium`，不当作本文证据 |
| 无法定位原句 | 不生成断言，记入 `uncertainty.missing` |""",
        "limits": "不做事实核查（不查外部数据库）；断言真值需人工或下游流程判定。",
    },
    {
        "slug": "paper-kg",
        "name": "paper-kg",
        "mode": "kg",
        "challenge": "阅读15 文献知识图谱构建",
        "title": "Paper Knowledge Graph",
        "description": "Build a small, evidence-bound knowledge graph from a paper: entities (methods, datasets, metrics, tasks), typed relations, alias groups and answerable queries. Use when a task asks for entity/relation extraction, a literature knowledge graph, or graph export with provenance.",
        "description_zh": "中文触发：文献知识图谱 / 实体关系抽取 / 三元组 / 本体构建；输出方法、数据集、指标、任务等实体与带类型的关系统计，附别名组与可查询导出。",
        "when": [
            "任务要求从论文抽实体与关系、建知识图谱",
            "需要别名归一、关系方向与条件、来源绑定",
            "要导出可查询的图（JSON/Cypher/DOT）",
        ],
        "method": """只建有证据的边，宁可少建，不可猜建。

1. **种子节点**：方法（transformer/bert/attention…）、数据集（`X dataset/corpus`）、指标（BLEU/F1/AUC…）、
   任务（translation/classification…）；`Introduction/Conclusion/References` 这类**无信息标题不进图**
   （它们不是概念，进了只会拉低图的可读性）。
2. **关系（两遍）**：
   - 句式模板：`uses`、`trained on`、`evaluated on`、`outperforms`、`improves`、`proposes` 六类线索动词；
   - 共现兜底：同一句里两个已识别实体共现时建 `related_to`，关系弱，但方向与来源都写清楚。
   每条边必须带 `evidence.block` 与匹配到的原句片段（≤300 字符），没有证据句就不建边。
3. **别名归一**：小写、去连字符、去复数后聚类；同一 canonical 下多个节点进 `alias_groups`，
   保留原始写法，不做不可逆合并。
4. **密度门槛**：节点 ≥8 且边 ≥ `max(10, 节点数×0.4)` 才算建成；达不到就降为 `partial`
   并在 `notes` 说明“图太稀疏，关系句不足”——不拿 3 条边冒充知识图谱。
5. **查询**：按关系类型各给一组示例查询及答案子图，并显式列出“无法确定的关系”。
6. **导出**：JSON（nodes/edges）+ Cypher `MERGE` 语句，便于导入 Neo4j。""",
        "output": """| 字段 | 内容 |
|---|---|
| `nodes[]` | id、label、type、evidence（block/page/section）|
| `edges[]` | source、target、relation、evidence（含原句 quote）|
| `alias_groups[]` | 归一后的同义节点 |
| `queries[]` | 查询语句 + 结果子图 |
| `stats` | `nodes`、`edges` 计数；`complete` 需满足密度门槛 |""",
        "example": """```bash
python3 scripts/run.py --input /input --out /app/output --profile kg
```

示意输出（**示例，非正式案例结果**）：

```json
{"nodes": [{"id": "n001", "label": "Transformer", "type": "method"}],
 "edges": [{"source": "n001", "target": "n004", "relation": "evaluated_on",
            "evidence": {"block": "p08-b012", "page": 8, "quote": "We evaluate on WMT 2014 English-to-German."}}],
 "stats": {"nodes": 34, "edges": 27}}
```""",
        "failure": """| 情况 | 处置 |
|---|---|
| 共现但无关系句 | 只建 `related_to`（弱关系）并保留原句，不硬套 `outperforms` |
| 图太稀疏（边 < 门槛） | 状态降 `partial`，`notes` 说明关系句不足，不硬凑边 |
| 同名不同物 | 保留为两个节点，`alias_groups` 不合并，注明冲突 |
| 代词指代不清 | 丢弃该边，避免把 it/this 错误连到实体 |""",
        "limits": "不引入论文外的常识实体；不做跨论文融合（单篇建图）。",
    },
    {
        "slug": "paper-polish",
        "name": "paper-polish",
        "mode": "polish",
        "challenge": "写作02 学术语言润色",
        "title": "Paper Polish",
        "description": "Diagnose academic prose before rewriting it: long sentences, passive stacking, hedging strength, absolute claims, terminology drift and abbreviation first use. Use when a task asks to polish, edit or proofread academic English/Chinese while preserving meaning, numbers and citations.",
        "description_zh": "中文触发：学术润色 / 语言修改 / 论文校对 / 中式英语；先做句级诊断（长句、被动堆叠、断言强度、术语漂移、缩写首现），再给出改写，保留数字与引用。",
        "when": [
            "任务要求润色/校对/改写学术文本，且不能改变原意与结论强度",
            "需要逐条修改记录（原文/改文/类型/理由）",
            "担心润色时丢限定词、改数字、术语漂移",
        ],
        "method": """先诊断，再改写，最后用规则守住“没改坏”。

1. **句级体检**：长句（>38 词）、被动堆叠、强化词（very/significantly）、绝对化（all/never/prove）、
   缩写（don't）、名词化过重，逐句给 `flags` 与 block id。
2. **术语一致性**：`X (ABC)` 首次定义、`dataset` vs `data set` 等拼写变体、缩写重复定义。
3. **文体判定**：期刊论文 / 学位论文 / 基金申请 / 审稿回复，语气与主语策略不同。
4. **改写（Agent 执行）**：脚本先给出**空改写队列** `rewrites[]`——每条带 block、原句、
   以及 `kept`（该句必须原样保留的数字/单位/引用，由保护令牌抽出）。Agent 只需补
   `revised` 与 `reason`，一条记录只改一处。含数字或引用的句子即使没有文体问题也会进队列，
   因为它们才是改写最容易改坏的对象。
5. **守住语义**：数字、单位、引用编号、否定范围、限定词强度、因果/相关措辞不得变化；
   违反时宁可少改。""",
        "output": """| 字段 | 内容 |
|---|---|
| `genre` | 判定出的文体 |
| `sentence_issues[]` | block、原句、flags、`protected` 令牌 |
| `rewrites[]` | 改写队列骨架：`original`、`revised`（待填）、`kept`、`reason` |
| `consistency[]` | 术语/拼写/缩写不一致 |
| `edit_record_schema` | 修改记录的字段约定 |
| `guardrails` | 改写红线 |""",
        "example": """```bash
python3 scripts/run.py --input /input --out /app/output --profile polish
# Agent 按 schema 产出 edits[]，再自查 guardrails
```

示意输出（**示例，非正式案例结果**）：

```json
{"sentence_issues": [{"block": "p02-b004", "page": 2,
  "sentence": "It is very clear that all models are always better with more data.",
  "flags": ["intensifier", "absolute-claim"]}]}
```""",
        "failure": """| 情况 | 处置 |
|---|---|
| 原句本身语法正确但风格不合 | 标注 `register` 而非 `grammar`，改写幅度最小 |
| 改写后数字/引用丢失 | 直接判为失败，回到原句重写 |
| 中文稿件夹英文术语 | 保留术语原形，只改连接与语序 |""",
        "limits": "不代替作者判断学术观点；不做降重、不做翻译（翻译用 paper-translate）。",
    },
    {
        "slug": "paper-refs",
        "name": "paper-refs",
        "mode": "refs",
        "challenge": "写作04 参考文献与引用管理",
        "title": "Paper References",
        "description": "Audit and rebuild reference lists: parse entries, map in-text citations, detect missing/uncited/duplicate items, check numbering and emit GB/T 7714 / APA / BibTeX. Use when a task involves citation management, bibliography cleanup, reference verification or citation-text consistency.",
        "description_zh": "中文触发：参考文献管理 / 引用核对 / 文献表整理 / 去重 / GB-T 7714 / APA / BibTeX；解析条目、映射正文引用、找出缺失未引用与重复项。",
        "when": [
            "任务要求检查/整理参考文献、正文引用与文末列表是否一致",
            "需要编号更新、去重、格式转换（GB/T 7714、APA、BibTeX）",
            "怀疑有编造条目、重复条目、引用错位",
        ],
        "method": """引用管理的核心是“集合运算 + 字段核对”。

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
   字段缺失处留空而不是编造。
6. **可疑条目**：无年份、无 venue、标题异常、DOI 形态不合法，单独列出待人工核验。""",
        "output": """| 字段 | 内容 |
|---|---|
| `entries[]` | n、authors、year、title、venue、volume、issue、pages、type、doi、page、block |
| `in_text_citations` | 编号 → 出现的 block 列表 |
| `issues` | 缺条目、未被引、重复、编号缺口 |
| `formatted` | `gbt`（GB/T 7714）、`apa`、`bibtex` 三套文本 |
| `stats` | 条目数、被引编号数 |""",
        "example": """```bash
python3 scripts/run.py --input /input --out /app/output --profile refs
```

示意输出（**示例，非正式案例结果**）：

```json
{"issues": {"citations_without_entry": ["27"], "entries_never_cited": ["31"],
            "duplicates": [{"a": "12", "b": "28", "key": "10.18653/v1/2020.acl-main.1"}]},
 "formatted": {"gbt": ["Vaswani A, Shazeer N, Parmar N, et al. Attention is all you need[C]//NeurIPS. 2017: 5998-6008."],
               "bibtex": ["@inproceedings{vaswani2017attention, booktitle={NeurIPS}, ...}"]}}
```""",
        "failure": """| 情况 | 处置 |
|---|---|
| 参考文献跨页被拆断 | 解析时按“下一个编号”合并续行 |
| 正文用作者-年制且重名 | 结合年份与标题判定，无法判定则列为待确认 |
| DOI 缺失 | 不做外部检索，标注 `doi: ""`，不虚构 |
| 卷期页缺失 | 该段直接省略（不写 `, : .`），并把条目列入可疑清单 |
| 类型判错（会议写成期刊） | `type` 依据 venue 词形（proceedings/workshop/conference）判定，判不出按 `J` 并标注 |""",
        "limits": "不联网核验真实性（评委环境可能无网络）；只做结构一致性与格式，不判断学术相关性。",
    },
    {
        "slug": "paper-intro",
        "name": "paper-intro",
        "mode": "intro",
        "challenge": "写作08 引言与相关工作写作",
        "title": "Paper Introduction",
        "description": "Assemble an evidence-bound introduction and related-work outline from a paper: problem statements, grouped prior work, gaps derived from those groups, contributions mapped to results, plus citation coverage. Use when a task asks to write or revise an introduction, related work section or research-gap statement.",
        "description_zh": "中文触发：写引言 / 相关工作 / 研究空白 / 贡献陈述；从论文里抽出问题句、分组的前人工作、由分组推出的空白与对应贡献，并给出引用覆盖。",
        "when": [
            "任务要求写/改引言、相关工作、研究空白与贡献表述",
            "需要“按问题分组比较”而不是逐篇罗列",
            "要保证每条断言都有引用或明确标注为作者判断",
        ],
        "method": """引言不是背景铺垫，是一条从“问题”到“空白”到“贡献”的论证链。

1. **问题句**：抽取 problem/challenge/costly/bottleneck 语境句，区分“领域重要性”与“具体困难”。
2. **相关工作分组**：以章节为初始分组，按问题设定/方法路线/数据与评价三个维度归并，
   每组给出代表工作与该组共同限制。
3. **空白推导**：`however/remains/few studies/has not been` 句作为空白证据，必须来自已引文献；
   一条都抽不到时退化为转折句并标 `derived: true`，明确这是推论而非原文断言。
4. **贡献映射**：`we propose/introduce/show` 句作为贡献条目，并要求每条能指向正文的图/表/结果块。
5. **引用覆盖**：统计引言中出现的引用编号与参考文献条目数，标出“引了但没在引言出现”的关键工作。
6. **成文骨架**：`draft` 预先摆好 5 个空段落（context / prior_work / gap / contributions / scope），
   每段声明 `must_use` 必须用到哪组证据、最少字数、只许引参考文献表里存在的编号。
   Agent 写进 `fill.json` 的 `replace.draft` 后重跑 `--fill`，脚本核对每段非空才把状态抬到 `complete`
   ——空骨架不会被当成“已写好”。""",
        "output": """| 字段 | 内容 |
|---|---|
| `problem_statements[]` | 具体困难句 + block |
| `related_work_groups[]` | 分组、代表条目、gist |
| `gap_statements[]` | 空白句 + block（推论句带 `derived`） |
| `contributions[]` | 贡献句 + block |
| `citation_coverage` | 引用编号数 vs 条目数 |
| `outline` | 建议的五段式论证骨架 |
| `draft` | `status`（`to_be_written`/`written`）+ 5 段骨架 + `rules` |
| `run.fill` | `--fill` 后回填的段落数与仍未写的段落数 |""",
        "example": """```bash
python3 scripts/run.py --input /input --out /app/output --profile intro
# Agent 按 draft.rules 写 5 段，fill.json: {"replace": {"draft": {"paragraphs": [...]}}}
python3 scripts/run.py --input /input --out /app/output --profile intro --fill
```

示意输出（**示例，非正式案例结果**）：

```json
{"gap_statements": [{"text": "However, how much of this advantage comes from linguistic vs acoustic properties remains unclear.",
  "block": "p02-b007", "page": 2}],
 "draft": {"status": "to_be_written", "paragraphs": [{"role": "context", "text": "", "must_use": "problem_statements"}]}}
```""",
        "failure": """| 情况 | 处置 |
|---|---|
| 论文没有显式 gap 句 | 用“共同限制”归纳，标 `derived: true`，不冒充原文 |
| 贡献与结果对不上 | 在 `uncertainty` 标出“贡献无对应证据” |
| 相关工作节缺失 | 只用引言内的引用构建分组，并说明来源受限 |
| `draft` 段落仍为空 | 状态保持 `to_be_written`，不把骨架算作成稿 |""",
        "limits": "不代替作者提出新贡献；不做跨论文综述（只围绕单篇）。",
    },
    {
        "slug": "paper-methods",
        "name": "paper-methods",
        "mode": "methods",
        "challenge": "写作09 方法与实验章节写作",
        "title": "Paper Methods",
        "description": "Extract experimental setup into a checkable parameter table: hyperparameters, datasets and splits, hardware, seeds, metrics, plus a reproducibility checklist with explicit gaps. Use when a task asks to write or audit a methods/experimental section, or to make an experiment reproducible.",
        "description_zh": "中文触发：写方法与实验章节 / 复现性检查 / 超参数与数据集整理；输出参数表、数据集与划分、硬件、随机种子、指标，以及逐项可复现清单。",
        "when": [
            "任务要求写方法与实验章节、整理参数表、检查可复现性",
            "需要把散落在正文/配置/日志里的参数对齐",
            "要明确“哪些条件原文没报告”而不是补一个合理值",
        ],
        "method": """实验章节的价值在于“别人能照着做”。

1. **参数抽取**：`learning rate / batch size / epochs / layers / hidden size / dropout / optimizer …`
   连同上下文片段一起抽出，值可能在同一句后半段，取不到就留空。
2. **数据集**：`X dataset/corpus` 命名实体 + 规模、划分比例、预处理描述句。
3. **环境**：GPU/TPU 型号、框架与版本、随机种子、重复次数。
4. **可复现清单**：8 项逐条判定 found/missing（代码版本、环境、超参、数据版本、种子、硬件、指标、重复）。
5. **缺口显式化**：missing 项写进 `uncertainty.missing`，并给出“需要作者确认”的具体问题。
6. **成文骨架**：`draft` 摆好 4 个空段落（data / model / training / evaluation），
   规则里写死“只准报 `parameters`/`datasets` 里出现过的数字”，从机制上堵住补默认值的路。
   Agent 写进 `fill.json` 的 `replace.draft` 后重跑 `--fill`，四段全非空才抬到 `complete`。""",
        "output": """| 字段 | 内容 |
|---|---|
| `parameters[]` | 名称、值、上下文、block、page |
| `datasets[]` | 名称、描述句、block |
| `hardware[]` / `seeds[]` | 环境与随机性证据 |
| `reproducibility_checklist[]` | 8 项 found/missing |
| `missing[]` | 原文未报告项 |
| `limitations[]` | 限制条件句 |
| `draft` | `status` + 4 段骨架 + `rules`（禁造数值） |
| `run.fill` | `--fill` 后回填的段落数 |""",
        "example": """```bash
python3 scripts/run.py --input /input --out /app/output --profile methods
# Agent 写 4 段后：python3 scripts/run.py --input /input --out /app/output --profile methods --fill
```

示意输出（**示例，非正式案例结果**）：

```json
{"parameters": [{"name": "layers", "value": "6", "context": "a stack of N = 6 identical layers",
  "block": "p03-b005", "page": 3}],
 "reproducibility_checklist": [{"item": "random seeds", "found": false}],
 "draft": {"status": "to_be_written", "paragraphs": [{"role": "data", "text": ""}]}}
```""",
        "failure": """| 情况 | 处置 |
|---|---|
| 参数只在图/表中 | 从表格行取，标注来源为表格而非正文 |
| 正文与配置冲突 | 两条都记录并标 `conflict`，不擅自取舍 |
| 值缺失 | 留空 + 进 missing，禁止用“常见默认值”填充 |
| `draft` 段落仍为空 | 保持 `to_be_written`，不把骨架当成写完的章节 |""",
        "limits": "不执行实验、不推断未报告的超参；不做结果显著性判断。",
    },
    {
        "slug": "paper-latex",
        "name": "paper-latex",
        "mode": "latex",
        "challenge": "写作13 LaTeX 写作与编译",
        "title": "Paper LaTeX",
        "description": "Turn a parsed paper into a compilable LaTeX project: escaped body, section hierarchy, booktabs tables, equation environments, thebibliography, and a real compile attempt with error lines. Use when a task asks to produce or fix LaTeX source, migrate a manuscript into a template, or make a build reproducible.",
        "description_zh": "中文触发：LaTeX 写作 / 生成 tex / 编译论文 / 模板迁移；转义正文、生成章节层级与 booktabs 表格、公式环境、参考文献，并真实编译并回填报错行。",
        "when": [
            "任务要求生成/修复 LaTeX 源码并编译",
            "需要把论文结构、表格、公式、参考文献转成 .tex",
            "编译报错需要定位到文件与行号",
        ],
        "method": """交付的是源码工程，不是一张 PDF 截图。

1. **结构映射**：章节层级 → `\\section/\\subsection/\\subsubsection`，标题去重，跳过重复 running head。
2. **转义**：`\\ & % $ # _ { } ~ ^` 全部转义，避免“一个下划线炸整篇”。
3. **表格**：解析出的表格转 `booktabs`（`\\toprule/\\midrule/\\bottomrule`），列数超 6 时截断并注明。
4. **公式**：公式块进 `equation` 环境，保留原编号文本。
5. **参考文献**：`thebibliography` + `\\bibitem`，编号与正文 `[n]` 对齐。
6. **真编译**：检测 `pdflatex/latexmk/xelatex`，编译**两遍**（第二遍让 `\ref`/目录稳定），
   抓 `!` 开头的错误行；引擎缺失时明确写 `compile.attempted: false`，不谎报成功。
7. **先静态自检**：没有引擎也要能查错——`compile.static_check` 做环境配对（`\\begin/\\end` 是否成对）
   与花括号配平，把“根本编译不过”的源码在提交前就拦下来，而不是等评委编译失败。
8. **公式可核**：`formula_to_tex` 把 √、希腊字母、上下标映射成 LaTeX 命令并转义 `&%$#_{}`；
   含非 ASCII 字符被丢掉的公式记进 `formula_review`，明确标“需人工复核”，不假装全都转对了。""",
        "output": """| 字段 | 内容 |
|---|---|
| `files` | 实际写出的文件清单（`main.tex`、`latex/main.tex`）|
| `tex` | 源码（截断展示）|
| `compile` | `attempted`、`engine`、`ok`、`errors[]`、`pdf`、`passes: 2`、`static_check` |
| `formula_review[]` | 低置信度公式（block、page、编号），需人工确认 |
| `structure` | 章节映射结果 |
| `environment` | 引擎与宏包依赖 |""",
        "example": """```bash
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
```""",
        "failure": """| 情况 | 处置 |
|---|---|
| 无 TeX 引擎 | `attempted: false`，交付源码 + 静态自检结果 + 所需宏包清单，说明未验证编译 |
| 编译报错 | 保留 `.log`，把首条 `!` 错误与行号写进 `compile.errors` |
| 静态自检不过 | `static_check.ok: false` 并列出未闭合的环境/括号，状态降为 `partial` |
| 公式含无法映射的符号 | 记进 `formula_review`，标“需人工复核”，不静默丢字符 |
| 缺字体/中文 | 提示改用 `xelatex` + `ctex`，不偷偷删内容求编译通过 |""",
        "limits": "不追求期刊模板的像素级还原；复杂浮动体排版需人工微调。",
    },
]
