from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_japanese_episode as analysis
import deploy_study_pages as deployment


def launchctl(manager, logged_in=True):
    def execute(arguments, **kwargs):
        if arguments[1] == "managername":
            return subprocess.CompletedProcess(arguments, 0, stdout=f"{manager}\n", stderr="")
        return subprocess.CompletedProcess(arguments, 0 if logged_in else 113, stdout="", stderr="")
    return execute


class WhisperSessionTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("EBS_WHISPER_SESSION", None)

    def test_logged_in_terminal_runs_directly(self):
        with patch.object(analysis.subprocess, "run", side_effect=launchctl("Aqua")):
            self.assertFalse(analysis.needs_login_session())

    def test_cron_moves_into_login_session(self):
        with patch.object(analysis.subprocess, "run", side_effect=launchctl("System")):
            self.assertTrue(analysis.needs_login_session())

    def test_cron_without_login_session_runs_directly(self):
        with patch.object(analysis.subprocess, "run", side_effect=launchctl("System", logged_in=False)):
            self.assertFalse(analysis.needs_login_session())

    def test_environment_overrides_detection(self):
        with patch.object(analysis.subprocess, "run", side_effect=AssertionError("not called")):
            os.environ["EBS_WHISPER_SESSION"] = "gui"
            self.assertTrue(analysis.needs_login_session())
            os.environ["EBS_WHISPER_SESSION"] = "direct"
            self.assertFalse(analysis.needs_login_session())

    def test_login_session_runs_whisper_as_standard_job(self):
        with patch.object(deployment, "run_in_gui_session", return_value="") as session:
            analysis.run(["/fake/whisper-cli", "-f", "a file.wav"], "Transcribing", login_session=True)
        session.assert_called_once_with("/fake/whisper-cli", ["-f", "a file.wav"], timeout=3600,
                                        name="whisper", process_type="Standard")

    def test_login_session_failure_reports_whisper_error(self):
        failure = subprocess.CalledProcessError(1, ["/fake/whisper-cli"], output="", stderr="model missing\n")
        with patch.object(deployment, "run_in_gui_session", side_effect=failure), \
                self.assertRaisesRegex(RuntimeError, "Transcribing failed:\nmodel missing"):
            analysis.run(["/fake/whisper-cli"], "Transcribing", login_session=True)


class SplitCharacterTests(unittest.TestCase):
    # Whisper cut "한" (ED 95 9C) after two bytes at a segment boundary.
    BROKEN = "1\n00:00:01,000 --> 00:00:02,000\n日本語".encode("utf-8") + b"\xed\x95\n"

    def test_command_with_broken_output_reports_failure_not_decode_error(self):
        with self.assertRaisesRegex(RuntimeError, "Transcribing failed"):
            analysis.run(["/bin/sh", "-c", "printf '\\355\\225\\n'; exit 1"], "Transcribing")

    def test_repair_drops_partial_characters_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a.transcript.srt"
            path.write_bytes(self.BROKEN)
            analysis.repair_utf8(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "1\n00:00:01,000 --> 00:00:02,000\n日本語\n")

    def test_old_transcript_with_partial_characters_is_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a.transcript.srt"
            path.write_bytes(self.BROKEN)
            self.assertIn("日本語", analysis.parse_srt(path))


if __name__ == "__main__":
    unittest.main()
