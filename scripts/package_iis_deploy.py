#!/usr/bin/env python3
"""Build a minimal IIS static deployment package for PreprocessingWeb."""

from __future__ import annotations

import argparse
import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILES = [
    "Preprocessing.html",
    "MANUAL.html",
    "program_intro.html",
    "deploy/iis/web.config",
    "assets/vendor/chart.umd.min.js",
    "assets/vendor/xlsx.full.min.js",
    "assets/Gemini_Generated_Image_kal48vkal48vkal4.jpeg",
    "assets/intro-overview-540.mp4",
    "assets/intro-workflow-540.mp4",
]
DEFAULT_DIRS = [
    "manual_assets/screenshots",
]
BLOCKED_PARTS = {".git", ".omx", ".playwright-mcp", "__pycache__", ".ruff_cache"}
BLOCKED_SUFFIXES = {".py", ".pyc", ".pyo", ".zip", ".bat", ".command", ".md", ".json"}


def should_copy(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in BLOCKED_PARTS for part in rel.parts):
        return False
    if path.suffix.lower() in BLOCKED_SUFFIXES:
        return False
    return path.is_file()


def copy_file(src: Path, dest_root: Path, rel: Path) -> None:
    dest = dest_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Package PreprocessingWeb for IIS")
    parser.add_argument("--output-dir", default="dist_iis")
    parser.add_argument("--name", default=None)
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    package_name = args.name or f"PreprocessingWeb_iis_{stamp}"
    output_dir = ROOT / args.output_dir
    stage = output_dir / package_name
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    copied: list[Path] = []
    for rel_text in DEFAULT_FILES:
        src = ROOT / rel_text
        if not src.exists():
            raise FileNotFoundError(src)
        rel = Path("web.config") if rel_text == "deploy/iis/web.config" else Path(rel_text)
        copy_file(src, stage, rel)
        copied.append(rel)

    for dir_text in DEFAULT_DIRS:
        src_dir = ROOT / dir_text
        if not src_dir.exists():
            continue
        for src in src_dir.rglob("*"):
            if should_copy(src):
                rel = src.relative_to(ROOT)
                copy_file(src, stage, rel)
                copied.append(rel)

    manifest = stage / "DEPLOY_MANIFEST.txt"
    manifest.write_text(
        "PreprocessingWeb IIS deployment package\n"
        f"Built: {datetime.now().isoformat(timespec='seconds')}\n"
        "Target IIS path: C:\\PreprocessingWeb\n"
        "Target binding: http://192.9.88.241:8511/\n\n"
        "Files:\n"
        + "\n".join(f"- {rel.as_posix()}" for rel in sorted(copied, key=lambda p: p.as_posix()))
        + "\n",
        encoding="utf-8",
    )

    zip_path = output_dir / f"{package_name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as zf:
        for file in stage.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(stage))

    checksum_path = zip_path.with_suffix(".zip.sha256")
    checksum_path.write_text(f"{sha256(zip_path)}  {zip_path.name}\n", encoding="utf-8")
    print(zip_path)
    print(checksum_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
