# -*- coding: utf-8 -*-
"""WorkBuddy -> OpenAI-compatible local bridge.

Exposes an OpenAI-compatible HTTP API on 127.0.0.1 so that OpenCode, Codex CLI,
Cursor or any other OpenAI client can use WorkBuddy models and spend WorkBuddy
credits.

Uplink: the official WorkBuddy WBIPC named-pipe client that ships with the
desktop app - the same channel WorkBuddy's own skills use. Authentication is
handled by the running desktop app, so this bridge never sees account tokens
and never needs an API key.

Endpoints:
  GET  /health                  bridge + wbipc status
  GET  /v1/models               model list (mirrors WorkBuddy product config)
  POST /v1/chat/completions     Chat Completions (stream relay)
  POST /v1/responses            Responses API, translated for Codex CLI

Environment:
  WORKBUDDY_HOME        install root containing WorkBuddy.exe (auto-detected)
  WORKBUDDY_CONFIG_DIR  config dir holding wbipc/endpoint.json (~/.workbuddy)
  WB_BRIDGE_PORT        listen port (18490)
  WB_BRIDGE_HOST        bind host (127.0.0.1 - do not expose publicly)
  WB_BRIDGE_DUMP        unset = no snapshots, "err" = failures, "full" = all

Notes:
  * The gateway only supports streaming requests; the WBIPC v1 host has no
    streaming primitive, so a request is buffered upstream and replayed to the
    client when complete. Functionally identical, just no token-by-token UI.
"""

import base64
import json
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import instance

# --instance / --port / --config-dir / --home override the environment before
# anything reads it, so one bridge process can serve one specific install.
INSTANCE = instance.apply()

import responses_api
import translate
import wbpaths

# --- WorkBuddy WBIPC (official stdlib client shipped with the desktop app) ---
WB_HOME = wbpaths.find_home()
WB_LIB = wbpaths.ipc_lib_dir(WB_HOME)

if not WB_LIB:
    # Two different failures share this exit path and they need different fixes:
    # no install at all, versus an install whose bundled IPC client is missing
    # (a trimmed or half-finished install). Telling a user who *does* have the
    # app installed to "install the app" wastes their time.
    _installs = wbpaths.find_installs()
    if _installs:
        print("FATAL: the WorkBuddy install was found but its built-in IPC client "
              "is missing.\n"
              "  Found: %s\n"
              "  Expected under: <install>/%s/workbuddy_ipc\n"
              "  This usually means the install is incomplete or was trimmed by an\n"
              "  updater. Reinstall the WorkBuddy desktop app, then run again.\n"
              "  If the library lives somewhere else, point WORKBUDDY_HOME at the\n"
              "  folder that contains WorkBuddy.exe."
              % (", ".join(_installs), wbpaths.IPC_LIB_REL),
              file=sys.stderr)
    else:
        print("FATAL: WBIPC client library not found.\n"
              + wbpaths.desktop_install_hint(), file=sys.stderr)
    sys.exit(1)

if WB_LIB not in sys.path:
    sys.path.insert(0, WB_LIB)

try:
    from workbuddy_ipc import connect, WbipcError, NotWorkBuddyEnv, EndpointUntrusted
except Exception as _e:  # pragma: no cover
    print("FATAL: cannot import workbuddy_ipc:", _e, file=sys.stderr)
    print(wbpaths.desktop_install_hint(), file=sys.stderr)
    sys.exit(1)

PORT = int(os.environ.get("WB_BRIDGE_PORT", "18490"))
HOST = os.environ.get("WB_BRIDGE_HOST", "127.0.0.1").strip() or "127.0.0.1"


