# -*- coding: utf-8 -*-
"""Locate a WorkBuddy desktop installation on this machine.

Nothing here is machine specific. Resolution order for the install root:

  1. ``WORKBUDDY_HOME`` environment variable (explicit override, always wins)
  2. the running ``WorkBuddy.exe`` process image path (works even when the app
     was installed somewhere unusual)
  3. the uninstall registry entries written by the installer
  4. the handful of directories the Windows installer normally uses

If none of those hit, callers get ``None`` and are expected to fail with a
message that names ``WORKBUDDY_HOME`` instead of guessing.

The IPC client library (``workbuddy_ipc``) ships *inside* the installed app.
It is deliberately never vendored into this repository: the bridge imports it
from the installation so it always matches the running desktop build.
"""

import os
import sys

# Relative location of the bundled WBIPC Python client inside an install.
IPC_LIB_REL = os.path.join(
    "resources", "app.asar.unpacked", "resources", "plugins",
    "workbuddy-builtin", "skills", "library")

_DEFAULT_DIRS = [
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "WorkBuddy"),
    os.path.join(os.environ.get("PROGRAMFILES", ""), "WorkBuddy"),
    os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "WorkBuddy"),
    r"C:\Program Files\WorkBuddy",
    r"C:\Program Files (x86)\WorkBuddy",
]

_UNINSTALL_KEYS = [
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
]


def _looks_like_install(path):
    return bool(path) and os.path.isfile(os.path.join(path, "WorkBuddy.exe"))


def _from_registry():
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:  # pragma: no cover - non-Windows
        return None
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for sub in _UNINSTALL_KEYS:
            try:
                key = winreg.OpenKey(root, sub)
            except OSError:
                continue
            with key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, name) as entry:
                            display = ""
                            try:
                                display = winreg.QueryValueEx(entry, "DisplayName")[0]
                            except OSError:
                                pass
                            if "workbuddy" not in str(display).lower():
                                continue
                            loc = winreg.QueryValueEx(entry, "InstallLocation")[0]
                            if _looks_like_install(loc):
                                return loc
                    except OSError:
                        continue
    return None


def _from_running_process():
    """Ask Windows for the image path of a live WorkBuddy.exe."""
    if sys.platform != "win32":
        return None
    try:
        import subprocess
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-Process WorkBuddy -ErrorAction SilentlyContinue |"
             " Select-Object -First 1).Path"],
            capture_output=True, text=True, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        path = (out.stdout or "").strip()
        if path and _looks_like_install(os.path.dirname(path)):
            return os.path.dirname(path)
    except Exception:
        pass
    return None


def find_home():
    """Return the WorkBuddy install root, or ``None`` when not found."""
    env = (os.environ.get("WORKBUDDY_HOME") or "").strip().strip('"')
    if env:
        # Trust an explicit override even if the exe is missing, so the caller
        # can report a precise error instead of "not installed".
        return env
    for probe in (_from_running_process, _from_registry):
        hit = probe()
        if hit:
            return hit
    for cand in _DEFAULT_DIRS:
        if _looks_like_install(cand):
            return cand
    return None


def find_installs():
    """Every WorkBuddy install on this machine, de-duplicated.

    Several builds can coexist (the domestic app and the international one are
    separate installs with separate sign-ins). ``find_home`` answers "which one
    does this process serve"; this answers "what is on the disk".
    """
    seen, out = set(), []
    cands = [
        (os.environ.get("WORKBUDDY_HOME") or "").strip().strip('"'),
        _from_running_process() or "",
    ]
    cands += [d for d in _DEFAULT_DIRS if d]
    for cand in cands:
        if not cand or not _looks_like_install(cand):
            continue
        key = os.path.normcase(os.path.abspath(cand))
        if key in seen:
            continue
        seen.add(key)
        out.append(os.path.abspath(cand))
    for loc in _registry_install_locations():
        key = os.path.normcase(os.path.abspath(loc))
        if key not in seen and _looks_like_install(loc):
            seen.add(key)
            out.append(os.path.abspath(loc))
    return out


def _registry_install_locations():
    """All uninstall entries whose DisplayName mentions WorkBuddy."""
    if sys.platform != "win32":
        return []
    try:
        import winreg
    except ImportError:  # pragma: no cover - non-Windows
        return []
    found = []
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for sub in _UNINSTALL_KEYS:
            try:
                key = winreg.OpenKey(root, sub)
            except OSError:
                continue
            with key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, name) as entry:
                            display = ""
                            try:
                                display = winreg.QueryValueEx(entry, "DisplayName")[0]
                            except OSError:
                                pass
                            if "workbuddy" not in str(display).lower():
                                continue
                            try:
                                loc = winreg.QueryValueEx(entry, "InstallLocation")[0]
                            except OSError:
                                continue
                            if loc:
                                found.append(str(loc))
                    except OSError:
                        continue
    return found


def ipc_lib_dir(home=None):
    """Directory that must be on ``sys.path`` to ``import workbuddy_ipc``.

    Falls back to the library bundled with *any* installed build: the WBIPC
    client is generic pipe code, so a second edition whose install root was not
    auto-detected still gets a working client instead of a hard failure.
    """
    home = home or find_home()
    cands = []
    if home:
        cands.append(home)
    cands += [h for h in find_installs() if os.path.normcase(os.path.abspath(h)) !=
              os.path.normcase(os.path.abspath(home or ""))]
    for h in cands:
        p = os.path.join(h, IPC_LIB_REL)
        if os.path.isdir(os.path.join(p, "workbuddy_ipc")):
            return p
    return None


def exe_path(home=None):
    home = home or find_home()
    if not home:
        return None
    p = os.path.join(home, "WorkBuddy.exe")
    return p if os.path.isfile(p) else None


def desktop_install_hint():
    return (
        "WorkBuddy desktop was not found.\n"
        "  * Install and sign in to the WorkBuddy desktop app, then retry.\n"
        "  * If it lives somewhere unusual, set WORKBUDDY_HOME to the folder\n"
        "    that contains WorkBuddy.exe (e.g. set WORKBUDDY_HOME=D:\\Apps\\WorkBuddy)."
    )
