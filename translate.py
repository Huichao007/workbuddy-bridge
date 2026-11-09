# -*- coding: utf-8 -*-
"""Pure protocol helpers: no IPC, no filesystem, no WorkBuddy install needed.

Everything here is a plain function over dicts and strings, which is why it can
be unit-tested on a machine that has never seen the desktop app (see
``tests/test_translate.py`` and the CI workflow). The bridge imports these; the
tests import these; nothing in this file imports the bridge.

Three jobs:

* ``aggregate``   - streamed Chat Completions chunks -> one chat.completion
* ``sse_text``    - chunk list -> an SSE body the client can replay
* ``parse_sse``   - an upstream SSE body -> chunk list (inverse of sse_text)

The streaming split/merge logic is the part most likely to regress silently:
tool-call fragments arrive spread over many chunks and must be glued back into
one ``tool_calls`` entry, or Agent mode in OpenCode / Cursor breaks with a
half-formed JSON argument.
"""

import json


def parse_sse(text):
    """Split an upstream SSE body into parsed ``data:`` frames.

    Tolerant by design: upstream occasionally emits keepalive lines, blank
    data, or a trailing ``[DONE]``. None of those are frames.
    """
    frames = []
    for line in (text or "").split("\n"):
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            frames.append(json.loads(data))
        except Exception:
            continue
    return frames


def sse_text(frames):
    """Render frames as an SSE body (already terminated with [DONE])."""
    out = []
    for f in frames:
        out.append("data: " + json.dumps(f, ensure_ascii=False) + "\n\n")
    out.append("data: [DONE]\n\n")
    return "".join(out)


def aggregate(frames):
    """Collapse streamed chunks into a single non-streaming response.

    Tool calls are keyed by (choice index, tool_call index) because a model may
    emit several calls in parallel and each arrives as many fragments: the id
    and function name in the first fragment, then `arguments` incrementally.
    Concatenating by position is the only order the protocol guarantees.
    """
    merged = {"id": None, "object": "chat.completion", "created": None,
              "model": None, "choices": [], "usage": None}
    tools = {}

    for f in frames:
        for k in ("id", "created", "model"):
            if f.get(k) is not None:
                merged[k] = f[k]
        if f.get("usage"):
            merged["usage"] = f["usage"]
        for ch in f.get("choices") or []:
            idx = ch.get("index") or 0
            while len(merged["choices"]) <= idx:
                merged["choices"].append(
                    {"index": idx, "message": {"role": "assistant", "content": ""},
                     "finish_reason": None})
            mc = merged["choices"][idx]["message"]
            d = ch.get("delta") or {}
            if d.get("role"):
                mc["role"] = d["role"]
            if d.get("content"):
                mc["content"] = (mc.get("content") or "") + d["content"]
            for tc in d.get("tool_calls") or []:
                pos = tc.get("index") or 0
                slot = tools.setdefault((idx, pos), {
                    "index": pos, "id": None, "type": "function",
                    "function": {"name": "", "arguments": ""}})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["function"]["name"] += fn["name"]
                if fn.get("arguments"):
                    slot["function"]["arguments"] += fn["arguments"]
            if ch.get("finish_reason"):
                merged["choices"][idx]["finish_reason"] = ch["finish_reason"]

    for (idx, _pos), slot in tools.items():
        merged["choices"][idx].setdefault("message", {})["tool_calls"] = []
    # attach tool calls in order
    for (idx, pos), slot in sorted(tools.items()):
        mc = merged["choices"][idx]["message"]
        mc.setdefault("tool_calls", []).append(
            {k: slot[k] for k in ("index", "id", "type", "function")})
        if not slot["id"]:
            slot["id"] = "call_%d" % pos
        if not mc.get("content"):
            mc["content"] = mc.get("content") or None

    if merged["usage"] is None:
        merged["usage"] = {"prompt_tokens": 0, "completion_tokens": 0,
                           "total_tokens": 0}
    return merged


def has_stream_noise(text):
    """True when an upstream body contains frames we could not parse.

    Used by the bridge to decide whether to log a warning: silently dropping a
    frame would look exactly like a truncated answer to the client.
    """
    total = 0
    bad = 0
    for line in (text or "").split("\n"):
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        total += 1
        try:
            json.loads(data)
        except Exception:
            bad += 1
    return total > 0 and bad > 0
