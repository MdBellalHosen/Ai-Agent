"""Apps installed on this PC (from the Start menu), plus nicknames the user saves."""
import difflib
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from . import config

NICKNAMES_FILE = config.DATA / "apps.json"  # {"nickname": "app name"}
BUILT_IN = {"notepad": "notepad.exe", "calculator": "calc.exe", "paint": "mspaint.exe",
            "explorer": "explorer.exe", "file explorer": "explorer.exe", "chrome": "chrome.exe",
            "edge": "msedge.exe", "settings": "ms-settings:", "task manager": "taskmgr.exe"}
# Apps that change or break the system are never opened by voice or chat.
BLOCKED = ("uninstall", "remove", "repair", "reset", "recovery", "installer", "setup",
           "regedit", "registry", "command prompt", "powershell", "terminal", "cmd",
           "disk management", "diskpart", "format", "bitlocker", "administrative", "windows tools",
           "control panel", "services", "group policy", "system configuration")
REFRESH = 600  # seconds

_cache = {"time": 0.0, "apps": {}}
_lock = threading.Lock()

LIST_SCRIPT = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
               "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress")


def normal(name):
    name = re.sub(r"[^\w\s+#]", " ", str(name).lower())
    name = re.sub(r"\b(app|application|the)\b", " ", name)
    return " ".join(name.split())


def blocked(name):
    name = normal(name)
    return any(re.search(rf"\b{re.escape(word)}\b", name) for word in BLOCKED)


def start_menu():
    """{name: AppID} from Windows' own Start menu list (desktop and Store apps)."""
    if os.name != "nt":
        return {}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    out = subprocess.run(["powershell", "-NoProfile", "-Command", LIST_SCRIPT], capture_output=True,
                         timeout=30, check=True, creationflags=flags).stdout.decode("utf-8", "replace")
    items = json.loads(out or "[]")
    if isinstance(items, dict):
        items = [items]
    return {i["Name"].strip(): i["AppID"] for i in items
            if i.get("Name") and i.get("AppID") and not blocked(i["Name"])}


def shortcut_folders():
    roots = [os.environ.get("ProgramData"), os.environ.get("APPDATA")]
    return [Path(r, "Microsoft", "Windows", "Start Menu", "Programs") for r in roots if r]


def start_menu_shortcuts():
    """Backup list: the .lnk files in the Start Menu folders (desktop apps only)."""
    found = {}
    for folder in shortcut_folders():
        if folder.is_dir():
            for link in folder.rglob("*.lnk"):
                if not blocked(link.stem):
                    found.setdefault(link.stem.strip(), str(link))
    return found


def installed(refresh=False):
    """{name: target}. Store apps come as shell:AppsFolder targets, others as .lnk paths."""
    with _lock:
        if refresh or time.monotonic() - _cache["time"] > REFRESH:
            found = {}
            try:
                found = start_menu_shortcuts()
            except Exception as err:
                print(f"  [app list problem] {err}")
            try:
                found.update({n: "shell:AppsFolder\\" + a for n, a in start_menu().items()})
            except Exception as err:
                print(f"  [app list problem] {err}")
            _cache["apps"] = found
            _cache["time"] = time.monotonic()
        return _cache["apps"]


def preload():
    threading.Thread(target=installed, daemon=True).start()


def nicknames():
    try:
        data = json.loads(NICKNAMES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def find(name, follow=True):
    """Returns (display name, target) or (None, close names)."""
    key = normal(name)
    if not key or blocked(key):
        return None, []
    if follow:
        nick = {normal(k): v for k, v in nicknames().items()}
        if key in nick:
            return find(nick[key], follow=False)
    if key in BUILT_IN:
        return key, BUILT_IN[key]
    apps = installed()
    by_name = {normal(n): n for n in apps}
    if key in by_name:
        return by_name[key], apps[by_name[key]]
    starts = [n for k, n in by_name.items() if k.startswith(key + " ") or k.startswith(key)]
    inside = [n for k, n in by_name.items() if re.search(rf"\b{re.escape(key)}\b", k)]
    for group in (starts, inside):
        if group:
            best = min(group, key=len)
            return best, apps[best]
    close = difflib.get_close_matches(key, list(by_name) + list(BUILT_IN), n=5, cutoff=0.6)
    if close and difflib.SequenceMatcher(None, key, close[0]).ratio() >= 0.8:
        return find(close[0], follow=False)
    return None, [by_name.get(c, c) for c in close]


def launch(target):
    if target.startswith("shell:AppsFolder\\"):
        subprocess.Popen(["explorer.exe", target])
    else:
        os.startfile(target)


def open_app(app):
    name, target = find(app)
    if name is None:
        if blocked(app):
            return "This app is not allowed for safety. The user can open it by hand."
        hint = f" Close names: {', '.join(target)}" if target else ""
        return f"Could not find '{app}' on this PC.{hint} Use list_apps to search."
    launch(target)
    return f"Opened {name}"


def list_apps(search=""):
    names = sorted(set(installed()) | set(BUILT_IN), key=str.lower)
    if search:
        key = normal(search)
        names = [n for n in names if key in normal(n)] or difflib.get_close_matches(
            search, names, n=10, cutoff=0.4)
    names = names[:40]
    saved = nicknames()
    lines = [", ".join(names) or "No app found"]
    if saved:
        lines.append("Nicknames: " + ", ".join(f"{k} = {v}" for k, v in saved.items()))
    return "\n".join(lines)


def save_nickname(nickname, app):
    name, target = find(app)
    if name is None:
        return f"Could not find '{app}' on this PC, nickname not saved."
    nick = str(nickname).strip()[:40]
    if not normal(nick):
        return "Nickname is empty"
    config.DATA.mkdir(exist_ok=True)
    data = nicknames()
    data[nick] = name
    NICKNAMES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"Saved: '{nick}' opens {name}"
