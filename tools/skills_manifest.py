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
6. **表格与公式**：优先引擎表格识别（`find_tables` / `extract_tables`），失败时用“行内多列宽间隙”
   兜底；公式按数学符号密度 + 编号 `(12)` 识别，同一公式的碎片行合并。
7. **证据粒度**：每个块得到 `p03-b012` 这样的稳定 id，页码、栏号、bbox、章节路径一并保留。""",
        "output": """`result.json` 主要字段：

| 字段 | 内容 |
|---|---|
| `document` | 标题、作者、摘要、关键词、DOI、页数、引擎、PDF sha256 |
| `structure` | 章节树（level/title/page/block） |
| `content.blocks` | 全量块：id、page、column、section、type、text |
| `content.tables` | 表格：caption、header、rows、markdown、行列数、来源 |
| `content.formulas` | 公式：编号、文本、所在块 |
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
        "method": """**术语先锁定，再逐段翻译，最后机器核验。**

1. **切段**：按块（而非按页）切分，块内再按句边界合并到 ≤850 字符，得到 `s0001…` 段号；
   每段保留 `block`、`page`、`section`，因此译文永远能回到原文位置。
2. **术语表**：从全文抽高频术语/缩写（`X (ABC)` 形式优先），与内置学术词表合并；
   同一术语只允许一个译名，冲突由 `verify.py` 报错。
3. **保护令牌**：每段提前抽出数字、单位、引用标记 `[12]`、图表编号、公式片段、模型/数据集专名，
   译文中必须原样出现——这一步把“翻译时把 28.4 BLEU 写成 28.4 分”这类错误变成机器可查的问题。
4. **逐段翻译**：Agent 按段填 `translation`，只译该段，不合并、不省略、不添加解释。
5. **核验**：`verify.py` 检查空译、数字/单位/引用丢失、译文长度异常、术语一名多译。""",
        "output": """`result.json` 主要字段：

| 字段 | 内容 |
|---|---|
| `segments[]` | `seg`、`block`、`page`、`section`、`source`、`protected`、`translation` |
| `glossary[]` | 术语、出现次数、建议译名 `zh` |
| `rules` | 术语策略、必须原样保留的令牌、语域要求 |

`translation` 初始为空是**设计如此**：这一栏必须由模型逐段填写，脚本不生成译文。""",
        "example": """```bash
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
```""",
        "failure": """| 情况 | 处置 |
|---|---|
| 段落过长导致截断 | 按句边界再切，禁止从句子中间截断 |
| 术语表冲突 | 以首次出现并在标题/摘要中使用的译名为准，其余全部改齐 |
| 公式/符号无法翻译 | 原样保留，前后文用中文衔接，不改写公式 |
| 原文本身残缺（PDF 丢字） | 译文中用 `[原文缺失]` 标注，不猜测 |""",
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

1. **实体**：方法（transformer/bert/attention…）、数据集（`X dataset/corpus`）、指标（BLEU/F1/AUC…）、
   任务（translation/classification…）、章节标题作为 concept 节点。
2. **关系**：`uses`、`evaluated_on`、`outperforms`、`improves` 四类句式模板匹配；
   每条边必须带 `evidence.block` 与匹配到的原句片段。
3. **别名归一**：小写、去连字符、去复数后聚类；同一 canonical 下多个节点进 `alias_groups`，
   保留原始写法，不做不可逆合并。
4. **查询**：按关系类型各给一组示例查询及答案子图，并显式列出“无法确定的关系”。
5. **导出**：JSON（nodes/edges）+ Cypher `MERGE` 语句，便于导入 Neo4j。""",
        "output": """| 字段 | 内容 |
|---|---|
| `nodes[]` | id、label、type、evidence（block/page/section）|
| `edges[]` | source、target、relation、evidence（含原句）|
| `alias_groups[]` | 归一后的同义节点 |
| `queries[]` | 查询语句 + 结果子图 |
| `stats` | 节点数、边数 |""",
        "example": """```bash
python3 scripts/run.py --input /input --out /app/output --profile kg
```

示意输出（**示例，非正式案例结果**）：

```json
{"nodes": [{"id": "n001", "label": "Transformer", "type": "method"}],
 "edges": [{"source": "n001", "target": "n004", "relation": "evaluated_on",
            "evidence": {"block": "p08-b012", "page": 8, "quote": "We evaluate on WMT 2014 English-to-German."}}]}
```""",
        "failure": """| 情况 | 处置 |
|---|---|
| 共现但无关系句 | 不建边，记入“未确定关系” |
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
4. **改写（Agent 执行）**：按 `edit_record_schema` 逐条产出，一条记录只改一处，
   `kept` 字段列出该句必须保留的数字、单位与引用。
5. **守住语义**：数字、单位、引用编号、否定范围、限定词强度、因果/相关措辞不得变化；
   违反时宁可少改。""",
        "output": """| 字段 | 内容 |
|---|---|
| `genre` | 判定出的文体 |
| `sentence_issues[]` | block、原句、flags |
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

1. **条目解析**：编号、作者串、年份、标题（引号内优先）、DOI、原文串。
2. **正文引用抽取**：`[12]`、`[3–5]` 区间展开、`(Author, 2020)` 作者-年制；记录每处出现的 block。
3. **一致性**：`citations_without_entry`（引了但列表没有）、`entries_never_cited`（列了但没引）、
   `numbering_gaps`（编号缺号/重号）。
4. **去重**：DOI 相同 → 同一条；无 DOI 时用标题归一化（去标点、小写、截断）比对，
   只报告“疑似”，不自动合并。
