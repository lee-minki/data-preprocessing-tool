"""Standalone OPC UA read adapter for helper-tag conditions.

The adapter mirrors the proven RiMS/narae read flow without importing that
project.  It imports ``opcua`` only when a real VDI read is attempted so local
planning/tests can run without the optional OPC dependency.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

from preprocessing_portal.tag_index import TagIndexEntry, find_entry

KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class OpcReadConfig:
    endpoint: str = "opc.tcp://192.9.110.151:51241/Capstone/OPCUAServer"
    namespace: int = 12
    connect_timeout_sec: float = 10.0
    chunk_minutes: int = 60
    boundary_minutes: tuple[int, ...] = (1, 5, 10, 30)

    def make_node_id(self, utagid: int) -> str:
        return f"ns={self.namespace};i={int(utagid)}"


def parse_kst(value: str | datetime) -> datetime:
    """Parse a timestamp and treat naive values as KST."""
    if isinstance(value, datetime):
        dt_value = value
    else:
        raw = value.strip().replace("Z", "+00:00")
        try:
            dt_value = datetime.fromisoformat(raw)
        except ValueError:
            dt_value = None
            for fmt in (
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y/%m/%d %H:%M",
                "%m/%d/%y %H:%M",
                "%m/%d/%Y %H:%M",
                "%Y-%m-%d",
                "%Y/%m/%d",
            ):
                try:
                    dt_value = datetime.strptime(raw, fmt)
                    break
                except ValueError:
                    continue
            if dt_value is None:
                raise ValueError(f"지원하지 않는 시간 형식입니다: {value}")
    if dt_value.tzinfo is None:
        return dt_value.replace(tzinfo=KST)
    return dt_value.astimezone(KST)


def _server_timestamp_to_kst_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(KST).replace(tzinfo=None)


class OpcUaReadAdapter:
    """Small OPC UA reader scoped to preprocessing helper tags."""

    def __init__(self, config: OpcReadConfig) -> None:
        self.config = config
        self._client: Any = None

    def connect(self) -> None:
        try:
            from opcua import Client  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - depends on VDI env
            raise ImportError(
                "opcua 라이브러리가 필요합니다. VDI 환경에서 설치 후 다시 실행하세요."
            ) from exc
        self._client = Client(self.config.endpoint)
        self._client.session_timeout = int(self.config.connect_timeout_sec * 1000)
        self._client.connect()

    def disconnect(self) -> None:
        if self._client is not None:
            self._client.disconnect()
            self._client = None

    def _node(self, entry: TagIndexEntry) -> Any:
        if self._client is None:
            raise RuntimeError("connect()를 먼저 호출하세요.")
        return self._client.get_node(self.config.make_node_id(entry.utagid))

    def read_current_values(self, entries: Iterable[TagIndexEntry]) -> dict[str, Any]:
        """Read current values for selected tags."""
        values: dict[str, Any] = {}
        for entry in entries:
            try:
                values[entry.fulltagname] = self._node(entry).get_value()
            except Exception as exc:  # pragma: no cover - VDI diagnostics path
                values[entry.fulltagname] = None
                values[f"{entry.fulltagname}__error"] = f"{type(exc).__name__}: {exc}"
        return values

    def read_raw_history(
        self,
        entry: TagIndexEntry,
        start: str | datetime,
        end: str | datetime,
        progress_callback: Callable[[int, int, datetime], None] | None = None,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> list[dict[str, Any]]:
        """Read raw history for a selected tag using bounded chunks.

        progress_callback(current_chunk, total_chunks, chunk_start_time) is called
        after each chunk so callers can display a progress bar or ETA.
        """
        start_kst = parse_kst(start)
        end_kst = parse_kst(end)
        if end_kst <= start_kst:
            raise ValueError("end must be greater than start")

        chunk = timedelta(minutes=max(1, self.config.chunk_minutes))
        total_chunks = math.ceil((end_kst - start_kst) / chunk)

        rows: list[dict[str, Any]] = []
        boundary = self._read_boundary(entry, start_kst)
        if boundary is not None:
            rows.append(boundary)

        cursor = start_kst
        chunk_idx = 0
        while cursor < end_kst:
            if cancel_callback is not None and cancel_callback():
                raise RuntimeError("OPC read cancelled")
            chunk_idx += 1
            chunk_end = min(cursor + chunk, end_kst)
            rows.extend(self._read_raw_window(entry, cursor, chunk_end))
            if cancel_callback is not None and cancel_callback():
                raise RuntimeError("OPC read cancelled")
            if progress_callback is not None:
                progress_callback(chunk_idx, total_chunks, cursor)
            cursor = chunk_end
        rows.sort(key=lambda row: row["datetime"])
        return rows

    def _read_boundary(
        self,
        entry: TagIndexEntry,
        start_kst: datetime,
    ) -> dict[str, Any] | None:
        for minutes in self.config.boundary_minutes:
            rows = [
                row
                for row in self._read_raw_window(
                    entry, start_kst - timedelta(minutes=minutes), start_kst
                )
                if row.get("datetime") is not None
                and row["datetime"] < start_kst.replace(tzinfo=None)
                and row.get("value") is not None
            ]
            if rows:
                return max(rows, key=lambda row: row["datetime"])
        return None

    def _read_raw_window(
        self,
        entry: TagIndexEntry,
        start_kst: datetime,
        end_kst: datetime,
    ) -> list[dict[str, Any]]:
        node = self._node(entry)
        start_utc = start_kst.astimezone(timezone.utc)
        end_utc = end_kst.astimezone(timezone.utc)
        history = node.read_raw_history(starttime=start_utc, endtime=end_utc, numvalues=0)
        rows: list[dict[str, Any]] = []
        for data_value in history:
            sample_dt = _server_timestamp_to_kst_naive(
                getattr(data_value, "ServerTimestamp", None)
                or getattr(data_value, "SourceTimestamp", None)
            )
            if sample_dt is None:
                continue
            try:
                good = data_value.StatusCode.is_good()
            except Exception:
                good = True
            value = (
                data_value.Value.Value
                if getattr(data_value, "Value", None) is not None
                else None
            )
            rows.append({"datetime": sample_dt, "value": value if good else None})
        return rows


def hold_sample(
    raw_rows: list[dict[str, Any]],
    timestamps: Iterable[str | datetime],
) -> list[Any]:
    """Return previous-hold values aligned to timestamps."""
    sorted_rows = sorted(raw_rows, key=lambda row: row["datetime"])
    index = 0
    last_value: Any = None
    values: list[Any] = []
    for ts in timestamps:
        current = parse_kst(ts).replace(tzinfo=None)
        while index < len(sorted_rows) and sorted_rows[index]["datetime"] <= current:
            if sorted_rows[index].get("value") is not None:
                last_value = sorted_rows[index]["value"]
            index += 1
        values.append(last_value)
    return values


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VDI OPC helper-tag read probe")
    parser.add_argument("--index-dir", default="opc_assets/tag_index")
    parser.add_argument("--tag", action="append", required=True)
    parser.add_argument("--endpoint", default=OpcReadConfig().endpoint)
    parser.add_argument("--namespace", type=int, default=OpcReadConfig().namespace)
    parser.add_argument("--current", action="store_true", help="Read current values")
    parser.add_argument("--start", help="History start time, ISO format")
    parser.add_argument("--end", help="History end time, ISO format")
    parser.add_argument("--chunk-minutes", type=int, default=60)
    args = parser.parse_args(argv)

    entries = [find_entry(args.index_dir, tag) for tag in args.tag]
    adapter = OpcUaReadAdapter(
        OpcReadConfig(
            endpoint=args.endpoint,
            namespace=args.namespace,
            chunk_minutes=args.chunk_minutes,
        )
    )
    adapter.connect()
    try:
        if args.current:
            print(json.dumps(adapter.read_current_values(entries), ensure_ascii=False))
            return 0
        if not args.start or not args.end:
            raise SystemExit("--start and --end are required for history reads")
        for entry in entries:
            print(f"\n📡 {entry.fulltagname} 히스토리 읽기 중...", flush=True)
            wall_start = time.time()

            def _make_progress_cb(t0: float) -> Callable[[int, int, datetime], None]:
                def cb(current: int, total: int, chunk_time: datetime) -> None:
                    pct = current / total * 100 if total else 0
                    elapsed = time.time() - t0
                    eta = int((elapsed / current) * (total - current)) if current else 0
                    bar_filled = int(pct / 5)
                    bar = "█" * bar_filled + "░" * (20 - bar_filled)
                    time_str = chunk_time.strftime("%Y-%m-%d %H:%M")
                    eta_str = f"ETA {eta // 60}m {eta % 60}s" if current < total else "완료"
                    print(
                        f"\r  [{bar}] {pct:5.1f}%  {time_str}  ({current}/{total})  {eta_str}   ",
                        end="",
                        flush=True,
                    )
                return cb

            rows = adapter.read_raw_history(
                entry, args.start, args.end, progress_callback=_make_progress_cb(wall_start)
            )
            elapsed_total = time.time() - wall_start
            print(f"\r  완료 ({elapsed_total:.1f}s, {len(rows):,}행)                              ")
            print(
                json.dumps(
                    {
                        "fulltagname": entry.fulltagname,
                        "rows": len(rows),
                        "first": str(rows[0]["datetime"]) if rows else None,
                        "last": str(rows[-1]["datetime"]) if rows else None,
                    },
                    ensure_ascii=False,
                )
            )
    finally:
        adapter.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