def _config_dir_candidates():
    """Where WorkBuddy keeps its config.

    An explicit ``WORKBUDDY_CONFIG_DIR`` (set by the user, by ``--config-dir``
    or by ``--instance``) is *authoritative*: it is the only candidate. That is
    what keeps two editions apart - the domestic app and the international app
    are separate config dirs, and a bridge that silently drifted to the other
    one would spend the wrong credit pool.

    With no override we look for every ``.workbuddy*`` config dir that has an
    endpoint, so a second edition is found without any configuration at all;
    ``_pick_latest`` then prefers whichever app ran last.
    """
    env = (os.environ.get("WORKBUDDY_CONFIG_DIR", "") or "").strip().strip('"')
    if env:
        return [os.path.expandvars(os.path.expanduser(env))]

    home = os.path.expanduser("~")
    cands = [os.path.join(home, ".workbuddy")]
    try:
        for name in sorted(os.listdir(home)):
            if name.startswith(".workbuddy") and name != ".workbuddy":
                cands.append(os.path.join(home, name))
    except OSError:
        pass
    seen, uniq = set(), []
    for d in cands:
        key = os.path.normcase(os.path.abspath(d))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(d)
    return uniq


CONFIG_DIR = _config_dir_candidates()[0]


def _pick_latest(relpath):
    """Return (config_dir, path) of the newest existing file among the
    candidates; falls back to the first candidate when none exists."""
    best, best_mtime = None, -1.0
    for d in _config_dir_candidates():
        p = os.path.join(d, *relpath)
        try:
            m = os.path.getmtime(p)
        except OSError:
            continue
        if m > best_mtime:
            best, best_mtime = (d, p), m
    if best is None:
        d = _config_dir_candidates()[0]
        best = (d, os.path.join(d, *relpath))
    return best


PRODUCT_CONFIG = _pick_latest(("cache", "acc-product-config-v3.json"))[1]

# workbuddy_ipc reads WORKBUDDY_CONFIG_DIR itself to locate endpoint.json;
# point it at the directory that actually holds the newest endpoint.
_EP_DIR, _EP_PATH = _pick_latest(("wbipc", "endpoint.json"))
if os.path.exists(_EP_PATH):
    os.environ["WORKBUDDY_CONFIG_DIR"] = _EP_DIR
CONFIG_DIR = _EP_DIR
GATEWAY_PATH = "/v2/chat/completions"
UPSTREAM_TIMEOUT = 600.0
# One repository can host several instances (domestic + international), so the
# log and dump files are named after the port: bridge-18490.log, dumps-18491/...
_SUFFIX = "" if PORT == 18490 else "-%d" % PORT
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "bridge%s.log" % _SUFFIX)

# WorkBuddy desktop app. The bridge reuses the desktop app's signed-in session,
# so the app must be running; if it is not, we try to launch it (best effort).
WB_EXE = wbpaths.exe_path(WB_HOME) or ""
LAUNCH_COOLDOWN = 120.0          # don't relaunch more than once per 2 min
DESKTOP_WAIT_TIMEOUT = 45.0      # how long to wait for wbipc after launching

_lock = threading.Lock()
_log_fh = None


def log(msg):
    line = "%s %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    with _lock:
        try:
            global _log_fh
            if _log_fh is None:
                _log_fh = open(LOG_FILE, "a", encoding="utf-8")
            _log_fh.write(line + "\n")
            _log_fh.flush()
        except Exception:
            pass


# --- model list ---------------------------------------------------------------

