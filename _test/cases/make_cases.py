"""Generate the self-test case set.

Every case is a directory shaped like the platform's input directory:
    <case>/case.json   contract the skill must answer against
    <case>/task.md     the instruction the agent reads
    <case>/paper.pdf   the document (absent for the "no pdf" case)

The synthetic papers are written here, so the expected answer is known in
advance -- `gold.json` holds that expectation and `run_cases.py` checks the
pipeline against it.  This is the difference between "the output is
self-consistent" and "the output is correct".

Run with the interpreter that has pymupdf installed:
    python make_cases.py
"""

from __future__ import annotations

import json
import os
import random
import shutil

import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 595, 842
LEFT, RIGHT = 72, 523


def wrap(text: str, width: float, size: float, font: str = "helv") -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if pymupdf.get_text_length(trial, fontname=font, fontsize=size) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def para(page, x, y, text, width, size=9.5, lead=13.2, font="helv"):
    for line in wrap(text, width, size, font):
        page.insert_text((x, y), line, fontsize=size, fontname=font)
        y += lead
    return y


def header(page, text="SYNTHETIC TEST DOCUMENT - generated for pipeline self-test, not a real publication"):
    page.insert_text((LEFT, 40), text, fontsize=6.5, fontname="helv", color=(0.45, 0.45, 0.45))


def footer(page, n):
    page.insert_text((W / 2 - 10, H - 36), str(n), fontsize=8, fontname="helv")


# --------------------------------------------------------------------------- #
# paper 1: single column, three pages, every extractable feature present
# --------------------------------------------------------------------------- #
TITLE = "Sparse Routing for Low-Resource Neural Machine Translation"
AUTHORS = "Mira Kovacs, Daniel Osei, Petra Lindqvist, Ravi Menon"
AFFIL = "Institute of Computational Linguistics, Zurich"

ABSTRACT = (
    "We study whether sparse expert routing helps neural machine translation when parallel "
    "data is scarce. A shared encoder feeds eight experts, of which two are active per token. "
    "On WMT 2014 English-German with only 10% of the bitext we observe a gain of 1.8 BLEU over "
    "a dense baseline of equal parameter count, while decoding stays within 1.2x of its latency. "
    "The gain disappears once the full corpus is used, which suggests the benefit comes from "
    "parameter isolation rather than from capacity alone."
)

SEC1 = (
    "Neural machine translation has improved rapidly, yet most gains assume millions of sentence "
    "pairs [1]. For languages with a few hundred thousand pairs, adding parameters usually overfits "
    "rather than helps. Conditional computation promises capacity without proportional compute [2], "
    "but routing quality is known to degrade when the training signal is thin [5]. "
    "We ask a narrower question: with a fixed compute budget, does sparse routing still pay off "
    "when the bitext is small?"
)

SEC2 = (
    "Sparse mixtures of experts route each token to a subset of feed-forward blocks. Prior work "
    "applies them at very large scale, where each expert still sees many tokens. Subword "
    "segmentation reduces vocabulary sparsity [2], and toolkit level optimisations make such models "
    "practical to train [3]. What remains unclear is the low-resource regime: with only 10% of the "
    "corpus, each expert may see too few gradient signals to specialise."
)

SEC3 = (
    "The model keeps the standard encoder-decoder shape and replaces every other feed-forward "
    "layer with a mixture of eight experts. A learned gate selects the top two experts per token, "
    "and their outputs are combined with the gate weights. We train with a learning rate of 0.0003, "
    "batch size 32, and dropout 0.1 for 40 epochs. The encoder has 8 attention heads and 6 layers, "
    "and the embedding size is 512. A load balancing loss with coefficient 0.01 prevents expert collapse."
)

SEC3B = (
    "Training minimises the token-level cross entropy with label smoothing 0.1. The routing loss is "
    "added with a fixed coefficient, so no additional tuning is required across datasets."
)

