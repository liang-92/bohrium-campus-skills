### 文献知识图谱构建：科研阅读：回答问题，也给出依据

#### 1. 题目介绍

你需要围绕“文献知识图谱构建”制作一个可被 Agent 调用的 Skill，在组织方提供的 3 个固定科研案例上完成实际任务，并交付能够被复核的结果。  
读取固定科研材料并完成本题指定的解析、翻译、问答、提取、核验或知识结构化，关键结果回到原文证据。

组织方为本题准备 3 个固定案例。每个案例包含任务说明、科研材料、必要的输入约束和评分所需的证据范围；案例会以相同内容分别交给基础 Agent 和加载参赛 Skill 的 Agent。你不需要自带正式测试案例，也不需要提交预先写好的答案。

1. 先识别输入材料和问题边界。
2. 按题目要求完成阅读或解析动作。
3. 为关键结论保留页码、段落、字段或图表定位。
4. 对未报告、无法判断和材料冲突明确说明。

围绕一个明确科研主题，开发能够从论文抽取实体和关系、绑定证据并支持基本查询的可运行图谱工作流。  
可选择实体关系抽取、别名归一、来源绑定、图谱导出、关系查询、增量更新等具体方向。允许聚焦一个问题，不要求开发完整的文献知识图谱构建系统。  
本课题重点关注四个问题：  
抽得准： 实体是否对应论文里真实出现的科研对象（研究者、材料、方法、任务、指标、结论），而不是模型凭常识补全的概念。连得对： 关系类型、方向和适用条件是否与原文一致，没有把共现、综述转述或推测当成直接证据。对得齐： 同一对象在不同论文中的别名、缩写、大小写和同名冲突是否被正确处理，既不产生重复节点，也不把不同对象错误合并。查得到、回得去： 图谱能否回答真实查询，并且每个节点和每条边都能回到论文的具体位置和原文片段。

可选择的突破方向：  
优先考虑以下六个方向，也允许提出其他具有明确科研价值的图谱构建问题。  
实体识别： 抽取研究者、材料、方法、任务、指标和结论等实体，保留原文位置与表述原文，区分作者自述与他人转述。实体对齐： 处理别名、缩写、大小写、全称与简称、同名实体，给出合并依据，避免重复节点和错误合并。关系抽取： 只建立有证据支持的关系，明确关系类型（例如使用、比较、优于、支持、矛盾）、方向和适用条件。来源绑定： 为每个节点和每条边保留可回查的证据（论文标识、章节或图表位置、原文片段），并标注证据强度。图谱查询： 提供至少 3 个真实查询，展示结果子图、支撑证据以及无法确定的关系。增量更新： 在新论文加入时保留既有节点与编号，说明新增、合并和冲突关系的处置方式，并能导出可读的图谱文件。  
参赛者只需要选择一个明确问题，形成能够真实运行、独立验证、持续改进的最小成果。

平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

#### 2. 评分维度概要

原题满分 **100 分**。GitHub 公开作品链接为额外附加分，最高加 **5 分**。综合三个固定案例的实际表现和提交材料评分，各评分项只计一次；本节只展示评分维度、分值和考察内容，不展示内部详细分档。

| 评分维度 | 分值 | 评分点及分值 | 考察内容 |
|-|-|-|-|
| 实际效果 | 40 分 | 任务完成度 15 分；结果正确性 15 分；结果完整性 5 分；结果可核验性 5 分 | 是否真正把一批论文转成带证据的节点与边，并按任务要求交付可查询的图谱。；实体是否真实出现在论文中、关系类型与方向是否与原文一致、实体合并是否正确。；是否覆盖任务要求的实体类型、关系类型、证据字段与查询问题。；节点与边能否回到论文的具体位置和原文片段，合并与冲突处置是否有记录。 |
| 使用增益 | 25 分 | 质量增益 15 分；效率增益 5 分；增益可验证性 5 分 | 相同文献与要求下，相比不加载 Skill 的基础 Agent，图谱质量是否提升。；是否减少逐篇摘录、人工比对、重复合并与查询返工。；是否通过同输入对照证明改善。 |
| 创新增益 | 15 分 | 新增能力 5 分；方法改进 5 分；创新证据 5 分 | 是否形成基础 Agent 或现有方案不具备的跨篇对齐、证据绑定或增量更新能力。；实体规范化、关系约束、证据定位或冲突处理方法是否带来实质改进。；是否证明创新点相对已有方案的边界和价值。 |
| 可靠体验 | 10 分 | 调用与易用性 3 分；运行稳定性 4 分；异常处理 3 分 | Agent 能否正确触发，用户能否按说明对一批论文完成一次构建与查询。；在不同主题、不同文献质量和重复运行下能否持续产出可用图谱。；对文献缺失、PDF 无法解析、实体同名、关系证据冲突、查询无结果等情况的识别与处置。 |
| 生态贡献 | 10 分 | 文档完整性 3 分；资源可复用性 4 分；分享推广价值 3 分 | 实体与关系类型定义、依赖、示例、适用范围和维护信息是否齐全。；Skill 本体、脚本、schema、题集、参考图谱和查询模板能否被他人复用。；是否沉淀可分享的案例、图谱样例、标注经验和真实应用价值。 |

质量与增益以平台固定案例、基础 Agent/Skill Agent 对照结果和可核验记录为依据；文字自述不能替代实际运行证据。

**GitHub 公开作品链接（5 分）**　提交本题作品的 GitHub 公开链接。评审无需登录即可打开链接并找到本次提交的作品，得 5 分。缺交或经核实链接无效，本项得 0 分，其他评分项按原规则计分。

