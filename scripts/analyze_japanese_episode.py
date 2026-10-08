#!/usr/bin/env python3
"""Transcribe one EBS recording locally and create a Korean study guide."""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from generate_feed import parse_env_file


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_WORKSPACE_DIR = SCRIPT_DIR.parent
WORKSPACE_DIR = Path(
    os.environ.get("RADIO_WORKSPACE", str(DEFAULT_WORKSPACE_DIR))
).expanduser().resolve()
DEFAULT_MODEL_PATH = WORKSPACE_DIR / "models/ggml-large-v3.bin"
DEFAULT_OUTPUT_DIR = WORKSPACE_DIR / "analysis_output"
ANALYSIS_ENV_PATH = Path(os.environ.get("ANALYSIS_ENV_PATH", str(WORKSPACE_DIR / "analysis.env"))).expanduser()
ANALYSIS_SETTINGS = parse_env_file(ANALYSIS_ENV_PATH)
DEFAULT_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", ANALYSIS_SETTINGS.get("OLLAMA_MODEL", "qwen3.5:27b"))
DEFAULT_OLLAMA_URL = os.environ.get(
    "OLLAMA_URL", ANALYSIS_SETTINGS.get("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
)
OLLAMA_LAUNCHD_SERVICE = os.environ.get("OLLAMA_LAUNCHD_SERVICE", ANALYSIS_SETTINGS.get("OLLAMA_LAUNCHD_SERVICE", ""))


def ollama_options(model: str, *, proofreading: bool = False) -> dict[str, object]:
    if model.lower().startswith("qwen3.5"):
        # Qwen3.5's model card recommends sampling rather than greedy decoding.
        # Keep penalties neutral for faithful translation and source quotation.
        return {
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 20, "min_p": 0.0, "presence_penalty": 0.0,
            "repeat_penalty": 1.0, "num_ctx": 16384, "num_predict": 8192,
        }
    return {"temperature": 0.0 if proofreading else 0.1, "num_ctx": 16384}


STUDY_SCHEMA = {
    "type": "object",
    "properties": {
        "episode_title": {"type": "string"},
        "summary_ko": {"type": "string"},
        "topics": {"type": "array", "items": {"type": "string"}},
        "vocabulary": {
            "type": "array",
            "minItems": 1,
            "maxItems": 25,
            "items": {
                "type": "object",
                "properties": {
                    "word": {"type": "string"},
                    "reading": {"type": "string"},
                    "part_of_speech": {"type": "string"},
                    "meaning_ko": {"type": "string"},
                    "source_sentence_ja": {"type": "string"},
                    "sentence_ko": {"type": "string"},
                    "timestamp": {"type": "string"},
                    "why_important": {"type": "string"},
                },
                "required": [
                    "word",
                    "reading",
                    "part_of_speech",
                    "meaning_ko",
                    "source_sentence_ja",
                    "sentence_ko",
                    "timestamp",
                    "why_important",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["episode_title", "summary_ko", "topics", "vocabulary"],
    "additionalProperties": False,
}


def executable(name: str, fallback: str | None = None) -> str:
    resolved = shutil.which(name)
    if resolved:
        return resolved
    if fallback and Path(fallback).is_file():
        return fallback
    raise SystemExit(f"Required executable not found: {name}")


def ensure_ollama_server(chat_url: str) -> None:
    parsed = urllib.parse.urlsplit(chat_url)
    health_url = urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, "/api/tags", "", "")
    )

    def is_available() -> bool:
        try:
            with urllib.request.urlopen(health_url, timeout=2) as response:
                return response.status == 200
        except (urllib.error.URLError, TimeoutError):
            return False

    if is_available():
        return

    if OLLAMA_LAUNCHD_SERVICE:
        command = ["/bin/launchctl", "kickstart", f"gui/{os.getuid()}/{OLLAMA_LAUNCHD_SERVICE}"]
        print(f"Ollama server is not running; starting {OLLAMA_LAUNCHD_SERVICE}...", flush=True)
    else:
        command = ["/usr/bin/open", "-gj", "-a", "Ollama"]
        print("Ollama server is not running; launching Ollama.app...", flush=True)
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as error:
        raise RuntimeError(f"Could not start Ollama server: {error}") from error

    for _ in range(45):
        if is_available():
            print("Ollama server is ready.", flush=True)
            return
        time.sleep(2)
    raise RuntimeError("Ollama server did not become ready within 90 seconds")


def needs_login_session() -> bool:
    """Whether Metal work must be moved into the logged-in user's session.

    Under cron, which runs outside that session, Whisper stalls on the GPU while
    the display sleeps. EBS_WHISPER_SESSION=gui|direct overrides the check.
    """
    mode = os.environ.get("EBS_WHISPER_SESSION", "auto")
    if mode in ("gui", "direct"):
        return mode == "gui"
    try:
        manager = subprocess.run(["/bin/launchctl", "managername"], capture_output=True,
                                 text=True, timeout=10).stdout.strip()
        if manager == "Aqua":
            return False
        # Without a login session there is nowhere to move the job.
        return subprocess.run(["/bin/launchctl", "print", f"gui/{os.getuid()}"],
                              capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def run(command: list[str], description: str, login_session: bool = False) -> None:
    print(f"{description}...", flush=True)
    started_at = time.monotonic()
    if login_session:
        from deploy_study_pages import run_in_gui_session

        try:
            run_in_gui_session(command[0], command[1:], timeout=3600,
                               name="whisper", process_type="Standard")
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or error.output or "").strip()
            raise RuntimeError(f"{description} failed:\n{detail}") from error
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"{description} timed out after {error.timeout}s") from error
    else:
        # Whisper can split a multibyte character across segments, so its
        # output is not always valid UTF-8.
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"{description} failed:\n{detail}")
    elapsed = time.monotonic() - started_at
    print(f"{description} complete ({elapsed:.1f}s)", flush=True)


def write_text_atomic(path: Path, value: str) -> None:
    with tempfile.TemporaryDirectory(prefix=".ebs-study-", dir=path.parent) as staging:
        temporary = Path(staging) / path.name
        temporary.write_text(value, encoding="utf-8")
        os.replace(temporary, path)


def repair_utf8(path: Path) -> None:
    """Drop the partial characters Whisper leaves where it splits a segment."""
    data = path.read_bytes()
    text = data.decode("utf-8", errors="ignore")
    if text.encode("utf-8") != data:
        write_text_atomic(path, text)


def parse_srt(path: Path) -> str:
    # Transcripts written before repair_utf8 may still hold partial characters.
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8", errors="ignore").strip())
    transcript: list[str] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        timestamp = lines[1].split("-->", 1)[0].strip().split(",", 1)[0]
        text = " ".join(lines[2:])
        transcript.append(f"[{timestamp}] {text}")
    if not transcript:
        raise RuntimeError(f"No transcript segments found in {path}")
    return "\n".join(transcript)


def request_study_guide(
    transcript: str, episode_title: str, model: str, url: str
) -> dict[str, object]:
    system_prompt = (
        "당신은 한국인 중급 일본어 학습자를 위한 편집자입니다. "
        "제공된 일본어 방송 전사에 실제로 등장한 내용만 사용하세요. "
        "전사 오류 가능성을 고려하고 근거가 불명확한 단어는 제외하세요. "
        "한국어 필드에 한글과 한자를 섞은 조어를 만들지 마세요. "
        "일본 고유 문화명은 자연스러운 한국어 설명 뒤 괄호에 일본어 원어를 쓰세요."
    )
    user_prompt = f"""
다음은 {episode_title}의 타임스탬프 포함 일본어 전사입니다.

요구사항:
1. 방송의 핵심 내용을 한국어 3~5문장으로 요약하세요.
2. 한국인 중급 학습자에게 유용한 주요 어휘와 표현을 8~18개 고르세요.
   짧은 전사는 항목이 더 적어도 됩니다. 개수를 채우려고 어휘나 원문을 만들지 마세요.
3. 너무 기초적인 단어, 단순 인명, 광고성 고유명사는 제외하세요.
4. 읽기는 히라가나로, 뜻과 문장 해석은 자연스러운 한국어로 쓰세요.
   meaning_ko는 어휘의 사전식 뜻만 쓰고, sentence_ko는 설명이나 요약이 아니라
   source_sentence_ja의 조건·이유·나열·시제를 그대로 살린 직접 번역으로 쓰세요.
   sentence_ko에는 선택한 단어의 뜻만 쓰지 말고 원문 문장 전체를 번역하세요.
   예: 界隈은 문맥에 따라 '같은 관심사를 가진 사람들의 모임/문화'로 풀어 쓰고,
   '계隈', '일기계隈'처럼 한글과 한자를 섞은 단어를 만들지 마세요.
   あえて는 문맥에 따라 '굳이', '일부러'로 옮기고 '도전적으로'로 옮기지 마세요.
5. source_sentence_ja는 전사의 문장을 수정하거나 새로 만들지 말고 그대로 인용하세요.
   필요하면 서로 인접한 전사 조각만 연결할 수 있습니다.
6. timestamp는 해당 원문이 처음 등장하는 [HH:MM:SS] 시각을 쓰세요.
7. 동일하거나 활용형만 다른 어휘는 하나로 합치세요.
8. episode_title은 방송의 실제 주제를 나타내는 짧은 일본어 제목으로 쓰세요.
   날짜, 파일명, 프로그램명만 반복하지 마세요.

전사:
{transcript}
""".strip()

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "format": STUDY_SCHEMA,
        "options": ollama_options(model),
    }
    if model.lower().startswith("qwen3.5"):
        payload["think"] = False
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    print(f"Extracting vocabulary with {model}...", flush=True)
    started_at = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=1200) as response:
            response_data = json.load(response)
    except urllib.error.URLError as error:
        raise RuntimeError(f"Ollama request failed: {error}") from error

    content = response_data["message"]["content"]
    study_guide = json.loads(content)
    elapsed = time.monotonic() - started_at
    print(f"Vocabulary extraction complete ({elapsed:.1f}s)", flush=True)
    return study_guide