def load_product_config():
    try:
        with open(PRODUCT_CONFIG, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:
        log("product config unreadable: %r" % (e,))
        return {}


PRODUCT_CFG = load_product_config()


def credit_name(m, mid):
    """Display name with the WorkBuddy credit multiplier, matching the desktop
    picker: "Deepseek-V4.1-Flash (0.11x)". Credits come from the product
    config's `credits` field ("x0.11")."""
    base = m.get("name") or mid
    cred = m.get("credits")
    if not cred:
        return base
    try:
        val = float(str(cred).strip().lstrip("xX"))
    except ValueError:
        return base
    return "%s (%.2fx)" % (base, val)


def load_models():
    """Mirror exactly what the WorkBuddy desktop chat picker offers: the
    main chat (cli) agent's model list from the product config."""
    if not PRODUCT_CFG:
        return {}

    all_models = PRODUCT_CFG.get("models") or []
    by_id = {m.get("id"): m for m in all_models if m.get("id")}

    cli_agent = None
    for agent in PRODUCT_CFG.get("agents") or []:
        if agent.get("name") == "cli":
            cli_agent = agent
            break
    if cli_agent is None:
        cli_agent = (PRODUCT_CFG.get("agents") or [{}])[0]

    chosen = [mid for mid in (cli_agent.get("models") or [])
              if mid in by_id]

    out = {}
    for mid in chosen:
        m = by_id[mid]
        caps = {"tools": bool(m.get("supportsToolCall")), "output": ["text"]}
        inputs = ["text"]
        if m.get("supportsImages"):
            inputs.append("image")
        caps["input"] = inputs
        limit = {}
        if m.get("maxInputTokens"):
            limit["context"] = int(m["maxInputTokens"])
        if m.get("maxOutputTokens"):
            limit["output"] = int(m["maxOutputTokens"])
        entry = {"name": credit_name(m, mid), "capabilities": caps}
        if limit:
            entry["limit"] = limit
        out[mid] = entry
    return out


MODELS = load_models()


def wbipc_endpoint_info():
    """Read the pipe endpoint advertised by the desktop app (may be stale)."""
    _dir, path = _pick_latest(("wbipc", "endpoint.json"))
    if not os.path.exists(path):
        return False, "endpoint.json missing (WorkBuddy desktop never ran)"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            ep = json.load(fh)
        return bool(ep.get("endpoint")), ep.get("endpoint", "")
    except Exception as e:
        return False, str(e)


def wbipc_probe(timeout=3.0):
    """Really open the WBIPC pipe (the only trustworthy reachability test).

    Returns (ok, detail). A stale endpoint.json from an earlier run still
    exists after the desktop app is closed, so checking the file alone would
    wrongly report the bridge as healthy.
    """
    try:
        client = connect(client_id="opencode-bridge-health",
                         client_kind="skill", client_version="1.0.0")
    except NotWorkBuddyEnv as e:
        return False, "desktop app not running (%s)" % e
    except EndpointUntrusted as e:
        return False, "pipe rejected handshake (%s)" % e
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)
    try:
        pipes = client.pipes or []
        if "wb.request" not in pipes:
            return False, "host pipe wb.request unavailable (logged out?)"
    finally:
        try:
            client.close()
        except Exception:
            pass
    return True, "wb.request reachable"


def wbipc_available():
    """Back-compat alias used by /health and startup logging."""
    return wbipc_probe()


_desktop_lock = threading.Lock()
_last_launch = 0.0


def desktop_running():
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq WorkBuddy.exe", "/NH"],
            capture_output=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        # tasklist writes the OEM code page on Windows (GBK on a Chinese
        # install), so decode leniently instead of trusting UTF-8.
        text = (out.stdout or b"").decode("utf-8", "replace")
        if "\ufffd" in text:
            text = (out.stdout or b"").decode("mbcs", "replace")
        return "WorkBuddy.exe" in text
    except Exception:
        return True  # cannot tell; assume running so we never relaunch blindly


def ensure_desktop_app():
    """If the WorkBuddy desktop app is gone, launch it and wait for WBIPC.

    The bridge borrows the desktop app's signed-in session, so the app must be
    running. Launching it is best effort: the user may have closed it on
    purpose, so this only fires on a failed request and is rate limited.
    Returns True if WBIPC becomes reachable.
    """
    global _last_launch
    ok, _ = wbipc_probe()
    if ok:
        return True

    with _desktop_lock:
        ok, _ = wbipc_probe()
        if ok:
            return True
        now = time.time()
        if not desktop_running():
            if now - _last_launch >= LAUNCH_COOLDOWN:
                _last_launch = now
                if os.path.exists(WB_EXE):
                    try:
                        subprocess.Popen([WB_EXE], close_fds=True)
                        log("desktop app not running; launched %s" % WB_EXE)
                    except Exception as e:
                        log("failed to launch WorkBuddy: %r" % (e,))
                        return False
                else:
                    log("WorkBuddy.exe not found at %s" % WB_EXE)
                    return False
            else:
                log("desktop relaunch suppressed (cooldown)")
                return False
        else:
            log("desktop process present but wbipc unreachable; waiting")

        deadline = time.time() + DESKTOP_WAIT_TIMEOUT
        while time.time() < deadline:
            time.sleep(1.0)
            ok, detail = wbipc_probe()
            if ok:
                log("wbipc recovered after waiting for desktop app")
                return True
        log("wbipc still unreachable after %.0fs wait" % DESKTOP_WAIT_TIMEOUT)
        return False


