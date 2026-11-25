"""Build an independent local test set for the ten paper-* skills.

Why this file exists: the only way to score a parser is to own the ground truth.
Every PDF here is generated from the text in this file, so the expected answer is
known before the skill runs -- no guessing, no "looks about right".

Design notes
------------
* Reading cases target the failure modes named by the rubric (multi-column order,
  merged header cells, cross-page continuation, scan without a text layer).
* Writing cases are text-only on purpose: nine of the ten official topics hand
  the agent prose/bib/tex/csv, not a PDF.
* Two contract shapes are exercised:
    flat   ``output_contract: {field: type, ...}``      (what the runtime
           contract describes: "all original output_contract fields")
    nested ``output_contract: {result_json: {required_fields: [...]}, ...}``
  A skill that only understands one of them is only half-compatible.

Run:  python _eval/make_cases.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from spec import DELIVERABLES  # noqa: E402

CASES = os.path.join(HERE, "cases")

# Half the set gets the machine-readable contract shape (`required_fields` +
# `required_files`); the other half only names its deliverables in task.md.
# Comparing the two groups separates "was not told" from "was told and ignored".
NESTED = {"B_R03_translate", "C_R10_notes", "D_R14_nanopub",
          "F_W02_polish", "J_W13_latex", "K_R01_span"}

PAGE_W, PAGE_H = 612.0, 792.0
BODY_SIZE = 8.8
LEAD = 11.4


# --------------------------------------------------------------------------- #
# tiny text layout engine (enough for a two-column paper)
# --------------------------------------------------------------------------- #
def wrap(text, font, size, width):
    """Greedy wrap using the real font metrics, so lines fit the column."""
    import pymupdf

    words, lines, cur = text.split(), [], ""
    for w in words:
        probe = w if not cur else cur + " " + w
        if pymupdf.get_text_length(probe, fontname=font, fontsize=size) <= width:
            cur = probe
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def put_block(page, text, rect, font="tiro", size=BODY_SIZE, align=0, color=(0, 0, 0)):
    """Insert wrapped text at the top of *rect*; return the y it ended at."""
    import pymupdf

    x0, y0, x1, y1 = rect
    lines = wrap(text, font, size, x1 - x0)
    y = y0 + size
    for ln in lines:
        if y > y1:
            break
        page.insert_text((x0, y), ln, fontname=font, fontsize=size,
                         color=color, render_mode=0)
        y += size * 1.3
    return y


def heading(page, text, rect, size=11.0, bold=True):
    import pymupdf

    page.insert_text((rect[0], rect[1] + size), text,
                     fontname="hebo" if bold else "tiro", fontsize=size)
    return rect[1] + size * 1.6


def para_height(text, width, size=BODY_SIZE):
    return len(wrap(text, "tiro", size, width)) * size * 1.3


# --------------------------------------------------------------------------- #
# case 1: two columns + full-width table + run-in abstract
# --------------------------------------------------------------------------- #
A1_BODY = [
    ("1 Introduction", [
        "Concentrated aqueous electrolytes control the structure of the electric "
        "double layer, and that structure in turn sets the interfacial capacitance "
        "measured in every electrochemical experiment. Continuum models reproduce "
        "the capacitance curve only after the ion distribution is fitted, which "
        "hides rather than explains the underlying physics.",
        "Machine-learning potentials trained on first-principles trajectories offer "
        "a way out: they keep the accuracy of the reference method while reaching "
        "the nanoseconds needed for a converged interfacial average. The open "
        "question is whether such a potential transfers across salt concentrations "
        "without being refitted for each one.",
    ]),
    ("2 Methods", [
        "We trained a neural network potential on 4,200 configurations sampled from "
        "ab initio molecular dynamics of NaCl solutions at three concentrations. "
        "The training set was split by configuration, never by frame, so that "
        "correlated snapshots cannot leak across the split.",
        "Error bars come from block averaging over five independent trajectories. "
        "Reported capacitance values are referenced to the potential of zero charge "
        "and carry a standard deviation of 0.4 microfarads per square centimetre.",
    ]),
    ("2.1 System setup", [
        "Each cell contained 512 water molecules and the salt pair required for the "
        "target concentration. Production runs lasted 2 ns after 200 ps of "
        "equilibration in the isothermal-isobaric ensemble at 298 K and 1 bar.",
    ]),
]

A1_BODY2 = [
    ("3 Results", [
        "The potential reproduces the experimental capacitance within 0.9 percent at "
        "0.5 mol/L and within 2.1 percent at the highest concentration studied. The "
        "ion-oxygen radial distribution function develops a sharp first peak whose "
        "height grows monotonically with concentration.",
        # a display equation, numbered on the right like a real paper
        "C = dQ / dV = eps eps0 A / d        (1)",
    ]),
    ("3.1 Interfacial structure", [
        "Contact pairing replaces solvent-separated pairing as concentration rises. "
        "The first coordination shell contracts from 4.1 to 2.6 angstroms over the "
        "same range, and the layer of oriented water at the surface thins by a "
        "third. These two changes together account for most of the capacitance rise.",
    ]),
    ("4 Discussion", [
        "The remaining discrepancy at high concentration tracks the known "
        "over-polarisation of the water model, not a failure of the potential. A "
        "polarisable water model would likely close the gap, at roughly four times "
        "the cost per timestep.",
    ]),
    ("5 Conclusion", [
        "A single machine-learning potential, trained once, reproduces the "
        "interfacial capacitance of aqueous NaCl across a threefold range of "
        "concentration. The structural origin of the rise is contact pairing, not a "
        "change in dielectric response.",
    ]),
]

A1_REFS = [
    "[1] Sample Author A., Example Author B. First-principles study of ion pairing "
    "in aqueous NaCl solutions at high concentration. Synth. J. Interface Sci., "
    "2022, 8(2): 101-114.",
    "[2] Fixture Author C., Model Author D. Ab initio molecular dynamics of "
    "oxide-water interfaces with machine-learned potentials. Synth. Phys. Chem., "
    "2021, 44(7): 2201-2218.",
    "[3] Descriptor Author E. et al. A local descriptor for machine-learning "
    "interatomic potentials in the condensed phase. Synth. Comput. Mater., 2023, "
    "9(1): 44-59.",
]

A1_TABLE_HEADER = [["Concentration", "(mol/L)"],
                   ["Contact layer", "thickness (A)"],
                   ["Interfacial", "capacitance", "(uF cm-2)"]]
A1_TABLE_ROWS = [["0.5", "4.1", "18.3"], ["1.5", "3.2", "23.7"], ["3.0", "2.6", "29.4"]]


def build_a1(path):
    """Two-column paper: run-in abstract, full-width table, three 2-line refs."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    _running_head(page, "Synthetic test data / not a real publication")

    y = 58.0
    page.insert_text((50, y), "Interfacial capacitance of concentrated aqueous",
                     fontname="hebo", fontsize=15)
    page.insert_text((50, y + 18), "electrolytes from a transferable potential",
                     fontname="hebo", fontsize=15)
    page.insert_text((50, y + 40), "Sample Author A, Example Author B, Fixture Author C",
                     fontname="tiro", fontsize=9.5)
    page.insert_text((50, y + 54), "Synthetic Institute of Interface Science",
                     fontname="tiro", fontsize=8.5)

    # Run-in abstract: same size as body, glued to the first sentence.  A
    # font-size-only heading detector cannot see it, which is the point.
    put_block(page, "Abstract The structure and dynamics of concentrated aqueous "
                    "electrolytes are resolved with a machine-learning potential "
                    "trained once on first-principles data. The potential reproduces "
                    "the measured capacitance across a threefold concentration range "
                    "and identifies contact ion pairing as the structural origin of "
                    "the rise.",
              (50, y + 66, 562, y + 120))
    page.insert_text((50, y + 128),
                     "Keywords: machine-learning potential; electrolyte interface; "
                     "capacitance; contact pairing",
                     fontname="tiro", fontsize=7.6)

    # two columns
    col_l = (50.0, 190.0, 296.0, 470.0)
    col_r = (316.0, 190.0, 562.0, 470.0)
    _flow_columns(page, A1_BODY, [col_l, col_r])

    # full-width table at the bottom of page 1: 3 columns x 4 rows with a
    # three-line header, plus a data cell that reads exactly "3.0"
    _table(page, 50, 500, 562, A1_TABLE_HEADER, A1_TABLE_ROWS,
           caption="Table 1. Interfacial metrics extracted from 20 ns trajectories "
                   "at 298 K.")
    _footer(page, 1)

    # page 2
    p2 = doc.new_page(width=PAGE_W, height=PAGE_H)
    _running_head(p2, "Synthetic test data / not a real publication")
    _flow_columns(p2, A1_BODY2, [(50.0, 60.0, 296.0, 640.0), (316.0, 60.0, 562.0, 640.0)])

    y = 660.0
    p2.insert_text((50, y), "References", fontname="hebo", fontsize=11)
    y += 16
    for r in A1_REFS:
        y = put_block(p2, r, (50, y, 562, y + 60), size=8.0) + 6

    _footer(p2, 2)
    doc.save(path)
    doc.close()