5. **格式化**：同时输出 GB/T 7714、APA 与 BibTeX 三种写法；BibTeX 的 citation key 由
   「第一作者姓氏 + 年份 + 标题首个实词」生成，稳定可复现。字段缺失处留空而不是编造。
6. **可疑条目**：无年份、无 venue、标题异常、DOI 形态不合法，单独列出待人工核验。""",
        "output": """| 字段 | 内容 |
|---|---|
| `entries[]` | n、authors、year、title、doi、page、block |
| `in_text_citations` | 编号 → 出现的 block 列表 |
| `issues` | 缺条目、未被引、重复、编号缺口 |
| `formatted` | GB/T 7714 与 APA 文本 |
| `stats` | 条目数、被引编号数 |""",
        "example": """```bash
python3 scripts/run.py --input /input --out /app/output --profile refs
```

示意输出（**示例，非正式案例结果**）：

```json
{"issues": {"citations_without_entry": ["27"], "entries_never_cited": ["31"],
            "duplicates": [{"a": "12", "b": "28", "key": "10.18653/v1/2020.acl-main.1"}]}}
```""",
        "failure": """| 情况 | 处置 |
|---|---|
| 参考文献跨页被拆断 | 解析时按“下一个编号”合并续行 |
| 正文用作者-年制且重名 | 结合年份与标题判定，无法判定则列为待确认 |
| DOI 缺失 | 不做外部检索，标注 `doi: ""`，不虚构 |""",
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
3. **空白推导**：`however/remains/few studies/has not been` 句作为空白证据，必须来自已引文献。
4. **贡献映射**：`we propose/introduce/show` 句作为贡献条目，并要求每条能指向正文的图/表/结果块。
5. **引用覆盖**：统计引言中出现的引用编号与参考文献条目数，标出“引了但没在引言出现”的关键工作。""",
        "output": """| 字段 | 内容 |
|---|---|
| `problem_statements[]` | 具体困难句 + block |
| `related_work_groups[]` | 分组、代表条目、gist |
| `gap_statements[]` | 空白句 + block |
| `contributions[]` | 贡献句 + block |
| `citation_coverage` | 引用编号数 vs 条目数 |
| `outline` | 建议的五段式论证骨架 |""",
        "example": """```bash
python3 scripts/run.py --input /input --out /app/output --profile intro
```

示意输出（**示例，非正式案例结果**）：

```json
{"gap_statements": [{"text": "However, how much of this advantage comes from linguistic vs acoustic properties remains unclear.",
  "block": "p02-b007", "page": 2}]}
```""",
        "failure": """| 情况 | 处置 |
|---|---|
| 论文没有显式 gap 句 | 用“共同限制”归纳，并标注为推论而非原文 |
| 贡献与结果对不上 | 在 `uncertainty` 标出“贡献无对应证据” |
| 相关工作节缺失 | 只用引言内的引用构建分组，并说明来源受限 |""",
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
5. **缺口显式化**：missing 项写进 `uncertainty.missing`，并给出“需要作者确认”的具体问题。""",
        "output": """| 字段 | 内容 |
|---|---|
| `parameters[]` | 名称、值、上下文、block、page |
| `datasets[]` | 名称、描述句、block |
| `hardware[]` / `seeds[]` | 环境与随机性证据 |
| `reproducibility_checklist[]` | 8 项 found/missing |
| `missing[]` | 原文未报告项 |
| `limitations[]` | 限制条件句 |""",
        "example": """```bash
python3 scripts/run.py --input /input --out /app/output --profile methods
```

示意输出（**示例，非正式案例结果**）：

```json
{"parameters": [{"name": "layers", "value": "6", "context": "a stack of N = 6 identical layers",
  "block": "p03-b005", "page": 3}],
 "reproducibility_checklist": [{"item": "random seeds", "found": false}]}
```""",
        "failure": """| 情况 | 处置 |
|---|---|
| 参数只在图/表中 | 从表格行取，标注来源为表格而非正文 |
| 正文与配置冲突 | 两条都记录并标 `conflict`，不擅自取舍 |
| 值缺失 | 留空 + 进 missing，禁止用“常见默认值”填充 |""",
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
6. **真编译**：检测 `pdflatex/latexmk/xelatex`，编译两次，抓 `!` 开头的错误行；
   引擎缺失时明确写 `compile.attempted: false`，不谎报成功。""",
        "output": """| 字段 | 内容 |
|---|---|
| `files` | 生成的文件清单（`main.tex`、`latex/main.tex`）|
| `tex` | 源码（截断展示）|
| `compile` | 是否尝试、引擎、是否成功、错误行、是否产出 PDF |
| `structure` | 章节映射结果 |
| `environment` | 引擎与宏包依赖 |""",
        "example": """```bash
python3 scripts/run.py --input /input --out /app/output --profile latex
ls /app/output/latex/main.tex
python3 scripts/verify.py --out /app/output --kind generic
```

示意输出（**示例，非正式案例结果**）：

```json
{"compile": {"attempted": true, "engine": "pdflatex", "ok": true, "pdf": true, "errors": []}}
```""",
        "failure": """| 情况 | 处置 |
|---|---|
| 无 TeX 引擎 | `attempted: false`，交付源码 + 所需宏包清单，说明未验证编译 |
| 编译报错 | 保留 `.log`，把首条 `!` 错误与行号写进 `compile.errors` |
| 缺字体/中文 | 提示改用 `xelatex` + `ctex`，不偷偷删内容求编译通过 |""",
        "limits": "不追求期刊模板的像素级还原；复杂浮动体排版需人工微调。",
    },
]
