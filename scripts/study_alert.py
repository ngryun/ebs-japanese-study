#!/usr/bin/env python3
"""Send a failure alert to the iPhone as an Apple Reminders reminder.

The signed EBSStudyAlert.app owns the Automation permission for Reminders,
like EBSStudyNotes.app does for Notes. This module only writes the message
next to the runtime scripts (on the internal disk, so an unmounted recording
disk can still be reported) and launches the helper.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


RUNTIME_DIR = Path(os.environ.get(
    "EBS_RUNTIME_DIR", str(Path.home() / "Library/Application Support/EBSPrivatePodcast")))
HELPER_APP = Path(os.environ.get(
    "ALERT_HELPER_APP", str(Path.home() / "Applications/EBSStudyAlert.app")))


def send_alert(title: str, body: str) -> bool:
    print(f"Alert: {title}\n{body}", file=sys.stderr, flush=True)
    if not HELPER_APP.is_dir():
        print(f"Warning: alert helper not installed: {HELPER_APP}", file=sys.stderr, flush=True)
        return False
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    (RUNTIME_DIR / "alert_title.txt").write_text(title + "\n", encoding="utf-8")
    (RUNTIME_DIR / "alert_body.txt").write_text(body + "\n", encoding="utf-8")
    result = subprocess.run(["/usr/bin/open", "-gj", "-n", str(HELPER_APP)],
                            capture_output=True, text=True)
    if result.returncode:
        print(f"Warning: could not launch alert helper: {result.stderr.strip()}", file=sys.stderr, flush=True)
    return result.returncode == 0


if __name__ == "__main__":
    title = sys.argv[1] if len(sys.argv) > 1 else "EBS 일본어 알림 테스트"
    body = sys.argv[2] if len(sys.argv) > 2 else "알림이 아이폰에 도착하면 설정이 끝난 것입니다."
    raise SystemExit(0 if send_alert(title, body) else 1)
