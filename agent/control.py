"""Control the PC by voice without a command line: keys, typing, windows, media,
closing apps, system status, brightness, folders, and WhatsApp messages."""
import ctypes
import difflib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.parse
import webbrowser
from pathlib import Path

from . import config

CONTACTS_FILE = config.DATA / "contacts.json"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Typing or pressing keys into these could run commands, so Mira never does it.
COMMAND_WINDOW = re.compile(r"\b(powershell|command prompt|cmd(\.exe)?|terminal|regedit|registry editor|"
                            r"administrator|wsl|ubuntu|git bash|mingw|bash)\b", re.I)
KEYS = {"ctrl", "alt", "shift", "win", "enter", "esc", "tab", "space", "backspace", "delete", "up", "down",
        "left", "right", "home", "end", "pageup", "pagedown", "printscreen", "capslock", "insert",
        "playpause", "nexttrack", "prevtrack", "volumeup", "volumedown", "volumemute",
        *[f"f{i}" for i in range(1, 13)], *"abcdefghijklmnopqrstuvwxyz0123456789", "+", "-", "=", ",", "."}
ALIASES = {"control": "ctrl", "windows": "win", "escape": "esc", "return": "enter", "del": "delete",
           "pgup": "pageup", "pgdn": "pagedown", "plus": "+", "minus": "-"}
BLOCKED_COMBOS = [{"win", "r"}, {"win", "x"}]  # Run box and the admin menu
PROTECTED = {"explorer.exe", "svchost.exe", "csrss.exe", "winlogon.exe", "lsass.exe", "services.exe",
             "smss.exe", "wininit.exe", "dwm.exe", "system", "registry", "python.exe", "pythonw.exe",
             "msmpeng.exe", "searchhost.exe", "startmenuexperiencehost.exe", "taskmgr.exe"}


def window_title():
    if os.name != "nt":
        return ""
    user32 = ctypes.windll.user32
    handle = user32.GetForegroundWindow()
    size = user32.GetWindowTextLengthW(handle)
    buffer = ctypes.create_unicode_buffer(size + 1)
    user32.GetWindowTextW(handle, buffer, size + 1)
    return buffer.value


def unsafe_window():
    title = window_title()
    return title if (title.strip() == "Run" or COMMAND_WINDOW.search(title)) else ""


# ---------- keyboard ----------
def press_keys(keys):
    """keys like 'ctrl+s', 'alt+tab', 'win+d', 'enter', 'ctrl+shift+t'."""
    parts = [ALIASES.get(k.strip().lower(), k.strip().lower()) for k in re.split(r"\s*\+\s*(?=.)", str(keys))]
    parts = [p for p in parts if p]
    if not parts or any(p not in KEYS for p in parts):
        return f"Unknown key in '{keys}'"
    if any(combo <= set(parts) for combo in BLOCKED_COMBOS):
        return "That shortcut opens a command box, so it is not allowed"
    if unsafe_window():
        return "A command window is in front, so keys are not pressed for safety"
    import pyautogui
    pyautogui.hotkey(*["winleft" if p == "win" else p for p in parts])
    return f"Pressed {'+'.join(parts)}"


def type_text(text, press_enter=False):
    """Type into the window in front (works for Bangla too, through the clipboard)."""
    title = unsafe_window()
    if title:
        return f"'{title}' is a command window, so Mira does not type there"
    from .files import copy_to_clipboard
    import pyautogui
    copy_to_clipboard(str(text))
    time.sleep(0.15)
    pyautogui.hotkey("ctrl", "v")
    if press_enter:
        time.sleep(0.1)
        pyautogui.press("enter")
    return f"Typed into '{window_title() or 'the window in front'}'"


