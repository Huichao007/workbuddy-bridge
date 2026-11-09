#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-command setup for WorkBuddy Bridge.

    python setup.py                    # find installs, start bridges, wire clients
    python setup.py --clients none     # only run the bridges
    python setup.py --no-autostart     # skip the scheduled tasks
    python setup.py status             # what is running right now
    python setup.py stop               # stop the bridges this file started
    python setup.py uninstall          # stop + remove scheduled tasks

What it does, in order:

  1. finds every WorkBuddy desktop install that is signed in (the domestic app
     and the international app are separate installs with separate credit pools)
  2. writes instances.json - one port per credit pool, 18490, 18491, ...
  3. starts one bridge process per instance and waits until /health answers
  4. merges the matching provider blocks into your OpenCode / Codex config
     (backing the file up first, never touching unrelated keys)
  5. optionally registers one logon task + one 10-minute keepalive task

Only the standard library is used, so there is nothing to pip install.
"""

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import wbpaths  # noqa: E402

IS_WIN = sys.platform == "win32"
CREATE_NO_WINDOW = 0x08000000 if IS_WIN else 0
PY = sys.executable
INSTANCES_FILE = os.path.join(HERE, "instances.json")
BASE_PORTS = [18490, 18491, 18492, 18493]

# provider id in the clients -> label shown in the picker
PROVIDER_CN = "workbuddy"
PROVIDER_INTL = "workbuddy-intl"


# --- small helpers -----------------------------------------------------------

def say(msg="", color=None):
    print(msg)


def ok(msg):
    print("  [ok]   " + msg)


def warn(msg):
    print("  [warn] " + msg)


def fail(msg, hint=""):
    print("  [fail] " + msg)
    if hint:
        print("         " + hint)


class Abort(Exception):
    pass


def console_encoding():
    """Encoding the Windows console tools actually emit.

    tasklist / schtasks write in the OEM code page (936 = GBK on a Chinese
    Windows), not UTF-8. Decoding them as UTF-8 raises UnicodeDecodeError inside
    subprocess's reader thread and takes the whole run down - which is exactly
    what happens on a Chinese machine. Ask the OS, then fall back.
    """
    if not IS_WIN:
        return None
    try:
        cp = subprocess.run(["cmd", "/c", "chcp"], capture_output=True,
                            creationflags=CREATE_NO_WINDOW)
        raw = cp.stdout or b""
        for token in raw.split():
            t = token.strip().decode("ascii", "ignore")
            if t.isdigit():
                enc = "cp%s" % t
                "".encode(enc)          # validate the codec name
                return enc
    except Exception:
        pass
    for enc in ("cp936", "cp1252", "cp65001"):
        try:
            "".encode(enc)
            return enc
        except LookupError:
            continue
    return None


CONSOLE_ENC = console_encoding()


def run_console(args, timeout=30):
    """Run a Windows console tool and return (rc, text) without decoding errors."""
    try:
        p = subprocess.run(args, capture_output=True,
                           creationflags=CREATE_NO_WINDOW, timeout=timeout)
    except Exception as e:
        return 1, "%r" % (e,)
    text = (p.stdout or b"").decode(CONSOLE_ENC or "utf-8", "replace")
    err = (p.stderr or b"").decode(CONSOLE_ENC or "utf-8", "replace")
    return p.returncode, (text + err)


def http_json(url, timeout=15):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def port_free(port, host="127.0.0.1"):
    try:
        with socket.create_connection((host, port), 0.4):
            return False
    except Exception:
        return True


def wait_health(port, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            return http_json("http://127.0.0.1:%d/health" % port, timeout=4)
        except Exception:
            time.sleep(0.4)
    return None


# --- discovery ---------------------------------------------------------------

def config_dirs():
    """Every directory that holds a live wbipc/endpoint.json.

    Each one is a separate signed-in desktop app, which means a separate credit
    pool. This is the only reliable pairing: the install root tells you where
    the exe is, the config dir tells you whose session it is.
    """
    home = os.path.expanduser("~")
    cands = []
    env = (os.environ.get("WORKBUDDY_CONFIG_DIR") or "").strip().strip('"')
    if env:
        cands.append(os.path.expandvars(os.path.expanduser(env)))
    cands.append(os.path.join(home, ".workbuddy"))
    # any sibling config dir a second edition may use: .workbuddy-ai, .workbuddy-intl, ...
    try:
        for name in sorted(os.listdir(home)):
            if name.startswith(".workbuddy") and name != ".workbuddy":
                cands.append(os.path.join(home, name))
    except OSError:
        pass
    # Anything the desktop app keeps under %APPDATA%\<Something>Buddy
    appdata = os.environ.get("APPDATA") or ""
    if appdata and os.path.isdir(appdata):
        try:
            for name in sorted(os.listdir(appdata)):
                if "buddy" in name.lower():
                    cands.append(os.path.join(appdata, name))
        except OSError:
            pass

    seen, out = set(), []
    for c in cands:
        if not c or not os.path.isdir(c):
            continue
        ep = os.path.join(c, "wbipc", "endpoint.json")
        if not os.path.isfile(ep):
            continue
        key = os.path.normcase(os.path.abspath(c))
        if key in seen:
            continue
        seen.add(key)
        out.append(os.path.abspath(c))
    return out


def guess_edition(cfg_dir):
    """cn / intl, decided by the desktop app's own product config.

    Every install writes ``cache/acc-product-config-v3.json`` with the
    ``endpoint`` it talks to (``https://www.workbuddy.cn`` for the domestic
    build). That is far more reliable than guessing from a folder name, so we
    read it first and only fall back to names.
    """
    cfg_file = os.path.join(cfg_dir, "cache", "acc-product-config-v3.json")
    try:
        with open(cfg_file, "r", encoding="utf-8-sig") as fh:
            cfg = json.load(fh)
        endpoint = str(cfg.get("endpoint") or "").lower()
        if endpoint:
            if ".cn" in endpoint or "workbuddy.cn" in endpoint:
                return "cn"
            return "intl"
    except Exception:
        pass
    low = cfg_dir.lower().replace("\\", "/").rstrip("/")
    tail = low.split("/")[-1]
    if "intl" in tail or "international" in tail:
        return "intl"
    return "cn"


def edition_endpoint(cfg_dir):
    """Human-readable upstream for the report, e.g. https://www.workbuddy.cn"""
    cfg_file = os.path.join(cfg_dir, "cache", "acc-product-config-v3.json")
    try:
        with open(cfg_file, "r", encoding="utf-8-sig") as fh:
            return str(json.load(fh).get("endpoint") or "")
    except Exception:
        return ""


