---
name: paper-polish
description: Diagnose academic prose before rewriting it: long sentences, passive stacking, hedging strength, absolute claims, terminology drift and abbreviation first use. Use when a task asks to polish, edit or proofread academic English/Chinese while preserving meaning, numbers and citations.
version: 1.0.0
license: MIT
---

# Paper Polish — 写作02 学术语言润色

## 用途

Diagnose academic prose before rewriting it: long sentences, passive stacking, hedging strength, absolute claims, terminology drift and abbreviation first use. Use when a task asks to polish, edit or proofread academic English/Chinese while preserving meaning, numbers and citations.

本 Skill 交付的不是一段“看起来像结果”的文本，而是一份**可复核的结构化结果**：
每条结论都带页码与块 id（`p07-b012` 形式），读不出的部分如实标注，而不是猜。

## 触发条件

- 任务要求润色/校对/改写学术文本，且不能改变原意与结论强度
- 需要逐条修改记录（原文/改文/类型/理由）
- 担心润色时丢限定词、改数字、术语漂移

不适用：与文献无关的任务、纯图片问答、需要联网检索的任务。

## 输入

| 位置 | 内容 |
|---|---|
| `/input/case.json` | 案例元信息，可能包含 `output_contract` 字段清单 |
| `/input/task.md` | 本次任务说明 |
| `/input/*.pdf` | 原始论文（无预抽取文本层）|
| `/input/*` | 其他材料：docx / tex / bib / csv / json / md |

## 快速开始

**先定位本 Skill 的安装目录**。评测环境把它装在 `/skills/weekly-skill`，本地可能在别处，
所以不要假设当前工作目录：脚本按 `SKILL.md` 所在目录相对定位。

```bash
# 0) 定位：官方安装在 /skills/weekly-skill，找不到再就近搜索
SKILL_DIR=/skills/weekly-skill
[ -f "$SKILL_DIR/SKILL.md" ] || SKILL_DIR="$(
  find /skills /app /workspace /opt -maxdepth 5 -name SKILL.md 2>/dev/null | head -1 | xargs -r dirname
)"
cd "$SKILL_DIR" || exit 1

# 1) 一次跑完解析 + 组包
python3 scripts/run.py --input /input --out /app/output

# 2) 看产物
ls /app/output          # doc.json doc.md coverage.json result.json run.log

# 3) 自检
python3 scripts/verify.py --out /app/output --kind generic
```

只依赖 Python 标准库；有 PyMuPDF 时用它做主力引擎，没有则自动退化到 pdfplumber / pypdf /
poppler，缺什么会在 `run.log` 和 `coverage.json` 里写明，不会静默降级。

`run.py` 是幂等的，可重复执行；`--no-ocr` 可跳过 OCR（更快，但扫描页会空）。

## 处理流程

先诊断，再改写，最后用规则守住“没改坏”。

1. **句级体检**：长句（>38 词）、被动堆叠、强化词（very/significantly）、绝对化（all/never/prove）、
   缩写（don't）、名词化过重，逐句给 `flags` 与 block id。
2. **术语一致性**：`X (ABC)` 首次定义、`dataset` vs `data set` 等拼写变体、缩写重复定义。
3. **文体判定**：期刊论文 / 学位论文 / 基金申请 / 审稿回复，语气与主语策略不同。
4. **改写（Agent 执行）**：按 `edit_record_schema` 逐条产出，一条记录只改一处，
   `kept` 字段列出该句必须保留的数字、单位与引用。
5. **守住语义**：数字、单位、引用编号、否定范围、限定词强度、因果/相关措辞不得变化；
   违反时宁可少改。

## 输出

| 字段 | 内容 |
|---|---|
| `genre` | 判定出的文体 |
| `sentence_issues[]` | block、原句、flags |
| `consistency[]` | 术语/拼写/缩写不一致 |
| `edit_record_schema` | 修改记录的字段约定 |
| `guardrails` | 改写红线 |

`result.json` 同时保留 `case_id`、`status`、`evidence`、`uncertainty`、`provenance`，
以及 `case.json` 里声明的 `output_contract` 字段。字段名与内部切片对不上时按语义匹配回填，
**仍为空才留 `null`**，并在 `uncertainty.inferred_fields` 里逐项说明是怎么推出来的。

## 最小调用示例

```bash
python3 scripts/run.py --input /input --out /app/output --profile polish
# Agent 按 schema 产出 edits[]，再自查 guardrails
```

示意输出（**示例，非正式案例结果**）：

```json
{"sentence_issues": [{"block": "p02-b004", "page": 2,
  "sentence": "It is very clear that all models are always better with more data.",
  "flags": ["intensifier", "absolute-claim"]}]}
```

## 异常处理

| 情况 | 处置 |
|---|---|
| 原句本身语法正确但风格不合 | 标注 `register` 而非 `grammar`，改写幅度最小 |
| 改写后数字/引用丢失 | 直接判为失败，回到原句重写 |
| 中文稿件夹英文术语 | 保留术语原形，只改连接与语序 |

## 适用边界

不代替作者判断学术观点；不做降重、不做翻译（翻译用 paper-translate）。

## 文件清单

```
SKILL.md
environment/resources.yaml     # 依赖与预置运行时说明
scripts/run.py                 # 入口
scripts/compose_all.py         # 题型组装
scripts/verify.py              # 事后核验
scripts/pk/                    # paperkit 内核（解析、版面、证据、结果）
examples/case.example.json     # 最小输入示例（示例，非正式案例）
examples/result.example.json   # 示意输出（示例，非正式案例）
GITHUB_URL.txt                 # 公开仓库链接
```

## 版本与依赖

- paperkit 1.0.0（纯标准库；按可用性依次使用 PyMuPDF / pdfplumber / pypdf / poppler）
- 无网络依赖；不下载模型；OCR 仅在系统存在 `tesseract` 或 `ocr-tool` 时启用
- 资源约束：≤50 个 UTF-8 文本文件，单文件 ≤500KB，合计 ≤2MB，无符号链接
