# 十题 Skill 自建测试集评测报告

> 评测对象：`skills/` 下 10 个 Skill 的**当前快照**（`_eval/pinned/skills`，sha256 前 16 位 `1533c85969917200`）
> 测试集：本题自建 12 例（`_eval/cases/`），由 `_eval/make_cases.py` 从零生成
> 评测时间：2026-11-24 22:00–22:55 · 环境：Windows / Python 3.13.12 / PyMuPDF 2.1 + pdfplumber 0.11.11 / 无 Tesseract
> 结论只对本快照成立。评测期间仓库仍在被修改（`core/` 文件 22:34–22:38 仍在变动），因此先固定副本再跑，所有数字都可按 §9 复现。
>
> **更新（2026-11-25 01:10）**：§1–§9 描述的是 `1533c85969917200` 那一版；此后 `pk/deliver.py` 等文件被改写，
> 同一套用例复测得均值 38.8/40、60/61 通过。**看当前状态请直接跳到 §10**，§1–§9 保留为修复前的记录。

---

## 1. 一句话结论

**输入通道这次是通的**——12 个用例没有一例报 `no_pdf`（9 例走文本通道、3 例走 PDF），比上一轮 46/50 报「没有 PDF」是实质改进。唯一的 `unable` 是扫描件本身没有文字层且本机无 OCR，属于如实报告。剩下的问题集中在**交付质量**：60 个检查项只过 35 个，最刺眼的是「文件交上来了，但内容是原文副本 / 占位符 / 空壳，状态却写 `success`」。

---

## 2. 这份测试集是怎么来的（独立性）

| 项目 | 做法 |
|---|---|
| 用例来源 | 全部现写，未复用桌面上那份 50 例的任何材料 |
| PDF 用例（A/K/L） | 用 `make_cases.py` 现场排版：双栏 + 行内 `Abstract` + 三行表头 + 跨页续表 + 纯图像扫描页 |
| 标准答案 | 在生成 PDF **之前**写定（章节 9 个、表 3×3、文献 3 条、公式 1 个、跨页表 24 行），评分逐项比对 |
| 文本用例（B–J） | 每例 1 份材料 + 1 份任务书，覆盖翻译/笔记/nanopub/知识图谱/润色/引用/引言/方法/LaTeX |
| 契约形状 | 6 例扁平（`output_contract: {字段: 类型}`），6 例嵌套（`result_json.required_fields` + `required_files`） |

两组条件各跑一遍，用来分离「没被告知」和「被告知了也不做」：

- **条件一（原样）**：6 例扁平契约，交付文件只在 `task.md` 里点名。
- **条件二（最优）**：强制给全部 12 例加上 `required_files`，每个 Skill 都拿到最明确的条件。

---

## 3. 评分口径（先说清哪一半没测）

官方 100 分里，**只有 50 分能本地机检**，其余 50 分需要平台的基础 Agent 对照或人工评审：

| 维度 | 分值 | 本报告 |
|---|--:|---|
| 实际效果 | 40 | ✅ 机检：完成度 15 + 正确性 15 + 完整性 5 + 可核验 5 |
| 可靠体验 | 10 | ✅ 机检：可调用 3 + 重复一致 4 + 异常诚实 3 |
| 使用增益 | 25 | ❌ **不测**。定义是与「不加载 Skill 的 Agent」同条件对照，本地没有这条基线，编一个数就是伪造证据 |
| 创新增益 | 15 | ❌ 不打分，只列观察（见 §5） |
| 生态贡献 | 10 | ❌ 不打分，只列观察（见 §5） |

表中「折算百分制」= 机检合计 × 2，**只用于横向排序，不等于官方得分**，尤其单例主题（n=1）波动极大。

正确性 = 该例全部检查项的加权通过率；证据可核验性要求 anchor 能落到真实 block/page，或 quote 能在原文中找到。

---

## 4. 结果总表（条件二：最优条件）

