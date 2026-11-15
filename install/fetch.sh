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

# The loader is the one part of ADW that is still a COPY: this script and the stubs in
# .claude/commands/ mirror install/ upstream, so they drift, and a new command (adw-dispatch,
# adw) never appears in a repo unless someone copies its stub. AXCMedApp also ran a revision-old
# loader for a day: its stubs did not know exit 2 existed.
#
# So every successful fetch syncs the STUBS (never fetch.sh itself, which is running):
#   - missing stub            -> installed
#   - stub we installed before and nobody edited -> updated (stubs.manifest records its hash)
#   - any other difference    -> a customised file: left alone, reported
# fetch.sh itself is only reported when it differs.
sync_loader() {
  up="$CACHE/install"; cmds="$(cd "$DIR/.." 2>/dev/null && pwd)/commands"; man="$DIR/stubs.manifest"
  [ -d "$up/stubs" ] || return 0
  mkdir -p "$cmds"; drift=""; added=""; updated=""; newman=""
  cmp -s "$DIR/fetch.sh" "$up/fetch.sh" 2>/dev/null || drift="fetch.sh"
  for s in "$up"/stubs/*.md; do
    [ -f "$s" ] || continue
    n=$(basename "$s"); h=$(git hash-object "$s"); dest="$cmds/$n"
    if [ ! -f "$dest" ]; then
      cp "$s" "$dest" && { added="$added $n"; newman="$newman$n $h
"; }
    elif cmp -s "$dest" "$s"; then
      newman="$newman$n $h
"
    else
      prev=$(awk -v n="$n" '$1==n{print $2}' "$man" 2>/dev/null)
      if [ -n "$prev" ] && [ "$prev" = "$(git hash-object "$dest")" ]; then
        cp "$s" "$dest" && { updated="$updated $n"; newman="$newman$n $h
"; }
      else
        drift="$drift commands/$n"
        [ -z "$prev" ] || newman="$newman$n $prev
"
      fi
    fi
  done
  printf '%s' "$newman" > "$man"
  [ -z "$added" ] || echo "adw: installed stubs into $cmds:$added" >&2
  [ -z "$updated" ] || echo "adw: updated stubs in $cmds:$updated" >&2
  [ -n "$drift" ] || return 0
  echo "adw: NOT synced (edited locally, or fetch.sh itself) —$drift" >&2
  echo "adw: diff against '$up' before overwriting; a customised stub is yours to keep or replace." >&2
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
    sync_loader
    echo "adw contract $(stamp)  ($REF, fetched)"
    exit 0
  fi
  echo "adw: fetch from $REPO ($REF) FAILED — reusing the cache at $(git -C "$CACHE" log -1 --format='%h, %cr')" >&2
  echo "adw contract $(stamp)  ($REF, CACHED — NOT VERIFIED)"
  exit 2
fi

if git clone --quiet --depth 1 --branch "$REF" "$REPO" "$CACHE" 2>/dev/null; then
  sync_loader
  echo "adw contract $(stamp)  ($REF, cloned)"
  exit 0
fi
rmdir "$CACHE" 2>/dev/null || true

echo "adw: clone of $REPO ($REF) failed and there is no cache at $CACHE" >&2
echo "STOP. Do not run ADW from memory. Fix the network, or set ADW_REPO / ADW_REF, then retry." >&2
exit 1
