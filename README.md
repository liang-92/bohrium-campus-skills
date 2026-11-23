# Bohrium Campus Skills · 论文阅读与写作的十个小工具

面向「玻尔校园挑战赛 · 北京化工大学站」第一期十道赛题的 Skill 包集合。
十道题共用一个确定性内核 **paperkit**：先把 PDF 还原成带页码与块号的结构，
再按题型组装成可复核的结果。所有结论都能回到 `p07-b012` 这样的锚点。

> 这些 Skill 是给 **Agent** 用的：`SKILL.md` 说明何时触发、怎么调、输出什么、
> 失败怎么办；`scripts/` 里是真正干活、可离线运行的代码。

## 这套东西解决什么问题

普通「把 PDF 丢给模型」的做法有四个稳定失败点：

| 失败点 | 后果 | 这里的做法 |
|---|---|---|
| 双栏被按 y 坐标读成一行 | 句子跨栏拼接，语义错乱 | XY-cut 递归分区：只接受能把区域**完整二分**的缝隙 |
| 页眉页脚/arXiv 边条混进正文 | 每页多出无关句子 | 位置 + 跨页重复模式 + 旋转文本 + stamp 四类规则剔除 |
| 表格被拍平成一段话 | 参数与结果无法比对 | 引擎表格识别 + 行间隙兜底，输出 Markdown/行列结构 |
| 「看起来像全文」但没有出处 | 评审无法核验 | 每个块有稳定 id、页码、栏号、bbox、章节路径 |

## 十个 Skill

| # | Skill | 对应赛题 | 核心产物 |
|---|---|---|---|
| 1 | [`paper-parse`](skills/paper-parse/SKILL.md) | 阅读01 文献文档解析 | 章节树 + 全量块 + 表格/公式/图/参考文献 |
| 2 | [`paper-translate`](skills/paper-translate/SKILL.md) | 阅读03 文献翻译 | 段落级双语对照 + 锁定术语表 + 译后核验 |
| 3 | [`paper-notes`](skills/paper-notes/SKILL.md) | 阅读10 文献总结与结构化笔记 | 论文卡片 + 分节笔记 + 知识点 |
| 4 | [`paper-nanopub`](skills/paper-nanopub/SKILL.md) | 阅读14 Nanopublication | 原子断言 + 最小证据 + provenance |
| 5 | [`paper-kg`](skills/paper-kg/SKILL.md) | 阅读15 文献知识图谱构建 | 实体/关系图 + 别名组 + 查询 |
| 6 | [`paper-polish`](skills/paper-polish/SKILL.md) | 写作02 学术语言润色 | 句级体检 + 术语一致性 + 改写记录规范 |
| 7 | [`paper-refs`](skills/paper-refs/SKILL.md) | 写作04 参考文献与引用管理 | 引用-条目一致性 + 去重 + GB/T 7714 / APA |
| 8 | [`paper-intro`](skills/paper-intro/SKILL.md) | 写作08 引言与相关工作写作 | 问题/空白/贡献证据链 + 引用覆盖 |
| 9 | [`paper-methods`](skills/paper-methods/SKILL.md) | 写作09 方法与实验章节写作 | 参数表 + 数据集 + 可复现清单 |
| 10 | [`paper-latex`](skills/paper-latex/SKILL.md) | 写作13 LaTeX 写作与编译 | 可编译 `.tex` 工程 + 真实编译结果 |

## 快速开始

```bash
# 单个 Skill，跑一个案例目录
python3 skills/paper-parse/scripts/run.py --input ./case --out ./out
ls ./out        # doc.json doc.md coverage.json result.json payload.json raw_text.txt run.log

# 自检
python3 skills/paper-parse/scripts/verify.py --out ./out --kind generic
```

`case` 目录的约定与平台一致：`case.json`、`task.md`、`*.pdf`，可选其他材料
（docx / tex / bib / csv / json / md）。

平台运行时通常直接：

```bash
python3 scripts/run.py --input /input --out /app/output
```

## 契约怎么填（`result.json`）

平台会用 `case.json` 里 `output_contract` 声明的字段逐个核对，所以这里只有一条硬规则：
**字段名逐字照抄，不改名、不增删**。

| 情形 | 落地方式 |
|---|---|
| 组装器切片里已有同名键 | 原值输出，`field_status.<字段>.method = "exact"` |
| 字段名是普通文献名词（`equations` / `citations` / `full_text_blocks`） | 路由到对应切片，`method = "alias:formulas"`，**用了哪条规则写在结果里** |
| 字段是任务型输出（`answers` / `summary`） | 用本题型自己的发现兜底，`method = "fallback:…"`，置信度 0.5 |
| 本题型确实产不出 | 保留原 key，输出 `{"value": <按声明类型的空值>, "method": "unsupported", "confidence": 0}`，并写进 `uncertainty.missing` |

