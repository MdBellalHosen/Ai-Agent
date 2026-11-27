"""Actions the assistant may perform on the PC.

To add a feature: write a function, then add one tool(...) line to TOOL_LIST.
Anything risky must call confirm() first.
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

from . import apps, voice
from .calculator import calculate
from .memory import add_note, read_notes, remember


# The window app replaces these: confirm -> a Yes/No button, announce -> chat message.
hooks = {"confirm": None, "announce": None, "tool": None}
reminders = []


def confirm(question):
    """Risky actions need a typed 'yes' or a button click. Voice cannot approve."""
    if hooks["confirm"]:
        return bool(hooks["confirm"](question))
    return input(f"\n[CONFIRM] {question} Type yes to allow: ").strip().lower() == "yes"


def reminders_pending():
    reminders[:] = [t for t in reminders if t.is_alive()]
    return bool(reminders)


def math_solve(task, expression, variable="", lower="", upper="", point="", order=1):
    """Exact math with sympy, in its own process so it can be stopped after 20 seconds."""
    request = {"task": task, "expression": expression, "variable": variable,
               "lower": lower, "upper": upper, "point": point, "order": order}
    script = Path(__file__).with_name("mathsolve.py")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        done = subprocess.run([sys.executable, "-I", str(script)], input=json.dumps(request),
                              capture_output=True, text=True, encoding="utf-8", timeout=20,
                              creationflags=flags)
    except subprocess.TimeoutExpired:
        return "Math took too long. Try a simpler form or solve step by step."
    try:
        answer = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return f"Math problem: {(done.stderr or 'no answer')[-300:]}"
    return answer.get("result") or f"Math problem: {answer.get('error')}"


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
        if hooks["announce"]:
            return hooks["announce"](message)
        print(f"\n[REMINDER] {message}")
        voice.speak(message)  # stays silent when muted or in private mode

    timer = threading.Timer(minutes * 60, ring)
    timer.daemon = True
    timer.start()
    reminders.append(timer)
    return f"Reminder set for {minutes:g} minutes (works while the program is open)"


def tool(func, description, required=(), **props):
    return func.__name__, func, {"type": "function", "function": {
        "name": func.__name__, "description": description,
        "parameters": {"type": "object", "properties": props, "required": list(required)}}}


S = {"type": "string"}
N = {"type": "number"}
TOOL_LIST = [
    tool(apps.open_app, "Open any app installed on this PC by name, e.g. WhatsApp, VS Code, Spotify, Word, "
         "notepad, calculator. Use the English app name, or a nickname the user saved", ["app"], app=S),
    tool(apps.list_apps, "List apps installed on this PC, optionally only names containing search", search=S),
    tool(apps.save_nickname, "Save a short name the user wants to use for an app, only when the user asks",
         ["nickname", "app"], nickname=S, app=S),
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
    tool(math_solve, "Exact algebra and calculus with sympy. Use it to solve and to check answers. "
         "solve: equations like 'x^2-5x+6=0', a system 'x+y=5; x-y=1'. diff: derivative (order). "
         "integrate: give lower and upper for a definite integral. limit: point like '0' or 'oo'. "
         "Also simplify, factor, expand, evaluate. Use * or plain juxtaposition like 2x, ^ for powers",
         ["task", "expression"],
         task={"type": "string", "enum": ["solve", "simplify", "factor", "expand", "diff",
                                          "integrate", "limit", "evaluate"]},
         expression=S, variable=S, lower=S, upper=S, point=S, order=N),
]
# Pure math tools: allowed even when a picture is attached, they cannot touch the PC.
SAFE_WITH_IMAGE = {"calculate", "math_solve"}
FUNCTIONS = {name: func for name, func, _ in TOOL_LIST}
SCHEMAS = [schema for _, _, schema in TOOL_LIST]


def run_tool(name, arguments):
    try:
        print(f"  [tool] {name} {arguments}")
        if hooks["tool"]:
            hooks["tool"](name)
        return str(FUNCTIONS[name](**json.loads(arguments or "{}")))
    except Exception as err:  # report the problem to the model instead of crashing
        return f"Tool error: {err}"
