# WorkBuddy Bridge

[![ci](https://github.com/Huichao007/workbuddy-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/Huichao007/workbuddy-bridge/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/Huichao007/workbuddy-bridge)](https://github.com/Huichao007/workbuddy-bridge/releases)
[![license](https://img.shields.io/github/license/Huichao007/workbuddy-bridge)](LICENSE)
![platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078d4)

**Install once and your OpenCode and Codex CLI can use WorkBuddy's models and credits
immediately — no API key required.**

One command installs it and both clients work afterwards. The domestic and the
international edition can also run at the same time, each on its own port.

> Windows only — it depends on the app's Windows named pipe.

## What you get

| You get                                     | How you use it                                                                       |
| ------------------------------------------- | ------------------------------------------------------------------------------------ |
| **A WorkBuddy model group inside OpenCode** | the picker shows `WorkBuddy` groups with every model and its credit multiplier       |
| **A `workbuddy` provider in Codex CLI**     | `codex -c model_provider=workbuddy -c model=... exec "..."`                          |
| **Your existing config untouched**          | providers are only _added_; other providers and your default model stay as they were |
| **Self-healing**                            | logon autostart + 10-minute keepalive; the desktop app is relaunched on demand       |

Both of these work right after install. They are captured from a real run, not
illustrations:

```powershell
PS> opencode run -m workbuddy/deepseek-v4.1-flash "answer: OpenCode connected"
> build · deepseek-v4.1-flash
OpenCode 已连通

PS> codex -c model_provider=workbuddy -c model=deepseek-v4.1-flash exec "answer: Codex connected"
codex
Codex 已连通。
tokens used
14,891
```

No API key, no third-party relay, no token ever leaves your machine: requests ride the
named pipe the WorkBuddy desktop app already opened.

```
OpenCode  ─┐                        ┌─► bridge(cn)   127.0.0.1:18490 ─┐
Codex CLI ─┼─► one /v1 protocol ────┤                                  ├─► each edition's
Cursor    ─┘                        └─► bridge(intl) 127.0.0.1:18491 ─┘      signed-in session
```

## Quick start (3 commands)

Requires Windows 10/11, Python 3.9+, and a WorkBuddy desktop app that is **installed and
signed in**.

```powershell
git clone https://github.com/Huichao007/workbuddy-bridge.git D:\tools\workbuddy-bridge
cd D:\tools\workbuddy-bridge
python setup.py
```

`setup.py` does the whole job and prints what it is doing:

1. finds every WorkBuddy install on the machine;
2. opens each session's named pipe **for real**, so a leftover config from an app that was
   closed or uninstalled is skipped instead of being mistaken for a live credit pool;
3. assigns every live pool a port and writes `instances.json`;
4. starts one bridge per pool and waits until `/health` actually answers;
5. merges the provider blocks into `opencode.json` and `config.toml` (backed up first,
   nothing else touched) and registers logon + 10-minute-keepalive tasks.

It ends with a table like:

```
  cn     workbuddy      http://127.0.0.1:18490/v1   22 models   [started]
  intl   workbuddy-intl http://127.0.0.1:18491/v1   18 models   [started]
```

## Prove it works in 30 seconds

```powershell
python doctor.py            # wiring self-check, last line ALL GOOD
python smoke.py             # one real request on both protocols
```

`doctor.py` answers "is everything wired up". `smoke.py` answers the blunter
question: **"can I get an answer right now"**. It picks the cheapest model on
your account and hits `/v1/chat/completions` (the OpenCode path) and
`/v1/responses` (the Codex path), printing latency and token count:

```
  [ok] default chat/hy4free  2.1s, 'OK', 86 tokens
  [ok] default responses/hy4free  2.4s, 'OK'

SMOKE OK - both protocols answered with a real model call
```

Then confirm with the real clients, using a model id you actually have
(**do not copy the ids below — WorkBuddy rotates them**):

```powershell
curl.exe http://127.0.0.1:18490/v1/models       # what you have right now

opencode run -m workbuddy/<model-id> "say three words"

$env:WORKBUDDY_API_KEY = "wb-bridge-local"      # placeholder, never checked
codex -c model_provider=workbuddy -c model=<model-id> exec "say three words"
```

If both answer, you are done. Re-running `setup.py` is safe: it will not add ports or
move a provider that is already working.

## Domestic + international at the same time

The two editions are separate installs with separate sign-ins and separate credit pools.
One bridge process serves exactly one pool, so "both at once" is two processes on two
ports — which is what setup arranges automatically.

| What you have                  | Result                                                        |
| ------------------------------ | ------------------------------------------------------------- |
| domestic only                  | one instance on 18490, provider `workbuddy`                   |
| international only             | one instance on 18490, provider `workbuddy-intl`              |
| both, signed in                | 18490 + 18491, providers `workbuddy` / `workbuddy-intl`       |
| both installed, one signed out | only the live one is wired; the other is reported and skipped |

The edition is not guessed from a folder name: setup reads each app's own
`cache/acc-product-config-v3.json` (`endpoint` is `https://www.workbuddy.cn` for the
domestic build) and then opens the pipe. The model picker ends up with two groups, each
carrying that subscription's real model list and credit multiplier.

## How it works

1. **WBIPC named pipe** — the desktop app ships a stdlib Python client
   (`workbuddy_ipc`) that WorkBuddy's own skills use. The bridge imports _the copy in your
   install_ at runtime, so it always matches the running build; nothing is vendored.
2. **`bridge.py`** — a stdlib HTTP server translating the OpenAI protocol into pipe calls.
   The model list is read from the desktop product config at startup, never hardcoded.
3. **Protocols** — `/v1/chat/completions` for OpenCode / Cursor / any SDK,
   `/v1/responses` for Codex CLI (which refuses `wire_api = "chat"`).

## Requirements

|                   |                                     |
| ----------------- | ----------------------------------- |
| OS                | Windows 10/11                       |
| WorkBuddy desktop | installed **and signed in**         |
| Python            | 3.9+, `python` on PATH              |
| Ports             | one per instance, starting at 18490 |

## Clients

`setup.py` already wired them. What it writes:

**OpenCode** — a `providers.<id>` block with `package` + `settings.baseURL`, models read
from the live `/v1/models`, backed up as `opencode.json.bak-setup-<stamp>`.

**Codex CLI** — a `[model_providers.<id>]` block with `wire_api = "responses"` in
`%CODEX_HOME%\config.toml`:

```powershell
$env:WORKBUDDY_API_KEY = "wb-bridge-local"
codex -c model_provider=workbuddy -c model=deepseek-v4.1-flash exec "write a quicksort"
```

**Cursor** — `python clients\cursor-point-to-bridge.py --port 18490` (closes Cursor,
backs up its state DB, verifies, rolls back on failure; `--restore` to undo).

**Any SDK**:

```python
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:18490/v1", api_key="local")
```

## Environment

| Variable               | Default   | Meaning                                                                                                                   |
| ---------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------- |
| `WORKBUDDY_HOME`       | auto      | folder containing `WorkBuddy.exe`                                                                                         |
| `WORKBUDDY_CONFIG_DIR` | auto      | config dir holding `wbipc/endpoint.json`. **When set, it is the only source** — that is what keeps the two editions apart |
| `WB_BRIDGE_PORT`       | 18490     | listen port                                                                                                               |
| `WB_BRIDGE_HOST`       | 127.0.0.1 | bind address, never expose it                                                                                             |
| `WB_BRIDGE_LABEL`      | WorkBuddy | name in logs and `/health`                                                                                                |
| `WB_BRIDGE_DUMP`       | off       | `err` = dump failed requests, `full` = dump everything                                                                    |

## Known limits

By design, not bugs:

1. **Buffered, not token-streamed.** WBIPC has no streaming primitive, so a reply is
   replayed once complete. The first byte arrives after the model finishes thinking.
2. **~640 KB response cap.** The desktop app's `http.fetch` has a hard body limit.
   Nothing in this repo patches the vendor binary to get around it.
3. **The desktop app must stay open and signed in.** The bridge borrows, it does not replace.
4. **Windows only.**
5. **Credits are unchanged.** Everything is billed to your WorkBuddy account.

## Troubleshooting

| Symptom                                           | Cause                                            | Fix                                  |
| ------------------------------------------------- | ------------------------------------------------ | ------------------------------------ |
| `FATAL: WBIPC client library not found`           | install not detected                             | set `WORKBUDDY_HOME`                 |
| setup says a session is `NOT reachable`           | that edition is closed or signed out             | open it, sign in, rerun setup        |
| 503 `WorkBuddy 桌面端未运行`                      | same                                             | start the app once                   |
| 400 `missing model`                               | stale model id                                   | read `GET /v1/models`                |
| Codex: `wire_api = "chat" is no longer supported` | config not switched                              | use `responses`                      |
| setup says a port is taken                        | previous process still alive                     | `python setup.py stop`, or `--ports` |
| setup says another autostart task exists          | the machine already runs a different bridge task | remove that task first               |

More in [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md).

## Safety and compliance

- **Loopback only.** `127.0.0.1`, unreachable from your LAN. Keep the default.
- **No credentials.** The bridge never reads, stores or forwards account passwords or
  tokens; authentication happens inside the desktop app. No secrets are in this repo.
- **Nothing is patched.** The installer only writes `instances.json`, client config and two
  scheduled tasks.
- **Compliance risk is yours.** This reuses a subscription through a non-public entry point
  (the WBIPC client the app ships). WorkBuddy's terms may not allow spending subscription
  credits from third-party clients, and the vendor can change the pipe or suspend accounts
  at any time. **This is a personal convenience tool: no promise of longevity, no promise
  of ToS compliance.** Commercial use or serving other people is riskier — judge for yourself.
- **Not affiliated with WorkBuddy.** The name only describes what it talks to.

## Layout

```
setup.py            one-command deploy: discover -> start -> wire clients -> autostart
doctor.py           preflight; run it first when something breaks
smoke.py            live end-to-end check: one real call on both protocols
bridge.py           the OpenAI-compatible server
translate.py        SSE chunk aggregation and tool-call merging (pure, unit-tested)
instance.py         --instance / --port / --config-dir resolution
responses_api.py    Responses <-> Chat Completions translation (Codex)
wbpaths.py          install/config discovery (multiple installs supported)
scripts/            start-bridge.ps1, watchdog.cmd, install-task.ps1
tools/              sync-opencode.py
clients/            opencode.json, codex.config.toml, cursor-point-to-bridge.py
tests/              protocol unit tests, run by CI without WorkBuddy installed
docs/               ARCHITECTURE, CLIENTS, TROUBLESHOOTING, LIMITATIONS
```

Generated at runtime and git-ignored: `instances.json`, `run/`, `bridge*.log`, `dumps-*/`.

## License

MIT — see [LICENSE](LICENSE).
