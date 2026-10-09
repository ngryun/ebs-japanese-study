# 로컬 녹음·분석 설정

주소와 경로는 예시입니다. 설정 파일은 예제를 복사하고, 경로와 서버 주소를 자신의 환경에 맞춰 지정하세요.

이 폴더는 요일에 따라 프로그램을 나눠 저장하도록 맞춰져 있습니다.

- `초급일본어`: 월, 화, 수 오전 5시부터 20분 녹음
- `중급일본어`: 목, 금, 토 오전 5시부터 20분 녹음
- 일요일: 녹음 없음

## 실행 파일

- 스크립트: `scripts/record_ebs_japanese.sh`
- 기본 스트림 주소: `https://ebsonair.ebs.co.kr/fmradiofamilypc/familypc1m/playlist.m3u8`
- 기본 녹음 길이: `1200`초
- 파일명: `YYYYMMDD-HHMM_EBS_초급일본어.m4a` 또는 `YYYYMMDD-HHMM_EBS_중급일본어.m4a`

녹음이 끝나면 M4A에 Bound 같은 오디오북 앱용 제목, 저자, 앨범, 날짜,
장르와 표지를 자동으로 넣습니다. 오디오는 다시 인코딩하지 않으므로 원본 음질이
유지됩니다.

스크립트는 자기 위치를 기준으로 저장 경로를 계산하므로, 폴더 전체를 원하는 위치로 옮겨도 그대로 사용할 수 있습니다.

기존 녹음 파일의 파일명과 메타데이터를 같은 규칙으로 다시 정리하려면 다음을 실행합니다.

```sh
python3 /path/to/ebs_japan_radio/scripts/prepare_bound_files.py
```

## 로컬 일본어 전사 및 학습 어휘 추출

### 아이폰에서 녹음·요약·단어를 함께 보기

`오늘 일본어` 학습 화면은 날짜별 녹음 재생, 한국어 요약, 주요 어휘와 원문·해석을
한 페이지에 표시합니다. 단어 옆의 시간 버튼으로 해당 녹음 위치를 들을 수 있고,
재생 속도와 듣던 위치는 브라우저에 저장됩니다. 초급·중급 모두 표시하며
팟캐스트의 `PODCAST_INCLUDE_SLUGS` 설정과는 별개입니다.

집 안 Wi-Fi에서 아이폰 Safari로 다음 주소를 엽니다.

```text
http://YOUR-MAC.local:8081/YOUR_PODCAST_TOKEN/study/index.html
```

Safari의 공유 메뉴에서 **홈 화면에 추가**를 선택하면 `오늘 일본어` 아이콘으로
열 수 있습니다. 맥과 기존 오디오 서버가 켜져 있어야 하며, 현재 주소는
집 밖에서는 연결되지 않습니다. 별도의 계정이나 앱 설치는 필요하지 않습니다.

새 녹음이 저장되면 화면의 보관함을 먼저 갱신하고, 로컬 분석이 완료되면 요약과
단어를 반영합니다. 열린 화면도 60초마다 또는 다시 화면으로 돌아왔을 때
최신 자료를 확인하며, 재생 중인 방송은 바꾸지 않습니다. 아직 분석하지 않은
기존 방송은 녹음만 표시됩니다.

학습 화면만 수동으로 갱신하려면 다음을 실행합니다.

```sh
/path/to/ebs_japan_radio/.venv-analysis/bin/python3 \
  /path/to/ebs_japan_radio/scripts/generate_study_site.py
```

- 기본 공개 경로: `<PODCAST_SITE_ROOT>/<PODCAST_TOKEN>/study/`
- `STUDY_SITE_DIR`: 공개 폴더를 별도로 지정할 때 사용
- `STUDY_WORKSPACE`: 녹음 원본 폴더를 별도로 지정할 때 사용
- `STUDY_ANALYSIS_DIR`: `analysis_output`의 위치를 별도로 지정할 때 사용
- `STUDY_MAX_EPISODES`: 보관함에 표시할 최근 회차 수, 기본 `180`
- `PYTHON_BIN`: 자동 녹음에서 사용할 Python 실행 파일을 지정할 때 사용

