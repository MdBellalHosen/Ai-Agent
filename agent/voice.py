"""Female voice output (edge-tts) and microphone input (Groq Whisper)."""
import array
import asyncio
import io
import math
import os
import re
import tempfile
import threading
import time
import wave

from . import config

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
settings = {"muted": False, "private": False}
RATE = 16000
FRAME = RATE // 20  # 50 ms of audio
# A short sentence in the right script helps Whisper write Bangla in Bangla letters.
HINTS = {"bn": "আমি বাংলায় কথা বলছি।", "en": "I am speaking in English."}

speak_lock = threading.Lock()
stop_flag = threading.Event()


def clean_text(text):
    """Remove markdown symbols so they are not read aloud. Everything else is kept and spoken."""
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", str(text))  # [title](link) -> title
    text = re.sub(r"https?://\S+", " ", text)  # long links are not read letter by letter
    return re.sub(r"[ \t]+", " ", re.sub(r"[*#`_>|~]", " ", text)).strip()


def pick_voice(text):
    return config.VOICE_BN if re.search(r"[ঀ-৿]", text) else config.VOICE_EN


def tts_bytes(text):
    """Female voice as mp3 bytes (Microsoft's free online voice)."""
    import edge_tts
    clean = clean_text(text)
    if not clean:
        return b""

    async def collect():
        audio = bytearray()
        async for chunk in edge_tts.Communicate(clean, pick_voice(clean)).stream():
            if chunk["type"] == "audio":
                audio += chunk["data"]
        return bytes(audio)

    return asyncio.run(collect())


def mixer():
    import pygame
    if not pygame.mixer.get_init():
        pygame.mixer.init()
    return pygame


problems = {"report": None}  # the app shows voice problems instead of staying silent


def report(message):
    print(f"  [voice problem] {message}")
    if problems["report"]:
        problems["report"](message)


def play_mp3(audio):
    """On Windows the built-in player comes first (it always uses the normal speaker); pygame is the backup."""
    if os.name == "nt" and config.env("PLAYER", "windows") != "pygame":
        try:
            return play_windows(audio)
        except Exception as err:
            print(f"  [windows player problem] {err}, trying pygame")
    pygame = mixer()
    with speak_lock:
        fd, path = tempfile.mkstemp(suffix=".mp3")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(audio)
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            try:
                while pygame.mixer.music.get_busy() and not stop_flag.is_set():
                    pygame.time.wait(50)
            except KeyboardInterrupt:  # Ctrl+C stops the voice only
                pass
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


def sentences(text, first=60, size=220):
    """Short first piece so Mira starts talking fast, then bigger pieces."""
    parts = [p.strip() for p in re.split(r"(?<=[।?!.:;\n])\s+", clean_text(text)) if p.strip()]
    chunks, current = [], ""
    for part in parts:
        limit = first if not chunks else size
        if current and len(current) + 1 + len(part) > limit:
            chunks.append(current)
            current = part
        else:
            current = f"{current} {part}".strip()
    if current:
        chunks.append(current)
    return chunks


def play_windows(audio, kind="mp3"):
    """Backup player built into Windows (MCI), used when pygame cannot open the sound card."""
    import ctypes
    mci = ctypes.windll.winmm.mciSendStringW
    with speak_lock:
        fd, path = tempfile.mkstemp(suffix="." + kind)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(audio)
            kind_name = "mpegvideo" if kind == "mp3" else "waveaudio"
            code = mci(f'open "{path}" type {kind_name} alias mira', None, 0, None)
            if code:
                reason = ctypes.create_unicode_buffer(256)
                ctypes.windll.winmm.mciGetErrorStringW(code, reason, 256)
                raise RuntimeError(f"Windows could not open the sound: {reason.value or code}")
            mci("play mira", None, 0, None)
            status = ctypes.create_unicode_buffer(32)
            while not stop_flag.is_set():
                mci("status mira mode", status, 32, None)
                if status.value != "playing":
                    break
                time.sleep(0.05)
            mci("close mira", None, 0, None)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


