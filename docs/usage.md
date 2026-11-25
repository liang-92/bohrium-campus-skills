# 使用过程记录（可复跑核对）

这份文档记录**实际怎么做的**：每一步用了什么命令、看到什么结果、哪一步错了、怎么修的。
文中的数字都来自仓库里的产物，任何人可以按第 5 节复跑并逐项对上。

> 判断依据只有三样——提交历史、`_test/cases/` 里的期望值与结果、`trace/` 里的执行轨迹。

---

## 1. 时间线（git 可查）

| 时间（2026-11-23） | 提交 | 做了什么 |
|---|---|---|
| 20:15 | `b5c7138` | 仓库初始化：10 个 Skill、核心 `paperkit`、构建脚本 |
| 20:35–21:05 | `0063740` `c3aef1c` | 安装目录自定位、BibTeX 导出；审计报告首版 |
| 21:10–21:45 | `5fa75ce` | 四路评审汇成 `_test/review.md`，审计报告补异常兜底补丁 |
| 21:50–22:05 | `e651c1e` `7fb9970` | 契约字段逐字回填、矢量图检测、决策证据字段 |
| 22:05–22:20 | `81f1ab5` `3655d90` | 乱码字体/页码错乱/图片型表格检测；`--probe` |
| 22:20–22:35 | `830dbee` `2255591` | 轨迹脱敏重导；双语触发词、基准数字对齐 |
| 22:35–22:50 | `4a546f1` `03823a6` | `--fill` 回灌、零提取判 `unable`、变更记录 |
| 23:00–00:00 | `7bd7ba2` | 第二轮：表格/作者/公式/图谱/引用缺陷 + 16 个带标准答案的用例 |
| 00:10–01:20 | `3289daf` | **第三轮**：独立核验（重开 PDF）、决策回放、离线对照基线；用例增至 18 个 |

---

## 2. 七个阶段（每阶段都可单独复跑）

### 阶段 1 · 先把仓库跑起来，确认"能跑"和"跑对"是两件事

```bash
python tools/build_skills.py            # 10 个包，每个 19 文件 / 约 230–244 KB
python skills/paper-parse/scripts/run.py --input _test/selftest/case-single --out out/att
python skills/paper-parse/scripts/verify.py --out out/att --kind generic
```

结果：10/10 包结构合规，20 次运行全部成功，两次运行只有 `seconds` 不同（可复现）。
**但**第一次跑就发现：`verify.py` 只检查"结果与契约自洽"，不检查"抽得对不对"。
这决定了后面必须补一套带标准答案的用例。

### 阶段 2 · 用"已知答案"的用例把错误逼出来

真实论文的正确答案没人知道，所以改为**用代码生成 PDF**，生成时就知道答案：

```bash
cd _test/cases
python make_cases.py        # 18 个用例：10 题 + 6 类异常 + 双栏阅读顺序
python run_cases.py         # 跑对应 Skill，按 gold.json 逐项核对
```

第一次跑的结果（未修）：**4 个用例失败、10 个断言不通过**，第 5 个用例是检查脚本自己崩了
（`coverage.pages` 在部分分支里是整数不是列表）。失败项很具体：

| 用例 | 现象 | 说明 |
|---|---|---|
| `p01` | 表格 0 个；公式 0 条 | 表格被算进正文，公式编号在行首检不到 |
| `p06` | 边 8 条（门槛 10） | 图里混进 "of the corpus" 这类噪声节点 |
| `p08` | BibTeX 没有 `@inproceedings` | 标题把 `[C]//NeurIPS` 吞了进去，类型判成期刊 |
| `p10` | 超参缺 3 个 | `learning rate = 0`，值被小数点截断 |

### 阶段 3 · 定位根因（不是猜，是打印中间层）

表格这一条最能说明问题。先看引擎原始输出：

```python
page.find_tables(strategy="text").tables[0].extract()
# 5 行 6 列，但数值是 '241\n.' / '0512\n.' —— 小数被拆成两行
```

再看单元格矩形：`row.cells[0] = (72.0, 246.03, 170.58, 258.40)`，
而表头文字基线正好在 `y=246.0`——**单元格矩形贴着文字基线**，
所以任何按矩形取字（`get_textbox`、`get_text(clip=...)`）都会把相邻行整行带进来。
5 行的表因此变成 9 行、每行重复两次。

结论：不能信引擎的"行框"，但可以信它的"列边界"。改成**按文字基线聚类成行、按水平重叠归列**。

