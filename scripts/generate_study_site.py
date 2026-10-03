#!/usr/bin/env python3
"""Publish a phone-friendly study library on the existing local audio server."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import generate_feed as feed


ASSET_DIR = Path(__file__).resolve().parent / "study_web"


def read_study(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("vocabulary"), list):
            raise ValueError("invalid study guide")
        if not isinstance(value.get("summary_ko"), str):
            raise ValueError("missing summary")
        words = []
        for item in value["vocabulary"]:
            if not isinstance(item, dict) or not isinstance(item.get("word"), str):
                continue
            words.append({key: item.get(key, "") if isinstance(item.get(key, ""), str) else ""
                          for key in ("word", "reading", "part_of_speech", "meaning_ko",
                                      "source_sentence_ja", "sentence_ko", "timestamp")})
        return {
            "episode_title": value.get("episode_title", "") if isinstance(value.get("episode_title"), str) else "",
            "summary_ko": value["summary_ko"],
            "topics": [topic for topic in value.get("topics", []) if isinstance(topic, str)]
                      if isinstance(value.get("topics"), list) else [],
            "vocabulary": words,
        }
    except (ValueError, OSError) as error:
        print(f"Warning: could not read study guide {path.name}: {error}", file=sys.stderr)
        return None


def copy_if_changed(source: Path, destination: Path) -> None:
    if destination.is_file():
        source_stat, destination_stat = source.stat(), destination.stat()
        if (source_stat.st_size, source_stat.st_mtime_ns) == (destination_stat.st_size, destination_stat.st_mtime_ns):
            return
    feed.link_or_copy(source, destination)


def publish(workspace: Path, output_dir: Path, analysis_dir: Path, max_episodes: int = 180) -> dict:
    # Never turn a temporarily unavailable disk into an empty published library.
    if not workspace.is_dir():
        raise FileNotFoundError(f"Recording workspace unavailable: {workspace}")
    if max_episodes < 1:
        raise ValueError("STUDY_MAX_EPISODES must be positive")
    candidates = []
    for program in feed.PROGRAMS:
        directory = workspace / program["source_dir"]
        if not directory.is_dir():
            raise FileNotFoundError(f"Recording folder unavailable: {directory}")
        for recording in directory.glob("*.m4a"):
            if recording.name.startswith(".") or not recording.is_file() or recording.stat().st_size == 0:
                continue
            recorded_at = feed.parse_recording_datetime(recording.name)
            if recorded_at is not None:
                candidates.append((recorded_at, recording, program))
    candidates.sort(key=lambda entry: (entry[0], entry[1].name), reverse=True)
    # Duplicate timestamps must not make two rows point at different recordings.
    seen = set()
    episodes = []
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    for recorded_at, recording, program in candidates:
        episode_id = Path(feed.export_filename(program["slug"], recorded_at)).stem
        if episode_id in seen:
            continue
        seen.add(episode_id)
        exported_name = f"{episode_id}.m4a"
        copy_if_changed(recording, audio_dir / exported_name)
        study = read_study(analysis_dir / f"{recording.stem}.study.json")
        episodes.append({
            "id": episode_id,
            "date": recorded_at.strftime("%Y-%m-%d"),
            "time": recorded_at.strftime("%H:%M"),
            "course": program["source_dir"],
            "audio_url": f"audio/{quote(exported_name)}",
            "study": study,
        })
        if len(episodes) >= max_episodes:
            break
    if not episodes:
        raise ValueError("No completed recordings; keeping the previous study library")
    for asset_name in ("index.html", "styles.css", "app.js", "icon.svg"):
        copy_if_changed(ASSET_DIR / asset_name, output_dir / asset_name)
    data = {"updated_at": datetime.now().astimezone().isoformat(), "episodes": episodes}
    # Publish the manifest last. An interrupted copy cannot advertise missing audio.
    with tempfile.TemporaryDirectory(prefix=".study-", dir=output_dir) as staging:
        temporary = Path(staging) / "data.json"
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, output_dir / "data.json")
    return data


def main() -> None:
    settings = feed.load_settings()
    workspace = Path(os.environ.get("STUDY_WORKSPACE", str(feed.WORKSPACE_DIR))).expanduser().resolve()
    output_dir = Path(os.environ.get("STUDY_SITE_DIR", str(Path(settings["PODCAST_SITE_ROOT"]).expanduser() / settings["PODCAST_TOKEN"] / "study"))).expanduser()
    analysis_dir = Path(os.environ.get("STUDY_ANALYSIS_DIR", str(workspace / "analysis_output"))).expanduser()
    data = publish(workspace, output_dir, analysis_dir, int(os.environ.get("STUDY_MAX_EPISODES", "180")))
    ready = sum(episode["study"] is not None for episode in data["episodes"])
    print(f"Study library updated: {len(data['episodes'])} recordings, {ready} study guides")
    print(f"{settings['PODCAST_BASE_URL']}/{settings['PODCAST_TOKEN']}/study/index.html")


if __name__ == "__main__":
    main()
