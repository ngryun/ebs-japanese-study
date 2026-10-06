import json
from pathlib import Path
import sys
import os
import plistlib
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import export_study_pages as pages
import deploy_study_pages as deployment


class PagesExportTests(unittest.TestCase):
    def make_source(self, root):
        workspace = root / "source"
        for program in pages.study_site.feed.PROGRAMS:
            (workspace / program["source_dir"]).mkdir(parents=True)
        for date in ("20261001", "20261002", "20261003"):
            (workspace / "중급일본어").joinpath(
                f"{date}-0500_EBS.m4a").write_bytes(b"audio")
        (workspace / "podcast.env").write_text("PODCAST_TOKEN=private-secret")
        (workspace / "private.log").write_text("private log")
        return workspace

    def test_only_selected_static_files_exported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self.make_source(root)
            output = root / "repository"
            report = pages.export(workspace, workspace / "analysis_output", output, 2)
            public = output / "public"
            manifest = json.loads((public / "data.json").read_text())
            self.assertEqual([episode["date"] for episode in manifest["episodes"]],
                             ["2026-10-03", "2026-10-02"])
            self.assertEqual(len(list((public / "audio").iterdir())), 2)
            self.assertEqual(report["episodes"], 2)
            self.assertTrue((public / ".nojekyll").is_file())
            self.assertTrue((output / ".github/workflows/pages.yml").is_file())
            self.assertEqual({path.name for path in public.iterdir()},
                             {"audio", "data.json", "index.html", "styles.css", "app.js", "icon.svg", ".nojekyll"})
            with self.assertRaises(FileExistsError):
                pages.export(workspace, workspace / "analysis_output", output)

    def test_oversized_export_leaves_no_partial_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self.make_source(root)
            output = root / "repository"
            with self.assertRaises(ValueError):
                pages.export(workspace, workspace / "analysis_output", output, max_bytes=1)
            self.assertFalse(output.exists())
            self.assertFalse(list(root.glob(".pages-export-*")))

    def test_archive_contains_real_files_even_when_sources_are_hardlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public = root / "public"
            public.mkdir()
            (public / "one").write_bytes(b"complete audio")
            os.link(public / "one", public / "two")
            archive = root / "site.tar.gz"
            deployment.archive_site(public, archive)
            with tarfile.open(archive) as bundle:
                for member in bundle.getmembers():
                    self.assertTrue(member.isfile())
                    self.assertFalse(member.islnk())
                    self.assertEqual(bundle.extractfile(member).read(), b"complete audio")

    def test_failed_deployment_never_removes_previous_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self.make_source(root)
            calls = []
            asset_name = None

            def fake_run(gh, arguments, timeout=1800):
                nonlocal asset_name
                calls.append(arguments)
                if arguments[:2] == ["workflow", "run"]:
                    asset_name = arguments[-1].split("=", 1)[1]
                if arguments[:2] == ["run", "list"]:
                    return json.dumps([{"databaseId": 42, "displayTitle": asset_name}])
                if arguments[:2] == ["run", "watch"]:
                    raise subprocess.CalledProcessError(1, arguments, stderr="deploy failed")
                return ""

            with patch.object(deployment, "run", side_effect=fake_run), self.assertRaises(subprocess.CalledProcessError):
                deployment.deploy(workspace, workspace / "analysis_output",
                                  {"repository": "owner/study", "max_episodes": 2})
            self.assertFalse(any("DELETE" in arguments for arguments in calls))


class GitHubSessionTests(unittest.TestCase):
    def execute_job(self, code=0):
        calls = []
        def execute(arguments, **kwargs):
            calls.append(arguments)
            if arguments[1] == "bootstrap":
                config = plistlib.loads(Path(arguments[3]).read_bytes())
                self.assertEqual(config["ProgramArguments"], ["/fake/gh", "release", "upload", "study-data", "a file $(literal).tar.gz"])
                self.assertNotIn("GH_TOKEN", config["EnvironmentVariables"])
                Path(config["StandardOutPath"]).write_text("command output\n")
                Path(config["StandardErrorPath"]).write_text("command error\n" if code else "")
            elif arguments[1] == "print":
                return subprocess.CompletedProcess(arguments, 0, stdout=f"state = not running\nlast exit code = {code}\n", stderr="")
            return subprocess.CompletedProcess(arguments, 0, stdout="", stderr="")
        return calls, execute

    def test_user_session_preserves_arguments_and_removes_temporary_job(self):
        calls, execute = self.execute_job()
        with patch.object(deployment.subprocess, "run", side_effect=execute):
            output = deployment.run_in_gui_session("/fake/gh", ["release", "upload", "study-data", "a file $(literal).tar.gz"])
        self.assertEqual(output, "command output\n")
        self.assertEqual(calls[-1][1], "bootout")
        self.assertFalse(Path(calls[0][3]).exists())

    def test_failed_user_session_command_is_reported_and_job_removed(self):
        calls, execute = self.execute_job(1)
        with patch.object(deployment.subprocess, "run", side_effect=execute), self.assertRaises(subprocess.CalledProcessError) as raised:
            deployment.run_in_gui_session("/fake/gh", ["release", "upload", "study-data", "a file $(literal).tar.gz"])
        self.assertEqual(raised.exception.stderr, "command error\n")
        self.assertEqual(calls[-1][1], "bootout")

    def test_timed_out_user_session_job_is_stopped(self):
        calls, execute = self.execute_job()
        with patch.object(deployment.subprocess, "run", side_effect=execute), patch.object(deployment.time, "monotonic", side_effect=[0, 1]), self.assertRaises(subprocess.TimeoutExpired):
            deployment.run_in_gui_session("/fake/gh", ["release", "upload", "study-data", "a file $(literal).tar.gz"], timeout=0)
        self.assertEqual(calls[-1][1], "bootout")


if __name__ == "__main__":
    unittest.main()
