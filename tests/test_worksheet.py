import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import deploy_study_pages as deployment
import generate_study_site as site
import study_worksheet as worksheet

STUDY = {
    "episode_title": "純喫茶の「純」って何？",
    "summary_ko": "순커피숍 이야기",
    "topics": ["純喫茶"],
    "vocabulary": [
        {"word": "純喫茶", "reading": "じゅんきっさ", "part_of_speech": "名詞", "meaning_ko": "순커피숍",
         "source_sentence_ja": "純喫茶を訪ね歩く若い人が増えています",
         "sentence_ko": "순가(純喫茶)를 찾아다니는 젊은이가 늘고 있습니다."},
        {"word": "レトロ", "reading": "れとろ", "meaning_ko": "레트로",
         "source_sentence_ja": "とてもレトロな店です", "sentence_ko": "아주 레트로한 가게입니다."},
        {"word": "背景", "reading": "はいけい", "meaning_ko": "배경",
         "source_sentence_ja": "人気を受けて", "sentence_ko": "인기를 받아"},
    ],
}
STEM = "20261010-0500_EBS_중급일본어"


class WorksheetContentTests(unittest.TestCase):
    def setUp(self):
        self.page = worksheet.worksheet_html(STUDY, STEM)

    def test_header_and_study_part(self):
        self.assertIn("EBS 중급일본어", self.page)
        self.assertIn("2026-10-10", self.page)
        self.assertIn("純喫茶の「純」って何？", self.page)
        self.assertIn("순커피숍 이야기", self.page)
        self.assertIn("じゅんきっさ", self.page)

    def test_blanks_hide_the_answer_in_sentence_and_hint(self):
        quiz = self.page.split('class="quiz"', 1)[1]
        self.assertIn(f"{worksheet.BLANK}を訪ね歩く若い人が増えています", quiz)
        self.assertIn("순가(○○)를 찾아다니는", quiz)
        self.assertNotIn("純喫茶を訪ね歩く", quiz)

    def test_sentence_without_the_word_is_not_a_blank_question(self):
        quiz = self.page.split('class="quiz"', 1)[1]
        self.assertNotIn("人気を受けて", quiz)

    def test_kana_only_words_skip_the_reading_question(self):
        readings = self.page.split("읽는 법 쓰기", 1)[1].split("빈칸 채우기", 1)[0]
        self.assertIn("背景", readings)
        self.assertNotIn("レトロ", readings)

    def test_text_is_escaped(self):
        page = worksheet.worksheet_html({**STUDY, "summary_ko": "<script>x</script>"}, STEM)
        self.assertNotIn("<script>x", page)


class WorksheetBuildTests(unittest.TestCase):
    def test_pdf_completion_needs_eof_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / "a.pdf"
            self.assertFalse(worksheet.pdf_complete(pdf))
            pdf.write_bytes(b"%PDF-1.4\npartial")
            self.assertFalse(worksheet.pdf_complete(pdf))
            pdf.write_bytes(b"%PDF-1.4\nbody\n%%EOF\n")
            self.assertTrue(worksheet.pdf_complete(pdf))

    def test_stale_pdf_is_rebuilt(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / f"{STEM}.study.json"
            study.write_text("{}")
            pdf = worksheet.worksheet_path(study)
            self.assertEqual(pdf.name, f"{STEM}.worksheet.pdf")
            self.assertFalse(worksheet.is_current(study))
            pdf.write_bytes(b"%PDF")
            future = time.time() + 60
            os.utime(pdf, (future, future))
            self.assertTrue(worksheet.is_current(study))
            os.utime(study, (future + 60, future + 60))
            self.assertFalse(worksheet.is_current(study))

    def test_login_session_stops_chrome_once_pdf_is_written(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / f"{STEM}.study.json"
            study.write_text(json.dumps(STUDY, ensure_ascii=False), encoding="utf-8")

            def fake_session(program, arguments, **kwargs):
                pdf = Path(next(a for a in arguments if a.startswith("--print-to-pdf=")).split("=", 1)[1])
                self.assertFalse(kwargs["finished"]())
                pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
                self.assertTrue(kwargs["finished"]())
                self.assertEqual(kwargs["process_type"], "Standard")
                return ""

            with patch.object(worksheet, "CHROME", Path(sys.executable)), \
                    patch.object(deployment, "run_in_gui_session", side_effect=fake_session):
                worksheet.build_pdf(study, worksheet.worksheet_path(study), login_session=True)
            self.assertTrue(worksheet.pdf_complete(worksheet.worksheet_path(study)))

    def test_missing_chrome_is_reported(self):
        with patch.object(worksheet, "CHROME", Path("/nonexistent/Chrome")), \
                self.assertRaisesRegex(RuntimeError, "Chrome not found"):
            worksheet.build_pdf(Path("a.study.json"), Path("a.pdf"))


class SessionFinishedTests(unittest.TestCase):
    def test_finished_job_is_stopped_without_waiting_for_exit(self):
        calls = []

        def execute(arguments, **kwargs):
            calls.append(arguments[1])
            return subprocess.CompletedProcess(arguments, 0, stdout="state = running\n", stderr="")

        with patch.object(deployment.subprocess, "run", side_effect=execute):
            deployment.run_in_gui_session("/fake/chrome", ["--headless"], timeout=5, finished=lambda: True)
        self.assertEqual(calls, ["bootstrap", "bootout"])


class SiteWorksheetTests(unittest.TestCase):
    def test_published_episode_links_its_worksheet(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "source"
            for program in site.feed.PROGRAMS:
                (workspace / program["source_dir"]).mkdir(parents=True)
            (workspace / "중급일본어" / f"{STEM}.m4a").write_bytes(b"audio")
            (workspace / "중급일본어" / "20261009-0500_EBS_중급일본어.m4a").write_bytes(b"audio")
            notes = root / "analysis"
            notes.mkdir()
            (notes / f"{STEM}.study.json").write_text(json.dumps(STUDY, ensure_ascii=False), encoding="utf-8")
            (notes / f"{STEM}.worksheet.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
            output = root / "site"
            data = site.publish(workspace, output, notes)
            latest, earlier = data["episodes"]
            self.assertEqual(latest["worksheet_url"], "worksheets/intermediate-japanese-20261010-0500.pdf")
            self.assertTrue((output / latest["worksheet_url"]).is_file())
            self.assertNotIn("worksheet_url", earlier)


if __name__ == "__main__":
    unittest.main()