SEC4 = (
    "We evaluate on WMT 2014 English-German, which contains 4.5M sentence pairs, and on a "
    "low-resource subset built by sampling 10% of the pairs. Translation quality is reported as "
    "BLEU. All models are trained on 8 NVIDIA V100 GPUs with fairseq [3]. Decoding uses beam size 4 "
    "and length penalty 1.0. Each configuration is trained once, and we report the final checkpoint."
)

SEC5 = (
    "Sparse routing helps when data is scarce and stops helping once data is abundant. The effect "
    "is consistent across two subsets but was measured on a single language pair, so the scope of "
    "the claim is limited. Future work should test whether routing patterns transfer across "
    "language families."
)

REFS = [
    "[1] Vaswani A, Shazeer N, Parmar N, et al. Attention is all you need[C]//NeurIPS. 2017: 5998-6008.",
    "[2] Sennrich R, Haddow B, Birch A. Neural machine translation of rare words with subword "
    "units[C]//ACL. 2016: 1715-1725. doi:10.18653/v1/P16-1162",
    "[3] Ott M, Edunov S, Baevski A, et al. fairseq: A fast, extensible toolkit for sequence "
    "modeling[C]//NAACL. 2019: 48-53.",
    "[4] Sennrich R, Haddow B, Birch A. Neural machine translation of rare words with subword "
    "units[C]//ACL. 2016: 1715-1725. doi:10.18653/v1/P16-1162",
]

TABLE = [
    ["Model", "BLEU", "Params", "Speed", "Memory", "Score"],
    ["Dense baseline", "24.1", "65M", "1.00x", "3.2G", "0.512"],
    ["Sparse top-1", "25.3", "102M", "1.31x", "4.92G", "0.548"],
    ["Sparse top-2", "25.9", "118M", "1.44x", "5.61G", "0.571"],
    ["Sparse top-2 + balance", "26.2", "118M", "1.44x", "5.61G", "0.583"],
]


def make_single(path):
    doc = pymupdf.open()
    p1 = doc.new_page(width=W, height=H)
    header(p1)
    y = 96
    for line in wrap(TITLE, RIGHT - LEFT, 17):
        p1.insert_text((LEFT, y), line, fontsize=17, fontname="helv")
        y += 21
    y += 8
    p1.insert_text((LEFT, y), AUTHORS, fontsize=10.5, fontname="helv")
    y += 15
    p1.insert_text((LEFT, y), AFFIL, fontsize=9, fontname="helv")
    y += 13
    p1.insert_text((LEFT, y), "mira.kovacs@example.org, daniel.osei@example.org",
                   fontsize=8.5, fontname="helv")
    y += 24
    p1.insert_text((LEFT, y), "Abstract", fontsize=11, fontname="helv")
    y += 15
    y = para(p1, LEFT, y, ABSTRACT, RIGHT - LEFT) + 10
    p1.insert_text((LEFT, y), "Keywords: sparse routing, low-resource MT, mixture of experts",
                   fontsize=9, fontname="helv")
    y += 22
    p1.insert_text((LEFT, y), "1 Introduction", fontsize=12, fontname="helv")
    y += 16
    y = para(p1, LEFT, y, SEC1, RIGHT - LEFT) + 10
    p1.insert_text((LEFT, y), "2 Related Work", fontsize=12, fontname="helv")
    y += 16
    y = para(p1, LEFT, y, SEC2, RIGHT - LEFT)
    footer(p1, 1)

    p2 = doc.new_page(width=W, height=H)
    header(p2)
    y = 80
    p2.insert_text((LEFT, y), "3 Method", fontsize=12, fontname="helv")
    y += 16
    y = para(p2, LEFT, y, SEC3, RIGHT - LEFT) + 12

    # equation with a number, a sqrt and a Greek letter
    p2.insert_text((LEFT + 40, y), "L = sqrt(1/T) * SUM_t [ -log p(y_t) ] + alpha * L_bal", fontsize=10,
                   fontname="times-roman")
    p2.insert_text((RIGHT - 20, y), "(1)", fontsize=10, fontname="helv")
    y += 22
    y = para(p2, LEFT, y, SEC3B, RIGHT - LEFT) + 14

    # table 1: horizontal rules only -- the classic borderless academic table
    p2.insert_text((LEFT, y), "Table 1: Quality and cost on WMT 2014 English-German (10% subset).",
                   fontsize=8.8, fontname="helv")
    y += 16
    cols = [LEFT, LEFT + 108, LEFT + 172, LEFT + 226, LEFT + 280, LEFT + 342]
    rowh = 15
    for i, row in enumerate(TABLE):
        for j, cell in enumerate(row):
            p2.insert_text((cols[j], y + i * rowh), cell, fontsize=8.6, fontname="helv")
    for i in range(len(TABLE) + 1):
        yy = y - 9 + i * rowh
        p2.draw_line((LEFT, yy), (RIGHT, yy), color=(0, 0, 0), width=0.7)
    y += len(TABLE) * rowh + 18

    p2.insert_text((LEFT, y), "4 Experiments", fontsize=12, fontname="helv")
    y += 16
    para(p2, LEFT, y, SEC4, RIGHT - LEFT)
    footer(p2, 2)

    p3 = doc.new_page(width=W, height=H)
    header(p3)
    y = 80
    p3.insert_text((LEFT, y), "5 Conclusion", fontsize=12, fontname="helv")
    y += 16
    y = para(p3, LEFT, y, SEC5, RIGHT - LEFT) + 22
    p3.insert_text((LEFT, y), "References", fontsize=12, fontname="helv")
    y += 18
    for r in REFS:
        y = para(p3, LEFT, y, r, RIGHT - LEFT, size=8.8, lead=12) + 5
    footer(p3, 3)
    doc.save(path, deflate=True)
    doc.close()


