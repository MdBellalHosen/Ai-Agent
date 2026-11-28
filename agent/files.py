"""Documents (PDF, text), clipboard, and tidying a folder into sub-folders."""
import datetime as dt
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import config

UPLOADS = config.DATA / "uploads"
UNDO_FILE = config.DATA / "organize_undo.json"
MAX_TEXT = 15000
TEXT_TYPES = {".txt", ".md", ".csv", ".json", ".py", ".html", ".css", ".js"}
CATEGORIES = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".svg"},
    "Documents": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".md", ".epub"},
    "Sheets and Slides": {".xls", ".xlsx", ".csv", ".ppt", ".pptx", ".ods", ".odp"},
    "Videos": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm"},
    "Music": {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "Installers": {".exe", ".msi", ".msix", ".appx"},
    "Code": {".py", ".js", ".html", ".css", ".json", ".java", ".c", ".cpp", ".ipynb"},
}
SKIP = {".lnk", ".url", ".ini", ".crdownload", ".part", ".tmp", ".partial", ".download"}


# ---------- documents ----------
def save_upload(name, data):
    """A document attached in the app is kept in data/uploads so the read_document tool can open it."""
    name = re.split(r"[\\/]", str(name))[-1]  # drop any folder part, Windows or not
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name).strip(" .")[:120] or "document"
    if Path(name).suffix.lower() not in TEXT_TYPES | {".pdf"}:
        raise ValueError("shudhu PDF ba text file deya jay")
    UPLOADS.mkdir(parents=True, exist_ok=True)
    path = UPLOADS / name
    stem, n = path.stem, 1
    while path.exists():
        path = UPLOADS / f"{stem} ({n}){path.suffix}"
        n += 1
    path.write_bytes(data)
    return path


def locate(name):
    from .tools import search_folders
    path = Path(str(name).strip().strip('"')).expanduser()
    if path.is_absolute():
        return path if path.is_file() else None
    key = name.strip().lower()
    for folder in [UPLOADS, *search_folders()]:
        if not folder.is_dir():
            continue
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
            for f in files:
                if key in f.lower() and Path(f).suffix.lower() in TEXT_TYPES | {".pdf"}:
                    return Path(root, f)
    return None


def read_document(name, start_page=1, pages=10):
    """Text of a PDF or text file, a few pages at a time."""
    path = locate(name)
    if not path:
        return f"Could not find a PDF or text file matching '{name}' in Desktop, Documents, Downloads."
    if path.suffix.lower() != ".pdf":
        text = path.read_text(encoding="utf-8", errors="replace")
        return f"[{path.name}]\n{text[:MAX_TEXT]}" + ("\n[...cut]" if len(text) > MAX_TEXT else "")
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    total = len(reader.pages)
    first = max(1, min(int(start_page or 1), total))
    last = min(total, first + max(1, min(int(pages or 10), 30)) - 1)
    parts, size = [], 0
    for number in range(first, last + 1):
        text = (reader.pages[number - 1].extract_text() or "").strip()
        parts.append(f"--- page {number} ---\n{text}")
        size += len(text)
        if size > MAX_TEXT:
            last = number
            break
    body = "\n".join(parts)[:MAX_TEXT]
    if not body.replace("-", "").replace("page", "").strip(" \n0123456789"):
        body += "\n(No text found. It may be a scanned PDF: ask the user for a photo of the page.)"
    more = f" Next: start_page={last + 1}." if last < total else ""
    return f"[{path.name}: pages {first}-{last} of {total}.{more}]\n{body}"


# ---------- clipboard ----------
def powershell(script, text=None):
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    done = subprocess.run(["powershell", "-NoProfile", "-Command",
                           "[Console]::InputEncoding = [Text.Encoding]::UTF8; "
                           "[Console]::OutputEncoding = [Text.Encoding]::UTF8; " + script],
                          input=(text or "").encode("utf-8"), capture_output=True, timeout=20,
                          check=True, creationflags=flags)
    return done.stdout.decode("utf-8", "replace")


def read_clipboard():
    """Text the user copied (Ctrl+C). Only when the user asks, e.g. to translate it."""
    text = powershell("Get-Clipboard -Raw").strip()
    return text[:6000] if text else "Clipboard is empty or has no text"


def copy_to_clipboard(text):
    powershell("Set-Clipboard -Value ([Console]::In.ReadToEnd())", str(text))
    return "Copied to clipboard. The user can paste it with Ctrl+V"


# ---------- tidy a folder ----------
def category(path):
    ext = path.suffix.lower()
    if ext in SKIP or path.name.startswith(".") or path.name.lower() == "desktop.ini":
        return None
    for name, types in CATEGORIES.items():
        if ext in types:
            return name
    return "Others"


def target_folder(folder):
    from .tools import search_folders
    key = str(folder or "Downloads").strip().lower()
    for path in search_folders():
        if path.name.lower() == key:
            return path
    return None


def organize_folder(folder="Downloads"):
    """Moves loose files in Desktop, Documents or Downloads into type folders. Asks first; can be undone."""
    from .tools import confirm
    path = target_folder(folder)
    if not path:
        return "Only Desktop, Documents or Downloads can be organized"
    plan = {}
    for item in path.iterdir():
        if item.is_file() and category(item):
            plan.setdefault(category(item), []).append(item)
    if not plan:
        return f"Nothing to organize in {path}"
    count = sum(len(v) for v in plan.values())
    summary = ", ".join(f"{k} ({len(v)})" for k, v in sorted(plan.items()))
    if not confirm(f"Move {count} files in {path} into folders: {summary}? Nothing is deleted."):
        return "User did not allow it"
    moved = []
    for name, items in plan.items():
        dest_dir = path / name
        dest_dir.mkdir(exist_ok=True)
        for item in items:
            dest = dest_dir / item.name
            n = 1
            while dest.exists():
                dest = dest_dir / f"{item.stem} ({n}){item.suffix}"
                n += 1
            try:
                shutil.move(str(item), str(dest))
                moved.append([str(dest), str(item)])
            except OSError as err:  # file open in another app
                print(f"  [organize problem] {err}")
    config.DATA.mkdir(exist_ok=True)
    UNDO_FILE.write_text(json.dumps({"time": f"{dt.datetime.now():%Y-%m-%d %H:%M}", "moves": moved},
                                    ensure_ascii=False, indent=1), encoding="utf-8")
    return f"Moved {len(moved)} of {count} files in {path}: {summary}. It can be undone with undo_organize."


def undo_organize():
    try:
        log = json.loads(UNDO_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "Nothing to undo"
    back = 0
    for new, old in reversed(log.get("moves", [])):
        if Path(new).exists() and not Path(old).exists():
            shutil.move(new, old)
            back += 1
    for new, _ in log.get("moves", []):  # remove folders left empty
        try:
            Path(new).parent.rmdir()
        except OSError:
            pass
    UNDO_FILE.unlink()
    return f"Moved {back} files back to where they were ({log.get('time')})"
