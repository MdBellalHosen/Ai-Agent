"""Window app, microphone and wake word tests. Offline: no mic, key or internet needed."""
import array
import http.client
import json
import math
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

from agent import brain, config, tools, voice, wake, web


def tone(seconds, loudness):
    n = int(voice.RATE * seconds)
    return array.array("h", (int(loudness * math.sin(i / 3)) for i in range(n))).tobytes()


class FakeStream:
    """Stands in for sounddevice.RawInputStream and plays back fixed audio."""

    def __init__(self, audio):
        self.audio = audio

    def __call__(self, **_):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, frames):
        size = frames * 2
        chunk, self.audio = self.audio[:size], self.audio[size:]
        return chunk.ljust(size, b"\0"), False


def fake_sounddevice(audio):
    return types.SimpleNamespace(RawInputStream=FakeStream(audio))


class RecordTests(unittest.TestCase):
    def record(self, audio, **kwargs):
        with mock.patch.dict(sys.modules, {"sounddevice": fake_sounddevice(audio)}):
            return voice.record(**kwargs)

    def test_stops_after_speech_then_silence(self):
        pcm, loudest = self.record(tone(0.5, 20) + tone(1.0, 4000) + tone(3.0, 20))
        self.assertGreater(loudest, 2000)
        self.assertLess(len(pcm) / 2 / voice.RATE, 3.0)  # stopped before the end

    def test_nothing_said(self):
        pcm, _ = self.record(tone(10, 20), wait=2)
        self.assertEqual(pcm, b"")

    def test_finish_button_keeps_quiet_audio(self):
        finish = threading.Event()
        finish.set()
        self.assertEqual(self.record(b"", finish=finish)[0], b"")  # nothing recorded yet

    def test_boost_makes_quiet_audio_louder(self):
        quiet = tone(0.2, 1000)
        self.assertGreater(voice.rms(voice.boost(quiet)), voice.rms(quiet) * 5)
        loud = tone(0.2, 20000)
        self.assertEqual(voice.boost(loud), loud)

    def fake_openai(self, gemini_text="আমার নাম কি", gemini_error=None):
        calls = []

        class Client:
            def __init__(self, **options):
                self.url = options.get("base_url", "")
                self.audio = types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=self.whisper))
                self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.gemini))

            def whisper(self, **request):
                calls.append(("groq", request))
                return types.SimpleNamespace(text=voice.HINTS["bn"])

            def gemini(self, **request):
                calls.append(("gemini", request))
                if gemini_error:
                    raise gemini_error
                message = types.SimpleNamespace(content=gemini_text)
                return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

        return calls, types.SimpleNamespace(OpenAI=Client)

    def transcribe(self, openai, gemini="g", groq="q", stt=None):
        env = {"STT": stt} if stt else {}
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(config, "GEMINI_KEY", gemini), mock.patch.object(config, "GROQ_KEY", groq), \
                mock.patch.object(config, "DATA", Path(folder)), \
                mock.patch.object(voice, "LAST_RECORDING", Path(folder, "last.wav")), \
                mock.patch.dict(os.environ, env), mock.patch.dict(sys.modules, {"openai": openai}), \
                mock.patch.dict(voice._clients, clear=True), \
                mock.patch("builtins.print"):
            text = voice.transcribe(b"wav", "bn")
            self.assertEqual(Path(folder, "last.wav").read_bytes(), b"wav")
            return text

    def test_gemini_writes_bangla_first(self):
        calls, openai = self.fake_openai()
        self.assertEqual(self.transcribe(openai), "আমার নাম কি")
        self.assertEqual([c[0] for c in calls], ["gemini"])
        parts = calls[0][1]["messages"][0]["content"]
        self.assertEqual(parts[1]["input_audio"]["format"], "wav")
        self.assertIn("Bangla", parts[0]["text"])

    def test_whisper_is_backup_and_drops_hint_echo(self):
        calls, openai = self.fake_openai(gemini_error=RuntimeError("quota"))
        self.assertEqual(self.transcribe(openai), "")
        self.assertEqual([c[0] for c in calls], ["gemini", "groq"])
        self.assertEqual(calls[1][1]["language"], "bn")
        self.assertEqual(calls[1][1]["prompt"], voice.HINTS["bn"])

    def test_choose_whisper_or_no_gemini_key(self):
        calls, openai = self.fake_openai()
        self.transcribe(openai, stt="groq")
        self.transcribe(openai, gemini="")
        self.assertEqual([c[0] for c in calls], ["groq", "groq"])


