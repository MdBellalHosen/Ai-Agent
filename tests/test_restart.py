"""After git pull, opening Mira replaces the older copy still running from Windows start."""
import types
import unittest
from unittest import mock

from agent import web


class RestartTests(unittest.TestCase):
    def serve(self, other, stopped=True):
        server = mock.MagicMock()
        with mock.patch.object(web, "make_server", side_effect=[OSError("busy"), server]) as make, \
                mock.patch.object(web, "running", return_value=other), \
                mock.patch.object(web, "stop_old", return_value=stopped) as stop, \
                mock.patch.object(web, "launch") as launch, mock.patch.object(web.time, "sleep"), \
                mock.patch.object(web.threading, "Thread"), mock.patch.object(web.apps, "preload"), \
                mock.patch.object(web.screen, "track_focus"), mock.patch.object(web.tray, "start", return_value=None), \
                mock.patch("builtins.print"):
            server.app.wake = None
            code = web.serve(open_window=True, port=8765)
        return code, make.call_count, stop.called, launch

    def test_same_version_just_opens_the_window(self):
        code, made, stopped, launch = self.serve({"app": "mira", "version": web.VERSION})
        self.assertEqual((code, made, stopped), (0, 1, False))
        launch.assert_called_once()

    def test_old_version_is_replaced(self):
        code, made, stopped, _ = self.serve({"app": "mira"})  # old copies send no version
        self.assertEqual((made, stopped), (2, True))

    def test_other_program_on_the_port_is_left_alone(self):
        code, made, stopped, _ = self.serve(None)
        self.assertEqual((code, made, stopped), (1, 1, False))

    def test_only_python_is_stopped(self):
        netstat = types.SimpleNamespace(stdout="  TCP    127.0.0.1:8765   0.0.0.0:0   LISTENING   4242\n")
        tasklist = types.SimpleNamespace(stdout='"chrome.exe","4242","Console"')
        with mock.patch.object(web.os, "name", "nt"), \
                mock.patch.object(web.subprocess, "run", side_effect=[netstat, tasklist]) as run, \
                mock.patch.object(web, "running", return_value={"app": "mira"}), mock.patch.object(web.time, "sleep"):
            self.assertFalse(web.stop_old(8765))
        self.assertEqual(run.call_count, 2)  # no taskkill

    def test_version_changes_with_code(self):
        self.assertEqual(len(web.VERSION), 10)
        self.assertEqual(web.code_version(), web.VERSION)


if __name__ == "__main__":
    unittest.main()