def proofread_study_guide(
    study_guide: dict[str, object], model: str, url: str, transcript: str | None = None
) -> dict[str, object]:
    if model.lower().startswith("qwen3.5") and transcript is not None:
        return proofread_qwen35(study_guide, model, url, transcript)
    system_prompt = (
        "당신은 일본어 사전 편집자이자 한국어 번역 교정자입니다. "
        "음성인식 결과에는 동음이의어와 활용형 오류가 있을 수 있으므로 "
        "자연스러운 표준 일본어인지 엄격히 판단하세요. "
        "summary_ko와 모든 _ko 필드는 반드시 한국어로 쓰세요. "
        "한국어 번역은 원문 전체의 의미를 보존하고, 한글과 한자를 섞은 조어를 만들지 마세요."
    )
    user_prompt = f"""
다음 일본어 학습자료 초안을 엄격하게 교정하세요.

교정 규칙:
1. 모든 일본어 어휘의 표준 읽기, 품사, 한국어 뜻을 다시 확인하세요.
2. source_sentence_ja가 문법적으로 부자연스럽거나 문맥상 음성인식 오류로 보이면
   해당 항목을 삭제하세요. 원문을 추측하여 새 문장으로 고치면 안 됩니다.
3. 서로 중복되는 어휘나 지나치게 기초적인 단어를 제거하세요.
4. 문장 번역은 원문의 의미를 빠짐없이 자연스럽게 옮기세요.
   설명식 의역을 피하고, 「と」「ので」「ながら」「たり」 같은 문법 관계와
   미완성된 문장 끝맺음도 원문 그대로 보존하세요.
5. 실제 전사가 제공되면 원문과 어휘를 대조하세요. 인용이 틀렸으면 실제 전사의
   문장으로 교체하고 그 시작 시각을 쓰세요. 인접한 조각만 연결할 수 있습니다.
   원문에 근거가 없는 어휘는 삭제하세요. 전사가 없으면 인용과 시각을 유지하세요.
6. 최종 어휘는 학습 가치가 높은 8~18개를 목표로 정리하세요.
   유용한 항목이 적으면 개수가 적어도 됩니다. 개수를 채우려고 항목을 만들지 마세요.
7. summary_ko의 어색한 한국어도 교정하세요. 문화명은 필요한 경우 한국어 설명과
   일본어 원어를 함께 쓰되, 한글과 한자를 어색하게 섞은 번역은 피하세요.
   예: 界隈은 같은 관심사를 가진 사람들의 모임/문화이며, 日記界隈은
   '일기를 쓰는 사람들의 문화(日記界隈)'처럼 쓰세요. '계隈', '일기계隈'은 잘못된 번역입니다.
8. sentence_ko는 source_sentence_ja 전체의 번역이어야 합니다. 단어 뜻만 쓰지 마세요.
   あえて는 문맥에 따라 '굳이/일부러'로 번역하고, とか의 나열 의미도 보존하세요.

초안:
{json.dumps(study_guide, ensure_ascii=False, indent=2)}
""".strip()
    if transcript is not None:
        user_prompt += "\n\n대조할 실제 전사:\n" + transcript
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "think": not model.lower().startswith("qwen3.5"),
        "format": STUDY_SCHEMA,
        "options": ollama_options(model, proofreading=True),
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    print(f"Proofreading vocabulary with {model}...", flush=True)
    started_at = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=1200) as response:
            response_data = json.load(response)
    except urllib.error.URLError as error:
        raise RuntimeError(f"Ollama proofreading request failed: {error}") from error
    corrected = json.loads(response_data["message"]["content"])
    elapsed = time.monotonic() - started_at
    print(f"Vocabulary proofreading complete ({elapsed:.1f}s)", flush=True)
    return corrected


