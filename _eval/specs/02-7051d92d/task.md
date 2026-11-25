### 学术语言润色：学术写作：完成产物，也保留来源

#### 1. 题目介绍

你需要围绕“学术语言润色”制作一个可被 Agent 调用的 Skill，在组织方提供的 3 个固定科研案例上完成实际任务，并交付能够被复核的结果。  
依据固定科研材料完成指定的学术写作、修改、格式、引用、双语或结构化写作产物，保持事实和来源一致。

组织方为本题准备 3 个固定案例。每个案例包含任务说明、科研材料、必要的输入约束和评分所需的证据范围；案例会以相同内容分别交给基础 Agent 和加载参赛 Skill 的 Agent。你不需要自带正式测试案例，也不需要提交预先写好的答案。

1. 读取事实底稿、受众、文体和格式约束。
2. 完成指定的生成、改写、校对或结构化动作。
3. 为事实、数字和引用保留来源或修改记录。
4. 对材料不足、冲突和需要人工确认的内容明确标注。

参赛者围绕一个真实、高频、具有明确输入和输出的学术语言润色任务，开发能够被 Agent 调用的 Skill，解决现有玻尔科学空间在该任务上的实际问题。  
可选择与语法、术语、学术语气、语义保持和中英文表达质量相关的具体方向。允许聚焦一个具体问题，不要求开发完整的学术语言润色系统。鼓励从基础 Agent 的真实失败案例出发：一段被整段重写后限定词消失的摘要、一篇术语在引言与方法之间来回漂移的稿件、一份中译英后满是直译腔的基金申请书，都可以是起点。  
本课题重点关注四个问题：  
改得对： 语法、句法、搭配、标点与用词错误是否被真正改掉，而不是被换一种说法掩盖。说得像： 改写后的文本是否符合目标文体与语域，术语是否全篇统一，是否仍然像同行写的学术文本。没改坏： 原意、限定强度、数据、单位、引用编号与图表指向是否保持原样，有没有在润色中偷偷加强或削弱结论。讲得清： 每一处修改是否有原文、改文、修改类型与理由，他人能否据此判断这处该不该改。

可选择的突破方向：  
优先考虑以下五个方向，也允许提出其他具有明确学术写作价值的问题。  
语法与句法修正： 处理主谓一致、时态与语态、冠词与介词、单复数、悬垂修饰、标点与长句切分，目标是消除硬错误而不改变句式承载的信息。术语与全篇一致性： 建立并维护术语表，统一同一概念的中英文写法、缩写首次出现形式、大小写与连字符，处理同义混用与跨章节漂移。学术语气与语域： 区分期刊论文、学位论文、基金申请书、审稿回复、英文摘要的不同语气要求，消除口语化、宣传化、绝对化表述与人称误用。语义保持与最小编辑： 在改写的同时守住限定词强度、因果与相关性的区别、否定范围、条件句和量词，避免过度同义替换造成专业含义偏移。中英文表达质量： 处理中式英语、直译腔、冗余名词化、逻辑连接词滥用，以及中译英时主语与信息重心的重新安排。  
参赛者只需要选择一个明确问题，形成能够真实运行、独立验证、持续改进的最小成果。

平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

#### 2. 评分维度概要

总分 **100 分**。综合三个固定案例的实际表现和提交材料评分，各评分项只计一次；本节只展示评分维度、分值和考察内容，不展示内部详细分档。

