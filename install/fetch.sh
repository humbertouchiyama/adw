#!/usr/bin/env bash
# Fetch the shared ADW contract into .claude/adw/cache/.
#
# Exit codes are the contract with the caller (see install/stubs/*.md):
#   0  fetched from origin — the cache is current
#   2  fetch FAILED, an existing cache was reused — age unknown, must be reported
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
  up="$CACHE/install"; cmds="$(cd "$DIR/.." 2>/dev/null && pwd)/commands"; drift=""
  [ -d "$up" ] || return 0
  cmp -s "$DIR/fetch.sh" "$up/fetch.sh" 2>/dev/null || drift="fetch.sh"
  for s in "$up"/stubs/*.md; do
    [ -f "$s" ] || continue
    n=$(basename "$s")
    [ -f "$cmds/$n" ] || continue
    cmp -s "$cmds/$n" "$s" 2>/dev/null || drift="$drift commands/$n"
  done
  [ -n "$drift" ] || return 0
  echo "adw: the LOADER is behind $REPO —$drift" >&2
  echo "adw: these are copies, not fetched, so nothing else reports this. Diff before overwriting:" >&2
  echo "adw:   cp '$up/fetch.sh' '$DIR/fetch.sh' && cp '$up'/stubs/*.md '$cmds'/" >&2
}

# Serialize concurrent runs in the same repo: two sessions resetting one cache can
# leave a reader mid-checkout. mkdir is atomic on every filesystem that matters.
for _ in $(seq 1 60); do
  if mkdir "$LOCK" 2>/dev/null; then
    trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT INT TERM
    break
  fi
  sleep 1
done

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