def ground_vocabulary(study_guide: dict[str, object], transcript: str) -> None:
    """Keep words and quotations grounded, allowing dictionary-form verbs."""
    try:
        from sudachipy import dictionary, tokenizer
        parser = dictionary.Dictionary().create()
        canonical = lambda text: "".join(m.dictionary_form() for m in parser.tokenize(text, tokenizer.Tokenizer.SplitMode.C) if m.surface().strip())
    except ImportError:
        canonical = lambda text: re.sub(r"\s+", "", text)
    segments = re.findall(r"^\[(\d{2}:\d{2}:\d{2})\]\s*(.*)$", transcript, re.MULTILINE)
    grounded = []
    for item in study_guide.get("vocabulary", []):
        word = canonical(str(item.get("word", "")))
        if not word:
            continue
        try:
            validate_source_sentences({"vocabulary": [item]}, transcript)
            valid = word in canonical(str(item.get("source_sentence_ja", "")))
        except RuntimeError:
            valid = False
        if not valid:
            match = next(((time, text) for time, text in segments if word in canonical(text)), None)
            if match is None:
                print(f"Excluded word without transcript evidence: {item.get('word')}", flush=True)
                continue
            item["timestamp"], item["source_sentence_ja"] = match
        grounded.append(item)
    if not grounded:
        raise RuntimeError("No vocabulary has transcript evidence")
    study_guide["vocabulary"] = grounded