# --- upstream call ------------------------------------------------------------

# Fields the gateway accepts. Everything else OpenCode may send (user, metadata,
# stream_options, ...) is dropped so unknown fields cannot 400 the request.
ALLOWED = {
    "model", "messages", "tools", "tool_choice", "temperature", "top_p",
    "max_tokens", "max_completion_tokens", "stop", "stream", "response_format",
    "parallel_tool_calls", "presence_penalty", "frequency_penalty",
    "reasoning_effort", "reasoningEffort",
}

# per-model reasoning config from the product config (effort / supportedEfforts)
_REASONING = {}


def _build_reasoning_map():
    for m in PRODUCT_CFG.get("models") or []:
        mid = m.get("id")
        if mid:
            _REASONING[mid] = m.get("reasoning") or None


_build_reasoning_map()


def _apply_reasoning_effort(body):
    """Some models (glm-5.1, glm-5.0-turbo, ...) reject requests without an
    explicit reasoning_effort; inject/validate it per product config."""
    mid = body.get("model")
    cfg = _REASONING.get(mid)
    if not cfg:
        body.pop("reasoning_effort", None)
        body.pop("reasoningEffort", None)
        return

    # accept OpenCode/AI-SDK style reasoningEffort as well
    alt = body.pop("reasoningEffort", None)
    if not body.get("reasoning_effort") and alt:
        body["reasoning_effort"] = alt

    effort = body.get("reasoning_effort")
    supported = cfg.get("supportedEfforts")
    if effort and supported and effort not in supported:
        effort = None  # clamp unsupported value
    if not effort:
        effort = cfg.get("effort") or cfg.get("defaultEffort") \
            or (supported[0] if supported else None)
    if effort:
        body["reasoning_effort"] = effort


DUMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "dumps%s" % _SUFFIX)
DUMP_KEEP = 300  # newest snapshots retained; older ones are pruned


def _prune_dumps():
    """Keep the dump folder from growing without bound."""
    try:
        names = [n for n in os.listdir(DUMP_DIR) if n.endswith(".json")]
        if len(names) <= DUMP_KEEP:
            return
        paths = [os.path.join(DUMP_DIR, n) for n in names]
        paths.sort(key=lambda p: os.path.getmtime(p))
        for p in paths[:len(paths) - DUMP_KEEP]:
            try:
                os.remove(p)
            except OSError:
                pass
    except OSError:
        pass