# --------------------------------------------------------------------------- #
# paper 2: two columns, right column written into the stream first
# --------------------------------------------------------------------------- #
LCOL = [
    ("3.1 Encoder", "The encoder maps an input sequence of symbol representations to a sequence of "
                    "continuous representations. It is composed of a stack of six identical layers."),
    ("", "Each layer has two sub-layers: multi-head self-attention and a position-wise feed-forward "
         "network. residual connections surround each sub-layer followed by layer normalisation."),
]
RCOL = [
    ("3.2 Decoder", "The decoder inserts a third sub-layer which performs multi-head attention over "
                    "the encoder output. Masking prevents positions from attending to later ones."),
    ("", "The decoder is also composed of a stack of six identical layers with the same width."),
]


def make_twocol(path):
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    header(page)
    page.insert_text((LEFT, 88), "Two Column Layout Probe", fontsize=16, fontname="helv")
    colw = (RIGHT - LEFT - 24) / 2
    lx, rx = LEFT, LEFT + colw + 24

    # deliberately write the RIGHT column first so that a naive "content stream
    # order" reader would produce right-before-left; a real layout pass must not.
    y = 130
    for head, body in RCOL:
        if head:
            page.insert_text((rx, y), head, fontsize=10.5, fontname="helv")
            y += 15
        y = para(page, rx, y, body, colw, size=9, lead=12.5) + 8

    y = 130
    for head, body in LCOL:
        if head:
            page.insert_text((lx, y), head, fontsize=10.5, fontname="helv")
            y += 15
        y = para(page, lx, y, body, colw, size=9, lead=12.5) + 8
    footer(page, 1)
    doc.save(path, deflate=True)
    doc.close()


# --------------------------------------------------------------------------- #
# exception cases
# --------------------------------------------------------------------------- #
def make_encrypted(src, dst):
    doc = pymupdf.open(src)
    doc.save(dst, encryption=pymupdf.PDF_ENCRYPT_AES_256,
             owner_pw="owner-secret", user_pw="user-secret",
             permissions=pymupdf.PDF_PERM_PRINT)
    doc.close()


