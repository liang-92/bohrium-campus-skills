"""Convert this workspace's real WorkBuddy session log into Playground's
conversation-record JSONL (format 2: one {"role","content"} object per line).

Nothing is invented: text comes from the actual session file, tool calls become
short labels, and long tool outputs are truncated with an explicit marker.

    python3 tools/make_trace.py --session <session.jsonl> --out trace.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

SKIP_MARKERS = ("<system-reminder", "<user_info>", "<identity_context>", "<project_context>")


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    parts = []
    if isinstance(content, list):
        for b in content:
            if not isinstance(b, dict):
                continue
            t = b.get("type")
            if t in {"input_text", "text", "output_text"}:
                s = b.get("text", "")
                if s:
                    parts.append(s)
            elif t == "tool_use":
                name = b.get("name", "tool")
                inp = b.get("input") or {}
                brief = ""
                if isinstance(inp, dict):
                    for k in ("command", "description", "file_path", "path", "query", "url"):
                        if k in inp and isinstance(inp[k], str):
                            brief = inp[k][:160].replace("\n", " ")
                            break
                parts.append(f"[tool_use] {name}: {brief}")
            elif t == "tool_result":
                c = b.get("content")
                s = text_of(c) if not isinstance(c, str) else c
                s = re.sub(r"\s+", " ", s or "")[:400]
                parts.append(f"[tool_result] {s}")
    return "\n".join(p for p in parts if p)


def clean(s: str) -> str:
    if any(m in s[:400] for m in SKIP_MARKERS):
        # keep the human's actual words after the reminder block
        s = re.sub(r"<system-reminder.*?</system-reminder>", "", s, flags=re.S)
        s = re.sub(r"<user_info>.*?</user_info>", "", s, flags=re.S)
        s = re.sub(r"<identity_context>.*?</identity_context>", "", s, flags=re.S)
        s = re.sub(r"<project_context>.*?</project_context>", "", s, flags=re.S)
        s = re.sub(r"<[^>]{1,40}>", "", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-chars", type=int, default=1600)
    args = ap.parse_args()

    rows = []
    with open(args.session, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            rtype = rec.get("type")
            if rtype == "function_call":
                name = rec.get("name") or (rec.get("function") or {}).get("name") or "tool"
                raw = rec.get("arguments") or (rec.get("function") or {}).get("arguments") or ""
                brief = re.sub(r"\s+", " ", str(raw))[:400]
                rows.append({"role": "assistant", "content": f"[tool_use] {name}: {brief}"})
                continue
            if rtype == "function_call_result":
                out = rec.get("output") or rec.get("result") or rec.get("content") or ""
                if isinstance(out, (dict, list)):
                    out = json.dumps(out, ensure_ascii=False)
                brief = re.sub(r"\s+", " ", str(out))[:400]
                rows.append({"role": "tool", "content": f"[tool_result] {brief}"})
                continue
            if rtype == "reasoning":
                txt = clean(text_of(rec.get("content") or rec.get("text") or ""))
                if txt:
                    rows.append({"role": "assistant", "content": "[reasoning] " + txt[:600]})
                continue
            if rtype != "message":
                continue
            role = rec.get("role") or "assistant"
            if role not in {"user", "assistant", "system", "tool"}:
                role = "assistant"
            text = clean(text_of(rec.get("content")))
            if not text:
                continue
            if len(text) > args.max_chars:
                text = text[: args.max_chars] + f"\n…[truncated {len(text) - args.max_chars} chars]"
            rows.append({"role": role, "content": text})

    with open(args.out, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    size = os.path.getsize(args.out)
    roles = {}
    for r in rows:
        roles[r["role"]] = roles.get(r["role"], 0) + 1
    print(json.dumps({"out": args.out, "messages": len(rows), "bytes": size, "roles": roles}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
