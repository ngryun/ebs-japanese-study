#!/usr/bin/env python3
"""Morning check that today's recording and study notes reached GitHub Pages.

Runs from cron after the 05:00 pipeline. When the site is behind the local
library it redeploys; whatever is still wrong afterwards becomes an iPhone
alert through Apple Reminders. Nothing is sent when everything is in place.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import study_alert

PIPELINE_PATTERN = "record_ebs_japanese.sh|analyze_japanese_episode.py"
PIPELINE_WAIT_SECONDS = 45 * 60
LOG_HINT = "로그: ~/Library/Logs/ebs_japan_radio.record.log, ebs_japan_radio.check.log"


def pipeline_running() -> bool:
    return subprocess.run(["/usr/bin/pgrep", "-f", PIPELINE_PATTERN],
                          capture_output=True).returncode == 0


def wait_for_pipeline(limit: float) -> bool:
    deadline = time.monotonic() + limit
    while pipeline_running():
        if time.monotonic() >= deadline:
            return False
        time.sleep(60)
    return True


def today_recordings(workspace: Path, day: str) -> list[tuple[Path, str]]:
    """Today's finished recordings with the episode id the site uses."""
    import generate_feed as feed

    found = []
    for program in feed.PROGRAMS:
        for recording in sorted((workspace / program["source_dir"]).glob(f"{day}-*.m4a")):
            if recording.name.startswith(".") or recording.stat().st_size == 0:
                continue
            recorded_at = feed.parse_recording_datetime(recording.name)
            if recorded_at is not None:
                episode_id = Path(feed.export_filename(program["slug"], recorded_at)).stem
                found.append((recording, episode_id))
    return found


def live_episodes(repository: str) -> dict[str, dict]:
    owner, name = repository.split("/")
    # The query string bypasses the Pages CDN cache (max-age 600).
    url = f"https://{owner}.github.io/{name}/data.json?checked={int(time.time())}"
    with urllib.request.urlopen(url, timeout=30) as response:
        data = json.load(response)
    return {episode.get("id"): episode for episode in data.get("episodes", [])}


def site_problems(recordings: list[tuple[Path, str]], analysis_dir: Path,
                  live: dict[str, dict]) -> list[str]:
    problems = []
    for recording, episode_id in recordings:
        episode = live.get(episode_id)
        if episode is None:
            problems.append(f"Pages에 오늘 회차가 없습니다: {recording.name}")
        elif (analysis_dir / f"{recording.stem}.study.json").is_file() and not episode.get("study"):
            problems.append(f"Pages에 오늘 학습노트가 없습니다: {recording.name}")
    return problems


def check(workspace: Path, analysis_dir: Path, day: str) -> list[str]:
    if not wait_for_pipeline(PIPELINE_WAIT_SECONDS):
        return [f"05:00 작업이 {PIPELINE_WAIT_SECONDS // 60}분을 더 기다려도 끝나지 않았습니다."]
    if not workspace.is_dir():
        return [f"녹음 폴더를 열 수 없습니다. 외장 디스크 연결을 확인하세요: {workspace}"]
    recordings = today_recordings(workspace, day)
    if not recordings:
        return ["오늘 녹음 파일이 없습니다."]

    problems = [f"학습노트가 만들어지지 않았습니다: {recording.name}"
                for recording, _ in recordings
                if not (analysis_dir / f"{recording.stem}.study.json").is_file()]

    import deploy_study_pages as deployment

    config = deployment.load_config(workspace)
    if config is None:
        return problems
    try:
        behind = site_problems(recordings, analysis_dir, live_episodes(config["repository"]))
    except (OSError, ValueError, urllib.error.URLError) as error:
        behind = [f"Pages 상태를 확인할 수 없습니다: {error}"]
    if behind:
        print("Site is behind; redeploying: " + "; ".join(behind), flush=True)
        try:
            deployment.deploy_with_retry(workspace, analysis_dir, config)
        except SystemExit as error:
            return problems + [str(error)]
        try:
            behind = site_problems(recordings, analysis_dir, live_episodes(config["repository"]))
        except (OSError, ValueError, urllib.error.URLError) as error:
            behind = [f"재배포 후 Pages 상태를 확인할 수 없습니다: {error}"]
    return problems + behind


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path,
                        default=Path(os.environ.get("RADIO_WORKSPACE", str(SCRIPT_DIR.parent))))
    parser.add_argument("--analysis-dir", type=Path)
    parser.add_argument("--date", default=datetime.now().strftime("%Y%m%d"), help="YYYYMMDD")
    args = parser.parse_args()
    analysis_dir = args.analysis_dir or args.workspace / "analysis_output"

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Checking {args.date}", flush=True)
    try:
        problems = check(args.workspace, analysis_dir, args.date)
    except Exception as error:  # an alert is better than a silent crash at 07:30
        problems = [f"점검 스크립트 오류: {type(error).__name__}: {error}"]
    if not problems:
        print("OK: today's recording and study notes are on GitHub Pages", flush=True)
        return
    day = datetime.strptime(args.date, "%Y%m%d")
    study_alert.send_alert(f"EBS 일본어 자동 갱신 문제 ({day:%m/%d})",
                           "\n".join(problems + [LOG_HINT]))
    raise SystemExit(1)


if __name__ == "__main__":
    main()
