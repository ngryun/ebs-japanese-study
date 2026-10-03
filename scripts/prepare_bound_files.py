#!/usr/bin/env python3
"""Add Bound-friendly names, metadata, and artwork to existing recordings."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = SCRIPT_DIR.parent
ARTWORK_PATH = WORKSPACE_DIR / "artwork.png"
TIMESTAMP_RE = re.compile(r"(\d{8})-(\d{4})")
PROGRAMS = (
    ("초급일본어", "초급일본어"),
    ("중급일본어", "중급일본어"),
)


def resolve_ffmpeg() -> str:
    configured = os.environ.get("FFMPEG_BIN")
    candidates = [
        configured,
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        shutil.which("ffmpeg"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise SystemExit("ffmpeg executable not found")


def recording_info(path: Path, program_title: str) -> tuple[datetime, Path]:
    match = TIMESTAMP_RE.search(path.name)
    if match is None:
        raise ValueError("filename has no YYYYMMDD-HHMM timestamp")
    recorded_at = datetime.strptime("".join(match.groups()), "%Y%m%d%H%M")
    destination = path.with_name(
        f"{recorded_at.strftime('%Y%m%d-%H%M')}_EBS_{program_title}.m4a"
    )
    return recorded_at, destination


def remux_recording(
    ffmpeg: str,
    source: Path,
    destination: Path,
    recorded_at: datetime,
    program_title: str,
) -> None:
    if destination != source and destination.exists():
        raise FileExistsError(f"destination already exists: {destination}")

    temporary = source.with_name(f".{source.stem}.bound-tmp.m4a")
    display_date = recorded_at.strftime("%Y-%m-%d")
    command = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
    ]
    if ARTWORK_PATH.is_file():
        command.extend(["-i", str(ARTWORK_PATH), "-map", "0:a:0", "-map", "1:v:0"])
    else:
        command.extend(["-map", "0:a:0"])

    command.extend(["-c:a", "copy"])
    if ARTWORK_PATH.is_file():
        command.extend(
            [
                "-c:v",
                "png",
                "-disposition:v:0",
                "attached_pic",
                "-metadata:s:v:0",
                "title=Cover",
                "-metadata:s:v:0",
                "comment=Cover (front)",
            ]
        )

    command.extend(
        [
            "-metadata",
            f"title={display_date} {program_title}",
            "-metadata",
            "artist=EBS",
            "-metadata",
            f"album=EBS {program_title}",
            "-metadata",
            "album_artist=EBS",
            "-metadata",
            f"date={display_date}",
            "-metadata",
            "genre=Language Learning",
            str(temporary),
        ]
    )

    try:
        subprocess.run(command, check=True)
        shutil.copystat(source, temporary)
        os.replace(temporary, source)
        if destination != source:
            source.rename(destination)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="rewrite files that already use the Bound-friendly filename",
    )
    args = parser.parse_args()
    ffmpeg = resolve_ffmpeg()

    processed = 0
    skipped = 0
    for directory_name, program_title in PROGRAMS:
        directory = WORKSPACE_DIR / directory_name
        for source in sorted(directory.glob("*.m4a")):
            try:
                recorded_at, destination = recording_info(source, program_title)
            except ValueError as error:
                print(f"Skip: {source.name} ({error})")
                skipped += 1
                continue

            if source == destination and not args.refresh:
                skipped += 1
                continue

            print(f"{source.name} -> {destination.name}")
            if not args.dry_run:
                remux_recording(
                    ffmpeg, source, destination, recorded_at, program_title
                )
            processed += 1

    print(f"Bound preparation complete: {processed} processed, {skipped} skipped")


if __name__ == "__main__":
    main()
