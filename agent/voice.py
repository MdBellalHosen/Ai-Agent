"""Female voice output (edge-tts) and microphone input (Groq Whisper)."""
import array
import asyncio
import io
import math
import os
import re
import tempfile
import threading
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
    """Remove markdown symbols so they are not read aloud."""
    return re.sub(r"[*#`_>|]", " ", text).strip()[:1500]


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


def play_mp3(audio):
    pygame = mixer()
    with speak_lock:
        stop_flag.clear()
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


def speak(text):
    if settings["muted"] or settings["private"]:  # private text never goes online
        return
    try:
        audio = tts_bytes(text)
        if audio:
            play_mp3(audio)
    except Exception as err:
        print(f"  [voice problem] {err}")


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


def record(finish=None, cancel=None, on_level=None, wait=7.0, limit=30.0, silence=1.2):
    """Record until the speaker goes quiet. Returns (pcm, loudest level).

    finish: Event, stop now and keep the audio.  cancel: Event, stop and drop it.
    """
    import sounddevice as sd
    chunks, floor, heard, quiet, elapsed, loudest = [], None, False, 0.0, 0.0, 0.0
    with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME) as stream:
        while elapsed < limit:
            if cancel is not None and cancel.is_set():
                return b"", loudest
            if finish is not None and finish.is_set():
                audio = b"".join(chunks)
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
            elif heard:
                quiet += 0.05
                if quiet >= silence:
                    break
            elif elapsed >= wait:
                return b"", loudest
    return (b"".join(chunks) if heard else b""), loudest


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


def gemini_transcribe(wav, language):
    """Gemini understands spoken Bangla much better than Whisper."""
    import base64
    from openai import OpenAI
    expected = LANGUAGE_NAMES.get(language, "Bangla or English")
    instruction = (
        "Write down exactly what the speaker says in this recording. "
        f"The speaker is from Bangladesh and usually speaks {expected}, sometimes mixing in English words. "
        "Write Bangla words in Bangla script and English words in English letters. "
        "Do not translate, answer, explain or add anything. "
        "If there is no clear speech, reply with nothing.")
    client = OpenAI(api_key=config.GEMINI_KEY, timeout=60, max_retries=1,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
    reply = client.chat.completions.create(
        model=config.env("STT_MODEL", config.env("GEMINI_MODEL", "gemini-3.5-flash-lite")),
        temperature=0,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": instruction},
            {"type": "input_audio", "input_audio": {
                "data": base64.b64encode(wav).decode(), "format": "wav"}}]}])
    return (reply.choices[0].message.content or "").strip().strip('"')


def whisper_transcribe(wav, language):
    from openai import OpenAI
    client = OpenAI(api_key=config.GROQ_KEY, base_url=config.GROQ_URL, timeout=60, max_retries=1)
    extra = {}
    if language:
        extra["language"] = language
    if language in HINTS:
        extra["prompt"] = HINTS[language]
    result = client.audio.transcriptions.create(
        model="whisper-large-v3", file=("speech.wav", wav), temperature=0, **extra)
    text = result.text.strip()
    return "" if text == HINTS.get(language) else text  # silence sometimes echoes the hint


def transcribe(wav, language="bn", offline_only=False):
    """Speech to text. Gemini first, Whisper (Groq) as backup, then offline English.
    .env STT=groq swaps the first two. offline_only: nothing leaves the PC (private mode)."""
    if offline_only:
        return offline(pcm_of(wav), language)
    if not can_listen():
        raise RuntimeError("Mic er jonno .env e GEMINI_API_KEY ba GROQ_API_KEY dao.")
    try:  # keep only the latest recording, on this PC, to check the mic if words come out wrong
        config.DATA.mkdir(exist_ok=True)
        LAST_RECORDING.write_bytes(wav)
    except OSError:
        pass
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
