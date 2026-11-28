"""The window app: a small web server that only this PC can reach (127.0.0.1).

The page is only the screen. Microphone, voice, tools and wake word all run here in Python.
"""
import base64
import binascii
import io
import json
import os
import secrets
import subprocess
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import apps, brain, config, files, screen, tools, tray, voice, wake
from .vision import image_url

PAGE = Path(__file__).with_name("static") / "index.html"


def code_version():
    """Changes whenever Mira's code changes (after git pull), so an old copy can be replaced."""
    import hashlib
    digest = hashlib.sha1()
    folder = Path(__file__).parent
    for path in sorted([*folder.glob("*.py"), PAGE]):
        digest.update(path.name.encode() + path.read_bytes())
    return digest.hexdigest()[:10]


VERSION = code_version()
MAX_BODY = 20 * 1024 * 1024
IDLE_LIMIT = 300  # seconds without a window before the server closes (when wake word is off)
LANGUAGES = ("bn", "en", "")
CHIME_DELAY = 0.35  # let the chime finish before recording
BROWSER_PICKUP = 1.5  # seconds the window gets to start fetching a voice piece
# Gemini hears the voice and answers in one step (faster, understands with context).
DIRECT_VOICE = config.env("VOICE_MODE", "direct").lower() != "separate"


