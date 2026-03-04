#!/usr/bin/env bash
set -euo pipefail

# Deterministic repo census fallback for environments without ~/.pi/agent/scripts/preflight-repo-census.sh
# Usage: ./scripts/preflight-repo-census.sh [scope]

SCOPE="${1:-.}"

if [ ! -d "$SCOPE" ]; then
  echo "error: scope not found: $SCOPE" >&2
  exit 1
fi

mapfile -t REPOS < <(find "$SCOPE" -mindepth 1 -maxdepth 5 -type d -name .git -printf '%h\n' | sort)

if [ ${#REPOS[@]} -eq 0 ]; then
  # Handle current repo edge case where .git is at scope root and excluded by mindepth
  if [ -d "$SCOPE/.git" ]; then
    REPOS=("$SCOPE")
  fi
fi

echo "scope: $SCOPE"
echo "repos: ${#REPOS[@]}"
echo
printf '%-45s %-28s %-8s\n' "REPO" "BRANCH" "DIRTY"
printf '%-45s %-28s %-8s\n' "----" "------" "-----"

for repo in "${REPOS[@]}"; do
  if ! git -C "$repo" rev-parse --git-dir >/dev/null 2>&1; then
    printf '%-45s %-28s %-8s\n' "$repo" "(not-git)" "n/a"
    continue
  fi

  branch="$(git -C "$repo" branch --show-current 2>/dev/null || true)"
  if [ -z "$branch" ]; then
    branch="(detached)"
  fi

  dirty_count="$(git -C "$repo" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
  dirty="clean"
  if [ "${dirty_count:-0}" -gt 0 ]; then
    dirty="dirty:$dirty_count"
  fi

  printf '%-45s %-28s %-8s\n' "$repo" "$branch" "$dirty"
done