def _running_head(page, text):
    page.insert_text((50, 34), text, fontname="tiro", fontsize=7.5, color=(.45, .45, .45))


def _footer(page, n):
    page.insert_text((PAGE_W / 2 - 4, PAGE_H - 30), str(n), fontname="tiro", fontsize=9)


def _flow_columns(page, content, cols):
    """Pour (heading, [paragraph...]) into columns, moving right then down."""
    ci, y = 0, cols[0][1]
    for head, paras in content:
        items = [(head, True)] + [(p, False) for p in paras]
        for text, is_head in items:
            size = 11.0 if is_head else BODY_SIZE
            need = (size * 1.6 if is_head else para_height(text, cols[ci][2] - cols[ci][0])) + 4
            x0, _, x1, y1 = cols[ci]
            if y + need > y1:
                ci += 1
                if ci >= len(cols):
                    return
                y = cols[ci][1]
                x0, _, x1, y1 = cols[ci]
            if is_head:
                y = heading(page, text, (x0, y, x1, y1), size=size)
            else:
                y = put_block(page, text, (x0, y, x1, y1)) + 4


def _table(page, x0, y0, x1, header, rows, caption="", row_h=15.0):
    """Draw a ruled table.  Header cells contain real line breaks."""
    ncol = len(header)
    colw = (x1 - x0) / ncol
    if caption:
        put_block(page, caption, (x0, y0, x1, y0 + 24), size=8.0)
        y0 += 26
    hh = max(len(c) for c in header) * 9.5 + 4
    y = y0
    page.draw_rect(pymupdf_rect(x0, y, x1, y + hh), color=(0, 0, 0), width=0.6)
    for i, cell in enumerate(header):
        cy = y + 9.0
        for part in cell:
            page.insert_text((x0 + i * colw + 3, cy), part, fontname="tiro", fontsize=7.8)
            cy += 9.0
    y += hh
    for r in rows:
        page.draw_rect(pymupdf_rect(x0, y, x1, y + row_h), color=(0, 0, 0), width=0.6)
        for i, cell in enumerate(r):
            page.insert_text((x0 + i * colw + 3, y + 10), cell,
                             fontname="tiro", fontsize=7.8)
        y += row_h
    for i in range(1, ncol):
        page.draw_line((x0 + i * colw, y0), (x0 + i * colw, y), color=(0, 0, 0), width=0.6)