def windows_voice(text):
    """Offline backup voice (Windows' own English voice) when the online voice fails."""
    script = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              "$f = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Gender -eq 'Female' } | Select-Object -First 1; "
              "if ($f) { $s.SelectVoice($f.VoiceInfo.Name) }; $s.SetOutputToWaveFile($env:MIRA_WAV); "
              "$s.Speak([Console]::In.ReadToEnd()); $s.Dispose()")
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        import subprocess
        subprocess.run(["powershell", "-NoProfile", "-Command", "[Console]::InputEncoding=[Text.Encoding]::UTF8; " + script],
                       input=text.encode("utf-8"), env={**os.environ, "MIRA_WAV": path}, timeout=60, check=True,
                       capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        with open(path, "rb") as f:
            audio = f.read()
    finally:
        os.remove(path)
    play_windows(audio, "wav")


def warm_up():
    """Load the voice parts before the first answer, so it starts faster."""
    try:
        import edge_tts  # noqa: F401
        mixer()
    except Exception as err:
        print(f"  [voice warm up] {err}")


def make_piece(piece):
    """Voice for one piece, tried up to three times so a network blip does not drop words."""
    for attempt in range(3):
        try:
            return tts_bytes(piece)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(0.4)


def speak(text, player=None):
    """Speaks the whole text. Pieces are made three at a time and played in order, so the
    first words come quickly. player(audio) may play a piece in the app window; False means here."""
    if settings["muted"] or settings["private"]:  # private text never goes online
        return
    from concurrent.futures import ThreadPoolExecutor
    pieces = sentences(text)
    if not pieces:
        return
    stop_flag.clear()
    pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="voice")
    jobs = [pool.submit(make_piece, piece) for piece in pieces]
    failed = []
    try:
        for job in jobs:
            if stop_flag.is_set():
                break
            try:
                audio = job.result(timeout=60)
            except Exception as err:
                failed.append(err)
                continue  # say the rest even if one piece could not be made
            try:
                if not (player and player(audio)):
                    play_mp3(audio)
            except Exception as err:
                report(f"ভয়েস বাজাতে সমস্যা: {err}")
                break
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    if failed and not stop_flag.is_set():
        english = not re.search(r"[\u0980-\u09FF]", text)
        if os.name == "nt" and english and len(failed) == len(pieces):
            try:
                windows_voice(clean_text(text))
            except Exception as err:
                report(f"ভয়েস তৈরি হয়নি: {err}")
        else:
            report(f"কিছু অংশের ভয়েস তৈরি হয়নি (ইন্টারনেট দেখো): {failed[0]}")
    stop_flag.set()


def stop_speaking():
    stop_flag.set()


def chime():
    """Two short notes: 'I heard Hey Mira'."""
    samples = array.array("h")
    for freq in (880, 1320):
        n = int(RATE * 0.11)
        for i in range(n):
            fade = min(1.0, i / 300, (n - i) / 300)
            samples.append(int(9000 * fade * math.sin(2 * math.pi * freq * i / RATE)))
    try:
        mixer().mixer.Sound(file=io.BytesIO(wav_bytes(samples.tobytes()))).play()
    except Exception as err:
        print(f"  [chime problem] {err}")


def rms(pcm):
    samples = array.array("h")
    samples.frombytes(pcm)
    return math.sqrt(sum(s * s for s in samples) / len(samples)) if samples else 0.0


def boost(pcm, target=12000, max_gain=8.0):
    """Make a quiet recording louder so Whisper can hear it."""
    samples = array.array("h")
    samples.frombytes(pcm)
    peak = max((abs(s) for s in samples), default=0)
    if 0 < peak < target:
        gain = min(target / peak, max_gain)
        samples = array.array("h", (max(-32768, min(32767, int(s * gain))) for s in samples))
    return samples.tobytes()


def wav_bytes(pcm):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return buffer.getvalue()


SILENCE = float(config.env("SILENCE_SECONDS", "0.9"))


def trim(chunks, voiced, pad=4):
    """Drop the quiet start and end (keeps 0.2 s around the speech): less to upload."""
    if not voiced:
        return b"".join(chunks)
    return b"".join(chunks[max(0, voiced[0] - pad):voiced[-1] + pad + 1])


def record(finish=None, cancel=None, on_level=None, wait=7.0, limit=30.0, silence=None):
    """Record until the speaker goes quiet. Returns (pcm, loudest level).

    finish: Event, stop now and keep the audio.  cancel: Event, stop and drop it.
    """
    import sounddevice as sd
    silence = SILENCE if silence is None else silence
    chunks, voiced, floor, heard, quiet, elapsed, loudest = [], [], None, False, 0.0, 0.0, 0.0
    with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME) as stream:
        while elapsed < limit:
            if cancel is not None and cancel.is_set():
                return b"", loudest
            if finish is not None and finish.is_set():
                audio = trim(chunks, voiced)
                return (audio if len(audio) >= RATE else b""), loudest  # at least 0.5 s
            data, _ = stream.read(FRAME)
            data = bytes(data)
            chunks.append(data)
            level = rms(data)
            loudest = max(loudest, level)
            elapsed += 0.05
            if on_level:
                on_level(level)
            if elapsed <= 0.3:  # learn the room noise first
                floor = level if floor is None else min(floor, level)
                continue
            if level > max(220.0, floor * 2.5):
                heard, quiet = True, 0.0
                voiced.append(len(chunks) - 1)
            elif heard:
                quiet += 0.05
                if quiet >= silence:
                    break
            elif elapsed >= wait:
                return b"", loudest
    return (trim(chunks, voiced) if heard else b""), loudest


