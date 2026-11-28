"""PC control, WhatsApp, voice backups and faster thinking."""
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from agent import brain, config, control, tools, voice, web
from tests.test_app import Base


class FakeKeys:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *a, **k: self.calls.append((name, a))


class KeyTests(unittest.TestCase):
    def setUp(self):
        self.keys = FakeKeys()
        for patcher in (mock.patch.dict(sys.modules, {"pyautogui": self.keys}),
                        mock.patch.object(control, "window_title", return_value="Notepad")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_shortcuts(self):
        self.assertEqual(control.press_keys("Ctrl + S"), "Pressed ctrl+s")
        self.assertEqual(control.press_keys("windows+d"), "Pressed win+d")
        self.assertEqual(self.keys.calls[-1], ("hotkey", ("winleft", "d")))
        self.assertEqual(control.press_keys("ctrl++"), "Pressed ctrl++")

    def test_dangerous_keys_refused(self):
        self.assertIn("not allowed", control.press_keys("win+r"))
        self.assertIn("Unknown", control.press_keys("ctrl+sudo"))
        with mock.patch.object(control, "window_title", return_value="Administrator: Windows PowerShell"):
            self.assertIn("command window", control.press_keys("enter"))
            self.assertIn("command window", control.type_text("del *"))
        with mock.patch.object(control, "window_title", return_value="Run"):
            self.assertIn("command window", control.type_text("cmd"))
        self.assertEqual(self.keys.calls, [])

    def test_typing_uses_clipboard_for_bangla(self):
        with mock.patch("agent.files.copy_to_clipboard") as copy:
            control.type_text("আমি আসছি", press_enter=True)
        copy.assert_called_once_with("আমি আসছি")
        self.assertEqual([c[0] for c in self.keys.calls], ["hotkey", "press"])

    def test_window_and_media(self):
        self.assertIn("minimize", control.window("minimize"))
        self.assertIn("must be", control.window("explode"))
        self.assertEqual(control.media("play_pause"), "Media play pause")
        self.assertEqual(self.keys.calls[-1], ("press", ("playpause",)))


class AppTests(unittest.TestCase):
    def test_close_app_asks_and_protects_windows(self):
        listing = '"chrome.exe","1","Console"\n"explorer.exe","2","Console"\n"Spotify.exe","3","Console"\n'
        tasklist = types.SimpleNamespace(stdout=listing)
        with mock.patch.object(control.subprocess, "run", return_value=tasklist) as run, \
                mock.patch("builtins.input", return_value="yes"), mock.patch("builtins.print"):
            self.assertEqual(control.close_app("spotify"), "Asked Spotify.exe to close")
            self.assertEqual(run.call_args.args[0], ["taskkill", "/IM", "Spotify.exe"])
            self.assertIn("not running", control.close_app("explorer"))
        with mock.patch.object(control.subprocess, "run", return_value=tasklist), \
                mock.patch("builtins.input", return_value="no"), mock.patch("builtins.print"):
            self.assertEqual(control.close_app("chrome"), "User did not allow it")

    def test_status_has_disk(self):
        self.assertIn("Disk free", control.system_status())


class WhatsAppTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.opened = []
        for patcher in (mock.patch.object(config, "DATA", Path(folder.name)),
                        mock.patch.object(control, "CONTACTS_FILE", Path(folder.name, "contacts.json")),
                        mock.patch.object(control.webbrowser, "open", side_effect=self.opened.append),
                        mock.patch.object(control, "desktop_whatsapp", return_value=False),
                        mock.patch.object(control.time, "sleep"),
                        mock.patch.object(control, "window_title", return_value="WhatsApp - Google Chrome"),
                        mock.patch("builtins.print")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_numbers(self):
        self.assertEqual(control.phone_number("01712-345678"), "8801712345678")
        self.assertEqual(control.phone_number("+880 1712 345678"), "8801712345678")
        self.assertEqual(control.phone_number("12"), "")

    def test_send_to_saved_contact(self):
        self.assertIn("Saved", control.save_contact("Anika", "01712345678"))
        keys = FakeKeys()
        with mock.patch("builtins.input", return_value="yes"), mock.patch.dict(sys.modules, {"pyautogui": keys}):
            result = control.whatsapp_message("anika", "আমি ১০ মিনিটে আসছি")
        self.assertIn("Sent to Anika", result)
        self.assertIn("web.whatsapp.com/send?phone=8801712345678&text=%E0%A6%86", self.opened[0])
        self.assertEqual(keys.calls, [("press", ("enter",))])

    def test_unknown_contact_and_refusal(self):
        self.assertIn("No WhatsApp number", control.whatsapp_message("Rafi", "hi"))
        control.save_contact("Rafi", "01812345678")
        with mock.patch("builtins.input", return_value="no"):
            self.assertEqual(control.whatsapp_message("Rafi", "hi"), "User did not allow it")
        self.assertEqual(self.opened, [])

    def test_does_not_press_enter_in_another_window(self):
        control.save_contact("Rafi", "01812345678")
        keys = FakeKeys()
        with mock.patch("builtins.input", return_value="yes"), mock.patch.dict(sys.modules, {"pyautogui": keys}), \
                mock.patch.object(control, "window_title", return_value="Notepad"), \
                mock.patch.object(control.time, "monotonic", side_effect=[0, 100]):
            self.assertIn("press Enter", control.whatsapp_message("rafi", "hi"))
        self.assertEqual(keys.calls, [])


class ThinkingTests(unittest.TestCase):
    def test_low_thinking_and_fallback(self):
        gemini = {"name": "gemini", "model": "m"}
        reply = types.SimpleNamespace(choices=[types.SimpleNamespace(message="ok")])
        calls = []

        def create(**request):
            calls.append(request)
            if "reasoning_effort" in request:
                raise ValueError("400 Invalid reasoning_effort: low")
            return reply

        client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
        with mock.patch("builtins.print"):
            self.assertEqual(brain.complete(client, gemini, [], {}), "ok")
            self.assertEqual(brain.complete(client, gemini, [], {}), "ok")
        self.assertEqual(calls[0]["reasoning_effort"], "low")
        self.assertEqual(len(calls), 3)  # refused once, then never sent again


class VoiceBackupTests(unittest.TestCase):
    def test_problem_is_shown_not_silent(self):
        told = []
        with mock.patch.dict(voice.settings, {"muted": False, "private": False}), \
                mock.patch.dict(voice.problems, {"report": told.append}), \
                mock.patch.object(voice, "tts_bytes", side_effect=OSError("no internet")), \
                mock.patch("builtins.print"):
            voice.speak("আমি মিরা")
        self.assertIn("ইন্টারনেট", told[0])

    def test_english_falls_back_to_windows_voice(self):
        with mock.patch.dict(voice.settings, {"muted": False, "private": False}), \
                mock.patch.object(voice, "tts_bytes", side_effect=OSError("blocked")), \
                mock.patch.object(voice.os, "name", "nt"), \
                mock.patch.object(voice, "windows_voice") as backup:
            voice.speak("Hello there")
        backup.assert_called_once_with("Hello there")


class AppVoiceTests(Base):
    def test_voice_test_reports_each_step(self):
        played = []
        with mock.patch.object(voice, "tts_bytes", return_value=b"mp3"), \
                mock.patch.object(voice, "play_mp3", side_effect=played.append), \
                mock.patch.object(web, "BROWSER_PICKUP", 0.1):
            self.request("POST", "/api/voicetest", {})
            self.wait_idle()
        report = self.updates()["messages"][-1]["text"]
        self.assertIn(web.VERSION, report)
        self.assertIn("ভয়েস তৈরি (Microsoft): ঠিক আছে", report)
        self.assertIn("জানালা থেকে বাজানো: হয়নি (window did not answer)", report)
        self.assertIn("Python থেকে বাজানো: ঠিক আছে", report)
        self.assertEqual(played, [b"mp3"])

    def test_voice_test_when_muted(self):
        self.request("POST", "/api/settings", {"muted": True})
        self.request("POST", "/api/voicetest", {})
        self.wait_idle()
        self.assertIn("ভয়েস: বন্ধ", self.updates()["messages"][-1]["text"])

    def test_tools_registered(self):
        for name in ("press_keys", "type_text", "whatsapp_message", "save_contact", "close_app"):
            self.assertIn(name, tools.FUNCTIONS)


if __name__ == "__main__":
    unittest.main()