def proofread_qwen35(study_guide: dict[str, object], model: str, url: str, transcript: str) -> dict[str, object]:
    # Fresh translations in small batches avoid copying mistakes from the draft.
    ground_vocabulary(study_guide, transcript)
    vocabulary = study_guide["vocabulary"]
    print(f"Translating {len(vocabulary)} source-backed words in small batches with {model}...", flush=True)
    started_at = time.monotonic()
    for start in range(0, len(vocabulary), 4):
        batch = [{"id": i, "word": vocabulary[i]["word"], "source_sentence_ja": vocabulary[i]["source_sentence_ja"]} for i in range(start, min(start + 4, len(vocabulary)))]
        properties = {"translations": {"type": "array", "minItems": len(batch), "maxItems": len(batch), "items": {"type": "object", "properties": {"id": {"type": "integer", "enum": [v["id"] for v in batch]}, "meaning_ko": {"type": "string"}, "sentence_ko": {"type": "string"}}, "required": ["id", "meaning_ko", "sentence_ko"], "additionalProperties": False}}}
        instruction = (
            "일본어 단어와 예문을 한국어로 번역하세요. meaning_ko에는 문맥에 맞는 사전식 뜻을, "
            "sentence_ko에는 일본어 예문 전체의 직접 번역을 쓰세요. 단어 뜻만 쓰거나 문장을 요약하지 마세요. "
            "조사, 시제, 나열(とか), 미완성된 끝맺음도 보존하세요. あえて는 굳이/일부러, "
            "根強い는 뿌리 깊은/강하게 남아 있는 뜻입니다. "
            "문화명은 '같은 관심사를 가진 사람들의 모임(界隈)', '일기를 쓰는 사람들의 문화(日記界隈)'처럼 "
            "한국어 설명 뒤 괄호에 원어를 쓰세요. '계隈', '일기界隈'처럼 섞어 쓰지 마세요.\n"
            + json.dumps(batch, ensure_ascii=False)
        )
        if start == 0:
            properties["summary_ko"] = {"type": "string"}
            instruction += "\n실제 방송 내용을 한국어로만 3~5문장 요약해 summary_ko에 쓰세요.\n" + transcript
        schema = {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}
        payload = {"model": model, "messages": [{"role": "system", "content": "당신은 일본어를 자연스러운 한국어로 정확하게 옮기는 번역가입니다. 모든 _ko 필드는 한국어로 쓰세요."}, {"role": "user", "content": instruction}], "stream": False, "think": False, "format": schema, "options": ollama_options(model, proofreading=True)}
        request = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=600) as response:
            translated = json.loads(json.load(response)["message"]["content"])
        results = translated["translations"]
        if sorted(result["id"] for result in results) != [v["id"] for v in batch]:
            raise RuntimeError("Translation batch does not match the source items")
        for result in results:
            vocabulary[result["id"]]["meaning_ko"] = result["meaning_ko"]
            vocabulary[result["id"]]["sentence_ko"] = result["sentence_ko"]
        if start == 0:
            study_guide["summary_ko"] = translated["summary_ko"]
        print(f"Korean translation complete: {start + len(batch)}/{len(vocabulary)}", flush=True)
    print(f"Vocabulary proofreading complete ({time.monotonic() - started_at:.1f}s)", flush=True)
    return study_guide