def endpoint_age(cfg_dir):
    try:
        return time.time() - os.path.getmtime(
            os.path.join(cfg_dir, "wbipc", "endpoint.json"))
    except OSError:
        return None


def probe_session(cfg_dir, timeout=12.0):
    """Really open the named pipe for this config dir.

    A leftover ``endpoint.json`` from an app that has since been closed or
    uninstalled looks exactly like a live one on disk, so the file is never
    trusted. Opening the pipe is the only honest answer, and it decides whether
    setup starts a bridge here or tells you to sign that app in again.
    """
    import threading

    lib = wbpaths.ipc_lib_dir(wbpaths.find_home())
    if not lib:
        return False, "WBIPC client library not found"
    if lib not in sys.path:
        sys.path.insert(0, lib)
    result = {"ok": False, "detail": "timed out"}

    def work():
        old = os.environ.get("WORKBUDDY_CONFIG_DIR")
        try:
            os.environ["WORKBUDDY_CONFIG_DIR"] = cfg_dir
            for m in [k for k in list(sys.modules) if k.startswith("workbuddy_ipc")]:
                del sys.modules[m]
            from workbuddy_ipc import connect
            client = connect(client_id="wb-bridge-setup", client_kind="skill",
                             client_version="1.0.0")
            try:
                pipes = client.pipes or []
                if "wb.request" in pipes:
                    result["ok"] = True
                    result["detail"] = "wb.request reachable"
                else:
                    result["detail"] = "pipe open but wb.request missing (signed out?)"
            finally:
                try:
                    client.close()
                except Exception:
                    pass
        except Exception as e:
            result["detail"] = "%s: %s" % (type(e).__name__, str(e)[:160])
        finally:
            if old is None:
                os.environ.pop("WORKBUDDY_CONFIG_DIR", None)
            else:
                os.environ["WORKBUDDY_CONFIG_DIR"] = old

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(timeout)
    return result["ok"], result["detail"]


