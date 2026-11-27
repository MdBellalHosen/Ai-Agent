"""Setup doctor: says which part works and which does not. Never prints API keys."""
import asyncio
import importlib
import os
import sys
import tempfile

from . import config, voice

PACKAGES = ("openai", "dotenv", "edge_tts", "pygame", "sounddevice", "pyautogui", "PIL", "vosk")


def report(name, action, required=True):
    try:
        detail = action() or ""
        print(f"[ OK ] {name} {detail}".rstrip())
        return True
    except Exception as err:
        print(f"[{'FAIL' if required else 'SKIP'}] {name}: {str(err)[:200]}")
        return False


def microphone():
    import sounddevice as sd
    return f"({sd.query_devices(kind='input')['name']})"


def brain(entry):
    from .brain import make_client
    client = make_client(entry).with_options(timeout=60, max_retries=0)
    client.chat.completions.create(
        model=entry["model"], messages=[{"role": "user", "content": "Say OK"}])
    return f"({entry['model']})"


def synthesize(name, text):
    import edge_tts
    fd, path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        asyncio.run(edge_tts.Communicate(text, name).save(path))
        if os.path.getsize(path) == 0:
            raise RuntimeError("empty audio")
    finally:
        os.remove(path)


def wake_word():
    from . import wake
    if not wake.enabled():
        return "(.env e WAKE_WORD=off)"
    if not wake.installed():
        raise RuntimeError("model nai. Chalao: .venv\\Scripts\\python main.py --install")
    import vosk
    vosk.SetLogLevel(-1)
    vosk.Model(str(wake.MODEL_DIR))


def run(offline=False):
    version = sys.version.split()[0]
    print(f"Python {version}")
    ok = all([report(f"package {p}", lambda p=p: importlib.import_module(p) and None) for p in PACKAGES])
    if offline:
        return 0 if ok else 1

    if not (config.BASE / ".env").exists():
        print("[FAIL] .env file nai. setup.bat chalao.")
        ok = False
    for key, value in (("GEMINI_API_KEY", config.GEMINI_KEY), ("GROQ_API_KEY", config.GROQ_KEY)):
        print(f"[{' OK ' if value else 'SKIP'}] {key} {'deya ache' if value else 'deya nai'}")
    working = [report(f"brain {b['name']}", lambda b=b: brain(b), required=False) for b in config.BRAINS]
    if not any(working):
        print("[FAIL] Kono brain kaj korche na.")
        ok = False
    report("microphone", microphone, required=False)
    for name, text in ((config.VOICE_BN, "আমি প্রস্তুত।"), (config.VOICE_EN, "I am ready.")):
        report(f"voice {name}", lambda n=name, t=text: synthesize(n, t), required=False)
    report("wake word (Hey Mira)", wake_word, required=False)
    print("\nSob thik." if ok else "\nUporer FAIL gulo thik koro.")
    return 0 if ok else 1