### GitHub Pages 배포본 준비

학습 화면은 정적 HTML/CSS/JavaScript여서 GitHub Pages에서도 실행됩니다.
Pages 사이트와 포함된 녹음은 인터넷에 공개됩니다. 비공개 저장소를 사용해도
일반 개인 계정의 Pages 사이트 접근을 비공개로 바꾸지는 못합니다.
전체 녹음은 약 1.54GB로 Pages의 사이트 1GB 제한을 넘으므로, 기본 배포본은
최근 30회만 포함합니다. 설정·토큰·전사 원본·모델·로그는 제외합니다.

```sh
/path/to/ebs_japan_radio/.venv-analysis/bin/python3 \
  /path/to/ebs_japan_radio/scripts/export_study_pages.py \
  --output /path/to/ebs_japan_radio/github-pages-preview
```

출력 폴더는 새 경로여야 합니다. `--max-episodes`로 회차 수를 조정할 수 있고,
950MB를 초과하면 불완전한 배포본을 남기지 않고 중단합니다. 이 명령은 로컬
파일만 준비하며 GitHub에 업로드하지 않습니다. **출력 폴더만** 별도 저장소로
올립니다. 기존 작업 폴더 전체를 업로드하면 녹음 원본과 개인 설정이 노출됩니다.

출력 폴더의 `public/`이 실제 사이트이고 `.github/workflows/pages.yml`이
배포 워크플로입니다. GitHub 저장소의 Settings → Pages → Source를
GitHub Actions로 설정하면 초기 정적 템플릿은 main 브랜치 푸시 시 배포합니다. 맥에서 새로
생성한 녹음과 학습노트의 업로드는 별도로 연결해야 합니다.

### 현재 GitHub Pages와 자동 갱신

macOS의 실제 예약 실행에서도 배포가 동작하도록 `cron`에 전체 디스크 접근 권한을
허용했습니다. 녹음·전사는 외장 디스크를 사용합니다. GitHub CLI는
`EBS_GITHUB_SESSION=gui` 설정으로 로그인한 사용자의 기존 키체인 인증을 이용합니다.
각 CLI 명령은 임시 LaunchAgent로 실행하고 끝나면 제거하며, 인증 토큰을 별도 파일에
복사하지 않습니다. 사용자는 맥에 로그인한 상태여야 합니다.

2026-10-06에 실제 cron에서 녹음 파일·Whisper 모델 읽기, 녹음·전사 폴더 쓰기,
기존 GitHub 계정 인증을 확인했습니다. 코드 테스트 22개도 통과했습니다.

2026-10-07 첫 예약 실행에서 Whisper 전사가 평소 약 4분 대신 89분 걸렸습니다.
cron은 로그인 세션 밖에서 실행되므로 모니터가 꺼져 있는 동안 Whisper의 GPU(Metal)
작업이 멈췄고, 모니터가 켜진 직후 재개됐습니다. 같은 조건에서 로그인 세션의
LaunchAgent로 실행하면 모니터가 꺼져 있어도 정상 속도였습니다. 그래서 cron에서
실행될 때는 Whisper만 임시 LaunchAgent(`ProcessType` Standard)로 옮겨 실행합니다.
터미널에서 직접 실행할 때는 기존처럼 바로 실행하며, `EBS_WHISPER_SESSION=gui` 또는
`direct`로 강제할 수 있습니다. Ollama는 이미 LaunchAgent라 영향이 없습니다.

2026-10-08에는 두 가지를 더 고쳤습니다.

- 녹음 ffmpeg가 멈춘 HLS 요청에서 05:20부터 07:44까지 기다렸습니다. 입출력 시간
  제한이 없으면 종료 신호로도 끝나지 않습니다. 이제 `-rw_timeout` 30초를 넘기면
  해당 조각만 건너뛰고 녹음을 이어 갑니다.
