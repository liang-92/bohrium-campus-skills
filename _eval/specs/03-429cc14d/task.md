### 参考文献与引用管理：学术写作：完成产物，也保留来源

#### 1. 题目介绍

你需要围绕“参考文献与引用管理”制作一个可被 Agent 调用的 Skill，在组织方提供的 3 个固定科研案例上完成实际任务，并交付能够被复核的结果。  
依据固定科研材料完成指定的学术写作、修改、格式、引用、双语或结构化写作产物，保持事实和来源一致。

组织方为本题准备 3 个固定案例。每个案例包含任务说明、科研材料、必要的输入约束和评分所需的证据范围；案例会以相同内容分别交给基础 Agent 和加载参赛 Skill 的 Agent。你不需要自带正式测试案例，也不需要提交预先写好的答案。

1. 读取事实底稿、受众、文体和格式约束。
2. 完成指定的生成、改写、校对或结构化动作。
3. 为事实、数字和引用保留来源或修改记录。
4. 对材料不足、冲突和需要人工确认的内容明确标注。

围绕真实、高频、输入输出明确的参考文献与引用管理任务，开发能够被 Agent 调用的 Skill、插件或轻量工作流，重点改善引用插入位置、编号更新、文献去重、格式转换、来源核验与正文—参考文献一致性。参赛者可以聚焦一个具体问题，不要求开发完整的参考文献与引用管理系统。  
鼓励从基础 Agent 和玻尔科学空间等现有工具的真实失败案例出发，用同一份稿件、同一个文献库做前后对照并给出结论。  
本课题重点关注四个问题：  
挂得对： 引用是否插到了真正需要来源支撑的那句话、那个位置，而不是整段末尾或图表注附近。编得顺： 插入、删除、调序之后，正文编号与文末列表能否同步更新，编号连续、交叉引用与上标样式一致。收得净： 同一篇文献以中英文题名、预印本与正式版、不同数据库导出等形式重复出现时，能否合并成一条并说明合并依据。对得上： 每条引用是否真实存在、元数据准确，正文论断与所引文献的主题和结论是否真的匹配，能否逐句说清。

可选择的突破方向：  
优先考虑以下五个方向，也允许提出其他具有明确学术写作价值的引用管理问题。  
引用插入与定位： 识别稿件中需要来源支撑的论断句，选择合适的引用位置与引用形式（顺序编码制、著者—出版年制、脚注），并处理一句多引、多句一引的情况。编号更新与交叉引用： 在插入、删除、调序、合并章节后重排编号，同步正文标记、文末列表序号、图表注与附录引用，保持编号连续、样式统一。文献去重与条目归并： 处理同一文献的中英文题名、预印本与正式版、期刊与会议版本、不同数据库导出字段差异，给出可解释的合并判据，避免误合并同名作者的不同文献。格式转换与字段补齐： 在 BibTeX、RIS、EndNote、CNKI 导出与目标规范（例如 GB/T 7714—2015、指定 APA 版本）之间转换，保留 DOI、卷期页、文献类型标识等关键字段，处理中英文混排与标点差异。来源核验与一致性检查： 通过 DOI、数据库检索或原文比对核验条目真实性，检出编造条目与元数据错配，逐句判定正文论断与所引文献是否对应，并标记证据不足的句子。  
参赛者只需要选择一个明确问题，形成能够真实运行、独立验证、持续改进的最小成果。

平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

#### 2. 评分维度概要

总分 **100 分**。综合三个固定案例的实际表现和提交材料评分，各评分项只计一次；本节只展示评分维度、分值和考察内容，不展示内部详细分档。

| 评分维度 | 分值 | 评分点及分值 | 考察内容 |
|-|-|-|-|
| 实际效果 | 40 分 | 任务完成度 15 分；结果正确性 15 分；结果完整性 5 分；结果可核验性 5 分 | 是否从一份真实稿件和一份真实文献库出发，完成引用插入、编号更新、文献去重、格式转换与来源核验，并交付可继续编辑的稿件和同步的文献表。；每条引用是否落到真实、可定位的文献记录上，元数据是否准确，正文论断与所引文献是否真的匹配。；是否覆盖任务要求的六类动作以及全部章节、全部引用点与全部文献条目。；能否从成品回溯到原始稿件、文献库快照、每条引用的匹配依据和每一步改动。 |
| 使用增益 | 25 分 | 质量增益 15 分；效率增益 5 分；增益可验证性 5 分 | 在相同稿件、相同文献库、相同目标规范下，加载 Skill、插件或工作流后，相比不加载的基础 Agent 是否提升引用管理质量。；完成同等引用整理所需的人工修改量、逐条核对量、返工轮次和综合资源成本是否下降。；是否通过公平对照证明质量或效率改善。 |
| 创新增益 | 15 分 | 新增能力 5 分；方法改进 5 分；创新证据 5 分 | 是否形成基础 Agent 或现有文献管理工具不具备、或难以稳定实现的能力，例如编号连锁更新、正文与列表双向同步、论断级引用匹配、去重决策可解释。；条目匹配策略、去重判据、编号重排算法、格式映射规则是否带来实质改进。；是否证明创新点相对已有方案（基础 Agent、通用文献管理工具）的边界和价值。 |
| 可靠体验 | 10 分 | 调用与易用性 3 分；运行稳定性 4 分；异常处理 3 分 | Agent 是否能正确触发和调用，用户是否能按说明完成一次从稿件到成品的引用整理。；在不同篇幅、不同文献库来源和重复运行下能否持续产出编号一致、条目完整的成品。；对文献库字段缺失、DOI 解析失败、条目歧义、编号冲突、稿件格式不支持、文件损坏等情况的识别与处置能力。 |
| 生态贡献 | 10 分 | 文档完整性 3 分；资源可复用性 4 分；分享推广价值 3 分 | 使用说明、依赖、配置、示例、支持的目标规范、适用范围、限制和维护信息是否齐全。；Skill 本体、脚本、去重规则、格式映射表、测试题集等资源能否被他人复用。；是否沉淀可分享的案例、失败模式和实践经验。 |

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