| 用例 | 技能 | 主题 | 完成15 | 正确15 | 完整5 | 可核5 | 效果40 | 可靠10 | status 原样/最优 |
|---|---|---|--:|--:|--:|--:|--:|--:|---|
| A_R01_parse | paper-parse | R01 | 15.0 | 14.2 | 5.0 | 5.0 | **39.2** | 10 | partial / success |
| B_R03_translate | paper-translate | R03 | 11.8 | 8.0 | 5.0 | 5.0 | 29.8 | 10 | partial / partial |
| C_R10_notes | paper-notes | R10 | 15.0 | 15.0 | 5.0 | 5.0 | **40.0** | 10 | partial / partial |
| D_R14_nanopub | paper-nanopub | R14 | 15.0 | 12.0 | 5.0 | 5.0 | 37.0 | 10 | partial / partial |
| E_R15_kg | paper-kg | R15 | 6.1 | 2.3 | 5.0 | 5.0 | 18.4 | 10 | partial / partial |
| F_W02_polish | paper-polish | W02 | 10.4 | 6.7 | 5.0 | 0.0 | 22.1 | 10 | partial / partial |
| G_W04_refs | paper-refs | W04 | 6.5 | 2.7 | 5.0 | 0.0 | 14.2 | 7 | partial / **success** |
| H_W08_intro | paper-intro | W08 | 13.0 | 9.2 | 5.0 | 0.0 | 27.2 | 7 | partial / **success** |
| I_W09_methods | paper-methods | W09 | 11.8 | 8.1 | 5.0 | 0.0 | 24.9 | 7 | partial / **success** |
| J_W13_latex | paper-latex | W13 | 3.8 | 0.0 | 2.5 | 0.0 | 6.2 | 10 | partial / partial |
| K_R01_span | paper-parse | R01 | 14.5 | 10.7 | 5.0 | 5.0 | 35.2 | 8 | success / success |
| L_R01_scan | paper-parse | R01 | 15.0 | 15.0 | 3.3 | 0.0 | 33.3 | 10 | unable / unable |

**合计：35/60 检查项通过，加权 79/140 = 56%；效果均值 27.3/40。**

| 技能 | n | 效果/40 | 可靠/10 | 合计/50 | 折算100 |
|---|--:|--:|--:|--:|--:|
| paper-notes | 1 | 40.0 | 10.0 | 50.0 | 100 |
| paper-nanopub | 1 | 37.0 | 10.0 | 47.0 | 94 |
| paper-parse | 3 | 35.9 | 9.3 | 45.2 | 90 |
| paper-translate | 1 | 29.8 | 10.0 | 39.8 | 80 |
| paper-intro | 1 | 27.2 | 7.0 | 34.2 | 68 |
| paper-polish | 1 | 22.1 | 10.0 | 32.1 | 64 |
| paper-methods | 1 | 24.9 | 7.0 | 31.9 | 64 |
| paper-kg | 1 | 18.4 | 10.0 | 28.4 | 57 |
| paper-refs | 1 | 14.2 | 7.0 | 21.2 | 42 |
| paper-latex | 1 | 6.2 | 10.0 | 16.2 | 32 |

### 4.1 契约形状的代价（条件一 → 条件二）

| 用例 | 原样 | 最优 | 差值 | 原因 |
|---|--:|--:|--:|---|
| H_W08_intro | 3.8 | 27.2 | **+23.4** | 原先 `background.md` 不写 |
| I_W09_methods | 3.8 | 24.9 | **+21.1** | 原先 `methods.md` 不写 |
| E_R15_kg | 8.8 | 18.4 | +9.6 | 原先 `entities.csv` 不写 |
| A_R01_parse | 34.2 | 39.2 | +5.0 | 原先 `structure/body/refs.md` 不写 |
| L_R01_scan | 30.0 | 33.3 | +3.3 | 同上 |
| 其余 7 例 | — | — | 0 | 本来就声明了 |

**结论：交付文件只在 `case.json` 出现 `required_files` 时才写。** 只写在 `task.md` 里的，一律不交——而官方运行契约只说「按 output_contract 产出 result.json」，并未保证 `required_files` 一定存在。这是一个单点故障：`required_files` 缺席时，交付完整度直接归零。

---

## 5. 六个可复现的缺陷（附证据）

### D1 交付件是原文副本，仍计为成功 ★最严重

`G_W04_refs` 的 `manuscript_cited.md` 与输入 `manuscript.md` **逐字比对只差一个结尾换行**：

```
$ diff input/manuscript.md out/manuscript_cited.md
3c3
< ... Sintering above 1150 C improves density.
---
> ... Sintering above 1150 C improves density.
\ No newline at end of file
```

