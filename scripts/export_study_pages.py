#!/usr/bin/env python3
"""Prepare a separate GitHub Pages repository; never upload anything."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

import generate_study_site as study_site


WORKFLOW = """name: Publish study site
on:
  push:
    branches: [main]
  workflow_dispatch:
permissions:
  contents: read
  pages: write
  id-token: write
concurrency:
  group: pages
  cancel-in-progress: false
jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v4
        with:
          path: public
      - name: Deploy
        id: deployment
        uses: actions/deploy-pages@v4
"""


def export(workspace: Path, analysis_dir: Path, destination: Path,
           max_episodes: int = 30, max_bytes: int = 950_000_000) -> dict:
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f"Choose a new output folder: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".pages-export-", dir=destination.parent) as staging:
        repository = Path(staging) / "repository"
        public = repository / "public"
        data = study_site.publish(workspace, public, analysis_dir, max_episodes)
        (public / ".nojekyll").touch()
        size = sum(path.stat().st_size for path in public.rglob("*") if path.is_file())
        if size > max_bytes:
            raise ValueError(f"Site is {size:,} bytes; export fewer episodes (limit {max_bytes:,})")
        workflow = repository / ".github" / "workflows" / "pages.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text(WORKFLOW, encoding="utf-8")
        report = {
            "episodes": len(data["episodes"]),
            "study_guides": sum(episode["study"] is not None for episode in data["episodes"]),
            "site_bytes": size,
            "first_date": data["episodes"][0]["date"],
            "last_date": data["episodes"][-1]["date"],
            "public_access": True,
        }
        (repository / "export-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (repository / "README.md").write_text(
            "# 오늘 일본어\n\n"
            "GitHub Pages로 공개할 수 있는 학습 화면의 정적 배포본입니다.\n"
            f"{report['last_date']}–{report['first_date']}, 녹음 {report['episodes']}회, "
            f"학습노트 {report['study_guides']}개.\n\n"
            "공개하면 녹음·요약·단어를 누구나 열 수 있습니다. "
            "설정 파일, 로컬 서버 주소와 토큰, 전사 원본, 모델, 로그는 포함하지 않습니다.\n\n"
            "배포: 이 폴더만 별도 저장소의 main 브랜치에 올리고, "
            "Settings → Pages → Source에서 GitHub Actions를 선택합니다.\n"
            "워크플로는 public 폴더만 배포합니다. 현재는 수동으로 만든 배포본이며, "
            "맥의 새 녹음이 인터넷에 자동 업로드되지는 않습니다.\n",
            encoding="utf-8")
        os.replace(repository, destination)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New destination folder")
    parser.add_argument("--workspace", type=Path, default=study_site.feed.WORKSPACE_DIR)
    parser.add_argument("--analysis-dir", type=Path)
    parser.add_argument("--max-episodes", type=int, default=30)
    args = parser.parse_args()
    report = export(args.workspace, args.analysis_dir or args.workspace / "analysis_output",
                    args.output, args.max_episodes)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Prepared locally (not published): {args.output.resolve()}")


if __name__ == "__main__":
    main()