- 일본어 고정 전사에서 한국어 해설이 나오면 Whisper가 한 문장을 방송 끝까지
  반복했습니다(10/07은 09:04부터 373줄 중 240줄). 이전 문장을 문맥으로 넘기지 않는
  `-mc 0`을 적용해 같은 방송이 20분 전체 전사되는 것을 확인했습니다.

2026-10-10에는 07:30 점검이 "학습노트가 만들어지지 않았습니다"를 알렸습니다.
전날 21:34 Ollama 앱이 자동 업데이트됐는데 `com.ebs.radio.ollama` 서버는 10/03부터
옛 실행 파일로 계속 돌고 있었고, macOS가 이 프로세스의 외장 디스크 접근을 막아
모든 요청이 HTTP 500(`operation not permitted`)으로 실패했습니다. 이제 분석을
시작할 때 서버가 실행 파일보다 먼저 시작됐으면 `launchctl kickstart -k`로 다시
띄우고, Ollama 오류는 응답 본문의 원인까지 로그에 남깁니다.

- 학습 화면: https://ngryun.github.io/ebs-japanese-study/
- 배포 저장소: https://github.com/ngryun/ebs-japanese-study
- 로컬 설정: `study_pages.json` (`enabled`, `repository`, `max_episodes`)

실제 배포는 `scripts/deploy_study_pages.py`가 최근 30회 배포본을 만들어
`study-data` 릴리스에 업로드하고, 배포 워크플로를 실행하는 방식입니다.
오디오를 Git 커밋 이력에 넣지 않고, 배포가 성공한 뒤 이전 배포 파일을
삭제합니다. 새 배포가 실패하면 기존 Pages 사이트는 유지됩니다.

사용자 승인에 따라 `enabled: true`로 설정하고 자동 런타임에 배포 도구를
설치했습니다. 분석 스크립트 종료 시 로컬 화면 갱신에 이어 Pages도 갱신합니다.
기존 월요일~토요일 오전 5시 녹음 일정으로 동작하며 일요일에는 새 녹음이 없습니다.
분석 실패 시에도
완성된 녹음을 반영하며, Pages 업로드 실패가 원본이나 학습노트를 지우지는 않습니다.
맥이 켜져 있고 인터넷에 연결되어야 새 자료를 생성·업로드할 수 있습니다.
이미 배포한 자료는 맥이 꺼져 있어도 열 수 있습니다.

수동 재배포:

```sh
/path/to/ebs_japan_radio/.venv-analysis/bin/python3 \
  /path/to/ebs_japan_radio/scripts/deploy_study_pages.py
```

`gh auth login`으로 로그인한 GitHub CLI가 필요합니다. 토큰은 설정 파일에
저장하지 않습니다. 자동 업로드를 중단하려면 `study_pages.json`의 `enabled`를
`false`로 바꿉니다. 이미 공개한 사이트를 삭제하지는 않습니다.

배포가 실패하면 1분, 5분 뒤 두 번 더 시도합니다. 시도마다 새 묶음을 올리고,
성공한 배포가 실패한 시도의 묶음까지 정리합니다.

#### 07:30 점검과 아이폰 알림

월~토 07:30에 cron이 `check_study_pages.py`를 실행합니다. 05:00 작업이 아직
돌고 있으면 최대 45분 기다린 뒤, 오늘 녹음과 학습노트가 공개 사이트의
`data.json`에 있는지 확인합니다. 사이트만 뒤처져 있으면 다시 배포합니다.
외장 디스크가 빠져 있어도 알릴 수 있도록 내장 디스크의 Command Line Tools
파이썬으로 실행합니다.

해결하지 못한 문제가 남을 때만 `~/Applications/EBSStudyAlert.app`이 미리 알림의
`EBS 일본어 알림` 목록에 항목을 만들고, iCloud를 거쳐 1분 뒤 아이폰에 알림이
뜹니다. 정상인 날에는 알림이 없습니다. 결과는
`~/Library/Logs/ebs_japan_radio.check.log`, 보조 앱 상태는 런타임 폴더의
`alert_status.txt`에서 확인합니다.