def pymupdf_rect(x0, y0, x1, y1):
    import pymupdf
    return pymupdf.Rect(x0, y0, x1, y1)


# --------------------------------------------------------------------------- #
# case 2: a table that continues onto the next page
# --------------------------------------------------------------------------- #
def build_a2(path):
    """One table split by a page break; the continuation repeats the header."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    _running_head(page, "Synthetic test data / not a real publication")
    page.insert_text((50, 70), "Ablation study with a table that spans pages",
                     fontname="hebo", fontsize=14)
    put_block(page, "Section 1 lists every ablation condition. The table is long "
                    "enough to be broken by the page boundary, as printed tables "
                    "often are.",
              (50, 90, 562, 130))
    header = [["Run"], ["Layers"], ["Width"], ["Accuracy"], ["Notes"]]
    rows = [[f"R{i:02d}", str(4 + i % 3), str(256 * (1 + i % 2)),
             f"{81 + i * 0.37:.2f}", "single seed"] for i in range(1, 13)]
    _table(page, 50, 150, 562, header, rows, caption="Table 1. Ablation grid.")
    _footer(page, 1)

    p2 = doc.new_page(width=PAGE_W, height=PAGE_H)
    _running_head(p2, "Synthetic test data / not a real publication")
    p2.insert_text((50, 60), "Table 1 (continued)", fontname="tiro", fontsize=8.0)
    rows2 = [[f"R{i:02d}", str(4 + i % 3), str(256 * (1 + i % 2)),
              f"{81 + i * 0.37:.2f}", "three seeds"] for i in range(13, 25)]
    _table(p2, 50, 70, 562, header, rows2)
    _footer(p2, 2)
    doc.save(path)
    doc.close()


# --------------------------------------------------------------------------- #
# case 3: a scan with no text layer at all
# --------------------------------------------------------------------------- #
def build_a3(path):
    """Raster-only page: the honest answer is 'no text layer', not 'complete'."""
    import pymupdf

    tmp = pymupdf.open()
    p = tmp.new_page(width=PAGE_W, height=PAGE_H)
    p.insert_text((60, 90), "Scanned page without a text layer", fontname="hebo", fontsize=16)
    y = 120
    for line in [
        "This page exists only as pixels.  There is no text object to extract,",
        "which is exactly the situation a scanned thesis page creates.",
        "",
        "A parser that reports success here is guessing.  A parser that says",
        "'no text layer, OCR unavailable, unable to read' is telling the truth.",
    ]:
        p.insert_text((60, y), line, fontname="tiro", fontsize=11)
        y += 18
    pix = p.get_pixmap(dpi=140)
    tmp.close()

    out = pymupdf.open()
    pg = out.new_page(width=PAGE_W, height=PAGE_H)
    pg.insert_image(pymupdf_rect(0, 0, PAGE_W, PAGE_H), pixmap=pix)
    out.save(path)
    out.close()


# --------------------------------------------------------------------------- #
# writing / reading text cases
# --------------------------------------------------------------------------- #
def w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def contract_flat(fields, enum=("success", "partial", "unable")):
    out = {}
    for name, spec in fields.items():
        out[name] = spec
    out.setdefault("case_id", "string")
    out["status"] = {"type": "string", "enum": list(enum)}
    return out


FLAT_READ = {
    "main_result": "object",
    "evidence": "array",
    "uncertainty": "object",
    "change_log": "array",
}
FLAT_WRITE = {
    "deliverables": "array",
    "fact_source_map": "array",
    "version_boundary": "object",
    "change_log": "array",
}


def make_case(root, name, skill, task_md, files, contract, expected, challenge=""):
    d = os.path.join(CASES, name)
    os.makedirs(d, exist_ok=True)
    case = {
        "case_id": name,
        "challenge_id": challenge,
        "case_name": name,
        "task": "见同目录 task.md",
        "input_files": [{"path": f"input/{f}", "type": f.rsplit('.', 1)[-1]}
                        for f in files if os.path.exists(os.path.join(d, "input", f))],
        "output_contract": contract,
        "evaluation_budget": {"max_model_requests": 64, "max_seconds": 900,
                             "max_response_tokens": 16384},
    }
    w(os.path.join(d, "case.json"), json.dumps(case, ensure_ascii=False, indent=2))
    w(os.path.join(d, "task.md"), task_md)
    expected["skill"] = skill
    w(os.path.join(d, "expected.json"), json.dumps(expected, ensure_ascii=False, indent=2))
    return d


def build_text_cases():
    # ---- R03 translate: 5 numbered paragraphs + a locked glossary ----------
    d = os.path.join(CASES, "B_R03_translate")
    abs_en = "\n\n".join([
        "P01 Solid-state electrolytes based on cubic garnet phases conduct lithium "
        "ions at room temperature, which makes them candidates for cells that "
        "cannot leak a liquid.",
        "P02 The conductivity depends strongly on the sintering temperature, and "
        "the dependence is not monotonic: above 1150 C grain growth competes with "
        "densification.",
        "P03 Interfacial resistance, not bulk conductivity, limits the cell. A "
        "0.1 ohm cm2 interface can dominate a 1 mm electrolyte.",
        "P04 Dendrite penetration was observed in only two of the forty cells, "
        "both sintered below 1100 C.",
        "P05 We therefore do not claim that the electrolyte suppresses dendrites; "
        "we claim only that it did so in our conditions.",
    ])
    w(os.path.join(d, "input/abstract_en.md"), abs_en)
    w(os.path.join(d, "input/glossary.csv"),
      "term,preferred_zh,note\n"
      "solid-state electrolyte,固态电解质,must not be 固体电解质\n"
      "garnet,石榴石,phase name\n"
      "grain growth,晶粒长大,\n"
      "interfacial resistance,界面电阻,\n"
      "dendrite,枝晶,\n")
    w(os.path.join(d, "input/style_guide.md"),
      "# 格式\n- 段落编号 P01-P05 必须保留\n- 数字与单位逐字保留\n- 术语表译名不得替换\n")
    make_case(
        d, "B_R03_translate", "paper-translate",
        "# 摘要翻译\n\n把 `input/abstract_en.md` 逐段译成中文，保留 P01–P05 编号，"
        "术语按 `input/glossary.csv` 锁定。\n\n必须交付双语对照与术语执行表，"
        "结论段（P05）的限定强度不得加强。\n",
        ["abstract_en.md", "glossary.csv", "style_guide.md"],
        contract_flat(FLAT_READ),
        {"expect": {"task": "R03", "paragraphs": 5,
                    "glossary_terms": ["固态电解质", "石榴石", "晶粒长大", "界面电阻", "枝晶"],
                    "must_keep": ["P01", "P05", "1150", "0.1", "40"]}},
        "product-arena-01-5a9928c1")

    # ---- R10 notes --------------------------------------------------------
    w(os.path.join(d := os.path.join(CASES, "C_R10_notes"), "input/paper.md"),
      "# Retrieval-augmented generation for scientific tables\n\n"
      "## Abstract\nWe test whether retrieval helps a language model read numeric "
      "tables. Retrieval improves exact-match accuracy from 41% to 58%.\n\n"
      "## 1 Introduction\nTables carry most of the quantitative content of a paper, "
      "yet models read them as flat text.\n\n"
      "## 2 Method\nWe index each table by its caption and header row, then retrieve "
      "the top three candidates per question.\n\n"
      "## 3 Results\nRetrieval helps on wide tables (more than 6 columns) and does "
      "not help on narrow ones.\n\n"
      "## 4 Limitations\nAll tables are from a single publisher; the layout "
      "distribution is narrow.\n")
    make_case(
        d, "C_R10_notes", "paper-notes",
        "# 章节摘要与提纲\n\n读 `input/paper.md`，按原有章节输出摘要与提纲。\n\n"
        "每节摘要不超过 80 字，必须保留关键数字（41%、58%、6 列）。\n",
        ["paper.md"], contract_flat(FLAT_READ),
        {"expect": {"task": "R10", "sections": ["Abstract", "1 Introduction",
                                                "2 Method", "3 Results",
                                                "4 Limitations"],
                    "must_keep": ["41%", "58%", "6"]}})

    # ---- R14 nanopublication ---------------------------------------------
    w(os.path.join(d := os.path.join(CASES, "D_R14_nanopub"), "input/paragraph.md"),
      "Cubic garnet electrolytes conduct lithium ions at room temperature, and the "
      "conductivity rises with sintering temperature up to 1150 C because grain "
      "growth reduces grain-boundary resistance. Dendrites were observed in two of "
      "forty cells, both sintered below 1100 C. Taken together, these results mean "
      "the material is ready for commercial cells.\n")
    w(os.path.join(d, "input/nanopub_schema.json"),
      json.dumps({"assertion": {"subject": "string", "predicate": "string",
                                "object": "string"},
                  "provenance": {"source": "string", "quote": "string"},
                  "evidence_level": ["direct", "indirect", "insufficient"]},
                 ensure_ascii=False, indent=2))
    make_case(
        d, "D_R14_nanopub", "paper-nanopub",
        "# 断言拆解\n\n把 `input/paragraph.md` 拆成原子断言，每条带原文引用。\n\n"
        "注意：段落里有因果（because）与频率（two of forty），因果不得升级为必然，"
        "样本量必须保留。证据不足的断言要标 `insufficient`。\n",
        ["paragraph.md", "nanopub_schema.json"], contract_flat(FLAT_READ),
        {"expect": {"task": "R14", "min_assertions": 3,
                    "must_flag": ["insufficient"],
                    "must_keep": ["two of forty", "1150", "1100"]}})

    # ---- R15 knowledge graph ---------------------------------------------
    w(os.path.join(d := os.path.join(CASES, "E_R15_kg"), "input/papers.md"),
      "## Paper 1\nChen et al. report that garnet electrolytes reach 1 mS/cm at 25 C. "
      "The same group later showed that barium doping raises this to 1.4 mS/cm.\n\n"
      "## Paper 2\nLi and co-workers argue that interfacial resistance, not bulk "
      "conductivity, limits the cell. They measure 0.1 ohm cm2 for a gold blocking "
      "electrode.\n\n"
      "## Paper 3\nA review by Okafor collects 40 cells and finds dendrites in two, "
      "both sintered below 1100 C.\n")
    make_case(
        d, "E_R15_kg", "paper-kg",
        "# 实体与关系\n\n从 `input/papers.md` 抽实体（材料、性质、方法、机构）与关系，"
        "导出 `entities.csv` 与 `type_summary.md`。\n\n"
        "要求：实体带原文锚点；关系不得把「相关」写成「导致」；"
        "同名不同人（Chen / Li）不得合并。\n",
        ["papers.md"], contract_flat(FLAT_READ),
        {"expect": {"task": "R15", "min_entities": 6,
                    "must_keep": ["garnet", "1.4", "0.1", "1100"]}})

    # ---- W02 polish -------------------------------------------------------
    w(os.path.join(d := os.path.join(CASES, "F_W02_polish"), "input/draft.md"),
      "# Draft\n\n"
      "The results is very significant and proves that our method is the best. "
      "We used a machine learning potential, and the machine-learning potential was "
      "trained on 4200 configurations. Machine learning potentials is accurate. "
      "The capacitance increase is caused by contact pairing in all cases.\n")
    w(os.path.join(d, "input/style_guide.md"),
      "# 规则\n- 只改语言，不加事实\n- 术语统一为 machine-learning potential\n"
      "- 不得把 may/indicate 改成 proves\n- 不得把 in our conditions 删掉\n")
    make_case(
        d, "F_W02_polish", "paper-polish",
        "# 最小编辑润色\n\n修 `input/draft.md` 的语法与术语漂移，输出 `revised.md` 与 "
        "`changes.csv`（原句/改句/理由）。\n\n"
        "硬性要求：不得新增材料外事实；`proves` 这类过度断言必须收敛；"
        "术语 `machine learning potential` / `machine-learning potential` 要统一。\n",
        ["draft.md", "style_guide.md"], contract_flat(FLAT_WRITE),
        {"expect": {"task": "W02",
                    "must_not_contain": ["proves", "the best"],
                    "must_keep": ["4200"],
                    "min_changes": 3}})

    # ---- W04 references ---------------------------------------------------
    w(os.path.join(d := os.path.join(CASES, "G_W04_refs"), "input/manuscript.md"),
      "# Manuscript\n\nGarnet electrolytes reach 1 mS/cm at room temperature. "
      "Interfacial resistance often limits the cell. Dendrites remain contested. "
      "Sintering above 1150 C improves density.\n")
    w(os.path.join(d, "input/references.md"),
      "1. Chen et al. (2021). Garnet electrolytes: conductivity revisited. "
      "J. Power Sources 480: 229-240. doi:10.1000/j.jpowsour.2021.229240\n"
      "2. Li & Okafor (2022). Interfacial resistance in solid cells. "
      "Solid State Ionics 377: 115-121.\n"
      "3. Okafor (2023). Dendrite penetration: a review of 40 cells. "
      "Adv. Energy Mater. 13: 2200-2210.\n"
      "4. Sample (2019). A study of garnet electrolytes. Journal of Results 4: 1-9.\n"
      "5. Fixture (2020). Sintering of oxides. Materials Letters 260: 126-130.\n")
    make_case(
        d, "G_W04_refs", "paper-refs",
        "# 句级引用插入\n\n给 `input/manuscript.md` 的每个论断配引用，"
        "从 `input/references.md` 里选，输出插入引用后的稿件与位置表。\n\n"
        "硬性要求：不得引用不存在的文献；每条引用要能指回参考文献条目；"
        "题录里的卷号/页码不得改动。\n",
        ["manuscript.md", "references.md"], contract_flat(FLAT_WRITE),
        {"expect": {"task": "W04", "min_citations": 3,
                    "must_keep": ["Chen", "Li", "Okafor"],
                    "must_not_invent": True}})

    # ---- W08 intro --------------------------------------------------------
    w(os.path.join(d := os.path.join(CASES, "H_W08_intro"), "input/research_brief.md"),
      "# Brief\n\nWe study garnet solid electrolytes for room-temperature cells. "
      "Gap: reports disagree on whether interfacial resistance or bulk conductivity "
      "limits performance, and the disagreement tracks sintering temperature.\n")
    w(os.path.join(d, "input/related_works.md"),
      "## Group A: bulk conductivity\n"
      "- Chen 2021: 1.0 mS/cm at 25 C for cubic garnet.\n"
      "- Chen 2022: 1.4 mS/cm after barium doping.\n"
      "## Group B: interface limited\n"
      "- Li 2022: 0.1 ohm cm2 interface dominates a 1 mm cell.\n"
      "- Okafor 2023: dendrites in 2 of 40 cells, both below 1100 C.\n")
    make_case(
        d, "H_W08_intro", "paper-intro",
        "# 引言与相关工作\n\n依据 `research_brief.md` 与 `related_works.md` 写引言，"
        "相关工作按两组比较，最后从分歧推出研究空白。\n\n"
        "硬性要求：引用 4 篇全部覆盖；数字逐字保留；不得新增材料外文献。\n",
        ["research_brief.md", "related_works.md"], contract_flat(FLAT_WRITE),
        {"expect": {"task": "W08", "min_citations": 4,
                    "must_keep": ["1.0", "1.4", "0.1", "40"]}})

    # ---- W09 methods ------------------------------------------------------
    w(os.path.join(d := os.path.join(CASES, "I_W09_methods"), "input/experiment_log.md"),
      "# Log (unsorted)\n\n"
      "09:12 started sintering, setpoint 1150 C, ramp 3 C/min\n"
      "10:40 furnace actually read 1140 C, adjusted +10\n"
      "11:05 pellet A removed, density 96.1%\n"
      "13:20 pellet B removed, density 94.8%\n"
      "notes: two pellets, same powder batch, binder 2 wt%\n"
      "14:00 EIS run, 1 MHz to 0.1 Hz, 100 mV amplitude\n"
      "error: sample B cracked during mounting, EIS repeated on A only\n"
      "annotation: setpoint logged as 1150 but controller offset +10 -> true 1160\n")
    make_case(
        d, "I_W09_methods", "paper-methods",
        "# 方法与实验\n\n把 `input/experiment_log.md` 整理成可执行步骤与参数表。\n\n"
        "硬性要求：日志里的设定值 1150 与控制器实际 1160 的冲突必须显式处理，"
        "不得取一个数了事；pellet B 开裂导致的数据缺口要写出来。\n",
        ["experiment_log.md"], contract_flat(FLAT_WRITE),
        {"expect": {"task": "W09", "min_steps": 4,
                    "must_keep": ["1150", "1160", "96.1", "94.8"],
                    "must_flag": ["cracked"]}})

    # ---- W13 latex --------------------------------------------------------
    d = os.path.join(CASES, "J_W13_latex")
    w(os.path.join(d, "input/project/main.tex"), r"""\documentclass[11pt]{article}