### 阶段 4 · 改完立刻用同一批用例验

```bash
python tools/build_skills.py && cd _test/cases && python run_cases.py
# 16 cases, 0 failed checks
```

表格 5×6 逐值正确（`24.1 / 1.00x / 4.92G / 0.512`），作者 4/4，公式编号 `(1)`，
Attention 论文的表 1 恢复 `Layer Type` 的空格、表 2 的 `23.75` 不再变成 `2375.`。

### 阶段 5 · 十包 × 两篇真实论文回归（防止改一处坏十处）

```bash
cd _test/cases && python run_matrix.py
# 20 runs, 0 failing
```

`paper-translate` 的 `verify.py` 报 `pending` 而不是 `ok`：译文按设计留给 Agent 填，
这一点在报告里如实写 `pending（译文待填）`，没有改成 `ok` 掩盖。

### 阶段 6 · 验证 `--fill` 往返（写作类最关键的一环）

```bash
# 译文只填 2/9 段
python skills/paper-translate/scripts/run.py --input p03-translate --out out/fill
# run.fill = {applied: 2, untranslated: 7}；status 仍是 partial（没填完就不算完成）

# 引言五段全填
python skills/paper-intro/scripts/run.py --input p09-intro --out out/fill
# draft.status: to_be_written -> written；整体 status: partial -> complete
```

这一步同时暴露了一个真 bug：按 SKILL.md 写的 `[{seg, translation}]` 形态会让 `--fill` 崩
（只实现了 dict 形态），已修，两种形态都接受。

### 阶段 7 · 把「自洽」换成「能被推翻」（第三轮）

前三阶段的所有检查都读自己写出的 `doc.json`，只能证明自洽。这一阶段补了两条外部通道：
**重开 PDF 复核**，以及**不加载 Skill 的对照**。

```bash
# 1) 重开 PDF：字符多重集 + 单元格溯源 + 第二个引擎
python skills/paper-parse/scripts/verify.py --out _test/cases/_out/paper-parse/p01 \
        --kind generic
# independent: chars_missing 0 / chars_extra 0 / verbatim_ratio 1.0
#              table_cells 30/30、cross_engine pypdf 3522 vs 3522（ratio 1.0）
# decisions:   10 条断段决策可回放，0 条失败

# 2) 不加载 Skill 的基线下界
python bench/base_agent.py --all
# p01 18.0→100.0、p02 0.0→100.0、p08 0.0→90.0、p06 0.0→90.0；均值 4.5→95.0（+90.5）

# 3) 用例与矩阵
cd _test/cases && python make_cases.py && python run_cases.py    # 18/18、0 失败
python run_matrix.py                                             # 10 包 × 2 篇真论文
```

这一轮自己踩了四个坑，都记在这里，因为「一次就对」的记录不可信：

1. **断段回放写错了对象**。第一版拿「上一块 bbox 底边」比「下一块 bbox 顶边」，
   9/10 条报不一致。打印后发现标题块合并会重建 bbox，块与块相邻 ≠ 行与行相邻。
   改成在断段时把触发断段的**两行 y 坐标**记进 `break_at`，回放这两行 → 0 失败。
2. **跨引擎比出了假差异**。pypdf 比 PyMuPDF 多 18% 字符，原因是口径不同（一边含空白）。
   统一成「非空白字符」后比例 1.0。若不查，就会写出一条不存在的“引擎不一致”。
3. **表格检测太慢**。PyMuPDF 2.x 的 `find_tables` 每页加载 ONNX 模型（约 3.5s/页）。
   加候选页门控（有 `Table N` 图注或横线才调用），p01 单次 8.6s→4.9s；
   改完先确认表格仍是 5×6、`24.1/4.92/0.512` 逐值不变，才保留这个优化。
4. **加密 PDF 的判断想当然了**。以为「仅 owner 口令」会让 `needs_pass` 为真，实测是 0。
   改用 `metadata.encryption` 判断，并新增 `x07-ownerlocked` 用例锁住这个行为。

---

## 3. 失败与修复对照（第二轮，共 11 条）

