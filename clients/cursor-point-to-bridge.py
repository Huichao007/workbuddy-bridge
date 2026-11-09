# -*- coding: utf-8 -*-
"""Point Cursor at the local WorkBuddy bridge (BYOK + "Override OpenAI Base URL").

Cursor keeps its AI settings in a SQLite key/value store. We set, for the
current user only:

    useOpenAIKey            = true
    openAIBaseUrl           = http://127.0.0.1:18490/v1
    aiSettings.userAddedModels += <WorkBuddy model ids>

Cursor normally encrypts the OpenAI key with Electron safeStorage, which we
cannot mint from outside. Its hydrateKey() falls back to the legacy plaintext
row ``cursorAuth/openAIKey``, and the bridge ignores auth entirely, so a
placeholder key is enough.

Cursor must not be running while we write - it caches settings in memory and
flushes them on exit, overwriting us. Every touched file is backed up, and the
backup is restored automatically if verification fails.

    python clients/cursor-point-to-bridge.py            # apply
    python clients/cursor-point-to-bridge.py --restore  # undo
    python clients/cursor-point-to-bridge.py --models a,b,c

Verified against Cursor 3.25.x. If a future Cursor moves these keys, the script
aborts before writing (it never leaves a half-patched DB behind).
"""

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time

BRIDGE_KEY = "wb-bridge-local"
BRIDGE_BASE_URL = "http://127.0.0.1:%s/v1" % os.environ.get("WB_BRIDGE_PORT", "18490")
APP_KEY = ("src.vs.platform.reactivestorage.browser.reactiveStorageServiceImpl"
           ".persistentStorage.applicationUser")
LEGACY_OPENAI_KEY_ROW = "cursorAuth/openAIKey"

DEFAULT_MODELS = [
    "glm-5.3", "glm-5.3-flash", "glm-5.2", "glm-5.1", "glm-5v-turbo",
    "deepseek-v4.1-flash", "deepseek-v4-pro", "kimi-k3-2", "kimi-k2.8-preview",
    "kimi-k2.7", "minimax-m3-pay", "hy3", "hy4-preview",
    "fast-model", "balanced-model", "deep-model",
]

HERE = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(HERE, ".cursor-state-backup")


def log(*a):
    print("[cursor-bridge]", *a, flush=True)


def db_path():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return os.path.join(appdata, "Cursor", "User", "globalStorage", "state.vscdb")


def cursor_exe():
    for p in (os.environ.get("CURSOR_EXE"),
              os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "cursor", "Cursor.exe"),
              r"C:\Program Files\Cursor\Cursor.exe"):
        if p and os.path.isfile(p):
            return p
    return None


def backup(db):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        src = db + suffix
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(BACKUP_DIR, "state.vscdb" + suffix))
            log("backed up", os.path.basename(src))


def restore(db):
    for suffix in ("", "-wal", "-shm"):
        src = os.path.join(BACKUP_DIR, "state.vscdb" + suffix)
        if os.path.exists(src):
            shutil.copy2(src, db + suffix)
            log("restored", db + suffix)


def running():
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Cursor.exe", "/NH"],
                             capture_output=True, text=True, timeout=20).stdout
        return "Cursor.exe" in out
    except Exception:
        return False


def close_cursor(timeout=40):
    ps1 = ("1..5 | ForEach-Object { Get-Process Cursor -ErrorAction SilentlyContinue |"
           " Where-Object { $_.MainWindowHandle -ne 0 } |"
           " ForEach-Object { $_.CloseMainWindow() | Out-Null }; Start-Sleep -Seconds 3 }")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps1], capture_output=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not running():
            log("Cursor exited gracefully")
            return True
        time.sleep(1)
    log("force-killing remaining Cursor processes")
    subprocess.run(["taskkill", "/IM", "Cursor.exe", "/F"], capture_output=True)
    time.sleep(2)
    return not running()


def patch(db, models):
    con = sqlite3.connect(db)
    try:
        cur = con.cursor()
        row = cur.execute("SELECT value FROM ItemTable WHERE key=?", (APP_KEY,)).fetchone()
        if not row:
            log("!! settings blob not found; this Cursor build stores it elsewhere - aborting")
            return False
        raw = row[0]
        blob = json.loads(raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else raw)

        blob["useOpenAIKey"] = True
        blob["openAIBaseUrl"] = BRIDGE_BASE_URL
        ai = blob.get("aiSettings") if isinstance(blob.get("aiSettings"), dict) else {}
        merged = list(ai.get("userAddedModels") or [])
        for m in models:
            if m not in merged:
                merged.append(m)
        ai["userAddedModels"] = merged
        blob["aiSettings"] = ai

        cur.execute("UPDATE ItemTable SET value=? WHERE key=?",
                    (json.dumps(blob, ensure_ascii=False, separators=(",", ":")), APP_KEY))
        cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
                    (LEGACY_OPENAI_KEY_ROW, BRIDGE_KEY))
        con.commit()
        log("patched: useOpenAIKey=true base=%s models+=%d"
            % (BRIDGE_BASE_URL, len(models)))
        return True
    except Exception as e:
        log("!! patch failed:", e)
        con.rollback()
        return False
    finally:
        con.close()


def verify(db, models):
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    try:
        row = con.execute("SELECT value FROM ItemTable WHERE key=?", (APP_KEY,)).fetchone()
        blob = json.loads(row[0])
        krow = con.execute("SELECT value FROM ItemTable WHERE key=?",
                           (LEGACY_OPENAI_KEY_ROW,)).fetchone()
        added = (blob.get("aiSettings") or {}).get("userAddedModels") or []
        return (blob.get("useOpenAIKey") is True
                and blob.get("openAIBaseUrl") == BRIDGE_BASE_URL
                and all(m in added for m in models[:3])
                and (krow[0] if krow else None) == BRIDGE_KEY)
    finally:
        con.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--models", default="", help="comma separated model ids to add")
    ap.add_argument("--port", default=None,
                    help="bridge port (default: $WB_BRIDGE_PORT or 18490)")
    ap.add_argument("--no-relaunch", action="store_true")
    args = ap.parse_args()

    global BRIDGE_BASE_URL
    if args.port:
        BRIDGE_BASE_URL = "http://127.0.0.1:%s/v1" % args.port

    db = db_path()
    if not db or not os.path.exists(db):
        log("!! state.vscdb not found at", db)
        return 1

    if args.restore:
        restore(db)
        return 0

    models = [m.strip() for m in args.models.split(",") if m.strip()] or DEFAULT_MODELS

    backup(db)
    if running():
        log("Cursor is running; closing it first")
        if not close_cursor():
            log("!! could not close Cursor; aborting to avoid DB corruption")
            return 2
    for suffix in ("-wal", "-shm"):
        p = db + suffix
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass

    if not patch(db, models) or not verify(db, models):
        log("!! verification failed; restoring backup")
        restore(db)
        return 3

    log("DONE. In Cursor -> Settings -> Models: 'OpenAI API Key' should read 'Secret saved',")
    log("  'Override OpenAI Base URL' = %s, then pick a model in the Agent picker." % BRIDGE_BASE_URL)

    exe = cursor_exe()
    if exe and not args.no_relaunch:
        subprocess.Popen([exe], cwd=os.path.dirname(exe))
        log("relaunched", exe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