def _dump(kind, obj):
    """Write a request/response snapshot for offline diagnosis (opt-in).

    WB_BRIDGE_DUMP=err   dump upstream/gateway failures only (default)
    WB_BRIDGE_DUMP=full  also snapshot every outgoing request
    """
    mode = (os.environ.get("WB_BRIDGE_DUMP") or "").strip().lower()
    if not mode:
        return
    if kind == "req" and mode not in ("full", "1", "true", "yes"):
        return
    try:
        os.makedirs(DUMP_DIR, exist_ok=True)
        _prune_dumps()
        path = os.path.join(DUMP_DIR, "%s-%d.json" % (kind, int(time.time() * 1000)))
        if isinstance(obj, (bytes, bytearray)):
            obj = obj.decode("utf-8", "replace")
        if isinstance(obj, str):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(obj)
        else:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(obj, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


def upstream_chat(payload):
    """Forward one chat request to the WorkBuddy gateway via WBIPC.

    Returns (http_status, parsed_json_or_raw_text).
    """
    body = {k: v for k, v in payload.items() if k in ALLOWED and v is not None}
    body["stream"] = True  # gateway rejects non-streaming
    if body.get("tools") == []:
        body.pop("tools")
        body.pop("tool_choice", None)
    if not body.get("model"):
        raise ValueError("missing model")
    if not body.get("messages"):
        raise ValueError("missing messages")
    _apply_reasoning_effort(body)

    if os.environ.get("WB_BRIDGE_DUMP"):
        _dump("req", body)

    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    # WBIPC frames carry base64, so the JSON body must stay under 3/4 of the
    # frame limit. patch-wbipc-limits.py raises the Python client's
    # MAX_FRAME_BYTES to 96 MiB and the host's `My` to 990 MB, so the usable
    # JSON budget is ~72 MiB. 60 MiB leaves headroom for the b64 expansion.
    # (This used to be 900 KB, which rejected ordinary long conversations and
    # image inputs with HTTP 400 before anything reached the gateway.)
    if len(raw) > 60 * 1024 * 1024:
        raise ValueError(
            "request payload too large for WBIPC frame: %d bytes > 60 MiB "
            "JSON budget (frame limit 96 MiB after base64)" % len(raw))

    # One bounded retry for the transport-level failure that shows up
    # intermittently as `E_UPSTREAM upstream request failed` (bridge.log
    # 2026-10-18 14:47/14:49): the call errored before any completion, so the
    # client never sees a reply and clients that immediately resend succeed.
    # Timeouts are NOT retried - the upstream may still be running and
    # retrying there would burn credits twice.
    resp = None
    for attempt in (1, 2):
        client = connect(client_id="opencode-bridge", client_kind="skill",
                         client_version="1.0.0")
        try:
            pipes = client.pipes or []
            if "wb.request" not in pipes:
                raise RuntimeError("WorkBuddy host pipe wb.request unavailable "
                                   "(logged out?)")
            pipe = client.get_pipe("wb.request")
            if "http.fetch" not in (pipe.methods or []):
                raise RuntimeError("http.fetch unavailable; upgrade WorkBuddy")
            resp = pipe.invoke("http.fetch", {
                "method": "POST",
                "path": GATEWAY_PATH,
                "headers": {"content-type": "application/json",
                            "accept": "text/event-stream"},
                "body_b64": base64.b64encode(raw).decode("ascii"),
            }, timeout=UPSTREAM_TIMEOUT)
        except WbipcError as e:
            # The pipe error carries no response body, so snapshot the request
            # here; otherwise "E_UPSTREAM upstream request failed" is
            # untraceable after the fact.
            _dump("wbipc-err", {"code": e.code, "message": e.message,
                                "attempt": attempt, "sent": body})
            retryable = (e.code == "E_UPSTREAM"
                         and "timed out" not in (e.message or "").lower())
            if attempt == 1 and retryable:
                log("wbipc %s: %s -- retrying once" % (e.code, e.message))
                time.sleep(0.5)
                continue
            raise
        finally:
            try:
                client.close()
            except Exception:
                pass
        break

    status = int(resp.get("status") or 502)
    text = base64.b64decode(resp.get("body_b64") or b"").decode("utf-8", "replace")
    if status != 200:
        _dump("upstream-err", {"status": status, "body": text[:4000],
                               "sent": body})
        try:
            return status, json.loads(text)
        except Exception:
            return status, {"error": {"message": text[:500]}}

    frames = translate.parse_sse(text)
    if not frames:
        return 502, {"error": {"message": "empty upstream response"}}
    if translate.has_stream_noise(text):
        log("upstream SSE had unparseable frames (%d chars)" % len(text))
    return 200, frames


def sse_text(frames):
    """Kept as a thin alias so existing callers and tests stay valid."""
    return translate.sse_text(frames)


def aggregate(frames):
    """Kept as a thin alias so existing callers and tests stay valid."""
    return translate.aggregate(frames)


# --- external relay bypass ----------------------------------------------------
#
# Some models are not served by WorkBuddy at all (e.g. claude-sonnet-5-5 lives
# on a New-API style relay under a different subscription). Those are declared
# in relay-models.json and proxied straight through this bridge, so Cursor (and
# any other client) keeps a single base URL of http://127.0.0.1:18490/v1 and
# still sees them next to the WorkBuddy lineup.
#
# Failures here never touch the WorkBuddy path: an unknown model simply falls
# through to the WBIPC uplink exactly as before.

RELAY_CONF_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "relay-models.json")
RELAY_TIMEOUT = 600.0
UA = "curl/8.7.1"   # the relay's WAF rejects the default python-urllib UA