\usepackage{natbib}
\bibliographystyle{plain}
\title{Sintering of cubic garnet electrolytes}
\author{Sample Author}
\begin{document}
\maketitle
\section{Introduction}
Garnet electrolytes reach 1\,mS/cm at room temperature \cite{chen2021}.
Interfacial resistance often limits the cell \citep{li2022}.
\begin{equation}
  \sigma = \frac{L}{R A}
\end{equation}
\section{Results}
Dendrites were observed in two of forty cells \cite{okafor2023}.
See Table~\ref{tab:ablation} and Section~\ref{sec:res}.
\section{Results}
\label{sec:res}
\begin{table}[h]
\centering
\begin{tabular}{lllllllll}
Run & Layers & Width & Acc & Seed & Time & GPU & Mem & Notes \\
R01 & 4 & 256 & 81.00 & 1 & 10 & A & 8 & ok \\
\end{tabular}
\caption{Ablation.}
\label{tab:ablation}
\end{table}
\bibliography{refs}
\end{document}
""")
    w(os.path.join(d, "input/project/refs.bib"), """@article{chen2021,
  author = {Chen, A.}, title = {Garnet electrolytes: conductivity revisited},
  journal = {J. Power Sources}, year = {2021}, volume = {480}, pages = {229--240}}
@article{okafor2023,
  author = {Okafor, B.}, title = {Dendrite penetration: a review},
  journal = {Adv. Energy Mater.}, year = {2023}, volume = {13}, pages = {2200--2210}}