def window(action):
    keys = {"minimize": ("winleft", "down"), "maximize": ("winleft", "up"), "close": ("alt", "f4"),
            "switch": ("alt", "tab"), "show_desktop": ("winleft", "d"), "snap_left": ("winleft", "left"),
            "snap_right": ("winleft", "right"), "task_view": ("winleft", "tab"),
            "new_tab": ("ctrl", "t"), "close_tab": ("ctrl", "w"), "next_tab": ("ctrl", "tab"),
            "zoom_in": ("ctrl", "+"), "zoom_out": ("ctrl", "-"), "refresh": ("f5",), "fullscreen": ("f11",)}
    if action not in keys:
        return f"action must be one of {', '.join(keys)}"
    title = window_title()
    import pyautogui
    pyautogui.hotkey(*keys[action])
    return f"{action.replace('_', ' ')} done" + (f" ({title})" if title and action == "close" else "")


def media(action):
    key = {"play_pause": "playpause", "next": "nexttrack", "previous": "prevtrack", "stop": "stop"}.get(action)
    if not key:
        return "action must be play_pause, next, previous or stop"
    import pyautogui
    pyautogui.press(key)
    return f"Media {action.replace('_', ' ')}"


def scroll(direction="down", amount=5):
    import pyautogui
    clicks = max(1, min(int(amount or 5), 30)) * 120
    pyautogui.scroll(clicks if direction == "up" else -clicks)
    return f"Scrolled {direction}"


# ---------- apps and system ----------
def running_apps():
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                         timeout=15, creationflags=NO_WINDOW).stdout
    names = {line.split('","')[0].strip('"') for line in out.splitlines() if line.startswith('"')}
    return sorted(n for n in names if n.lower() not in PROTECTED)


def close_app(app):
    """Closes an app politely (it can still ask to save). Asks the user first."""
    from .tools import confirm
    key = re.sub(r"[^a-z0-9]", "", str(app).lower().replace(".exe", ""))
    if not key:
        return "Say which app to close"
    names = running_apps()
    plain = {re.sub(r"[^a-z0-9]", "", n.lower().replace(".exe", "")): n for n in names}
    match = plain.get(key) or next((n for k, n in plain.items() if key in k), None)
    if not match:
        close = difflib.get_close_matches(key, list(plain), n=1, cutoff=0.7)
        match = plain[close[0]] if close else None
    if not match:
        return f"'{app}' is not running"
    if not confirm(f"Close {match}? Unsaved work may ask to be saved."):
        return "User did not allow it"
    subprocess.run(["taskkill", "/IM", match], capture_output=True, timeout=15, creationflags=NO_WINDOW)
    return f"Asked {match} to close"


class _Power(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_byte), ("BatteryFlag", ctypes.c_byte),
                ("BatteryLifePercent", ctypes.c_byte), ("SystemStatusFlag", ctypes.c_byte),
                ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]


class _Memory(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def system_status():
    """Battery, memory and disk space."""
    lines = []
    if os.name == "nt":
        power = _Power()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(power)):
            percent = power.BatteryLifePercent & 0xFF
            if percent != 255:
                lines.append(f"Battery {percent}%, " + ("charging" if power.ACLineStatus == 1 else "on battery"))
        memory = _Memory()
        memory.dwLength = ctypes.sizeof(_Memory)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
            lines.append(f"Memory in use {memory.dwMemoryLoad}% of {memory.ullTotalPhys / 2**30:.1f} GB")
    disk = shutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/")
    lines.append(f"Disk free {disk.free / 2**30:.0f} GB of {disk.total / 2**30:.0f} GB")
    return "\n".join(lines)


def brightness(level):
    """Screen brightness 0-100 (laptop screens)."""
    level = max(0, min(int(level), 100))
    script = ("(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods)"
              f" | Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=1; Brightness={level}}}")
    done = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True,
                          timeout=20, creationflags=NO_WINDOW)
    return f"Brightness {level}%" if done.returncode == 0 else "This screen does not allow brightness control"


