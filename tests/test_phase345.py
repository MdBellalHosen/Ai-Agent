"""Phase 3-5 tests: tray, offline mic, documents, clipboard, organizer, web info, Google, study, mood."""
import base64
import datetime as dt
import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
import wave
from pathlib import Path
from unittest import mock

from agent import brain, config, daily, files, google, info, study, tools, voice, wake, web
from tests.test_app import Base, tone


def wav(seconds=1):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(tone(seconds, 3000))
    return buffer.getvalue()


class DataFolder(unittest.TestCase):
    """Every file Mira writes goes to a temporary data folder."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.data = Path(folder.name, "data")
        self.home = Path(folder.name, "home")
        for path in ("Downloads", "Documents", "Desktop"):
            (self.home / path).mkdir(parents=True)
        patches = [mock.patch.object(config, "DATA", self.data),
                   mock.patch.object(files, "UPLOADS", self.data / "uploads"),
                   mock.patch.object(files, "UNDO_FILE", self.data / "undo.json"),
                   mock.patch.object(study, "CARDS_FILE", self.data / "cards.json"),
                   mock.patch.object(study, "MOOD_FILE", self.data / "mood.json"),
                   mock.patch.object(Path, "home", return_value=self.home),
                   mock.patch("builtins.print")]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)


class OfflineVoiceTests(unittest.TestCase):
    def test_english_works_without_internet(self):
        with mock.patch.object(config, "GEMINI_KEY", ""), mock.patch.object(config, "GROQ_KEY", ""), \
                mock.patch.object(wake, "installed", return_value=True), \
                mock.patch.object(wake, "offline_transcribe", return_value="open notepad") as offline:
            self.assertTrue(voice.can_listen())
            self.assertEqual(voice.transcribe(wav(), "en"), "open notepad")
        self.assertEqual(len(offline.call_args.args[0]), 32000)  # raw audio, header removed

    def test_bangla_offline_explains(self):
        with mock.patch.object(wake, "installed", return_value=True):
            with self.assertRaises(voice.Offline):
                voice.transcribe(wav(), "bn", offline_only=True)

    def test_private_mode_never_uses_the_cloud(self):
        with mock.patch.object(config, "GEMINI_KEY", "g"), \
                mock.patch.object(voice, "gemini_transcribe") as cloud, \
                mock.patch.object(wake, "installed", return_value=True), \
                mock.patch.object(wake, "offline_transcribe", return_value="hello"):
            self.assertEqual(voice.transcribe(wav(), "en", offline_only=True), "hello")
        cloud.assert_not_called()

    def test_cloud_failure_falls_back_to_offline(self):
        with mock.patch.object(config, "GEMINI_KEY", "g"), mock.patch.object(config, "GROQ_KEY", ""), \
                mock.patch.object(voice, "gemini_transcribe", side_effect=OSError("no internet")), \
                mock.patch.object(wake, "installed", return_value=True), \
                mock.patch.object(wake, "offline_transcribe", return_value="hello"), \
                mock.patch.object(voice, "LAST_RECORDING", Path(tempfile.gettempdir(), "mira-test.wav")), \
                mock.patch("builtins.print"):
            self.assertEqual(voice.transcribe(wav(), "en"), "hello")

    def test_tiny_local_model_cannot_see_pictures(self):
        with mock.patch.object(config, "BRAINS", [{"name": "ollama", "vision": False}]):
            self.assertIn("ছবি", brain.ask("look", image="data:x", private=True))


class PrivateMicTests(Base):
    def test_private_english_mic_stays_offline(self):
        with mock.patch.object(voice, "record", return_value=(tone(1, 3000), 3000)), \
                mock.patch.object(voice, "offline_ready", return_value=True), \
                mock.patch.object(voice, "transcribe", return_value="hello") as transcribe, \
                mock.patch.object(brain, "ask", return_value="hi"):
            self.request("POST", "/api/settings", {"private": True, "language": "en"})
            self.request("POST", "/api/mic", {})
            self.wait_idle()
        self.assertTrue(transcribe.call_args.kwargs["offline_only"])
        self.speak.assert_not_called()

    def test_document_upload(self):
        data = "data:application/pdf;base64," + base64.b64encode(b"%PDF-1.4 test").decode()
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(files, "UPLOADS", Path(folder)), \
                mock.patch.object(brain, "ask", return_value="ok") as ask:
            self.request("POST", "/api/send", {"document": {"name": "../../Chapter 1.pdf", "data": data}})
            self.wait_idle()
            self.assertTrue(Path(folder, "Chapter 1.pdf").exists())
        self.assertIn("read_document", ask.call_args.args[0])
        self.assertEqual(self.updates()["messages"][0]["document"], "Chapter 1.pdf")
        bad = {"name": "virus.exe", "data": data}
        self.assertEqual(self.request("POST", "/api/send", {"document": bad})[0], 400)


@unittest.skipUnless(importlib.util.find_spec("pystray"), "pystray not installed here")
class TrayTests(unittest.TestCase):
    def test_tray_menu(self):
        import pystray
        app = mock.Mock(url="http://127.0.0.1:1/")
        with mock.patch.object(pystray.Icon, "run_detached"):
            icon = web.tray.start(app, mock.Mock(), mock.Mock())
        self.assertIsNotNone(icon)
        names = [i.text for i in icon.menu.items if i is not pystray.Menu.SEPARATOR]
        self.assertEqual(len(names), 5)


class DocumentTests(DataFolder):
    def test_text_file(self):
        (self.home / "Documents" / "notes-physics.txt").write_text("নিউটনের সূত্র", encoding="utf-8")
        self.assertIn("নিউটনের সূত্র", files.read_document("physics"))
        self.assertIn("Could not find", files.read_document("nothing"))

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "pypdf not installed here")
    def test_pdf_pages(self):
        from pypdf import PdfWriter
        writer = PdfWriter()
        for _ in range(3):
            writer.add_blank_page(100, 100)
        with open(self.home / "Downloads" / "book.pdf", "wb") as f:
            writer.write(f)
        result = files.read_document("book", pages=2)
        self.assertIn("pages 1-2 of 3", result)
        self.assertIn("start_page=3", result)
        self.assertIn("scanned", result)

    def test_upload_names_are_safe(self):
        path = files.save_upload('..\\..\\a<b>.txt', b"x")
        self.assertEqual(path.parent, files.UPLOADS)
        self.assertEqual(files.save_upload("a_b_.txt", b"y").name, "a_b_ (1).txt")
        with self.assertRaises(ValueError):
            files.save_upload("run.bat", b"x")


class ClipboardTests(unittest.TestCase):
    def test_clipboard_uses_utf8(self):
        done = mock.Mock(stdout="আমি ভাত খাই\r\n".encode())
        with mock.patch.object(files.subprocess, "run", return_value=done) as run:
            self.assertEqual(files.read_clipboard(), "আমি ভাত খাই")
            files.copy_to_clipboard("I eat rice")
        self.assertEqual(run.call_args.kwargs["input"], b"I eat rice")


class OrganizeTests(DataFolder):
    def make(self, *names):
        for name in names:
            (self.home / "Downloads" / name).write_text("x")

    def test_organize_and_undo(self):
        self.make("photo.JPG", "cv.pdf", "song.mp3", "setup.exe", "odd.xyz", "half.crdownload")
        with mock.patch("builtins.input", return_value="yes"):
            result = files.organize_folder("Downloads")
        self.assertIn("Moved 5 of 5", result)
        downloads = self.home / "Downloads"
        self.assertTrue((downloads / "Images" / "photo.JPG").exists())
        self.assertTrue((downloads / "Others" / "odd.xyz").exists())
        self.assertTrue((downloads / "half.crdownload").exists())  # still downloading
        self.assertIn("Moved 5 files back", files.undo_organize())
        self.assertTrue((downloads / "cv.pdf").exists())
        self.assertFalse((downloads / "Documents").exists())

    def test_needs_yes_and_only_known_folders(self):
        self.make("photo.png")
        with mock.patch("builtins.input", return_value="no"):
            self.assertEqual(files.organize_folder(), "User did not allow it")
        self.assertTrue((self.home / "Downloads" / "photo.png").exists())
        self.assertIn("Only", files.organize_folder("C:\\Windows"))

    def test_same_name_is_not_overwritten(self):
        (self.home / "Downloads" / "Images").mkdir()
        (self.home / "Downloads" / "Images" / "a.png").write_text("old")
        self.make("a.png")
        with mock.patch("builtins.input", return_value="yes"):
            files.organize_folder()
        self.assertEqual((self.home / "Downloads" / "Images" / "a.png").read_text(), "old")
        self.assertTrue((self.home / "Downloads" / "Images" / "a (1).png").exists())


class InfoTests(unittest.TestCase):
    def test_weather(self):
        replies = [{"results": [{"name": "Dhaka", "country": "Bangladesh", "latitude": 23.7, "longitude": 90.4}]},
                   {"current": {"temperature_2m": 24, "apparent_temperature": 25, "relative_humidity_2m": 70,
                                "weather_code": 2, "wind_speed_10m": 8},
                    "daily": {"time": ["2026-11-28"], "temperature_2m_min": [18], "temperature_2m_max": [27],
                              "precipitation_probability_max": [10], "weather_code": [0]}}]
        with mock.patch.object(info, "get_json", side_effect=replies) as get:
            result = info.weather()
        self.assertEqual(get.call_args_list[0].kwargs["name"], config.env("CITY", "Dhaka"))
        self.assertIn("24°C", result)
        self.assertIn("partly cloudy", result)

    def test_news(self):
        feed = b"""<rss><channel><item><title>Headline one - Prothom Alo</title>
        <pubDate>Sat, 28 Nov 2026 01:00:00 GMT</pubDate></item><item><title>Two</title></item></channel></rss>"""
        with mock.patch.object(info, "fetch", return_value=feed) as fetch:
            self.assertIn("Headline one", info.news("cricket"))
        self.assertIn("q=cricket", fetch.call_args.args[0])
        self.assertIn("hl=bn", fetch.call_args.args[0])

    def test_wikipedia_falls_back_to_english(self):
        replies = [{"query": {"search": []}}, {"query": {"search": [{"title": "Photosynthesis"}]}}]
        summary = json.dumps({"title": "Photosynthesis", "extract": "Plants make food."}).encode()
        with mock.patch.object(info, "get_json", side_effect=replies), \
                mock.patch.object(info, "fetch", return_value=summary):
            result = info.wikipedia("photosynthesis")
        self.assertIn("Plants make food.", result)
        self.assertIn("en.wikipedia.org", result)


class GoogleTests(DataFolder):
    def setUp(self):
        super().setUp()
        for name in ("CREDENTIALS", "TOKEN"):
            patcher = mock.patch.object(google, name, self.data / f"{name}.json")
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_not_set_up(self):
        with mock.patch.object(google, "credentials", return_value=None):
            self.assertIn("not set up", google.unread_emails())
            self.assertIn("not set up", google.calendar_events())
        self.assertFalse(google.ready())

    def test_reads_mail_and_events(self):
        gmail = mock.MagicMock()
        users = gmail.users.return_value.messages.return_value
        users.list.return_value.execute.return_value = {"messages": [{"id": "1"}]}
        users.get.return_value.execute.return_value = {
            "snippet": "Exam on Monday",
            "payload": {"headers": [{"name": "From", "value": "Teacher"}, {"name": "Subject", "value": "Exam"}]}}
        cal = mock.MagicMock()
        cal.events.return_value.list.return_value.execute.return_value = {
            "items": [{"start": {"dateTime": "2026-11-28T10:00:00+06:00"}, "summary": "Class"}]}
        with mock.patch.object(google, "service", side_effect=lambda n, v: gmail if n == "gmail" else cal):
            self.assertIn("Subject: Exam", google.unread_emails())
            self.assertIn("2026-11-28 10:00: Class", google.calendar_events())
        self.assertEqual(users.list.call_args.kwargs["q"], "is:unread in:inbox")

    def test_only_read_access(self):
        self.assertTrue(all(s.endswith(".readonly") for s in google.SCOPES))


class StudyTests(DataFolder):
    def test_flashcards_spaced_review(self):
        cards = [{"front": "H2O কী?", "back": "পানি"}, {"front": "2+2", "back": "4"}, {"front": "", "back": "x"}]
        self.assertIn("Added 2", study.add_flashcards("Science", json.dumps(cards)))
        self.assertIn("H2O কী?", study.next_flashcards("science"))
        self.assertIn("2 due", study.list_decks())
        study.grade_flashcard(1, True)
        study.grade_flashcard(2, False)
        due = [c["id"] for c in study.due_cards()]
        self.assertEqual(due, [2])
        tomorrow = dt.date.today() + dt.timedelta(days=2)
        with mock.patch.object(study, "today", return_value=tomorrow):
            self.assertEqual(len(study.due_cards()), 2)

    def test_mood_diary(self):
        self.assertIn("1 to 5", study.log_mood(9))
        study.log_mood(2, "exam er chinta")
        study.log_mood(4)
        summary = study.mood_summary(7)
        self.assertIn("2 entries, average 3.0", summary)
        self.assertIn("exam er chinta", summary)


class BriefingTests(DataFolder):
    def test_briefing_survives_failures(self):
        with mock.patch.object(info, "weather", side_effect=OSError("offline")), \
                mock.patch.object(info, "news", return_value="- headline"), \
                mock.patch.object(google, "ready", return_value=False):
            result = daily.daily_briefing()
        self.assertIn("not available", result)
        self.assertIn("- headline", result)
        self.assertNotIn("Unread email", result)


class ToolListTests(unittest.TestCase):
    def test_every_tool_has_a_valid_schema(self):
        self.assertEqual({s["function"]["name"] for s in tools.SCHEMAS}, set(tools.FUNCTIONS))
        self.assertGreaterEqual(len(tools.FUNCTIONS), 34)
        json.dumps(tools.SCHEMAS)

    def test_pictures_still_only_get_math(self):
        self.assertEqual(tools.SAFE_WITH_IMAGE, {"calculate", "math_solve"})


if __name__ == "__main__":
    unittest.main()