def load_relay_models():
    try:
        with open(RELAY_CONF_PATH, "r", encoding="utf-8") as fh:
            conf = json.load(fh)
        out = {}
        for mid, cfg in (conf.get("models") or {}).items():
            if isinstance(cfg, dict) and cfg.get("base_url"):
                out[mid] = cfg
        return out
    except FileNotFoundError:
        return {}
    except Exception as e:
        log("relay config unreadable: %r" % (e,))
        return {}


RELAY_MODELS = load_relay_models()


def relay_key(cfg):
    """Read the relay API key at request time from its file.

    Keeping the key in its own file (never in the repo JSON) lets the bridge
    pick up a rotated key without a restart, and keeps the secret out of any
    config that might get committed or shared.
    """
    path = cfg.get("key_file")
    if path:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                key = fh.read().strip()
            if key:
                return key
        except OSError as e:
            log("relay key file unreadable (%s): %r" % (path, e))
    return (cfg.get("api_key") or "").strip()


def relay_chat(payload, cfg):
    """POST an OpenAI chat request to an external relay and return
    (status, frames_or_error).

    The upstream call is always streamed, exactly like the WBIPC uplink: one
    code path then produces both the streaming and the aggregated reply. The
    caller decides whether the client gets SSE or a single JSON body.
    """
    body = {k: v for k, v in payload.items() if k in ALLOWED and v is not None}
    body["model"] = cfg.get("upstream_model") or payload.get("model")
    body["stream"] = True
    if body.get("tools") == []:
        body.pop("tools")
        body.pop("tool_choice", None)

    key = relay_key(cfg)
    if not key:
        raise ValueError("relay key missing for model %r" % payload.get("model"))

    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    if os.environ.get("WB_BRIDGE_DUMP"):
        _dump("relay-req", {"url": url, "body": body})

    req = urllib.request.Request(url, data=raw, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + key,
        "Accept": "text/event-stream",
        "User-Agent": UA,
    })
    try:
        with urllib.request.urlopen(req, timeout=RELAY_TIMEOUT) as resp:
            status = resp.getcode()
            text = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status = e.code
        text = e.read().decode("utf-8", "replace")
        _dump("relay-err", {"status": status, "body": text[:4000],
                            "sent": body})
        try:
            return status, json.loads(text)
        except Exception:
            return status, {"error": {"message": text[:500]}}
    except Exception as e:
        log("relay transport error: %r" % (e,))
        _dump("relay-err", {"transport": repr(e), "sent": body})
        return 502, {"error": {"message": "relay unreachable: %s" % e}}

    if status != 200:
        try:
            return status, json.loads(text)
        except Exception:
            return status, {"error": {"message": text[:500]}}

    # Relay answers with SSE (or, defensively, a single JSON document).
    frames = []
    for line in text.split("\n"):
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
    if not frames:
        # Not SSE - maybe one plain JSON body was returned despite stream=true.
        try:
            one = json.loads(text)
        except Exception:
            return 502, {"error": {"message": "empty relay response"}}
        return 200, [_json_to_frame(one)]
    return 200, frames


