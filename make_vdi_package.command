#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if ! command -v git >/dev/null 2>&1; then
  echo "[ERROR] git command not found"
  exit 1
fi

BRANCH="$(git branch --show-current 2>/dev/null || echo unknown)"
SAFE_BRANCH="$(echo "$BRANCH" | tr '/ ' '__')"
SHA="$(git rev-parse --short HEAD)"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="$ROOT_DIR/vdi_packages"
OUT_FILE="$OUT_DIR/Preprocessing_${SAFE_BRANCH}_${SHA}_${STAMP}.zip"

mkdir -p "$OUT_DIR"

echo "[1/3] Creating VDI package from committed files"
echo "      branch: $BRANCH"
echo "      commit: $SHA"
echo "      output: $OUT_FILE"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "[WARN] Uncommitted tracked changes exist."
  echo "       This package uses HEAD only. Commit changes first if they must be included."
fi

echo "[2/3] Archiving tracked project files only"
git archive --format=zip --output "$OUT_FILE" HEAD

echo "[3/3] Verifying package"
if unzip -tq "$OUT_FILE" >/dev/null; then
  SIZE="$(du -h "$OUT_FILE" | awk '{print $1}')"
  echo "[OK] VDI package created: $OUT_FILE ($SIZE)"
  echo ""
  echo "VDI에서 압축 해제 후 실행:"
  echo "python3 -m preprocessing_portal.server --host 127.0.0.1 --port 8765 --index-dir opc_assets/tag_index"
  echo "브라우저: http://127.0.0.1:8765/Preprocessing.html"
else
  echo "[ERROR] zip verification failed: $OUT_FILE"
  exit 1
fi
