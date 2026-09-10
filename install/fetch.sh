#!/usr/bin/env bash
# Fetch the shared ADW contract into .claude/adw/cache/.
# Idempotent, fast, and safe to run at the start of every ADW phase.
# Override the source with ADW_REPO / ADW_REF.
set -u

REPO="${ADW_REPO:-https://github.com/humbertouchiyama/adw.git}"
REF="${ADW_REF:-main}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE="$DIR/cache"

stamp() { git -C "$CACHE" log -1 --format='%h'; }

if [ -d "$CACHE/.git" ]; then
  if git -C "$CACHE" fetch --quiet --depth 1 origin "$REF" 2>/dev/null \
     && git -C "$CACHE" reset --hard --quiet FETCH_HEAD; then
    echo "adw contract $(stamp)  ($REF, fetched)"
    exit 0
  fi
  echo "adw fetch FAILED — using cache from $(git -C "$CACHE" log -1 --format='%h, %cr')" >&2
  echo "adw contract $(stamp)  ($REF, CACHED — may be stale)"
  exit 0
fi

if git clone --quiet --depth 1 --branch "$REF" "$REPO" "$CACHE" 2>/dev/null; then
  echo "adw contract $(stamp)  ($REF, cloned)"
  exit 0
fi

echo "adw fetch FAILED and no cache exists at $CACHE" >&2
echo "STOP. Do not run ADW from memory. Fix the network or set ADW_REPO, then retry." >&2
exit 1
