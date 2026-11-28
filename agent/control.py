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
    from .screen import focus_target
    focus_target()
    if unsafe_window():
        return "A command window is in front, so keys are not pressed for safety"
    import pyautogui
    pyautogui.hotkey(*["winleft" if p == "win" else p for p in parts])
    return f"Pressed {'+'.join(parts)}"


def type_text(text, press_enter=False):
    """Type into the app the user was using (works for Bangla too, through the clipboard)."""
    from .screen import focus_target
    focus_target()
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
    from .screen import focus_target
    title = focus_target() if action not in ("show_desktop", "task_view", "switch") else window_title()
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


# ---------- files ----------
SETTINGS = {"wifi": "network-wifi", "bluetooth": "bluetooth", "display": "display", "sound": "sound",
            "battery": "batterysaver", "notifications": "notifications", "focus": "quiethours",
            "night_light": "nightlight", "wallpaper": "personalization-background", "theme": "themes",
            "apps": "appsfeatures", "startup_apps": "startupapps", "updates": "windowsupdate",
            "storage": "storagesense", "mouse": "mousetouchpad", "keyboard": "keyboard",
            "language": "regionlanguage", "date_time": "dateandtime", "privacy": "privacy",
            "camera": "privacy-webcam", "microphone": "privacy-microphone", "vpn": "network-vpn",
            "hotspot": "network-mobilehotspot", "airplane_mode": "network-airplanemode",
            "printers": "printers", "about": "about"}
RUNS_CODE = {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".msi", ".msix",
             ".scr", ".com", ".lnk", ".reg", ".hta", ".jar", ".py", ".pyw", ".appx", ".url"}


def open_settings(page):
    """Open a Windows Settings page, e.g. wifi, bluetooth, display, night_light, wallpaper."""
    key = str(page).strip().lower().replace(" ", "_").replace("-", "_")
    if key not in SETTINGS:
        return f"page must be one of: {', '.join(SETTINGS)}"
    os.startfile("ms-settings:" + SETTINGS[key])
    return f"Opened {key.replace('_', ' ')} settings"


def user_roots():
    from .tools import search_folders
    home = Path.home()
    roots = list(search_folders()) + [home / n for n in ("Pictures", "Music", "Videos")]
    return [r for r in roots if r.is_dir()]


def inside_user_folders(path):
    path = Path(path).resolve()
    return any(path == r.resolve() or path.is_relative_to(r.resolve()) for r in user_roots())


def resolve(name, must_exist=True):
    """A file or folder in Desktop, Documents, Downloads, Pictures, Music or Videos."""
    text = str(name).strip().strip('"')
    if not text:
        return None, "Give a file or folder name"
    path = Path(text).expanduser()
    if not path.is_absolute():
        first, *rest = [part for part in re.split(r"[\\/]+", text) if part]
        root = next((r for r in user_roots() if r.name.lower() == first.lower()), None)
        if root:
            path = root.joinpath(*rest)
        elif must_exist:
            from .tools import find_file
            hits = [h for h in find_file(text).splitlines() if os.path.exists(h)]
            if len(hits) != 1:
                return None, (f"Found {len(hits)} matches for '{name}'" + (":\n" + "\n".join(hits[:8]) if hits else "")
                              + ". Give the folder too, e.g. Downloads\\file.pdf")
            path = Path(hits[0])
        else:
            return None, "Give where it goes, e.g. Documents\\Notes"
    if not inside_user_folders(path):
        return None, "Mira only works with files in Desktop, Documents, Downloads, Pictures, Music and Videos"
    if must_exist and not path.exists():
        return None, f"'{path}' does not exist"
    return path, ""


def to_recycle_bin(path):
    class Op(ctypes.Structure):
        _fields_ = [("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint), ("pFrom", ctypes.c_wchar_p),
                    ("pTo", ctypes.c_wchar_p), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", ctypes.c_bool),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_wchar_p)]
    op = Op(None, 3, str(path) + "\0", None, 0x0040 | 0x0010 | 0x0004 | 0x0400, False, None, None)
    if ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) or op.fAnyOperationsAborted:
        raise OSError("Recycle Bin move failed")


def file_action(action, path, target=""):
    """create_folder, rename, move, copy, or delete (to the Recycle Bin, asks first), inside the user's folders."""
    from .tools import confirm
    if action == "create_folder":
        folder, problem = resolve(path, must_exist=False)
        if problem:
            return problem
        folder.mkdir(parents=True, exist_ok=True)
        return f"Created folder {folder}"
    source, problem = resolve(path)
    if problem:
        return problem
    if action == "delete":
        if not confirm(f"Move '{source.name}' to the Recycle Bin? You can restore it from there."):
            return "User did not allow it"
        to_recycle_bin(source)
        return f"Moved {source.name} to the Recycle Bin"
    if action == "rename":
        new_name = Path(str(target)).name
        if not new_name or new_name in (".", ".."):
            return "Give the new name"
        dest = source.with_name(new_name)
    elif action in ("move", "copy"):
        dest, problem = resolve(target, must_exist=False)
        if problem:
            return problem
        if dest.is_dir() or not dest.suffix:
            dest.mkdir(parents=True, exist_ok=True)
            dest = dest / source.name
    else:
        return "action must be create_folder, rename, move, copy or delete"
    if dest.exists():
        return f"'{dest}' already exists, nothing was changed"
    if action == "copy":
        (shutil.copytree if source.is_dir() else shutil.copy2)(source, dest)
    else:
        shutil.move(str(source), str(dest))
    return f"{ {'rename': 'Renamed', 'move': 'Moved', 'copy': 'Copied'}[action] } {source.name} to {dest}"


def open_file(name):
    """Open a document, photo, song or video with its normal app. Programs and scripts are not opened."""
    path, problem = resolve(name)
    if problem:
        return problem
    if path.is_file() and path.suffix.lower() in RUNS_CODE:
        return "That file runs a program, so Mira does not open it. The user can open it by hand."
    os.startfile(str(path))
    return f"Opened {path}"


def list_folder(name="Downloads"):
    path, problem = resolve(name)
    if problem:
        return problem
    if not path.is_dir():
        return f"{path} is a file"
    items = sorted(path.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:40]
    return "\n".join(("[folder] " if i.is_dir() else "") + i.name for i in items) or "Empty folder"


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
