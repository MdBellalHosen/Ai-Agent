"""Female voice output (edge-tts) and microphone input (Groq Whisper)."""
import asyncio
import io
import os
import re
import tempfile
import threading
import wave

from . import config

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
settings = {"muted": False, "private": False}


def clean_text(text):
    """Remove markdown symbols so they are not read aloud."""
    return re.sub(r"[*#`_>|]", " ", text).strip()[:1500]


def pick_voice(text):
    return config.VOICE_BN if re.search(r"[\u0980-\u09FF]", text) else config.VOICE_EN


speak_lock = threading.Lock()


def speak(text):
    if settings["muted"] or settings["private"]:  # private text never goes online
        return
    clean = clean_text(text)
    if not clean:
        return
    voice = pick_voice(clean)
    path = None
    try:
        import edge_tts
        import pygame
        with speak_lock:
            fd, path = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)
            asyncio.run(edge_tts.Communicate(clean, voice).save(path))
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            try:
                while pygame.mixer.music.get_busy():
                    pygame.time.wait(100)
            except KeyboardInterrupt:  # Ctrl+C stops the voice only
                pygame.mixer.music.stop()
            pygame.mixer.music.unload()
    except Exception as err:
        print(f"  [voice problem] {err}")
    finally:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


def listen(language):
    if not config.GROQ_KEY:
        print("Voice input er jonno .env e GROQ_API_KEY dao.")
        return ""
    import sounddevice as sd
    from openai import OpenAI
    rate, chunks = 16000, []

    def collect(data, frames, time, status):
        chunks.append(bytes(data))

    with sd.RawInputStream(samplerate=rate, channels=1, dtype="int16", callback=collect):
        input("Bolo... shesh hole Enter chapo ")
    audio = b"".join(chunks)
    if len(audio) < rate:  # less than half a second
        return ""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(audio)
    client = OpenAI(api_key=config.GROQ_KEY, base_url=config.GROQ_URL)
    extra = {"language": language} if language else {}
    result = client.audio.transcriptions.create(
        model="whisper-large-v3", file=("speech.wav", buffer.getvalue()), **extra)
    return result.text.strip()
