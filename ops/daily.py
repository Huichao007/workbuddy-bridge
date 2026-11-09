# -*- coding: utf-8 -*-
"""Daily operator check for the published repo.

Runs on this machine, not in CI, because the thing worth watching is whether
the *live* project still looks healthy from the outside:

  * is the bridge still serving, and does a real request still work
  * is local main in sync with origin/main (drift is how "I fixed it" and
    "it is still broken for users" happen at the same time)
  * did the last CI run on main pass
  * does the README still lead with something a visitor understands
  * is an issue still open from an earlier failure

Writes a short report to D:\\projects\\workbuddy-bridge\\ops\\report-<date>.md
and prints the same to stdout. Exit code is 1 when something needs attention.

    python ops/daily.py            # full check
    python ops/daily.py --fast     # skip the live model call
"""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OPS_DIR = os.path.join(ROOT, "ops", "reports")
OWNER, REPO = "Huichao007", "workbuddy-bridge"
API = "https://api.github.com"

findings = []
notes = []


def add(level, text):
    findings.append((level, text))
    print("  [%s] %s" % (level, text))


TOKEN_FILE = r"D:\opencode\secrets\workbuddy-bridge-ops.token"


def token():
    for name in ("WB_GH_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(name)
        if value:
            return value
    # The scheduled task has no useful environment, so the token lives in a
    # user-only file outside the repo. See ops/README.md.
    try:
        with open(TOKEN_FILE, "r", encoding="ascii") as fh:
            value = fh.read().strip()
        if value:
            return value
    except OSError:
        pass
    # last resort: whatever gh has stored
    try:
        out = subprocess.run(["gh", "auth", "token"], capture_output=True,
                             text=True, timeout=20)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return None


def api(path, tok):
    req = urllib.request.Request(
        API + path,
        headers={"Authorization": "Bearer " + tok,
                 "Accept": "application/vnd.github+json",
                 "User-Agent": "wb-ops"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def git(*args):
    return subprocess.run(["git", "-C", ROOT] + list(args),
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def check_bridge(fast):
    try:
        with urllib.request.urlopen("http://127.0.0.1:18490/health",
                                    timeout=10) as r:
            health = json.loads(r.read().decode())
    except Exception as e:
        add("fail", "bridge on 18490 not answering (%s)" % str(e)[:60])
        return
    if not (health.get("wbipc") or {}).get("available"):
        add("fail", "bridge up but wbipc unavailable - desktop app closed or "
                    "signed out")
        return
    add("ok", "bridge up, %s models" % health.get("models"))
    if fast:
        return
    out = subprocess.run([sys.executable, os.path.join(ROOT, "smoke.py")],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=600)
    if out.returncode == 0:
        last = [l for l in out.stdout.splitlines() if "SMOKE" in l]
        add("ok", "live call passed: %s" % (last[-1] if last else "ok"))
    else:
        add("fail", "live call failed - see smoke.py output")


def check_sync(tok):
    local = git("rev-parse", "HEAD").stdout.strip()
    try:
        remote = api("/repos/%s/%s/commits/main" % (OWNER, REPO), tok)["sha"]
    except Exception as e:
        add("warn", "cannot read remote HEAD (%s)" % str(e)[:60])
        return
    if local == remote:
        add("ok", "local main == origin/main (%s)" % local[:7])
    else:
        ahead = git("rev-list", "--count", "%s..%s" % (remote, local)).stdout.strip()
        behind = git("rev-list", "--count", "%s..%s" % (local, remote)).stdout.strip()
        add("warn", "drift: %s ahead, %s behind (local %s / remote %s)"
            % (ahead, behind, local[:7], remote[:7]))


def check_ci(tok):
    try:
        runs = api("/repos/%s/%s/actions/runs?branch=main&per_page=1"
                   % (OWNER, REPO), tok)["workflow_runs"]
    except Exception as e:
        add("warn", "cannot read CI status (%s)" % str(e)[:60])
        return
    if not runs:
        add("warn", "no CI runs found")
        return
    r = runs[0]
    when = r["created_at"][:16].replace("T", " ")
    if r["status"] != "completed":
        add("warn", "CI %s is %s (%s)" % (r["name"], r["status"], when))
    elif r["conclusion"] == "success":
        add("ok", "last CI on main: success (%s, %s)" % (r["head_sha"][:7], when))
    else:
        add("fail", "last CI on main: %s (%s)" % (r["conclusion"], when))


def check_readme():
    path = os.path.join(ROOT, "README.md")
    try:
        text = open(path, encoding="utf-8").read()
    except OSError as e:
        add("fail", "README.md unreadable (%s)" % e)
        return
    missing = [t for t in ("OpenCode", "Codex", "python setup.py",
                           "python smoke.py") if t not in text]
    if missing:
        add("fail", "README lost its install story: %s" % ", ".join(missing))
    else:
        add("ok", "README still leads with OpenCode + Codex + the commands")


def check_issues(tok):
    try:
        issues = api("/repos/%s/%s/issues?state=open&per_page=30"
                     % (OWNER, REPO), tok)
    except Exception as e:
        add("warn", "cannot read issues (%s)" % str(e)[:60])
        return
    real = [i for i in issues if "pull_request" not in i]
    if not real:
        add("ok", "no open issues")
        return
    health = [i for i in real if any(l["name"] == "health"
                                     for l in i.get("labels") or [])]
    if health:
        add("fail", "%d open health issue(s): %s"
            % (len(health), ", ".join("#%d" % i["number"] for i in health)))
    others = [i for i in real if i not in health]
    if others:
        add("warn", "%d other open issue(s)" % len(others))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fast", action="store_true",
                    help="skip the live model call")
    args = ap.parse_args(argv)

    print("WorkBuddy Bridge - daily ops check")
    print("")
    print("service")
    check_bridge(args.fast)

    tok = token()
    print("")
    print("repository")
    if not tok:
        add("warn", "no GitHub token available; repository checks skipped")
    else:
        check_sync(tok)
        check_ci(tok)
        check_issues(tok)

    print("")
    print("product page")
    check_readme()

    fails = [f for f in findings if f[0] == "fail"]
    warns = [f for f in findings if f[0] == "warn"]
    oks = [f for f in findings if f[0] == "ok"]

    print("")
    print("%d ok, %d warn, %d fail" % (len(oks), len(warns), len(fails)))

    try:
        os.makedirs(OPS_DIR, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y-%m-%d")
        path = os.path.join(OPS_DIR, "report-%s.md" % stamp)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("# Ops report %s\n\n" % dt.datetime.now().strftime(
                "%Y-%m-%d %H:%M"))
            for level, text in findings:
                fh.write("- **%s** %s\n" % (level, text))
            fh.write("\n")
        print("report: %s" % path)
    except Exception as e:
        print("could not write report: %r" % (e,))

    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
