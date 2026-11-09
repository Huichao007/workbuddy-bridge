# -*- coding: utf-8 -*-
"""Which WorkBuddy install does *this* bridge serve?

One bridge process serves exactly one desktop app (one credit pool). Running the
domestic build and the international build side by side is therefore just two
processes on two ports - and this module is how each one knows who it is.

Resolution order (first hit wins, each field independently):

  1. ``--instance NAME``      -> look NAME up in ``instances.json`` next to this file
  2. explicit flags           -> ``--port 18491 --config-dir ... --home ...``
  3. environment (legacy)     -> ``WB_BRIDGE_PORT`` / ``WORKBUDDY_CONFIG_DIR`` /
                                 ``WORKBUDDY_HOME`` / ``WB_BRIDGE_LABEL``
  4. defaults                 -> port 18490, auto-detected install and config

Nothing here writes into the desktop app; it only decides where to look and
where to listen. Importing this module has one side effect: it fills in the
``WORKBUDDY_*`` / ``WB_BRIDGE_PORT`` environment variables that the rest of the
bridge already reads, so no other file needs to change.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
INSTANCES_FILE = os.path.join(HERE, "instances.json")

DEFAULT_PORT = 18490


def _argv_value(flag):
    """Read ``--flag value`` / ``--flag=value`` from sys.argv without argparse,
    so this can run before anything else claims the command line."""
    for i, arg in enumerate(sys.argv[1:]):
        if arg == flag and i + 2 <= len(sys.argv) - 1:
            return sys.argv[i + 2]
        if arg.startswith(flag + "="):
            return arg.split("=", 1)[1]
    return None


def load_instances():
    """Return ``{name: spec}`` from instances.json, or {} when absent/invalid."""
    try:
        with open(INSTANCES_FILE, "r", encoding="utf-8-sig") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print("instances.json unreadable (%r) - ignoring it" % (e,), file=sys.stderr)
        return {}
    table = raw.get("instances", raw) if isinstance(raw, dict) else {}
    return {k: v for k, v in table.items() if isinstance(v, dict)}


def apply():
    """Populate the environment the bridge reads. Returns the resolved dict."""
    name = _argv_value("--instance")
    table = load_instances()
    spec = {}
    if name:
        if name not in table:
            known = ", ".join(sorted(table)) or "none (create instances.json)"
            print("unknown instance %r - known: %s" % (name, known), file=sys.stderr)
            sys.exit(2)
        spec = table[name]
        # --instance is the strongest signal: it wins over an inherited
        # environment, otherwise a stale WB_BRIDGE_PORT from the parent shell
        # would silently point this process at the other edition's port.
        if spec.get("port"):
            os.environ["WB_BRIDGE_PORT"] = str(spec["port"])
        if spec.get("config_dir"):
            os.environ["WORKBUDDY_CONFIG_DIR"] = os.path.expandvars(
                os.path.expanduser(spec["config_dir"]))
        if spec.get("home"):
            os.environ["WORKBUDDY_HOME"] = os.path.expandvars(
                os.path.expanduser(spec["home"]))
        if spec.get("label"):
            os.environ["WB_BRIDGE_LABEL"] = spec["label"]

    port = _argv_value("--port")
    if port:
        os.environ["WB_BRIDGE_PORT"] = port
    config_dir = _argv_value("--config-dir")
    if config_dir:
        os.environ["WORKBUDDY_CONFIG_DIR"] = os.path.expandvars(
            os.path.expanduser(config_dir))
    home = _argv_value("--home")
    if home:
        os.environ["WORKBUDDY_HOME"] = os.path.expandvars(os.path.expanduser(home))
    label = _argv_value("--label")
    if label:
        os.environ["WB_BRIDGE_LABEL"] = label

    resolved = {
        "instance": name or "",
        "port": int(os.environ.get("WB_BRIDGE_PORT") or DEFAULT_PORT),
        "config_dir": os.environ.get("WORKBUDDY_CONFIG_DIR") or "",
        "home": os.environ.get("WORKBUDDY_HOME") or "",
        "label": os.environ.get("WB_BRIDGE_LABEL") or "WorkBuddy",
    }
    return resolved


def label():
    return os.environ.get("WB_BRIDGE_LABEL") or "WorkBuddy"
