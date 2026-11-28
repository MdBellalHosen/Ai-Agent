"""Full PC control: focus goes back to the user's app, clicking by description, files, settings."""
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from agent import brain, config, control, screen, tools
from tests.test_control import FakeKeys


class FakeUser32:
    def __init__(self, front, titles):
        self.front, self.titles, self.raised = front, titles, []

    def GetForegroundWindow(self):
        return self.front

    def IsWindow(self, hwnd):
        return hwnd in self.titles

    def IsIconic(self, hwnd):
        return False

    def GetWindowThreadProcessId(self, hwnd, _):
        return 1

    def AttachThreadInput(self, *a):
        return True

    def SetForegroundWindow(self, hwnd):
        self.front = hwnd
        self.raised.append(hwnd)

    def BringWindowToTop(self, hwnd):
        return True

    def ShowWindow(self, *a):
        return True


class FocusTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeUser32(1, {1: "Mira", 2: "notes.txt - Notepad"})
        kernel = types.SimpleNamespace(GetCurrentThreadId=lambda: 9)
        for patcher in (mock.patch.object(screen, "user32", return_value=self.fake),
                        mock.patch.object(screen, "title_of", side_effect=lambda h: self.fake.titles.get(h, "")),
                        mock.patch.object(screen.os, "name", "nt"),
                        mock.patch.object(screen.ctypes, "windll", types.SimpleNamespace(kernel32=kernel), create=True),
                        mock.patch.object(screen.time, "sleep"),
                        mock.patch.dict(screen._focus, {"hwnd": 2, "title": "notes.txt - Notepad"})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_keys_go_back_to_the_users_app(self):
        self.assertEqual(screen.focus_target(), "notes.txt - Notepad")
        self.assertEqual(self.fake.raised, [2])

    def test_no_change_when_the_app_is_in_front(self):
        self.fake.front = 2
        self.assertEqual(screen.focus_target(), "notes.txt - Notepad")
        self.assertEqual(self.fake.raised, [])

    def test_mira_window_names(self):
        self.assertTrue(screen.is_mira("Mira"))
        self.assertTrue(screen.is_mira("Mira - Microsoft Edge"))
        self.assertFalse(screen.is_mira("Mirage game"))

    def test_switch_to(self):
        with mock.patch.object(screen, "windows", return_value=[(1, "Mira"), (2, "notes.txt - Notepad")]):
            self.assertEqual(screen.switch_to("notepad"), "Switched to notes.txt - Notepad")
            self.assertIn("No open window", screen.switch_to("excel"))
            self.assertNotIn("Mira", screen.list_windows())

    def test_typing_focuses_first(self):
        keys = FakeKeys()
        with mock.patch.dict(sys.modules, {"pyautogui": keys}), mock.patch("agent.files.copy_to_clipboard"), \
                mock.patch.object(control, "window_title", return_value="notes.txt - Notepad"), \
                mock.patch.object(screen, "focus_target") as focus:
            control.type_text("hello")
            control.press_keys("ctrl+s")
        self.assertEqual(focus.call_count, 2)


class ClickTests(unittest.TestCase):
    def setUp(self):
        self.keys = FakeKeys()
        self.keys.size = lambda: (1920, 1080)
        picture = types.SimpleNamespace(width=3840, height=2160)  # a 4K screen at 200% scale
        for patcher in (mock.patch.dict(sys.modules, {"pyautogui": self.keys}),
                        mock.patch.object(screen, "focus_target"), mock.patch.object(screen, "grab", return_value=picture),
                        mock.patch.object(control, "window_title", return_value="YouTube - Google Chrome"),
                        mock.patch.object(screen.time, "sleep")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def vision(self, answer):
        return mock.patch.object(screen, "ask_vision", return_value=answer)

    def test_click_maps_to_the_screen(self):
        with self.vision('```json\n{"found": true, "x": 500, "y": 250, "label": "Search box"}\n```'):
            self.assertEqual(screen.click_on("the search box"), "Clicked Search box at (960, 270)")
        self.assertEqual(self.keys.calls, [("click", (960.0, 270.0))])

    def test_not_found(self):
        with self.vision('{"found": false, "label": "a login page"}'):
            self.assertIn("a login page", screen.click_on("play button"))
        self.assertEqual(self.keys.calls, [])

    def test_risky_clicks_ask_first(self):
        with self.vision('{"found": true, "x": 10, "y": 10, "label": "Delete account"}'), \
                mock.patch("builtins.input", return_value="no"):
            self.assertEqual(screen.click_on("the red button"), "User did not allow it")
        self.assertEqual(self.keys.calls, [])

    def test_never_clicks_in_command_windows(self):
        with mock.patch.object(control, "window_title", return_value="Windows PowerShell"):
            self.assertIn("command window", screen.click_on("anything"))


class FileTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name)
        for name in ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos"):
            (self.home / name).mkdir()
        (self.home / "Downloads" / "cv.pdf").write_text("cv")
        (self.home / "secret.txt").write_text("x")
        for patcher in (mock.patch.object(Path, "home", return_value=self.home), mock.patch("builtins.print"),
                        mock.patch.object(control.os, "startfile", create=True)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_create_rename_move_copy(self):
        self.assertIn("Created", control.file_action("create_folder", "Documents\\Job"))
        self.assertIn("Renamed", control.file_action("rename", "Downloads\\cv.pdf", "my-cv.pdf"))
        self.assertIn("Copied", control.file_action("copy", "Downloads\\my-cv.pdf", "Desktop"))
        self.assertIn("Moved", control.file_action("move", "Downloads/my-cv.pdf", "Documents\\Job"))
        self.assertTrue((self.home / "Documents" / "Job" / "my-cv.pdf").exists())
        self.assertTrue((self.home / "Desktop" / "my-cv.pdf").exists())
        self.assertIn("already exists", control.file_action("copy", "Desktop\\my-cv.pdf", "Documents\\Job"))

    def test_delete_goes_to_recycle_bin_after_yes(self):
        with mock.patch.object(control, "to_recycle_bin") as bin_, mock.patch("builtins.input", return_value="yes"):
            self.assertIn("Recycle Bin", control.file_action("delete", "Downloads\\cv.pdf"))
        bin_.assert_called_once()
        with mock.patch.object(control, "to_recycle_bin") as bin_, mock.patch("builtins.input", return_value="no"):
            self.assertEqual(control.file_action("delete", "Downloads\\cv.pdf"), "User did not allow it")
        bin_.assert_not_called()

    def test_stays_inside_user_folders(self):
        self.assertIn("only works", control.file_action("delete", str(self.home / "secret.txt")))
        self.assertIn("only works", control.file_action("move", "Downloads\\cv.pdf", str(self.home.parent)))
        self.assertIn("only works", control.file_action("copy", "Downloads\\cv.pdf", "Downloads\\..\\.."))

    def test_open_and_list(self):
        (self.home / "Downloads" / "setup.exe").write_text("x")
        self.assertIn("Opened", control.open_file("Downloads\\cv.pdf"))
        self.assertIn("runs a program", control.open_file("Downloads\\setup.exe"))
        self.assertIn("cv.pdf", control.list_folder("Downloads"))
        self.assertIn("Found 0", control.open_file("nothing-like-this"))

    def test_settings_pages(self):
        self.assertEqual(control.open_settings("Night light"), "Opened night light settings")
        control.os.startfile.assert_called_with("ms-settings:nightlight")
        self.assertIn("must be one of", control.open_settings("registry"))


class PlanTests(unittest.TestCase):
    def test_enough_steps_and_instructions(self):
        self.assertGreaterEqual(brain.MAX_STEPS, 12)
        self.assertIn("look_at_screen", brain.system_prompt())
        for name in ("click_on", "look_at_screen", "switch_to", "file_action", "open_settings"):
            self.assertIn(name, tools.FUNCTIONS)
        self.assertNotIn("click_on", tools.SAFE_WITH_IMAGE)


if __name__ == "__main__":
    unittest.main()
