#!/usr/bin/env python3
"""Turn a study guide into a printable A4 worksheet PDF.

Part 1 repeats the summary and the vocabulary with the broadcast sentences;
part 2 asks for meanings, readings and the missing word in each sentence, so
part 1 doubles as the answer key. Chrome prints the HTML, which gives proper
Japanese and Korean typesetting with the system fonts.

Run directly to build worksheets for study guides that lack an up-to-date PDF.
"""

from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time

CHROME = Path(os.environ.get("CHROME_BIN", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
KANJI = re.compile(r"[㐀-鿿々]")
BLANK = "（　　　　　）"
MAX_BLANK_SENTENCES = 8

STYLE = """
@page { size: A4; margin: 15mm 16mm 16mm; }
* { box-sizing: border-box; }
body { margin: 0; color: #253b33; font: 10.5pt/1.6 "Apple SD Gothic Neo", "Hiragino Sans", sans-serif; }
:lang(ja) { font-family: "Hiragino Sans", "Hiragino Kaku Gothic ProN", sans-serif; }
header { border-bottom: 2px solid #244d40; padding-bottom: 8px; margin-bottom: 14px; }
.meta { display: flex; justify-content: space-between; font-size: 9pt; color: #727b73; }
.badge { color: #244d40; font-weight: 700; }
h1 { font: 600 19pt/1.35 "Hiragino Mincho ProN", serif; margin: 6px 0 2px; }
.name { font-size: 9pt; color: #727b73; }
h2 { font-size: 12.5pt; margin: 18px 0 8px; color: #244d40; }
h2 small { font-weight: 400; color: #727b73; font-size: 9pt; margin-left: 6px; }
.summary { background: #f3f5ef; border-radius: 6px; padding: 10px 12px; margin: 0; }
table { width: 100%; border-collapse: collapse; }
.vocab td { border-top: 1px solid #dedfd5; padding: 6px 4px; vertical-align: top; }
.vocab .no { width: 22px; color: #a3aa73; font-weight: 700; }
.vocab .word { width: 34%; }
.vocab .word strong { font-size: 13pt; }
.vocab .reading { display: block; color: #727b73; font-size: 9pt; }
.vocab .pos { color: #727b73; font-size: 8.5pt; }
.vocab .example-row td { border-top: 0; padding-top: 0; }
.vocab .example { font-size: 9.5pt; color: #4a5a52; }
.vocab .example span { display: block; color: #727b73; font-size: 9pt; }
.vocab tbody { break-inside: avoid; }
.quiz { break-before: page; }
.grid { display: grid; grid-template-columns: 1fr 1fr; column-gap: 22px; }
.item { display: flex; align-items: baseline; gap: 6px; padding: 7px 0; break-inside: avoid; }
.item .n { color: #a3aa73; font-weight: 700; min-width: 18px; }
.line { flex: 1; border-bottom: 1px solid #b9bdb2; min-height: 1.3em; }
.sentence { padding: 7px 0 8px; break-inside: avoid; }
.sentence p { margin: 0; }
.sentence .hint { color: #727b73; font-size: 9pt; margin-left: 24px; }
.write .line { display: block; height: 2.2em; margin-bottom: 4px; }
footer { margin-top: 18px; font-size: 8.5pt; color: #727b73; text-align: right; }
"""


def esc(value: object) -> str:
    return html.escape(str(value or ""))


def episode_meta(stem: str) -> tuple[str, str]:
    match = re.match(r"(\d{4})(\d{2})(\d{2})-\d{4}_EBS_(.+)$", stem)
    if not match:
        return "", ""
    year, month, day, course = match.groups()
    return f"{year}-{month}-{day}", course


def blank_sentence(item: dict) -> str | None:
    sentence, word = item.get("source_sentence_ja", ""), item.get("word", "")
    if not word or word not in sentence:
        return None
    return esc(sentence.replace(word, "\0", 1)).replace("\0", BLANK)


def blank_hint(item: dict) -> str:
    # The model sometimes leaves the Japanese word inside the Korean
    # translation ("순가(純喫茶)를…"), which would give the answer away.
    hint = item.get("sentence_ko", "")
    for answer in (item.get("word", ""), item.get("reading", "")):
        if answer:
            hint = hint.replace(answer, "○○")
    return esc(hint)


def worksheet_html(study: dict, stem: str) -> str:
    date, course = episode_meta(stem)
    vocabulary = [item for item in study.get("vocabulary", []) if item.get("word")]
    rows = []
    for number, item in enumerate(vocabulary, start=1):
        pos = f' <span class="pos" lang="ja">{esc(item.get("part_of_speech"))}</span>' if item.get("part_of_speech") else ""
        example = ""
        if item.get("source_sentence_ja"):
            example = (f'<tr class="example-row"><td></td><td colspan="2" class="example"><span lang="ja">{esc(item["source_sentence_ja"])}</span>'
                       f'{esc(item.get("sentence_ko"))}</td></tr>')
        rows.append(f'<tbody><tr><td class="no">{number:02d}</td><td class="word"><strong lang="ja">{esc(item["word"])}</strong>'
                    f'<span class="reading" lang="ja">{esc(item.get("reading"))}</span></td>'
                    f'<td>{esc(item.get("meaning_ko"))}{pos}</td></tr>{example}</tbody>')

    meanings = "".join(f'<div class="item"><span class="n">{n}.</span><span lang="ja">{esc(item["word"])}</span><span class="line"></span></div>'
                       for n, item in enumerate(vocabulary, start=1))
    readable = [item for item in vocabulary if KANJI.search(item["word"])]
    readings = "".join(f'<div class="item"><span class="n">{n}.</span><span lang="ja">{esc(item["word"])}</span><span class="line"></span></div>'
                       for n, item in enumerate(readable, start=1))
    blanks = [(item, sentence) for item in vocabulary if (sentence := blank_sentence(item))][:MAX_BLANK_SENTENCES]
    sentences = "".join(f'<div class="sentence"><p><span class="n">{n}.</span> <span lang="ja">{sentence}</span></p>'
                        f'<p class="hint">{blank_hint(item)}</p></div>'
                        for n, (item, sentence) in enumerate(blanks, start=1))

    sections = [f'<h2>1. 뜻 쓰기<small>단어의 뜻을 한국어로 쓰세요.</small></h2><div class="grid">{meanings}</div>']
    if readable:
        sections.append(f'<h2>{len(sections) + 1}. 읽는 법 쓰기<small>히라가나로 쓰세요.</small></h2><div class="grid">{readings}</div>')
    if blanks:
        sections.append(f'<h2>{len(sections) + 1}. 빈칸 채우기<small>방송에 나온 문장입니다. 알맞은 표현을 넣으세요.</small></h2>{sentences}')
    sections.append(f'<h2>{len(sections) + 1}. 문장 만들기<small>오늘 표현을 하나 골라 나만의 문장을 써 보세요.</small></h2>'
                    '<div class="write">' + '<span class="line"></span>' * 4 + '</div>')

    title = study.get("episode_title") or f"{date} {course}"
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>{esc(date)} {esc(course)} 학습지</title><style>{STYLE}</style></head>
<body>
<header><div class="meta"><span class="badge">EBS {esc(course)}</span><span>{esc(date)} · 오늘 일본어 학습지</span></div>
<h1 lang="ja">{esc(title)}</h1></header>
<h2>오늘의 이야기</h2><p class="summary">{esc(study.get("summary_ko"))}</p>
<h2>기억할 단어와 표현<small>{len(vocabulary)}개 · 2부 문제의 정답입니다.</small></h2>
<table class="vocab">{''.join(rows)}</table>
<section class="quiz">
<header><div class="meta"><span class="badge">확인 문제</span><span>{esc(date)} · 이름 ____________</span></div>
<h1 lang="ja">{esc(title)}</h1></header>
{''.join(sections)}
<footer>정답은 1부 단어 목록에서 확인하세요.</footer>
</section>
</body></html>
"""


def chrome_arguments(page: Path, pdf: Path, profile: Path) -> list[str]:
    # A throwaway profile with a mock keychain keeps Chrome away from the
    # user's browser data and from keychain prompts.
    return ["--headless", "--disable-gpu", "--use-mock-keychain", "--no-first-run",
            "--no-default-browser-check", "--disable-extensions", "--disable-background-networking",
            "--disable-component-update", "--disable-sync", f"--user-data-dir={profile}",
            "--no-pdf-header-footer", f"--print-to-pdf={pdf}", page.as_uri()]


def pdf_complete(pdf: Path) -> bool:
    """Whether Chrome has finished writing the PDF (it ends with %%EOF)."""
    try:
        size = pdf.stat().st_size
        with pdf.open("rb") as handle:
            handle.seek(max(0, size - 1024))
            return b"%%EOF" in handle.read()
    except OSError:
        return False


def print_directly(arguments: list[str], pdf: Path, timeout: float) -> None:
    # Headless Chrome on macOS writes the PDF and then keeps running, so wait
    # for the file rather than for the process, then stop its process group.
    process = subprocess.Popen([str(CHROME), *arguments], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        deadline = time.monotonic() + timeout
        while not pdf_complete(pdf):
            if process.poll() is not None:
                raise RuntimeError(f"Chrome exited ({process.returncode}) without writing the worksheet PDF")
            if time.monotonic() > deadline:
                raise RuntimeError(f"Chrome did not finish the worksheet PDF within {timeout:.0f}s")
            time.sleep(0.5)
    finally:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(process.pid, sig)
                process.wait(timeout=10)
                break
            except ProcessLookupError:
                break
            except subprocess.TimeoutExpired:
                continue


def build_pdf(study_json: Path, pdf_path: Path, login_session: bool = False) -> None:
    """Write the worksheet PDF for one study guide.

    Chrome works in a local temporary folder and the finished file is moved
    into place here, so Chrome never needs access to the recording disk.
    """
    if not CHROME.is_file():
        raise RuntimeError(f"Google Chrome not found: {CHROME}")
    study = json.loads(study_json.read_text(encoding="utf-8"))
    stem = study_json.name.removesuffix(".study.json")
    with tempfile.TemporaryDirectory(prefix="ebs-worksheet-", dir="/tmp") as directory:
        root = Path(directory)
        page, pdf = root / "worksheet.html", root / "worksheet.pdf"
        page.write_text(worksheet_html(study, stem), encoding="utf-8")
        arguments = chrome_arguments(page, pdf, root / "profile")
        if login_session:
            from deploy_study_pages import run_in_gui_session

            try:
                run_in_gui_session(str(CHROME), arguments, timeout=300, name="worksheet",
                                   process_type="Standard", finished=lambda: pdf_complete(pdf))
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                raise RuntimeError(f"Chrome could not print the worksheet: {error}") from error
        else:
            print_directly(arguments, pdf, timeout=300)
        if not pdf_complete(pdf):
            raise RuntimeError("Chrome finished without writing the worksheet PDF")
        staged = pdf_path.with_name(f".{pdf_path.name}.partial")
        shutil.copyfile(pdf, staged)
        os.replace(staged, pdf_path)


def worksheet_path(study_json: Path) -> Path:
    return study_json.with_name(study_json.name.removesuffix(".study.json") + ".worksheet.pdf")


def is_current(study_json: Path) -> bool:
    """A PDF is stale when its study guide or this template is newer."""
    pdf = worksheet_path(study_json)
    return pdf.is_file() and pdf.stat().st_mtime >= max(study_json.stat().st_mtime, Path(__file__).stat().st_mtime)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-dir", type=Path,
                        default=Path(os.environ.get("RADIO_WORKSPACE", str(Path(__file__).resolve().parents[1]))) / "analysis_output")
    parser.add_argument("--force", action="store_true", help="rebuild PDFs that are already current")
    args = parser.parse_args()
    built = 0
    for study_json in sorted(args.analysis_dir.glob("*.study.json")):
        if study_json.name.startswith(".") or (not args.force and is_current(study_json)):
            continue
        try:
            build_pdf(study_json, worksheet_path(study_json))
            built += 1
            print(f"Worksheet: {worksheet_path(study_json).name}", flush=True)
        except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
            print(f"Warning: worksheet failed for {study_json.name}: {error}", flush=True)
    print(f"Worksheets built: {built}")


if __name__ == "__main__":
    main()
