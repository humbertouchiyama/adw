#!/usr/bin/env bash
# Fetch the shared ADW contract into .claude/adw/cache/.
#
# Exit codes are the contract with the caller (see install/stubs/*.md):
#   0  fetched from origin — the cache is current
#   2  fetch FAILED (or the fetch lock stayed held for 60 s), an existing cache was reused —
#      age unknown, must be reported
#   1  no usable contract — the caller must stop
#
# Everything under cache/ is discarded on the next successful fetch: `reset --hard`.
# Never keep local edits there. To run against a different source or branch, set
# ADW_REPO / ADW_REF; both are honoured on every run, not only the first.
set -u

REPO="${ADW_REPO:-https://github.com/humbertouchiyama/adw.git}"
REF="${ADW_REF:-main}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE="$DIR/cache"
LOCK="$DIR/.fetch.lock"

stamp() { git -C "$CACHE" log -1 --format='%h' 2>/dev/null; }

# The loader is the one part of ADW that is still a COPY. This script and the stubs in
# .claude/commands/ are tracked files mirroring install/ upstream, so they drift exactly the way
# the contract used to — and nothing else in the system will ever tell you. AXCMedApp ran a
# revision-old loader for a day: its stubs did not know exit 2 existed, so an unverified cache
# would have run as verified, and a human code review is what caught it.
# Report only. Never rewrite a tracked file behind the author's back.
loader_drift() {
  up="$CACHE/install"; cmds="$(cd "$DIR/.." 2>/dev/null && pwd)/commands"; drift=""; missing=""; have=""
  [ -d "$up" ] || return 0
  cmp -s "$DIR/fetch.sh" "$up/fetch.sh" 2>/dev/null || drift="fetch.sh"
  for s in "$up"/stubs/*.md; do
    [ -f "$s" ] || continue
    n=$(basename "$s")
    [ -f "$cmds/$n" ] || { missing="$missing commands/$n(missing)"; continue; }
    have=1
    cmp -s "$cmds/$n" "$s" 2>/dev/null || drift="$drift commands/$n"
  done
  # A repo with no stub at all is mid-install (the README runs this before the cp): say nothing.
  [ -z "$have" ] || drift="$drift$missing"
  [ -n "$drift" ] || return 0
  echo "adw: the LOADER is behind $REPO —$drift" >&2
  echo "adw: these are copies, not fetched, so nothing else reports this. Diff before overwriting:" >&2
  echo "adw:   cp '$up/fetch.sh' '$DIR/fetch.sh' && cp '$up'/stubs/*.md '$cmds'/" >&2
}

# Serialize concurrent runs in the same repo: two sessions resetting one cache can
# leave a reader mid-checkout. mkdir is atomic on every filesystem that matters.
# A lock older than 10 minutes whose owner is gone was left by a killed run: remove it. The owner's
# pid is in the lock, so a fetch that is only slow keeps its lock.
if [ -d "$LOCK" ] && [ -n "$(find "$LOCK" -maxdepth 0 -mmin +10 2>/dev/null)" ]; then
  owner="$(cat "$LOCK/pid" 2>/dev/null)"
  if [ -z "$owner" ] || ! kill -0 "$owner" 2>/dev/null; then
    rm -f "$LOCK/pid"
    rmdir "$LOCK" 2>/dev/null && echo "adw: removed a stale fetch lock (older than 10 min, owner gone): $LOCK" >&2
  fi
fi
locked=""
for _ in $(seq 1 60); do
  if mkdir "$LOCK" 2>/dev/null; then
    echo "$$" > "$LOCK/pid"
    trap 'rm -f "$LOCK/pid"; rmdir "$LOCK" 2>/dev/null || true' EXIT INT TERM
    locked=1
    break
  fi
  sleep 1
done
# Still held after 60 s: never fetch unlocked, which is the race the lock exists for. Say so, and
# reuse the cache as an unverified one (exit 2), or stop when there is none.
if [ -z "$locked" ]; then
  # GNU stat first: on GNU, `stat -f` is file-system mode and prints no mtime. Anything not a number
  # is an unknown age, never an arithmetic error that would end the script before its exit code.
  mtime="$(stat -c %Y "$LOCK" 2>/dev/null || stat -f %m "$LOCK" 2>/dev/null)"
  case "$mtime" in
    ''|*[!0-9]*) held="age unknown" ;;
    *) held="$(( $(date +%s) - mtime ))s old" ;;
  esac
  echo "adw: fetch lock held by another run (or stale: $held) at $LOCK" >&2
  if [ -d "$CACHE/.git" ]; then
    echo "adw contract $(stamp)  ($REF, CACHED — NOT VERIFIED)"
    exit 2
  fi
  echo "STOP. No cache to fall back on. If no other run is fetching, remove the lock and retry:  rmdir '$LOCK'" >&2
  exit 1
fi

if [ -d "$CACHE" ] && [ ! -d "$CACHE/.git" ]; then
  echo "adw: $CACHE exists but is not a git clone." >&2
  echo "STOP. Remove it and retry:  rm -rf '$CACHE'" >&2
  exit 1
fi

if [ -d "$CACHE/.git" ]; then
  # set-url every run: without it a renamed, moved or compromised source can never be
  # overridden once a cache exists, because `fetch origin` ignores $REPO entirely.
  git -C "$CACHE" remote set-url origin "$REPO" 2>/dev/null
  if git -C "$CACHE" fetch --quiet --depth 1 origin "$REF" 2>/dev/null \
     && git -C "$CACHE" reset --hard --quiet FETCH_HEAD; then
    loader_drift
    echo "adw contract $(stamp)  ($REF, fetched)"
    exit 0
  fi
  echo "adw: fetch from $REPO ($REF) FAILED — reusing the cache at $(git -C "$CACHE" log -1 --format='%h, %cr')" >&2
  echo "adw contract $(stamp)  ($REF, CACHED — NOT VERIFIED)"
  exit 2
fi

if git clone --quiet --depth 1 --branch "$REF" "$REPO" "$CACHE" 2>/dev/null; then
  loader_drift
  echo "adw contract $(stamp)  ($REF, cloned)"
  exit 0
fi
rmdir "$CACHE" 2>/dev/null || true

echo "adw: clone of $REPO ($REF) failed and there is no cache at $CACHE" >&2
echo "STOP. Do not run ADW from memory. Fix the network, or set ADW_REPO / ADW_REF, then retry." >&2
exit 1
