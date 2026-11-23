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
ls ./out        # doc.json doc.md coverage.json result.json run.log

# 自检
python3 skills/paper-parse/scripts/verify.py --out ./out --kind generic
```

`case` 目录的约定与平台一致：`case.json`、`task.md`、`*.pdf`，可选其他材料
（docx / tex / bib / csv / json / md）。

平台运行时通常直接：

```bash
python3 scripts/run.py --input /input --out /app/output
```

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

| 文件 | 页 | 块 | 章节 | 表(带题注) | 公式 | 参考文献 | 阅读顺序倒挂 | 耗时 |
|---|---|---|---|---|---|---|---|---|
| 1706.03762 (Attention) | 15 | 268 | 27 | 4 (4) | 7 | 41 | 0 | 10.3s |
| 1810.04805 (BERT) | 16 | 799 | 27 | 6 (6) | 1 | 58 | 0 | 11.2s |
| acl2020 (双栏 ACL) | 6 | 174 | 17 | 3 (3) | 0 | 23 | 0 | 4.6s |

「阅读顺序倒挂 = 0」指没有任何块的页码相对前一块回退；两次运行输出指纹一致，
说明结果确定。完整表格见 [`docs/benchmark.md`](docs/benchmark.md)。

## 和「朴素抽取」的对照

同一份 PDF、同一个抽取引擎，只换版面逻辑，跑 `python3 bench/baseline_compare.py` 可复现：

| 文件 | 双栏页 | 串栏拼接（朴素→paperkit） | 断词残留 | 竖排边条残段 |
|---|---|---|---|---|
| 1706.03762 (单栏) | 2 | 29 → **0** | 16 → 0 | 13 → 0 |
| 1810.04805 (BERT) | 16 | 672 → **0** | 330 → 4 | 2 → 0 |
| acl2020 (ACL) | 5 | 213 → **0** | 113 → 0 | 0 → 0 |

「串栏拼接」是几何真值：同一 y 高度上左右两栏各有一行，按 y 排序必然焊成一句。
「竖排边条残段」是 arXiv 左侧 90° 旋转的提交戳被切成的碎片。
口径、复现命令与局限见 [`docs/baseline.md`](docs/baseline.md)。

## 设计原则

1. **确定性优先**：能用规则解决的（版面、编号、字段一致性）不交给模型，
   模型只做判断类工作（翻译、改写、措辞）。这样同一案例跑三次结果一致。
2. **证据先行**：任何结论必须带 `block/page/quote`；读不出来就写 `uncertainty`，
   不用「合理猜测」补齐。
3. **失败要可见**：引擎缺失、OCR 未启用、表格识别为空、编译未尝试，都写进结果，
   而不是静默降级。
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