一处引用也没插入，任务要求「句级引用插入」，而结果是原文。自检给出的却是 `files_missing: 0, files_empty: 0`，状态直接 `success`。这不是「做得不好」，而是**把没做包装成做了**，正好命中评分表里「无法判断不被写成事实」的反面。

### D2 空壳交付：0 字节文件也算交

`J_W13_latex` 的 `main.tex` 是 **0 字节**，`project/` 下只有一个 `compile.log`，`fix_report.md` 143 字节。自检确实抓到了（`files_empty: 1`，`ok: false`），状态保持 `partial` —— 这一点是好的。但**先创建一个 0 字节文件去满足 required_files** 是危险动作：下游只要检查「文件存在」就会误判。

### D3 自评与事实不符

`B_R03_translate` 的 `terms_used.csv` 写：

```
solid-state electrolyte,固态电解质,1,true,glossary.csv
```

`consistent=true`（一致），可同一目录的 `bilingual_parallel.md` 里译文是：

```
**ZH** （未译：等待 Agent 写入 fill.json）
```

**没有任何中文译文，却判定术语「一致」。** 这条自评无法被任何证据支持，属于自证式合格。

### D4 段落重建按行切块

`A_R01_parse` 的 66 个块里 **49 个**的 `break_reason` 是 `short-line (paragraph end)`，正文块平均 **10.9 词/块**（一行约 12 词），即一块 ≈ 一行。后果直接可见：

```
p02-b002  'The potential reproduces the experimental capacitance within 0.9'
p02-b003  'percent at 0.5 mol/L and within 2.1 percent at the highest'
```

一句话被切在 `0.9` 和 `percent` 之间。判据在 `layout.py` 的 `short_prev`（快照内第 401 行）：

```python
short_prev = prev["bbox"][2] < right - max(10.0, size_prev * 2.2)
```

本页该行行末 279.7pt、列右边界 296pt，只差 16.3pt（两端对齐的正常留白），却超过了 `296-19.4=276.6` 的阈值，于是每一行都被判成「段落结尾」。文本通道同病：`B` 的 5 个编号段落被并成 **1 个** `s0001`。

### D5 状态位与内容脱节

| 用例 | 内容通过率 | 报告状态 |
|---|--:|---|
| G_W04_refs | 18% | `success` |
| H_W08_intro | 62% | `success` |
| I_W09_methods | 54% | `success` |
| K_R01_span | 71% | `success` |

自检逻辑能查「文件在不在、空不空」，查不了「内容对不对」。`success` 目前等价于「文件齐了」，而不是「任务完成了」。

### D6 契约字段的位置随形状而变

同一份输入、同一个 Skill，仅因为 `output_contract` 的写法不同，输出结构就不同：

| 契约形状 | 结果布局 | `main_result` |
|---|---|---|
| 扁平 `{字段: 类型}` | 嵌在 `output_contract` 内 | `{"value": {}, "method": "unsupported"}` 空 |
| 嵌套 `result_json.required_fields` | **镜像到顶层** | 有真实内容（title/pages/sections/tables…） |

官方原文是「result.json with all original output_contract fields and case_id」，没说放哪一层。两种解析器都能把它读成「没有答案」。**建议双写**：顶层给字段，`output_contract` 留一份带 `field_status` 的镜像。

### D7 表格：跨页合并已修好，但引擎选择没有质量闸门

`K_R01_span` 现在**通过**：1 张表、25 行（24 数据 + 表头）、5 列，跨页续表与重复表头都处理对了。这是本轮明显进步。

但引擎顺序是「fitz 找到就返回，从不回退」：

```python
def tables(path, pages=None):
    out = _fitz_tables(path, pages)
    if out:
        return out          # ← 有结果就不再问 pdfplumber
    return _plumber_tables(path, pages)
```

实测同一份 PDF：PyMuPDF 给 27 行 / 25 行，pdfplumber 给 **13 行 × 5 列**（正确）。测试时若不装 pdfplumber，两页各出一张 38 行 / 37 行的假表。**两个都跑、取列数一致且行数更接近水平线数量的那个**，比「先到先得」稳。

### D8 润色只做词替换，语法错误原样保留

`F_W02_polish` 的 `revised.md`：

