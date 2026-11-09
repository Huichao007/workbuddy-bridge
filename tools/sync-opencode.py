#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rewrite OpenCode's workbuddy provider model list from the live bridge.

WorkBuddy changes its lineup server-side, so any cached model list goes stale
silently: the picker then offers ids the gateway rejects. This script takes the
bridge (which reads the WorkBuddy product config) as the single source of truth
and rewrites only `providers.workbuddy.models` in opencode.json.

    python tools/sync-opencode.py                       # dry run, prints drift
    python tools/sync-opencode.py --apply               # write (timestamped backup)
    python tools/sync-opencode.py --apply --force       # allow a large shrink

The config path comes from, in order:
  --config PATH  /  $WB_OPENCODE_JSON  /  %APPDATA%/opencode/opencode.json
  /  ~/.config/opencode/opencode.json

Nothing else in the file is touched.
"""

import argparse
import json
import os
import shutil
import sys
import time
import urllib.request

PROVIDER = "workbuddy"
BASE_URL = "http://127.0.0.1:%s/v1" % os.environ.get("WB_BRIDGE_PORT", "18490")


def default_config_path():
    cands = []
    env = os.environ.get("WB_OPENCODE_JSON")
    if env:
        cands.append(env)
    appdata = os.environ.get("APPDATA")
    if appdata:
        cands.append(os.path.join(appdata, "opencode", "opencode.json"))
    cands.append(os.path.join(os.path.expanduser("~"), ".config", "opencode", "opencode.json"))
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return cands[0] if cands else None


def fetch_models(base_url=None):
    url = (base_url or BASE_URL) + "/models"
    with urllib.request.urlopen(url, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    out = {}
    for m in data.get("data") or []:
        mid = m.get("id")
        if not mid:
            continue
        meta = m.get("meta") or {}
        entry = {"name": meta.get("name") or mid,
                 "capabilities": meta.get("capabilities")
                 or {"tools": True, "input": ["text"], "output": ["text"]}}
        if meta.get("limit"):
            entry["limit"] = meta["limit"]
        out[mid] = entry
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    ap.add_argument("--provider", default=PROVIDER,
                    help="provider key in opencode.json (default: workbuddy)")
    ap.add_argument("--port", default=None,
                    help="bridge port to read models from (default: $WB_BRIDGE_PORT or 18490)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    provider_key = args.provider
    base_url = ("http://127.0.0.1:%s/v1" % args.port) if args.port else BASE_URL

    cfg_path = args.config or default_config_path()
    if not cfg_path or not os.path.isfile(cfg_path):
        print("opencode.json not found (pass --config). Looked at: %r" % cfg_path)
        return 2

    try:
        live = fetch_models(base_url)
    except Exception as e:
        print("cannot reach the bridge at %s: %r" % (base_url, e))
        print("start it first: python setup.py")
        return 2
    if not live:
        print("bridge returned 0 models - refusing to write")
        return 1

    cfg = json.load(open(cfg_path, encoding="utf-8-sig"))
    provider = ((cfg.get("providers") or {}).get(provider_key))
    if not isinstance(provider, dict):
        print("no providers.%s in %s - add it first (see clients/opencode.json)" % (provider_key, cfg_path))
        return 1

    current = provider.get("models") or {}
    add = sorted(set(live) - set(current))
    drop = sorted(set(current) - set(live))
    print("config  : %s" % cfg_path)
    print("bridge  : %d models   config: %d models" % (len(live), len(current)))
    print("added   (%d): %s" % (len(add), add))
    print("removed (%d): %s" % (len(drop), drop))

    changed = add or drop or any(current.get(k) != v for k, v in live.items())
    if not changed:
        print("already in sync")
        return 0

    if len(live) < max(1, len(current) // 2) and not args.force:
        print("would shrink %d -> %d; pass --force if the lineup really halved"
              % (len(current), len(live)))
        return 1

    if not args.apply:
        print("dry run - re-run with --apply to write")
        return 0

    bak = "%s.bak-sync-%s" % (cfg_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(cfg_path, bak)
    provider["models"] = live
    with open(cfg_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    back = json.load(open(cfg_path, encoding="utf-8-sig"))
    assert len(back["providers"][provider_key]["models"]) == len(live)
    print("wrote %d models, backup %s" % (len(live), os.path.basename(bak)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