보조 앱은 `scripts/build_alert_helper.sh`로 다시 만들 수 있습니다. 다시 만들면
서명이 바뀌므로 첫 알림 때 맥에서 '미리 알림' 제어를 다시 허용해야 합니다.
알림 경로만 시험하려면 다음을 실행합니다.

```sh
/Library/Developer/CommandLineTools/usr/bin/python3 \
  "$HOME/Library/Application Support/EBSPrivatePodcast/study_alert.py"
```

변경 없는 오디오는 다시 복사하지 않습니다. 소스 폴더가 없거나 새 파일 복사에
실패하면 기존 목록을 유지하며, 이전에 공개한 오디오를 자동 삭제하지 않습니다.
메타데이터 처리나 최종 저장에 실패한 녹음 원본은 내부 임시 폴더에 보존하고
그 경로를 로그로 알립니다. 피드·미러 복사 실패는 이후 학습 분석을 중단하지 않습니다.

자동 실행용 홈 폴더 런타임에는 `record_ebs_japanese.sh`, `generate_feed.py`,
`analyze_japanese_episode.py`, `generate_study_site.py`와 `study_web/`을 함께
반영해야 합니다. `start_server.sh`도 학습 화면을 갱신한 뒤 서버를 실행합니다.
다음 명령은 기존 런타임 설정을 유지하고 교체하는 스크립트를
`.runtime-backups`에 백업한 뒤 코드만 갱신합니다.

```sh
/path/to/ebs_japan_radio/.venv-analysis/bin/python3 \
  /path/to/ebs_japan_radio/scripts/install_study_runtime.py
```

`scripts/analyze_japanese_episode.py`는 녹음 파일을 외부 API로 보내지 않고 다음
결과를 만듭니다.

- Whisper large-v3 일본어 전사: TXT, SRT, JSON
- Ollama를 이용한 한국어 요약과 주요 어휘·원문 문장 추출
- Sudachi 사전을 이용한 읽기와 품사 교정
- 원문 문장이 실제 전사에 존재하는지 검증

요약·어휘·번역 모델은 `Qwen3.5 27B` (`qwen3.5:27b`)입니다. 모델과 서버는
`analysis.env`에서 지정하며, `OLLAMA_MODEL`과 `OLLAMA_URL` 환경변수 또는
`--ollama-model`·`--ollama-url` 옵션이 해당 설정보다 우선합니다.
`ANALYSIS_ENV_PATH`로 다른 설정 파일을 사용할 수 있습니다.

현재 맥은 내부 디스크 공간을 아끼기 위해 모델을 외장 디스크의 `models/ollama/`에
저장하고, `com.ebs.radio.ollama.plist`로 `127.0.0.1:11435`에서 분석용 서버를
자동 실행합니다. 기존 Ollama 앱의 `11434` 서버와 모델은 그대로 사용할 수 있습니다.
분석용 서버는 로컬 모델만 사용하며, 녹음과 함께 외장 디스크가 연결되어 있어야 합니다.
음성인식 모델은 기존 Whisper large-v3를 유지합니다.
Qwen3.5의 초안 생성과 번역 교정은 비추론 모드로 실행합니다. 9B 시험에서 추론
교정 시간이 과도하게 길어져, 27B에도 비교 시험에서 확인한 비추론 설정을 적용합니다.
샘플링 설정은 공식 모델 카드에 맞춰 조정하되 원문 인용을 위해 반복 페널티는
중립적으로 유지합니다. 번역 지침은 문장 전체의 의미와 자연스러운 한국어 표기를
명시하며, 원문 검증을 통과한 자료만 기존 학습노트를 교체합니다.
교정에는 실제 전사도 함께 제공해 인용을 대조합니다. 어휘는 8~18개를 목표로
하되, 짧은 방송에서는 개수를 채우려고 불필요한 항목을 추가하지 않습니다.
Qwen3.5에서는 인용문에 해당 어휘가 실제로 있는지도 사전 기본형으로 대조합니다.
다른 전사 구간에만 있으면 그 구간으로 연결하고, 방송에 없는 단어는 제외합니다.
한국어 뜻과 문장 번역은 오류가 있는 초안을 복사하지 않도록 4개씩 새로 생성합니다.
2026-10-03 동일 방송·설정으로 9B와 27B를 비교했습니다. 전사와 모델 로딩을
제외한 학습 자료 생성 시간은 9B 약 3분 12초, 27B 약 7분 37초였습니다.
원문과 대조한 12문항의 소규모 검토에서는 27B의 번역 품질이 더 좋아,
사용자 선택에 따라 자동 분석을 27B로 전환했습니다. 27B에서도 어색한 표현이나
문장 끝맺음 오류가 남을 수 있습니다. 비교 기록은
`logs/model-comparison-20261003/summary.json`에 보존했습니다.
이날 사이트의 기존 학습 자료는 별도로 검토·수정한 13개 어휘 자료를 유지합니다.