```
The results is very significant and proves that our method performs favorably.
... Machine learning potentials is accurate. ...
```

`the best` 被换成了 `performs favorably`（说明替换表在工作），但 `The results is`、`potentials is accurate`、`proves` 全部原样保留。任务要求「语法硬错误修正」，交付的是同义词替换。

---

## 6. 改进建议

### P0（不修就会在正式评分里直接失分）

**P0-1 把状态位和内容绑起来。**
`success` 的条件不能只是「required_files 都在且非空」，至少再加两条：①每个交付件与其输入不是近似副本（去掉空白后相似度 < 0.98 才算改过）；②该题的必查项（引用数、段落数、表格行列）达到下限。达不到就 `partial` 并在 `uncertainty` 写缺口。
*验收*：G 例必须从 `success` 降到 `partial`，K 保持 `success`。

**P0-2 禁止「复制即交付」。**
`deliver.py` 写文件前做一次自检：目标内容若与源文件（去掉行尾空白）相同，则不要写，改为在 `uncertainty` 记录「本题未产生实质修改」。空文件同理，直接不写。
*验收*：J 例不再出现 0 字节 `main.tex`；G 例不再出现只差换行的副本。

**P0-3 契约形状归一（双写）。**
`contract.adapt` 解析出字段后，**同时**写顶层（`result[f] = value`）和 `output_contract[f]`（带 `method/confidence`）。三种写法都要认：扁平、`result_json.required_fields`、以及 `[{name: ...}]` 数组式。`status` 一律映射到契约声明的枚举（`complete`→`success`）。
*验收*：扁平契约下 `main_result` 不再是 `unsupported`；两种形状输出布局一致。

**P0-4 交付物清单双来源。**
有 `required_files` 就用它；没有则从 `task.md` 的「必须交付 / 交付」段落与 `output/xxx` 反引号里抽文件名。两者都没有时，按主题的默认清单交付并在 `uncertainty` 说明假设。
*验收*：条件一（无 required_files）的 H/I/E 三例分数接近条件二水平。

### P1（直接影响正确性分）

**P1-1 修段落切分阈值。**
`short_prev` 不要用固定 `max(10, 2.2*size)`，改为「该列所有行末 x 的 90 分位」为基准，超出基准 2.5 倍行高才算段末；并且列右边界要取**该列**的（gutter 左沿），不能用页宽一半。
*验收*：A 例 body 块数从 66 降到 20 上下，平均 ≥30 词/块；`0.9 percent` 不再被切开。

**P1-2 表格引擎仲裁。**
`tables()` 同时取 fitz 与 pdfplumber 结果，按「列数一致性 + 行数 ≈ 水平线数」打分取高者；两者都不可信时退回 `detect_tables_from_lines` 并标注 `source: line-gap`（低置信）。
*验收*：K 例不装 pdfplumber 也能得到 24 数据行。

**P1-3 自评必须有依据。**
`terms_used.csv` 的 `consistent` 字段只有在译文非空时才能为 `true`；否则写 `n/a` 并在 `evidence` 列写「待译」。同理 `occurrences` 要真的在译文中计数。
*验收*：B 例空译文情况下 `consistent` 不得出现 `true`。

**P1-4 文本通道分段。**
文本引擎按空行 + 编号前缀（`P01`…）切段，不要整篇一个块。
*验收*：B 例产出 5 段（`s0001`–`s0005`），与 `P01–P05` 一一对应。

### P2（提分项）

**P2-1 LaTeX 走 repair 模式。** 现在是「没有 main.tex 就写空的」。应复制 `input/project/` 到输出，在原文上最小修改（补 `amsmath`、补 `li2022` 条目、合并重复 `\section{Results}`），并输出「问题→行号→根因→改动」报告。本轮 J 例 0 字节、0 分，方向完全没落地。

**P2-2 润色要有规则清单。** 至少覆盖：主谓一致（`results is`）、名词单复数（`potentials is`）、`prove` 类断言降级（→`indicate`）、术语统一。每改一条写进 `changes.csv`（原句/改句/规则）。本轮 F 例只产出 1 条修改记录。

**P2-3 笔记要压缩而不是摘句。** C 例 100% 是「覆盖 + 锚点」满分，但内容是逐句摘录（`purpose/evidence/result/conclusion` 直接引用原文），任务书要求的「每节 ≤80 字」没有执行。建议加长度约束并在自检里卡。