""")
    w(os.path.join(d, "input/toolchain.md"),
      "# 可用工具链\n- pdflatex, bibtex 可用\n- 不允许联网\n- 编译两次 + bibtex 一次\n")
    make_case(
        d, "J_W13_latex", "paper-latex",
        "# LaTeX 修复与编译\n\n`input/project/` 是一个编译不过的工程。\n\n"
        "要求：复制原工程做**最小修改**，修到 0 error、无未定义引用。\n\n"
        "硬性规则：不得重写正文、不得删内容绕过错误、不得留 `[TODO]`；"
        "列出「问题→行号→根因→改动」的修复报告。\n",
        ["project/main.tex", "project/refs.bib", "toolchain.md"],
        contract_flat(FLAT_WRITE),
        {"expect": {"task": "W13",
                    "must_fix": ["amsmath", "li2022", "duplicate_label"],
                    "must_keep_body": ["Sintering of cubic garnet electrolytes",
                                       "two of forty"],
                    "must_not": ["[TODO]"]}})

    return d


def to_nested(name):
    """Rewrite one case's flat contract into the nested shape + required_files."""
    p = os.path.join(CASES, name, "case.json")
    case = json.load(open(p, encoding="utf-8"))
    flat = case["output_contract"]
    fields = [k for k in flat]
    enum = (flat.get("status") or {}).get("enum") if isinstance(
        flat.get("status"), dict) else None
    task = json.load(open(os.path.join(CASES, name, "expected.json"),
                          encoding="utf-8"))["expect"]["task"]
    case["output_contract"] = {
        "result_json": {
            "required_fields": fields,
            "status_enum": enum or ["success", "partial", "unable"],
            "evidence_item": {"anchor": "页码/章节/段落/表号/单元格",
                              "quote": "原文逐字片段", "note": "判定依据"},
        },
        "rules": ["main_result 覆盖任务要求的全部要素，不得用通用摘要替代",
                  "evidence 逐条可回到原文位置",
                  "status 为 partial 时必须在 uncertainty 中写明缺口"],
        "required_files": ["result.json"] + DELIVERABLES.get(task, []),
    }
    w(p, json.dumps(case, ensure_ascii=False, indent=2))


