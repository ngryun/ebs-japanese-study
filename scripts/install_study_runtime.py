#!/usr/bin/env python3
"""Install the study screen and recording scripts into the existing cron runtime."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import shutil
import tempfile
import os


SCRIPT_DIR = Path(__file__).resolve().parent
FILES = (
    "record_ebs_japanese.sh", "generate_feed.py", "analyze_japanese_episode.py",
    "generate_study_site.py", "podcast_server.py", "start_server.sh",
    "export_study_pages.py", "deploy_study_pages.py", "check_study_pages.py", "study_alert.py",
    "study_web/index.html", "study_web/styles.css", "study_web/app.js", "study_web/icon.svg",
)


def install(runtime: Path, backup: Path) -> None:
    # Keep the runtime's settings, token, public files, and recording schedules.
    # Back up only the code that this operation replaces.
    for filename in FILES:
        source = SCRIPT_DIR / filename
        if not source.is_file():
            raise FileNotFoundError(source)
    runtime.mkdir(parents=True, exist_ok=True)
    for filename in FILES:
        source, destination = SCRIPT_DIR / filename, runtime / filename
        if destination.is_file() and source.read_bytes() == destination.read_bytes():
            continue
        if destination.exists():
            saved = backup / filename
            saved.parent.mkdir(parents=True, exist_ok=True)
            if not saved.exists():
                shutil.copy2(destination, saved)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".study-install-", dir=destination.parent) as staging:
            temporary = Path(staging) / destination.name
            shutil.copy2(source, temporary)
            os.replace(temporary, destination)
    print(f"Runtime installed: {runtime}")
    print(f"Previous scripts saved: {backup}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", type=Path, default=Path.home() / "Library/Application Support/EBSPrivatePodcast")
    parser.add_argument("--backup-dir", type=Path, default=SCRIPT_DIR.parent / ".runtime-backups" / datetime.now().strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args()
    install(args.runtime_dir.expanduser().resolve(), args.backup_dir.expanduser().resolve())


if __name__ == "__main__":
    main()
