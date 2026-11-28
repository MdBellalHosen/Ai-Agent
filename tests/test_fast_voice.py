"""Faster and clearer voice: one-step hearing, speaking piece by piece, trimmed recordings."""
import importlib.util
import types
import unittest
from unittest import mock

from agent import brain, config, voice, web
from tests.test_app import Base, tone


def fake_reply(text):
    message = types.SimpleNamespace(content=text, tool_calls=None)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


class HeardTests(unittest.TestCase):
    def test_split_heard(self):
        self.assertEqual(brain.split_heard("HEARD: আমার নাম কি\nআমার নাম মিরা।"), ("আমার নাম কি", "আমার নাম মিরা।"))
        self.assertEqual(brain.split_heard("**HEARD:** open notepad\nOpened it."), ("open notepad", "Opened it."))
        self.assertEqual(brain.split_heard("HEARD:\nআবার বলো তো?"), ("", "আবার বলো তো?"))
        self.assertEqual(brain.split_heard("Just an answer"), ("", "Just an answer"))

    def test_one_step_voice(self):
        requests = []
        gemini = {"name": "gemini", "audio": True, "vision": True, "key": "k", "url": "u", "model": "m"}
        client = mock.Mock()
        client.chat.completions.create.side_effect = lambda **r: requests.append(r) or fake_reply(
            "HEARD: নোটপ্যাড খোলো\nআচ্ছা, খুলছি।")
        brain.history.clear()
        self.addCleanup(brain.history.clear)
        with mock.patch.object(config, "BRAINS", [gemini]), mock.patch.object(brain, "make_client", return_value=client):
            self.assertEqual(brain.ask_voice(b"RIFF", "bn"), ("নোটপ্যাড খোলো", "আচ্ছা, খুলছি।"))
        sent = requests[0]["messages"]
        self.assertIn("one to three short", sent[0]["content"])  # short spoken answers
        self.assertEqual(sent[-1]["content"][1]["input_audio"]["format"], "wav")
        self.assertIn("Bangla", sent[-1]["content"][0]["text"])
        self.assertEqual(brain.history[0], {"role": "user", "content": "নোটপ্যাড খোলো"})  # text, not audio

    def test_no_audio_brain(self):
        groq = {"name": "groq", "vision": False, "key": "k", "url": "u", "model": "m"}
        with mock.patch.object(config, "BRAINS", [groq]):
            with self.assertRaises(brain.NoVoiceBrain):
                brain.ask_voice(b"RIFF")
        failing = {"name": "gemini", "audio": True, "key": "k", "url": "u", "model": "m"}
        client = mock.Mock()
        client.chat.completions.create.side_effect = OSError("offline")
        with mock.patch.object(config, "BRAINS", [failing]), mock.patch.object(brain, "make_client", return_value=client), \
                mock.patch("builtins.print"):
            with self.assertRaises(brain.NoVoiceBrain):
                brain.ask_voice(b"RIFF")

    @unittest.skipUnless(importlib.util.find_spec("openai"), "openai not installed here")
    def test_clients_are_reused(self):
        gemini = {"name": "gemini", "key": "k", "url": "https://example.com/v1"}
        with mock.patch.dict(brain._clients, clear=True):
            self.assertIs(brain.make_client(gemini), brain.make_client(dict(gemini)))


class SpeakTests(unittest.TestCase):
    def test_first_piece_is_short(self):
        text = "হ্যালো! আমি মিরা। " + "এটা একটা লম্বা বাক্য। " * 20
        pieces = voice.sentences(text)
        self.assertLessEqual(len(pieces[0]), 60)
        self.assertGreater(len(pieces), 2)
        self.assertEqual(" ".join(pieces).split(), voice.clean_text(text).split())

    def test_plays_every_piece_in_order(self):
        played = []
        with mock.patch.dict(voice.settings, {"muted": False, "private": False}), \
                mock.patch.object(voice, "tts_bytes", side_effect=lambda t: t.encode()), \
                mock.patch.object(voice, "play_mp3", side_effect=played.append):
            voice.speak("এক। দুই। " + "তিন " * 30 + "। চার।")
        self.assertGreater(len(played), 1)
        self.assertTrue(played[0].decode().startswith("এক।"))
        self.assertTrue(played[-1].decode().endswith("চার।"))

    def test_stop_ends_speaking(self):
        played = []

        def play(audio):
            played.append(audio)
            voice.stop_speaking()

        with mock.patch.dict(voice.settings, {"muted": False, "private": False}), \
                mock.patch.object(voice, "tts_bytes", side_effect=lambda t: t.encode()), \
                mock.patch.object(voice, "play_mp3", side_effect=play):
            voice.speak("প্রথম বাক্যটা একটু লম্বা যাতে আলাদা টুকরো হয়। " * 10)
        self.assertEqual(len(played), 1)

    def test_trim_keeps_speech(self):
        chunks = [bytes([i]) for i in range(20)]
        self.assertEqual(voice.trim(chunks, [8, 9, 10]), bytes(range(4, 15)))
        self.assertEqual(voice.trim(chunks, []), bytes(range(20)))


class AppVoiceTests(Base):
    def test_one_step_voice_turn(self):
        with mock.patch.object(voice, "record", return_value=(tone(1, 3000), 3000)), \
                mock.patch.object(voice, "keep"), \
                mock.patch.object(web, "DIRECT_VOICE", True), \
                mock.patch.object(brain, "ask_voice", return_value=("সময় কত?", "দুপুর একটা।")) as ask, \
                mock.patch.object(voice, "transcribe") as transcribe:
            self.request("POST", "/api/mic", {})
            self.wait_idle()
        transcribe.assert_not_called()
        self.assertEqual(ask.call_args.args[1], "bn")
        user, mira = self.updates()["messages"]
        self.assertEqual((user["text"], user["voice"]), ("সময় কত?", True))
        self.assertEqual(mira["text"], "দুপুর একটা।")
        self.assertIsNotNone(mira["took"])
        self.assertEqual(self.speak.call_args.args, ("দুপুর একটা।",))

    def test_falls_back_to_writing_first(self):
        with mock.patch.object(voice, "record", return_value=(tone(1, 3000), 3000)), \
                mock.patch.object(web, "DIRECT_VOICE", True), \
                mock.patch.object(brain, "ask_voice", side_effect=brain.NoVoiceBrain), \
                mock.patch.object(voice, "transcribe", return_value="হ্যালো"), \
                mock.patch.object(brain, "ask", return_value="হাই") as ask:
            self.request("POST", "/api/mic", {})
            self.wait_idle()
        self.assertTrue(ask.call_args.kwargs["spoken"])
        self.assertEqual([m["text"] for m in self.updates()["messages"]], ["হ্যালো", "হাই"])

    def test_private_never_sends_audio(self):
        with mock.patch.object(voice, "record", return_value=(tone(1, 3000), 3000)), \
                mock.patch.object(voice, "offline_ready", return_value=True), \
                mock.patch.object(brain, "ask_voice") as direct, \
                mock.patch.object(voice, "transcribe", return_value="hello"), \
                mock.patch.object(brain, "ask", return_value="hi"):
            self.request("POST", "/api/settings", {"private": True, "language": "en"})
            self.request("POST", "/api/mic", {})
            self.wait_idle()
        direct.assert_not_called()


if __name__ == "__main__":
    unittest.main()
