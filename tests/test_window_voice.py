"""Mira's voice is played by the app window; Python plays it when the window cannot."""
import http.client
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
                        mock.patch.object(web, "BROWSER_PICKUP", 0.4), mock.patch.object(web, "AUDIO_WAIT", 0.3)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def next_piece(self, after):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", f"/api/audio/next?after={after}",
                     headers={"Host": f"127.0.0.1:{self.port}", "X-Token": self.app.token})
        res = conn.getresponse()
        body, audio_id = res.read(), res.getheader("X-Audio-Id")
        conn.close()
        return res.status, body, int(audio_id) if audio_id else None

    def page(self, behaviour, stop):
        """A pretend window: always has one request waiting for the next piece, plays it, reports back."""
        played, after = [], 0
        while not stop.is_set():
            status, body, audio_id = self.next_piece(after)
            if status == 200:
                after = audio_id
                result = behaviour(audio_id)
                if result.get("started"):
                    self.request("POST", "/api/audio/started", {"id": audio_id})
                    played.append(body.decode())
                self.request("POST", "/api/audio/done", result)
        return played

    def run_page(self, behaviour):
        stop, out = threading.Event(), {}
        thread = threading.Thread(target=lambda: out.setdefault("played", self.page(behaviour, stop)))
        thread.start()
        time.sleep(0.05)
        return stop, thread, out

    def finish(self, stop, thread):
        stop.set()
        thread.join()

    def test_window_plays_every_piece_once(self):
        stop, thread, out = self.run_page(lambda i: {"id": i, "started": True})
        text = "প্রথম কথা। " + "দ্বিতীয় অংশটা বেশ লম্বা। " * 12
        with mock.patch.object(brain, "ask", return_value=text):
            self.request("POST", "/api/send", {"text": "হ্যালো"})
            self.wait_idle()
        self.finish(stop, thread)
        self.assertEqual(out["played"], voice.sentences(text))  # every piece, in order, once
        self.assertEqual(self.local, [])

    def test_window_behind_other_apps_still_plays(self):
        self.app.last_seen = 0  # the window has not polled for a while (slowed down by the browser)
        stop, thread, out = self.run_page(lambda i: {"id": i, "started": True})
        with mock.patch.object(brain, "ask", return_value="ঠিক আছে।"):
            self.app.start("thinking", self.app.reply, "hi")
            self.wait_idle()
        self.finish(stop, thread)
        self.assertEqual(out["played"], ["ঠিক আছে।"])
        self.assertEqual(self.local, [])

    def test_python_plays_when_window_is_blocked(self):
        stop, thread, out = self.run_page(lambda i: {"id": i, "started": False, "error": "NotAllowedError"})
        with mock.patch.object(brain, "ask", return_value="ঠিক আছে।"):
            self.request("POST", "/api/send", {"text": "হ্যালো"})
            self.wait_idle()
        self.finish(stop, thread)
        self.assertEqual(self.local, ["ঠিক আছে।".encode()])

    def test_python_plays_when_no_window(self):
        with mock.patch.object(brain, "ask", return_value="ঠিক আছে।"):
            self.app.start("thinking", self.app.reply, "hi")
            self.wait_idle()
        self.assertEqual(self.local, ["ঠিক আছে।".encode()])
        self.assertEqual(self.app.last_play, "window not listening")

    def test_a_closed_window_does_not_swallow_a_piece(self):
        # an old window's request is still waiting at the server, then a new window opens
        stale = threading.Thread(target=lambda: self.next_piece(0))
        stale.start()
        time.sleep(0.05)
        stop, thread, out = self.run_page(lambda i: {"id": i, "started": True})
        with mock.patch.object(brain, "ask", return_value="ঠিক আছে।"):
            self.app.start("thinking", self.app.reply, "hi")
            self.wait_idle()
        self.finish(stop, thread)
        stale.join()
        self.assertEqual(out["played"], ["ঠিক আছে।"])

    def test_python_plays_when_the_window_takes_but_never_starts(self):
        with mock.patch.object(web, "START_WAIT", 0.2):
            stop, thread, out = self.run_page(lambda i: {"id": i, "started": False})
            with mock.patch.object(brain, "ask", return_value="ঠিক আছে।"):
                self.app.start("thinking", self.app.reply, "hi")
                self.wait_idle()
            self.finish(stop, thread)
        self.assertEqual(self.local, ["ঠিক আছে।".encode()])

    def test_stop_reaches_the_window(self):
        before = self.updates()["stops"]
        self.request("POST", "/api/stop", {})
        self.assertEqual(self.updates()["stops"], before + 1)

    def test_audio_needs_the_token(self):
        self.assertEqual(self.request("GET", "/api/audio/next?after=0", token=False)[0], 403)
        self.assertEqual(self.next_piece(0)[0], 204)  # nothing to say
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
