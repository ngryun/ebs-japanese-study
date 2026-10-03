#!/bin/sh

set -eu

STREAM_URL="${STREAM_URL:-https://ebsonair.ebs.co.kr/fmradiofamilypc/familypc1m/playlist.m3u8}"
DURATION_SECONDS="${DURATION_SECONDS:-1200}"
START_DELAY_SECONDS="${START_DELAY_SECONDS:-0}"
DAY_OVERRIDE="${DAY_OVERRIDE:-}"
DRY_RUN="${DRY_RUN:-0}"

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
DEFAULT_BASE_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd -P)
BASE_DIR="${RADIO_WORKSPACE:-$DEFAULT_BASE_DIR}"
PODCAST_MIRROR_BASE_DIR="${PODCAST_MIRROR_BASE_DIR:-}"
PODCAST_FEED_WORKSPACE="${PODCAST_FEED_WORKSPACE:-}"
ANALYZE_RECORDING="${ANALYZE_RECORDING:-1}"
BOUND_ICLOUD_ENABLED="${BOUND_ICLOUD_ENABLED:-1}"
APPLE_NOTES_ENABLED="${APPLE_NOTES_ENABLED:-1}"
DEFAULT_NOTES_HELPER_APP=""
if [ -n "${HOME:-}" ] && [ -d "$HOME/Applications/EBSStudyNotes.app" ]; then
  DEFAULT_NOTES_HELPER_APP="$HOME/Applications/EBSStudyNotes.app"
fi
NOTES_HELPER_APP="${NOTES_HELPER_APP:-$DEFAULT_NOTES_HELPER_APP}"
DEFAULT_BOUND_ICLOUD_DIR=""
if [ -n "${HOME:-}" ] && [ -d "$HOME/Library/Mobile Documents/com~apple~CloudDocs" ]; then
  DEFAULT_BOUND_ICLOUD_DIR="$HOME/Library/Mobile Documents/com~apple~CloudDocs/Bound Inbox"
fi
BOUND_ICLOUD_DIR="${BOUND_ICLOUD_DIR:-$DEFAULT_BOUND_ICLOUD_DIR}"

resolve_ffmpeg() {
  if [ -n "${FFMPEG_BIN:-}" ]; then
    printf '%s\n' "$FFMPEG_BIN"
    return 0
  fi

  if [ -x "/volume1/@appstore/ffmpeg/bin/ffmpeg" ]; then
    printf '%s\n' "/volume1/@appstore/ffmpeg/bin/ffmpeg"
    return 0
  fi

  if [ -x "/opt/homebrew/bin/ffmpeg" ]; then
    printf '%s\n' "/opt/homebrew/bin/ffmpeg"
    return 0
  fi

  if [ -x "/usr/local/bin/ffmpeg" ]; then
    printf '%s\n' "/usr/local/bin/ffmpeg"
    return 0
  fi

  if command -v ffmpeg >/dev/null 2>&1; then
    command -v ffmpeg
    return 0
  fi

  printf '%s\n' "ffmpeg executable not found. Set FFMPEG_BIN first." >&2
  exit 1
}

resolve_python() {
  if [ -n "${PYTHON_BIN:-}" ]; then
    printf '%s\n' "$PYTHON_BIN"
  elif [ -x "$BASE_DIR/.venv-analysis/bin/python3" ]; then
    printf '%s\n' "$BASE_DIR/.venv-analysis/bin/python3"
  elif [ -x /Library/Developer/CommandLineTools/usr/bin/python3 ]; then
    printf '%s\n' /Library/Developer/CommandLineTools/usr/bin/python3
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    return 1
  fi
}

publish_study_site() {
  STUDY_SCRIPT="${STUDY_SCRIPT:-$SCRIPT_DIR/generate_study_site.py}"
  if [ -n "$PYTHON_BIN" ] && [ -f "$STUDY_SCRIPT" ]; then
    if ! RADIO_WORKSPACE="$BASE_DIR" STUDY_WORKSPACE="$BASE_DIR" "$PYTHON_BIN" "$STUDY_SCRIPT"; then
      printf '%s\n' "Warning: study library update failed; recording is saved." >&2
    fi
  fi
}

WEEKDAY="${DAY_OVERRIDE:-$(date '+%u')}"

case "$WEEKDAY" in
  1|2|3)
    PROGRAM_DIR="초급일본어"
    PROGRAM_TITLE="초급일본어"
    ;;
  4|5|6)
    PROGRAM_DIR="중급일본어"
    PROGRAM_TITLE="중급일본어"
    ;;
  7)
    printf '%s\n' "No recording scheduled on Sunday."
    exit 0
    ;;
  *)
    printf '%s\n' "Unsupported weekday value: $WEEKDAY" >&2
    exit 1
    ;;
esac

