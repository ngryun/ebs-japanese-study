#!/usr/bin/env python3
"""Generate a private podcast feed from recorded EBS Japanese radio files."""

from __future__ import annotations

import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from typing import Dict, List

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_WORKSPACE_DIR = SCRIPT_DIR.parent
WORKSPACE_DIR = Path(os.environ.get("RADIO_WORKSPACE", str(DEFAULT_WORKSPACE_DIR))).expanduser().resolve()
ENV_PATH = Path(
    os.environ.get("PODCAST_ENV_PATH", str(WORKSPACE_DIR / "podcast.env"))
).expanduser()
ARTWORK_SOURCE = Path(
    os.environ.get("PODCAST_ARTWORK_SOURCE", str(WORKSPACE_DIR / "artwork.png"))
).expanduser()
ROOT_FEED_PATH = Path(
    os.environ.get("PODCAST_ROOT_FEED_PATH", str(WORKSPACE_DIR / "feed.xml"))
).expanduser()
WRITE_ROOT_FEED_COPY = os.environ.get("PODCAST_WRITE_ROOT_COPY", "1").lower() not in {
    "0",
    "false",
    "no",
}
INCLUDED_PROGRAM_SLUGS = {
    value.strip().lower()
    for value in os.environ.get("PODCAST_INCLUDE_SLUGS", "").split(",")
    if value.strip()
}
DEFAULT_TIMEZONE = "Asia/Seoul"
DEFAULT_SITE_ROOT = Path.home() / "Library/Application Support/EBSPrivatePodcast/site"

PROGRAMS = [
    {
        "source_dir": "초급일본어",
        "title": "EBS 초급일본어",
        "slug": "beginner-japanese",
    },
    {
        "source_dir": "중급일본어",
        "title": "EBS 중급일본어",
        "slug": "intermediate-japanese",
    },
]


def default_base_url() -> str:
    hostname = socket.gethostname()
    if not hostname.endswith(".local"):
        hostname = f"{hostname}.local"
    return f"http://{hostname}:8081"


