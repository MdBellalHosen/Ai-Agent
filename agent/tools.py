"""Actions the assistant may perform on the PC.

To add a feature: write a function, then add one tool(...) line to TOOL_LIST.
Anything risky must call confirm() first.
"""
import datetime as dt
import json
import os
import re
import threading
import urllib.parse
import webbrowser
from pathlib import Path

from . import voice
from .calculator import calculate
from .memory import add_note, read_notes, remember


def confirm(question):
    """Risky actions need a typed 'yes' from the keyboard. Voice cannot approve."""
    return input(f"\n[CONFIRM] {question} Type yes to allow: ").strip().lower() == "yes"


def open_app(app):
    apps = {"notepad": "notepad.exe", "calculator": "calc.exe", "paint": "mspaint.exe",
            "explorer": "explorer.exe", "chrome": "chrome.exe", "edge": "msedge.exe",
            "settings": "ms-settings:", "task manager": "taskmgr.exe"}
    key = app.strip().lower()
    if key not in apps:
        return f"Not in the allowed list: {', '.join(apps)}"
    os.startfile(apps[key])
    return f"Opened {key}"


def open_website(url):
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    if not confirm(f"Open {url}?"):
        return "User did not allow it"
    webbrowser.open(url)
    return f"Opened {url}"


def web_search(query, site="google"):
    q = urllib.parse.quote_plus(query)
    base = {"google": "https://www.google.com/search?q=",
            "youtube": "https://www.youtube.com/results?search_query="}
    webbrowser.open(base.get(site, base["google"]) + q)
    return f"Opened {site} search for {query}"


def volume(action, steps=5):
    import pyautogui
    key = {"up": "volumeup", "down": "volumedown", "mute": "volumemute"}.get(action)
    if not key:
        return "action must be up, down or mute"
    count = 1 if action == "mute" else max(1, min(int(steps), 50))
    pyautogui.press(key, presses=count)
    return f"Volume {action} done"


def take_screenshot():
    from PIL import ImageGrab
    folder = Path.home() / "Pictures" / "AI-Agent"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"shot_{dt.datetime.now():%Y%m%d_%H%M%S}.png"
    ImageGrab.grab().save(path)
    return f"Saved screenshot to {path}"


def search_folders():
    """Normal folders plus the OneDrive copies Windows 11 often uses instead."""
    home = Path.home()
    roots = [home, home / "OneDrive"]
    return [r / n for r in roots for n in ("Desktop", "Documents", "Downloads") if (r / n).is_dir()]


def find_file(name):
    name = name.strip().lower()
    if not name:
        return "Give part of a file name"
    hits = []
    for folder in search_folders():
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
            hits += [os.path.join(root, f) for f in files if name in f.lower()]
            if len(hits) >= 10:
                return "\n".join(hits[:10])
    return "\n".join(hits) or "No file found"


def lock_pc():
    import ctypes
    ctypes.windll.user32.LockWorkStation()
    return "PC locked"


def shutdown_pc(restart=False):
    word = "Restart" if restart else "Shut down"
    if not confirm(f"{word} the PC in 60 seconds?"):
        return "User did not allow it"
    os.system(f"shutdown {'/r' if restart else '/s'} /t 60")
    return f"{word} in 60 seconds. To stop it run: shutdown /a"


def set_reminder(minutes, message):
    minutes = float(minutes)
    if not 0 < minutes <= 1440:
        return "minutes must be between 0 and 1440"

    def ring():
        print(f"\n[REMINDER] {message}")
        voice.speak(message)  # stays silent when muted or in private mode

    timer = threading.Timer(minutes * 60, ring)
    timer.daemon = True
    timer.start()
    return f"Reminder set for {minutes:g} minutes (works while the program is open)"


def tool(func, description, required=(), **props):
    return func.__name__, func, {"type": "function", "function": {
        "name": func.__name__, "description": description,
        "parameters": {"type": "object", "properties": props, "required": list(required)}}}


S = {"type": "string"}
N = {"type": "number"}
TOOL_LIST = [
    tool(open_app, "Open an app: notepad, calculator, paint, explorer, chrome, edge, settings, task manager", ["app"], app=S),
    tool(open_website, "Open a website", ["url"], url=S),
    tool(web_search, "Search Google or YouTube in the browser", ["query"], query=S,
         site={"type": "string", "enum": ["google", "youtube"]}),
    tool(volume, "Change volume", ["action"], action={"type": "string", "enum": ["up", "down", "mute"]}, steps=N),
    tool(take_screenshot, "Save a screenshot"),
    tool(find_file, "Find files by name in Desktop, Documents, Downloads", ["name"], name=S),
    tool(lock_pc, "Lock the PC"),
    tool(shutdown_pc, "Shut down or restart the PC", restart={"type": "boolean"}),
    tool(add_note, "Save a note", ["text"], text=S),
    tool(read_notes, "Read recent notes"),
    tool(remember, "Remember a fact only when the user asks you to", ["fact"], fact=S),
    tool(set_reminder, "Remind the user after N minutes", ["minutes", "message"], minutes=N, message=S),
    tool(calculate, "Calculate a math expression, e.g. sqrt(2)*5+3^2. Trig uses radians", ["expression"], expression=S),
]
FUNCTIONS = {name: func for name, func, _ in TOOL_LIST}
SCHEMAS = [schema for _, _, schema in TOOL_LIST]


def run_tool(name, arguments):
    try:
        print(f"  [tool] {name} {arguments}")
        return str(FUNCTIONS[name](**json.loads(arguments or "{}")))
    except Exception as err:  # report the problem to the model instead of crashing
        return f"Tool error: {err}"