같은 날 Qwen3.6-27B도 동일한 12문장과 방송 전사로 비교했습니다. 원문과 대조한
AI 검토 점수는 3.5-27B 66/72, 3.6-27B 63/72였습니다. 이번 재측정에서 학습 자료
생성은 각각 약 8분 40초(8개 어휘), 10분 7초(10개 어휘)였으며, 출력 분량이 달라
총 시간만으로 모델 속도를 단정할 수 없습니다. 3.6의 최종 요약에도 한글·한자
혼용과 문화명 표기 오류가 남아 자동 분석은 3.5-27B를 유지합니다. 단일 시드의
소규모 시험이며 기존 전사의 반복 오류도 있어 일반적인 모델 우열을 뜻하지는
않습니다. 비교 원출력·설정·검토는 로컬 `logs/model-comparison-20261003-qwen36/`에
저장했고, 공개용 결과 요약은 [모델 비교](model-comparison-20261003.json)에 있습니다.
운영 설정과 사이트 학습 자료는 변경하지 않았습니다.

최초 한 번 필요한 설치:

```sh
brew install whisper-cpp
python3 -m venv /path/to/ebs_japan_radio/.venv-analysis
/path/to/ebs_japan_radio/.venv-analysis/bin/pip install -r /path/to/ebs_japan_radio/requirements-analysis.txt
```

Whisper 모델은 아래 위치에 `ggml-large-v3.bin`이라는 이름으로 둡니다.

```text
/path/to/ebs_japan_radio/models/ggml-large-v3.bin
```

분석 실행 예시:

```sh
python3 /path/to/ebs_japan_radio/scripts/analyze_japanese_episode.py \
  "/path/to/ebs_japan_radio/중급일본어/20260711-0500_EBS_중급일본어.m4a"
```

결과는 `analysis_output` 폴더에 저장됩니다. 같은 파일을 다시 실행하면 기존
전사를 재사용하고 어휘 추출과 검수만 다시 수행합니다.

### iCloud 메모 자동 생성

분석이 성공하면 승인된 `~/Applications/EBSStudyNotes.app`이 결과를 iCloud
메모의 `EBS 일본어 학습노트` 폴더에 자동으로 생성합니다. 같은 제목의 메모가
이미 있으면 새 메모를 중복 생성하지 않고 내용을 갱신합니다. 메모 제목은 날짜,
과정명, 회차의 주제를 포함합니다.

메모 자동 생성을 일시적으로 끄려면 `APPLE_NOTES_ENABLED=0`을 설정합니다.
보조 앱의 위치를 옮겼다면 `NOTES_HELPER_APP`에 앱의 절대 경로를 지정할 수
있습니다. 메모 저장 실패는 녹음, Bound 복사, 팟캐스트 피드에 영향을 주지
않으며 결과는 `analysis_output/apple_notes_status.txt`에서 확인할 수 있습니다.