def label_for(cfg_dir):
    ed = guess_edition(cfg_dir)
    if ed == "intl":
        return "WorkBuddy International (国际版)"
    return "WorkBuddy 国内版 (China)"


def provider_for(index, edition, taken=()):
    """Provider id in the client config. Edition first, index as a tiebreaker,
    so the domestic build is always `workbuddy` and the international one is
    `workbuddy-intl` no matter which directory sorts first."""
    base = PROVIDER_INTL if edition == "intl" else PROVIDER_CN
    pid, n = base, 2
    while pid in taken:
        pid = "%s%d" % (base, n)
        n += 1
    return pid


# --- instances.json ----------------------------------------------------------

def read_instances():
    try:
        with open(INSTANCES_FILE, "r", encoding="utf-8-sig") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        return {}
    except Exception as e:
        warn("instances.json unreadable (%r) - regenerating" % (e,))
        return {}
    table = raw.get("instances", raw) if isinstance(raw, dict) else {}
    return {k: v for k, v in table.items() if isinstance(v, dict)}


def write_instances(table):
    payload = {"_comment": "Generated by setup.py. One entry = one WorkBuddy "
                           "credit pool = one bridge port.",
               "instances": table}
    with open(INSTANCES_FILE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def _opencode_cfg_path():
    """Path only - never reads the file, safe to call before clients are wired."""
    try:
        return opencode_config_path()
    except Exception:
        return None


def ports_already_wired(table):
    """Move an instance onto the port its provider is *already* using, when that
    port is alive.

    This is what makes re-running setup a no-op instead of slowly accumulating
    one bridge per run: the user's working config is the best evidence of which
    port this edition belongs on.
    """
    path = _opencode_cfg_path()
    if not path or not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            providers = (json.load(fh) or {}).get("providers") or {}
    except Exception:
        return
    used = {int(s["port"]) for s in table.values()}
    for name, spec in table.items():
        block = providers.get(spec.get("provider") or "")
        if not isinstance(block, dict):
            continue
        url = ((block.get("settings") or {}).get("baseURL")
               or (block.get("options") or {}).get("baseURL") or "")
        m = re.search(r"127\.0\.0\.1:(\d+)", url)
        if not m:
            continue
        port = int(m.group(1))
        cur = int(spec["port"])
        if port == cur or port in used:
            continue
        if live_bridge_on(port):
            used.discard(cur)
            used.add(port)
            spec["port"] = port
            ok("%s is already wired to port %d - reusing that bridge" % (name, port))


def plan_instances(cfg_dirs, ports=None):
    """Assign a stable name and port to every config dir."""
    old = read_instances()
    used_ports = set()
    taken_providers = set()
    table = {}
    free = list(ports or BASE_PORTS)
    for cfg in cfg_dirs:
        name = None
        for k, spec in old.items():
            if spec.get("config_dir") and \
                    os.path.normcase(os.path.abspath(spec["config_dir"])) == \
                    os.path.normcase(cfg):
                name = k
                break
        edition = guess_edition(cfg)
        if name is None:
            base = edition
            name, n = base, 2
            while name in table:
                name = "%s%d" % (base, n)
                n += 1
        port = None
        if name in old and old[name].get("port") and old[name]["port"] not in used_ports:
            port = int(old[name]["port"])
        while port is None or port in used_ports:
            port = free.pop(0) if free else 18490 + len(used_ports)
        used_ports.add(port)
        pid = provider_for(len(table), edition, taken_providers)
        taken_providers.add(pid)
        table[name] = {
            "label": label_for(cfg),
            "port": port,
            "config_dir": cfg,
            "provider": pid,
            "endpoint": edition_endpoint(cfg),
        }
    return table


# --- process control ---------------------------------------------------------

def pid_file():
    return os.path.join(HERE, "run", "bridges.json")


def read_pids():
    try:
        with open(pid_file(), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def write_pids(d):
    os.makedirs(os.path.dirname(pid_file()), exist_ok=True)
    with open(pid_file(), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def alive(pid):
    if not pid:
        return False
    try:
        if IS_WIN:
            rc, out = run_console(["tasklist", "/FI", "PID eq %d" % int(pid), "/NH"])
            return str(int(pid)) in out
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def start_one(name, spec):
    port = int(spec["port"])
    health = None
    if not port_free(port):
        health = wait_health(port, timeout=3)
        if health and health.get("status") == "ok":
            ok("%s already running on %d (%d models)"
               % (name, port, health.get("models", 0)))
            return "reused", health
        fail("port %d is taken by something that is not this bridge" % port,
             "free it, or hand-pick ports with: python setup.py --ports 18500,18501")
        return "blocked", None

    logdir = os.path.join(HERE, "run")
    os.makedirs(logdir, exist_ok=True)
    out = open(os.path.join(logdir, "%s.out.log" % name), "ab")
    err = open(os.path.join(logdir, "%s.err.log" % name), "ab")
    env = dict(os.environ)
    env["WB_BRIDGE_DUMP"] = env.get("WB_BRIDGE_DUMP", "err")
    env.pop("WB_BRIDGE_PORT", None)          # let --instance decide
    env.pop("WORKBUDDY_CONFIG_DIR", None)
    proc = subprocess.Popen(
        [PY, "bridge.py", "--instance", name],
        cwd=HERE, stdout=out, stderr=err, stdin=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW, env=env)
    health = wait_health(port)
    if not health:
        try:
            proc.terminate()
        except Exception:
            pass
        tail = ""
        try:
            with open(os.path.join(logdir, "%s.err.log" % name), "r",
                      encoding="utf-8", errors="replace") as fh:
                tail = fh.read()[-800:]
        except OSError:
            pass
        fail("%s did not answer on port %d" % (name, port), tail.strip())
        return "failed", None
    pids = read_pids()
    pids[name] = proc.pid
    write_pids(pids)
    ok("%s started on http://127.0.0.1:%d (%d models, wbipc=%s)"
       % (name, port, health.get("models", 0),
          (health.get("wbipc") or {}).get("available")))
    return "started", health


def stop_all():
    pids = read_pids()
    if not pids:
        say("no bridge started by setup.py is recorded")
        return
    for name, pid in list(pids.items()):
        if not alive(pid):
            say("  %-6s pid %s already gone" % (name, pid))
            continue
        try:
            if IS_WIN:
                subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                               capture_output=True,
                               creationflags=CREATE_NO_WINDOW)
            else:
                os.kill(int(pid), 15)
            say("  %-6s stopped (pid %s)" % (name, pid))
        except Exception as e:
            warn("could not stop %s (%s): %r" % (name, pid, e))
    write_pids({})


# --- client config -----------------------------------------------------------

def opencode_config_path():
    cands = []
    env = (os.environ.get("WB_OPENCODE_JSON") or "").strip()
    if env:
        cands.append(env)
    xdg = (os.environ.get("XDG_CONFIG_HOME") or "").strip()
    if xdg:
        cands.append(os.path.join(xdg, "opencode", "opencode.json"))
    appdata = os.environ.get("APPDATA")
    if appdata:
        cands.append(os.path.join(appdata, "opencode", "opencode.json"))
    cands.append(os.path.join(os.path.expanduser("~"), ".config", "opencode",
                              "opencode.json"))
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return cands[0] if cands else None


def codex_config_path():
    home = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"),
                                                        ".codex")
    return os.path.join(home, "config.toml")


def models_from_bridge(port):
    data = http_json("http://127.0.0.1:%d/v1/models" % port)
    out = {}
    for m in data.get("data") or []:
        mid = m.get("id")
        if not mid:
            continue
        meta = m.get("meta") or {}
        entry = {
            "name": meta.get("name") or mid,
            "capabilities": meta.get("capabilities") or
            {"tools": True, "input": ["text"], "output": ["text"]},
        }
        if meta.get("limit"):
            entry["limit"] = meta["limit"]
        out[mid] = entry
    return out


def backup(path):
    if not os.path.exists(path):
        return None
    dst = "%s.bak-setup-%s" % (path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(path, dst)
    return dst


def live_bridge_on(port, timeout=3):
    """True when something that looks like this bridge answers on `port`."""
    try:
        h = http_json("http://127.0.0.1:%d/health" % port, timeout=timeout)
        return h.get("status") == "ok"
    except Exception:
        return False


def wire_opencode(instances, path, dry=False, force=False):
    if not path:
        warn("no opencode.json path could be determined - skipped")
        return False
    if not os.path.isfile(path):
        # create a minimal config; OpenCode tolerates partial files
        base = {"$schema": "https://opencode.ai/schemas/config.json"}
        if dry:
            say("  would create %s" % path)
            return False
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(base, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        ok("created %s" % path)

    with open(path, "r", encoding="utf-8-sig") as fh:
        cfg = json.load(fh)
    providers = cfg.setdefault("providers", {})

    # Safety: never silently move a provider that is currently pointing at a
    # *working* bridge to a different port. That is how a working setup breaks.
    for name, spec in instances.items():
        pid = spec.get("provider") or ("workbuddy" if name == "cn"
                                       else "workbuddy-" + name)
        old = providers.get(pid)
        if not isinstance(old, dict) or force:
            continue
        old_url = ((old.get("settings") or {}).get("baseURL")
                   or (old.get("options") or {}).get("baseURL") or "")
        m = re.search(r"127\.0\.0\.1:(\d+)", old_url)
        if not m:
            continue
        old_port = int(m.group(1))
        new_port = int(spec["port"])
        if old_port != new_port and live_bridge_on(old_port):
            warn("providers.%s already points at a working bridge on %d;"
                 " leaving it alone" % (pid, old_port))
            say("         this run would have moved it to %d. Use --force to do that,"
                % new_port)
            say("         or stop that bridge first (python setup.py stop).")
            spec["port"] = old_port
            continue

    changed = []
    for name, spec in instances.items():
        port = int(spec["port"])
        try:
            models = models_from_bridge(port)
        except Exception as e:
            warn("%s: cannot read /v1/models (%r) - provider left as is" % (name, e))
            continue
        pid = spec.get("provider") or ("workbuddy" if name == "cn"
                                       else "workbuddy-" + name)
        old_block = providers.get(pid) if isinstance(providers.get(pid), dict) else {}
        # Keep a name the user already picked, and keep any extra metadata they
        # attached to a model id; only the bridge-derived facts (baseURL, model
        # set) are authoritative.
        merged_models = {}
        old_models = old_block.get("models") if isinstance(
            old_block.get("models"), dict) else {}
        for mid, entry in models.items():
            prev = old_models.get(mid) if isinstance(old_models.get(mid), dict) else {}
            merged = dict(entry)
            for k, v in prev.items():
                if k not in merged:
                    merged[k] = v
            merged["name"] = entry.get("name") or prev.get("name") or mid
            merged_models[mid] = merged
        block = {
            "name": old_block.get("name") or spec.get("label") or name,
            "package": old_block.get("package")
            or "@opencode/ai/providers/openai-compatible",
            "settings": {"baseURL": "http://127.0.0.1:%d/v1" % port},
            "models": merged_models,
        }
        for k, v in old_block.items():
            if k not in block:
                block[k] = v
        if providers.get(pid) != block:
            providers[pid] = block
            changed.append("%s (port %d, %d models)" % (pid, port, len(merged_models)))
        spec["provider"] = pid

    if not changed:
        ok("opencode.json already in sync: %s" % path)
        return False
    if dry:
        say("  would update %s: %s" % (path, ", ".join(changed)))
        return False
    bak = backup(path)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    back = json.load(open(path, encoding="utf-8-sig"))
    for name, spec in instances.items():
        pid = spec["provider"]
        assert back["providers"][pid]["settings"]["baseURL"].endswith(
            ":%d/v1" % int(spec["port"]))
    ok("updated %s: %s%s"
       % (path, ", ".join(changed), (" (backup %s)" % os.path.basename(bak)) if bak else ""))
    return True


CODEX_BLOCK = """
# --- WorkBuddy Bridge ({name}) ---------------------------------------------
# Added by setup.py. Remove this block to undo.
[model_providers.{pid}]
name = "{label}"
base_url = "http://127.0.0.1:{port}/v1"
wire_api = "responses"
# The bridge authenticates through the WorkBuddy desktop app, so the key is a
# placeholder. Keep env_key if your Codex build requires one to exist; newer
# builds accept requires_openai_auth = false instead.
env_key = "WORKBUDDY_API_KEY"
"""


def wire_codex(instances, path, dry=False, force=False):
    if not path:
        return False
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            text = fh.read()
    except FileNotFoundError:
        text = ""
    added, moved = [], []
    for name, spec in instances.items():
        pid = spec.get("provider") or name
        port = int(spec["port"])
        header = re.search(r"^\s*\[model_providers\.%s\]" % re.escape(pid),
                           text, re.M)
        if header:
            # The block exists. If its base_url points at a different port that
            # is no longer alive, retarget it - otherwise Codex keeps talking to
            # nothing after the user changes ports.
            tail = text[header.end():]
            nxt = re.search(r"^\s*\[", tail, re.M)
            block = tail[:nxt.start()] if nxt else tail
            m = re.search(r'base_url\s*=\s*"http://127\.0\.0\.1:(\d+)/v1"', block)
            if not m:
                continue
            old = int(m.group(1))
            if old == port or (not force and live_bridge_on(old)):
                continue
            new_block = re.sub(
                r'base_url\s*=\s*"http://127\.0\.0\.1:\d+/v1"',
                'base_url = "http://127.0.0.1:%d/v1"' % port, block, count=1)
            text = text[:header.end()] + new_block + tail[len(block):]
            moved.append("%s %d->%d" % (pid, old, port))
            continue
        text += CODEX_BLOCK.format(name=name, pid=pid,
                                   label=spec.get("label") or name,
                                   port=port)
        added.append(pid)
    if not added and not moved:
        ok("codex config already has every provider: %s" % path)
        return False
    if dry:
        say("  would change %s in %s"
            % (", ".join(added + moved), path))
        return False
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    bak = backup(path)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text if text.endswith("\n") else text + "\n")
    parts = []
    if added:
        parts.append("added " + ", ".join(added))
    if moved:
        parts.append("retargeted " + ", ".join(moved))
    ok("%s in %s%s"
       % ("; ".join(parts), path,
          (" (backup %s)" % os.path.basename(bak)) if bak else ""))
    return True


# --- scheduled tasks ---------------------------------------------------------

TASK_ONCE = "WorkBuddyBridge-Logon"
TASK_KEEP = "WorkBuddyBridge-Keepalive"


def existing_bridge_tasks():
    """Task names that already launch *some* WorkBuddy bridge on this machine.

    Registering a second logon task next to one the user already has would race
    for the same port at every logon, so setup refuses to add its own when it
    finds a foreign one.
    """
    if not IS_WIN:
        return []
    rc, out = run_console(["schtasks", "/Query", "/FO", "CSV", "/NH"])
    found = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) < 1:
            continue
        name = parts[0].strip('"')
        low = name.lower()
        if ("bridge" in low or "workbuddy" in low) and low not in (
                TASK_ONCE.lower(), TASK_KEEP.lower()):
            found.append(name)
    return found


def register_tasks():
    if not IS_WIN:
        warn("scheduled tasks are Windows-only - skipped")
        return False
    others = existing_bridge_tasks()
    if others:
        warn("not registering autostart: the machine already has %s"
             % ", ".join(others))
        say("         (that task keeps your existing bridge alive; remove it first if"
            " you want this install to own autostart)")
        return False
    script = os.path.join(HERE, "scripts", "install-task.ps1")
    if not os.path.isfile(script):
        warn("scripts/install-task.ps1 missing - skipped autostart")
        return False
    rc, out = run_console(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                           "-File", script], timeout=60)
    if rc == 0:
        ok("autostart registered: %s + %s (every 10 min)" % (TASK_ONCE, TASK_KEEP))
        return True
    warn("could not register scheduled tasks: %s" % (out.strip()[:300]))
    return False