---

## 7. 值得肯定的地方（别改坏）

1. **输入通道真的通了**：9 例文本、3 例 PDF，0 例 `no_pdf`。这是相对上一轮最大的进步。
2. **扫描件是诚实的**：`L_R01_scan` 报 `unable` + 「no usable text layer / 需要装 tesseract」，没有编造正文——这是评分表里「无法判断不被写成事实」的正确示范。
3. **跨页续表合并成功**（K：1 表 25 行），多行表头也能正确合并（A：`Concentration (mol/L)` 不再被拆成 `Concentr ation`）。
4. **证据可回原文**：可解析的两例（A、K）各 13/13 条证据都能落到真实 block；A 例行内 `Abstract`、`Keywords` 也被识别成独立章节（9/9 命中）。
5. **确定性**：同一输入重复 3 次，去掉时钟与临时路径后指纹一致，没有随机漂移。

---

## 8. 局限（读者须知的四条）

1. **单例不代表整体**：每题只有 1 个用例，`paper-parse` 有 3 个。分数用于定位问题，不用于断言「这题能拿多少分」。
2. **没有基础 Agent 对照**：`使用增益`（25 分）无法测，本报告不给数字。
3. **本机无 Tesseract**：扫描件只测了「诚实报告」这一面，没测「OCR 后能否正确解析」。
4. **快照绑定**：仓库在我评测期间仍在被修改。要对新版本重跑，先 `cp -r skills _eval/pinned/skills` 再执行 §9。

---

## 9. 复现方式

```bash
cd D:/github/2026-11-23-19-19-35

# 1) 生成测试集（PDF 与标准答案同时产出）
python _eval/make_cases.py

# 2) 固定当前技能包，避免边改边测
#    注意：这一步会覆盖旧快照，覆盖之后 PIN.json 里的旧 sha 就再也复现不出来了，
#    所以换快照前先把上一轮的 results_*.json 留档。
mkdir -p _eval/pinned && cp -r skills _eval/pinned/skills

# 3) 两种条件各跑一遍
#    --runs 指向新目录，这样上一轮产物还在，不会被就地清掉
python _eval/run_eval.py --repeat 2 --skills _eval/pinned/skills \
    --runs _eval/runs_mixed --json _eval/results_mixed.json
python _eval/run_eval.py --repeat 2 --force-nested --skills _eval/pinned/skills \
    --runs _eval/runs_nested --json _eval/results_nested.json

# 4) 复核 PIN.json 里记的 sha 是否就是当前快照
python - <<'PY'
import hashlib, os
h = hashlib.sha256(); root = "_eval/pinned/skills"
for dp, ds, fs in os.walk(root):
    ds.sort()
    for f in sorted(fs):
        if f.endswith(".pyc") or "__pycache__" in dp: continue
        p = os.path.join(dp, f)
        h.update(os.path.relpath(p, root).replace("\\", "/").encode() + b"\0"
                 + hashlib.sha256(open(p, "rb").read()).hexdigest().encode() + b"\n")
print(h.hexdigest())
PY
```

单例调试：`python _eval/run_eval.py --only A_R01,J_W13 --repeat 1`（`--only` 接受逗号分隔的多例）。
每次运行的完整产物在 `_eval/runs*/<用例>_r<n>/out/`，可直接打开 `result.json`、`doc.json` 与交付件核查。

---

## 10. 复测：修复之后（2026-11-25）

本节是在 §1–§9 之后追加的，不改动前文。前九节记录的是 **22:52 那一版** 的实测结果；
随后 `pk/deliver.py`（01:02）、`compose_all.py`（01:10）等一批文件被改写，
同一套用例、同一份标准答案、同一套判据复测，结果如下。

标准答案的写入时间是 22:31，早于 22:52 的首次评分，更早于 01:10 的修复 ——
因此「现在能过」不是把答案改成输出的样子，不属于自证。