def _json_to_frame(obj):
    """Convert one non-streaming chat completion into a single delta frame.

    Lets a relay that ignored stream=true flow through the same aggregation and
    SSE re-emission used for genuinely streamed replies.
    """
    if not isinstance(obj, dict):
        return {}
    frame = {"id": obj.get("id"), "created": obj.get("created"),
             "model": obj.get("model"), "choices": [], "usage": obj.get("usage")}
    for ch in obj.get("choices") or []:
        msg = ch.get("message") or {}
        delta = {"role": msg.get("role") or "assistant",
                 "content": msg.get("content") or ""}
        if msg.get("tool_calls"):
            delta["tool_calls"] = msg["tool_calls"]
        frame["choices"].append({"index": ch.get("index") or 0,
                                 "delta": delta,
                                 "finish_reason": ch.get("finish_reason") or "stop"})
    return frame





# --- HTTP server --------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "WorkBuddyBridge/1.0"

    def log_message(self, fmt, *args):
        log("http %s" % (fmt % args))

    def _json(self, code, obj, extra_headers=None):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

    def _err(self, code, message, etype="invalid_request_error"):
        self._json(code, {"error": {"message": message, "type": etype}})

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path.rstrip("/") or "/"
        if path in ("/", "/health"):
            ok, info = wbipc_available()
            self._json(200, {
                "status": "ok",
                "label": INSTANCE.get("label") or "WorkBuddy",
                "instance": INSTANCE.get("instance") or "",
                "port": PORT,
                "wbipc": {"available": ok, "info": info},
                "models": len(MODELS),
                "product_config": os.path.exists(PRODUCT_CONFIG),
            })
        elif path == "/v1/models":
            now = int(time.time())
            data = [{"id": mid, "object": "model", "created": now,
                     "owned_by": "workbuddy", "meta": meta}
                    for mid, meta in MODELS.items()]
            for mid, cfg in RELAY_MODELS.items():
                caps = {"tools": True, "input": ["text", "image"],
                        "output": ["text"]}
                limit = {}
                if cfg.get("context"):
                    limit["context"] = int(cfg["context"])
                if cfg.get("output"):
                    limit["output"] = int(cfg["output"])
                entry = {"name": cfg.get("display") or mid,
                         "capabilities": caps}
                if limit:
                    entry["limit"] = limit
                data.append({"id": mid, "object": "model", "created": now,
                             "owned_by": "relay", "meta": entry})
            self._json(200, {"object": "list", "data": data})
        else:
            self._err(404, "unknown path %s" % path, "not_found_error")

    def _call_upstream(self, payload):
        """Forward to the gateway, retrying once after relaunching the desktop
        app if WBIPC is unreachable. Returns (status, result) or None after
        writing an error response.
        """
        # Models declared in relay-models.json are served by an external relay
        # and must never reach the WorkBuddy uplink.
        cfg = RELAY_MODELS.get(payload.get("model"))
        if cfg is not None:
            try:
                log("relay model=%s -> %s" % (payload.get("model"),
                                              cfg.get("base_url")))
                return relay_chat(payload, cfg)
            except ValueError as e:
                self._err(400, str(e))
                return None
            except Exception as e:
                log("relay error: " + traceback.format_exc())
                self._err(502, "relay error: %s" % e, "api_error")
                return None
        try:
            return upstream_chat(payload)
        except (NotWorkBuddyEnv, EndpointUntrusted) as e:
            log("wbipc unavailable: %r" % (e,))
            # WorkBuddy desktop app is the session source; if it was closed the
            # pipe is gone. Try to relaunch it once, then retry the request.
            if ensure_desktop_app():
                try:
                    return upstream_chat(payload)
                except (NotWorkBuddyEnv, EndpointUntrusted) as e2:
                    log("wbipc still unavailable after relaunch: %r" % (e2,))
                    self._err(503,
                              "WorkBuddy 桌面端未运行,自动拉起后仍连不上命名管道。"
                              "请手动打开 WorkBuddy 桌面端并确认已登录,然后重发。"
                              "(%s)" % e2, "api_error")
                    return None
            self._err(503,
                      "WorkBuddy 桌面端未运行(命名管道不可达)。"
                      "已尝试自动打开 WorkBuddy;若未自动打开请手动启动并登录,"
                      "然后重发消息。模型与积分都来自桌面端登录态。(%s)" % e,
                      "api_error")
            return None
        except WbipcError as e:
            log("wbipc error: %s %s" % (e.code, e.message))
            self._err(502, "WorkBuddy IPC %s: %s" % (e.code, e.message), "api_error")
            return None
        except ValueError as e:
            self._err(400, str(e))
            return None
        except Exception as e:
            log("bridge error: " + traceback.format_exc())
            self._err(500, "bridge error: %s" % e, "api_error")
            return None

    def _relay_sse(self, text):
        """Write an SSE body, flushing per event so clients see a stream."""
        data = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            for line in data.decode("utf-8").split("\n\n"):
                if not line.strip():
                    continue
                self.wfile.write((line + "\n\n").encode("utf-8"))
                self.wfile.flush()
        except Exception:
            pass
        try:
            self.close_connection = True
        except Exception:
            pass

    def _do_responses(self):
        """OpenAI Responses API endpoint (Codex CLI speaks only this)."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            payload = json.loads(raw.decode("utf-8"))
        except Exception as e:
            self._err(400, "bad request body: %s" % e)
            return

        want_stream = bool(payload.get("stream", True))
        model = payload.get("model")
        log("responses model=%s stream=%s" % (model, want_stream))

        try:
            chat_payload = responses_api.to_chat_request(payload)
        except Exception as e:
            log("responses translate error: " + traceback.format_exc())
            self._err(400, "cannot translate responses request: %s" % e)
            return

        result = self._call_upstream(chat_payload)
        if result is None:
            return
        status, res = result

        if status != 200:
            msg = res.get("msg") or (res.get("error") or {}).get("message") \
                or json.dumps(res, ensure_ascii=False)[:400]
            code = 400 if status < 500 else 502
            self._err(code, "WorkBuddy gateway %d: %s" % (status, msg),
                      "api_error")
            return

        frames = res
        if want_stream:
            self._relay_sse(responses_api.sse_from_frames(frames, model))
        else:
            self._json(200, responses_api.json_from_frames(frames, model))

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path.rstrip("/")
        if path == "/v1/responses":
            self._do_responses()
            return
        if path != "/v1/chat/completions":
            self._err(404, "unknown path %s" % path, "not_found_error")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            payload = json.loads(raw.decode("utf-8"))
        except Exception as e:
            self._err(400, "bad request body: %s" % e)
            return

        want_stream = bool(payload.get("stream", True))
        model = payload.get("model")
        log("chat model=%s stream=%s msgs=%d" % (model, want_stream,
                                                 len(payload.get("messages") or [])))

        result = self._call_upstream(payload)
        if result is None:
            return
        status, result = result

        if status != 200:
            # upstream error object -> pass through with its status
            msg = result.get("msg") or (result.get("error") or {}).get("message") \
                or json.dumps(result, ensure_ascii=False)[:400]
            code = 400 if status < 500 else 502
            self._err(code, "WorkBuddy gateway %d: %s" % (status, msg),
                      "api_error")
            return

        frames = result  # list of parsed chunks
        if want_stream:
            self._relay_sse(sse_text(frames))
        else:
            self._json(200, aggregate(frames))


def wait_for_port(port, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), 0.3):
                return True
        except Exception:
            time.sleep(0.2)
    return False


def main():
    label = INSTANCE.get("label") or "WorkBuddy"
    log("starting bridge instance=%r label=%r port=%d models=%d"
        % (INSTANCE.get("instance"), label, PORT, len(MODELS)))
    log("wbipc lib=%s" % WB_LIB)
    log("WB_BRIDGE_DUMP=%r" % (os.environ.get("WB_BRIDGE_DUMP") or ""))
    ok, info = wbipc_available()
    log("wbipc available=%s info=%s" % (ok, info))
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print("%s bridge listening on http://%s:%d (%d models)"
          % (label, HOST, PORT, len(MODELS)))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
