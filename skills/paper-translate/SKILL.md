---
name: paper-translate
description: Translate research papers segment by segment with a locked glossary, protected numbers/units/citations and a verification pass. Use when a task asks for a Chinese translation of a paper, bilingual paragraph alignment, terminology consistency, or a translation QA report.
version: 1.0.0
license: MIT
---

# Paper Translate — 阅读03 文献翻译

## 用途

Translate research papers segment by segment with a locked glossary, protected numbers/units/citations and a verification pass. Use when a task asks for a Chinese translation of a paper, bilingual paragraph alignment, terminology consistency, or a translation QA report.

本 Skill 交付的不是一段“看起来像结果”的文本，而是一份**可复核的结构化结果**：
每条结论都带页码与块 id（`p07-b012` 形式），读不出的部分如实标注，而不是猜。

## 触发条件

- 任务要求翻译论文/摘要/章节，并要求术语统一、可回看原文
- 需要段落级双语对照、译后核验、译不准处标注
- 长文跨页跨栏，直接整篇翻译会漏段、串段、术语漂移

不适用：与文献无关的任务、纯图片问答、需要联网检索的任务。

## 输入

| 位置 | 内容 |
|---|---|
| `/input/case.json` | 案例元信息，可能包含 `output_contract` 字段清单 |
| `/input/task.md` | 本次任务说明 |
| `/input/*.pdf` | 原始论文（无预抽取文本层）|
| `/input/*` | 其他材料：docx / tex / bib / csv / json / md |

## 快速开始

```bash
# 1) 一次跑完解析 + 组包
python3 scripts/run.py --input /input --out /app/output

# 2) 看产物
ls /app/output          # doc.json doc.md coverage.json result.json run.log

# 3) 自检
python3 scripts/verify.py --out /app/output --kind translate
```

`run.py` 是幂等的，可重复执行；`--no-ocr` 可跳过 OCR（更快，但扫描页会空）。

## 处理流程

**术语先锁定，再逐段翻译，最后机器核验。**

1. **切段**：按块（而非按页）切分，块内再按句边界合并到 ≤850 字符，得到 `s0001…` 段号；
   每段保留 `block`、`page`、`section`，因此译文永远能回到原文位置。
2. **术语表**：从全文抽高频术语/缩写（`X (ABC)` 形式优先），与内置学术词表合并；
   同一术语只允许一个译名，冲突由 `verify.py` 报错。
3. **保护令牌**：每段提前抽出数字、单位、引用标记 `[12]`、图表编号、公式片段、模型/数据集专名，
   译文中必须原样出现——这一步把“翻译时把 28.4 BLEU 写成 28.4 分”这类错误变成机器可查的问题。
4. **逐段翻译**：Agent 按段填 `translation`，只译该段，不合并、不省略、不添加解释。
5. **核验**：`verify.py` 检查空译、数字/单位/引用丢失、译文长度异常、术语一名多译。

## 输出

`result.json` 主要字段：

| 字段 | 内容 |
|---|---|
| `segments[]` | `seg`、`block`、`page`、`section`、`source`、`protected`、`translation` |
| `glossary[]` | 术语、出现次数、建议译名 `zh` |
| `rules` | 术语策略、必须原样保留的令牌、语域要求 |

`translation` 初始为空是**设计如此**：这一栏必须由模型逐段填写，脚本不生成译文。

`result.json` 同时保留 `case_id`、`status`、`evidence`、`uncertainty`、`provenance`，
以及 `case.json` 里声明的 `output_contract` 字段（存在则逐项填，缺证据就留 `null` 并说明）。

## 最小调用示例

```bash
python3 scripts/run.py --input /input --out /app/output      # 生成分段与术语表
# Agent 逐段填写 result.json 的 segments[].translation
python3 scripts/verify.py --out /app/output --kind translate  # 译后核验
```

示意输出（**示例，非正式案例结果**）：

```json
{"segments": [{"seg": "s0001", "block": "p01-b005", "section": "Abstract",
  "source": "The dominant sequence transduction models are based on complex recurrent networks.",
  "protected": {"numbers": [], "citations": []},
  "translation": "主流的序列转换模型基于复杂的循环神经网络。"}]}
```

## 异常处理

| 情况 | 处置 |
|---|---|
| 段落过长导致截断 | 按句边界再切，禁止从句子中间截断 |
| 术语表冲突 | 以首次出现并在标题/摘要中使用的译名为准，其余全部改齐 |
| 公式/符号无法翻译 | 原样保留，前后文用中文衔接，不改写公式 |
| 原文本身残缺（PDF 丢字） | 译文中用 `[原文缺失]` 标注，不猜测 |

## 适用边界

不润色原文、不补写原文没有的内容；诗歌、广告等非学术文体不在适用范围。

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
