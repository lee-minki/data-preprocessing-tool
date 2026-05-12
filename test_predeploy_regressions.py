"""Pre-deployment regression checks for security and stability fixes."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from data_preprocessor import DataPreprocessor
from preprocessing_portal.server import (
    MAX_REQUEST_BYTES,
    _normalize_prefix,
    _resolve_prefixes,
)
from preprocessing_portal.tag_cache import (
    DATETIME_COLUMN,
    QUALITY_COLUMN,
    VALUE_COLUMN,
    TagCache,
    opc_rows_to_frame,
)


class DataPreprocessorRegressionTests(unittest.TestCase):
    def test_load_dataframe_clears_stale_date_metadata(self) -> None:
        preprocessor = DataPreprocessor()
        ok, _ = preprocessor.load_dataframe(
            pd.DataFrame({"Date": ["2026-01-01 00:00:00"], "Value": [1]})
        )
        self.assertTrue(ok)
        self.assertEqual(preprocessor.date_column, "Date")

        ok, _ = preprocessor.load_dataframe(pd.DataFrame({"a": [1], "b": [2]}))

        self.assertTrue(ok)
        self.assertIsNone(preprocessor.date_column)
        self.assertIsNone(preprocessor.original_date_format)

    def test_save_dataframe_escapes_formula_like_strings_for_xlsx_and_csv(self) -> None:
        preprocessor = DataPreprocessor()
        df = pd.DataFrame(
            {
                '=HYPERLINK("http://evil-header")': ["=HYPERLINK(\"http://evil\")"],
                "+SUM(1,2)": ["+SUM(1,2)"],
                "\r=CMD": ["\n=PAYLOAD"],
                "safe": ["safe"],
            }
        )
        ok, _ = preprocessor.load_dataframe(df)
        self.assertTrue(ok)

        with tempfile.TemporaryDirectory() as tmpdir:
            xlsx_path = Path(tmpdir) / "out.xlsx"
            csv_path = Path(tmpdir) / "out.csv"
            preprocessor._save_dataframe(preprocessor.processed_df, xlsx_path)
            preprocessor._save_dataframe(preprocessor.processed_df, csv_path)

            wb = load_workbook(xlsx_path, data_only=False)
            ws = wb.active
            self.assertEqual(ws["A1"].value, "'=HYPERLINK(\"http://evil-header\")")
            self.assertEqual(ws["B1"].value, "'+SUM(1,2)")
            self.assertEqual(ws["C1"].value, "'=CMD")
            self.assertEqual(ws["A2"].value, "'=HYPERLINK(\"http://evil\")")
            self.assertEqual(ws["B2"].value, "'+SUM(1,2)")
            self.assertEqual(ws["C2"].value, "'=PAYLOAD")
            self.assertNotEqual(ws["A1"].data_type, "f")

            with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f))
            self.assertEqual(rows[0][0], "'=HYPERLINK(\"http://evil-header\")")
            self.assertEqual(rows[0][1], "'+SUM(1,2)")
            self.assertEqual(rows[0][2], "'=CMD")
            self.assertEqual(rows[1][0], "'=HYPERLINK(\"http://evil\")")
            self.assertEqual(rows[1][1], "'+SUM(1,2)")
            self.assertEqual(rows[1][2], "'=PAYLOAD")

    def test_load_data_drops_unnamed_columns_without_crashing(self) -> None:
        preprocessor = DataPreprocessor()
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "with_unnamed.csv"
            csv_path.write_text("Unnamed: 0,Date,Value\n0,2026-01-01 00:00:00,10\n", encoding="utf-8")
            ok, message = preprocessor.load_data(str(csv_path))

        self.assertTrue(ok, message)
        self.assertNotIn("Unnamed: 0", preprocessor.columns)
        self.assertEqual(preprocessor.columns, ["Date", "Value"])

    def test_removed_source_indices_survive_index_reset(self) -> None:
        preprocessor = DataPreprocessor()
        ok, _ = preprocessor.load_dataframe(
            pd.DataFrame(
                {
                    "Date": pd.date_range("2026-01-01", periods=5, freq="min"),
                    "Value": [10, 20, 30, 40, 50],
                }
            )
        )
        self.assertTrue(ok)
        ok, _ = preprocessor.apply_filters(
            [{"column": "Value", "operator": ">=", "value": 30}]
        )
        self.assertTrue(ok)
        self.assertEqual(preprocessor.processed_df.index.tolist(), [0, 1, 2])
        self.assertEqual(preprocessor.get_removed_source_indices(), [0, 1])


class TagCacheRegressionTests(unittest.TestCase):
    @staticmethod
    def _sample_rows(start_iso: str, count: int) -> pd.DataFrame:
        return pd.DataFrame(
            {
                DATETIME_COLUMN: pd.date_range(start_iso, periods=count, freq="2min"),
                VALUE_COLUMN: [float(i) for i in range(count)],
            }
        )

    def test_save_then_load_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = TagCache(tmpdir)
            df = self._sample_rows("2024-01-01 00:00:00", 5)
            total = cache.save("TI-101", df)
            self.assertEqual(total, 5)

            coverage = cache.get_coverage("TI-101")
            self.assertIsNotNone(coverage)
            self.assertEqual(coverage.row_count, 5)
            self.assertEqual(coverage.first_time.year, 2024)

            loaded = cache.load_range(
                "TI-101",
                pd.Timestamp("2024-01-01 00:00:00").to_pydatetime(),
                pd.Timestamp("2024-01-01 00:08:00").to_pydatetime(),
            )
            self.assertEqual(len(loaded), 5)
            self.assertTrue(loaded[QUALITY_COLUMN].eq("Good").all())

    def test_has_range_requires_full_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = TagCache(tmpdir)
            cache.save("TI-101", self._sample_rows("2024-01-01 00:00:00", 3))

            in_range = pd.Timestamp("2024-01-01 00:00:00").to_pydatetime()
            out_of_range = pd.Timestamp("2024-01-01 00:10:00").to_pydatetime()
            self.assertTrue(
                cache.has_range("TI-101", in_range, in_range)
            )
            self.assertFalse(
                cache.has_range("TI-101", in_range, out_of_range)
            )

    def test_merge_dedupes_overlapping_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = TagCache(tmpdir)
            first = self._sample_rows("2024-01-01 00:00:00", 3)
            cache.save("TI-101", first)

            overlap = pd.DataFrame(
                {
                    DATETIME_COLUMN: [pd.Timestamp("2024-01-01 00:02:00")],
                    VALUE_COLUMN: [999.0],
                }
            )
            total = cache.save("TI-101", overlap)
            self.assertEqual(total, 3)

            loaded = cache.load_range(
                "TI-101",
                pd.Timestamp("2024-01-01 00:02:00").to_pydatetime(),
                pd.Timestamp("2024-01-01 00:02:00").to_pydatetime(),
            )
            self.assertEqual(loaded.iloc[0][VALUE_COLUMN], 999.0)

    def test_yearly_split_writes_separate_sheets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = TagCache(tmpdir)
            df = pd.DataFrame(
                {
                    DATETIME_COLUMN: [
                        pd.Timestamp("2023-12-31 23:58:00"),
                        pd.Timestamp("2024-01-01 00:00:00"),
                    ],
                    VALUE_COLUMN: [1.0, 2.0],
                }
            )
            cache.save("TI-101", df)
            with pd.ExcelFile(cache.tag_path("TI-101")) as xl:
                self.assertEqual(sorted(xl.sheet_names), ["2023", "2024"])

    def test_index_auto_rebuilds_when_tag_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = TagCache(tmpdir)
            cache.save("TI-101", self._sample_rows("2024-01-01 00:00:00", 2))
            index_df = cache.read_index()
            self.assertEqual(len(index_df), 1)

            # Add another tag and ensure index refreshes.
            cache.save("FI-205", self._sample_rows("2024-06-01 00:00:00", 2))
            refreshed = cache.read_index()
            self.assertEqual(sorted(refreshed["tag"].tolist()), ["FI-205", "TI-101"])

    def test_opc_rows_to_frame_fills_missing_quality(self) -> None:
        rows = [
            {"datetime": pd.Timestamp("2024-01-01"), "value": 1.0},
            {"datetime": pd.Timestamp("2024-01-01 00:02"), "value": 2.0, "quality": "Bad"},
        ]
        df = opc_rows_to_frame(rows)
        self.assertEqual(df[QUALITY_COLUMN].iloc[0], "Good")
        self.assertEqual(df[QUALITY_COLUMN].iloc[1], "Bad")


class PortalSecurityRegressionTests(unittest.TestCase):
    def test_prefix_normalization_blocks_traversal(self) -> None:
        self.assertEqual(_normalize_prefix("pj1"), "PJ1")
        self.assertIsNone(_normalize_prefix("../PJ1"))
        self.assertIsNone(_normalize_prefix("PJ1/../../secret"))
        self.assertEqual(_resolve_prefixes({"prefix": ["../PJ1", "KY"]}), ("KY",))

    def test_request_body_limit_constant_is_bounded(self) -> None:
        self.assertLessEqual(MAX_REQUEST_BYTES, 1_000_000)


class PortalMultiUserModeTests(unittest.TestCase):
    """다중 사용자 모드 토글과 IP rate limit 동작."""

    def _make_handler(self, *, allow_remote: bool, rate_limit: int) -> object:
        import threading

        from preprocessing_portal.server import PortalHandler

        class FakeHandler(PortalHandler):
            allow_remote_api = allow_remote
            api_rate_limit_per_minute = rate_limit
            _rate_limit_lock = threading.Lock()
            _rate_limit_state: dict = {}

            def __init__(self, client_ip: str, host_header: str = "") -> None:
                # SimpleHTTPRequestHandler 초기화는 우회 — 필요한 속성만 셋업
                self.client_address = (client_ip, 12345)
                self.headers = {"Host": host_header} if host_header else {}

        return FakeHandler

    def test_allow_remote_api_bypasses_localhost_check(self) -> None:
        Handler = self._make_handler(allow_remote=True, rate_limit=0)
        handler = Handler("203.0.113.42", host_header="203.0.113.42:8765")
        self.assertTrue(handler._api_request_allowed())

    def test_localhost_only_blocks_remote_when_flag_off(self) -> None:
        Handler = self._make_handler(allow_remote=False, rate_limit=0)
        handler = Handler("203.0.113.42", host_header="203.0.113.42:8765")
        self.assertFalse(handler._api_request_allowed())

    def test_rate_limit_kicks_in_after_n_requests(self) -> None:
        Handler = self._make_handler(allow_remote=True, rate_limit=3)
        # Fresh state per Handler class
        Handler._rate_limit_state = {}
        handler = Handler("10.0.0.5")

        for _ in range(3):
            self.assertFalse(handler._is_rate_limited())
        self.assertTrue(handler._is_rate_limited())

    def test_rate_limit_zero_means_unlimited(self) -> None:
        Handler = self._make_handler(allow_remote=True, rate_limit=0)
        Handler._rate_limit_state = {}
        handler = Handler("10.0.0.5")
        for _ in range(50):
            self.assertFalse(handler._is_rate_limited())

    def test_x_forwarded_for_overrides_client_address(self) -> None:
        Handler = self._make_handler(allow_remote=True, rate_limit=2)
        Handler._rate_limit_state = {}

        # IIS/nginx 가 forwarding 한 client IP — 본 client_address 는 127.0.0.1
        h1 = Handler("127.0.0.1")
        h1.headers = {"X-Forwarded-For": "10.0.0.5, 192.168.1.1"}
        h2 = Handler("127.0.0.1")
        h2.headers = {"X-Forwarded-For": "10.0.0.6"}

        self.assertFalse(h1._is_rate_limited())
        self.assertFalse(h1._is_rate_limited())
        self.assertTrue(h1._is_rate_limited())
        # 다른 X-Forwarded-For 는 별도 버킷
        self.assertFalse(h2._is_rate_limited())

    def test_rate_limit_is_per_ip(self) -> None:
        Handler = self._make_handler(allow_remote=True, rate_limit=2)
        Handler._rate_limit_state = {}

        h1 = Handler("10.0.0.5")
        h2 = Handler("10.0.0.6")
        self.assertFalse(h1._is_rate_limited())
        self.assertFalse(h1._is_rate_limited())
        self.assertTrue(h1._is_rate_limited())
        # 두 번째 IP는 영향 안 받음
        self.assertFalse(h2._is_rate_limited())
        self.assertFalse(h2._is_rate_limited())
        self.assertTrue(h2._is_rate_limited())


if __name__ == "__main__":
    unittest.main()
