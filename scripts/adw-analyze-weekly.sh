#!/usr/bin/env bash
# The weekly ADW analysis (docs/specs/2026-10-27-adw-self-improving-loop-design.md §5.5).
#
# Every step is deterministic shell except the critical pass, which runs `claude -p` with a fixed tool
# list, no Bash and no push: an unattended `claude -p` cannot answer a permission prompt, so anything
# that must happen is done here. Any failed step opens an issue in the reports repo naming the step.
#
# Usage: adw-analyze-weekly.sh [run | --dry-run | --install | --uninstall]
#   run         refresh the adw worktree, analyze, critical pass, leak scan, commit, push, open the issue
#   --dry-run   the same without push or issue (prints them)
#   --install   write the launchd agent (Mondays 07:00 local) and load it; --uninstall removes it
set -euo pipefail

ADW_ANALYSIS_DIR="${ADW_ANALYSIS_DIR:-$HOME/dev/Projects/adw-analysis}"
ADW_REPO="${ADW_REPO:-$HOME/dev/Projects/adw}"
ADW_WEEKLY_WORKTREE="${ADW_WEEKLY_WORKTREE:-$HOME/dev/Projects/adw-weekly}"
ADW_WEEKLY_PATH="${ADW_WEEKLY_PATH:-/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin}"
export PATH="$ADW_WEEKLY_PATH" ADW_ANALYSIS_DIR ADW_REPO ADW_WEEKLY_WORKTREE ADW_WEEKLY_PATH

LABEL=dev.adw.analyze-weekly
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/adw-analyze-weekly.log"
WT="$ADW_WEEKLY_WORKTREE"
R="$ADW_ANALYSIS_DIR"
MODE="${1:-run}"
DRY=0
D="$(date -u +%Y-%m-%d)"
STEP=start

slug() {
  [ -n "${ADW_ANALYSIS_SLUG:-}" ] && { echo "$ADW_ANALYSIS_SLUG"; return; }
  git -C "$R" remote get-url origin | sed -E 's#^.*github\.com[:/]##; s#\.git$##'
}

on_exit() {
  local code=$?
  [ "$STEP" = done ] && return
  local title="ADW analysis $D failed at $STEP"
  if [ "$DRY" = 1 ]; then
    echo "would open issue: $title"
  else
    gh issue create -R "$(slug)" --title "$title" --body "exit $code; the log is $LOG on the analysis machine." >/dev/null || true
  fi
  exit "$code"
}

# Replace the single line $2 in file $1 with the contents of file $3, or with the text $3 when it is not a file.
replace_line() {
  local f=$1 line=$2 with=$3
  if [ -f "$with" ]; then
    awk -v L="$line" -v W="$with" '$0 == L { while ((getline x < W) > 0) print x; next } { print }' "$f" > "$f.tmp"
  else
    awk -v L="$line" -v W="$with" '$0 == L { print W; next } { print }' "$f" > "$f.tmp"
  fi
  mv "$f.tmp" "$f"
}

worktree() {
  if [ ! -d "$WT" ]; then
    git -C "$ADW_REPO" fetch -q origin
    git -C "$ADW_REPO" worktree add -q --detach "$WT" origin/main
  fi
  git -C "$WT" fetch -q origin
  git -C "$WT" checkout -q --detach origin/main
}

run() {
  trap on_exit EXIT
  STEP=worktree
  worktree
  if [ -z "${ADW_WEEKLY_REEXEC:-}" ]; then
    export ADW_WEEKLY_REEXEC=1
    trap - EXIT
    exec bash "$WT/scripts/adw-analyze-weekly.sh" "$MODE"
  fi

  STEP="reports pull"
  git -C "$R" pull -q --ff-only origin "$(git -C "$R" rev-parse --abbrev-ref HEAD)"

  STEP=reader
  python3 "$WT/scripts/adw-analyze.py" --reports "$R" --adw "$WT"

  STEP="critical pass"
  local prompt findings="$R/$D/critical-pass.md"
  prompt="$(sed -e "s#{DATE}#$D#g" "$WT/.claude/skills/adw-analyze/critical-pass.md")"
  (cd "$R" && claude -p "$prompt" --model sonnet --permission-mode dontAsk --add-dir "$HOME/.claude/projects" \
     --allowedTools Read Grep Glob "Edit($D/critical-pass.md)" --disallowedTools Bash WebFetch WebSearch Agent) \
     >/dev/null 2>&1 || true
  if [ -s "$findings" ]; then
    replace_line "$R/$D/report.md" "critical pass: pending" "$findings"
    rm -f "$findings"
  else
    rm -f "$findings"
    replace_line "$R/$D/report.md" "critical pass: pending" "critical pass: missing"
  fi

  STEP="leak scan"
  local rc=0
  python3 "$WT/scripts/adw-analyze.py" --reports "$R" --scan --date "$D" || rc=$?
  if [ "$rc" -ne 0 ]; then
    [ "$rc" -eq 4 ] && rm -rf "${R:?}/$D"
    exit 1
  fi
  replace_line "$R/$D/issue.md" "leak scan: pending" "leak scan: clean"

  STEP=commit
  git -C "$R" add -- "$D"
  git -C "$R" commit -q -m "report $D"
  if [ "$DRY" = 1 ]; then
    echo "would push $R to origin"
    echo "would open issue: ADW analysis $D"
  else
    STEP=push
    git -C "$R" push -q origin HEAD
    STEP=issue
    gh issue create -R "$(slug)" --title "ADW analysis $D" --body-file "$R/$D/issue.md"
  fi
  STEP=done
}

install() {
  mkdir -p "$(dirname "$PLIST")" "$(dirname "$LOG")"
  worktree
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>$LABEL</string>
	<key>ProgramArguments</key>
	<array>
		<string>/bin/bash</string>
		<string>$WT/scripts/adw-analyze-weekly.sh</string>
		<string>run</string>
	</array>
	<key>StartCalendarInterval</key>
	<dict>
		<key>Weekday</key>
		<integer>1</integer>
		<key>Hour</key>
		<integer>7</integer>
		<key>Minute</key>
		<integer>0</integer>
	</dict>
	<key>StandardOutPath</key>
	<string>$LOG</string>
	<key>StandardErrorPath</key>
	<string>$LOG</string>
	<key>EnvironmentVariables</key>
	<dict>
		<key>ADW_ANALYSIS_DIR</key>
		<string>$ADW_ANALYSIS_DIR</string>
		<key>ADW_REPO</key>
		<string>$ADW_REPO</string>
		<key>ADW_WEEKLY_WORKTREE</key>
		<string>$ADW_WEEKLY_WORKTREE</string>
		<key>ADW_WEEKLY_PATH</key>
		<string>$ADW_WEEKLY_PATH</string>
	</dict>
</dict>
</plist>
EOF
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  echo "installed $PLIST; prove it with: launchctl kickstart -k gui/$(id -u)/$LABEL"
}

uninstall() {
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "removed $PLIST"
}

case "$MODE" in
  run) run ;;
  --dry-run) DRY=1; run ;;
  --install) install ;;
  --uninstall) uninstall ;;
  *) echo "usage: adw-analyze-weekly.sh [run | --dry-run | --install | --uninstall]" >&2; exit 2 ;;
esac