def open_folder(name="Downloads"):
    from .tools import search_folders
    key = str(name).strip().lower()
    home = Path.home()
    places = {p.name.lower(): p for p in search_folders()}
    for extra in ("Pictures", "Music", "Videos"):
        places.setdefault(extra.lower(), home / extra)
    if key in ("this pc", "computer", "my computer"):
        subprocess.Popen(["explorer.exe", "shell:MyComputerFolder"])
        return "Opened This PC"
    path = places.get(key)
    if not path or not path.is_dir():
        return f"Folder must be one of: This PC, {', '.join(p.title() for p in places)}"
    os.startfile(str(path))
    return f"Opened {path}"


def sleep_pc():
    from .tools import confirm
    if not confirm("Put the PC to sleep now?"):
        return "User did not allow it"
    subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
    return "Going to sleep"


# ---------- WhatsApp ----------
def load_contacts():
    try:
        data = json.loads(CONTACTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def phone_number(text):
    """Bangladesh numbers: 01XXXXXXXXX becomes 8801XXXXXXXXX."""
    digits = re.sub(r"\D", "", str(text))
    if len(digits) == 11 and digits.startswith("01"):
        digits = "88" + digits
    return digits if 10 <= len(digits) <= 15 else ""


def save_contact(name, phone):
    """Save a WhatsApp number on this PC, only when the user gives it."""
    number = phone_number(phone)
    name = str(name).strip()[:60]
    if not number or not name:
        return "Need a name and a phone number like 01712345678"
    config.DATA.mkdir(exist_ok=True)
    contacts = load_contacts()
    contacts[name] = number
    CONTACTS_FILE.write_text(json.dumps(contacts, ensure_ascii=False, indent=1), encoding="utf-8")
    return f"Saved {name}: +{number}"


def list_contacts():
    contacts = load_contacts()
    return "\n".join(f"{n}: +{p}" for n, p in contacts.items()) or "No contacts saved yet"


def find_contact(to):
    contacts = load_contacts()
    number = phone_number(to)
    if number:
        return next((n for n, p in contacts.items() if p == number), f"+{number}"), number
    lower = {n.lower(): n for n in contacts}
    key = str(to).strip().lower()
    name = lower.get(key) or next((n for k, n in lower.items() if key in k or k in key), None)
    if not name:
        close = difflib.get_close_matches(key, list(lower), n=1, cutoff=0.75)
        name = lower[close[0]] if close else None
    return (name, contacts[name]) if name else (None, None)


def desktop_whatsapp():
    from . import apps
    return any("whatsapp" in n.lower() for n in apps.installed())


def whatsapp_message(to, message):
    """Send a WhatsApp message to a saved contact or a phone number. Asks the user first."""
    from .tools import confirm
    name, number = find_contact(to)
    if not number:
        return (f"No WhatsApp number saved for '{to}'. Ask the user for the number, "
                "then save it with save_contact and try again.")
    text = str(message).strip()
    if not text:
        return "The message is empty"
    if not confirm(f"WhatsApp এ {name} (+{number}) কে পাঠাবো:\n\"{text}\""):
        return "User did not allow it"
    query = urllib.parse.urlencode({"phone": number, "text": text}, quote_via=urllib.parse.quote)
    use_app = config.env("WHATSAPP", "auto").lower() != "web" and desktop_whatsapp()
    if use_app:
        os.startfile("whatsapp://send?" + query)
    else:
        webbrowser.open("https://web.whatsapp.com/send?" + query)
    if config.env("WHATSAPP_AUTOSEND", "on").lower() in ("off", "no", "0", "false"):
        return f"Opened WhatsApp with the message to {name}. The user presses Enter to send."
    wait = float(config.env("WHATSAPP_WAIT", "4" if use_app else "12"))
    deadline = time.monotonic() + wait + 20
    time.sleep(wait)
    while time.monotonic() < deadline and "whatsapp" not in window_title().lower():
        time.sleep(0.5)
    if "whatsapp" not in window_title().lower():
        return f"Opened WhatsApp with the message to {name}, but could not see the window. The user should press Enter."
    import pyautogui
    pyautogui.press("enter")
    return f"Sent to {name} on WhatsApp (pressed Enter). Ask the user to check it went."
