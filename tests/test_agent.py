"""Offline tests: no API key, microphone or internet needed."""
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from agent import brain, config, memory, tools, vision, voice
from agent.calculator import calculate


class Call:
    id = "c1"

    def __init__(self, name, arguments="{}"):
        self.function = types.SimpleNamespace(name=name, arguments=arguments)

    def model_dump(self, **_):
        return {"id": self.id, "type": "function", "extra_content": {"keep": "me"},
                "function": {"name": self.function.name, "arguments": self.function.arguments}}


def reply(content=None, calls=None):
    return types.SimpleNamespace(content=content, tool_calls=calls)


class FakeModels:
    """Plays back scripted replies and records every request."""

    def __init__(self, *script):
        self.script, self.requests = list(script), []

    def __call__(self, _brain):
        def create(**request):
            self.requests.append(json.loads(json.dumps(request)))
            item = self.script.pop(0)
            if isinstance(item, Exception):
                raise item
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=item)])
        return types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))


BRAINS = [{"name": "gemini", "vision": True, "model": "cloud"},
          {"name": "groq", "vision": False, "model": "text-only"},
          {"name": "ollama", "vision": True, "model": "local"}]


class CalculatorTests(unittest.TestCase):
    def test_math(self):
        self.assertEqual(calculate("sqrt(16)+3^2"), "13.0")
        self.assertEqual(calculate("(2+3)*4/5"), "4.0")

    def test_rejects_code_and_huge_powers(self):
        for bad in ("__import__('os').system('x')", "open('a')", "9**9**9", "(10**100)**100"):
            with self.assertRaises(ValueError, msg=bad):
                calculate(bad)


class ChatTests(unittest.TestCase):
    def setUp(self):
        brain.history.clear()
        brain.private_history.clear()
        patcher = mock.patch.object(config, "BRAINS", BRAINS)
        patcher.start()
        self.addCleanup(patcher.stop)

    def ask(self, models, *args, **kwargs):
        with mock.patch.object(brain, "make_client", models), mock.patch("builtins.print"):
            return brain.ask(*args, **kwargs)

    def test_tool_call_round_trip(self):
        models = FakeModels(reply(calls=[Call("calculate", '{"expression":"6*7"}')]), reply("42"))
        self.assertEqual(self.ask(models, "6*7?"), "42")
        messages = models.requests[-1]["messages"]
        self.assertEqual(messages[-1]["content"], "42")
        self.assertIn("extra_content", messages[-2]["tool_calls"][0])
        self.assertEqual(len(brain.history), 2)

    def test_picture_cannot_trigger_pc_actions(self):
        models = FakeModels(reply(calls=[Call("lock_pc")]), reply("done"))
        with mock.patch.dict(tools.FUNCTIONS, {"lock_pc": mock.Mock()}) as functions:
            self.ask(models, "look", image="data:x")
            functions["lock_pc"].assert_not_called()
        self.assertEqual([t["function"]["name"] for t in models.requests[0]["tools"]], ["calculate"])

    def test_private_chat_stays_local(self):
        models = FakeModels(reply("ok"), reply("hello"))
        self.ask(models, "secret", private=True)
        self.ask(models, "hi")
        self.assertEqual(models.requests[0]["model"], "local")
        self.assertNotIn("tools", models.requests[0])
        self.assertNotIn("secret", json.dumps(models.requests[1]))

    def test_next_brain_is_used_when_one_fails(self):
        models = FakeModels(RuntimeError("quota"), reply("fallback"))
        self.assertEqual(self.ask(models, "hi"), "fallback")
        self.assertEqual([r["model"] for r in models.requests], ["cloud", "text-only"])

    def test_actions_are_not_repeated_after_a_failure(self):
        action = mock.Mock(return_value="locked")
        models = FakeModels(reply(calls=[Call("lock_pc")]), RuntimeError("network"))
        with mock.patch.dict(tools.FUNCTIONS, {"lock_pc": action}):
            self.ask(models, "lock")
        action.assert_called_once()
        self.assertEqual(len(models.requests), 2)


class ToolTests(unittest.TestCase):
    def test_risky_actions_need_yes(self):
        with mock.patch("builtins.input", return_value="no"), \
                mock.patch("os.system") as system, mock.patch("webbrowser.open") as browser:
            self.assertEqual(tools.shutdown_pc(), "User did not allow it")
            self.assertEqual(tools.open_website("example.com"), "User did not allow it")
        system.assert_not_called()
        browser.assert_not_called()

    def test_only_listed_apps_open(self):
        with mock.patch("os.startfile", create=True) as start:
            self.assertIn("Not in the allowed list", tools.open_app("powershell"))
            tools.open_app("Notepad")
        start.assert_called_once_with("notepad.exe")

    def test_find_file(self):
        with tempfile.TemporaryDirectory() as home:
            folder = Path(home, "OneDrive", "Documents")
            folder.mkdir(parents=True)
            (folder / "Math-Assignment.pdf").write_text("x")
            with mock.patch.object(Path, "home", return_value=Path(home)):
                self.assertIn("Math-Assignment.pdf", tools.find_file("assignment"))
                self.assertEqual(tools.find_file("nothing-here"), "No file found")

    def test_bad_arguments_do_not_crash(self):
        with mock.patch("builtins.print"):
            self.assertTrue(tools.run_tool("volume", "not json").startswith("Tool error"))

    def test_every_tool_has_a_schema(self):
        self.assertEqual({s["function"]["name"] for s in tools.SCHEMAS}, set(tools.FUNCTIONS))


class StorageTests(unittest.TestCase):
    def test_memory_and_notes_keep_bangla(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder, "data")
            with mock.patch.multiple(config, DATA=data, MEMORY_FILE=data / "memory.json",
                                     NOTES_FILE=data / "notes.txt"):
                memory.remember("আমি চা পছন্দ করি")
                memory.add_note("পরীক্ষার রুটিন")
                self.assertEqual(memory.load_memory(), ["আমি চা পছন্দ করি"])
                self.assertIn("পরীক্ষার রুটিন", memory.read_notes())
                self.assertIn("আমি চা পছন্দ করি", brain.system_prompt())


class VoiceAndImageTests(unittest.TestCase):
    def test_voice_follows_language(self):
        self.assertEqual(voice.pick_voice("কেমন আছো?"), config.VOICE_BN)
        self.assertEqual(voice.pick_voice("How are you?"), config.VOICE_EN)

    def test_private_and_muted_stay_silent(self):
        for key in ("private", "muted"):
            with mock.patch.dict(voice.settings, {key: True}), \
                    mock.patch.object(voice, "clean_text") as clean:
                voice.speak("secret")
            clean.assert_not_called()

    def test_picture_is_resized_to_jpeg(self):
        from PIL import Image
        url = vision.image_url(Image.new("RGBA", (4000, 2000)))
        self.assertTrue(url.startswith("data:image/jpeg;base64,"))


if __name__ == "__main__":
    unittest.main()