TIMESTAMP=$(date '+%Y%m%d-%H%M')
DISPLAY_DATE=$(date '+%Y-%m-%d')
OUTPUT_DIR="$BASE_DIR/$PROGRAM_DIR"
OUTPUT_FILE="$OUTPUT_DIR/${TIMESTAMP}_EBS_${PROGRAM_TITLE}.m4a"
ARTWORK_SOURCE="${PODCAST_ARTWORK_SOURCE:-$BASE_DIR/artwork.png}"
MIRROR_OUTPUT_DIR=""
MIRROR_OUTPUT_FILE=""

if [ -n "$PODCAST_MIRROR_BASE_DIR" ]; then
  MIRROR_OUTPUT_DIR="$PODCAST_MIRROR_BASE_DIR/$PROGRAM_DIR"
  MIRROR_OUTPUT_FILE="$MIRROR_OUTPUT_DIR/${TIMESTAMP}_EBS_${PROGRAM_TITLE}.m4a"
fi

if [ "$DRY_RUN" = "1" ]; then
  printf '%s\n' "Program: $PROGRAM_DIR"
  printf '%s\n' "Output: $OUTPUT_FILE"
  if [ -n "$MIRROR_OUTPUT_FILE" ]; then
    printf '%s\n' "Mirror output: $MIRROR_OUTPUT_FILE"
  fi
  printf '%s\n' "Duration: $DURATION_SECONDS seconds"
  printf '%s\n' "Stream: $STREAM_URL"
  exit 0
fi

mkdir -p "$OUTPUT_DIR"
if [ -n "$MIRROR_OUTPUT_DIR" ]; then
  mkdir -p "$MIRROR_OUTPUT_DIR"
fi

if [ "$START_DELAY_SECONDS" -gt 0 ] 2>/dev/null; then
  sleep "$START_DELAY_SECONDS"
fi

FFMPEG_BIN=$(resolve_ffmpeg)
PYTHON_BIN=$(resolve_python || true)

# Keep the raw capture on the internal temporary volume. A failed cleanup of an
# external-disk file must not stop feed generation and study analysis.
RECORDING_TEMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/ebs-radio.XXXXXX")
RAW_OUTPUT_FILE="$RECORDING_TEMP_DIR/raw.recording.m4a"
TAGGED_OUTPUT_FILE="$RECORDING_TEMP_DIR/tagged.m4a"

# Preserve a completed raw recording if tagging or publication fails.
cleanup_recording() {
  if [ -f "$RAW_OUTPUT_FILE" ]; then
    printf '%s\n' "Unpublished recording retained at: $RAW_OUTPUT_FILE" >&2
  elif ! rm -rf "$RECORDING_TEMP_DIR"; then
    printf '%s\n' "Warning: temporary recording cleanup failed." >&2
  fi
}
trap cleanup_recording 0
trap 'exit 130' 1 2 15

"$FFMPEG_BIN" \
  -nostdin \
  -hide_banner \
  -loglevel error \
  -re \
  -i "$STREAM_URL" \
  -vn \
  -acodec copy \
  -t "$DURATION_SECONDS" \
  "$RAW_OUTPUT_FILE"

if [ -f "$ARTWORK_SOURCE" ]; then
  "$FFMPEG_BIN" \
    -nostdin \
    -hide_banner \
    -loglevel error \
    -y \
    -i "$RAW_OUTPUT_FILE" \
    -i "$ARTWORK_SOURCE" \
    -map 0:a:0 \
    -map 1:v:0 \
    -c:a copy \
    -c:v png \
    -disposition:v:0 attached_pic \
    -metadata "title=$DISPLAY_DATE $PROGRAM_TITLE" \
    -metadata "artist=EBS" \
    -metadata "album=EBS $PROGRAM_TITLE" \
    -metadata "album_artist=EBS" \
    -metadata "date=$DISPLAY_DATE" \
    -metadata "genre=Language Learning" \
    -metadata:s:v:0 "title=Cover" \
    -metadata:s:v:0 "comment=Cover (front)" \
    "$TAGGED_OUTPUT_FILE"
else
  "$FFMPEG_BIN" \
    -nostdin \
    -hide_banner \
    -loglevel error \
    -y \
    -i "$RAW_OUTPUT_FILE" \
    -map 0:a:0 \
    -c:a copy \
    -metadata "title=$DISPLAY_DATE $PROGRAM_TITLE" \
    -metadata "artist=EBS" \
    -metadata "album=EBS $PROGRAM_TITLE" \
    -metadata "album_artist=EBS" \
    -metadata "date=$DISPLAY_DATE" \
    -metadata "genre=Language Learning" \
    "$TAGGED_OUTPUT_FILE"
fi

