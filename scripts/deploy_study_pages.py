#!/usr/bin/env python3
"""Upload the recent study library and wait for its GitHub Pages deployment."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import uuid

import export_study_pages as pages


def run_in_gui_session(gh: str, arguments: list[str], timeout: int = 1800,
                       name: str = "github", process_type: str = "Background") -> str:
    """Run a command in the logged-in user's session through a temporary LaunchAgent.

    GitHub CLI needs the user's keychain there; Whisper needs it so Metal keeps
    running while the display sleeps, which it does not do under cron.
    """
    launchctl = shutil.which("launchctl") or "/bin/launchctl"
    domain = f"gui/{os.getuid()}"
    label = f"com.ebs.radio.{name}." + uuid.uuid4().hex
    target = f"{domain}/{label}"
    with tempfile.TemporaryDirectory(prefix=f"ebs-{name}-session-") as directory:
        root = Path(directory)
        output, errors, plist = root / "stdout", root / "stderr", root / "job.plist"
        plist.write_bytes(plistlib.dumps({
            "Label": label, "ProgramArguments": [gh, *arguments], "RunAtLoad": True,
            "ProcessType": process_type, "StandardOutPath": str(output),
            "StandardErrorPath": str(errors),
            "EnvironmentVariables": {"HOME": str(Path.home()),
                "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"},
        }))
        loaded = False
        try:
            subprocess.run([launchctl, "bootstrap", domain, str(plist)], check=True,
                           text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            loaded = True
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                state = subprocess.run([launchctl, "print", target], check=True, text=True,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30).stdout
                exit_code = re.search(r"^\s*last exit code = (\d+)\s*$", state, re.MULTILINE)
                if exit_code and re.search(r"^\s*state = (?:not running|exited)\s*$", state, re.MULTILINE):
                    stdout = output.read_text(encoding="utf-8", errors="replace") if output.is_file() else ""
                    stderr = errors.read_text(encoding="utf-8", errors="replace") if errors.is_file() else ""
                    code = int(exit_code.group(1))
                    if code:
                        raise subprocess.CalledProcessError(code, [gh, *arguments], output=stdout, stderr=stderr)
                    return stdout
                time.sleep(1)
            raise subprocess.TimeoutExpired([gh, *arguments], timeout)
        finally:
            if loaded:
                subprocess.run([launchctl, "bootout", target], text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)


def run(gh: str, arguments: list[str], timeout: int = 1800) -> str:
    if os.environ.get("EBS_GITHUB_SESSION") == "gui":
        return run_in_gui_session(gh, arguments, timeout)
    result = subprocess.run([gh, *arguments], check=True, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    return result.stdout


def archive_site(public: Path, archive: Path) -> None:
    with tarfile.open(archive, "w:gz", compresslevel=1) as bundle:
        # Add ordinary files individually so the Pages artifact has no links.
        for path in sorted(public.rglob("*")):
            if path.is_file():
                info = bundle.gettarinfo(str(path), arcname=path.relative_to(public).as_posix())
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.type = tarfile.REGTYPE
                info.linkname = ""
                info.size = path.stat().st_size
                with path.open("rb") as source:
                    bundle.addfile(info, source)


def deploy(workspace: Path, analysis_dir: Path, config: dict) -> None:
    repo = config["repository"]
    if not isinstance(repo, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Invalid GitHub repository")
    gh = shutil.which("gh") or "/opt/homebrew/bin/gh"
    if not Path(gh).is_file():
        raise FileNotFoundError("GitHub CLI is required")
    tag = "study-data"
    name = "study-site-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8] + ".tar.gz"
    with tempfile.TemporaryDirectory(prefix="ebs-pages-") as directory:
        root = Path(directory)
        report = pages.export(workspace, analysis_dir, root / "export",
                              int(config.get("max_episodes", 30)))
        archive = root / name
        archive_site(root / "export/public", archive)
        print(f"Uploading {report['episodes']} recordings ({report['site_bytes']:,} bytes) to {repo}", flush=True)
        run(gh, ["release", "upload", tag, str(archive), "--repo", repo])
        run(gh, ["workflow", "run", "pages.yml", "--repo", repo, "--ref", "main", "-f", f"asset={name}"])
        run_id = None
        for attempt in range(18):
            runs = json.loads(run(gh, ["run", "list", "--repo", repo, "--workflow", "pages.yml",
                                      "--limit", "30", "--json", "databaseId,displayTitle"]))
            match = next((item for item in runs if name in item["displayTitle"]), None)
            if match:
                run_id = str(match["databaseId"])
                break
            time.sleep(5)
        if run_id is None:
            raise RuntimeError("Deployment requested, but workflow run has not appeared; check GitHub Actions")
        print(f"Waiting for deployment: https://github.com/{repo}/actions/runs/{run_id}", flush=True)
        run(gh, ["run", "watch", run_id, "--repo", repo, "--exit-status", "--interval", "15"])
        # Only remove older bundles after this exact bundle is successfully live.
        # A later concurrent upload is preserved, as are unrelated release files.
        release = json.loads(run(gh, ["api", f"repos/{repo}/releases/tags/{tag}"]))
        current = next(asset for asset in release["assets"] if asset["name"] == name)
        for asset in release["assets"]:
            if (asset["name"].startswith("study-site-") and asset["name"].endswith(".tar.gz")
                    and asset["id"] < current["id"]):
                try:
                    run(gh, ["api", "--method", "DELETE", f"repos/{repo}/releases/assets/{asset['id']}"])
                except subprocess.CalledProcessError:
                    print(f"Warning: old deployment bundle could not be removed: {asset['name']}", flush=True)
        owner, repository = repo.split("/")
        print(f"Published: https://{owner}.github.io/{repository}/", flush=True)


# Waits before the second and third attempts. A network or GitHub hiccup must
# not leave the site a day behind; each attempt uploads a fresh bundle and the
# successful one removes the bundles left by failed attempts.
RETRY_DELAYS = (60, 300)


def load_config(workspace: Path, config_path: Path | None = None) -> dict | None:
    """Return the Pages settings, or None when publishing is not enabled."""
    path = config_path or Path(os.environ.get("STUDY_PAGES_CONFIG", str(workspace / "study_pages.json")))
    if not path.is_file():
        return None
    config = json.loads(path.read_text(encoding="utf-8"))
    return config if config.get("enabled", False) else None


def deploy_with_retry(workspace: Path, analysis_dir: Path, config: dict) -> None:
    for attempt, delay in enumerate((*RETRY_DELAYS, None), start=1):
        try:
            deploy(workspace, analysis_dir, config)
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError) as error:
            detail = (getattr(error, "stderr", None) or str(error)).strip()
            if delay is None:
                raise SystemExit(f"GitHub Pages update failed after {attempt} attempts: {detail}")
            print(f"GitHub Pages update failed (attempt {attempt}); retrying in {delay}s: {detail}", flush=True)
            time.sleep(delay)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=pages.study_site.feed.WORKSPACE_DIR)
    parser.add_argument("--analysis-dir", type=Path)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    config = load_config(args.workspace, args.config)
    if config is None:
        return
    deploy_with_retry(args.workspace, args.analysis_dir or args.workspace / "analysis_output", config)


if __name__ == "__main__":
    main()
