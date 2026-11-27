"""The keyboard and microphone chat loop."""
import sys

from . import apps, config, voice
from .brain import ask
from .vision import image_url

HELP = """
Enter (khali)        : mic diye kotha bolo
lekha + Enter        : likhe kotha bolo
/image PATH | prosno : chobi theke prosno ba math
/screen prosno       : ekhonkar screen dekhe uttor
/bn  /en  /auto      : mic er vasha (shuru te Bangla)
/private             : private mode on/off (shudhu local Ollama, voice bondho)
/mute                : female voice on/off
/help  /exit
"""


def main():
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    language = "bn"
    settings = voice.settings
    apps.preload()
    print(f"{config.NAME} ready.{HELP}")

    while True:
        try:
            text = input(f"\n{'[private] ' if settings['private'] else ''}Tumi: ").strip()
            image = None
            command, _, rest = text.partition(" ")
            if command == "/exit":
                break
            if command == "/help":
                print(HELP)
                continue
            if command in ("/bn", "/en", "/auto"):
                language = "" if command == "/auto" else command[1:]
                print("Mic er vasha:", language or "auto")
                continue
            if command == "/private":
                settings["private"] = not settings["private"]
                print("Private mode", "ON" if settings["private"] else "OFF")
                continue
            if command == "/mute":
                settings["muted"] = not settings["muted"]
                print("Voice", "OFF" if settings["muted"] else "ON")
                continue
            if command == "/image":
                path, _, question = rest.partition("|")
                image = image_url(path.strip().strip('"'))
                text = question.strip() or "Ei chobi ta bujhiye dao. Math thakle solve koro."
            elif command == "/screen":
                from PIL import ImageGrab
                image = image_url(ImageGrab.grab())
                text = rest.strip() or "Amar screen e ki ache bolo."
            elif command.startswith("/"):
                print("Ei command nai. /help likho.")
                continue
            elif not text:
                if settings["private"]:
                    print("Private mode e mic bondho. Likhe bolo.")
                    continue
                text = voice.listen(language)
                if not text:
                    continue
                print("Tumi (voice):", text)

            answer = ask(text, image=image, private=settings["private"])
            print(f"\n{config.NAME}: {answer}")
            voice.speak(answer)
        except (KeyboardInterrupt, EOFError):
            break
        except Exception as err:
            print(f"  [problem] {err}")