if [ -e "$OUTPUT_FILE" ]; then
  printf '%s\n' "Recording already exists; refusing to overwrite: $OUTPUT_FILE" >&2
  exit 1
fi
# Stage on the destination volume, then publish the completed recording.
PUBLISH_TEMP_FILE="$OUTPUT_DIR/.${TIMESTAMP}_EBS_${PROGRAM_TITLE}.completed.m4a"
cp -p "$TAGGED_OUTPUT_FILE" "$PUBLISH_TEMP_FILE"
mv "$PUBLISH_TEMP_FILE" "$OUTPUT_FILE"
if ! rm -f "$RAW_OUTPUT_FILE"; then
  printf '%s\n' "Warning: temporary raw recording cleanup failed." >&2
fi

if [ -n "$MIRROR_OUTPUT_FILE" ]; then
  if ! cp -p "$OUTPUT_FILE" "$MIRROR_OUTPUT_FILE"; then
    printf '%s\n' "Warning: podcast mirror copy failed; recording is saved." >&2
  fi
fi

publish_study_site

# Put the completed, tagged M4A in an iCloud Drive inbox for manual import into
# Bound. A temporary iCloud failure must not invalidate the recording.
case "$BOUND_ICLOUD_ENABLED" in
  0|false|FALSE|no|NO)
    ;;
  *)
    if [ -n "$BOUND_ICLOUD_DIR" ]; then
      if ! mkdir -p "$BOUND_ICLOUD_DIR"; then
        printf '%s\n' "Warning: could not create Bound inbox: $BOUND_ICLOUD_DIR" >&2
      elif ! cp -p "$OUTPUT_FILE" "$BOUND_ICLOUD_DIR/$(basename "$OUTPUT_FILE")"; then
        printf '%s\n' "Warning: could not copy recording to Bound inbox: $OUTPUT_FILE" >&2
      else
        printf '%s\n' "Bound inbox copy: $BOUND_ICLOUD_DIR/$(basename "$OUTPUT_FILE")"
      fi
    fi
    ;;
esac

# Regenerate podcast RSS feed
if [ -n "$PYTHON_BIN" ]; then
  FEED_SCRIPT="${FEED_SCRIPT:-$SCRIPT_DIR/generate_feed.py}"
  FEED_WORKSPACE="${PODCAST_FEED_WORKSPACE:-$BASE_DIR}"
  if ! RADIO_WORKSPACE="$FEED_WORKSPACE" "$PYTHON_BIN" "$FEED_SCRIPT"; then
    printf '%s\n' "Warning: podcast feed update failed; continuing study analysis." >&2
  fi
fi

# Generate a local transcript and Japanese study guide after the recording and
# podcast feed are safely written. Analysis failures do not invalidate the
# completed recording.
case "$ANALYZE_RECORDING" in
  0|false|FALSE|no|NO)
    ;;
  *)
    ANALYSIS_SCRIPT="${ANALYSIS_SCRIPT:-$SCRIPT_DIR/analyze_japanese_episode.py}"
    ANALYSIS_SUCCEEDED=0
    if [ -f "$ANALYSIS_SCRIPT" ] && [ -n "$PYTHON_BIN" ]; then
      if [ -x /usr/bin/caffeinate ]; then
        if RADIO_WORKSPACE="$BASE_DIR" /usr/bin/caffeinate -i "$PYTHON_BIN" "$ANALYSIS_SCRIPT" "$OUTPUT_FILE"; then
          ANALYSIS_SUCCEEDED=1
        else
          printf '%s\n' "Warning: local Japanese analysis failed for $OUTPUT_FILE" >&2
        fi
      else
        if RADIO_WORKSPACE="$BASE_DIR" "$PYTHON_BIN" "$ANALYSIS_SCRIPT" "$OUTPUT_FILE"; then
          ANALYSIS_SUCCEEDED=1
        else
          printf '%s\n' "Warning: local Japanese analysis failed for $OUTPUT_FILE" >&2
        fi
      fi
    else
      printf '%s\n' "Warning: analysis script not found: $ANALYSIS_SCRIPT" >&2
    fi

    # The signed helper owns the macOS Automation permission. Launch it only
    # after analysis has produced the latest Apple Notes HTML files.
    if [ "$ANALYSIS_SUCCEEDED" = "1" ]; then
      case "$APPLE_NOTES_ENABLED" in
        0|false|FALSE|no|NO)
          ;;
        *)
          if [ -n "$NOTES_HELPER_APP" ] && [ -d "$NOTES_HELPER_APP" ] && [ -x /usr/bin/open ]; then
            if ! /usr/bin/open -gj -n "$NOTES_HELPER_APP"; then
              printf '%s\n' "Warning: could not launch Apple Notes helper: $NOTES_HELPER_APP" >&2
            fi
          fi
          ;;
      esac
    fi
    ;;
esac
