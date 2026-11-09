#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Live smoke test - does the whole chain actually work right now?

    python smoke.py                    # every instance in instances.json
    python smoke.py --port 18490       # one bridge
    python smoke.py --model glm-5.3    # pin the model instead of auto-picking

`doctor.py` answers "is everything wired up". This answers the different and
blunter question "can I actually get an answer". It is slow (a real model call)
and it costs credits, which is why it is not part of setup.

Exit codes: 0 all good, 1 at least one failure, 2 nothing to test.
"""

import argparse
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def load_instances():
    try:
        with open(os.path.join(HERE, "instances.json"), "r",
                  encoding="utf-8-sig") as fh:
            raw = json.load(fh)
    except Exception:
        return {}
    table = raw.get("instances", raw) if isinstance(raw, dict) else {}
    return {k: v for k, v in table.items() if isinstance(v, dict)}


def post(url, body, timeout=180):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer local"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def get(url, timeout=15):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def pick_model(base, prefer=None):
    """Prefer a cheap model: the lowest credit multiplier that supports tools."""
    if prefer:
        return prefer
    try:
        data = get(base + "/v1/models").get("data") or []
    except Exception:
        return None
    best, best_credit = None, None
    for m in data:
        mid = m.get("id")
        name = ((m.get("meta") or {}).get("name") or "")
        credit = None
        if "(" in name and name.rstrip().endswith("x)"):
            try:
                credit = float(name.rsplit("(", 1)[1].rstrip("x) "))
            except ValueError:
                credit = None
        if credit is None:
            continue
        if best_credit is None or credit < best_credit:
            best, best_credit = mid, credit
    return best or (data[0].get("id") if data else None)


def check_chat(base, model):
    t0 = time.time()
    out = post(base + "/v1/chat/completions", {
        "model": model,
        "messages": [{"role": "user",
                      "content": "Reply with exactly: OK"}],
        "stream": False,
    })
    dt = time.time() - t0
    text = (out.get("choices") or [{}])[0].get("message", {}).get("content")
    usage = out.get("usage") or {}
    return True, "%0.1fs, %r, %s tokens" % (
        dt, (text or "").strip()[:40], usage.get("total_tokens", "?"))


def check_responses(base, model):
    """The Codex path uses a different endpoint and translation layer."""
    t0 = time.time()
    out = post(base + "/v1/responses", {
        "model": model,
        "input": [{"role": "user",
                   "content": [{"type": "input_text",
                                "text": "Reply with exactly: OK"}]}],
        "stream": False,
    })
    dt = time.time() - t0
    if out.get("status") != "completed":
        return False, "status=%r" % out.get("status")
    text = ""
    for item in out.get("output") or []:
        if item.get("type") == "message":
            for part in item.get("content") or []:
                text += part.get("text") or ""
    return True, "%0.1fs, %r" % (dt, text.strip()[:40])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--skip-responses", action="store_true",
                    help="only test the chat endpoint")
    args = ap.parse_args(argv)

    targets = []
    if args.port:
        targets = [("port %d" % args.port, args.port)]
    else:
        table = load_instances()
        if table:
            targets = [(n, int(s["port"])) for n, s in table.items()]
        else:
            targets = [("default", 18490)]

    failures = 0
    for name, port in targets:
        base = "http://127.0.0.1:%d" % port
        try:
            health = get(base + "/health")
        except Exception as e:
            print("  [fail] %-6s %s  bridge not answering (%s)"
                  % (name, base, str(e)[:60]))
            failures += 1
            continue
        if not (health.get("wbipc") or {}).get("available"):
            print("  [fail] %-6s wbipc unavailable - is the desktop app open "
                  "and signed in?" % name)
            failures += 1
            continue

        model = pick_model(base, args.model)
        if not model:
            print("  [fail] %-6s no model available from /v1/models" % name)
            failures += 1
            continue

        try:
            ok_chat, detail = check_chat(base, model)
        except Exception as e:
            ok_chat, detail = False, str(e)[:90]
        print("  [%s] %-6s chat/%s  %s"
              % ("ok" if ok_chat else "fail", name, model, detail))
        if not ok_chat:
            failures += 1

        if not args.skip_responses:
            try:
                ok_r, detail_r = check_responses(base, model)
            except Exception as e:
                ok_r, detail_r = False, str(e)[:90]
            print("  [%s] %-6s responses/%s  %s"
                  % ("ok" if ok_r else "fail", name, model, detail_r))
            if not ok_r:
                failures += 1

    print("")
    if failures:
        print("SMOKE FAILED (%d) - see docs/TROUBLESHOOTING.md" % failures)
        return 1
    print("SMOKE OK - both protocols answered with a real model call")
    return 0


if __name__ == "__main__":
    sys.exit(main())