class App:
    def __init__(self, url=""):
        self.url = url
        self.token = secrets.token_urlsafe(24)
        self.lock = threading.RLock()
        self.state = "idle"  # idle listening transcribing thinking confirm speaking
        self.level = 0.0
        self.messages, self.next_id = [], 1
        self.notice = {"id": 0, "text": ""}
        self.question, self.ask_id, self.approved = None, 0, False
        self.decided = threading.Event()
        self.finish, self.cancel = threading.Event(), threading.Event()
        self.worker = None
        self.used_tools = []
        self.language, self.convo, self.listen_next = "bn", False, False
        self.last_seen = time.monotonic()
        self.wake = None
        self.tray = None
        self.direct_failures = 0
        self.muted_told = False
        self.wake_on = True  # the menu can pause "Hey Mira" for this session
        self.page_visible = True
        self.click_told = False
        self.last_play = ""
        self.via_wake = False
        # Mira's voice is played by the window itself (the browser's sound always works).
        self.audio, self.audio_id = None, 0
        self.audio_taken, self.audio_done = threading.Event(), threading.Event()
        self.audio_result = {}

    # ---------- shared state ----------
    @property
    def private(self):
        return voice.settings["private"]

    def busy(self):
        return self.state != "idle"

    def page_open(self):
        return time.monotonic() - self.last_seen < 6

    def add(self, role, text, **extra):
        with self.lock:
            message = {"id": self.next_id, "role": role, "text": text,
                       "private": self.private, **extra}
            self.next_id += 1
            self.messages.append(message)
            del self.messages[:-300]
            return message

    def tell(self, text):
        with self.lock:
            self.notice = {"id": self.notice["id"] + 1, "text": text}

    def snapshot(self, after=0):
        with self.lock:
            return {
                "state": self.state, "level": round(min(self.level / 3000, 1.0), 2),
                "name": config.NAME, "private": self.private, "muted": voice.settings["muted"],
                "language": self.language, "convo": self.convo, "notice": self.notice,
                "question": self.question if self.state == "confirm" else None, "ask": self.ask_id,
                "mic": voice.can_listen(), "wake": self.wake.status if self.wake else "off",
                "wake_on": self.wake_on, "play": {"id": self.audio["id"]} if self.audio else None,
                "messages": [m for m in self.messages if m["id"] > after and m["private"] == self.private],
            }

    # ---------- turns ----------
    def start(self, first_state, job, *args):
        with self.lock:
            if self.busy():
                return False
            self.state = first_state
            self.finish.clear()
            self.cancel.clear()
            self.listen_next = False
            self.worker = threading.Thread(target=self._run, args=(job, args), daemon=True)
            self.worker.start()
            return True

    def _run(self, job, args):
        try:
            job(*args)
        except Exception as err:
            print(f"  [problem] {err}")
            self.add("error", f"সমস্যা: {err}")
        finally:
            with self.lock:
                self.state, self.level, self.question = "idle", 0.0, None

    def set_state(self, state):
        with self.lock:
            self.state = state

    def text_turn(self, text, picture=None, screen=False, document=None):
        if screen:
            from PIL import ImageGrab
            picture = image_url(ImageGrab.grab())
        self.add("user", text, image=bool(picture), screen=screen, document=document)
        if document:  # the model reads it with the read_document tool
            text += f"\n\n[The user attached the file '{document}'. Read it with read_document.]"
        self.reply(text, picture)
        if self.listen_next:
            self.voice_loop()

    def voice_turn(self):
        self.voice_loop()

    def voice_loop(self):
        while not self.cancel.is_set():
            private = self.private
            if private and not (self.language == "en" and voice.offline_ready()):
                self.tell("প্রাইভেট মোডে শুধু English মাইক চলে (ইন্টারনেট ছাড়া)। উপরে English বেছে নাও, বা লিখে বলো।")
                return
            if not voice.can_listen():
                self.tell("মাইকের জন্য .env এ GEMINI_API_KEY বা GROQ_API_KEY লাগবে।")
                return
            self.set_state("listening")
            self.finish.clear()
            self.listen_next = False
            pcm, loudest = voice.record(self.finish, self.cancel, on_level=self.on_level)
            self.level = 0.0
            if self.cancel.is_set():
                return
            if not pcm:
                self.tell("কিছু শুনতে পাইনি।" + (
                    " মাইকের আওয়াজ খুব কম। Windows Sound settings এ input volume বাড়াও." if loudest < 300 else ""))
                return
            wav = voice.wav_bytes(voice.boost(pcm))
            started = time.monotonic()
            if not private and DIRECT_VOICE and self.direct_failures < 2:
                try:
                    self.heard_and_answer(wav, started)
                    self.direct_failures = 0
                    if not (self.convo or self.listen_next):
                        return
                    continue
                except brain.NoVoiceBrain:
                    self.direct_failures += 1  # after two in a row, use the older way this session
            self.set_state("transcribing")
            try:
                text = voice.transcribe(wav, self.language, offline_only=private)
            except voice.Offline as err:
                self.tell(str(err))
                return
            if not text:
                self.tell("কথা বুঝতে পারিনি, আবার বলো।")
                return
            self.add("user", text, voice=True, wake=self.took_wake())
            self.reply(text, spoken=True, started=started)
            if not (self.convo or self.listen_next):
                return

    def took_wake(self):
        """True once for the first thing heard after "Hey Mira"."""
        was, self.via_wake = self.via_wake, False
        return was

    def on_level(self, level):
        self.level = level

    def heard_and_answer(self, wav, started):
        """One step: Gemini hears the recording with the chat so far, and answers."""
        self.set_state("thinking")
        self.used_tools = []
        voice.keep(wav)
        heard, answer = brain.ask_voice(wav, self.language)
        self.add("user", heard or "(বুঝতে পারিনি)", voice=True, wake=self.took_wake())
        self.say(answer, started)

    def reply(self, text, picture=None, spoken=False, started=None):
        self.set_state("thinking")
        self.used_tools = []
        answer = brain.ask(text, image=picture, private=self.private, spoken=spoken)
        self.say(answer, started)

    def say(self, answer, started=None):
        took = round(time.monotonic() - started, 1) if started else None
        if took is not None:
            print(f"  [time] answer ready {took}s after you stopped talking")
        self.add("mira", answer, tools=list(self.used_tools), took=took)
        if voice.settings["muted"] and started and not self.muted_told:
            self.muted_told = True  # once per session
            self.tell("মিরার ভয়েস বন্ধ আছে। শুনতে চাইলে উপরের স্পিকার বাটনে চাপ দাও।")
        if self.cancel.is_set() or voice.settings["muted"] or self.private:
            return
        self.set_state("speaking")
        voice.speak(answer, player=self.browser_play)

    def say_again(self, text):
        if voice.settings["muted"]:
            self.tell("মিরার ভয়েস বন্ধ আছে। উপরের স্পিকার বাটনে চাপ দাও।")
            return
        voice.speak(text, player=self.browser_play)

    def browser_play(self, audio):
        """Plays one piece in the window. False means the window could not, so Python plays it."""
        if not self.page_open():
            self.last_play = "no window"
            return False
        if not self.page_visible:  # minimized windows play late
            self.last_play = "window hidden"
            return False
        with self.lock:
            self.audio_id += 1
            self.audio = {"id": self.audio_id, "data": audio}
            self.audio_taken.clear()
            self.audio_done.clear()
            self.audio_result = {}
        try:
            if not self.audio_taken.wait(BROWSER_PICKUP):  # window asleep or closed
                self.last_play = "window did not answer"
                return False
            limit = time.monotonic() + 10 + len(audio) / 2500
            while not self.audio_done.wait(0.05):
                if voice.stop_flag.is_set() or time.monotonic() > limit:
                    self.last_play = "played"
                    return True
            started = bool(self.audio_result.get("started"))
            self.last_play = "played" if started else "window refused: " + self.audio_result.get("error", "")
            return started
        finally:
            with self.lock:
                self.audio = None  # the window stops playing when this disappears

    def audio_finished(self, data):
        with self.lock:
            if not self.audio or data.get("id") != self.audio["id"]:
                return False
            self.audio_result = {"started": data.get("started") is True, "error": str(data.get("error") or "")[:200]}
            if self.audio_result["error"]:
                print(f"  [window sound] {self.audio_result['error']}, playing from Python instead")
                if "NotAllowed" in self.audio_result["error"] and not self.click_told:
                    self.click_told = True
                    self.tell("মিরার ভয়েস জানালা থেকে বাজাতে একবার জানালার যেকোনো জায়গায় ক্লিক করো।")
            self.audio_done.set()
            return True

    # ---------- buttons ----------
    def mic(self):
        """Mic button: start listening, finish listening, or interrupt Mira."""
        with self.lock:
            if self.state == "idle":
                return self.start("listening", self.voice_turn)
            if self.state == "listening":
                self.finish.set()
                return True
            if self.state == "speaking":
                self.listen_next = True
                voice.stop_speaking()
                return True
            if self.state == "thinking":
                self.listen_next = True
                return True
            return False

    def stop(self):
        self.cancel.set()
        self.listen_next = False
        voice.stop_speaking()
        if self.state == "confirm":
            self.decide(self.ask_id, False)

    def decide(self, ask, yes):
        with self.lock:
            if self.state != "confirm" or ask != self.ask_id:
                return False
            self.approved = bool(yes)
            self.decided.set()
            return True

    # ---------- hooks used by tools.py ----------
    def confirm(self, question):
        if threading.current_thread() is not self.worker:
            return False  # only the current request can ask, and only a click can approve
        with self.lock:
            previous = self.state
            self.question, self.ask_id, self.approved = question, self.ask_id + 1, False
            self.decided.clear()
            self.state = "confirm"
        if not self.page_open() and self.url:
            launch(self.url)
        allowed = self.decided.wait(120) and self.approved
        with self.lock:
            self.question, self.state = None, previous
        return allowed

    def tool_used(self, name):
        if threading.current_thread() is self.worker:
            self.used_tools.append(name)

    def announce(self, message):
        self.add("mira", f"রিমাইন্ডার: {message}", reminder=True)
        if not self.page_open() and self.url:
            launch(self.url)
        if not self.busy():
            voice.speak(message, player=self.browser_play)

    def heard_wake(self):
        if not voice.can_listen():
            voice.chime()
            self.tell("Hey Mira শুনেছি, কিন্তু মাইক এখন বন্ধ। লিখে বলো।")
        elif not self.start("listening", self.wake_turn):  # also pauses the wake word
            return
        if not self.page_open() and self.url:
            launch(self.url)

    def wake_turn(self):
        self.via_wake = True
        voice.chime()
        time.sleep(CHIME_DELAY)
        self.voice_loop()

    def install(self):
        tools.hooks.update(confirm=self.confirm, announce=self.announce, tool=self.tool_used)
        voice.problems["report"] = self.tell

    def voice_test(self):
        """Says a test line and writes down each step, so a problem shows where it is."""
        line = "হ্যালো! আমি মিরা। আমার কথা শুনতে পাচ্ছ?"
        steps = [f"মিরার ভার্সন: {VERSION}"]
        if voice.settings["muted"]:
            steps.append("ভয়েস: বন্ধ। উপরের স্পিকার বাটনে চাপ দিয়ে চালু করো।")
        elif self.private:
            steps.append("ভয়েস: প্রাইভেট মোডে মিরা ভয়েসে বলে না।")
        else:
            self.set_state("speaking")
            began = time.monotonic()
            try:
                audio = voice.tts_bytes(line)
                steps.append(f"ভয়েস তৈরি (Microsoft): ঠিক আছে, {time.monotonic() - began:.1f} সেকেন্ড")
            except Exception as err:
                audio = None
                steps.append(f"ভয়েস তৈরি (Microsoft): হয়নি, {err}. ইন্টারনেট দেখো।")
            if audio:
                self.last_play = ""
                if self.browser_play(audio):
                    steps.append("জানালা থেকে বাজানো: ঠিক আছে")
                else:
                    steps.append(f"জানালা থেকে বাজানো: হয়নি ({self.last_play})")
                    try:
                        voice.play_mp3(audio)
                        steps.append("Python থেকে বাজানো: ঠিক আছে")
                    except Exception as err:
                        steps.append(f"Python থেকে বাজানো: হয়নি, {err}")
        steps.append("শুনতে না পেলে Windows এর ভলিউম আর কোন স্পিকার বাছা আছে দেখো।")
        self.add("mira", "ভয়েস পরীক্ষা\n" + "\n".join(steps))

    def start_wake(self):
        if wake.enabled() and wake.installed():
            self.wake = wake.Listener(self.heard_wake, paused=lambda: self.busy() or not self.wake_on)
            self.wake.start()


