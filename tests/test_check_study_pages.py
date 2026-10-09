from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_study_pages as checker
import deploy_study_pages as deployment
import study_alert

DAY = "20261009"
EPISODE = "intermediate-japanese-20261009-0500"
CONFIG = {"enabled": True, "repository": "owner/site", "max_episodes": 30}


class DeployRetryTests(unittest.TestCase):
    def test_transient_failures_are_retried(self):
        failure = subprocess.CalledProcessError(1, ["gh"], stderr="502 Bad Gateway")
        with patch.object(deployment, "deploy", side_effect=[failure, RuntimeError("no run"), None]) as deploy, \
                patch.object(deployment.time, "sleep") as sleep:
            deployment.deploy_with_retry(Path("w"), Path("a"), CONFIG)
        self.assertEqual(deploy.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], list(deployment.RETRY_DELAYS))

    def test_gives_up_after_last_attempt(self):
        failure = subprocess.CalledProcessError(1, ["gh"], stderr="502 Bad Gateway")
        with patch.object(deployment, "deploy", side_effect=failure) as deploy, \
                patch.object(deployment.time, "sleep"), \
                self.assertRaisesRegex(SystemExit, "after 3 attempts: 502 Bad Gateway"):
            deployment.deploy_with_retry(Path("w"), Path("a"), CONFIG)
        self.assertEqual(deploy.call_count, 3)

    def test_disabled_config_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            self.assertIsNone(deployment.load_config(workspace))
            (workspace / "study_pages.json").write_text('{"enabled": false, "repository": "o/s"}')
            self.assertIsNone(deployment.load_config(workspace))


class MorningCheckTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.workspace = Path(directory.name)
        self.analysis = self.workspace / "analysis_output"
        self.analysis.mkdir()
        (self.workspace / "초급일본어").mkdir()
        (self.workspace / "중급일본어").mkdir()
        (self.workspace / "study_pages.json").write_text('{"enabled": true, "repository": "owner/site"}')
        patcher = patch.object(checker, "pipeline_running", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def record(self, notes=True):
        recording = self.workspace / "중급일본어" / f"{DAY}-0500_EBS_중급일본어.m4a"
        recording.write_bytes(b"audio")
        if notes:
            (self.analysis / f"{recording.stem}.study.json").write_text("{}")

    def run_check(self, live_states, deploy_error=None):
        with patch.object(checker, "live_episodes", side_effect=live_states) as live, \
                patch.object(deployment, "deploy_with_retry", side_effect=deploy_error) as deploy:
            problems = checker.check(self.workspace, self.analysis, DAY)
        return problems, live, deploy

    def test_published_episode_needs_nothing(self):
        self.record()
        problems, _, deploy = self.run_check([{EPISODE: {"study": {"vocabulary": []}}}])
        self.assertEqual(problems, [])
        deploy.assert_not_called()

    def test_site_behind_is_redeployed(self):
        self.record()
        problems, _, deploy = self.run_check([{}, {EPISODE: {"study": {"vocabulary": []}}}])
        self.assertEqual(problems, [])
        deploy.assert_called_once()

    def test_missing_study_on_site_is_redeployed(self):
        self.record()
        problems, _, deploy = self.run_check([{EPISODE: {"study": None}}, {EPISODE: {"study": {"x": 1}}}])
        self.assertEqual(problems, [])
        deploy.assert_called_once()

    def test_failed_redeploy_is_reported(self):
        self.record()
        problems, _, _ = self.run_check([{}], deploy_error=SystemExit("GitHub Pages update failed"))
        self.assertEqual(problems, ["GitHub Pages update failed"])

    def test_still_missing_after_redeploy_is_reported(self):
        self.record()
        problems, _, _ = self.run_check([{}, {}])
        self.assertEqual(len(problems), 1)
        self.assertIn("Pages에 오늘 회차가 없습니다", problems[0])

    def test_missing_notes_are_reported_but_recording_still_published(self):
        self.record(notes=False)
        problems, _, deploy = self.run_check([{EPISODE: {"study": None}}])
        self.assertEqual(len(problems), 1)
        self.assertIn("학습노트가 만들어지지 않았습니다", problems[0])
        deploy.assert_not_called()

    def test_missing_recording_is_reported(self):
        problems, live, _ = self.run_check([])
        self.assertEqual(problems, ["오늘 녹음 파일이 없습니다."])
        live.assert_not_called()

    def test_unmounted_disk_is_reported(self):
        problems = checker.check(self.workspace / "missing", self.analysis, DAY)
        self.assertIn("외장 디스크", problems[0])

    def test_unfinished_pipeline_is_reported(self):
        with patch.object(checker, "wait_for_pipeline", return_value=False):
            problems = checker.check(self.workspace, self.analysis, DAY)
        self.assertIn("끝나지 않았습니다", problems[0])

    def test_problems_send_one_alert_and_success_sends_none(self):
        with patch.object(checker, "check", return_value=["오늘 녹음 파일이 없습니다."]), \
                patch.object(checker.study_alert, "send_alert") as alert, \
                patch.object(sys, "argv", ["check", "--date", DAY]), self.assertRaises(SystemExit):
            checker.main()
        alert.assert_called_once()
        self.assertEqual(alert.call_args.args[0], "EBS 일본어 자동 갱신 문제 (10/09)")
        self.assertIn("오늘 녹음 파일이 없습니다.", alert.call_args.args[1])
        with patch.object(checker, "check", return_value=[]), \
                patch.object(checker.study_alert, "send_alert") as alert, \
                patch.object(sys, "argv", ["check", "--date", DAY]):
            checker.main()
        alert.assert_not_called()


class AlertTests(unittest.TestCase):
    def test_alert_writes_message_and_launches_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper = root / "EBSStudyAlert.app"
            helper.mkdir()
            with patch.object(study_alert, "RUNTIME_DIR", root / "runtime"), \
                    patch.object(study_alert, "HELPER_APP", helper), \
                    patch.object(study_alert.subprocess, "run",
                                 return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
                self.assertTrue(study_alert.send_alert("제목", "첫 줄\n둘째 줄"))
            self.assertEqual((root / "runtime/alert_title.txt").read_text(encoding="utf-8"), "제목\n")
            self.assertEqual((root / "runtime/alert_body.txt").read_text(encoding="utf-8"), "첫 줄\n둘째 줄\n")
            self.assertEqual(run.call_args.args[0], ["/usr/bin/open", "-gj", "-n", str(helper)])

    def test_missing_helper_does_not_raise(self):
        with patch.object(study_alert, "HELPER_APP", Path("/nonexistent/EBSStudyAlert.app")):
            self.assertFalse(study_alert.send_alert("제목", "내용"))


if __name__ == "__main__":
    unittest.main()
