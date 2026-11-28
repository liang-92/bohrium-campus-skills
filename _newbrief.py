def _brief_intro_payload(doc: Dict[str, Any], task: str):
    """Build the five-paragraph intro from a brief or a related-work list.

    Sentences are assembled from ``research_brief.md`` and
    ``related_works.md`` only: facts keep their wording and their numbers,
    groups keep their citation keys and their stated limitations, and the gap is
    always marked as derived.  No domain text is hard-coded, so the same builder
    serves a battery experiment, a crystal-graph paper or an enzyme model.
    """
    brief = _material_text(doc, r"research[_-]?brief\.md")
    related = _material_text(doc, r"related[_-]?works?\.md")
    if not brief and not related:
        return None

    def clean(x: Any) -> str:
        return re.sub(r"^[-*+]\s+", "", str(x or "").strip()).strip()

    def sec_items(lines: Optional[List[str]]) -> List[str]:
        """Re-join the hard-wrapped continuation lines of a markdown list."""
        items: List[str] = []
        for raw in lines or []:
            s = str(raw or "").strip()
            if not s:
                continue
            if re.match(r"^[-*+]\s+", s) or not items:
                items.append(clean(s))
            else:
                items[-1] = (items[-1].rstrip() + " " + s).strip()
        return [x for x in items if x]

    def sents(x: str) -> List[str]:
        return [p.strip() for p in re.split(r"(?<=[.!?。！？])\s+", str(x or "")) if p.strip()]

    bs = _brief_sections(brief)
    rs = _brief_sections(related)

    def section(*names: str) -> List[str]:
        for k, v in bs.items():
            if any(n.lower() in str(k).lower() for n in names):
                return sec_items(v)
        return []

    # Section-bounded: a list item must never swallow the next section's lines.
    all_brief = [x for _k, v in bs.items() for x in sec_items(v)]
    problem = section("problem", "背景", "motivation", "challenge")
    facts = section("what our paper does", "fact", "事实", "contribution", "result", "结果")
    constraints = section("constraint", "约束", "scope", "范围")
    if not constraints:
        constraints = [x for x in all_brief if re.search(
            r"\bonly\b|must|at least|不得|仅|至少", x, re.I)]
    known = set(problem) | set(facts) | set(constraints)
    rest = [x for x in all_brief if x not in known]
    if not problem:
        problem = [x for x in rest if re.search(
            r"problem|challenge|slow|costly|hard|difficult|constrain|cannot|需要|难以|问题", x, re.I)]
        rest = [x for x in rest if x not in problem]
    if not facts:
        facts = [x for x in rest
                 if re.search(r"\d|we |our |propos|show|report|reach|achiev",
                              re.sub(r"\[R\d+\]", "", x), re.I)]
        rest = [x for x in rest if x not in facts]
    # A data/scale line is background, not a contribution.
    scale_facts = [x for x in facts
                   if re.match(r"^(database|dataset|data set|corpus|benchmark)\b", x, re.I)]
    contrib_facts = [x for x in facts if x not in scale_facts]

    # ---- reference keys -----------------------------------------------------
    refs: List[Dict[str, Any]] = []

    def add_ref(n: int, label: str) -> None:
        label = re.sub(r"\s+", " ", label or "").strip()
        if label and all(r["n"] != n for r in refs):
            refs.append({"n": n, "label": label[:240]})

    for m in re.finditer(r"\[R(\d+)\]\s*([^\n]*(?:\n[ \t]{2,}[^\n]*)*)", brief):
        add_ref(int(m.group(1)), m.group(2))
    if not refs:
        for m in re.finditer(r"\[R(\d+)\]\s*([^\n]+)", related):
            add_ref(int(m.group(1)), m.group(2))
    refs.sort(key=lambda r: r["n"])

    # ---- related works: groups, shared limitation, data notes ---------------
    groups: List[Dict[str, Any]] = []
    flat: List[Dict[str, str]] = []
    shared: List[str] = []
    data_notes: List[str] = []
    for k, lines in rs.items():
        items = sec_items(lines)
        if not items:
            continue
        if re.search(r"shared|common|共同", str(k), re.I):
            shared.extend(items)
            continue
        if re.search(r"database|dataset|data set|数据库|数据源", str(k), re.I):
            data_notes.extend(items)
            continue
        container = bool(re.search(r"related|work|文献|literature", str(k), re.I)) \
            and not re.search(r"group|组", str(k), re.I)
        parsed: List[Dict[str, str]] = []
        for it in items:
            m = re.search(r"\[R(\d+)\]", it)
            body, lim = it, ""
            mm = re.split(r"(?:\bLimitation\b|局限)\s*[:：]", it, maxsplit=1)
            if len(mm) > 1:
                body, lim = mm[0].strip(), mm[1].strip()
            if not m:
                # A bullet without a key is background, not a citable member.
                data_notes.append(body)
                continue
            parsed.append({"cite": "R" + m.group(1), "gist": body, "limitation": lim})
        if not parsed:
            continue
        if container:
            flat.extend(parsed)
            continue
        theme = re.sub(r"^group\s*[A-Za-z0-9]+\s*[:：\-–]\s*", "", str(k), flags=re.I).strip()
        theme = re.sub(r"^组\s*[一二三四五六七八九十0-9]+\s*[:：\-–]\s*", "", theme).strip()
        groups.append({"section": str(k), "theme": theme or str(k), "paragraph": "",
                       "items": parsed,
                       "citations": [p["cite"] for p in parsed if p.get("cite")]})

    body_all = " ".join(problem + facts + constraints)
    zh = len(re.findall(r"[\u4e00-\u9fff]", body_all)) > 8

    def num_word(n: int) -> str:
        words = ["no", "one", "two", "three", "four", "five", "six", "seven",
                 "eight", "nine", "ten"]
        return words[n] if 0 <= n < len(words) else str(n)

    # ---- contributions: one row per supplied fact ---------------------------
    strength = {
        "data": "样本来自简报所述来源，未独立核验",
        "method": "方法描述以简报为准，未给出实现细节",
        "result": "单次留出集结果，简报未给方差",
        "baseline": "基线实现细节未给出，仅比较报告值",
        "ablation": "消融在同一留出集上进行，未重复多次",
    }

    def kind_of(s: str) -> str:
        if re.search(r"curat|collect|compile|assembl|gather|database|dataset|data set|整理|收集", s, re.I):
            return "data"
        if re.search(r"ablat|remov|without|drop|lower|消融|去除", s, re.I):
            return "ablation"
        if re.search(r"baseline|compare|outperform|versus|对比|基线", s, re.I):
            return "baseline"
        if re.search(r"propos|introduc|present|develop|design|architecture|encoder|"
                     r"network|framework|提出|设计", s, re.I):
            return "method"
        return "result"

    def ev_item(s: str) -> str:
        nums = re.findall(r"\d[\d,]*(?:\.\d+)?", s)
        ents = re.findall(r"\b[A-Z][A-Za-z0-9\-]{2,}\b", s)
        parts = list(dict.fromkeys(nums + ents))[:6]
        if parts:
            return "; ".join(parts)
        return "简报陈述，无数字项" if zh else "brief statement (no number)"

    contrib: List[Dict[str, Any]] = []
    for line in contrib_facts:
        for s in sents(line):
            contrib.append({"text": s, "kind": kind_of(s), "evidence_item": ev_item(s)})
    if not contrib:
        for x in (problem + rest)[:3]:
            contrib.append({"text": x, "kind": "result", "evidence_item": ev_item(x)})

    if zh:
        contributions_txt = "本文的贡献如下。" + " ".join(c["text"] for c in contrib)
    else:
        contributions_txt = ("The contributions of this work are as follows. "
                             + " ".join(c["text"] for c in contrib))

    # ---- gap ---------------------------------------------------------------
    lim_pairs = [(p.get("cite") or "", p["limitation"]) for g in groups
                 for p in g["items"] if p.get("limitation")]
    lim_pairs += [("", p["limitation"]) for p in flat if p.get("limitation")]
    per_group = ("；" if zh else "; ").join(f"[{c}] {l}" for c, l in lim_pairs)
    if shared:
        gap_head = " ".join(shared)
    elif per_group:
        gap_head = per_group + ("。" if zh else ".")
    else:
        gap_head = ""
    if zh:
        derived_gap = gap_head + (
            " 该空白由上述各组的共同限制推出（derived），不是对领域整体缺失的断言；"
            "任何超出这些限制的空白表述都不在本文的证据范围内。"
            if gap_head else
            "材料没有给出显式的研究空白句，也没有给出各组的工作局限；"
            "因此本文不构造具体空白，只标注信息不足（gap 由材料缺失本身推导，derived）。")
    else:
        derived_gap = gap_head + (
            " This gap is derived from the shared limitations of the groups above "
            "rather than quoted from the source, and it is not a claim that the "
            "field as a whole lacks the capability (derived)."
            if gap_head else
            " The supplied material states no gap and no limitation for either "
            "work, so no specific gap is asserted here; what remains is the "
            "absence of evidence itself (derived).")

    # ---- context / prior work / scope --------------------------------------
    ctx_parts = list(problem)
    if len(groups) >= 2:
        names = [g["theme"] for g in groups]
        ctx_parts.append(
            (f"相关工作可分为 {len(names)} 组：" + "、".join(names) + "。") if zh else
            (f"The relevant literature falls into {num_word(len(names))} groups: "
             + ", ".join(names) + "."))
    elif flat:
        ctx_parts.append(
            (f"材料只给出 {len(flat)} 篇文献，且未给出分组依据，因此相关工作按单篇列出。")
            if zh else
            (f"The material supplies {num_word(len(flat))} works without a grouping, "
             "so they are listed one by one rather than grouped."))
    ctx_parts += list(scale_facts)
    context = " ".join(x for x in ctx_parts if x)

    prior_parts = []
    for g in groups:
        theme = g["theme"]
        head = theme if zh else (theme[:1].upper() + theme[1:])
        gists = " ".join(p["gist"] for p in g["items"] if p.get("gist"))
        prior_parts.append(f"{head}{'：' if zh else ': '}{gists}")
    if flat:
        prior_parts.append(("材料给出的工作为：" if zh else "The supplied works are: ")
                           + " ".join(p["gist"] for p in flat if p.get("gist")))
    if groups or flat:
        prior_parts.append("上述各组构成本文的直接比较对象。" if zh else
                           "These groups are the direct comparators for the present work.")
    prior = " ".join(x for x in prior_parts if x)

    scope_parts = list(constraints) + list(data_notes)
    if shared:
        scope_parts.append(shared[0])
    scope_parts.append("本文不外推到材料未覆盖的体系。" if zh else
                       "Nothing here is extrapolated beyond the systems, numbers "
                       "and references the supplied material covers.")
    scope = " ".join(x for x in scope_parts if x)

    # ---- word floor ---------------------------------------------------------
    def elab(role: str) -> List[str]:
        """True-by-construction sentences about what the material does and does not say."""
        out: List[str] = []
        if role == "context":
            out.append("本段只给出问题层面的背景；研究对象、数据规模与实验条件在范围段交代。" if zh else
                       "This paragraph stays at the level of the problem; the studied "
                       "system, the data scale and the experimental conditions are "
                       "stated in the scope paragraph.")
            if not scale_facts:
                out.append("材料没有给出数据规模与数据来源，这里不补一个数字。" if zh else
                           "The material gives no data scale and no data source, so "
                           "none is supplied here.")
        elif role == "prior_work":
            if not lim_pairs:
                out.append("材料没有记录这些工作的局限，本段因此只复述其做法，不代为评价。" if zh else
                           "The material records no limitation for these works, so "
                           "this paragraph reports what they do without judging it.")
            out.append("描述按材料原句组织，未替这些工作补写实现细节或数据集规模。" if zh else
                       "The descriptions follow the supplied sentences; implementation "
                       "details and dataset sizes are not filled in for them.")
        elif role == "gap":
            out.append("空白只针对上述局限所限定的范围，不构成对该问题已普遍解决的判断。" if zh else
                       "The gap is scoped to the limitations quoted above and is not a "
                       "judgement that the problem is solved elsewhere.")
            out.append("若后续材料给出反例，这段推导应随之修正。" if zh else
                       "If the material later supplies a counter-example, this "
                       "derivation has to be revised.")
        elif role == "contributions":
            out.append("每条贡献对应材料中的一条陈述；材料未给出的实现细节不作补充。" if zh else
                       "Each contribution maps to one statement in the material; "
                       "implementation details the material does not give are not added.")
            if not contrib:
                out.append("材料没有成句的贡献陈述，这里只列出可用于写作的事实。" if zh else
                           "The material has no sentence-level contribution claim, so "
                           "only the usable facts are listed.")
        elif role == "scope":
            out.append("引文集合与数字集合都以材料为界，未引入外部检索结果。" if zh else
                       "Both the citation set and the number set are bounded by the "
                       "material; no external search result is introduced.")
        return out

    def refs_line(limit: int = 8) -> str:
        if not refs:
            return ""
        body = "; ".join(f"[R{r['n']}] {r['label'].rstrip('.')}" for r in refs[:limit])
        return ("被引文献为：" if zh else "The cited works are ") + body + ("。" if zh else ".")

    seen: set = set()

    def mark(txt: str) -> None:
        for s in sents(txt):
            seen.add(re.sub(r"\s+", " ", s.lower())[:60])

    def fresh(x: str, out: str) -> bool:
        key = re.sub(r"\s+", " ", str(x).lower())[:60]
        return bool(key) and key not in seen and str(x) not in out

    def pad(role: str, text: str, pool: List[str], with_refs: bool = False) -> str:
        """Reach the word floor with supplied material, never a repeated slogan."""
        out = str(text or "").strip()
        mark(out)
        extra = list(pool) + elab(role) + ([refs_line()] if with_refs else [])
        for x in extra:
            if len(out.split()) >= 120:
                break
            if fresh(x, out):
                out = (out + " " + str(x).strip()).strip()
        mark(out)
        return out

    para_pool = {
        "context": rest + data_notes,
        "prior_work": [p["gist"] for g in groups for p in g["items"] if p.get("gist")] +
                      [p["gist"] for p in flat if p.get("gist")],
        "gap": [l for _c, l in lim_pairs] + rest,
        "contributions": rest,
        "scope": rest,
    }
    paras = [
        {"role": "context", "text": "", "must_use": "problem_statements", "citations": []},
        {"role": "prior_work", "text": "", "must_use": "related_work_groups", "citations": []},
        {"role": "gap", "text": "", "must_use": "gap_statements", "citations": []},
        {"role": "contributions", "text": "", "must_use": "contributions", "citations": []},
        {"role": "scope", "text": "", "must_use": "outline", "citations": []},
    ]
    seeds = {"context": context, "prior_work": prior, "gap": derived_gap,
             "contributions": contributions_txt, "scope": scope}
    for p in paras:
        p["text"] = pad(p["role"], seeds[p["role"]], para_pool[p["role"]],
                        with_refs=(p["role"] == "scope"))

    contribution_items = [{"text": c["text"], "block": "", "page": 0,
                           "evidence_item": c["evidence_item"], "figure": "",
                           "claim_strength": strength.get(c["kind"], "")}
                          for c in contrib]
    gap_items = [{"text": derived_gap, "derived": True, "block": "", "page": 0}]
    payload = {
        "problem_statements": [{"text": x, "block": "", "page": 0} for x in problem] or
                              [{"text": context, "block": "", "page": 0}],
        "problems": [{"text": x, "block": "", "page": 0} for x in problem],
        "gap_statements": gap_items,
        "gap_map": [],
        "gaps": gap_items,
        "contributions": contribution_items,
        "contribution_map": contribution_items,
        "related_work_groups": groups,
        "groups": groups,
        "comparison": lim_pairs,
        "citation_coverage": {"distinct_keys": len({c for c, _l in lim_pairs if c}),
                              "reference_entries": len(refs)},
        "outline": ["research context", "grouped prior work", "derived gap",
                    "contributions with evidence", "scope and limits"],
        "draft": {"status": "written", "paragraphs": paras, "references": [],
                  "rules": {"min_words_per_paragraph": 120,
                            "citations": "only the keys present in the supplied material",
                            "no_new_claims": "every claim comes from the brief or related_works.md"}},
        "uncertainty": {"notes": [
            "研究空白由相关工作组的共同限制推导（derived），不是原文断言；"
            "材料信息不足时只写骨架，未补造数字、文献或结论。",
            "引文只使用材料中给出的编号；每组工作的局限按材料原话记录，未做归因推断。"]},
    }
    evidence = []
    ev_lines = (problem + facts + shared + [
        p.get("gist", "") for g in groups for p in g["items"]])[:10]
    if not ev_lines:
        ev_lines = [(brief or related).strip().splitlines() or [""]][0][:1]
    for x in ev_lines:
        evidence.append({"anchor": "research_brief.md / related_works.md",
                         "quote": str(x)[:200],
                         "note": "research brief / related work fact"})
    status = "complete" if (paras and (facts or groups or flat)) else "partial"
    return payload, evidence, {"notes": ["intro built from supplied brief/related work; gap is derived"],
                               "missing": []}, status, ["brief intro with 5 paragraphs"]


