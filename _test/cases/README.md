# 自建测试用例（带标准答案）

平台给的 case 只有一份，改不动也看不到期望值。这里用代码**生成**测试用例：
页面、表格、数值、公式编号、引用缺口在生成时就确定，所以"抽得对不对"可以自动判定，
而不只是"看起来合理"。

## 目录约定

每个用例目录与平台输入目录同构：

```
<case>/
  case.json     # case_id + topic + output_contract（skill 要按这些键回填）
  task.md       # agent 读到的任务说明
  paper.pdf     # 材料，由 make_cases.py 生成，不进仓库
  gold.json     # 期望值，run_cases.py 用它逐项核对
```

## 跑法

```bash
cd _test/cases
python make_cases.py      # 生成 18 个用例目录（含 paper.pdf）
python run_cases.py       # 跑对应 skill，按 gold.json 核对 → report.md
python run_matrix.py      # 10 个包 × 2 篇真实论文 + verify.py → matrix.md
```

`run_cases.py` 支持只跑部分用例与单个技能：

```bash
python run_cases.py p01 p08          # 按前缀筛
python run_cases.py --skill=paper-kg
```

需要安装 `pymupdf`（生成 PDF、跑解析都要）。

## 用例清单

| 用例 | 题 | 期望值要点 |
|---|---|---|
| `p01-parse-single` | 阅读01 | 3 页、4 位作者、5 章节、表格 5×6（`24.1/4.92/0.512` 逐值）、公式编号 `(1)` |
| `p02-parse-twocol` | 阅读01 | 右栏先写入内容流，正确输出必须 `3.1` 在 `3.2` 之前 |
| `p03-translate` | 阅读03 | 段数 ≤120、每批 ≤20、跳过参考文献、`1.8/10%/1.2x/[1]/fairseq` 保留 |
| `p04-notes` | 阅读10 | 要点含 low-resource / WMT 2014 / BLEU；局限句来自原文 |
| `p05-nanopub` | 阅读14 | 断言 ≥2 条且保留 `1.8 BLEU` |
| `p06-kg` | 阅读15 | 实体含 fairseq / WMT 2014 / BLEU，边 ≥10 |
| `p07-polish` | 写作02 | 数字与引用原样进入改写队列的 `kept` |
| `p08-refs` | 写作04 | 缺失条目 `5`、未引用 `4`、重复对 `2-4`、BibTeX `@inproceedings` |
| `p09-intro` | 写作08 | draft 五段骨架；`--fill` 后才 `complete` |
| `p10-methods` | 写作09 | 三个超参取到、种子进 `missing`（原文确实没写） |
| `p11-latex` | 写作13 | `main.tex` 落盘、`compile.static_check` 存在 |
| `x01-encrypted` | 异常 | AES-256 加密 → `unable`，不生成正文 |
| `x02-imageonly` | 异常 | 整页图片、无 OCR → `unable` |
| `x03-corrupt` | 异常 | 随机字节 → `unable`，`result.json` 仍写出 |
| `x04-nopdf` | 异常 | 目录里没有 PDF → `unable` |
| `x05-zeropage` | 异常 | `/Count 0` → `unable`，不崩 |
| `x06-imagetable` | 异常 | 有文字层但表格是图片 → `image_tables[]` 标记，不报「无表格」 |
| `x07-ownerlocked` | 异常 | 仅 owner 口令、user 口令为空 → 空口令读出，标 `encrypted/decrypted` |

合成论文页眉写着 `SYNTHETIC TEST DOCUMENT`，内容为虚构，仅用于测试，
不要当成真实文献引用。
