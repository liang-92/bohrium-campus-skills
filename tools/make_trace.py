"""Turn this workspace's real WorkBuddy session log into a Playground trace.

Two output formats:

    --format arm           typed-step JSONL (ARM trace-step v1, the richest form)
    --format conversation  {"role","content"} per line (format 2, the simple form)

Nothing is invented. Every field comes from the session file:

    step_type      from the record type (reasoning -> thought, function_call -> tool_call, ...)
    timestamp      the record's own epoch-ms stamp, converted to ISO-8601
    tool_call_id   the record's `callId`, so tool_call/tool_result genuinely pair
    cost_usd       `providerData.rawUsage.credit`, the platform's own per-request charge
    tokens         `providerData.usage.totalTokens`
    body/output    the record's text, truncated with an explicit marker

The typed form exists because the platform's admission gate looks for concrete
signals (paired tool calls, a declared cost, a moving timeline). A chat-style
transcript carries none of them, so it enters scoring on a single weak signal.

    python3 tools/make_trace.py --session <session.jsonl> --out trace/steps.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone

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
        s = re.sub(r"<system-reminder.*?</system-reminder>", "", s, flags=re.S)
        s = re.sub(r"<user_info>.*?</user_info>", "", s, flags=re.S)
        s = re.sub(r"<identity_context>.*?</identity_context>", "", s, flags=re.S)
        s = re.sub(r"<project_context>.*?</project_context>", "", s, flags=re.S)
        s = re.sub(r"<[^>]{1,40}>", "", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def iso(ms) -> str | None:
    try:
        return datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc) \
            .strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(float(ms)) % 1000:03d}Z"
    except Exception:
        return None


def clip(s: str, limit: int) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    if len(s) <= limit:
        return s
    return s[:limit] + f"…[truncated {len(s) - limit} chars]"


def as_args(raw):
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else {"value": val}
    except Exception:
        return {"raw": clip(raw, 300)}


def arm_steps(records, max_chars: int):
    steps = []
    order = 0

    def add(step):
        nonlocal order
        order += 1
        step["step_order"] = order
        steps.append(step)

    for rec in records:
        rtype = rec.get("type")
        pd = rec.get("providerData") or {}
        ts = iso(rec.get("timestamp"))
        usage = pd.get("usage") or {}
        credit = (pd.get("rawUsage") or {}).get("credit")
        cost = float(credit) if isinstance(credit, (int, float)) else None
        tokens = usage.get("totalTokens") if isinstance(usage, dict) else None

        base = {}
        if ts:
            base["timestamp"] = ts
        if cost:
            base["cost_usd"] = cost
        if isinstance(tokens, int) and tokens > 0:
            base["tokens"] = tokens

        if rtype == "function_call":
            name = rec.get("name") or (rec.get("function") or {}).get("name") or "tool"
            raw = rec.get("arguments") or (rec.get("function") or {}).get("arguments") or {}
            args = as_args(raw)
            brief = ""
            for k in ("command", "description", "file_path", "path", "query", "url", "prompt"):
                if isinstance(args.get(k), str):
                    brief = args[k]
                    break
            add({"step_type": "tool_call", "title": name,
                 "tool_name": name,
                 "tool_call_id": rec.get("callId") or rec.get("id"),
                 "tool_args": args,
                 "body": clip(brief, max_chars), **base})
            continue

        if rtype == "function_call_result":
            out = rec.get("output")
            if out is None:
                out = rec.get("result") or rec.get("content") or ""
            if isinstance(out, dict) and "text" in out:
                out = out["text"]
            elif isinstance(out, (dict, list)):
                out = json.dumps(out, ensure_ascii=False)
            status = rec.get("status")
            add({"step_type": "tool_result",
                 "title": rec.get("name") or "tool",
                 "tool_call_id": rec.get("callId") or rec.get("id"),
                 "tool_output": clip(str(out), max_chars),
                 "body": clip(f"status={status}" if status else "", 120), **base})
            continue

        if rtype == "reasoning":
            txt = clean(text_of(rec.get("content") or rec.get("text") or pd.get("reasoning") or ""))
            if txt:
                add({"step_type": "thought", "title": "reasoning",
                     "body": clip(txt, max_chars), **base})
            continue

        if rtype == "message":
            role = rec.get("role") or "assistant"
            txt = clean(text_of(rec.get("content")))
            if not txt:
                continue
            if role == "user":
                add({"step_type": "observation", "title": "user",
                     "body": clip(txt, max_chars), **base})
            else:
                add({"step_type": "thought", "title": role,
                     "body": clip(txt, max_chars), **base})
            continue

    return steps


def conversation_rows(records, max_chars: int):
    rows = []
    for rec in records:
        rtype = rec.get("type")
        if rtype == "function_call":
            name = rec.get("name") or "tool"
            raw = rec.get("arguments") or ""
            rows.append({"role": "assistant",
                         "content": f"[tool_use] {name}: {clip(str(raw), 400)}"})
        elif rtype == "function_call_result":
            out = rec.get("output") or rec.get("result") or ""
            if isinstance(out, (dict, list)):
                out = json.dumps(out, ensure_ascii=False)
            rows.append({"role": "tool", "content": f"[tool_result] {clip(str(out), 400)}"})
        elif rtype == "reasoning":
            txt = clean(text_of(rec.get("content") or rec.get("text") or ""))
            if txt:
                rows.append({"role": "assistant", "content": "[reasoning] " + clip(txt, 600)})
        elif rtype == "message":
            role = rec.get("role") or "assistant"
            if role not in {"user", "assistant", "system", "tool"}:
                role = "assistant"
            txt = clean(text_of(rec.get("content")))
            if txt:
                rows.append({"role": role, "content": clip(txt, max_chars)})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--format", choices=["arm", "conversation"], default="arm")
    ap.add_argument("--max-chars", type=int, default=1200)
    args = ap.parse_args()

    records = []
    with open(args.session, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)

    if args.format == "conversation":
        rows = conversation_rows(records, args.max_chars)
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        kinds = {}
        for r in rows:
            kinds[r["role"]] = kinds.get(r["role"], 0) + 1
        summary = {"out": args.out, "format": "conversation", "messages": len(rows), "roles": kinds}
    else:
        steps = arm_steps(records, args.max_chars)
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            for s in steps:
                fh.write(json.dumps(s, ensure_ascii=False, separators=(",", ":")) + "\n")
        kinds = {}
        for s in steps:
            kinds[s["step_type"]] = kinds.get(s["step_type"], 0) + 1
        calls = {s.get("tool_call_id") for s in steps if s["step_type"] == "tool_call"}
        results = {s.get("tool_call_id") for s in steps if s["step_type"] == "tool_result"}
        stamps = {s.get("timestamp") for s in steps if s.get("timestamp")}
        total = sum(s.get("cost_usd", 0) or 0 for s in steps)
        summary = {
            "out": args.out, "format": "arm", "steps": len(steps), "step_types": kinds,
            "paired_tool_calls": len(calls & results),
            "unpaired": len(calls ^ results),
            "distinct_timestamps": len(stamps),
            "total_cost_usd": round(total, 6),
            "first": min(stamps) if stamps else None,
            "last": max(stamps) if stamps else None,
            "bytes": os.path.getsize(args.out),
        }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
