import json
from pathlib import Path
import sys
import os
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


if __name__ == "__main__":
    unittest.main()
