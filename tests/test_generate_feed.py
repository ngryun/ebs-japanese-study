import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location(
    "generate_feed", Path(__file__).resolve().parents[1] / "scripts/generate_feed.py"
)
feed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(feed)


class FeedTests(unittest.TestCase):
    def test_invalid_recording_date_is_skipped(self):
        self.assertIsNone(feed.parse_recording_datetime("20260230-0500_EBS.m4a"))
        self.assertIsNotNone(feed.parse_recording_datetime("20260228-0500_EBS.m4a"))

    def test_collect_excludes_temporary_files_and_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recordings = root / "초급일본어"
            recordings.mkdir()
            for name in ("20260228-0500_EBS.m4a", ".20260301-0500.recording.m4a",
                         "20260230-0500_EBS.m4a"):
                (recordings / name).write_bytes(b"audio")
            (recordings / "20260302-0500_EBS.m4a").mkdir()
            with patch.object(feed, "WORKSPACE_DIR", root), patch.object(feed, "INCLUDED_PROGRAM_SLUGS", set()):
                episodes = feed.collect_episodes({"PODCAST_MAX_EPISODES": "180"})
            self.assertEqual(len(episodes), 1)
            self.assertEqual(episodes[0]["recording_path"].name, "20260228-0500_EBS.m4a")

    def test_failed_copy_preserves_published_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root / "source", root / "destination"
            source.write_bytes(b"new")
            destination.write_bytes(b"old")
            def fail_copy(src, dst):
                Path(dst).write_bytes(b"partial")
                raise OSError("disk full")
            with patch.object(feed.os, "link", side_effect=OSError("different devices")), patch.object(feed.shutil, "copy2", side_effect=fail_copy):
                with self.assertRaises(OSError):
                    feed.link_or_copy(source, destination)
            self.assertEqual(destination.read_bytes(), b"old")
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["destination", "source"])

    def test_successful_copy_replaces_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root / "source", root / "destination"
            source.write_bytes(b"new")
            destination.write_bytes(b"old")
            with patch.object(feed.os, "link", side_effect=OSError("different devices")):
                feed.link_or_copy(source, destination)
            self.assertEqual(destination.read_bytes(), b"new")

    def test_failed_xml_write_preserves_feed(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "feed.xml"
            destination.write_bytes(b"old feed")
            tree = ET.ElementTree(ET.Element("rss"))
            with patch.object(tree, "write", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    feed.write_feed_atomic(tree, destination)
            self.assertEqual(destination.read_bytes(), b"old feed")
            feed.write_feed_atomic(tree, destination)
            self.assertEqual(ET.parse(destination).getroot().tag, "rss")


if __name__ == "__main__":
    unittest.main()
