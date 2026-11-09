#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Preflight check - run this first when something does not work.

    python doctor.py                 # check every instance in instances.json
    python doctor.py --instance cn   # check one
    python doctor.py --port 18490    # check a bridge on a hand-picked port

Checks, in the order the bridge itself needs them:
  1. WorkBuddy desktop install found (and how many installs exist)
  2. bundled WBIPC client library present
  3. desktop config / pipe endpoint advertised
  4. named pipe actually accepting a handshake (this is the real test)
  5. bridge port reachable, /health and /v1/models
  6. model count vs what the desktop config advertises

Exit code 0 = everything a request needs is in place.
"""

import argparse
import json
import os
import socket
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import wbpaths  # noqa: E402

DEFAULT_PORT = 18490
ok_all = True


def step(label, ok, detail=""):
    global ok_all
    if not ok:
        ok_all = False
    print("  [%s] %-42s %s" % ("PASS" if ok else "FAIL", label, detail))
    return ok


def note(label, detail=""):
    print("  [info] %-42s %s" % (label, detail))


def load_instances():
    path = os.path.join(HERE, "instances.json")
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            raw = json.load(fh)
    except Exception:
        return {}
    table = raw.get("instances", raw) if isinstance(raw, dict) else {}
    return {k: v for k, v in table.items() if isinstance(v, dict)}


def check_pipe(lib_dir, cfg_dir, label):
    """Open the real named pipe - the only trustworthy reachability test."""
    if lib_dir and lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    old = os.environ.get("WORKBUDDY_CONFIG_DIR")
    try:
        if cfg_dir:
            os.environ["WORKBUDDY_CONFIG_DIR"] = cfg_dir
        for m in [k for k in sys.modules if k.startswith("workbuddy_ipc")]:
            del sys.modules[m]
        from workbuddy_ipc import connect
        client = connect(client_id="wb-bridge-doctor", client_kind="skill",
                         client_version="1.0.0")
        try:
            pipes = client.pipes or []
            good = "wb.request" in pipes
            step("%s: pipe handshake" % label, good, "pipes=%s" % (pipes,))
            return good
        finally:
            try:
                client.close()
            except Exception:
                pass
    except Exception as e:
        step("%s: pipe handshake" % label, False,
             "%s: %s (desktop app running and signed in?)"
             % (type(e).__name__, str(e)[:120]))
        return False
    finally:
        if old is None:
            os.environ.pop("WORKBUDDY_CONFIG_DIR", None)
        else:
            os.environ["WORKBUDDY_CONFIG_DIR"] = old


def http_json(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def check_bridge(name, port, label):
    base = "http://127.0.0.1:%d" % port
    try:
        with socket.create_connection(("127.0.0.1", port), 2):
            listening = True
    except Exception:
        listening = False
    if not step("%s: port %d listening" % (label, port), listening,
                "" if listening else "start it: python setup.py"):
        return False
    try:
        health = http_json(base + "/health")
    except Exception as e:
        return step("%s: /health" % label, False, repr(e))
    step("%s: /health" % label, health.get("status") == "ok",
         "wbipc=%s models=%s"
         % ((health.get("wbipc") or {}).get("available"), health.get("models")))
    try:
        models = http_json(base + "/v1/models").get("data") or []
    except Exception as e:
        return step("%s: /v1/models" % label, False, repr(e))
    step("%s: /v1/models" % label, bool(models), "%d models" % len(models))
    if models:
        note("%s: sample model ids" % label,
             ", ".join(m.get("id", "?") for m in models[:5]))
    return bool(models)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--instance", default=None)
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args(argv)

    print("WorkBuddy Bridge - doctor\n")

    print("1. installation")
    installs = wbpaths.find_installs()
    step("desktop install found", bool(installs),
         ", ".join(installs) if installs else wbpaths.desktop_install_hint())
    if len(installs) > 1:
        note("multiple installs", "%d found (domestic + international)" % len(installs))
    home = os.environ.get("WORKBUDDY_HOME") or (installs[0] if installs else None)
    lib = wbpaths.ipc_lib_dir(home)
    step("bundled WBIPC client library", bool(lib),
         lib or ("missing under <install>/" + wbpaths.IPC_LIB_REL))
    exe = wbpaths.exe_path(home) if home else None
    step("WorkBuddy.exe", bool(exe), exe or "-")

    print("\n2. targets")
    table = load_instances()
    targets = []
    if args.port:
        targets = [{"name": "", "label": "port %d" % args.port,
                    "port": args.port, "config_dir": ""}]
    elif args.instance:
        if args.instance not in table:
            step("instance %r exists" % args.instance, False,
                 "known: %s" % (", ".join(table) or "none"))
        else:
            spec = table[args.instance]
            targets = [{"name": args.instance,
                        "label": spec.get("label") or args.instance,
                        "port": int(spec["port"]),
                        "config_dir": spec.get("config_dir") or ""}]
    elif table:
        for name, spec in table.items():
            targets = targets + [{"name": name,
                                  "label": spec.get("label") or name,
                                  "port": int(spec["port"]),
                                  "config_dir": spec.get("config_dir") or ""}]
    else:
        env_dir = os.environ.get("WORKBUDDY_CONFIG_DIR") or os.path.join(
            os.path.expanduser("~"), ".workbuddy")
        targets = [{"name": "", "label": "default",
                    "port": int(os.environ.get("WB_BRIDGE_PORT") or DEFAULT_PORT),
                    "config_dir": env_dir}]

    for t in targets:
        print("\n-- %s (%s)" % (t["label"], t["config_dir"] or "auto-detected config"))
        cfg_dir = t["config_dir"] or os.path.join(os.path.expanduser("~"),
                                                  ".workbuddy")
        ep = os.path.join(cfg_dir, "wbipc", "endpoint.json")
        if step("%s: endpoint.json" % t["label"], os.path.exists(ep), ep):
            try:
                info = json.load(open(ep, encoding="utf-8"))
                step("%s: endpoint advertised" % t["label"],
                     bool(info.get("endpoint")), str(info.get("endpoint"))[:70])
            except Exception as e:
                step("%s: endpoint readable" % t["label"], False, repr(e))
        if lib:
            check_pipe(lib, cfg_dir, t["label"])
        print("")
        check_bridge(t["name"], t["port"], t["label"])

    print("")
    if ok_all:
        base = "http://127.0.0.1:%d" % (targets[0]["port"] if targets else DEFAULT_PORT)
        print("ALL GOOD - point your client at %s/v1" % base)
    else:
        print("SOMETHING IS MISSING - fix the FAIL lines above")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
