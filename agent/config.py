"""Settings read from the .env file in the project folder."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent
load_dotenv(BASE / ".env", encoding="utf-8-sig")  # also accepts a Notepad BOM


def env(name, default=""):
    return os.getenv(name, "").strip() or default


NAME = env("AGENT_NAME", "Mira")
USER = env("USER_NAME", "bondhu")
VOICE_BN = env("VOICE_BN", "bn-BD-NabanitaNeural")
VOICE_EN = env("VOICE_EN", "en-US-AriaNeural")
GROQ_KEY = env("GROQ_API_KEY")
GEMINI_KEY = env("GEMINI_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1"

DATA = BASE / "data"  # personal data, ignored by git
MEMORY_FILE = DATA / "memory.json"
NOTES_FILE = DATA / "notes.txt"

BRAINS = []  # tried in this order
if GEMINI_KEY:
    BRAINS.append({
        "name": "gemini", "vision": True, "key": GEMINI_KEY,
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": env("GEMINI_MODEL", "gemini-3.5-flash-lite"),
    })
if GROQ_KEY:
    BRAINS.append({
        "name": "groq", "vision": False, "key": GROQ_KEY, "url": GROQ_URL,
        "model": env("GROQ_MODEL", "openai/gpt-oss-120b"),
    })
BRAINS.append({
    "name": "ollama", "vision": True, "key": "ollama",
    "url": "http://localhost:11434/v1",
    "model": env("OLLAMA_MODEL", "gemma4:e2b"),
})
