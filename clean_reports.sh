#!/usr/bin/env zsh
# Clean up generated retirement report PDFs
# Usage:
#   ./clean_reports.sh           # delete all retirement_report_*.pdf in current dir
#   ./clean_reports.sh --dry-run # list files that would be deleted
#   ./clean_reports.sh --path /some/dir  # target directory
#   ./clean_reports.sh --help    # show help

set -euo pipefail

function usage() {
  echo "Clean up retirement_report_*.pdf files"
  echo ""
  echo "Options:"
  echo "  --dry-run       Print files to delete without deleting"
  echo "  --path <dir>    Directory to clean (default: current)"
  echo "  --help          Show this help"
}

DRY_RUN=false
TARGET_DIR="$PWD"

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --path)
      [[ $# -lt 2 ]] && { echo "Error: --path requires a directory"; exit 1; }
      TARGET_DIR="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "Error: Target directory not found: $TARGET_DIR" >&2
  exit 1
fi

# Find matching PDFs
typeset -a files
files=($(find "$TARGET_DIR" -maxdepth 1 -type f -name 'retirement_report_*.pdf'))

if [[ ${#files[@]} -eq 0 ]]; then
  echo "No retirement_report_*.pdf files found in $TARGET_DIR"
  exit 0
fi

if $DRY_RUN; then
  echo "[DRY RUN] Would delete ${#files[@]} files:"
  printf '%s\n' $files
  exit 0
fi

# Confirm deletion interactively unless NO_CONFIRM is set
if [[ -z "${NO_CONFIRM:-}" ]]; then
  echo "About to delete ${#files[@]} files in $TARGET_DIR:"
  printf '%s\n' $files
  read -q "REPLY?Proceed? [y/N] " || { echo "\nAborted."; exit 1; }
  echo
fi

# Delete files
for f in $files; do
  rm -f "$f"
  echo "Deleted: $f"
done

echo "Cleanup complete."