类型由契约自己决定：`list` → 数组，`title/authors/abstract` → 对象，
`complete|partial|unable` → 三选一。契约没声明的切片不进 `output_contract`，
另存 `payload.json`——否则多出来的键会被读成「把答案改了名」。

字段值是空的（`[]` / `{}` / `""`）时，`field_status` 会多一个 `"empty": true`：
空列表可能是**真的没有**（这篇论文就没有公式），也可能是**没读到**（PDF 没文本层）。
两者的区别放在 `confidence` 上——文档解析成功时空值保留路由置信度（0.90/0.95），
一个都没解析出来时降到 `0` 并写 `"why_empty": "no document was parsed from the input"`。
另外，形状齐全但内容全空的 `{"title": "", "authors": []}` 也算空：那些键是占位符，不是发现。

## 目录结构

```
core/paperkit/        内核：PDF 后端、版面、结构、证据、结果
core/compose_all.py   十种题型的组装器（纯规则，无网络）
core/run.py           入口脚本（每个 Skill 里都有一份）
tools/build_skills.py 从 core 生成十个独立 Skill 包
skills/<slug>/        提交物：SKILL.md + scripts + environment + examples
bench/run_bench.py    本地回归基准（可复现、可确定性校验）
bench/baseline_compare.py  朴素抽取 vs paperkit 的量化对照
docs/                 方法与基准说明
```

每个 `skills/<slug>/` 都是**自包含**的：平台只安装提交目录，所以 `scripts/pk/`
是内核的副本，不依赖仓库其他部分。

## 本地基准

三篇公开论文，默认参数，`python3 bench/run_bench.py` 可复现：

| 文件 | 页 | 块 | 章节 | 表(带题注) | 图 | 公式 | 参考文献 | 分栏倒挂 | 耗时 |
|---|---|---|---|---|---|---|---|---|---|
| 1706.03762 (Attention) | 15 | 268 | 27 | 4 (4) | 2 | 14 | 41 | 7 | 30.8s |
| 1810.04805 (BERT) | 16 | 800 | 28 | 6 (6) | 5 | 8 | 58 | 52 | 30.0s |
| acl2020 (双栏 ACL) | 6 | 174 | 17 | 3 (3) | 2 | 1 | 23 | 6 | 9.4s |

耗时随 PyMuPDF 2.x 的 ONNX 表格模型波动（同机 25–40s/篇），只作量级参考，不是评分项。

「分栏倒挂」按**同页同栏**统计（后一块的顶边低于前一块，容差 5pt），表格区域整块跳过——
表格本来就该逐列读。这个数字不是 0，它反映的是真实残留：作者信息栏、图内文字、
公式编号等不是线性排版的区域。**页码回退**是同名的粗指标，任何正常抽取都是 0，
所以单列出来只作护栏，不当成绩。两次运行输出指纹一致，说明结果确定。
完整表格与逐项解释见 [`docs/benchmark.md`](docs/benchmark.md)。

「图」同时包含位图与**矢量图表**：学术 PDF 里的流程图/柱状图大多是矢量路径，
不在图片列表里，只认图片会得到 0 张（BERT 的 5 张全是矢量图）。

## 和「朴素抽取」的对照

同一份 PDF、同一个抽取引擎，只换版面逻辑，跑 `python3 bench/baseline_compare.py` 可复现：

| 文件 | 双栏页 | 串栏拼接（朴素→paperkit） | 断词残留 | 竖排边条残段 |
|---|---|---|---|---|
| 1706.03762 (单栏) | 2 | 29 → **0** | 16 → 0 | 13 → 0 |
| 1810.04805 (BERT) | 16 | 672 → **0** | 330 → 4 | 2 → 0 |
| acl2020 (ACL) | 5 | 213 → **0** | 113 → 0 | 0 → 0 |

「串栏拼接」是几何真值：同一 y 高度上左右两栏各有一行，按 y 排序必然焊成一句。
「竖排边条残段」是 arXiv 左侧 90° 旋转的提交戳被切成的碎片。

同一脚本还会算**对齐评分口径**的五项（逐字一致率 / 多出字符 / 分栏倒挂 /
表格单元格可回查 / 契约字段回填），当前结果：

