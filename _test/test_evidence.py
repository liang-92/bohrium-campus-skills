"""Evidence checks: is a quote really a quote, and does an anchor resolve?

The earlier rule graded a quote by token overlap (>= 0.8 passed).  That answers
"are these mostly the same words", not "is this what the paper says": swapping
`dog` for `cat` in a ten-word sentence still scored 0.89.  These tests pin the
stricter contract, including the cases the strict rule must still accept (a
quote truncated with `…`, a passage split across two blocks).

Run:  python _test/test_evidence.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "core"))

from paperkit import evidence as evd  # noqa: E402
from paperkit import result as pk_result  # noqa: E402

CASES = []


def check(name, ok, detail=""):
    CASES.append((name, ok, detail))


DOC = {
    "document": {
        "blocks": [
            {"id": "p01-b001", "page": 1, "text":
                "We trained the model on eight GPUs for twelve hours and the "
                "dog barked at the postman every morning."},
            {"id": "p01-b002", "page": 1, "text":
                "The encoder stacks six identical layers. Each layer has two "
                "sub-layers."},
            {"id": "p02-b001", "page": 2, "text":
                "Continued from the previous page, the decoder mirrors the "
                "encoder."},
        ],
        "tables": [{"id": "t01", "page": 1, "caption": "Table 1: BLEU scores.",
                    "caption_block": "p01-b009"}],
    }
}

DOC["document"]["blocks"].append(
    {"id": "p01-b009", "page": 1, "text": "Table 1: BLEU scores."})


def v(block, quote):
    return evd.verify(DOC, block, quote)


# --- 1. the honest positive cases -------------------------------------------

r = v("p01-b001", "we trained the model on eight gpus")
check("verbatim (case-folded) passes", r["ok"] and r["exact"], r)

r = v("p01-b001", "the  dog barked   at the postman")
check("whitespace differences pass", r["ok"], r)

r = v("p01-b002", "The encoder stacks six identical layers. Each layer has two sub-layers.")
check("a full block passes", r["ok"], r)

r = v("p01-b001", "We trained the model on eight GPUs for twelve hours and the…")
check("a quote truncated with … passes", r["ok"], r)

r = v("p01-b001", "We trained the model … the dog barked at the postman")
check("an elision between two verbatim fragments passes", r["ok"], r)

r = v("p01-b001", "")
check("an empty quote only asserts the block exists", r["ok"] and not r["exact"], r)


# --- 2. the negatives the old 80% rule let through --------------------------

r = v("p01-b001", "We trained the model on eight GPUs for twelve hours and the "
                  "cat barked at the postman every morning.")
check("one swapped word fails", not r["ok"], r)
check("the failure names where it diverges", "cat" in r["reason"], r)

r = v("p01-b002", "The encoder stacks seven identical layers. Each layer has two sub-layers.")
check("one swapped number fails", not r["ok"], r)

r = v("p01-b001", "We trained the model on eight GPUs for twelve hours and the "
                  "Elephant barked at the postman every morning.")
check("a paraphrase fails", not r["ok"], r)

r = v("p01-b001", "We trained the model on eight GPUs … the elephant barked at the postman")
check("an elision cannot hide a wrong fragment", not r["ok"], r)

r = v("p01-b001", "the dog barked … We trained the model")
check("elided fragments must keep their original order", not r["ok"], r)

r = v("p01-b001", "zz … yy")
check("short invented fragments cannot hide behind an elision", not r["ok"], r)

r = v("p01-b001", "twelve hours and the dog barked")
check("a substring of the block passes even mid-sentence", r["ok"], r)


# --- 3. anchors: one block, or a span of them -------------------------------

r = v("p01-b002+p02-b001", "sub-layers. … continued from the previous page")
check("a `a+b` span resolves and verifies", r["ok"], r)

r = v("p01-b002+p02-b001", "sub-layers. continued from the previous page")
check("a span joins its blocks with a space, not a newline", r["ok"], r)

r = v("p01-b002+p99-b999", "sub-layers")
check("a span with a missing component fails", not r["ok"], r)
check("the missing component is named", "p99-b999" in r["reason"], r)

r = v("p99-b999", "anything")
check("an unknown single block fails", not r["ok"], r)

r = v("p01-b009", "Table 1: BLEU scores.")
check("a table caption block verifies like any other block", r["ok"], r)

check("components() splits only on +", evd.components("a+b") == ["a", "b"]
      and evd.components("a") == ["a"], evd.components("a+b"))


# --- 4. the validator uses the same resolution ------------------------------

def validate(ev_items, status="complete"):
    res = {"case_id": "t", "status": status, "evidence": ev_items,
           "output_contract": {"entries": [], "status": status},
           "uncertainty": {"notes": [], "missing": []}}
    return pk_result.validate_result(res, DOC, case={})


r = validate([{"block": "p01-b001", "quote": "the dog barked at the postman"}])
check("validator accepts a verbatim quote", r["ok"], r)

r = validate([{"block": "p01-b002+p02-b001", "quote": "sub-layers. continued"}])
check("validator accepts a span anchor", r["ok"], r)

r = validate([{"block": "p01-b001", "quote": "the cat barked at the postman"}])
check("validator rejects a doctored quote", not r["ok"], r)
check("the rejection is a quote problem, not an unknown block",
      r["ok"] is False and "unknown block" not in " ".join(r["problems"]), r)

r = validate([{"block": "p01-b002+p99-b999", "quote": "sub-layers"}])
check("validator rejects a span with a missing block", not r["ok"], r)

r = validate([{"table": "t01", "page": 1, "quote": "Table 1: BLEU scores."}])
check("validator accepts a table-only anchor", r["ok"], r)

r = validate([{"table": "t99", "page": 1}])
check("validator rejects an unknown table", not r["ok"], r)

empty_tables = {"document": {"blocks": DOC["document"]["blocks"], "tables": []}}
r = pk_result.validate_result(
    {"case_id": "t", "status": "partial", "evidence": [{"table": "t99"}],
     "output_contract": {}}, empty_tables, case={})
check("an unknown table is invalid even when the document has no tables", not r["ok"], r)

r = validate([{"table": "t01", "page": 1, "quote": "Table 1: invented scores."}])
check("validator rejects a doctored table-caption quote", not r["ok"], r)

r = validate([{"quote": "unanchored"}])
check("validator rejects an unanchored quote", not r["ok"], r)


# --- 5. no fuzzy scoring left anywhere -------------------------------------

r = v("p01-b001", "completely unrelated words about a different paper entirely")
check("unrelated text fails", not r["ok"], r)
check("no similarity score is reported as a reason",
      "overlap" not in r["reason"].lower(), r)


bad = [c for c in CASES if not c[1]]
for name, ok, detail in CASES:
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"   <- {detail}"))
print({"total": len(CASES), "failed": len(bad)})
sys.exit(1 if bad else 0)