자동 녹음에서는 파일과 팟캐스트 피드를 먼저 저장한 다음 이 분석을 자동으로
실행합니다. 분석이 실패해도 이미 완료된 녹음과 피드는 유지되며, 오류는
`~/Library/Logs/ebs_japan_radio.record.log`에 기록됩니다. 분석 중에는 macOS의
`caffeinate`로 잠자기를 막고, Ollama 서버가 꺼져 있으면 Ollama 앱을 자동으로
시작해 최대 90초 동안 준비를 기다립니다.

분석을 일시적으로 끄고 녹음만 하려면 다음 환경 변수를 사용합니다.

```sh
ANALYZE_RECORDING=0 /bin/sh /path/to/ebs_japan_radio/scripts/record_ebs_japanese.sh
```

### Bound Inbox 자동 복사

macOS에서는 녹음과 메타데이터 처리가 끝난 M4A를 다음 iCloud Drive 폴더로
자동 복사합니다.

```text
iCloud Drive/Bound Inbox
```

아이폰에서는 Bound의 `Add Audiobook` > `Apple Files`에서 `Bound Inbox`를
열고 최신 파일만 가져오면 됩니다. iCloud 복사가 실패해도 녹음, 팟캐스트 피드,
로컬 분석은 계속 진행됩니다.

자동 복사를 끄려면 `BOUND_ICLOUD_ENABLED=0`을 설정합니다. 다른 폴더를 쓰려면
`BOUND_ICLOUD_DIR`에 원하는 절대 경로를 지정할 수 있습니다.

## 수동 실행

```sh
/bin/sh /path/to/ebs_japan_radio/scripts/record_ebs_japanese.sh
```

## 동작 테스트

실제 녹음 없이 어떤 폴더와 파일명으로 저장되는지만 확인할 수 있습니다.

```sh
DAY_OVERRIDE=1 DRY_RUN=1 /bin/sh /path/to/ebs_japan_radio/scripts/record_ebs_japanese.sh
DAY_OVERRIDE=4 DRY_RUN=1 /bin/sh /path/to/ebs_japan_radio/scripts/record_ebs_japanese.sh
```

모의 실행(`DRY_RUN=1`)은 폴더를 생성하거나 시작 지연 시간만큼 기다리지 않습니다.

### 피드 갱신 안정성 및 회귀 테스트

피드 생성기는 숨김 임시 녹음 파일, 디렉터리, 날짜가 잘못된 파일을 제외합니다.
공개 오디오와 RSS는 임시 경로에 저장한 뒤 완성된 파일로 교체하므로,
복사·저장에 실패해도 해당 파일의 기존 공개본이 유지됩니다.

다음 명령은 임시 폴더에서 파일 수집과 저장 실패 시 기존 파일 보존을 검증합니다.

```sh
python3 -m unittest discover -s tests -v
```

이 변경은 이 폴더의 `scripts`에 적용됩니다. 홈 폴더에 별도로 복사해 실행하는
런타임을 사용한다면 그 스크립트에도 변경 사항을 반영해야 합니다.

## 시놀로지 작업 스케줄러 예시

- 일정: 매주 월요일~토요일
- 시간: 오전 5시 0분
- 사용자 정의 스크립트:

```sh
/bin/sh /volume1/music/radio/EBS/ebs_japan_radio/scripts/record_ebs_japanese.sh
```

## 30초 늦게 시작하고 싶을 때

기존 예시처럼 30초 뒤에 시작하고 19분 30초만 녹음하려면 아래처럼 실행하면 됩니다.

```sh
START_DELAY_SECONDS=30 DURATION_SECONDS=1170 /bin/sh /volume1/music/radio/EBS/ebs_japan_radio/scripts/record_ebs_japanese.sh
```

## 맥미니에서 자동 실행

맥미니를 항상 켜둘 예정이면 `cron`으로 돌리는 것이 가장 단순합니다.