def katakana_to_hiragana(value: str) -> str:
    converted = []
    for character in value:
        codepoint = ord(character)
        if 0x30A1 <= codepoint <= 0x30F6:
            converted.append(chr(codepoint - 0x60))
        else:
            converted.append(character)
    return "".join(converted)


def apply_sudachi_readings(study_guide: dict[str, object]) -> int:
    try:
        from sudachipy import dictionary, tokenizer
    except ImportError:
        print(
            "Sudachi is not installed; keeping LLM-generated readings.", flush=True
        )
        return 0

    tokenizer_object = dictionary.Dictionary().create()
    split_mode = tokenizer.Tokenizer.SplitMode.C
    corrected = 0
    vocabulary = study_guide.get("vocabulary", [])
    if not isinstance(vocabulary, list):
        return 0

    for item in vocabulary:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word", ""))
        morphemes = list(tokenizer_object.tokenize(word, split_mode))
        readings = [morpheme.reading_form() for morpheme in morphemes]
        if readings and all(readings):
            dictionary_reading = katakana_to_hiragana("".join(readings))
            if item.get("reading") != dictionary_reading:
                item["reading"] = dictionary_reading
                corrected += 1
        if len(morphemes) == 1:
            dictionary_pos = morphemes[0].part_of_speech()[0]
            if item.get("part_of_speech") != dictionary_pos:
                item["part_of_speech"] = dictionary_pos
                corrected += 1
    print(f"Sudachi dictionary corrections: {corrected}", flush=True)
    return corrected


