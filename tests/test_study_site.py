import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import generate_study_site as site
import analyze_japanese_episode as analysis


class StudySiteTests(unittest.TestCase):
    def make_workspace(self, root):
        workspace = root / "source"
        for program in site.feed.PROGRAMS:
            (workspace / program["source_dir"]).mkdir(parents=True)
        return workspace

    def test_matches_study_to_recording_and_excludes_incomplete_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self.make_workspace(root)
            recordings = workspace / "중급일본어"
            name = "20261003-0500_EBS_중급일본어"
            (recordings / f"{name}.m4a").write_bytes(b"complete audio")
            (recordings / f".{name}.recording.m4a").write_bytes(b"raw")
            (recordings / "20261002-0500_EBS.m4a").write_bytes(b"")
            (recordings / "20260230-0500_EBS.m4a").write_bytes(b"invalid date")
            (recordings / "20261001-0500_EBS.m4a").mkdir()
            notes = workspace / "analysis_output"
            notes.mkdir()
            (notes / f"{name}.study.json").write_text(json.dumps({
                "episode_title": "猫と犬", "summary_ko": "오늘의 요약", "topics": ["ペット"],
                "vocabulary": [{"word": "飼い主", "timestamp": "00:04:37"}],
            }, ensure_ascii=False), encoding="utf-8")
            output = root / "site"
            data = site.publish(workspace, output, notes)
            self.assertEqual(len(data["episodes"]), 1)
            episode = data["episodes"][0]
            self.assertEqual(episode["study"]["summary_ko"], "오늘의 요약")
            self.assertEqual((output / episode["audio_url"]).read_bytes(), b"complete audio")
            self.assertTrue((output / "index.html").is_file())
            self.assertEqual(json.loads((output / "data.json").read_text()), data)
            with patch.object(site.feed, "link_or_copy", wraps=site.feed.link_or_copy) as copy:
                site.publish(workspace, output, notes)
            self.assertEqual(copy.call_count, 0, "unchanged audio and assets must not be recopied")

    def test_missing_workspace_preserves_existing_library(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "site"
            output.mkdir()
            manifest = output / "data.json"
            manifest.write_text("previous library")
            with self.assertRaises(FileNotFoundError):
                site.publish(root / "missing", output, root / "notes")
            self.assertEqual(manifest.read_text(), "previous library")

    def test_failed_audio_copy_does_not_publish_new_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self.make_workspace(root)
            (workspace / "초급일본어" / "20261001-0500_EBS.m4a").write_bytes(b"new audio")
            output = root / "site"
            output.mkdir()
            (output / "data.json").write_text("old manifest")
            with patch.object(site.feed, "link_or_copy", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    site.publish(workspace, output, root / "notes")
            self.assertEqual((output / "data.json").read_text(), "old manifest")

    def test_missing_or_invalid_study_keeps_audio_available(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self.make_workspace(root)
            name = "20261001-0500_EBS"
            (workspace / "초급일본어" / f"{name}.m4a").write_bytes(b"audio")
            notes = root / "notes"
            notes.mkdir()
            (notes / f"{name}.study.json").write_text("invalid JSON")
            data = site.publish(workspace, root / "site", notes)
            self.assertIsNone(data["episodes"][0]["study"])
            self.assertTrue((root / "site" / data["episodes"][0]["audio_url"]).is_file())


class TranscriptValidationTests(unittest.TestCase):
    def test_word_must_be_supported_by_its_quoted_sentence(self):
        guide = {"vocabulary": [
            {"word": "あえて", "source_sentence_ja": "ノートに書きます。", "timestamp": "00:00:01"},
            {"word": "記憶定着", "source_sentence_ja": "ノートに書きます。", "timestamp": "00:00:01"},
        ]}
        analysis.ground_vocabulary(guide, "[00:00:01] ノートに書きます。\n[00:00:42] あえて紙を使います。")
        self.assertEqual(len(guide["vocabulary"]), 1)
        self.assertEqual(guide["vocabulary"][0]["source_sentence_ja"], "あえて紙を使います。")
        self.assertEqual(guide["vocabulary"][0]["timestamp"], "00:00:42")

    def test_no_supported_words_cannot_replace_a_guide(self):
        with self.assertRaises(RuntimeError):
            analysis.ground_vocabulary({"vocabulary": [{"word": "宇宙", "source_sentence_ja": "ノートに書きます。"}]}, "[00:00:01] ノートに書きます。")

    def test_joined_adjacent_segments_are_valid_and_time_is_corrected(self):
        guide = {"vocabulary": [{"source_sentence_ja": "日本語を勉強します。", "timestamp": "00:19:59"}]}
        analysis.validate_source_sentences(guide, "[00:00:01] 日本語を\n[00:00:02] 勉強します。")
        self.assertEqual(guide["vocabulary"][0]["timestamp"], "00:00:01")

    def test_empty_or_invented_source_is_rejected(self):
        for sentence in ("", "！？", "存在しない文です。"):
            with self.subTest(sentence=sentence), self.assertRaises(RuntimeError):
                analysis.validate_source_sentences({"vocabulary": [{"source_sentence_ja": sentence}]}, "[00:00:01] 日本語を勉強します。")


class RecordingPipelineTests(unittest.TestCase):
    def setup_recording(self, root, ffmpeg_script):
        ffmpeg = root / "ffmpeg"
        ffmpeg.write_text("#!/bin/sh\nlast=''\nfor arg do last=\"$arg\"; done\n" + ffmpeg_script)
        ffmpeg.chmod(0o755)
        return dict(os.environ, RADIO_WORKSPACE=str(root), FFMPEG_BIN=str(ffmpeg), DAY_OVERRIDE="1",
                    ANALYZE_RECORDING="0", BOUND_ICLOUD_ENABLED="0", APPLE_NOTES_ENABLED="0",
                    TMPDIR=str(root), PODCAST_ARTWORK_SOURCE=str(root / "absent.png"), START_DELAY_SECONDS="0",
                    PODCAST_MIRROR_BASE_DIR="", PODCAST_FEED_WORKSPACE="")

    def test_tagging_failure_retains_raw_and_never_publishes_partial_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self.setup_recording(root, 'case "$last" in\n*.recording.m4a) printf raw > "$last" ;;\n*) printf partial > "$last"; exit 1 ;;\nesac\n')
            result = subprocess.run(["/bin/sh", str(SCRIPTS / "record_ebs_japanese.sh")], env=environment, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(list((root / "초급일본어").glob("*.m4a")), [])
            raw = list(root.glob("ebs-radio.*/raw.recording.m4a"))
            self.assertEqual(len(raw), 1)
            self.assertEqual(raw[0].read_bytes(), b"raw")

    def test_failed_feed_does_not_stop_study_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self.setup_recording(root, 'printf complete > "$last"\n')
            fake_python = root / "python"
            fake_python.write_text('#!/bin/sh\ncase "$1" in\n*generate_feed.py) exit 1 ;;\n*analyze_japanese_episode.py) touch "$RADIO_WORKSPACE/analyzed" ;;\nesac\n')
            fake_python.chmod(0o755)
            environment.update(PYTHON_BIN=str(fake_python), ANALYZE_RECORDING="1")
            result = subprocess.run(["/bin/sh", str(SCRIPTS / "record_ebs_japanese.sh")], env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / "analyzed").exists())
            self.assertEqual(len(list((root / "초급일본어").glob("*.m4a"))), 1)
            self.assertEqual(list(root.glob("ebs-radio.*")), [])


if __name__ == "__main__":
    unittest.main()
