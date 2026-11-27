"""'Hey Mira' wake word. Runs fully offline with a small free Vosk model,
so the always-on microphone never sends anything to the internet."""
import json
import shutil
import threading
import time
import urllib.request
import zipfile

from . import config

MODEL_NAME = "vosk-model-small-en-us-0.15"
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"
MODEL_DIR = config.DATA / MODEL_NAME
RATE = 16000

CALLS = ("hey", "hi")
# Sounds close to "Mira". Words the model does not know are skipped by Vosk.
NAMES = ("mira", "meera", "mirror", "mera", "myra")
GRAMMAR = [f"{c} {n}" for c in CALLS for n in NAMES] + ["[unk]"]
MIN_CONFIDENCE = 0.6


def enabled():
    return config.env("WAKE_WORD", "on").lower() not in ("off", "no", "0", "false")


def installed():
    return (MODEL_DIR / "am").is_dir() or (MODEL_DIR / "conf").is_dir()


def download(progress=print):
    """About 40 MB, downloaded once into data/."""
    config.DATA.mkdir(exist_ok=True)
    archive = config.DATA / f"{MODEL_NAME}.zip"
    progress("Wake word model download hocche (~40 MB)...")
    with urllib.request.urlopen(MODEL_URL, timeout=60) as response, archive.open("wb") as out:
        shutil.copyfileobj(response, out)
    with zipfile.ZipFile(archive) as z:
        root = config.DATA.resolve()
        for name in z.namelist():  # refuse paths that leave data/
            if not (root / name).resolve().is_relative_to(root):
                raise RuntimeError("bad zip file")
        z.extractall(config.DATA)
    archive.unlink()
    progress("Wake word model ready.")


def is_wake(result):
    """result: Vosk's final JSON as a dict."""
    words = result.get("result") or [{"word": w, "conf": 1.0} for w in result.get("text", "").split()]
    for first, second in zip(words, words[1:]):
        if (first["word"] in CALLS and second["word"] in NAMES
                and min(first.get("conf", 1.0), second.get("conf", 1.0)) >= MIN_CONFIDENCE):
            return True
    return False


class Listener(threading.Thread):
    """Waits for 'Hey Mira'. Pauses (and frees the mic) while paused() is True."""

    def __init__(self, on_wake, paused):
        super().__init__(daemon=True, name="wake-word")
        self.on_wake, self.paused = on_wake, paused
        self.stopped = threading.Event()
        self.status = "starting"

    def stop(self):
        self.stopped.set()

    def run(self):
        try:
            import sounddevice as sd
            import vosk
            vosk.SetLogLevel(-1)
            recognizer = vosk.KaldiRecognizer(vosk.Model(str(MODEL_DIR)), RATE, json.dumps(GRAMMAR))
            recognizer.SetWords(True)
        except Exception as err:
            self.status = f"off ({err})"
            print(f"  [wake word problem] {err}")
            return
        while not self.stopped.is_set():
            if self.paused():
                self.status = "paused"
                time.sleep(0.2)
                continue
            try:
                with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=4000) as stream:
                    self.status = "listening"
                    recognizer.Reset()
                    while not self.stopped.is_set() and not self.paused():
                        data, _ = stream.read(4000)  # a quarter second
                        if recognizer.AcceptWaveform(bytes(data)) and is_wake(json.loads(recognizer.Result())):
                            self.on_wake()
                            break
            except Exception as err:  # mic unplugged or busy: try again soon
                self.status = f"mic problem ({err})"
                print(f"  [wake word problem] {err}")
                time.sleep(5)
