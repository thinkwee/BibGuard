#!/usr/bin/env bash
# Install a git pre-commit hook that runs BibGuard in --quick mode whenever
# the staged changes touch .bib or .tex files.
#
# Usage (run from the repo root that contains your paper, NOT BibGuard's repo):
#   bash /path/to/BibGuard/scripts/install-hook.sh
#
# Skip the hook for one commit:  git commit --no-verify
set -euo pipefail

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "Error: not inside a git repo." >&2
  exit 1
fi

HOOK_DIR="$(git rev-parse --git-dir)/hooks"
HOOK="$HOOK_DIR/pre-commit"

# Locate BibGuard's main.py — we assume this script lives in BibGuard/scripts/.
BIBGUARD_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MAIN_PY="$BIBGUARD_DIR/main.py"
if [[ ! -f "$MAIN_PY" ]]; then
  echo "Error: cannot locate BibGuard main.py at $MAIN_PY" >&2
  exit 1
fi

mkdir -p "$HOOK_DIR"

if [[ -f "$HOOK" ]]; then
  echo "A pre-commit hook already exists at $HOOK"
  echo "Backing it up to $HOOK.bibguard-backup"
  mv "$HOOK" "$HOOK.bibguard-backup"
fi

cat >"$HOOK" <<EOF
#!/usr/bin/env bash
# BibGuard pre-commit hook (auto-generated)
# Runs only if staged files include .tex or .bib.
set -e

if git diff --cached --name-only --diff-filter=ACM | grep -qE '\.(tex|bib)$'; then
  echo "[BibGuard] Running quick checks on staged paper sources…"
  python "$MAIN_PY" --quick || {
    echo
    echo "[BibGuard] Issues found. Fix or run:  git commit --no-verify  to skip."
    exit 1
  }
fi
EOF

chmod +x "$HOOK"
echo "Installed BibGuard pre-commit hook at: $HOOK"
echo "It will run only when staged files include .tex or .bib."