def parse_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def write_env_file(path: Path, settings: Dict[str, str]) -> None:
    lines = [
        "# Set PODCAST_BASE_URL to your public HTTPS address when you expose this server.",
        f"PODCAST_BASE_URL={settings['PODCAST_BASE_URL']}",
        f"PODCAST_TOKEN={settings['PODCAST_TOKEN']}",
        f"PODCAST_TITLE={settings['PODCAST_TITLE']}",
        f"PODCAST_DESCRIPTION={settings['PODCAST_DESCRIPTION']}",
        f"PODCAST_AUTHOR={settings['PODCAST_AUTHOR']}",
        f"PODCAST_LANGUAGE={settings['PODCAST_LANGUAGE']}",
        f"PODCAST_MAX_EPISODES={settings['PODCAST_MAX_EPISODES']}",
        f"PODCAST_SITE_ROOT={settings['PODCAST_SITE_ROOT']}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_settings() -> Dict[str, str]:
    settings = {
        "PODCAST_BASE_URL": default_base_url(),
        "PODCAST_TOKEN": secrets.token_hex(16),
        "PODCAST_TITLE": "EBS 일본어 라디오",
        "PODCAST_DESCRIPTION": "EBS 초급/중급 일본어 라디오 녹음",
        "PODCAST_AUTHOR": "EBS",
        "PODCAST_LANGUAGE": "ja",
        "PODCAST_MAX_EPISODES": "180",
        "PODCAST_SITE_ROOT": str(DEFAULT_SITE_ROOT),
    }

    file_settings = parse_env_file(ENV_PATH)
    settings.update(file_settings)

    for key in list(settings.keys()):
        env_value = os.environ.get(key)
        if env_value:
            settings[key] = env_value

    settings["PODCAST_BASE_URL"] = settings["PODCAST_BASE_URL"].rstrip("/")
    if not ENV_PATH.exists():
        write_env_file(ENV_PATH, settings)

    return settings


def parse_recording_datetime(filename: str) -> datetime | None:
    match = re.search(r"(\d{8})-(\d{4})", filename)
    if not match:
        return None

    try:
        value = datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M")
    except ValueError:
        return None
    if ZoneInfo is not None:
        return value.replace(tzinfo=ZoneInfo(DEFAULT_TIMEZONE))
    return value


def probe_duration_seconds(filepath: Path) -> int:
    commands = [
        "ffprobe",
        "/opt/homebrew/bin/ffprobe",
        "/usr/local/bin/ffprobe",
    ]
    for command in commands:
        try:
            result = subprocess.run(
                [
                    command,
                    "-v",
                    "quiet",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(filepath),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

        if result.returncode == 0 and result.stdout.strip():
            return int(float(result.stdout.strip()))

    return 1200


def format_duration(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def export_filename(program_slug: str, recorded_at: datetime) -> str:
    return f"{program_slug}-{recorded_at.strftime('%Y%m%d-%H%M')}.m4a"


def link_or_copy(source: Path, destination: Path) -> None:
    if destination.exists() and os.path.samefile(source, destination):
        return

    # Stage beside the destination so replacement is atomic, even when the
    # source is on the external disk and the site is on the internal disk.
    with tempfile.TemporaryDirectory(prefix=".podcast-", dir=destination.parent) as staging:
        temporary = Path(staging) / destination.name
        try:
            os.link(source, temporary)
        except OSError:
            shutil.copy2(source, temporary)
        os.replace(temporary, destination)


def write_feed_atomic(tree: ET.ElementTree, destination: Path) -> None:
    with tempfile.TemporaryDirectory(prefix=".podcast-", dir=destination.parent) as staging:
        temporary = Path(staging) / destination.name
        tree.write(temporary, encoding="utf-8", xml_declaration=True)
        os.replace(temporary, destination)


def is_program_enabled(program: Dict[str, str]) -> bool:
    if not INCLUDED_PROGRAM_SLUGS:
        return True
    return str(program["slug"]).lower() in INCLUDED_PROGRAM_SLUGS


def collect_episodes(settings: Dict[str, str]) -> List[Dict[str, object]]:
    episodes: List[Dict[str, object]] = []

    for program in PROGRAMS:
        if not is_program_enabled(program):
            continue

        source_dir = WORKSPACE_DIR / program["source_dir"]
        if not source_dir.exists():
            continue

        for recording in sorted(source_dir.glob("*.m4a")):
            if recording.name.startswith(".") or not recording.is_file():
                continue
            recorded_at = parse_recording_datetime(recording.name)
            if recorded_at is None:
                continue

            exported_name = export_filename(program["slug"], recorded_at)
            episodes.append(
                {
                    "title": f"{program['title']} - {recorded_at.strftime('%Y-%m-%d')}",
                    "program_title": program["title"],
                    "recording_path": recording,
                    "recorded_at": recorded_at,
                    "exported_name": exported_name,
                    "guid": exported_name,
                }
            )

    episodes.sort(key=lambda episode: episode["recorded_at"], reverse=True)
    max_episodes = int(settings["PODCAST_MAX_EPISODES"])
    return episodes[:max_episodes]


def build_site_tree(settings: Dict[str, str], episodes: List[Dict[str, object]]) -> Path:
    site_root = Path(settings["PODCAST_SITE_ROOT"]).expanduser()
    token_root = site_root / settings["PODCAST_TOKEN"]
    episodes_dir = token_root / "episodes"
    episodes_dir.mkdir(parents=True, exist_ok=True)

    if ARTWORK_SOURCE.exists():
        link_or_copy(ARTWORK_SOURCE, token_root / "artwork.png")

    expected_files = set()
    for episode in episodes:
        destination = episodes_dir / str(episode["exported_name"])
        link_or_copy(Path(episode["recording_path"]), destination)
        expected_files.add(destination.name)

    for existing in episodes_dir.glob("*.m4a"):
        if existing.name not in expected_files:
            existing.unlink()

    return token_root


def build_feed_xml(settings: Dict[str, str], token_root: Path, episodes: List[Dict[str, object]]) -> ET.ElementTree:
    base_url = settings["PODCAST_BASE_URL"]
    token = settings["PODCAST_TOKEN"]
    channel_url = f"{base_url}/{token}"
    feed_url = f"{channel_url}/feed.xml"
    artwork_url = f"{channel_url}/artwork.png"

    rss = ET.Element(
        "rss",
        {
            "version": "2.0",
            "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
            "xmlns:atom": "http://www.w3.org/2005/Atom",
        },
    )

    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = settings["PODCAST_TITLE"]
    ET.SubElement(channel, "link").text = channel_url
    ET.SubElement(channel, "description").text = settings["PODCAST_DESCRIPTION"]
    ET.SubElement(channel, "language").text = settings["PODCAST_LANGUAGE"]
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(datetime.now().astimezone())
    ET.SubElement(
        channel,
        "atom:link",
        {"href": feed_url, "rel": "self", "type": "application/rss+xml"},
    )
    ET.SubElement(channel, "itunes:author").text = settings["PODCAST_AUTHOR"]
    ET.SubElement(channel, "itunes:summary").text = settings["PODCAST_DESCRIPTION"]
    ET.SubElement(channel, "itunes:explicit").text = "false"
    ET.SubElement(channel, "itunes:block").text = "yes"
    ET.SubElement(channel, "itunes:type").text = "episodic"
    ET.SubElement(channel, "itunes:image", {"href": artwork_url})

    image = ET.SubElement(channel, "image")
    ET.SubElement(image, "url").text = artwork_url
    ET.SubElement(image, "title").text = settings["PODCAST_TITLE"]
    ET.SubElement(image, "link").text = channel_url

    category = ET.SubElement(channel, "itunes:category", {"text": "Education"})
    ET.SubElement(category, "itunes:category", {"text": "Language Learning"})

    for episode in episodes:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = str(episode["title"])
        ET.SubElement(item, "description").text = str(episode["program_title"])
        ET.SubElement(item, "itunes:summary").text = str(episode["program_title"])
        ET.SubElement(item, "itunes:explicit").text = "false"
        ET.SubElement(item, "itunes:episodeType").text = "full"
        ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = str(episode["guid"])

        recording_path = Path(episode["recording_path"])
        file_size = str(recording_path.stat().st_size)
        episode_url = f"{channel_url}/episodes/{episode['exported_name']}"
        ET.SubElement(
            item,
            "enclosure",
            {"url": episode_url, "length": file_size, "type": "audio/mp4"},
        )

        recorded_at = episode["recorded_at"]
        ET.SubElement(item, "pubDate").text = format_datetime(recorded_at)
        ET.SubElement(item, "itunes:duration").text = format_duration(
            probe_duration_seconds(recording_path)
        )

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")

    feed_path = token_root / "feed.xml"
    write_feed_atomic(tree, feed_path)
    return tree


def write_root_feed_copy(tree: ET.ElementTree) -> None:
    root_feed_path = ROOT_FEED_PATH
    write_feed_atomic(tree, root_feed_path)


def main() -> None:
    settings = load_settings()
    episodes = collect_episodes(settings)
    token_root = build_site_tree(settings, episodes)
    tree = build_feed_xml(settings, token_root, episodes)
    if WRITE_ROOT_FEED_COPY:
        write_root_feed_copy(tree)
    print(
        f"Feed generated: {token_root / 'feed.xml'} ({len(episodes)} episodes)"
    )


if __name__ == "__main__":
    main()