def decode_picture(data_url):
    head, _, data = str(data_url).partition(",")
    if not (head.startswith("data:image/") and head.endswith(";base64")):
        raise ValueError("chobi bujhte parini")
    from PIL import Image
    try:
        return image_url(Image.open(io.BytesIO(base64.b64decode(data, validate=True))))
    except (binascii.Error, OSError) as err:
        raise ValueError("chobi bujhte parini") from err


class Handler(BaseHTTPRequestHandler):
    server_version = "Mira"
    sys_version = ""

    def log_message(self, *args):
        pass

    @property
    def app(self):
        return self.server.app

    def reply(self, code, body=None, kind="application/json; charset=utf-8", headers=()):
        data = body if isinstance(body, bytes) else json.dumps(body or {}, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def checked(self, need_token=True):
        """Only this PC's own page may talk to the server."""
        port = self.server.server_address[1]
        if self.headers.get("Host", "") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            self.reply(403, {"error": "host"})
            return False
        if need_token and not secrets.compare_digest(self.headers.get("X-Token", ""), self.app.token):
            self.reply(403, {"error": "token"})
            return False
        if need_token:
            self.app.last_seen = time.monotonic()
        return True

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            if not self.checked(need_token=False):
                return
            nonce = secrets.token_urlsafe(16)
            page = PAGE.read_text(encoding="utf-8").replace("__TOKEN__", self.app.token)
            page = page.replace("__NONCE__", nonce)
            policy = (f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
                      "img-src data: blob:; media-src blob:; connect-src 'self'; base-uri 'none'; form-action 'none'; "
                      "frame-ancestors 'none'")
            return self.reply(200, page.encode(), "text/html; charset=utf-8",
                              [("Content-Security-Policy", policy)])
        if url.path == "/api/ping":
            return self.checked(need_token=False) and self.reply(200, {"app": "mira", "version": VERSION})
        if not self.checked():
            return
        if url.path == "/api/audio":
            wanted = parse_qs(url.query).get("id", [""])[0]
            with self.app.lock:
                audio = self.app.audio
                if not audio or str(audio["id"]) != wanted:
                    return self.reply(404, {"error": "gone"})
                self.app.audio_taken.set()
            return self.reply(200, audio["data"], "audio/mpeg")
        if url.path == "/api/updates":
            query = parse_qs(url.query)
            after = query.get("after", ["0"])[0]
            self.app.page_visible = query.get("v", ["1"])[0] != "0"
            return self.reply(200, self.app.snapshot(int(after) if after.isdigit() else 0))
        self.reply(404, {"error": "not found"})

    def do_POST(self):
        if not self.checked():
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self.close_connection = True
            return self.reply(413, {"error": "khub boro"})
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            return self.reply(400, {"error": "bad request"})
        app, path = self.app, urlparse(self.path).path

        if path == "/api/send":
            text = str(data.get("text") or "").strip()[:4000]
            screen = bool(data.get("screen"))
            try:
                picture = decode_picture(data["image"]) if data.get("image") else None
            except ValueError as err:
                return self.reply(400, {"error": str(err)})
            document = None
            if isinstance(data.get("document"), dict):
                if app.private:
                    return self.reply(400, {"error": "প্রাইভেট মোডে ফাইল পড়া যায় না"})
                try:
                    raw = base64.b64decode(str(data["document"].get("data", "")).partition(",")[2], validate=True)
                    document = files.save_upload(data["document"].get("name", "document.pdf"), raw).name
                except (ValueError, binascii.Error) as err:
                    return self.reply(400, {"error": str(err) or "file bujhte parini"})
                text = text or "এই ফাইলটা সহজ করে বুঝিয়ে দাও, মূল পয়েন্টগুলো বলো।"
            if picture or screen:
                text = text or ("আমার স্ক্রিনে কী আছে বলো।" if screen else
                                "এই ছবিটা বুঝিয়ে দাও। অঙ্ক থাকলে সমাধান করো।")
            if not text:
                return self.reply(400, {"error": "kichu likho"})
            ok = app.start("thinking", app.text_turn, text, picture, screen, document)
            return self.reply(200 if ok else 409, {"ok": ok})
        if path == "/api/mic":
            return self.reply(200, {"ok": bool(app.mic())})
        if path == "/api/audio/done":
            return self.reply(200, {"ok": app.audio_finished(data)})
        if path == "/api/say":  # "hear it again" on one of Mira's messages
            with app.lock:
                found = next((m for m in app.messages if m["id"] == data.get("id") and m["role"] == "mira"
                              and m["private"] == app.private), None)
            if not found or app.private:
                return self.reply(400, {"error": "এই উত্তরটা শোনানো যাচ্ছে না"})
            ok = app.start("speaking", app.say_again, found["text"])
            return self.reply(200 if ok else 409, {"ok": ok})
        if path == "/api/voicetest":
            return self.reply(200 if app.start("speaking", app.voice_test) else 409, {"ok": True})
        if path == "/api/stop":
            app.stop()
            return self.reply(200, {"ok": True})
        if path == "/api/confirm":
            return self.reply(200, {"ok": app.decide(data.get("ask"), data.get("yes") is True)})
        if path == "/api/settings":
            if "private" in data:
                if app.busy():
                    return self.reply(409, {"error": "ekhon kaj cholche"})
                voice.settings["private"] = bool(data["private"])
            if "muted" in data:
                voice.settings["muted"] = bool(data["muted"])
                if voice.settings["muted"]:
                    voice.stop_speaking()
            if "convo" in data:
                app.convo = bool(data["convo"])
            if "wake" in data:
                app.wake_on = bool(data["wake"])
            if data.get("language") in LANGUAGES:
                app.language = data["language"]
            return self.reply(200, app.snapshot(10 ** 9))
        if path == "/api/clear":
            if app.busy():
                return self.reply(409, {"error": "ekhon kaj cholche"})
            with app.lock:
                app.messages = [m for m in app.messages if m["private"] != app.private]
            (brain.private_history if app.private else brain.history).clear()
            return self.reply(200, {"ok": True})
        if path == "/api/quit":
            self.reply(200, {"ok": True})
            app.stop()
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        self.reply(404, {"error": "not found"})


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = os.name != "nt"  # on Windows it would let two copies share a port


def make_server(port):
    server = Server(("127.0.0.1", port), Handler)
    server.app = App(f"http://127.0.0.1:{server.server_address[1]}/")
    return server


def running(url):
    """The Mira already answering on this port: {"app": "mira", "version": ...}, or None."""
    try:
        with urllib.request.urlopen(url + "api/ping", timeout=2) as response:
            info = json.load(response)
            return info if info.get("app") == "mira" else None
    except Exception:
        return None


def stop_old(port):
    """Ends an older Mira still running on this port (often the one started with Windows)."""
    if os.name != "nt":
        return False
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    listing = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True,
                             timeout=15, creationflags=flags).stdout
    pids = {line.split()[-1] for line in listing.splitlines()
            if f"127.0.0.1:{port} " in line and "LISTENING" in line}
    stopped = False
    for pid in pids:
        image = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True,
                               text=True, timeout=15, creationflags=flags).stdout.lower()
        if "python" in image and int(pid) != os.getpid():  # only an old Mira, never another program
            subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True, timeout=15, creationflags=flags)
            stopped = True
    for _ in range(25):
        if not running(f"http://127.0.0.1:{port}/"):
            return stopped
        time.sleep(0.2)
    return False