class WakeTests(unittest.TestCase):
    def test_wake_phrase(self):
        self.assertTrue(wake.is_wake({"text": "hey mira"}))
        self.assertTrue(wake.is_wake({"result": [{"word": "hi", "conf": 0.9}, {"word": "mirror", "conf": 0.8}]}))
        self.assertFalse(wake.is_wake({"result": [{"word": "hey", "conf": 0.9}, {"word": "mira", "conf": 0.3}]}))
        self.assertFalse(wake.is_wake({"text": "mira"}))
        self.assertFalse(wake.is_wake({"text": ""}))


class Base(unittest.TestCase):
    def setUp(self):
        brain.history.clear()
        brain.private_history.clear()
        for patcher in (mock.patch.dict(voice.settings, {"muted": False, "private": False}),
                        mock.patch.dict(tools.hooks), mock.patch.object(config, "GROQ_KEY", "test"),
                        mock.patch.object(web, "launch"), mock.patch.object(voice, "chime"),
                        mock.patch("builtins.print")):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.speak = mock.patch.object(voice, "speak").start()
        self.addCleanup(mock.patch.stopall)
        self.server = web.make_server(0)
        self.app = self.server.app
        self.app.install()
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]

    def request(self, method, path, body=None, token=True, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Host": host or f"127.0.0.1:{self.port}"}
        if token:
            headers["X-Token"] = self.app.token
        data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
        conn.request(method, path, body=data, headers=headers)
        res = conn.getresponse()
        raw = res.read()
        conn.close()
        try:
            return res.status, json.loads(raw)
        except ValueError:
            return res.status, raw.decode()

    def wait_idle(self):
        for _ in range(200):
            if not self.app.busy():
                return
            time.sleep(0.02)
        self.fail("still busy")

    def wait_state(self, state):
        for _ in range(200):
            if self.app.state == state:
                return
            time.sleep(0.02)
        self.fail(f"never reached {state}")

    def updates(self):
        return self.request("GET", "/api/updates")[1]


class SecurityTests(Base):
    def test_other_websites_cannot_use_it(self):
        self.assertEqual(self.request("GET", "/api/updates", token=False)[0], 403)
        self.assertEqual(self.request("POST", "/api/send", {"text": "hi"}, token=False)[0], 403)
        self.assertEqual(self.request("GET", "/", host="evil.example")[0], 403)  # DNS rebinding
        self.assertEqual(self.request("GET", "/api/updates", host=f"evil.example:{self.port}")[0], 403)

    def test_page_carries_token_and_strict_policy(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/")
        res = conn.getresponse()
        page = res.read().decode()
        self.assertIn(self.app.token, page)
        self.assertNotIn("__NONCE__", page)
        self.assertIn("script-src 'nonce-", res.getheader("Content-Security-Policy"))
        self.assertEqual(self.request("GET", "/api/ping", token=False), (200, {"app": "mira"}))

    def test_bad_input(self):
        self.assertEqual(self.request("POST", "/api/send", b"[1]")[0], 400)
        self.assertEqual(self.request("POST", "/api/send", {"text": "x", "image": "data:text/html;base64,AA"})[0], 400)
        self.assertEqual(self.request("POST", "/api/send", {"text": ""})[0], 400)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.putrequest("POST", "/api/send")
        conn.putheader("X-Token", self.app.token)
        conn.putheader("Content-Length", str(web.MAX_BODY + 1))
        conn.endheaders()
        self.assertEqual(conn.getresponse().status, 413)


class ChatTests(Base):
    def test_typed_message_is_answered_and_spoken(self):
        with mock.patch.object(brain, "ask", return_value="ভালো আছি") as ask:
            self.assertEqual(self.request("POST", "/api/send", {"text": "কেমন আছো?"})[0], 200)
            self.wait_idle()
        ask.assert_called_once_with("কেমন আছো?", image=None, private=False, spoken=False)
        self.assertEqual([(m["role"], m["text"]) for m in self.updates()["messages"]],
                         [("user", "কেমন আছো?"), ("mira", "ভালো আছি")])
        self.assertEqual(self.speak.call_args.args, ("ভালো আছি",))

    def test_picture_is_sent_to_the_brain(self):
        import base64
        import io
        from PIL import Image
        buffer = io.BytesIO()
        Image.new("RGB", (40, 20), "white").save(buffer, "PNG")
        data = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
        with mock.patch.object(brain, "ask", return_value="ok") as ask:
            self.request("POST", "/api/send", {"image": data})
            self.wait_idle()
        self.assertTrue(ask.call_args.kwargs["image"].startswith("data:image/jpeg;base64,"))

    def test_risky_action_needs_a_click(self):
        def ask(text, image=None, private=False, spoken=False):
            return "allowed" if tools.confirm("Shut down the PC?") else "stopped"

        with mock.patch.object(brain, "ask", side_effect=ask):
            self.request("POST", "/api/send", {"text": "shutdown"})
            self.wait_state("confirm")
            state = self.updates()
            self.assertEqual(state["question"], "Shut down the PC?")
            self.assertEqual(self.request("POST", "/api/confirm", {"ask": state["ask"], "yes": "yes"})[1]["ok"], True)
            self.wait_idle()
        self.assertEqual(self.updates()["messages"][-1]["text"], "stopped")  # only true approves

        with mock.patch.object(brain, "ask", side_effect=ask):
            self.request("POST", "/api/send", {"text": "shutdown"})
            self.wait_state("confirm")
            self.request("POST", "/api/confirm", {"ask": self.updates()["ask"], "yes": True})
            self.wait_idle()
        self.assertEqual(self.updates()["messages"][-1]["text"], "allowed")

    def test_confirm_from_outside_the_request_is_refused(self):
        self.assertFalse(tools.confirm("Open example.com?"))

    def test_one_job_at_a_time(self):
        release = threading.Event()
        with mock.patch.object(brain, "ask", side_effect=lambda *a, **k: release.wait(2) and "ok"):
            self.assertEqual(self.request("POST", "/api/send", {"text": "one"})[0], 200)
            self.assertEqual(self.request("POST", "/api/send", {"text": "two"})[0], 409)
            release.set()
            self.wait_idle()

    def test_private_mode_is_silent_and_separate(self):
        with mock.patch.object(brain, "ask", return_value="hello"):
            self.request("POST", "/api/send", {"text": "normal"})
            self.wait_idle()
            self.request("POST", "/api/settings", {"private": True})
            self.request("POST", "/api/send", {"text": "secret"})
            self.wait_idle()
        self.assertEqual([m["text"] for m in self.updates()["messages"]], ["secret", "hello"])
        self.speak.assert_called_once()  # only the normal answer
        with mock.patch.object(voice, "record") as record:
            self.request("POST", "/api/mic", {})
            self.wait_idle()
        record.assert_not_called()
        self.assertIn("প্রাইভেট", self.updates()["notice"]["text"])

    def test_reminder_shows_in_window(self):
        tools.hooks["announce"]("পানি খাও")
        self.assertIn("পানি খাও", self.updates()["messages"][-1]["text"])


class VoiceTests(Base):
    def test_voice_turn(self):
        with mock.patch.object(voice, "record", return_value=(tone(1, 3000), 3000)), \
                mock.patch.object(voice, "transcribe", return_value="নোটপ্যাড খোলো") as transcribe, \
                mock.patch.object(brain, "ask", return_value="খুলেছি"):
            self.request("POST", "/api/settings", {"language": "bn"})
            self.request("POST", "/api/mic", {})
            self.wait_idle()
        self.assertEqual(transcribe.call_args.args[1], "bn")
        messages = self.updates()["messages"]
        self.assertTrue(messages[0]["voice"])
        self.assertEqual(messages[1]["text"], "খুলেছি")

    def test_quiet_mic_gets_a_tip(self):
        with mock.patch.object(voice, "record", return_value=(b"", 80)):
            self.request("POST", "/api/mic", {})
            self.wait_idle()
        self.assertIn("আওয়াজ", self.updates()["notice"]["text"])

    def test_conversation_mode_listens_again(self):
        heard = iter([(tone(1, 3000), 3000), (tone(1, 3000), 3000), (b"", 2000)])
        with mock.patch.object(voice, "record", side_effect=lambda *a, **k: next(heard)), \
                mock.patch.object(voice, "transcribe", side_effect=["এক", "দুই"]), \
                mock.patch.object(brain, "ask", return_value="হুম"):
            self.request("POST", "/api/settings", {"convo": True})
            self.request("POST", "/api/mic", {})
            self.wait_idle()
        self.assertEqual([m["text"] for m in self.updates()["messages"] if m["role"] == "user"], ["এক", "দুই"])

    def test_hey_mira_opens_the_window_and_listens(self):
        with mock.patch.object(voice, "record", return_value=(tone(1, 3000), 3000)), \
                mock.patch.object(voice, "transcribe", return_value="সময় কত?"), \
                mock.patch.object(brain, "ask", return_value="রাত তিনটা"), \
                mock.patch.object(web, "CHIME_DELAY", 0):
            self.app.last_seen = 0  # no window open yet
            self.app.heard_wake()
            self.assertTrue(self.app.busy())  # wake word pauses at once
            self.wait_idle()
        web.launch.assert_called_once_with(self.app.url)
        voice.chime.assert_called_once()
        self.assertEqual(self.updates()["messages"][-1]["text"], "রাত তিনটা")


if __name__ == "__main__":
    unittest.main()
