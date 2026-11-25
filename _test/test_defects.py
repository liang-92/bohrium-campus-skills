"""Exception-path checks: garbled fonts, out-of-order pagination, image tables.

These three are rubric-named failure modes that produce *plausible-looking* wrong
output rather than a crash, so they need their own tests.  Synthetic page dicts
are enough -- no PDF, no engine, deterministic.

Run:  python _test/test_defects.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "core"))

from paperkit import document  # noqa: E402

CASES = []


def check(name, ok, detail=""):
    CASES.append((name, ok, detail))


def page(n, text, y=100.0, images=(), h=800.0):
    return {"number": n, "width": 600.0, "height": h, "chars": len(text),
            "images": list(images),
            "lines": [{"text": text, "bbox": [72, y, 300, y + 12]}]}


# --- 1. a font without toUnicode: PUA code points are not text -------------
bad = page(1, "\ue001\ue002\ue003\ue004" * 5)
good = page(2, "ordinary paper text that carries real characters")
g = document.garbled_pages([bad, good])
check("PUA chars counted", g["pua_chars"] == 20, g)
check("PUA page flagged", g["pages"] == [1], g)
check("clean page not flagged", 2 not in g["pages"], g)
check("no PUA -> zero", document.garbled_pages([good])["pua_chars"] == 0)

# --- 2. printed page numbers out of order ---------------------------------
def numbered(nums, h=800.0):
    out = []
    for i, n in enumerate(nums, 1):
        text = str(n) if n is not None else "body text"
        out.append({"number": i, "width": 600.0, "height": h, "chars": len(text),
                    "images": [], "lines": [{"text": text, "bbox": [290, h - 60, 310, h - 48]}]})
    return out


ok_order = document.page_order(numbered([1, 2, 3, 4]))
check("monotonic pages -> no warning", not ok_order["warning"], ok_order)
check("monotonic pages counted", ok_order["found"] == 4, ok_order)

swapped = document.page_order(numbered([1, 3, 2, 4]))
check("swapped pages -> warning", swapped["warning"], swapped)
check("swapped pages -> break recorded", (3, 2) in swapped["breaks"], swapped)

dupes = document.page_order(numbered([1, 1, 2, 3]))
check("duplicate page numbers reported", dupes["duplicates"] == [1], dupes)

none_at_all = document.page_order(numbered([None, None, None]))
check("no printed numbers -> no warning", not none_at_all["warning"], none_at_all)

# --- 3. a table that exists only as a picture ------------------------------
tbl_page = {"number": 7, "width": 600.0, "height": 800.0, "chars": 20,
            "images": [[100, 300, 500, 500]],
            "lines": [{"text": "Table 3: Results on the test set.",
                       "bbox": [100, 510, 400, 522]}]}
blocks = [{"id": "p07-b001", "page": 7, "text": "Table 3: Results on the test set.",
           "bbox": [100, 510, 400, 522]}]
hits = document.find_image_tables([tbl_page], blocks, tables=[])
check("image-only table detected", len(hits) == 1, hits)
check("image table keeps its page", hits and hits[0]["page"] == 7, hits)

covered = document.find_image_tables(
    [tbl_page], blocks, tables=[{"page": 7, "bbox": [100, 280, 500, 505]}])
check("extracted table is not double-reported", covered == [], covered)

no_image = document.find_image_tables(
    [dict(tbl_page, images=[])], blocks, tables=[])
check("no image -> no image-table claim", no_image == [], no_image)


# --- 4. nothing to read: the input itself is wrong -------------------------
# The harness mounts the case at a fixed path; a typo there used to crash before
# result.json existed, which is strictly worse than an honest "unable".
import shutil      # noqa: E402
import tempfile    # noqa: E402

from paperkit import sources  # noqa: E402

tmp = tempfile.mkdtemp(prefix="pk_noinput_")
try:
    miss = sources.discover(os.path.join(tmp, "nope"))
    check("missing dir -> missing_input",
          (miss.get("problem") or {}).get("kind") == "missing_input", miss.get("problem"))

    empty = os.path.join(tmp, "empty")
    os.makedirs(empty)
    check("empty dir -> empty",
          (sources.discover(empty).get("problem") or {}).get("kind") == "empty")

    # A task file is an instruction, not material.  Since text inputs became
    # readable the kind widened from "no pdf" to "no material"; an
    # instructions-only directory now claims no problem on purpose, because a
    # writing Skill may legitimately be driven by task.md alone.  What a parse
    # Skill needs to be able to trust is that nothing was picked as material.
    only_txt = os.path.join(tmp, "only_txt")
    os.makedirs(only_txt)
    with open(os.path.join(only_txt, "task.md"), "w", encoding="utf-8") as fh:
        fh.write("read this\n")
    only = sources.discover(only_txt)
    check("instructions only -> no pdf selected", only.get("primary_pdf") is None, only.get("problem"))
    check("instructions only -> no text material selected",
          only.get("primary_text") is None, only.get("primary_text"))
    check("instructions only -> not called empty",
          (only.get("problem") or {}).get("kind") != "empty", only.get("problem"))

    # An image is a file we can see but not read: this is the case where the
    # reason must be stated, and it must say how many files it looked at.
    only_png = os.path.join(tmp, "only_png")
    os.makedirs(only_png)
    with open(os.path.join(only_png, "scan.png"), "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
    prob = sources.discover(only_png).get("problem") or {}
    check("unreadable file -> no_material", prob.get("kind") == "no_material", prob)
    check("reason names the file count",
          "1 file" in (prob.get("detail") or "").replace("file(s)", "file"), prob)

    with_pdf = os.path.join(tmp, "with_pdf")
    os.makedirs(with_pdf)
    with open(os.path.join(with_pdf, "p.pdf"), "wb") as fh:
        fh.write(b"%PDF-1.4\n")
    check("a real pdf -> no problem claimed",
          sources.discover(with_pdf).get("problem") is None)

    # An unparsed document must not make the composer raise: the caller needs a
    # result.json even when there is nothing in it.
    import compose_all  # noqa: E402
    payload, ev, unc, status, notes = compose_all.build(
        "parse", {"document": None, "input": {"problem": {"kind": "missing_input",
                                                           "detail": "x"}}}, {}, "")
    check("composer survives a null document", payload == {} and ev == [], payload)
    check("null document -> unable", status == "unable", status)
    check("null document still explains itself",
          any("no document" in n for n in unc.get("notes", [])), unc)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

bad = [c for c in CASES if not c[1]]
for name, ok, detail in CASES:
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"   <- {detail}"))
print({"total": len(CASES), "failed": len(bad)})
sys.exit(1 if bad else 0)