def make_imageonly(src, dst):
    src_doc = pymupdf.open(src)
    out = pymupdf.open()
    for sp in src_doc:
        pix = sp.get_pixmap(dpi=140)
        np = out.new_page(width=W, height=H)
        np.insert_image(pymupdf.Rect(0, 0, W, H), pixmap=pix)
    out.save(dst, deflate=True)
    out.close()
    src_doc.close()


def make_corrupt(dst):
    rnd = random.Random(20261123)
    body = bytes(rnd.randrange(256) for _ in range(900))
    with open(dst, "wb") as fh:
        fh.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        fh.write(body)
        fh.write(b"\n%%EOF\n")


def make_zeropage(dst):
    with open(dst, "wb") as fh:
        fh.write(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
                 b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
                 b"trailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n0\n%%EOF\n")


# --------------------------------------------------------------------------- #
# case directories
# --------------------------------------------------------------------------- #
def write_case(name, case_id, topic, note, contract, task, pdf=None, gold=None):
    d = os.path.join(HERE, name)
    os.makedirs(d, exist_ok=True)
    case = {"case_id": case_id, "topic": topic, "note": note, "output_contract": contract}
    with open(os.path.join(d, "case.json"), "w", encoding="utf-8") as fh:
        json.dump(case, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    with open(os.path.join(d, "task.md"), "w", encoding="utf-8") as fh:
        fh.write(task.strip() + "\n")
    if pdf:
        shutil.copyfile(pdf, os.path.join(d, "paper.pdf"))
    if gold is not None:
        with open(os.path.join(d, "gold.json"), "w", encoding="utf-8") as fh:
            json.dump(gold, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    return d


CONTRACT_PARSE = {
    "document": "title/authors/abstract/pages/engine",
    "structure": "section tree",
    "content.blocks": "list with page + block id",
    "content.tables": "caption/header/rows",
    "content.formulas": "number/text/block",
    "content.references": "n/text/page",
    "coverage": "per-page chars, empty pages, issues",
    "status": "complete|partial|unable",
}

CONTRACT_TRANSLATE = {"segments": "seg/block/page/section/source/translation", "glossary": "term/zh",
                      "status": "complete|partial|unable"}
CONTRACT_NOTES = {"note": "question/data/methods/findings/limitations/sections", "evidence": "anchors",
                  "status": "complete|partial|unable"}
CONTRACT_NANOPUB = {"assertion": "claim", "provenance": "block anchors", "status": "complete|partial|unable"}
CONTRACT_KG = {"nodes": "id/label/type", "edges": "source/target/relation/evidence", "stats": "counts",
               "status": "complete|partial|unable"}
CONTRACT_POLISH = {"diagnostics": "per-sentence issues", "rewrites": "before/after", "status": "complete|partial|unable"}
CONTRACT_REFS = {"entries": "parsed entries", "issues": "missing/uncited/duplicate", "formatted": "gbt/apa/bibtex",
                 "status": "complete|partial|unable"}
CONTRACT_INTRO = {"problem_statements": "list", "related_work_groups": "list", "gap_statements": "list",
                  "contributions": "list", "draft": "paragraph skeleton", "status": "complete|partial|unable"}
CONTRACT_METHODS = {"parameters": "name/value/context", "datasets": "list",
                    "reproducibility_checklist": "found/missing", "draft": "skeleton",
                    "status": "complete|partial|unable"}
CONTRACT_LATEX = {"files": "written files", "compile": "attempted/engine/ok/errors", "status": "complete|partial|unable"}


def main():
    gold_pdf = os.path.join(HERE, "_build_single.pdf")
    twocol_pdf = os.path.join(HERE, "_build_twocol.pdf")
    make_single(gold_pdf)
    make_twocol(twocol_pdf)

    gold = {
        "pages": 3,
        "title_words": ["Sparse", "Routing"],
        "authors": ["Mira Kovacs", "Daniel Osei", "Petra Lindqvist", "Ravi Menon"],
        "sections": ["1 Introduction", "2 Related Work", "3 Method", "4 Experiments", "5 Conclusion"],
        "tables": [{"n_rows": 5, "n_cols": 6, "must_contain": ["26.2", "0.583", "118M"]}],
        "formulas": {"at_least": 1, "number": "(1)"},
        "hyperparameters": {"learning rate": "0.0003", "batch size": "32", "dropout": "0.1",
                            "attention heads": "8", "layers": "6"},
        "datasets": ["WMT 2014"],
        "hardware": "V100",
        "seeds_reported": False,
        "refs": {"entries": 4, "citations_without_entry": ["5"], "entries_never_cited": ["4"],
                 "duplicate_pair": ["2", "4"]},
        "kg_must_have": ["fairseq", "WMT 2014", "BLEU"],
    }

    write_case("p01-parse-single", "self-parse-single", "阅读01 文献文档解析",
               "自建单栏三页用例，含无边框表格、带编号公式、四位作者、四条参考文献（一条重复 DOI、一条未被引用、正文引用了不存在的 [5]）。",
               CONTRACT_PARSE,
               """### 文献文档解析（单栏）

解析本目录 `paper.pdf`，输出章节树、带 `[pNN-bNNN]` 锚点的正文块、表格（含题注与行列数）、
公式（编号与所在块）以及参考文献条目。作者、页数、引擎写入 `document`。
表格必须恢复 6 列 5 行（含表头），数值不得被改写。无法识别的部分在 `status`/`uncertainty` 中说明。""",
               gold_pdf, gold)

    write_twocol = {
        "reading_order": ["3.1 Encoder", "3.2 Decoder"],
        "note": "右栏在内容流中先于左栏写入，正确实现应输出 3.1 在 3.2 之前",
    }
    write_case("p02-parse-twocol", "self-parse-twocol", "阅读01 文献文档解析",
               "自建双栏用例：右栏在 PDF 内容流中先写入，用于检验 XY-cut 阅读顺序是否真的按栏排序。",
               CONTRACT_PARSE,
               """### 文献文档解析（双栏阅读顺序）

本目录 `paper.pdf` 为双栏排版，且右栏在文件内容流中先于左栏写入。
请输出正文块顺序，并说明阅读顺序判定依据（`order_rule`）。正确结果中
`3.1 Encoder` 必须出现在 `3.2 Decoder` 之前。""",
               twocol_pdf, write_twocol)

    write_case("p03-translate", "self-translate", "阅读03 文献翻译",
               "自建翻译用例：三段正文 + 参考文献，检验分段上限、批量切分与保护令牌（数字、引用、模型名）。",
               CONTRACT_TRANSLATE,
               """### 文献翻译

把本目录 `paper.pdf` 的摘要与正文译为中文，逐段输出中英对照。
数字（1.8 BLEU、10%、1.2x）、引用编号（[1] [2] [3] [5]）与模型/工具名（fairseq、WMT 2014）必须原样保留。
参考文献不译。译不准处标注，不臆造。""",
               gold_pdf, {"max_segments": 120, "batch_size": 20, "skip_sections": ["References"],
                          "protected_examples": ["1.8", "10%", "1.2x", "[1]", "fairseq"]})

    write_case("p04-notes", "self-notes", "阅读10 文献总结与结构化笔记",
               "自建笔记用例：研究问题、数据、方法、结论、局限均可从原文定位。",
               CONTRACT_NOTES,
               """### 结构化阅读笔记

为本目录 `paper.pdf` 生成阅读笔记：研究问题、数据与规模、方法要点、主要结论、局限。
每条都要能在原文找到出处（页码 + 块号）。原文没写的内容留空并说明，不要补写。""",
               gold_pdf, {"must_answer": ["low-resource", "WMT 2014", "BLEU"],
                          "limitations_from_text": ["single language pair"]})

    write_case("p05-nanopub", "self-nanopub", "阅读14 语义标注与纳米出版",
               "自建纳米出版用例：断言 + 前提 + 方法与材料 + 支持证据。",
               CONTRACT_NANOPUB,
               """### 纳米出版（Nanopublication）

把本目录 `paper.pdf` 的核心结论拆成可独立引用的断言（assertion），
每条配 provenance（原文锚点）、premise（前提）与 por（方法/材料）。
断言只写论文明确支持的，不外推。""",
               gold_pdf, {"assertion_count_min": 2, "must_include": "1.8 BLEU"})

    write_case("p06-kg", "self-kg", "阅读15 文献知识图谱构建",
               "自建知识图谱用例：方法/数据集/指标实体 + uses/trained_on/evaluated_on 关系，含密度门槛。",
               CONTRACT_KG,
               """### 文献知识图谱

从本目录 `paper.pdf` 构建实体-关系图：方法、数据集、指标、任务为节点，
关系只取有原句支撑的 uses / trained_on / evaluated_on / outperforms。
每条边给 evidence（block + 原句）。图太稀疏请如实标 partial。""",
               gold_pdf, {"kg_must_have": ["fairseq", "WMT 2014", "BLEU"],
                          "min_edges": 10})

    write_case("p07-polish", "self-polish", "写作02 学术语言润色",
               "自建润色用例：长句、被动堆叠、断言强度与术语漂移，改写需保留数字与引用。",
               CONTRACT_POLISH,
               """### 学术润色

润色本目录 `paper.pdf` 的摘要与第 1 节：先给句级诊断（长句、被动、断言过强/过弱、术语不一致），
再给改写。数字（1.8 BLEU、10%、1.2x）与引用编号必须原样保留。""",
               gold_pdf, {"keep_numbers": ["1.8", "10%", "1.2x"], "keep_citations": ["[1]", "[2]", "[5]"]})

    write_case("p08-refs", "self-refs", "写作04 参考文献与引用管理",
               "自建引用核对用例：正文引用 [5] 无对应条目、条目 [4] 未被引用、[2] 与 [4] DOI 重复。",
               CONTRACT_REFS,
               """### 参考文献与引用核对

核对本目录 `paper.pdf` 的正文引用与文末列表：
找出「引了但没有条目」「有条目但没被引用」「重复条目」「编号缺口」，
并输出 GB/T 7714、APA、BibTeX 三种格式。缺失字段留空，不编造 DOI。""",
               gold_pdf, {"citations_without_entry": ["5"], "entries_never_cited": ["4"],
                          "duplicate_pair": ["2", "4"], "entries": 4,
                          "gbt_has_type_marker": True, "bibtex_has_inproceedings": True})

    write_case("p09-intro", "self-intro", "写作08 引言与相关工作写作",
               "自建引言用例：问题句、分组相关工作、空白句、贡献句，draft 骨架需由 agent 填写后才算完成。",
               CONTRACT_INTRO,
               """### 引言与相关工作

依据本目录 `paper.pdf` 写一节引言（含相关工作分组与空白陈述）。
每条事实性断言必须能回到原文块；引用只用参考文献表中存在的编号。
输出 `draft` 五段骨架并逐段填写，未填写的段落不得标记为完成。""",
               gold_pdf, {"draft_paragraphs": 5, "gap_min": 1, "contribution_min": 1})

    write_case("p10-methods", "self-methods", "写作09 方法与实验章节写作",
               "自建方法章用例：5 个超参可从原文取到，随机种子原文未报告（应进 missing 而非补默认值）。",
               CONTRACT_METHODS,
               """### 方法与实验章节

整理本目录 `paper.pdf` 的实验设置：超参数（学习率、批大小、dropout、头数、层数）、
数据集与规模、硬件、评价指标，并给可复现清单。
原文没报告的项（如随机种子）必须留空并列入 missing，不得用常见默认值填充。""",
               gold_pdf, {"hyperparameters": {"learning rate": "0.0003", "batch size": "32", "dropout": "0.1"},
                          "datasets": ["WMT 2014"], "hardware": "V100", "seeds_reported": False})

    write_case("p11-latex", "self-latex", "写作13 LaTeX 写作与编译",
               "自建 LaTeX 用例：正文含 & % _ 等需转义字符、booktabs 表格、公式环境与参考文献。",
               CONTRACT_LATEX,
               """### LaTeX 生成与编译

把本目录 `paper.pdf` 转成可编译的 LaTeX 工程：章节层级、booktabs 表格、
公式环境、thebibliography。若本机没有 TeX 引擎，请给出静态自检结果并说明未验证编译。""",
               gold_pdf, {"requires_files": ["main.tex"], "requires_static_check": True})

    enc = os.path.join(HERE, "_build_encrypted.pdf")
    make_encrypted(gold_pdf, enc)
    write_case("x01-encrypted", "self-ex-encrypted", "阅读01 文献文档解析",
               "自建异常用例：AES-256 加密 PDF（用户口令 user-secret），不可解析，应判 unable 而非崩溃。",
               CONTRACT_PARSE,
               """### 异常：加密 PDF

本目录 `paper.pdf` 已加密且未提供口令。请如实报告无法解析（`status: unable`），
写明原因与可人工接管的位置，不得编造任何正文内容。""",
               enc, {"expect_status": ["unable", "partial"], "must_not_have_text": True})

    img = os.path.join(HERE, "_build_imageonly.pdf")
    make_imageonly(gold_pdf, img)
    write_case("x02-imageonly", "self-ex-imageonly", "阅读01 文献文档解析",
               "自建异常用例：整页图片化（无文本层），检验 OCR 路径与 ocr_pages 标注。",
               CONTRACT_PARSE,
               """### 异常：无文本层（整页图片）

本目录 `paper.pdf` 的每一页都是图片，没有文本层。
请走 OCR 路径并在 `source.ocr_pages` 标注；OCR 置信度无法保证时在 `uncertainty` 说明。
如果没有 OCR 引擎，请判 `unable` 并说明缺什么。""",
               img, {"expect_ocr_or_unable": True})

    corrupt = os.path.join(HERE, "_build_corrupt.pdf")
    make_corrupt(corrupt)
    write_case("x03-corrupt", "self-ex-corrupt", "阅读01 文献文档解析",
               "自建异常用例：损坏 PDF（随机字节，无有效 xref），应判 unable 且仍写出 result.json。",
               CONTRACT_PARSE,
               """### 异常：损坏文件

本目录 `paper.pdf` 是损坏的 PDF。请捕获解析失败，输出 `status: unable` 与 `input.problem`，
仍然写出合法的 `result.json`，不要伪造文档结构。""",
               corrupt, {"expect_status": ["unable"], "result_must_exist": True})

    write_case("x04-nopdf", "self-ex-nopdf", "阅读01 文献文档解析",
               "自建异常用例：输入目录里没有任何 PDF，只有 case.json 与 task.md。",
               CONTRACT_PARSE,
               """### 异常：输入没有 PDF

本目录只有 `case.json` 和本说明，没有 `paper.pdf`。
请说明输入缺失并输出 `status: unable`，不要凭空生成内容。""",
               None, {"expect_status": ["unable"], "result_must_exist": True})

    zp = os.path.join(HERE, "_build_zeropage.pdf")
    make_zeropage(zp)
    write_case("x05-zeropage", "self-ex-zeropage", "阅读01 文献文档解析",
               "自建异常用例：零页 PDF（/Count 0），检验零提取判定与不崩溃。",
               CONTRACT_PARSE,
               """### 异常：零页 PDF

本目录 `paper.pdf` 声明 0 页。请说明无可解析页面并输出 `status: unable`，不崩溃。""",
               zp, {"expect_status": ["unable"], "result_must_exist": True})

    for tmp in (gold_pdf, twocol_pdf, enc, img, corrupt, zp):
        if os.path.exists(tmp):
            os.remove(tmp)

    print("cases written under", HERE)
    for name in sorted(os.listdir(HERE)):
        p = os.path.join(HERE, name)
        if os.path.isdir(p):
            n = len(os.listdir(p))
            print(f"  {name:20s} {n} files")


if __name__ == "__main__":
    main()
