#!/bin/sh
# Build the Reminders alert helper as a background app with its own
# Automation permission. Rebuilding changes its ad-hoc signature, so macOS
# asks again for permission to control Reminders on the next alert.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
APP="${ALERT_HELPER_APP:-$HOME/Applications/EBSStudyAlert.app}"
PLIST="$APP/Contents/Info.plist"

mkdir -p "$(dirname -- "$APP")"
rm -rf "$APP"
/usr/bin/osacompile -o "$APP" "$SCRIPT_DIR/ebs_alert_helper.applescript"
/usr/bin/plutil -replace CFBundleIdentifier -string com.ngryun.ebsstudyalert "$PLIST"
/usr/bin/plutil -replace CFBundleName -string EBSStudyAlert "$PLIST"
/usr/bin/plutil -replace LSUIElement -bool true "$PLIST"
/usr/bin/plutil -replace NSAppleEventsUsageDescription \
  -string "EBS 일본어 자동 갱신이 실패하면 미리 알림으로 알려 줍니다." "$PLIST"
/usr/bin/plutil -replace NSRemindersUsageDescription \
  -string "EBS 일본어 자동 갱신 실패 알림을 미리 알림에 추가합니다." "$PLIST"
/usr/bin/codesign --force --deep --sign - "$APP"
printf '%s\n' "Alert helper built: $APP"
