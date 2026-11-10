#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Push a tree of local file changes through the GitHub Git Data API.

Needed because `git push` over HTTPS gets reset from this network while the
REST API stays reachable. Equivalent to a single commit on main.
"""
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

REPO = "Huichao007/workbuddy-bridge"
BRANCH = "main"
TOKEN_FILE = r"D:\opencode\secrets\workbuddy-bridge-ops.token"
ROOT = r"D:\projects\workbuddy-bridge"


def token():
    with open(TOKEN_FILE, "r", encoding="utf-8") as fh:
        return fh.read().strip()


def api(path, method="GET", payload=None, tok=None):
    url = "https://api.github.com" + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "token " + (tok or token()))
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "workbuddy-bridge-release")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")[:600]
        raise SystemExit("HTTP %s on %s %s\n%s" % (err.code, method, path, detail))


def git(*args):
    return subprocess.check_output(("git", "-C", ROOT) + args).decode("utf-8").strip()


def main():
    message_file = sys.argv[1]
    with open(message_file, "r", encoding="utf-8") as fh:
        message = fh.read().strip()

    head_sha = git("rev-parse", "HEAD")
    base_sha = git("rev-parse", "origin/main")
    if head_sha == base_sha:
        print("nothing to push: local == origin/main")
        return

    changes = []
    for line in git("diff", "--name-status", "--no-renames", base_sha, head_sha).splitlines():
        status, path = line.split("\t", 1)
        changes.append((status.strip(), path))
    print("changes to publish: %d" % len(changes))

    remote_head = api("/repos/%s/git/ref/heads/%s" % (REPO, BRANCH))["object"]["sha"]
    if remote_head != base_sha:
        raise SystemExit("remote moved: expected %s, found %s" % (base_sha, remote_head))
    base_tree = api("/repos/%s/git/commits/%s" % (REPO, base_sha))["tree"]["sha"]

    entries = []
    for status, path in changes:
        if status in ("M", "A"):
            with open(os.path.join(ROOT, path), "rb") as fh:
                content = base64.b64encode(fh.read()).decode("ascii")
            blob = api("/repos/%s/git/blobs" % REPO, "POST",
                       {"content": content, "encoding": "base64"})
            entries.append({"path": path, "mode": "100644",
                            "type": "blob", "sha": blob["sha"]})
            print("  %s %s -> %s" % (status, path, blob["sha"][:8]))
        elif status == "D":
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
            print("  %s %s" % (status, path))
        else:
            raise SystemExit("unsupported status %r for %s" % (status, path))

    tree = api("/repos/%s/git/trees" % REPO, "POST",
               {"base_tree": base_tree, "tree": entries})
    commit = api("/repos/%s/git/commits" % REPO, "POST",
                 {"message": message, "tree": tree["sha"], "parents": [base_sha]})
    api("/repos/%s/git/refs/heads/%s" % (REPO, BRANCH), "PATCH",
        {"sha": commit["sha"], "force": False})

    print("published commit %s" % commit["sha"])
    print("https://github.com/%s/commit/%s" % (REPO, commit["sha"]))
    # keep the local ref in sync so status is honest
    subprocess.call(["git", "-C", ROOT, "update-ref",
                     "refs/remotes/origin/" + BRANCH, commit["sha"]])


if __name__ == "__main__":
    main()