def remove_tasks():
    if not IS_WIN:
        return
    script = os.path.join(HERE, "scripts", "install-task.ps1")
    if os.path.isfile(script):
        run_console(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                     "-File", script, "-Remove"], timeout=60)
        say("  autostart tasks removed (if they existed)")
        return
    for t in (TASK_ONCE, TASK_KEEP):
        rc, _ = run_console(["schtasks", "/Delete", "/TN", t, "/F"])
        if rc == 0:
            say("  removed task %s" % t)


# --- commands ----------------------------------------------------------------

def cmd_setup(args):
    say("WorkBuddy Bridge - setup")
    say("")
    if sys.version_info < (3, 9):
        raise Abort("Python 3.9+ is required (found %d.%d)" % sys.version_info[:2])

    installs = wbpaths.find_installs()
    ok("installs found: %s" % (", ".join(installs) if installs else "none"))
    if not installs:
        raise Abort("WorkBuddy desktop is not installed or could not be located.\n"
                    "         Install it, sign in, then run this again. If it lives in an\n"
                    "         unusual place: set WORKBUDDY_HOME=D:\\path\\to\\WorkBuddy")

    dirs = config_dirs()
    if not dirs:
        raise Abort("No signed-in WorkBuddy session found (no wbipc/endpoint.json).\n"
                    "         Start the desktop app once and sign in, then run this again.")
    say("")
    say("Checking each signed-in session (opening the real named pipe):")
    live, dead = [], []
    for d in dirs:
        okp, detail = probe_session(d)
        if okp:
            live.append(d)
            ok("%s  %s" % (d, detail))
        else:
            dead.append((d, detail))
            warn("%s  NOT reachable: %s" % (d, detail))
    if not live:
        hint = "\n".join("           %s" % d for d, _ in dead)
        raise Abort("None of these sessions answer on the pipe:\n%s\n"
                    "         Open that WorkBuddy desktop app, make sure it is signed in,\n"
                    "         then run this again." % hint)
    if dead:
        say("")
        say("  Skipping %d stale session(s): the app is not running or not signed in."
            % len(dead))
        for d, detail in dead:
            say("    %s  (%s)" % (d, detail))
    dirs = live

    ports = None
    if args.ports:
        ports = [int(p) for p in args.ports.split(",") if p.strip()]
    table = plan_instances(dirs, ports)
    ports_already_wired(table)
    write_instances(table)
    say("")
    ok("instances.json written: %d instance(s)" % len(table))
    for name, spec in table.items():
        say("         %-6s port %-6d %-34s %s"
            % (name, spec["port"], spec.get("endpoint") or "-", spec["config_dir"]))
    say("")

    dry = args.dry_run
    if dry:
        say("  dry run: nothing started, nothing written to client configs")
        return 0

    results = {}
    for name, spec in table.items():
        try:
            state, health = start_one(name, spec)
        except Exception as e:
            state, health = "failed", None
            fail("%s: %r" % (name, e))
        results[name] = (state, health)
    write_instances(table)  # start_one may not change it, but keep ports stable

    pending = [n for n, (s, _) in results.items() if s == "blocked"]
    if pending:
        raise Abort("port(s) blocked for: %s" % ", ".join(pending))

    say("")
    say("clients")
    if args.clients is None:
        clients = ["opencode", "codex"]
    elif args.clients.strip().lower() in ("", "none"):
        clients = []
        say("  skipped (--clients none)")
    else:
        clients = [c.strip().lower() for c in args.clients.split(",") if c.strip()]
        if "all" in clients:
            clients = ["opencode", "codex"]
        unknown = [c for c in clients if c not in ("opencode", "codex")]
        if unknown:
            say("  ignoring unknown client(s): %s (known: opencode, codex, all, none)"
                % ", ".join(unknown))
            clients = [c for c in clients if c in ("opencode", "codex")]
    if clients:
        wrote = False
        if "opencode" in clients:
            wrote |= wire_opencode(table, args.opencode_json or opencode_config_path(),
                                   force=args.force)
        if "codex" in clients:
            wrote |= wire_codex(table, codex_config_path(), force=args.force)
        if not wrote:
            say("  nothing to change")

    if not args.no_autostart and not args.no_task:
        say("")
        register_tasks()

    say("")
    say("=" * 66)
    for name, spec in table.items():
        state, health = results.get(name, ("?", None))
        models = (health or {}).get("models", 0)
        say("  %-6s %-6s http://127.0.0.1:%d/v1   %d models   [%s]"
            % (name, spec.get("provider"), int(spec["port"]), models, state))
    say("=" * 66)
    say("")
    say("Next (copy-paste):")
    first = table[sorted(table)[0]]
    say("  python smoke.py            # one real call on both protocols")
    say("")
    say("  opencode run -m %s/<model> \"hello\"" % first["provider"])
    say("  $env:WORKBUDDY_API_KEY = \"wb-bridge-local\"")
    say("  codex -c model_provider=%s -c model=<model> exec \"hello\""
        % first["provider"])
    say("")
    say("Models: http://127.0.0.1:%d/v1/models" % int(first["port"]))
    return 0