def main():
    if os.path.isdir(CASES):
        shutil.rmtree(CASES)
    os.makedirs(CASES, exist_ok=True)
    pdf_dir = os.path.join(CASES, "A_R01_parse")
    os.makedirs(os.path.join(pdf_dir, "input"), exist_ok=True)
    build_a1(os.path.join(pdf_dir, "input", "paper.pdf"))
    make_case(
        pdf_dir, "A_R01_parse", "paper-parse",
        "# 双栏论文解析\n\n解析 `input/paper.pdf`，输出章节树、正文块、表 1 与参考文献。\n\n"
        "要求：双栏顺序不得串栏；行内摘要 `Abstract ...` 与 `Keywords:` 要作为独立章节；"
        "表 1 的三行表头要还原成一个单元格；参考文献按 `[n]` 计数。\n",
        ["paper.pdf"], contract_flat(FLAT_READ),
        {"expect": {
            "task": "R01",
            "title_contains": "Interfacial capacitance",
            "sections": ["Abstract", "1 Introduction", "2 Methods", "2.1 System setup",
                         "3 Results", "3.1 Interfacial structure", "4 Discussion",
                         "5 Conclusion", "References"],
            "table": {"rows": 3, "cols": 3,
                      "header_cells": ["Concentration", "Contact layer", "Interfacial"]},
            "references": 3,
            "equations": 1,
            "must_keep": ["4.1 to 2.6", "0.9 percent"],
        }})

    span_dir = os.path.join(CASES, "K_R01_span")
    os.makedirs(os.path.join(span_dir, "input"), exist_ok=True)
    build_a2(os.path.join(span_dir, "input", "paper.pdf"))
    make_case(
        span_dir, "K_R01_span", "paper-parse",
        "# 跨页续表\n\n解析 `input/paper.pdf`。表 1 被分页切断，第二页重复了表头。\n\n"
        "要求：合并成一张表，续页的重复表头不得当成数据行；总数据行数应为 24。\n",
        ["paper.pdf"], contract_flat(FLAT_READ),
        {"expect": {"task": "R01", "table": {"rows": 24, "cols": 5,
                                             "merged_pages": True},
                    "must_keep": ["R01", "R24"]}})

    scan_dir = os.path.join(CASES, "L_R01_scan")
    os.makedirs(os.path.join(scan_dir, "input"), exist_ok=True)
    build_a3(os.path.join(scan_dir, "input", "paper.pdf"))
    make_case(
        scan_dir, "L_R01_scan", "paper-parse",
        "# 无文字层扫描页\n\n解析 `input/paper.pdf`。这一页只有像素，没有文字层。\n\n"
        "期望行为：如实报告「没有文字层」，status 为 `partial` 或 `unable`，"
        "不得声称成功解析出正文。\n",
        ["paper.pdf"], contract_flat(FLAT_READ),
        {"expect": {"task": "R01", "honesty_only": True,
                    "forbid_status": ["success"]}})

    build_text_cases()
    for n in NESTED:
        to_nested(n)
    names = sorted(os.listdir(CASES))
    print(f"{len(names)} cases -> {CASES}")
    for n in names:
        files = sum(len(f) for _, _, f in os.walk(os.path.join(CASES, n)))
        print(f"  {n:22s} {files} files")


if __name__ == "__main__":
    main()
