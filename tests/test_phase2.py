"""App list and sympy math tests. The sympy ones run where sympy is installed (setup.bat, CI)."""
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent import apps, config, mathsolve, tools

START_MENU = {"WhatsApp": "shell:AppsFolder\\5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App",
              "Visual Studio Code": "C:\\ProgramData\\Start Menu\\Visual Studio Code.lnk",
              "Spotify": "shell:AppsFolder\\SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify",
              "Word": "shell:AppsFolder\\Microsoft.Office.WINWORD.EXE.15",
              "Microsoft Teams": "shell:AppsFolder\\MSTeams_8wekyb3d8bbwe!MSTeams"}
HAS_SYMPY = importlib.util.find_spec("sympy") is not None
REAL_INSTALLED = apps.installed


class AppTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        for patcher in (mock.patch.object(apps, "installed", return_value=START_MENU),
                        mock.patch.object(apps, "NICKNAMES_FILE", Path(folder.name, "apps.json")),
                        mock.patch.object(config, "DATA", Path(folder.name)),
                        mock.patch.object(apps, "launch")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_finds_installed_apps(self):
        self.assertEqual(apps.find("whatsapp")[0], "WhatsApp")
        self.assertEqual(apps.find("WhatsApp app")[0], "WhatsApp")
        self.assertEqual(apps.find("vs code")[0], None)  # needs a nickname, see below
        self.assertEqual(apps.find("visual studio")[0], "Visual Studio Code")
        self.assertEqual(apps.find("spotfy")[0], "Spotify")  # small spelling mistake
        self.assertEqual(apps.find("teams")[0], "Microsoft Teams")
        self.assertEqual(apps.find("Notepad"), ("notepad", "notepad.exe"))

    def test_opens_store_apps_through_the_start_menu(self):
        self.assertEqual(apps.open_app("WhatsApp"), "Opened WhatsApp")
        apps.launch.assert_called_once_with(START_MENU["WhatsApp"])

    def test_risky_apps_are_refused(self):
        for name in ("powershell", "Command Prompt", "Uninstall Spotify", "Registry Editor", "cmd"):
            self.assertIn("not allowed", apps.open_app(name), name)
        apps.launch.assert_not_called()
        self.assertTrue(apps.blocked("Windows PowerShell ISE"))
        self.assertFalse(apps.blocked("Spotify"))

    def test_unknown_app_gives_close_names(self):
        self.assertIn("Could not find", apps.open_app("photoshop"))
        apps.launch.assert_not_called()

    def test_nicknames_in_bangla_or_english(self):
        self.assertIn("Saved", apps.save_nickname("vs code", "Visual Studio Code"))
        self.assertIn("Saved", apps.save_nickname("গান", "spotify"))
        self.assertIn("not saved", apps.save_nickname("ps", "powershell"))
        self.assertEqual(apps.find("VS Code")[0], "Visual Studio Code")
        self.assertEqual(apps.open_app("গান"), "Opened Spotify")
        self.assertIn("গান = Spotify", apps.list_apps())
        self.assertIn("Spotify", apps.list_apps("spot"))

    def test_start_menu_list_is_read_and_filtered(self):
        rows = [{"Name": "WhatsApp", "AppID": "wa!App"}, {"Name": "Uninstall Foo", "AppID": "u"},
                {"Name": "Windows PowerShell", "AppID": "ps"}]
        done = mock.Mock(stdout=json.dumps(rows).encode())
        with mock.patch.object(apps.os, "name", "nt"), \
                mock.patch.object(apps.subprocess, "run", return_value=done):
            self.assertEqual(apps.start_menu(), {"WhatsApp": "wa!App"})

    def test_start_menu_shortcut_folders(self):
        with tempfile.TemporaryDirectory() as folder:
            programs = Path(folder, "Programs")
            (programs / "Tools").mkdir(parents=True)
            (programs / "Tools" / "Notepad++.lnk").write_text("x")
            (programs / "Uninstall Notepad++.lnk").write_text("x")
            with mock.patch.object(apps, "shortcut_folders", return_value=[programs]):
                self.assertEqual(list(apps.start_menu_shortcuts()), ["Notepad++"])

    def test_first_look_right_after_boot(self):
        with mock.patch.dict(apps._cache, {"time": None, "apps": {}}), \
                mock.patch.object(apps.time, "monotonic", return_value=5.0), \
                mock.patch.object(apps, "start_menu_shortcuts", return_value={"Zoom": "z.lnk"}), \
                mock.patch.object(apps, "start_menu", return_value={}):
            self.assertEqual(REAL_INSTALLED(), {"Zoom": "z.lnk"})

    def test_tools_are_registered(self):
        for name in ("open_app", "list_apps", "save_nickname", "math_solve"):
            self.assertIn(name, tools.FUNCTIONS)


class MathSafetyTests(unittest.TestCase):
    def test_only_plain_math_is_parsed(self):
        for bad in ("__import__('os')", "x.__class__", "().__class__", 'open("a")', "a[0]",
                    "lambda: 1", "x; import os", "{1}", "verylongfunctionname(1)"):
            with self.assertRaises(ValueError, msg=bad):
                mathsolve.check(bad.replace("; import os", "\nimport os"))
        self.assertEqual(mathsolve.check("2x^2 + 3.5x - 1 = 0"), "2x^2 + 3.5x - 1 = 0")
        self.assertEqual(mathsolve.check("x**2 × 3"), "x^2 * 3")

    def test_slow_math_is_stopped(self):
        with mock.patch.object(tools.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("python", 20)):
            self.assertIn("too long", tools.math_solve("integrate", "x"))


@unittest.skipUnless(HAS_SYMPY, "sympy not installed here")
class SympyTests(unittest.TestCase):
    def solve(self, task, expression, **extra):
        return tools.math_solve(task, expression, **extra)

    def test_equations(self):
        answer = self.solve("solve", "x^2-5x+6=0")
        self.assertIn("x = 2", answer)
        self.assertIn("x = 3", answer)
        system = self.solve("solve", "x+y=5; x-y=1")
        self.assertIn("x = 3", system)
        self.assertIn("y = 2", system)
        self.assertIn("sqrt(2)", self.solve("solve", "x^2=2"))
        self.assertIn("≈ 1.414213562", self.solve("solve", "x^2=2"))

    def test_calculus(self):
        self.assertEqual(self.solve("diff", "x^3 + sin(x)"), "3*x^2 + cos(x)")
        self.assertEqual(self.solve("diff", "x^3", order=2), "6*x")
        self.assertEqual(self.solve("integrate", "2x"), "x^2 + C")
        self.assertEqual(self.solve("integrate", "x^2", lower="0", upper="3"), "9")
        self.assertEqual(self.solve("limit", "sin(x)/x", point="0"), "1")
        self.assertEqual(self.solve("limit", "1/x", point="oo"), "0")

    def test_algebra(self):
        self.assertEqual(self.solve("factor", "x^2-9"), "(x - 3)*(x + 3)")
        self.assertEqual(self.solve("expand", "(a+b)^2"), "a^2 + 2*a*b + b^2")
        self.assertEqual(self.solve("simplify", "(x^2-1)/(x-1)"), "x + 1")
        self.assertIn("11/12", self.solve("evaluate", "2/3+1/4"))
        self.assertIn("120", self.solve("evaluate", "5!"))

    def test_bad_and_huge_input(self):
        self.assertIn("Math problem", self.solve("evaluate", "9^9^9"))
        self.assertIn("Math problem", self.solve("evaluate", "100000!"))
        self.assertIn("Math problem", self.solve("evaluate", "__import__('os')"))
        self.assertIn("Math problem", self.solve("dance", "x"))


if __name__ == "__main__":
    unittest.main()
