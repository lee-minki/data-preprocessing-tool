"""Small local/portal backend skeleton for the preprocessing web UI.

This is intentionally dependency-light: it serves static files and a small tag
search/current-value API using only the standard library plus the optional
``opcua`` package when a live read endpoint is called.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
from collections import deque
from datetime import timedelta
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from preprocessing_portal.opc_adapter import OpcReadConfig, OpcUaReadAdapter, hold_sample, parse_kst
from preprocessing_portal.tag_index import TagIndexEntry, search_tags

PLANT_PREFIXES = {
    "paju": ("PJ1", "PJ2"),
    "파주": ("PJ1", "PJ2"),
    "pj": ("PJ1", "PJ2"),
    "gwangyang": ("KY",),
    "광양": ("KY",),
    "ky": ("KY",),
    "hanam": ("HN",),
    "하남": ("HN",),
    "hn": ("HN",),
    "wirye": ("WR",),
    "위례": ("WR",),
    "wr": ("WR",),
    "yeoju": ("YJ",),
    "여주": ("YJ",),
    "yj": ("YJ",),
}
ALLOWED_PREFIXES = frozenset({prefix for values in PLANT_PREFIXES.values() for prefix in values})
PREFIX_PATTERN = re.compile(r"^[A-Z0-9_]+$")
MAX_REQUEST_BYTES = 1_000_000
MAX_TIMESTAMP_COUNT = 200_000
MAX_HISTORY_SPAN_DAYS = 370
MIN_CHUNK_MINUTES = 1
MAX_CHUNK_MINUTES = 24 * 60
BLOCKED_STATIC_NAMES = {
    ".git",
    ".omx",
    ".playwright-mcp",
    "__pycache__",
    ".ruff_cache",
}
BLOCKED_STATIC_SUFFIXES = {".py", ".pyc", ".pyo", ".zip", ".json"}


def _entry_payload(entry: TagIndexEntry) -> dict[str, object]:
    return {
        "fulltagname": entry.fulltagname,
        "plant": entry.plant,
        "sourcename": entry.sourcename,
        "tagname": entry.tagname,
        "utagid": entry.utagid,
        "description": entry.description,
        "units": entry.units,
    }


def _normalize_prefix(prefix: str) -> str | None:
    normalized = prefix.strip().upper()
    if normalized not in ALLOWED_PREFIXES:
        return None
    if not PREFIX_PATTERN.fullmatch(normalized):
        return None
    return normalized


def _resolve_prefixes(query: dict[str, list[str]]) -> tuple[str, ...]:
    prefixes = [
        normalized
        for item in query.get("prefix", [])
        if (normalized := _normalize_prefix(item)) is not None
    ]
    plant = (query.get("plant", [""])[0] or "").strip().lower()
    if prefixes:
        return tuple(dict.fromkeys(prefixes))
    if plant in PLANT_PREFIXES:
        return PLANT_PREFIXES[plant]
    return ()


def _is_local_host(host: str) -> bool:
    hostname = host.split(":", 1)[0].strip().lower()
    return hostname in {"127.0.0.1", "localhost", "::1", "[::1]"}


def _static_path_blocked(url_path: str) -> bool:
    decoded = unquote(url_path).replace("\\", "/")
    parts = [part for part in decoded.split("/") if part and part != "."]
    if any(part == ".." for part in parts):
        return True
    if any(part in BLOCKED_STATIC_NAMES for part in parts):
        return True
    return any(Path(part).suffix.lower() in BLOCKED_STATIC_SUFFIXES for part in parts)


class PortalHandler(SimpleHTTPRequestHandler):
    index_dir = Path("opc_assets/tag_index")
    allowed_opc_endpoints = frozenset({OpcReadConfig().endpoint})
    allow_remote_api: bool = False
    api_rate_limit_per_minute: int = 60

    _rate_limit_lock = threading.Lock()
    _rate_limit_state: dict[str, deque[float]] = {}

    def _client_ip(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip() or "unknown"
        return self.client_address[0] if self.client_address else "unknown"

    def _is_rate_limited(self) -> bool:
        limit = self.api_rate_limit_per_minute
        if limit <= 0:
            return False
        now = time.time()
        window = 60.0
        ip = self._client_ip()
        with self._rate_limit_lock:
            timestamps = self._rate_limit_state.setdefault(ip, deque())
            while timestamps and timestamps[0] < now - window:
                timestamps.popleft()
            if len(timestamps) >= limit:
                return True
            timestamps.append(now)
            return False

    def _api_request_allowed(self) -> bool:
        if self.allow_remote_api:
            return True
        host = self.headers.get("Host", "")
        if host and not _is_local_host(host):
            return False
        origin = self.headers.get("Origin")
        if origin:
            parsed = urlparse(origin)
            if parsed.scheme not in {"http", "https"} or not _is_local_host(parsed.netloc):
                return False
        return True

    def _reject_forbidden_api(self) -> bool:
        if not self._api_request_allowed():
            self._json(
                {"ok": False, "error": "로컬 포털 API는 localhost 요청만 허용합니다"},
                status=HTTPStatus.FORBIDDEN,
            )
            return True
        if self._is_rate_limited():
            self._json(
                {
                    "ok": False,
                    "error": (
                        f"요청이 너무 많습니다 (분당 "
                        f"{self.api_rate_limit_per_minute}회 제한)"
                    ),
                },
                status=HTTPStatus.TOO_MANY_REQUESTS,
            )
            return True
        return False

    def _resolve_allowed_endpoint(self, endpoint: object | None) -> str:
        value = str(endpoint or OpcReadConfig().endpoint).strip()
        if value not in self.allowed_opc_endpoints:
            raise ValueError("허용되지 않은 OPC endpoint입니다")
        return value

    def do_GET(self) -> None:  # noqa: N802 - stdlib override
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/") and self._reject_forbidden_api():
            return
        if parsed.path == "/api/health":
            self._json({"ok": True, "service": "preprocessing_portal"})
            return
        if parsed.path == "/api/tags":
            self._handle_tag_search(parse_qs(parsed.query))
            return
        if parsed.path == "/api/opc/current":
            self._handle_opc_current(parse_qs(parsed.query))
            return
        if _static_path_blocked(parsed.path):
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden static path")
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - stdlib override
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/") and self._reject_forbidden_api():
            return
        if parsed.path == "/api/opc/helper-values":
            try:
                payload = self._read_json_body()
            except ValueError as exc:
                self._json(
                    {"ok": False, "error": str(exc)},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return
            self._handle_opc_helper_values(payload)
            return
        self._json(
            {"ok": False, "error": "지원하지 않는 API 경로입니다"},
            status=HTTPStatus.NOT_FOUND,
        )

    def _read_json_body(self) -> dict[str, object]:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError as exc:
            raise ValueError("Content-Length는 숫자여야 합니다") from exc
        if length > MAX_REQUEST_BYTES:
            raise ValueError(f"요청 본문은 최대 {MAX_REQUEST_BYTES:,} bytes까지 허용됩니다")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON 본문을 파싱할 수 없습니다: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON 본문은 객체여야 합니다")
        return payload

    def _handle_tag_search(self, query: dict[str, list[str]]) -> None:
        prefixes = _resolve_prefixes(query)
        if not prefixes:
            self._json(
                {"ok": False, "error": "plant 또는 prefix를 지정하세요"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        try:
            limit = int((query.get("limit", ["100"])[0] or "100"))
        except ValueError:
            self._json(
                {"ok": False, "error": "limit은 숫자여야 합니다"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        search_query = query.get("q", [""])[0]
        try:
            results = search_tags(
                self.index_dir,
                prefixes,
                search_query,
                limit=max(1, min(limit, 500)),
            )
        except FileNotFoundError as exc:
            self._json(
                {"ok": False, "error": f"태그 인덱스를 찾지 못했습니다: {exc}"},
                status=HTTPStatus.NOT_FOUND,
            )
            return
        self._json(
            {
                "ok": True,
                "prefixes": list(prefixes),
                "count": len(results),
                "tags": [_entry_payload(entry) for entry in results],
            }
        )

    def _handle_opc_current(self, query: dict[str, list[str]]) -> None:
        tags = [tag for tag in query.get("tag", []) if tag.strip()]
        if not tags:
            self._json(
                {"ok": False, "error": "tag를 1개 이상 지정하세요"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        if len(tags) > 10:
            self._json(
                {"ok": False, "error": "한 번에 최대 10개 태그만 조회할 수 있습니다"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        try:
            endpoint = self._resolve_allowed_endpoint(query.get("endpoint", [None])[0])
            namespace = int(query.get("namespace", [str(OpcReadConfig().namespace)])[0])
        except ValueError as exc:
            self._json(
                {"ok": False, "error": str(exc) if "endpoint" in str(exc).lower() else "namespace는 숫자여야 합니다"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        entries = []
        try:
            for tag in tags:
                # Reuse search to avoid repeatedly scanning every prefix when callers
                # pass fulltagname with plant prefix.
                prefix = _normalize_prefix(tag.split(".", 1)[0])
                if prefix is None:
                    raise ValueError(f"허용되지 않은 태그 prefix입니다: {tag}")
                matches = [
                    entry
                    for entry in search_tags(self.index_dir, [prefix], tag, limit=1)
                    if entry.fulltagname == tag
                ]
                if not matches:
                    raise KeyError(tag)
                entries.append(matches[0])
            adapter = OpcUaReadAdapter(
                OpcReadConfig(endpoint=endpoint, namespace=namespace)
            )
            adapter.connect()
            try:
                values = adapter.read_current_values(entries)
            finally:
                adapter.disconnect()
        except Exception as exc:  # pragma: no cover - VDI diagnostic path
            self._json(
                {"ok": False, "error": f"OPC 현재값 조회 실패: {type(exc).__name__}: {exc}"},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return
        self._json({"ok": True, "values": values})

    def _handle_opc_helper_values(self, payload: dict[str, object]) -> None:
        try:
            tags = [str(tag).strip() for tag in payload.get("tags", []) if str(tag).strip()]
            timestamps = [
                str(timestamp).strip()
                for timestamp in payload.get("timestamps", [])
            ]
        except TypeError:
            self._json(
                {"ok": False, "error": "tags/timestamps는 배열이어야 합니다"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        if not tags:
            self._json(
                {"ok": False, "error": "helper 태그를 1개 이상 지정하세요"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        if len(tags) > 10:
            self._json(
                {"ok": False, "error": "한 번에 최대 10개 helper 태그만 조회할 수 있습니다"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        if len(timestamps) < 2:
            self._json(
                {"ok": False, "error": "시간축 timestamp가 2개 이상 필요합니다"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        if any(not timestamp for timestamp in timestamps):
            self._json(
                {"ok": False, "error": "빈 timestamp가 포함되어 있습니다"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        try:
            endpoint = self._resolve_allowed_endpoint(payload.get("endpoint"))
            namespace = int(payload.get("namespace") or OpcReadConfig().namespace)
            chunk_minutes = int(payload.get("chunk_minutes") or OpcReadConfig().chunk_minutes)
        except (TypeError, ValueError) as exc:
            self._json(
                {"ok": False, "error": str(exc) if "endpoint" in str(exc).lower() else "namespace/chunk_minutes는 숫자여야 합니다"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        if not (MIN_CHUNK_MINUTES <= chunk_minutes <= MAX_CHUNK_MINUTES):
            self._json(
                {"ok": False, "error": f"chunk_minutes는 {MIN_CHUNK_MINUTES}~{MAX_CHUNK_MINUTES} 범위여야 합니다"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        if len(timestamps) > MAX_TIMESTAMP_COUNT:
            self._json(
                {"ok": False, "error": f"timestamp는 최대 {MAX_TIMESTAMP_COUNT:,}개까지 허용됩니다"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        helpers: list[dict[str, object]] = []
        try:
            parsed_timestamps = [parse_kst(timestamp) for timestamp in timestamps]
            start = min(parsed_timestamps)
            end = max(parsed_timestamps)
            if end - start > timedelta(days=MAX_HISTORY_SPAN_DAYS):
                self._json(
                    {"ok": False, "error": f"OPC 조회 기간은 최대 {MAX_HISTORY_SPAN_DAYS}일입니다"},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return
            entries = []
            for tag in tags:
                prefix = _normalize_prefix(tag.split(".", 1)[0])
                if prefix is None:
                    raise ValueError(f"허용되지 않은 태그 prefix입니다: {tag}")
                matches = [
                    entry
                    for entry in search_tags(self.index_dir, [prefix], tag, limit=1)
                    if entry.fulltagname == tag
                ]
                if not matches:
                    raise KeyError(tag)
                entries.append(matches[0])
            adapter = OpcUaReadAdapter(
                OpcReadConfig(
                    endpoint=endpoint,
                    namespace=namespace,
                    chunk_minutes=chunk_minutes,
                )
            )
            adapter.connect()
            try:
                for index, entry in enumerate(entries, start=1):
                    raw_rows = adapter.read_raw_history(entry, start, end)
                    values = hold_sample(raw_rows, parsed_timestamps)
                    helpers.append(
                        {
                            "id": f"helper_opc_{index:03d}",
                            "column": f"__helper__opc_{index:03d}",
                            "fulltagname": entry.fulltagname,
                            "display_name": entry.description or entry.tagname or entry.fulltagname,
                            "units": entry.units,
                            "non_null_count": sum(value is not None for value in values),
                            "values": values,
                        }
                    )
            finally:
                adapter.disconnect()
        except Exception as exc:  # pragma: no cover - VDI diagnostic path
            self._json(
                {"ok": False, "error": f"OPC helper 값 조회 실패: {type(exc).__name__}: {exc}"},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return
        self._json({"ok": True, "helpers": helpers})

    def _json(self, payload: dict[str, object], *, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run preprocessing portal backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--index-dir", default="opc_assets/tag_index")
    parser.add_argument("--directory", default=".")
    parser.add_argument(
        "--allowed-opc-endpoint",
        action="append",
        default=None,
        help="허용할 OPC endpoint. 여러 번 지정 가능하며 미지정 시 기본 endpoint만 허용합니다.",
    )
    parser.add_argument(
        "--allow-remote-api",
        action="store_true",
        default=_env_truthy("PORTAL_ALLOW_REMOTE"),
        help=(
            "비-localhost API 요청을 허용 (다중 사용자 모드). "
            "PORTAL_ALLOW_REMOTE=1 환경변수로도 켤 수 있습니다. 사내망에서만 사용."
        ),
    )
    parser.add_argument(
        "--api-rate-limit",
        type=int,
        default=int(os.environ.get("PORTAL_API_RATE_LIMIT", "60") or 60),
        help="IP별 API 요청 분당 한도 (0=무제한, 기본 60).",
    )
    args = parser.parse_args(argv)

    allowed_endpoints = frozenset(args.allowed_opc_endpoint or [OpcReadConfig().endpoint])

    class Handler(PortalHandler):
        index_dir = Path(args.index_dir)
        allowed_opc_endpoints = allowed_endpoints
        allow_remote_api = bool(args.allow_remote_api)
        api_rate_limit_per_minute = int(args.api_rate_limit)

        def __init__(self, *handler_args: object, **handler_kwargs: object) -> None:
            super().__init__(
                *handler_args,
                directory=args.directory,
                **handler_kwargs,
            )

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Serving preprocessing portal on http://{args.host}:{args.port}")
    print(f"Tag index dir: {Path(args.index_dir).resolve()}")
    if args.allow_remote_api:
        print("⚠️  Remote API access ENABLED (다중 사용자 모드)")
    print(f"API rate limit: {args.api_rate_limit}/min per IP" if args.api_rate_limit > 0 else "API rate limit: disabled")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