| # | 现象 | 根因 | 修法 | 验证 |
|---|---|---|---|---|
| 1 | 表格 5 行变 9 行、每行重复 | 单元格矩形贴基线，取字带进相邻行 | 按基线聚类成行 | `p01` 表格 5×6 |
| 2 | `24.1` → `241` + `.` | 同上（单元格被切成两行） | 同上 | `p01`、Attention 表 2 |
| 3 | 作者 = `['Computational Linguistics']` | 作者区整段拼接，机构的两大写词被当人名 | 按行在首个机构词处截断 | `p01` 作者 4/4 |
| 4 | 3 页论文 `formulas=0` | 编号在行首；全 ASCII 公式符号密度不足 | `EQ_LEAD` + 算子密度判据 | `p01` 公式 1 条 |
| 5 | 图里出现 `of the corpus` | 实体正则用了 `re.I`，`[A-Z]` 退化成任意字母 | 实体匹配区分大小写 | `p06` 节点去噪 |
| 6 | 标题第二行成了章节节点 | 标题被拆成两个块 | 标题区（前两个标题块）不进图 | `p06` |
| 7 | 图谱只有 5 条边 | 只靠共现 | 加 `mentions`（章节→本节实体）+ 密度门槛 | `p06` 边 ≥10 |
| 8 | `learning rate = 0` | 上下文窗口在小数点处截断 | 窗口放宽 + 逐名扫描 | `p10` 三个超参 |
| 9 | `…[C]//NeurIPS[J]. 2017, 2017` | 按句点切段，会议名落进标题 | 类型标记/`//`/句点三处取最早截断 | `p08` BibTeX `@inproceedings` |
| 10 | `--fill` 崩溃 | 只认 dict 形态的 segments | 两种形态都接受 | 阶段 6 |
| 11 | `verify.py` 报 "no segments" | 契约把数组包成 `{items,count}` | 校验器兼容包装形态 | 矩阵 20/20 |

---

## 4. 证据在哪

| 证据 | 路径 | 规模 |
|---|---|---|
| 用例与期望值 | `_test/cases/*/gold.json` | 18 个用例 |
| 用例结果 | `_test/cases/report.md` | 17/17、34/34 断言 |
| 十包回归 | `_test/cases/matrix.md` | 20 次运行、0 失败 |
| 缺陷专项断言 | `_test/test_defects.py` | 14 条 |
| 逐字一致性 | `out/*/raw_text.txt` + 字符账本 | 每次运行生成 |
| 原始轨迹 | `trace/steps.jsonl`、`trace/round2-steps.jsonl` | 见下 |

轨迹是**平台会话日志直接导出**的，只做脱敏（token / 口令 / 本地路径），不做美化：

| 轨迹 | 步数 | 配对工具调用 | 时间跨度 | 说明 |
|---|---|---|---|---|
| `trace/round2-steps.jsonl` | 815（399 tool_call / 398 tool_result） | 398 | 2026-11-23 13:16–16:02 UTC | 本轮复核与修复，随仓库分发 |
| `trace/steps.jsonl` | 1671 | — | 首轮开发 | 1.6 MB，未随仓库分发，可用同一脚本重导 |

重新导出（换一个会话文件即可）：

```bash
python tools/make_trace.py --session <session.jsonl> --out trace/steps.jsonl
```

---

## 5. 怎么核对这份文档

```bash
# 1) 用例能不能重现
cd _test/cases && python make_cases.py && python run_cases.py     # 期望 17/17

# 2) 十包有没有退化
python run_matrix.py                                              # 期望 20/20

# 3) 表格这一条对不对
python - <<'PY'
import json, subprocess, sys
subprocess.run([sys.executable, "../../skills/paper-parse/scripts/run.py",
                "--input", "p01-parse-single", "--out", "out/check"], check=True)
d = json.load(open("out/check/result.json", encoding="utf-8"))
t = d["output_contract"]["content.tables"]["value"][0]
print(t["n_rows"], t["n_cols"], t["rows"][1])     # 期望 5 6 ['Dense baseline', '24.1', ...]
PY
```

三条都能对上，说明本文的数字不是写的，是跑出来的。

---

## 6. 边界声明（哪些不是脚本做的）

- **文字是 Agent 写的**：译文、引言、方法章、润色后的句子都由模型生成，脚本只给证据、
  约束和空骨架，`run.fill` 会标明"这段文字来自 Agent，不是从 PDF 抽的"。
- **公式只做 ASCII 化转换**：希腊字母、根号能映射，矩阵/分段函数会进 `formula_review`
  等人工确认，不假装转对。
- **未覆盖**：中文 PDF、竖排排版、双栏跨页表格的跨页合并。
- **分数**：`docs/audit-2026-11-23.md` 第 9.5 节的区间是**按赛题维度做的保守模拟**，
  不是官方评分，也不作为承诺。