#### 3. 交付要求

**提交材料**

参赛者只提交 Skill 及其必要资源；平台统一使用本题固定的 3 个案例运行 Skill。

| 材料 | 必需内容 | 交付标准 |
|-|-|-|
| Skill 本体 | `SKILL.md`，以及实际使用的提示、规则或处理流程；写清用途、适用条件、调用方式、输入输出和异常处理。 | 平台能据此加载并执行给定案例，不能用预制答案代替实际运行。 |
| 运行必需的脚本与资源 | 实际依赖的脚本、配置、模板、词表或其他资源；写清版本、安装方式、路径、来源和使用条件。 | 文件齐备、路径有效，不依赖作者未说明的个人文件或手工操作。 |
| 使用与方法说明 | 完整调用步骤、输入输出解释、关键方法、适用场景、限制、失败处理和自查方法。 | 其他人或 Agent 可按说明独立使用，说明与提交版本一致。 |
| 最小调用示例 | 至少一组输入、调用方式和示意输出；示意输出须标明为示例。 | 足以说明接口和完整使用流程，不冒充正式案例结果。 |

**Skill 运行后的输出要求**

每个案例返回一份结构化结果，保留输入标识、主结果、证据/来源定位、运行状态和不确定性。

| 内容 | 字段与要求 |
|-|-|
| 阅读/解析结果 | 按题目要求的答案、结构化字段、翻译或知识结构；完成标准：覆盖任务要求且能回到材料定位 |
| 证据与边界 | 页码、段落、图表、字段或公式位置；未报告和不确定项；完成标准：关键结论可复核，无法判断不被写成事实 |
| 运行状态 | 成功、部分完成、无法判断或拒答及原因；完成标准：异常原因和可人工接管位置清楚 |

正式测试案例、白板和测评结果由平台提供或生成，参赛者无须另交三个测试案例、白板或预先生成的正式答案。材料缺失、无法判断和运行失败要分别说明。

**本题作品的 GitHub 公开链接**　请在提交材料中填写作品所在的 GitHub 仓库、目录或文件链接。如一个仓库包含多个作品，请直接链接到本题作品所在位置，或在链接旁注明目录或文件名。提交前请用未登录 GitHub 的浏览器窗口打开一次，确认能看到作品。

请在提交目录根路径放置 `GITHUB_URL.txt`，第一行写 GitHub 链接。如需指定作品文件，可在第二行写本次提交目录中的相对文件路径。

## Harbor技术提交约定

# Runtime contract
This is a Skill authoring task. Create /app/submission/SKILL.md and any required text resources. Use valid name/description YAML frontmatter. Do not submit prepared answers or formal test outputs. The evaluator installs the actual Skill under /skills/weekly-skill, then runs official DeepSeek Harness on each fixed original case.

At execution time original input is /input/case.json and task.md. Material and artifacts are provided according to the topic; PDF parsing receives the actual PDF without a pre-extracted answer layer. Read actual files instead of assuming source content from labels. Work under /app/work; final actual results and editable artifacts belong under /app/output, including result.json with all original output_contract fields and case_id. Include honest status, sources, uncertainty and change records. Editable Office/slide/diagram outputs should also have real rendered PDF/PNG previews for inspection. A partial result must identify its limits. Do not fabricate missing software state or scientific data.

Model, source/case versions, runtime, budgets and actual native traces are recorded by the platform; do not invent benchmark scores. Execution budget: 64 model requests, 900 seconds, 16384 tokens per response including reasoning. Save honest partial deliverables early and improve incrementally. Three cases, three repetitions per condition; actual service failures are paused separately. The platform provides/generates any required comparison; participants do not provide hidden tests or whiteboards. Skill resources: at most 50 UTF-8 text files, 500KB each and 2MB total, no symlinks. Runtime artifacts may be binary and are retained independently of final JSON validity.

实际输入文件和原论文是事实依据；不依据错误的领域标签补造数据。


输入修订：本案例输入修订：现在提供两篇独立、真实且许可可再分发的论文文本，而不是把同篇JSON与Markdown当两篇。corpus-manifest.json列出各DOI、作者、来源哈希和许可证；material.json是两篇正文段落的汇总索引，primary-material.json保留原论文，secondary-material.json是新增论文，均可回溯各自原文。根DOI/title/authors属于第一篇，不得套到第二篇。

在同一图谱中保留两篇材料的节点、关系与来源，按原题选择可运行的实体关系/证据绑定与查询工作流；给出至少3个实际执行的查询及其结果和证据。记录跨篇候选同一概念的合并依据与不得合并的冲突/不同对象；不能强迫每个别名都合并，也不能把不同论文的条件、样本和数值结果合成一个结论。相同通用方法/材料术语不代表两篇使用了相同物理样品、模型实例、数据集或实验条件。只存在同篇多种文件格式不算跨篇证据。

每个实质节点/边使用独立论文source_id、paragraph_id及原文短引。位置是组织方JATS段落ID，不是实际PDF页码；本包无PDF页码，不得把自建页面1称原PDF页。正文行内公式/上下标被线性化，原secondary-publisher.xml留供核对；不提供图像像素、补充附件、底层临床或实验数据，不推断其中数值。未报告和源内冲突明确保留。输入文件集合及要求同时交给基础Agent和SkillAgent，不提供图谱答案。


Resource entry point: environment/resources.yaml. Bundled files are relative to that directory; declared preinstalled runtime paths describe the pinned image. The actual fixed scientific cases are supplied by the evaluation platform.


---

题面已公开，正式提交开放时间以赛事通知为准。