| 评分维度 | 分值 | 评分点及分值 | 考察内容 |
|-|-|-|-|
| 实际效果 | 40 分 | 任务完成度 15 分；结果正确性 15 分；结果完整性 5 分；结果可核验性 5 分 | 是否按任务口径交付"润色后的完整文本＋逐句修改说明"，而不是一段写作建议或一次整段重写。；改写后的句子是否仍然表达作者的主张：限定强度有没有被加强或削弱、数据与单位有没有被顺手改掉、引用编号与图表指向是否对得上、术语译法是否符合领域惯例。；是否覆盖任务要求的所有处理项：指定章节是否逐段处理、术语表是否建全、缩写与符号的首次出现是否统一、中英双语对照与修改清单是否齐全。；原文—改文对照、修改类型标签与修改理由是否足以让第三方判断"这处该不该改"。 |
| 使用增益 | 25 分 | 质量增益 15 分；效率增益 5 分；增益可验证性 5 分 | 在相同输入、相同术语表与风格规则下，加载 Skill 相比基础 Agent 是否在语法修正、术语一致性、语义保持与语气贴合上稳定更好。；是否减少人工返修条目、往返轮次与逐句核对条目，同时不把成本转移到事后校对。；对照条件是否一致：同一份原文、同一术语表、同一评分人与同一验收标准，必要时是否采用盲评。 |
| 创新增益 | 15 分 | 新增能力 5 分；方法改进 5 分；创新证据 5 分 | 是否形成基础 Agent 不具备或难以稳定实现的能力，例如术语表驱动的全篇一致性回扫、限定强度守恒检查、双语术语对齐、按目标期刊风格整体改写。；方法层面的改进：最小编辑原则、分句级编辑策略、术语表与风格指南注入方式、改后回读或回译校验、改写与审校双通道。；是否证明创新点相对已有方案的边界与价值，比较对象应包括基础 Agent、通用写作工具、翻译工具以及人工润色基线中适用的部分。 |
| 可靠体验 | 10 分 | 调用与易用性 3 分；运行稳定性 4 分；异常处理 3 分 | Agent 是否能准确触发（该润色时触发、纯内容问答时不应擅自改写），以及粘入纯文本、Markdown、LaTeX 片段或章节稿后输出能否直接使用。；长文本、分章节输入、多次重复运行、不同学科术语下能否持续产出可用结果，同一段落重复润色时结论是否漂移。；对超长输入、编码混乱、公式与引用混杂、中英日混排、术语表内部冲突、目标文体不明等情况的识别与处置能力。 |
| 生态贡献 | 10 分 | 文档完整性 3 分；资源可复用性 4 分；分享推广价值 3 分 | SKILL.md、术语表与风格指南格式、输入输出示例、适用范围、限制与维护信息是否齐全。；术语表、风格规则、测试文本、评分表与脚本能否被他人直接用于自己的稿件与学科。；是否沉淀可分享的案例、评测集、术语治理经验与真实应用价值。 |

质量与增益以平台固定案例、基础 Agent/Skill Agent 对照结果和可核验记录为依据；文字自述不能替代实际运行证据。

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
| 目标产物 | 可编辑的稿件、改稿、引用/格式结果或结构化写作产物；完成标准：满足题目指定体裁、受众和格式 |
| 事实与来源映射 | 数字、术语、引用、图表和关键论断的来源/修改记录；完成标准：可逐条回溯，不新增材料外事实 |
| 版本与边界 | 修改差异、人工确认项、材料缺口和异常；完成标准：结果可继续编辑，未确认部分明确标注 |

正式测试案例、白板和测评结果由平台提供或生成，参赛者无须另交三个测试案例、白板或预先生成的正式答案。材料缺失、无法判断和运行失败要分别说明。



## Harbor技术提交约定

# Runtime contract
This is a Skill authoring task. Create /app/submission/SKILL.md and any required text resources. Use valid name/description YAML frontmatter. Do not submit prepared answers or formal test outputs. The evaluator installs the actual Skill under /skills/weekly-skill, then runs official DeepSeek Harness on each fixed original case.

At execution time original input is /input/case.json and task.md. Material and artifacts are provided according to the topic; PDF parsing receives the actual PDF without a pre-extracted answer layer. Read actual files instead of assuming source content from labels. Work under /app/work; final actual results and editable artifacts belong under /app/output, including result.json with all original output_contract fields and case_id. Include honest status, sources, uncertainty and change records. Editable Office/slide/diagram outputs should also have real rendered PDF/PNG previews for inspection. A partial result must identify its limits. Do not fabricate missing software state or scientific data.

Model, source/case versions, runtime, budgets and actual native traces are recorded by the platform; do not invent benchmark scores. Execution budget: 64 model requests, 900 seconds, 16384 tokens per response including reasoning. Save honest partial deliverables early and improve incrementally. Three cases, three repetitions per condition; actual service failures are paused separately. The platform provides/generates any required comparison; participants do not provide hidden tests or whiteboards. Skill resources: at most 50 UTF-8 text files, 500KB each and 2MB total, no symlinks. Runtime artifacts may be binary and are retained independently of final JSON validity.

实际输入文件和原论文是事实依据；不依据错误的领域标签补造数据。


Resource entry point: environment/resources.yaml. Bundled files are relative to that directory; declared preinstalled runtime paths describe the pinned image. The actual fixed scientific cases are supplied by the evaluation platform.


---

题面已公开，正式提交开放时间以赛事通知为准。