- `ffmpeg`는 이미 `/opt/homebrew/bin/ffmpeg` 경로도 자동 인식하도록 되어 있습니다.
- 작업 등록 시간: 월요일~토요일 오전 5시 0분
- 로그 파일: `~/Library/Logs/ebs_japan_radio.record.log`

현재 폴더 경로 기준 크론 예시는 아래와 같습니다.

```sh
0 5 * * 1-6 RADIO_WORKSPACE=/path/to/ebs_japan_radio /bin/sh "/Users/YOUR_USER/Library/Application Support/EBSPrivatePodcast/record_ebs_japanese.sh" >> /Users/YOUR_USER/Library/Logs/ebs_japan_radio.record.log 2>&1
```

등록 방법:

```sh
crontab -e
```

열린 편집기에 위 한 줄을 넣고 저장하면 됩니다.

`cron`은 외장 디스크 위의 실행 파일을 직접 열지 않고, 홈 폴더에 복사된 런타임 스크립트를 호출합니다. 외장 디스크는 녹음 원본 저장 위치로만 씁니다.

외장 디스크가 부팅 직후 늦게 마운트될 수 있으면, 이 폴더를 맥 내부 디스크로 옮기거나 맥이 오전 5시 전에 항상 `/Volumes/Transcend`를 마운트한 상태인지 확인해 주세요.

## Private Podcast

녹음이 끝나면 `scripts/generate_feed.py`가 private podcast용 RSS를 자동으로 갱신합니다.

- 설정 파일: `podcast.env`
- feed 출력 폴더: `~/Library/Application Support/EBSPrivatePodcast/site/<PODCAST_TOKEN>/feed.xml`
- 오디오 출력 폴더: `~/Library/Application Support/EBSPrivatePodcast/site/<PODCAST_TOKEN>/episodes/`
- 현재 로컬 feed URL:

```text
http://YOUR-MAC.local:8081/YOUR_PODCAST_TOKEN/feed.xml
```

`podcast.env`의 `PODCAST_BASE_URL`을 나중에 공인 HTTPS 주소로 바꾸면, RSS 안의 오디오 URL도 함께 바뀝니다.

### 로컬 서버 실행

```sh
/bin/sh /path/to/ebs_japan_radio/scripts/start_server.sh
```

이 서버는 `HEAD`와 `byte-range` 요청을 처리하도록 따로 구현돼 있어서 팟캐스트 앱 재생용으로 쓸 수 있습니다.

서버가 읽는 공개용 정적 파일은 외장 디스크가 아니라 홈 폴더 아래로 복사됩니다.

### launchd 템플릿

`com.ebs.radio.server.plist`는 맥에서 서버를 계속 띄워둘 때 쓸 템플릿입니다.

예시 설치 경로:

```text
~/Library/LaunchAgents/com.ebs.radio.server.plist
```

로드 예시:

```sh
launchctl unload ~/Library/LaunchAgents/com.ebs.radio.server.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.ebs.radio.server.plist
```

### Apple Podcasts에 추가

- iPhone/iPad: `Podcasts` 앱 `보관함` > `...` > `URL로 쇼 팔로우`
- Mac: `Podcasts` 앱 메뉴 `파일` > `URL로 쇼 팔로우`

### 외부에서 들으려면

현재 기본값은 `http://YOUR-MAC.local:8081`이라 같은 네트워크에서만 쓸 수 있습니다.

어디서든 들으려면 아래 둘이 더 필요합니다.

1. 맥미니의 `8081` 서버를 인터넷에서 접근 가능하게 열기
2. `podcast.env`의 `PODCAST_BASE_URL`을 그 공인 `https://...` 주소로 바꾸기

가능한 방법 예시:

- 공유기 포트포워딩 + 도메인 + HTTPS 리버스프록시
- Cloudflare Tunnel 같은 터널 서비스

공인 주소가 준비되면 아래 명령으로 feed를 다시 만들면 됩니다.

```sh
python3 /path/to/ebs_japan_radio/scripts/generate_feed.py
```