| 文件 | 逐字一致率 | 多出字符 | 表格单元格可回查 | 契约回填（10 字段探针） |
|---|---|---|---|---|
| 1706.03762 | 98.11% | 0 | 136/140（97%） | 10/10 |
| 1810.04805 | 99.04% | 0 | 142/166（86%） | 10/10 |
| acl2020 | 99.46% | 0 | 74/81（91%） | 10/10 |

「表格单元格可回查」按「每个词都能在该页文字层找到」判定：`docs/baseline.md` 在表格区域内
的块里查（136/140），`verify.py` 在整页文字层里查（139/140）。合并单元格（`BLEU EN-DE EN-FR`
这种跨列拼接）整串不会连续出现，整串匹配的严格值另记为 `verbatim_rate`。

差额可由两项完全解释：行末连字符合并、`ﬁ/ﬂ` 连字展开；原始文字层另存
`raw_text.txt`，可与 PDF 文字层逐字节 diff。口径、复现命令与局限见
[`docs/baseline.md`](docs/baseline.md)。

**这一段对照的是「朴素抽取」，不是「不加载 Skill 的 Agent」。** 后者另有一个离线下界代理：
`bench/base_agent.py` 只给引擎的 `page.get_text("text")` 纯文本转储，skill 跑同一个 case，
两者用**同一个打分器**、同一份 `gold.json`：

| case | base（纯文本转储） | skill | delta |
|---|---|---|---|
| `p01-parse-single`（单栏，表/公式/引用） | 18.0 | 100.0 | +82.0 |
| `p02-parse-twocol`（右栏先写入内容流） | 0.0 | 100.0 | +100.0 |
| `p08-refs`（条目/缺失/未引用/重复） | 0.0 | 90.0 | +90.0 |
| `p06-kg`（实体与关系图） | 0.0 | 90.0 | +90.0 |
| 均值 | 4.5 | 95.0 | +90.5 |

结果是 `bench/base_vs_skill.json`，**离线对照、不是平台成绩**。纯文本转储是多模态模型的
下界（模型能看图、能自己读表），真实 delta 只会更小；真正的模型对照仍需评测方执行，
协议写在 `docs/method.md` 与各 `SKILL.md` 的「对照协议」一节。

## 设计原则

1. **确定性优先**：能用规则解决的（版面、编号、字段一致性）不交给模型，
   模型只做判断类工作（翻译、改写、措辞）。这样同一案例跑三次结果一致。
2. **证据先行**：任何结论必须带 `block/page/quote`；读不出来就写 `uncertainty`，
   不用「合理猜测」补齐。
3. **失败要可见**：引擎缺失、OCR 未启用、表格识别为空、编译未尝试，都写进结果，
   而不是静默降级。四种会「看起来成功、其实是错」的输入也单独标记在 `coverage.json`：

   | 输入 | 标记 |
   |---|---|
   | 加密 PDF | `status=unable` + 原因；不崩、不假装读到 |
   | 无文字层扫描件 | OCR 补齐；没装 OCR 引擎则写 `ocr_failed`，`status=unable` |
   | 乱码字体（私用区码点） | `garbled_text_layer.pages`，并对这几页改走 OCR |
   | 页码错乱 / 表格是图片 | `page_order.warning` / `image_tables[]` |
   | 路径挂了但目录不存在 / 目录里没有 PDF | `input.problem` 写 `missing_input` / `no_pdf`，`status=unable` |

   `partial` 的判据是**真拿到了一部分**（有块、有表或有参考文献）。一个字都没
   抽出来时是 `unable`——零提取还报 `partial`，等于宣称「读到了一半」。
4. **无网络**：评审环境可能断网，全部依赖本地库；OCR 仅在系统已有 `tesseract` 时启用。

## 适用边界

- 只处理学术 PDF（论文、预印本、技术报告）；海报、竖排、手写不在范围。
- 图表只做**结构识别**（位置、题注、表格行列），不解释科学含义。
- 参考文献不联网核验真实性，只做结构一致性与格式。
- 翻译/润色/写作类：脚本给分段、术语表、问题清单，文字由 Agent 写。

## 自测与改进

提交前的实测记录（2 篇真实论文、40 次运行、5 类异常输入）与逐题提分清单见
[`docs/audit-2026-11-23.md`](docs/audit-2026-11-23.md)；本地自建用例（单栏/双栏/
损坏 PDF/引擎降级对照）见 [`docs/selftest.md`](docs/selftest.md)：包含各题模拟评分、共性硬伤
（异常兜底、表格行重建、公式 LaTeX 化、引擎降级可见化）与复现命令。

## 许可

MIT，见 [LICENSE](LICENSE)。第三方论文仅用于本地测试，不随仓库分发。