def validate_source_sentences(
    study_guide: dict[str, object], transcript: str
) -> None:
    def normalize(value: str) -> str:
        return re.sub(r"[\s、。！？!?・\"「」『』]", "", value)

    # Keep segment times separate so adjacent subtitle text can be joined.
    segments = re.findall(r"^\[(\d{2}:\d{2}:\d{2})\]\s*(.*)$", transcript, re.MULTILINE)
    normalized_transcript = "".join(normalize(text) for _, text in segments) if segments else normalize(transcript)
    vocabulary = study_guide.get("vocabulary", [])
    if not isinstance(vocabulary, list):
        raise RuntimeError("Study guide vocabulary is not a list")
    invalid = []
    for item in vocabulary:
        if not isinstance(item, dict):
            raise RuntimeError("Study guide vocabulary item is not an object")
        sentence = str(item.get("source_sentence_ja", ""))
        normalized_sentence = normalize(sentence)
        if not normalized_sentence or normalized_sentence not in normalized_transcript:
            invalid.append(sentence)
            continue
        # Use the actual matching segment time instead of trusting a generated time.
        match_offset = normalized_transcript.find(normalized_sentence)
        offset = 0
        for timestamp, text in segments:
            offset += len(normalize(text))
            if match_offset < offset:
                item["timestamp"] = timestamp
                break
    if invalid:
        raise RuntimeError(
            "Study guide contains sentences absent from the transcript: "
            + "; ".join(invalid)
        )


