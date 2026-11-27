"""Facts and notes stored only on this PC."""
import datetime as dt
import json

from . import config


def load_memory():
    try:
        facts = json.loads(config.MEMORY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return facts if isinstance(facts, list) else []


def remember(fact):
    config.DATA.mkdir(exist_ok=True)
    facts = load_memory() + [fact]
    config.MEMORY_FILE.write_text(
        json.dumps(facts[-50:], ensure_ascii=False, indent=2), encoding="utf-8")
    return "Remembered"


def add_note(text):
    config.DATA.mkdir(exist_ok=True)
    with config.NOTES_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{dt.datetime.now():%Y-%m-%d %H:%M}] {text}\n")
    return "Note saved"


def read_notes():
    if not config.NOTES_FILE.exists():
        return "No notes yet"
    return config.NOTES_FILE.read_text(encoding="utf-8")[-2000:]
