"""Small local/portal backend skeleton for the preprocessing web UI.

This is intentionally dependency-light: it serves static files and a small tag
search/current-value API using only the standard library plus the optional
``opcua`` package when a live read endpoint is called.
"""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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


def _resolve_prefixes(query: dict[str, list[str]]) -> tuple[str, ...]:
    prefixes = [item.upper() for item in query.get("prefix", []) if item.strip()]
    plant = (query.get("plant", [""])[0] or "").strip().lower()
    if prefixes:
        return tuple(prefixes)
    if plant in PLANT_PREFIXES:
        return PLANT_PREFIXES[plant]
    return ()


class PortalHandler(SimpleHTTPRequestHandler):
    index_dir = Path("opc_assets/tag_index")

    def do_GET(self) -> None:  # noqa: N802 - stdlib override
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._json({"ok": True, "service": "preprocessing_portal"})
            return
        if parsed.path == "/api/tags":
            self._handle_tag_search(parse_qs(parsed.query))
            return
        if parsed.path == "/api/opc/current":
            self._handle_opc_current(parse_qs(parsed.query))
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - stdlib override
        parsed = urlparse(self.path)
        if parsed.path == "/api/opc/helper-values":
            self._handle_opc_helper_values(self._read_json_body())
            return
        self._json(
            {"ok": False, "error": "지원하지 않는 API 경로입니다"},
            status=HTTPStatus.NOT_FOUND,
        )

    def _read_json_body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0") or "0")
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
        limit = int((query.get("limit", ["100"])[0] or "100"))
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
        endpoint = query.get("endpoint", [OpcReadConfig().endpoint])[0]
        namespace = int(query.get("namespace", [str(OpcReadConfig().namespace)])[0])
        entries = []
        try:
            for tag in tags:
                # Reuse search to avoid repeatedly scanning every prefix when callers
                # pass fulltagname with plant prefix.
                prefix = tag.split(".", 1)[0].upper()
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

        endpoint = str(payload.get("endpoint") or OpcReadConfig().endpoint)
        namespace = int(payload.get("namespace") or OpcReadConfig().namespace)
        chunk_minutes = int(payload.get("chunk_minutes") or OpcReadConfig().chunk_minutes)
        helpers: list[dict[str, object]] = []
        try:
            parsed_timestamps = [parse_kst(timestamp) for timestamp in timestamps]
            start = min(parsed_timestamps)
            end = max(parsed_timestamps)
            entries = []
            for tag in tags:
                prefix = tag.split(".", 1)[0].upper()
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


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run preprocessing portal backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--index-dir", default="opc_assets/tag_index")
    parser.add_argument("--directory", default=".")
    args = parser.parse_args(argv)

    class Handler(PortalHandler):
        index_dir = Path(args.index_dir)

        def __init__(self, *handler_args: object, **handler_kwargs: object) -> None:
            super().__init__(
                *handler_args,
                directory=args.directory,
                **handler_kwargs,
            )

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Serving preprocessing portal on http://{args.host}:{args.port}")
    print(f"Tag index dir: {Path(args.index_dir).resolve()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
