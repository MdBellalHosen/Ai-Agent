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


def transcribe(wav, language="bn"):
    if not config.GROQ_KEY:
        raise RuntimeError("Voice input er jonno .env e GROQ_API_KEY dao.")
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


def listen(language):
    """Terminal version: speak, then press Enter."""
    if not config.GROQ_KEY:
        print("Voice input er jonno .env e GROQ_API_KEY dao.")
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
