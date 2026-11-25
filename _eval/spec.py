"""Shared grading spec: what each topic is asked to hand over.

Kept out of ``case.json`` so the skill cannot read its own answer sheet -- it has
to learn these from ``task.md`` (group 1) or from ``required_files`` (group 2).
"""

DELIVERABLES = {
    "R01": ["structure.md", "body.md", "refs.md"],
    "R03": ["bilingual_parallel.md", "terms_used.csv"],
    "R10": ["section_summary.md", "outline.md"],
    "R14": ["nanopubs.json", "decomposition.md"],
    "R15": ["entities.csv", "type_summary.md"],
    "W02": ["revised.md", "changes.csv"],
    "W04": ["manuscript_cited.md", "citation_placement.csv"],
    "W08": ["background.md", "citation_map.csv"],
    "W09": ["methods.md", "materials_equipment.csv"],
    "W13": ["main.tex", "fix_report.md"],
}

DELIVERABLE_ALIASES = {
    "structure.md": ["structure.md", "sections.md", "outline.md", "structure.json"],
    "body.md": ["body.md", "fulltext.md", "full_text.md", "body.txt"],
    "refs.md": ["refs.md", "references.md", "refs.json", "references.json"],
    "bilingual_parallel.md": ["bilingual_parallel.md", "bilingual.md", "parallel.md"],
    "terms_used.csv": ["terms_used.csv", "glossary_used.csv", "terms.csv"],
    "section_summary.md": ["section_summary.md", "summary.md", "notes.md"],
    "outline.md": ["outline.md", "structure.md"],
    "nanopubs.json": ["nanopubs.json", "nanopub.json", "nanopublications.json"],
    "decomposition.md": ["decomposition.md", "decompose.md", "assertions.md"],
    "entities.csv": ["entities.csv", "entity.csv", "graph_nodes.csv"],
    "type_summary.md": ["type_summary.md", "types.md", "summary.md"],
    "revised.md": ["revised.md", "draft_revised.md", "polished.md"],
    "changes.csv": ["changes.csv", "edits.csv", "change_log.csv"],
    "manuscript_cited.md": ["manuscript_cited.md", "cited.md", "manuscript.md"],
    "citation_placement.csv": ["citation_placement.csv", "citations.csv", "cite_map.csv"],
    "background.md": ["background.md", "intro.md", "introduction.md"],
    "citation_map.csv": ["citation_map.csv", "citations.csv"],
    "methods.md": ["methods.md", "method.md", "methods_section.md"],
    "materials_equipment.csv": ["materials_equipment.csv", "materials.csv", "params.csv"],
    "main.tex": ["main.tex", "project/main.tex"],
    "fix_report.md": ["fix_report.md", "fixes.md", "repair_report.md"],
}

# Keys inside output_contract that describe the contract rather than answer it.
META_KEYS = {"rules", "required_files", "result_json", "notes",
             "status_enum", "evidence_item", "case_id_type"}