def markdown_for(study_guide: dict[str, object], audio_name: str) -> str:
    topics = study_guide.get("topics", [])
    vocabulary = study_guide.get("vocabulary", [])
    lines = [
        f"# {study_guide.get('episode_title', audio_name)} 학습 노트",
        "",
        f"- 원본 오디오: `{audio_name}`",
        f"- 주요 주제: {', '.join(str(topic) for topic in topics)}",
        "",
        "## 방송 요약",
        "",
        str(study_guide.get("summary_ko", "")),
        "",
        "## 주요 어휘와 표현",
        "",
    ]
    for index, item in enumerate(vocabulary, start=1):
        if not isinstance(item, dict):
            continue
        lines.extend(
            [
                f"### {index}. {item.get('word', '')}（{item.get('reading', '')}）",
                "",
                f"- 품사: {item.get('part_of_speech', '')}",
                f"- 뜻: {item.get('meaning_ko', '')}",
                f"- 위치: {item.get('timestamp', '')}",
                f"- 원문: {item.get('source_sentence_ja', '')}",
                f"- 해석: {item.get('sentence_ko', '')}",
                f"- 선정 이유: {item.get('why_important', '')}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def notes_title_for(audio_stem: str, study_guide: dict[str, object]) -> str:
    match = re.search(r"(\d{8})-\d{4}_EBS_(초급일본어|중급일본어)", audio_stem)
    if match:
        date_text = datetime.strptime(match.group(1), "%Y%m%d").strftime("%Y-%m-%d")
        prefix = f"{date_text} {match.group(2)}"
    else:
        prefix = audio_stem.replace("_", " ")
    episode_title = str(study_guide.get("episode_title", "학습노트"))
    return f"{prefix} — {episode_title}"


def announced_title_for(transcript: str, fallback: str) -> str:
    for line in transcript.splitlines()[:30]:
        match = re.search(r"(?:今日のタイトルは|今日のテーマは)\s*(.+)$", line)
        if match and 3 <= len(match.group(1).strip()) <= 60:
            return match.group(1).strip()
    return fallback


def notes_html_for(
    study_guide: dict[str, object], audio_name: str, note_title: str
) -> str:
    escape = lambda value: html.escape(str(value), quote=True)
    topics = study_guide.get("topics", [])
    vocabulary = study_guide.get("vocabulary", [])
    parts = [
        "<div>",
        f"<h1>{escape(note_title)}</h1>",
        f"<p><b>원본 오디오:</b> {escape(audio_name)}</p>",
        f"<p><b>주요 주제:</b> {escape(', '.join(str(topic) for topic in topics))}</p>",
        "<h2>방송 요약</h2>",
        f"<p>{escape(study_guide.get('summary_ko', ''))}</p>",
        "<h2>주요 어휘와 표현</h2>",
    ]
    for index, item in enumerate(vocabulary, start=1):
        if not isinstance(item, dict):
            continue
        parts.extend(
            [
                f"<h3>{index}. {escape(item.get('word', ''))}（{escape(item.get('reading', ''))}）</h3>",
                "<ul>",
                f"<li><b>품사:</b> {escape(item.get('part_of_speech', ''))}</li>",
                f"<li><b>뜻:</b> {escape(item.get('meaning_ko', ''))}</li>",
                f"<li><b>위치:</b> {escape(item.get('timestamp', ''))}</li>",
                f"<li><b>원문:</b> {escape(item.get('source_sentence_ja', ''))}</li>",
                f"<li><b>해석:</b> {escape(item.get('sentence_ko', ''))}</li>",
                f"<li><b>선정 이유:</b> {escape(item.get('why_important', ''))}</li>",
                "</ul>",
            ]
        )
    parts.extend(["<p>#EBS일본어 #일본어학습</p>", "</div>"])
    return "\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--ollama-model", default=DEFAULT_OLLAMA_MODEL)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--force-transcribe", action="store_true")
    parser.add_argument("--transcript-only", action="store_true")
    parser.add_argument(
        "--reuse-study-json",
        action="store_true",
        help="reuse an existing .study.json as the proofreading draft",
    )
    parser.add_argument("--skip-proofread", action="store_true")
    args = parser.parse_args()

    try:
        analyze(args)
    finally:
        # Publish completed recordings even when analysis fails. Existing guides
        # remain available; manual analyses update the same phone screen too.
        publisher = SCRIPT_DIR / "generate_study_site.py"
        if publisher.is_file() and not args.transcript_only:
            environment = dict(os.environ, STUDY_ANALYSIS_DIR=str(args.output_dir.expanduser().resolve()))
            result = subprocess.run([sys.executable, str(publisher)], env=environment)
            if result.returncode:
                print("Warning: study library could not be updated", file=sys.stderr)
            pages_publisher = SCRIPT_DIR / "deploy_study_pages.py"
            if pages_publisher.is_file():
                result = subprocess.run([sys.executable, str(pages_publisher),
                    "--workspace", str(WORKSPACE_DIR), "--analysis-dir", str(args.output_dir.expanduser().resolve())],
                    env=environment)
                if result.returncode:
                    print("Warning: GitHub Pages could not be updated; local recording and notes are saved", file=sys.stderr)


def analyze(args: argparse.Namespace) -> None:

    audio = args.audio.expanduser().resolve()
    model_path = args.model.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if not audio.is_file():
        raise SystemExit(f"Audio file not found: {audio}")
    if not model_path.is_file():
        raise SystemExit(f"Whisper model not found: {model_path}")
    output_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg = executable("ffmpeg", "/opt/homebrew/bin/ffmpeg")
    whisper_cli = executable("whisper-cli", "/opt/homebrew/bin/whisper-cli")
    transcript_base = output_dir / f"{audio.stem}.transcript"
    transcript_srt = Path(f"{transcript_base}.srt")

    if args.force_transcribe or not transcript_srt.is_file():
        with tempfile.TemporaryDirectory(prefix="ebs-whisper-", dir="/tmp") as temp_dir:
            wav_path = Path(temp_dir) / f"{audio.stem}.wav"
            run(
                [
                    ffmpeg,
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(audio),
                    "-vn",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    str(wav_path),
                ],
                "Preparing 16 kHz audio",
            )
            run(
                [
                    whisper_cli,
                    "-m",
                    str(model_path),
                    "-f",
                    str(wav_path),
                    "-l",
                    "ja",
                    "-t",
                    "8",
                    # Do not feed earlier text back as context. With it, Korean
                    # commentary under forced Japanese sent Whisper into loops
                    # that repeated one sentence for the rest of the episode
                    # (2026-10-07: 240 of 373 lines from 09:04 onward).
                    "-mc",
                    "0",
                    "-oj",
                    "-osrt",
                    "-otxt",
                    "-of",
                    str(transcript_base),
                    "-np",
                ],
                "Transcribing Japanese audio",
                login_session=needs_login_session(),
            )
            for suffix in (".srt", ".txt", ".json"):
                output = Path(f"{transcript_base}{suffix}")
                if output.is_file():
                    repair_utf8(output)
    else:
        print(f"Reusing transcript: {transcript_srt}", flush=True)

    transcript = parse_srt(transcript_srt)
    if args.transcript_only:
        print(transcript_srt)
        return

    episode_title = audio.stem.replace("_", " ")
    study_json_path = output_dir / f"{audio.stem}.study.json"
    study_draft_path = output_dir / f"{audio.stem}.study.draft.json"
    study_markdown_path = output_dir / f"{audio.stem}.study.md"
    study_notes_html_path = output_dir / f"{audio.stem}.study.notes.html"
    notes_title_path = output_dir / "apple_notes_title.txt"
    notes_body_path = output_dir / "apple_notes_body.html"

    if not args.reuse_study_json or not args.skip_proofread:
        ensure_ollama_server(args.ollama_url)

    if args.reuse_study_json:
        if not study_json_path.is_file():
            raise SystemExit(f"Study JSON not found: {study_json_path}")
        study_guide = json.loads(study_json_path.read_text(encoding="utf-8"))
    else:
        study_guide = request_study_guide(
            transcript, episode_title, args.ollama_model, args.ollama_url
        )
    study_draft_path.write_text(
        json.dumps(study_guide, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if not args.skip_proofread:
        study_guide = proofread_study_guide(
            study_guide, args.ollama_model, args.ollama_url, transcript
        )
    study_guide["episode_title"] = announced_title_for(transcript, str(study_guide.get("episode_title", episode_title)))
    apply_sudachi_readings(study_guide)
    validate_source_sentences(study_guide, transcript)
    write_text_atomic(study_json_path,
        json.dumps(study_guide, ensure_ascii=False, indent=2) + "\n",
    )
    study_markdown_path.write_text(
        markdown_for(study_guide, audio.name), encoding="utf-8"
    )
    note_title = notes_title_for(audio.stem, study_guide)
    note_body = notes_html_for(study_guide, audio.name, note_title)
    study_notes_html_path.write_text(note_body, encoding="utf-8")
    notes_body_path.write_text(note_body, encoding="utf-8")
    notes_title_path.write_text(note_title + "\n", encoding="utf-8")
    print(f"Study JSON: {study_json_path}")
    print(f"Study Markdown: {study_markdown_path}")
    print(f"Apple Notes HTML: {study_notes_html_path}")


def restart_in_analysis_venv_if_needed() -> None:
    venv_python = WORKSPACE_DIR / ".venv-analysis/bin/python3"
    if (
        importlib.util.find_spec("sudachipy") is None
        and venv_python.is_file()
        and Path(sys.prefix).resolve() != venv_python.parent.parent.resolve()
    ):
        os.execv(str(venv_python), [str(venv_python), *sys.argv])


if __name__ == "__main__":
    restart_in_analysis_venv_if_needed()
    main()
