from datetime import datetime
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_japanese_episode as analysis


class ReplacedOllamaTests(unittest.TestCase):
    def run_check(self, started, binary_modified):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "ollama"
            binary.write_text("")
            os.utime(binary, (binary_modified.timestamp(), binary_modified.timestamp()))

            def execute(arguments, **kwargs):
                calls.append(arguments)
                if arguments[1] == "print":
                    output = f"\tstate = running\n\tprogram = {binary}\n\tpid = 57804\n"
                elif arguments[0] == "/bin/ps":
                    output = started.strftime("%a %b %e %H:%M:%S %Y") + "\n"
                else:
                    output = ""
                return subprocess.CompletedProcess(arguments, 0, stdout=output, stderr="")

            with patch.object(analysis.subprocess, "run", side_effect=execute):
                analysis.restart_replaced_ollama("com.ebs.radio.ollama")
        return [call for call in calls if call[1:2] == ["kickstart"]]

    def test_server_older_than_updated_binary_is_restarted(self):
        restarts = self.run_check(datetime(2026, 10, 3, 20, 49, 56), datetime(2026, 10, 9, 21, 34, 1))
        self.assertEqual(restarts, [["/bin/launchctl", "kickstart", "-k",
                                     f"gui/{os.getuid()}/com.ebs.radio.ollama"]])

    def test_server_started_after_update_is_left_running(self):
        restarts = self.run_check(datetime(2026, 10, 10, 8, 12, 0), datetime(2026, 10, 9, 21, 34, 1))
        self.assertEqual(restarts, [])

    def test_stopped_server_is_left_to_normal_startup(self):
        with patch.object(analysis.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, stdout="\tstate = waiting\n", stderr="")) as run:
            analysis.restart_replaced_ollama("com.ebs.radio.ollama")
        self.assertEqual(run.call_count, 1)

    def test_error_body_explains_http_500(self):
        body = io.BytesIO(b'{"error":"open /Volumes/Transcend/models: operation not permitted"}')
        error = urllib.error.HTTPError("http://127.0.0.1:11435/api/chat", 500, "Internal Server Error", {}, body)
        self.assertEqual(analysis.ollama_error(error),
                         "HTTP Error 500: Internal Server Error (open /Volumes/Transcend/models: operation not permitted)")
        self.assertEqual(analysis.ollama_error(urllib.error.URLError("refused")), "<urlopen error refused>")


if __name__ == "__main__":
    unittest.main()
