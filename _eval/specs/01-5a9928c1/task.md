### 文献翻译：科研阅读：回答问题，也给出依据

#### 1. 题目介绍

你需要围绕“文献翻译”制作一个可被 Agent 调用的 Skill，在组织方提供的 3 个固定科研案例上完成实际任务，并交付能够被复核的结果。  
读取固定科研材料并完成本题指定的解析、翻译、问答、提取、核验或知识结构化，关键结果回到原文证据。

组织方为本题准备 3 个固定案例。每个案例包含任务说明、科研材料、必要的输入约束和评分所需的证据范围；案例会以相同内容分别交给基础 Agent 和加载参赛 Skill 的 Agent。你不需要自带正式测试案例，也不需要提交预先写好的答案。

1. 先识别输入材料和问题边界。
2. 按题目要求完成阅读或解析动作。
3. 为关键结论保留页码、段落、字段或图表定位。
4. 对未报告、无法判断和材料冲突明确说明。

围绕真实科研论文中的高频翻译难点，开发能够被 Agent 调用的翻译 Skill、插件或轻量工作流，确保术语、段落结构、引用和公式在翻译后仍可核验，重点改善术语一致性、长文分段翻译、双语对照与译文质量核验。  
参赛者可选择术语表驱动翻译、双语段落对照、长文分段续译、译文核验与修改建议等具体方向，允许聚焦一个问题，不要求开发完整的文献翻译系统。鼓励从基础 Agent 在真实文献上的失败案例出发，通过对照与评测证明实际改善。  
本课题重点关注四个问题：  
术语稳： 同一术语在标题、摘要、正文、图注和结论中是否始终使用同一译名，术语表能否被真正执行而不是写在提示里。段落全： 长文跨页、跨栏、跨章节时是否不漏段、不重复、不错位，段号能否与原文一一对应。关系准： 指代对象、否定与限定条件、因果与让步关系、数字单位、公式与文献编号是否与原文一致。可核验： 每段译文能否指回原文并说明译法依据，译不准的部分是否被明确标注而不是含混处理。

可选择的突破方向：  
优先考虑以下五个方向，也允许提出其他具有明确科研价值的文献翻译问题。  
术语一致性： 从原文抽取领域术语建立术语表，全篇锁定同一译名，并验证标题、正文、图注与结论中的译法统一。长文分段翻译： 按语义边界切分长文，携带必要上下文与已确定术语逐段翻译，处理跨页、跨栏和章节衔接，减少漏译与重复翻译。双语对照： 输出原文与译文的段落级对应关系，保留段号与句子边界，支持定位回看、逐段修改与引用核对。译文核验： 检查数字、单位、公式、图表编号、文献引用、否定关系和限定条件是否被准确保留，并给出需要人工确认的清单。结果复核与复用： 优先选择能够回到原文、可重复运行、术语表可持续维护且方便其他用户复用的翻译任务。  
参赛者只需选择一个明确方向，形成能够真实运行、独立验证、持续改进的最小成果。

平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

#### 2. 评分维度概要

原题满分 **100 分**。GitHub 公开作品链接为额外附加分，最高加 **5 分**。综合三个固定案例的实际表现和提交材料评分，各评分项只计一次；本节只展示评分维度、分值和考察内容，不展示内部详细分档。

| 评分维度 | 分值 | 评分点及分值 | 考察内容 |
|-|-|-|-|
| 实际效果 | 40 分 | 任务完成度 15 分；结果正确性 15 分；结果完整性 5 分；结果可核验性 5 分 | 是否真的把一篇（或一个明确段落区间）的真实文献翻译成可用的双语对照结果，而不是只给大意或改写。；术语、指代关系、否定与限定、数字单位、公式与文献编号是否与原文一致，而不是看译文是否通顺。；是否覆盖任务要求的要素：全文段落、图表题注与表头、公式与编号、文献引用标记、术语表条目。；每一段译文能否指回原文的具体段落与句子，并说明译法依据。 |
| 使用增益 | 25 分 | 质量增益 15 分；效率增益 5 分；增益可验证性 5 分 | 同篇文献、同同术语表口径下，加载 Skill 后相比基础 Agent 在术语一致率、长文完整率和事实准确率上的提升。；是否减少分段整理、查术语、对照排版与逐段校对的时间。；是否用公平对照证明“更准、更全、更省时”。 |
| 创新增益 | 15 分 | 新增能力 5 分；方法改进 5 分；创新证据 5 分 | 是否形成基础 Agent 不具备的能力，例如术语表强制约束与全篇回填、跨页段落接续与上下文携带、段落级对齐输出、公式与引用标记保护、译文自检清单。；分段策略、术语抽取与锁定、上下文携带、数字公式回填、译文自检规则是否带来实质改进。；是否证明新增能力相对已有翻译方案的价值边界。 |
| 可靠体验 | 10 分 | 调用与易用性 3 分；运行稳定性 4 分；异常处理 3 分 | Agent 能否正确触发，用户能否按说明完成一次从原文到双语对照的完整翻译。；在不同长度、排版与重复运行下能否稳定产出完整译文。；遇到文字层缺失、扫描件模糊、公式与表格为图片、参考文献无法解析、原文残缺或语言混杂时的处置能力。 |
| 生态贡献 | 10 分 | 文档完整性 3 分；资源可复用性 4 分；分享推广价值 3 分 | 使用说明、依赖、输入要求、术语表格式、段号与对齐约定、未译标注规则、限制与维护信息是否齐全。；Skill 本体、脚本、术语表、分段规则、题集与评分表能否被别人直接用于新学科文献。；是否沉淀可分享的翻译案例、术语资源、核验口径和实践经验。 |

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


Resource entry point: environment/resources.yaml. Bundled files are relative to that directory; declared preinstalled runtime paths describe the pinned image. The actual fixed scientific cases are supplied by the evaluation platform.


---

题面已公开，正式提交开放时间以赛事通知为准。