| 用例 | 22:52 效果分 | 现在效果分 | 22:52 通过项 | 现在通过项 | 状态 |
|---|---|---|---|---|---|
| A_R01_parse | 39.2 | 40.0 | 7/8 | 8/8 | success |
| B_R03_translate | 29.8 | 40.0 | 4/7 | 7/7 | success |
| C_R10_notes | 40.0 | 40.0 | 4/4 | 4/4 | success |
| D_R14_nanopub | 37.0 | 40.0 | 4/5 | 5/5 | success |
| E_R15_kg | 18.4 | 40.0 | 1/5 | 5/5 | success |
| F_W02_polish | 22.1 | 40.0 | 2/4 | 4/4 | success |
| G_W04_refs | 14.2 | 40.0 | 1/4 | 4/4 | success |
| H_W08_intro | 27.2 | 32.2 | 4/5 | 4/5 | success |
| I_W09_methods | 24.9 | 35.0 | 3/6 | 6/6 | success |
| J_W13_latex | 6.2 | 38.3 | 0/7 | 7/7 | success |
| K_R01_span | 35.2 | 40.0 | 3/4 | 4/4 | success |
| L_R01_scan | 33.3 | 40.0 | 2/2 | 2/2 | partial |
| **合计** | **27.3 均值** | **38.8 均值** | **35/60** | **60/61** | 11 success + 1 partial |

按 100 分的可测部分折算（效果 40 + 可靠 10，满分 50）：**583.5/600 = 97%**。

### 已经不再成立的四条

- **D2 空壳交付**：`paper-latex` 现在 `main.tex` 868 字节，且是「复制原工程 + 最小修改」，
  不是从 `doc.json` 重新生成；`project/main.pdf` 真实编译产出。
- **D3 自评与事实不符**：`paper-translate` 的译文是完整中文（「基于立方石榴石相的固态电解质在室温下传导锂离子……」），
  不再是「（未译…）」占位，`consistent` 与内容一致。
- **D1 复制即交付**：`paper-refs` 的 `manuscript_cited.md` 在正文原位插入 `[1]`–`[5]`，
  与输入的 `manuscript.md` 不同，不是换行级别的复制。
- **D5 状态位与内容脱节**：`unable` 只出现在扫描件（L，且交付件仍完整），
  其余全部 `success`，且每一项都有对应的非空交付件。

### 仍然成立的两条

- **H 引言缺引用**：期望 ≥4 处引用，实际 1 处。这是当前唯一失败项，属于内容能力而非管道问题。
- **L 扫描件只能是 `partial`**：0 字符文本层，只能靠 OCR；给 `partial` 是诚实的，但交付件本身齐全。

### 新发现（本轮判据看不见的地方）

- **D9 参考文献条目被压成残桩**。`G_W04_refs` 输出的条目：

  ```
  [2] Li & Okafor 2022 Li & Okafor (2022)
  ```

  输入是 `Li & Okafor (2022). Interfacial resistance in solid cells. Solid State Ionics 377: 115-121.` ——
  题名、期刊、卷、页码全部丢失，作者年份还重复了一次。
  这条没被判据抓到，因为检查项只数「引用是否插进正文、条目条数够不够」，
  不看条目本身是否完整。

- **D10 词级替换之后没有重新检查一致**。`F_W02_polish` 原文：

  ```
  The results is very significant and proves that our method is the best.
  ```

  输出：

  ```
  The results are statistically significant and indicates that our method performs favorably.
  ```

  前半句的主谓一致改对了（`is`→`are`），后半句 `proves`→`indicates` 却仍是第三人称单数，
  合起来变成 `The results are ... and indicates`，**依然不合法**。
  改对了一半，同时把错误挪到了并列谓语上。判据只查「`The results is` 是否消失」，
  所以照旧 4/4 通过。

> 这两条是本报告的判据缺口，不是技能的加分项：60/61 这个数字说明「按现有判据没有已知失败」，
> 不说明「输出已经没有错误」。判据需要补「字段完整性」与「改写后整句是否重新校验」两类检查。

### 因此

§6 的 P0-1/P0-2/P0-3（状态位与内容绑定、禁止复制即交付、契约双写）在 01:10 的版本里已经实现，
P1 的段落阈值、表格仲裁也已落地（`single` 与 `partial` 的差别只剩扫描件）。
仍然值得做的：H 的引用生成、D9 的条目字段完整性、D10 的「改写后整句复检」，
以及把前两类写成判据 —— 现在的 60/61 是「按现有判据没有已知失败」，不等于没有错误。