def cmd_status(_args):
    table = read_instances()
    if not table:
        say("no instances.json - run: python setup.py")
        return 1
    pids = read_pids()
    for name, spec in table.items():
        port = int(spec["port"])
        try:
            h = http_json("http://127.0.0.1:%d/health" % port, timeout=4)
            say("  %-6s port %-6d models=%-3s wbipc=%-5s pid=%s"
                % (name, port, h.get("models"),
                   (h.get("wbipc") or {}).get("available"), pids.get(name, "-")))
        except Exception:
            say("  %-6s port %-6d DOWN (%s)" % (name, port, spec["config_dir"]))
    return 0


def cmd_stop(_args):
    stop_all()
    return 0


def cmd_uninstall(_args):
    stop_all()
    remove_tasks()
    say("")
    say("Client configs were left alone (they are just provider blocks).")
    say("Remove providers.<id> from opencode.json / the model_providers blocks")
    say("from config.toml if you want those gone too.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="One-command setup for WorkBuddy Bridge",
        epilog="Run with no arguments to do everything.")
    ap.add_argument("command", nargs="?", default="setup",
                    choices=["setup", "status", "stop", "uninstall"])
    ap.add_argument("--ports", default=None,
                    help="comma separated ports to assign, e.g. 18490,18491")
    ap.add_argument("--clients", default=None,
                    help="opencode,codex,all,none (default: opencode,codex)")
    ap.add_argument("--opencode-json", default=None,
                    help="path to opencode.json (default: auto-detect)")
    ap.add_argument("--no-autostart", action="store_true",
                    help="do not register the logon/keepalive tasks")
    ap.add_argument("--no-task", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--dry-run", action="store_true",
                    help="discover and report only")
    ap.add_argument("--force", action="store_true",
                    help="allow moving a provider off a bridge that is currently up")
    args = ap.parse_args(argv)

    try:
        if args.command == "status":
            return cmd_status(args)
        if args.command == "stop":
            return cmd_stop(args)
        if args.command == "uninstall":
            return cmd_uninstall(args)
        return cmd_setup(args)
    except Abort as e:
        say("")
        say("  [abort] " + str(e))
        return 1
    except KeyboardInterrupt:
        say("")
        say("interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
