"""Local Excel-backed cache for OPC tag history.

Stores frequently-used tags as plain Excel files under ``data_cache/`` so
long historical reads do not have to hit OPC every time. The on-disk
format is intentionally simple so the user can open, paste, and edit
each file directly in Excel:

* One file per tag: ``data_cache/<tag>.xlsx``
* One sheet per year: ``2020``, ``2021``, ...
* Columns: ``A=datetime``, ``B=value``, ``C=quality`` (quality optional)
* Header row only; no formulas, no merged cells, no metadata columns.

``_index.xlsx`` is a catalogue of available tags and their covered
ranges. It is regenerated from the tag files (mtime-based) so manual
edits to tag files propagate automatically.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

DATETIME_COLUMN = "datetime"
VALUE_COLUMN = "value"
QUALITY_COLUMN = "quality"
DEFAULT_QUALITY = "Good"
INDEX_FILENAME = "_index.xlsx"
INDEX_COLUMNS = (
    "tag",
    "first_time",
    "last_time",
    "row_count",
    "years",
    "file_mtime",
)

_TAG_FILENAME_PATTERN = re.compile(r"[^\w.\-]+")


def _safe_filename(tag_name: str) -> str:
    """Convert an OPC tag name into a filesystem-safe filename stem."""
    cleaned = _TAG_FILENAME_PATTERN.sub("_", tag_name.strip())
    return cleaned or "_unnamed"


@dataclass(frozen=True)
class TagCoverage:
    """Time range and row count available in the cache for a tag."""

    tag: str
    first_time: datetime
    last_time: datetime
    row_count: int

    def covers(self, start: datetime, end: datetime) -> bool:
        return self.first_time <= start and end <= self.last_time


class TagCache:
    """Read/write Excel-backed OPC tag history."""

    def __init__(self, cache_dir: str | Path) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.cache_dir / INDEX_FILENAME

    # ── Path helpers ────────────────────────────────────────────────

    def tag_path(self, tag_name: str) -> Path:
        return self.cache_dir / f"{_safe_filename(tag_name)}.xlsx"

    def has_tag(self, tag_name: str) -> bool:
        return self.tag_path(tag_name).exists()

    def list_tag_files(self) -> list[Path]:
        return sorted(
            p
            for p in self.cache_dir.glob("*.xlsx")
            if p.name != INDEX_FILENAME and not p.name.startswith("~$")
        )

    # ── Reads ───────────────────────────────────────────────────────

    def get_coverage(self, tag_name: str) -> TagCoverage | None:
        """Return cached time range for a tag, or None if absent."""
        path = self.tag_path(tag_name)
        if not path.exists():
            return None
        df = self._read_all_sheets(path)
        if df.empty:
            return None
        return TagCoverage(
            tag=tag_name,
            first_time=df[DATETIME_COLUMN].iloc[0].to_pydatetime(),
            last_time=df[DATETIME_COLUMN].iloc[-1].to_pydatetime(),
            row_count=len(df),
        )

    def has_range(self, tag_name: str, start: datetime, end: datetime) -> bool:
        """True if the cache fully covers ``[start, end]``."""
        coverage = self.get_coverage(tag_name)
        return coverage is not None and coverage.covers(start, end)

    def load_range(
        self, tag_name: str, start: datetime, end: datetime
    ) -> pd.DataFrame:
        """Load rows in ``[start, end]`` from the relevant year sheets."""
        path = self.tag_path(tag_name)
        if not path.exists():
            raise FileNotFoundError(f"캐시에 태그가 없습니다: {tag_name}")

        years = range(start.year, end.year + 1)
        frames: list[pd.DataFrame] = []
        with pd.ExcelFile(path) as xl:
            available = {sheet for sheet in xl.sheet_names}
            for year in years:
                sheet = str(year)
                if sheet not in available:
                    continue
                frames.append(self._read_sheet(xl, sheet))

        if not frames:
            return self._empty_frame()

        df = pd.concat(frames, ignore_index=True)
        df = self._normalize_frame(df)
        mask = (df[DATETIME_COLUMN] >= pd.Timestamp(start)) & (
            df[DATETIME_COLUMN] <= pd.Timestamp(end)
        )
        return df.loc[mask].reset_index(drop=True)

    # ── Writes ──────────────────────────────────────────────────────

    def save(self, tag_name: str, df: pd.DataFrame) -> int:
        """Merge ``df`` into the tag file, splitting by year.

        Returns the total row count after merge. Existing rows for the
        same timestamp are replaced (last write wins).
        """
        incoming = self._normalize_frame(df.copy())
        if incoming.empty:
            return 0

        path = self.tag_path(tag_name)
        if path.exists():
            existing = self._read_all_sheets(path)
            combined = pd.concat([existing, incoming], ignore_index=True)
        else:
            combined = incoming

        combined = self._normalize_frame(combined)

        self._write_yearly(path, combined)
        return len(combined)

    # ── Index ───────────────────────────────────────────────────────

    def refresh_index(self) -> pd.DataFrame:
        """Rebuild ``_index.xlsx`` from current tag files."""
        rows: list[dict[str, object]] = []
        for path in self.list_tag_files():
            df = self._read_all_sheets(path)
            if df.empty:
                continue
            years = sorted({ts.year for ts in df[DATETIME_COLUMN]})
            rows.append(
                {
                    "tag": path.stem,
                    "first_time": df[DATETIME_COLUMN].iloc[0],
                    "last_time": df[DATETIME_COLUMN].iloc[-1],
                    "row_count": len(df),
                    "years": ", ".join(str(y) for y in years),
                    "file_mtime": datetime.fromtimestamp(path.stat().st_mtime),
                }
            )
        index_df = pd.DataFrame(rows, columns=list(INDEX_COLUMNS))
        self._atomic_write_index(index_df)
        return index_df

    def read_index(self, *, auto_refresh: bool = True) -> pd.DataFrame:
        """Return ``_index.xlsx`` as a DataFrame, refreshing if stale."""
        if auto_refresh and self._index_is_stale():
            return self.refresh_index()
        if not self.index_path.exists():
            return self.refresh_index()
        return pd.read_excel(self.index_path)

    # ── Internals ───────────────────────────────────────────────────

    def _empty_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                DATETIME_COLUMN: pd.Series(dtype="datetime64[ns]"),
                VALUE_COLUMN: pd.Series(dtype="float64"),
                QUALITY_COLUMN: pd.Series(dtype="object"),
            }
        )

    def _normalize_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        """Coerce columns, parse dates, drop empty rows, sort, dedupe."""
        if df.empty:
            return self._empty_frame()

        df = df.rename(columns={c: str(c).strip().lower() for c in df.columns})
        if DATETIME_COLUMN not in df.columns:
            raise ValueError(
                "캐시 파일에 'datetime' 컬럼이 필요합니다 (A열)"
            )
        if VALUE_COLUMN not in df.columns:
            raise ValueError("캐시 파일에 'value' 컬럼이 필요합니다 (B열)")

        df[DATETIME_COLUMN] = pd.to_datetime(df[DATETIME_COLUMN], errors="coerce")
        df[VALUE_COLUMN] = pd.to_numeric(df[VALUE_COLUMN], errors="coerce")
        if QUALITY_COLUMN not in df.columns:
            df[QUALITY_COLUMN] = DEFAULT_QUALITY
        else:
            df[QUALITY_COLUMN] = (
                df[QUALITY_COLUMN].astype("object").fillna(DEFAULT_QUALITY)
            )

        df = df[[DATETIME_COLUMN, VALUE_COLUMN, QUALITY_COLUMN]]
        df = df.dropna(subset=[DATETIME_COLUMN])
        df = df.sort_values(DATETIME_COLUMN, kind="stable")
        df = df.drop_duplicates(subset=[DATETIME_COLUMN], keep="last")
        return df.reset_index(drop=True)

    def _read_sheet(self, xl: pd.ExcelFile, sheet: str) -> pd.DataFrame:
        return xl.parse(sheet_name=sheet)

    def _read_all_sheets(self, path: Path) -> pd.DataFrame:
        with pd.ExcelFile(path) as xl:
            frames = [self._read_sheet(xl, sheet) for sheet in xl.sheet_names]
        if not frames:
            return self._empty_frame()
        df = pd.concat(frames, ignore_index=True)
        return self._normalize_frame(df)

    def _write_yearly(self, path: Path, df: pd.DataFrame) -> None:
        """Write ``df`` split into one sheet per year via atomic rename."""
        with tempfile.NamedTemporaryFile(
            suffix=".xlsx",
            delete=False,
            dir=path.parent,
        ) as tmp:
            tmp_path = Path(tmp.name)
        try:
            with pd.ExcelWriter(tmp_path, engine="openpyxl") as writer:
                for year, group in df.groupby(df[DATETIME_COLUMN].dt.year):
                    out = group.copy()
                    out[DATETIME_COLUMN] = out[DATETIME_COLUMN].dt.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    out.to_excel(writer, sheet_name=str(int(year)), index=False)
                    sheet = writer.sheets[str(int(year))]
                    sheet.freeze_panes = "A2"
            shutil.move(str(tmp_path), str(path))
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    def _atomic_write_index(self, df: pd.DataFrame) -> None:
        with tempfile.NamedTemporaryFile(
            suffix=".xlsx",
            delete=False,
            dir=self.cache_dir,
        ) as tmp:
            tmp_path = Path(tmp.name)
        try:
            with pd.ExcelWriter(tmp_path, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name="index", index=False)
                sheet = writer.sheets["index"]
                sheet.freeze_panes = "A2"
            shutil.move(str(tmp_path), str(self.index_path))
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    def _index_is_stale(self) -> bool:
        """True if any tag file is newer than ``_index.xlsx``."""
        if not self.index_path.exists():
            return True
        index_mtime = self.index_path.stat().st_mtime
        for path in self.list_tag_files():
            if path.stat().st_mtime > index_mtime:
                return True
        return False


def coverage_to_dict(coverage: TagCoverage | None) -> dict[str, object] | None:
    if coverage is None:
        return None
    return {
        "tag": coverage.tag,
        "first_time": coverage.first_time.isoformat(),
        "last_time": coverage.last_time.isoformat(),
        "row_count": coverage.row_count,
    }


def opc_rows_to_frame(rows: Iterable[dict[str, object]]) -> pd.DataFrame:
    """Convert OPC adapter rows into the cache schema."""
    records: list[dict[str, object]] = []
    for row in rows:
        records.append(
            {
                DATETIME_COLUMN: row.get("datetime"),
                VALUE_COLUMN: row.get("value"),
                QUALITY_COLUMN: row.get("quality") or DEFAULT_QUALITY,
            }
        )
    return pd.DataFrame.from_records(records)