def browsers():
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 os.environ.get("LOCALAPPDATA")):
        for name in (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"):
            if base and Path(base, name).is_file():
                yield str(Path(base, name))


def launch(url):
    """Open the page as its own app window (Edge or Chrome), else in the normal browser."""
    for exe in browsers():
        try:
            subprocess.Popen([exe, f"--app={url}", "--window-size=520,820",
                              "--autoplay-policy=no-user-gesture-required"])
            return
        except OSError:
            continue
    webbrowser.open(url)


def watch(server):
    app = server.app
    while True:
        time.sleep(20)
        wake_on = (app.wake is not None and app.wake.is_alive()) or app.tray is not None
        if (not wake_on and not app.busy() and not tools.reminders_pending()
                and time.monotonic() - app.last_seen > IDLE_LIMIT):
            server.shutdown()
            return


def serve(open_window=True, port=None):
    port = int(port or config.env("WEB_PORT", "8765"))
    url = f"http://127.0.0.1:{port}/"
    try:
        server = make_server(port)
    except OSError:
        other = running(url)
        if other and other.get("version") == VERSION:  # already open, e.g. started with Windows
            if open_window:
                launch(url)
            return 0
        if not (other and stop_old(port)):
            print(f"Port {port} e onno program cholche. .env e WEB_PORT=8770 likhe abar chalao.")
            return 1
        print("Purono Mira bondho kore notun ta chalu korchi.")
        time.sleep(0.5)
        server = make_server(port)
    app = server.app
    app.install()
    app.start_wake()
    apps.preload()
    screen.track_focus()
    threading.Thread(target=lambda: (brain.warm_up(), voice.warm_up()), daemon=True).start()
    app.tray = tray.start(app, server, launch)
    print(f"{config.NAME} cholche: {url}")
    print("Wake word:", "on (Hey Mira)" if app.wake else "off")
    if open_window:
        launch(url)
    threading.Thread(target=watch, args=(server,), daemon=True).start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        if app.wake:
            app.wake.stop()
        if app.tray:
            app.tray.stop()
        server.server_close()
    return 0
