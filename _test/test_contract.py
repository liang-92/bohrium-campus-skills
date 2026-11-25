"""Contract-filling unit checks: shapes, verbatim keys, type conformance.

Run:  python _test/test_contract.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "core"))

from paperkit import contract  # noqa: E402
from paperkit import result as pk_result  # noqa: E402

DOC = {
    "document": {
        "meta": {"title": "T", "authors": ["A"], "abstract": "abs", "keywords": [], "doi": ""},
        "sections": [{"level": 1, "title": "Intro", "page": 1, "block": "p01-b001"}],
        "blocks": [{"id": "p01-b001", "page": 1, "type": "body", "text": "hello world"}],
        "tables": [{"id": "t1", "page": 1, "caption": "Table 1"}],
        "figures": [], "formulas": [], "references": [{"n": 1, "text": "ref"}],
        "page_stats": [{"page": 1, "chars": 11}],
        "source": {"pages": 1, "backend": "pymupdf", "name": "x.pdf", "sha256": "ab"},
        "quality": {"blocks": 1},
    },
    "quality": {"blocks": 1, "chars": 11},
}
PAYLOAD = {"document": {"title": "T", "pages": 1}, "structure": [{"title": "Intro"}]}

CASES = []


def check(name, ok, detail=""):
    CASES.append((name, ok, detail))


def spec_of(contract_obj):
    return contract.spec({"output_contract": contract_obj})


def fill(contract_obj, payload=None):
    fields = spec_of(contract_obj)
    return contract.adapt(payload if payload is not None else PAYLOAD, fields, DOC,
                          evidence=[{"block": "p01-b001"}], status="partial")


# 1. key names are verbatim, whatever shape the contract arrives in
shapes = [
    ({"full_text_blocks": "list"}, ["full_text_blocks"]),
    ({"tables": {"type": "array", "items": {"type": "object"}}}, ["tables"]),
    ({"sections": [{"level": 1}]}, ["sections"]),
    ([{"name": "figures", "type": "array"}], ["figures"]),
    ({"my Own-Key.v2": "whatever"}, ["my Own-Key.v2"]),
]
for obj, want in shapes:
    body, _, _ = fill(obj)
    check(f"verbatim keys {want}", list(body) == want, str(list(body)))

# 2. declared type is respected
body, st, _ = fill({"tables": "list", "paper_metadata": "title/authors/abstract",
                    "status": "complete|partial|unable", "paragraph_count": "number"})
check("list -> array", isinstance(body["tables"], list), type(body["tables"]).__name__)
check("title/authors/abstract -> object", isinstance(body["paper_metadata"], dict),
      st["paper_metadata"])
check("no type_mismatch on paper_metadata", not st["paper_metadata"].get("type_mismatch"),
      st["paper_metadata"])
check("enum field gets run status", body["status"] in {"complete", "partial", "unable"},
      body["status"])

# 3. semantic routing is *recorded*, never silent
body, st, _ = fill({"equations": "list", "citations": "list", "coverage_report": "object"})
check("equations -> formulas", st["equations"]["method"] == "alias:formulas", st["equations"])
check("citations -> references", st["citations"]["method"] == "alias:references", st["citations"])
check("coverage_report -> quality", st["coverage_report"]["method"] == "alias:quality",
      st["coverage_report"])

# 4. unknown field: key kept, honestly unsupported, still type-correct
body, st, _ = fill({"something_never_seen": "?", "weird_list": "list"})
check("unknown keeps key", "something_never_seen" in body)
check("unknown says unsupported", body["something_never_seen"]["method"] == "unsupported",
      body["something_never_seen"])
check("unknown list gets []", body["weird_list"]["value"] == [], body["weird_list"])

# 5. extras never leak into the contract body
body, _, leftover = fill({"tables": "list"})
check("no unasked keys in body", set(body) == {"tables"}, list(body))
check("leftover keeps composer slices", "structure" in leftover, list(leftover))

# 6. empty slice is an honest answer, not a hole
body, st, _ = fill({"figures": "list"})
check("empty figures stays []", body["figures"] == [], body["figures"])
check("empty figures not unsupported", st["figures"]["method"] != "unsupported", st["figures"])

# 7. no contract at all -> payload is the result, no crash
r = contract.spec({"case_id": "x"})
check("null contract -> no fields", r == [], r)

# 8. exact payload key wins and is not overwritten by a slice
body, st, _ = fill({"document": "full structure"})
check("document exact", st["document"]["method"] == "exact", st["document"])
check("document value is composer's", body["document"]["title"] == "T", body["document"])

# 9. result validation enforces the declaration instead of only recording mismatches
def validate_body(contract_obj, body):
    return pk_result.validate_result(
        {"case_id": "types", "status": "partial", "evidence": [],
         "output_contract": body}, DOC, case={"output_contract": contract_obj})


r = validate_body({"paragraph_count": {"type": "number"}}, {"paragraph_count": "many"})
check("validator rejects a string in a numeric field", not r["ok"], r)

r = validate_body({"tables": {"type": "array"}}, {"tables": {"not": "a list"}})
check("validator rejects an object in an array field", not r["ok"], r)

r = validate_body({"status": {"type": "string", "enum": ["complete", "partial"]}},
                  {"status": "done"})
check("validator rejects a value outside the declared enum", not r["ok"], r)

r = validate_body({"weird_list": "list"},
                  {"weird_list": {"value": [], "method": "unsupported", "confidence": 0}})
check("unsupported wrapper is checked by its typed empty value", r["ok"], r)

r = pk_result.validate_result(
    {"case_id": "types", "status": "partial", "evidence": [],
     "output_contract": "not an object"}, DOC, case={"output_contract": {"tables": "list"}})
check("output_contract itself must be an object", not r["ok"], r)

bad = [c for c in CASES if not c[1]]
for name, ok, detail in CASES:
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"   <- {detail}"))
print(json.dumps({"total": len(CASES), "failed": len(bad)}, ensure_ascii=False))
sys.exit(1 if bad else 0)
