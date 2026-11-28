"""Mira's voice is played by the app window; Python plays it when the window cannot."""
import threading
import time
import unittest
from unittest import mock

from agent import brain, voice, web
from tests.test_app import Base

REAL_SPEAK = voice.speak


class WindowVoiceTests(Base):
    def setUp(self):
        super().setUp()
        self.speak.side_effect = REAL_SPEAK
        self.local = []
        for patcher in (mock.patch.object(voice, "tts_bytes", side_effect=lambda t: t.encode()),
                        mock.patch.object(voice, "play_mp3", side_effect=self.local.append),
                        mock.patch.object(web, "BROWSER_PICKUP", 0.4)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def page(self, behaviour, stop):
        """A pretend window: polls, fetches each voice piece, then reports back."""
        played = []
        while not stop.is_set():
            state = self.updates()
            item = state.get("play")
            if item:
                code, body = self.request("GET", f"/api/audio?id={item['id']}")
                if code == 200:
                    played.append(body)
                    self.request("POST", "/api/audio/done", behaviour(item["id"]))
            time.sleep(0.02)
        return played

    def run_page(self, behaviour):
        stop, out = threading.Event(), {}
        thread = threading.Thread(target=lambda: out.setdefault("played", self.page(behaviour, stop)))
        thread.start()
        return stop, thread, out

    def test_window_plays_every_piece(self):
        stop, thread, out = self.run_page(lambda i: {"id": i, "started": True})
        with mock.patch.object(brain, "ask", return_value="প্রথম কথা। " + "দ্বিতীয় অংশটা বেশ লম্বা। " * 6):
            self.request("POST", "/api/send", {"text": "হ্যালো"})
            self.wait_idle()
        stop.set()
        thread.join()
        self.assertGreater(len(out["played"]), 1)
        self.assertTrue(out["played"][0].startswith("প্রথম কথা।"))
        self.assertEqual(self.local, [])  # nothing played by Python

    def test_python_plays_when_window_is_blocked(self):
        stop, thread, out = self.run_page(lambda i: {"id": i, "started": False, "error": "NotAllowedError"})
        with mock.patch.object(brain, "ask", return_value="ঠিক আছে।"):
            self.request("POST", "/api/send", {"text": "হ্যালো"})
            self.wait_idle()
        stop.set()
        thread.join()
        self.assertEqual(self.local, ["ঠিক আছে।".encode()])

    def test_python_plays_when_no_window(self):
        self.app.last_seen = 0
        with mock.patch.object(brain, "ask", return_value="ঠিক আছে।"):
            self.app.start("thinking", self.app.reply, "hi")
            self.wait_idle()
        self.assertEqual(self.local, ["ঠিক আছে।".encode()])

    def test_python_plays_when_window_is_minimized(self):
        self.request("GET", "/api/updates?after=0&v=0")
        with mock.patch.object(brain, "ask", return_value="ঠিক আছে।"):
            self.app.start("thinking", self.app.reply, "hi")
            self.wait_idle()
        self.assertEqual(self.local, ["ঠিক আছে।".encode()])

    def test_audio_needs_the_token_and_current_id(self):
        self.assertEqual(self.request("GET", "/api/audio?id=1", token=False)[0], 403)
        self.assertEqual(self.request("GET", "/api/audio?id=99")[0], 404)
        self.assertFalse(self.request("POST", "/api/audio/done", {"id": 5, "started": True})[1]["ok"])

    def test_hey_mira_switch_and_tag(self):
        self.request("POST", "/api/settings", {"wake": False})
        self.assertFalse(self.updates()["wake_on"])
        self.app.via_wake = True
        self.assertTrue(self.app.took_wake())
        self.assertFalse(self.app.took_wake())


class SayAgainTests(Base):
    def test_hear_an_answer_again(self):
        with mock.patch.object(brain, "ask", return_value="প্রথম উত্তর।"):
            self.request("POST", "/api/send", {"text": "হ্যালো"})
            self.wait_idle()
        mira = self.updates()["messages"][-1]
        self.speak.reset_mock()
        self.assertEqual(self.request("POST", "/api/say", {"id": mira["id"]})[0], 200)
        self.wait_idle()
        self.assertEqual(self.speak.call_args.args, ("প্রথম উত্তর।",))
        self.assertEqual(self.request("POST", "/api/say", {"id": mira["id"] - 1})[0], 400)  # user's own message


class FullTextTests(unittest.TestCase):
    def test_long_answers_are_spoken_to_the_end(self):
        text = "অনেক লম্বা উত্তর। " * 200 + "শেষ লাইন।"
        self.assertTrue(" ".join(voice.sentences(text)).endswith("শেষ লাইন।"))

    def test_a_failed_piece_is_tried_again(self):
        played, tries = [], {"n": 0}

        def flaky(piece):
            tries["n"] += 1
            if tries["n"] == 2:
                raise OSError("network blip")
            return piece.encode()

        with mock.patch.dict(voice.settings, {"muted": False, "private": False}), \
                mock.patch.object(voice, "tts_bytes", side_effect=flaky), \
                mock.patch.object(voice, "play_mp3", side_effect=played.append), \
                mock.patch.object(voice.time, "sleep"):
            voice.speak("এক। " + "দুই নম্বর অংশটা বেশ লম্বা করে লেখা। " * 4 + "তিন।")
        self.assertTrue(b" ".join(played).decode().endswith("তিন।"))


class PromptTests(unittest.TestCase):
    def test_mira_knows_she_can_speak(self):
        self.assertIn("read aloud", brain.system_prompt())
        self.assertIn("Never say you can only write text", brain.system_prompt())


if __name__ == "__main__":
    unittest.main()