LANGUAGE_NAMES = {"bn": "Bangla", "en": "English"}
LAST_RECORDING = config.DATA / "last_voice.wav"


def can_listen():
    return bool(config.GEMINI_KEY or config.GROQ_KEY) or offline_ready()


def offline_ready():
    from . import wake
    return wake.installed()


class Offline(RuntimeError):
    pass


def offline(pcm, language):
    """Without internet only English can be understood (small free Vosk model)."""
    from . import wake
    if language == "bn":
        raise Offline("ইন্টারনেট ছাড়া শুধু English বুঝি। উপরে English বেছে নিয়ে বলো, বা লিখে বলো।")
    if not wake.installed():
        raise Offline("Offline model nai. Chalao: .venv\\Scripts\\python main.py --install")
    return wake.offline_transcribe(pcm)


_clients = {}


def client(name, key, url):
    from openai import OpenAI
    if (name, key) not in _clients:
        _clients[(name, key)] = OpenAI(api_key=key, base_url=url, timeout=60, max_retries=1)
    return _clients[(name, key)]


def gemini_transcribe(wav, language):
    """Gemini understands spoken Bangla much better than Whisper."""
    import base64
    expected = LANGUAGE_NAMES.get(language, "Bangla or English")
    instruction = (
        "Write down exactly what the speaker says in this recording. "
        f"The speaker is from Bangladesh and usually speaks {expected}, sometimes mixing in English words. "
        "Write Bangla words in Bangla script and English words in English letters. "
        "Do not translate, answer, explain or add anything. "
        "If there is no clear speech, reply with nothing.")
    gemini = client("gemini", config.GEMINI_KEY, "https://generativelanguage.googleapis.com/v1beta/openai/")
    reply = gemini.chat.completions.create(
        model=config.env("STT_MODEL", config.env("GEMINI_MODEL", "gemini-3.5-flash-lite")),
        temperature=0,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": instruction},
            {"type": "input_audio", "input_audio": {
                "data": base64.b64encode(wav).decode(), "format": "wav"}}]}])
    return (reply.choices[0].message.content or "").strip().strip('"')


def whisper_transcribe(wav, language):
    groq = client("groq", config.GROQ_KEY, config.GROQ_URL)
    extra = {}
    if language:
        extra["language"] = language
    if language in HINTS:
        extra["prompt"] = HINTS[language]
    result = groq.audio.transcriptions.create(
        model="whisper-large-v3", file=("speech.wav", wav), temperature=0, **extra)
    text = result.text.strip()
    return "" if text == HINTS.get(language) else text  # silence sometimes echoes the hint


def keep(wav):
    """Keep only the latest recording, on this PC, to check the mic if words come out wrong."""
    try:
        config.DATA.mkdir(exist_ok=True)
        LAST_RECORDING.write_bytes(wav)
    except OSError:
        pass


def transcribe(wav, language="bn", offline_only=False):
    """Speech to text. Gemini first, Whisper (Groq) as backup, then offline English.
    .env STT=groq swaps the first two. offline_only: nothing leaves the PC (private mode)."""
    if offline_only:
        return offline(pcm_of(wav), language)
    if not can_listen():
        raise RuntimeError("Mic er jonno .env e GEMINI_API_KEY ba GROQ_API_KEY dao.")
    keep(wav)
    order = [("gemini", config.GEMINI_KEY, gemini_transcribe), ("groq", config.GROQ_KEY, whisper_transcribe)]
    if config.env("STT", "gemini").lower() == "groq":
        order.reverse()
    problem = None
    for name, key, engine in order:
        if not key:
            continue
        try:
            return engine(wav, language)
        except Exception as err:
            print(f"  [{name} speech problem] {err}")
            problem = err
    if offline_ready():
        return offline(pcm_of(wav), language)
    raise RuntimeError(f"Kotha lekha gelo na: {problem}")


def pcm_of(wav):
    with wave.open(io.BytesIO(wav)) as w:
        return w.readframes(w.getnframes())


def listen(language):
    """Terminal version: speak, then press Enter."""
    if not can_listen():
        print("Voice input er jonno .env e GEMINI_API_KEY ba GROQ_API_KEY dao.")
        return ""
    import sounddevice as sd
    chunks = []

    def collect(data, frames, time, status):
        chunks.append(bytes(data))

    with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", callback=collect):
        input("Bolo... shesh hole Enter chapo ")
    audio = b"".join(chunks)
    if len(audio) < RATE:  # less than half a second
        return ""
    if rms(audio) < 120:
        print("  [mic] awaj khub aste. Windows Sound settings e input volume barao.")
    return transcribe(wav_bytes(boost(audio)), language)
