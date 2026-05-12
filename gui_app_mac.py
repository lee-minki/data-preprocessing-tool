"""
데이터 전처리 GUI 애플리케이션 - Mac 버전 (PyQt5)
- PyQt5 기반 사용자 인터페이스
- macOS 호환
- 파일 로드, 필터링, 이상값 처리, 저장 기능
"""

import sys
import os
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

import pandas as pd
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QPushButton,
    QLabel,
    QComboBox,
    QLineEdit,
    QCheckBox,
    QRadioButton,
    QButtonGroup,
    QProgressBar,
    QTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QFileDialog,
    QMessageBox,
    QDialog,
    QListWidget,
    QAction,
    QFrame,
    QHeaderView,
    QSpinBox,
    QDoubleSpinBox,
    QTabWidget,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

# 핵심 로직 임포트
from data_preprocessor import DataPreprocessor
from preset_manager import PresetManager
from version import __version__, APP_NAME

try:
    from preprocessing_portal.opc_adapter import OpcUaReadAdapter, OpcReadConfig
    from preprocessing_portal.tag_index import find_entry
    HAS_OPC = True
except Exception:
    HAS_OPC = False

try:
    from preprocessing_portal.tag_cache import (
        TagCache,
        opc_rows_to_frame,
        DATETIME_COLUMN,
        VALUE_COLUMN,
    )
    HAS_TAG_CACHE = True
except Exception:
    HAS_TAG_CACHE = False

CACHE_DIR_NAME = "data_cache"


class FilterWidget(QFrame):
    """필터 조건 위젯"""

    delete_requested = pyqtSignal(object)

    def __init__(self, columns: List[str], parent=None):
        super().__init__(parent)
        self.columns = columns
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)

        # 컬럼 선택
        self.column_combo = QComboBox()
        self.column_combo.addItems(self.columns)
        self.column_combo.setMinimumWidth(150)
        layout.addWidget(self.column_combo)

        # 연산자 선택
        self.operator_combo = QComboBox()
        self.operator_combo.addItems([">=", "<=", ">", "<", "=", "!=", "range"])
        self.operator_combo.setCurrentText("range")
        self.operator_combo.currentTextChanged.connect(self._on_operator_changed)
        layout.addWidget(self.operator_combo)

        # 단일 값 입력
        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText("값")
        self.value_edit.setMaximumWidth(80)
        layout.addWidget(self.value_edit)

        # 범위 입력
        self.min_edit = QLineEdit()
        self.min_edit.setPlaceholderText("최소")
        self.min_edit.setMaximumWidth(60)
        layout.addWidget(self.min_edit)

        self.range_label = QLabel("~")
        layout.addWidget(self.range_label)

        self.max_edit = QLineEdit()
        self.max_edit.setPlaceholderText("최대")
        self.max_edit.setMaximumWidth(60)
        layout.addWidget(self.max_edit)

        # 삭제 버튼
        delete_btn = QPushButton("✕")
        delete_btn.setMaximumWidth(30)
        delete_btn.clicked.connect(lambda: self.delete_requested.emit(self))
        layout.addWidget(delete_btn)

        layout.addStretch()
        self._on_operator_changed("range")

    def _on_operator_changed(self, operator: str):
        """연산자 변경 시"""
        is_range = operator == "range"
        self.value_edit.setVisible(not is_range)
        self.min_edit.setVisible(is_range)
        self.range_label.setVisible(is_range)
        self.max_edit.setVisible(is_range)

    def get_filter(self) -> Optional[Dict]:
        """필터 조건 반환"""
        column = self.column_combo.currentText()
        operator = self.operator_combo.currentText()

        if not column:
            return None

        if operator == "range":
            try:
                min_val = (
                    float(self.min_edit.text())
                    if self.min_edit.text()
                    else float("-inf")
                )
                max_val = (
                    float(self.max_edit.text())
                    if self.max_edit.text()
                    else float("inf")
                )
                return {
                    "column": column,
                    "operator": "range",
                    "min": min_val,
                    "max": max_val,
                }
            except ValueError:
                return None
        else:
            try:
                value = float(self.value_edit.text())
                return {"column": column, "operator": operator, "value": value}
            except ValueError:
                return None

    def update_columns(self, columns: List[str]):
        """컬럼 목록 업데이트"""
        current = self.column_combo.currentText()
        self.column_combo.clear()
        self.column_combo.addItems(columns)
        if current in columns:
            self.column_combo.setCurrentText(current)


class ProcessingThread(QThread):
    """전처리 실행 스레드"""

    progress_updated = pyqtSignal(int, str)
    log_message = pyqtSignal(str)
    finished_signal = pyqtSignal(bool)

    def __init__(self, app, settings: Dict, parent=None):
        super().__init__(parent)
        self.app = app
        self.settings = settings
        self.is_cancelled = False

    def run(self):
        """전처리 실행"""
        try:
            start_time = time.time()

            self.log_message.emit("\n" + "=" * 50)
            self.log_message.emit("🔄 전처리 시작...")
            self.app.preprocessor.reset_processing_state()

            # 1. 필터링
            self.progress_updated.emit(10, "필터링 적용 중...")

            filters = self.settings.get("filters", [])

            if filters:
                success, msg = self.app.preprocessor.apply_filters(filters)
                self.log_message.emit(f"{'✅' if success else '❌'} {msg}")
            else:
                self.app.preprocessor.processed_df = (
                    self.app.preprocessor.original_df.copy()
                )
                self.log_message.emit("ℹ️ 필터 없음 - 전체 데이터 사용")

            if self.is_cancelled:
                self.finished_signal.emit(False)
                return

            # 2. 이상값 처리
            self.progress_updated.emit(40, "이상값 처리 중...")

            outlier_settings = self.settings.get("outlier", {})
            if outlier_settings.get("apply", True):
                success, msg = self.app.preprocessor.remove_outliers(
                    method=outlier_settings.get("method", "2.5sigma"), action="drop"
                )
                self.log_message.emit(f"{'✅' if success else '❌'} {msg}")

            if self.is_cancelled:
                self.finished_signal.emit(False)
                return

            self.progress_updated.emit(75, "시간 처리 중...")

            time_settings = self.settings.get("time", {})
            if time_settings.get("normalize", False):
                interval = int(time_settings.get("interval") or 2)
                success, msg = self.app.preprocessor.normalize_timestamps(interval)
                self.log_message.emit(f"{'✅' if success else '❌'} {msg}")

            if time_settings.get("realign", False):
                start_time_str = time_settings.get("start_time", "")
                interval = int(time_settings.get("interval") or 2)
                success, msg = self.app.preprocessor.realign_timestamps(
                    start_time_str, interval
                )
                self.log_message.emit(f"{'✅' if success else '❌'} {msg}")

            elapsed = time.time() - start_time
            self.progress_updated.emit(100, "✅ 완료!")
            self.log_message.emit("")
            self.log_message.emit(self.app.preprocessor.get_summary())
            self.log_message.emit(f"\n⏱ 소요 시간: {elapsed:.2f}초")
            self.finished_signal.emit(True)

        except Exception as e:
            self.log_message.emit(f"❌ 오류: {str(e)}")
            self.finished_signal.emit(False)


class OpcFetchThread(QThread):
    """OPC 히스토리 데이터를 백그라운드에서 읽고 진행률을 시그널로 전달."""

    progress_updated = pyqtSignal(int, str)   # (percent, status_label)
    log_message = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, object)  # (success, DataFrame or None)

    def __init__(self, tag_name: str, start_str: str, end_str: str,
                 endpoint: str, namespace: int, chunk_minutes: int,
                 index_dir: str, parent=None):
        super().__init__(parent)
        self.tag_name = tag_name
        self.start_str = start_str
        self.end_str = end_str
        self.endpoint = endpoint
        self.namespace = namespace
        self.chunk_minutes = chunk_minutes
        self.index_dir = index_dir
        self.is_cancelled = False
        self._wall_start: float = 0.0

    def run(self):
        import time
        self._wall_start = time.time()

        def on_progress(current: int, total: int, chunk_time) -> None:
            if self.is_cancelled:
                return
            pct = int(current / total * 100) if total > 0 else 0
            elapsed = time.time() - self._wall_start
            eta_sec = int((elapsed / current) * (total - current)) if current > 0 else 0
            time_str = chunk_time.strftime("%Y-%m-%d %H:%M")
            eta_str = f"  |  ETA {eta_sec // 60}분 {eta_sec % 60}초" if current < total else ""
            self.progress_updated.emit(
                pct,
                f"읽는 중... {time_str}  ({current}/{total} chunks){eta_str}"
            )

        try:
            config = OpcReadConfig(
                endpoint=self.endpoint,
                namespace=self.namespace,
                chunk_minutes=self.chunk_minutes,
            )
            entry = find_entry(self.index_dir, self.tag_name)
            adapter = OpcUaReadAdapter(config)
            adapter.connect()
            self.log_message.emit(f"OPC 연결됨: {self.endpoint}")
            try:
                raw_rows = adapter.read_raw_history(
                    entry, self.start_str, self.end_str,
                    progress_callback=on_progress,
                    cancel_callback=lambda: self.is_cancelled,
                )
            finally:
                adapter.disconnect()

            if self.is_cancelled:
                self.finished_signal.emit(False, None)
                return

            elapsed = time.time() - self._wall_start
            self.log_message.emit(
                f"✅ OPC 완료: {len(raw_rows):,}행  ({elapsed:.1f}s)"
            )
            df = pd.DataFrame(raw_rows)
            self.finished_signal.emit(True, df)
        except Exception as exc:
            self.log_message.emit(f"❌ OPC 오류: {exc}")
            self.finished_signal.emit(False, None)


class DataPreprocessorMac(QMainWindow):
    """Mac용 데이터 전처리 애플리케이션"""

    def __init__(self):
        super().__init__()
        self.preprocessor = DataPreprocessor()
        self.preset_manager = PresetManager()
        self.current_file = None
        self.filter_widgets: List[FilterWidget] = []
        self.processing_thread = None
        self.opc_fetch_thread = None
        self.current_preset_name: Optional[str] = None
        self.validation_settings = {
            "ratio": 20,
            "segment_ratios": [25, 25, 25, 25],
            "sigma_start": 2.5,
            "sigma_end": 4.0,
        }

        self._setup_ui()
        self._create_menu()

    def _create_menu(self):
        """메뉴바 생성"""
        menubar = self.menuBar()

        # 파일 메뉴
        file_menu = menubar.addMenu("파일")

        open_action = QAction("열기...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._load_file)
        file_menu.addAction(open_action)

        save_action = QAction("저장...", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_file)
        file_menu.addAction(save_action)

        file_menu.addSeparator()

        quit_action = QAction("종료", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # 프리셋 메뉴
        preset_menu = menubar.addMenu("프리셋")

        save_preset = QAction("프리셋 저장...", self)
        save_preset.setShortcut("Ctrl+P")
        save_preset.triggered.connect(self._save_preset)
        preset_menu.addAction(save_preset)

        load_preset = QAction("프리셋 불러오기...", self)
        load_preset.triggered.connect(self._load_preset)
        preset_menu.addAction(load_preset)

        preset_menu.addSeparator()

        one_click = QAction("파일+프리셋 한번에 열기...", self)
        one_click.triggered.connect(self._load_file_with_preset)
        preset_menu.addAction(one_click)

        # 분석 메뉴
        analysis_menu = menubar.addMenu("분석")

        trend_action = QAction("📊 트렌드 차트...", self)
        trend_action.setShortcut("Ctrl+T")
        trend_action.triggered.connect(self._show_trend_chart)
        analysis_menu.addAction(trend_action)

        analysis_menu.addSeparator()

        validation_action = QAction("🧪 Validation 데이터 생성...", self)
        validation_action.setShortcut("Ctrl+Shift+S")
        validation_action.triggered.connect(self._show_simulation_dialog)
        analysis_menu.addAction(validation_action)

        # 도움말 메뉴
        help_menu = menubar.addMenu("도움말")

        manual_action = QAction("사용자 매뉴얼", self)
        manual_action.setShortcut("F1")
        manual_action.triggered.connect(self._show_manual)
        help_menu.addAction(manual_action)

        help_menu.addSeparator()

        about_action = QAction("프로그램 정보", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_ui(self):
        """UI 설정"""
        self.setWindowTitle(f"{APP_NAME} v{__version__}")
        self.setMinimumSize(900, 700)
        self.resize(950, 850)  # 1920x1080에 적합한 크기

        # 컴팩트 스타일 설정
        self.setStyleSheet("""
            QGroupBox { font-size: 11px; font-weight: bold; padding-top: 8px; margin-top: 4px; }
            QGroupBox::title { padding: 0 5px; }
            QLabel { font-size: 11px; }
            QPushButton { font-size: 11px; padding: 4px 8px; }
            QRadioButton, QCheckBox { font-size: 11px; }
            QLineEdit, QComboBox { font-size: 11px; padding: 2px; }
        """)

        # 메인 위젯
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # === OPC 데이터 불러오기 ===
        opc_group = QGroupBox("📡 OPC 데이터 불러오기")
        opc_layout = QVBoxLayout(opc_group)

        opc_row1 = QHBoxLayout()
        opc_row1.addWidget(QLabel("Tag:"))
        self.opc_tag_edit = QLineEdit()
        self.opc_tag_edit.setPlaceholderText("예) PJ1.BOILER.TEMP_01")
        self.opc_tag_edit.setMinimumWidth(200)
        opc_row1.addWidget(self.opc_tag_edit)

        opc_row1.addWidget(QLabel("시작:"))
        self.opc_start_edit = QLineEdit("2024-01-01 00:00:00")
        self.opc_start_edit.setMaximumWidth(140)
        opc_row1.addWidget(self.opc_start_edit)

        opc_row1.addWidget(QLabel("종료:"))
        self.opc_end_edit = QLineEdit(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.opc_end_edit.setMaximumWidth(140)
        opc_row1.addWidget(self.opc_end_edit)
        opc_row1.addStretch()
        opc_layout.addLayout(opc_row1)

        opc_row2 = QHBoxLayout()
        opc_row2.addWidget(QLabel("Endpoint:"))
        self.opc_endpoint_edit = QLineEdit("opc.tcp://192.9.110.151:51241/Capstone/OPCUAServer")
        opc_row2.addWidget(self.opc_endpoint_edit)

        opc_row2.addWidget(QLabel("NS:"))
        self.opc_ns_edit = QLineEdit("12")
        self.opc_ns_edit.setMaximumWidth(40)
        opc_row2.addWidget(self.opc_ns_edit)

        opc_row2.addWidget(QLabel("Chunk(분):"))
        self.opc_chunk_edit = QLineEdit("60")
        self.opc_chunk_edit.setMaximumWidth(45)
        opc_row2.addWidget(self.opc_chunk_edit)

        opc_row2.addWidget(QLabel("Index Dir:"))
        self.opc_index_edit = QLineEdit("opc_assets/tag_index")
        self.opc_index_edit.setMaximumWidth(160)
        opc_row2.addWidget(self.opc_index_edit)

        self.opc_fetch_btn = QPushButton("📥 불러오기")
        self.opc_fetch_btn.clicked.connect(self._run_opc_fetch)
        if not HAS_OPC:
            self.opc_fetch_btn.setEnabled(False)
            self.opc_fetch_btn.setToolTip("preprocessing_portal 모듈 또는 opcua 패키지 없음")
        opc_row2.addWidget(self.opc_fetch_btn)

        self.opc_cancel_btn = QPushButton("⏹ 취소")
        self.opc_cancel_btn.setEnabled(False)
        self.opc_cancel_btn.clicked.connect(self._cancel_opc_fetch)
        opc_row2.addWidget(self.opc_cancel_btn)
        opc_layout.addLayout(opc_row2)

        opc_cache_row = QHBoxLayout()
        self.cache_use_check = QCheckBox("📦 캐시 우선 사용")
        self.cache_use_check.setChecked(True)
        self.cache_use_check.setToolTip(
            "data_cache/ 에 해당 태그·기간이 있으면 OPC 대신 즉시 로드"
        )
        opc_cache_row.addWidget(self.cache_use_check)

        self.cache_auto_save_check = QCheckBox("자동 저장")
        self.cache_auto_save_check.setChecked(True)
        self.cache_auto_save_check.setToolTip(
            "OPC에서 가져온 데이터를 data_cache/<tag>.xlsx 에 자동 추가"
        )
        opc_cache_row.addWidget(self.cache_auto_save_check)

        self.cache_save_btn = QPushButton("💾 캐시에 저장")
        self.cache_save_btn.setToolTip(
            "현재 로드된 데이터를 data_cache/<tag>.xlsx 에 병합 저장"
        )
        self.cache_save_btn.clicked.connect(self._save_to_cache_manual)
        opc_cache_row.addWidget(self.cache_save_btn)

        self.cache_open_btn = QPushButton("📂 캐시 폴더 열기")
        self.cache_open_btn.clicked.connect(self._open_cache_dir)
        opc_cache_row.addWidget(self.cache_open_btn)

        opc_cache_row.addStretch()
        opc_layout.addLayout(opc_cache_row)

        if not HAS_TAG_CACHE:
            for widget in (
                self.cache_use_check,
                self.cache_auto_save_check,
                self.cache_save_btn,
                self.cache_open_btn,
            ):
                widget.setEnabled(False)
            self.cache_use_check.setToolTip("tag_cache 모듈을 사용할 수 없습니다")

        opc_group.setMaximumHeight(165)
        main_layout.addWidget(opc_group)

        # === 파일 선택 ===
        file_group = QGroupBox("📁 파일 선택")
        file_layout = QVBoxLayout(file_group)

        file_btn_layout = QHBoxLayout()
        load_btn = QPushButton("파일 불러오기")
        load_btn.clicked.connect(self._load_file)
        file_btn_layout.addWidget(load_btn)

        self.file_label = QLabel("파일을 선택해주세요")
        self.file_label.setStyleSheet("color: gray;")
        file_btn_layout.addWidget(self.file_label)
        file_btn_layout.addStretch()

        self.data_info_label = QLabel("")
        self.data_info_label.setStyleSheet("color: blue;")
        file_btn_layout.addWidget(self.data_info_label)

        file_layout.addLayout(file_btn_layout)

        # 미리보기 테이블 (컴팩트)
        self.preview_table = QTableWidget()
        self.preview_table.setMaximumHeight(100)
        self.preview_table.setStyleSheet("font-size: 10px;")
        file_layout.addWidget(self.preview_table)

        file_group.setMaximumHeight(160)
        main_layout.addWidget(file_group)

        # === 필터 조건 ===
        filter_group = QGroupBox("🔧 필터 조건 (AND 결합)")
        filter_layout = QVBoxLayout(filter_group)

        self.filters_container = QVBoxLayout()
        filter_layout.addLayout(self.filters_container)

        add_filter_btn = QPushButton("+ 필터 추가")
        add_filter_btn.clicked.connect(self._add_filter)
        filter_layout.addWidget(add_filter_btn, alignment=Qt.AlignLeft)

        main_layout.addWidget(filter_group)
        filter_group.setMaximumHeight(100)

        # === 이상값 처리 ===
        outlier_group = QGroupBox("📊 이상값 처리")
        outlier_layout = QVBoxLayout(outlier_group)

        method_layout = QHBoxLayout()
        method_layout.addWidget(QLabel("방법:"))

        self.outlier_method_group = QButtonGroup()
        for text, value in [
            ("2σ (95.4%)", "2sigma"),
            ("2.5σ (98.8%)", "2.5sigma"),
            ("3σ (99.7%)", "3sigma"),
            ("IQR", "iqr"),
        ]:
            rb = QRadioButton(text)
            rb.setProperty("value", value)
            self.outlier_method_group.addButton(rb)
            method_layout.addWidget(rb)
            if value == "2.5sigma":
                rb.setChecked(True)

        method_layout.addStretch()
        outlier_layout.addLayout(method_layout)

        action_layout = QHBoxLayout()
        action_layout.addWidget(QLabel("처리:"))
        self.outlier_drop = QRadioButton("행 전체 삭제")
        self.outlier_drop.setChecked(True)
        action_layout.addWidget(self.outlier_drop)
        action_layout.addStretch()
        outlier_layout.addLayout(action_layout)

        self.apply_outlier = QCheckBox("이상값 처리 적용")
        self.apply_outlier.setChecked(True)
        outlier_layout.addWidget(self.apply_outlier)

        outlier_group.setMaximumHeight(100)
        main_layout.addWidget(outlier_group)

        # === 시간 처리 ===
        time_group = QGroupBox("🕐 시간 처리 (선택사항)")
        time_layout = QVBoxLayout(time_group)

        self.apply_time_normalize = QCheckBox("시간 정규화 (2분 간격 스냅)")
        time_layout.addWidget(self.apply_time_normalize)

        self.apply_time_realign = QCheckBox("시간 재정렬 (새 시작 시간부터)")
        time_layout.addWidget(self.apply_time_realign)

        time_input_layout = QHBoxLayout()
        time_input_layout.addWidget(QLabel("   시작 시간:"))
        self.start_time_edit = QLineEdit(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.start_time_edit.setMaximumWidth(180)
        time_input_layout.addWidget(self.start_time_edit)
        time_input_layout.addWidget(QLabel("간격(분):"))
        self.interval_edit = QLineEdit("2")
        self.interval_edit.setMaximumWidth(50)
        time_input_layout.addWidget(self.interval_edit)
        time_input_layout.addStretch()
        time_layout.addLayout(time_input_layout)

        time_group.setMaximumHeight(90)
        main_layout.addWidget(time_group)

        # === 진행률 ===
        progress_group = QGroupBox("⏳ 진행 상황")
        progress_layout = QVBoxLayout(progress_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("대기 중...")
        progress_layout.addWidget(self.progress_label)

        progress_group.setMaximumHeight(70)
        main_layout.addWidget(progress_group)

        # === 실행 버튼 ===
        btn_layout = QHBoxLayout()

        self.process_btn = QPushButton("🚀 전처리 실행")
        self.process_btn.setStyleSheet("font-weight: bold; padding: 8px 16px;")
        self.process_btn.clicked.connect(self._run_preprocessing)
        btn_layout.addWidget(self.process_btn)

        self.validation_btn = QPushButton("🧪 Validation 데이터 생성")
        self.validation_btn.clicked.connect(self._show_simulation_dialog)
        btn_layout.addWidget(self.validation_btn)

        self.save_btn = QPushButton("💾 결과 저장")
        self.save_btn.clicked.connect(self._save_file)
        btn_layout.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("⏹ 취소")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_processing)
        btn_layout.addWidget(self.cancel_btn)

        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)

        # === 결과 표시 ===
        result_group = QGroupBox("📋 처리 결과")
        result_layout = QVBoxLayout(result_group)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setFont(QFont("Menlo", 9))
        self.result_text.setMaximumHeight(150)
        result_layout.addWidget(self.result_text)

        main_layout.addWidget(result_group)

    def _get_tag_cache(self):
        """data_cache/ 폴더 기준 TagCache 인스턴스. 모듈 없으면 None."""
        if not HAS_TAG_CACHE:
            return None
        cache_dir = Path(__file__).resolve().parent / CACHE_DIR_NAME
        return TagCache(cache_dir)

    def _try_load_from_cache(self, tag: str, start: str, end: str) -> bool:
        """캐시가 [start, end] 전체를 덮으면 즉시 로드. 성공 시 True."""
        cache = self._get_tag_cache()
        if cache is None or not cache.has_tag(tag):
            return False
        try:
            start_dt = pd.to_datetime(start).to_pydatetime()
            end_dt = pd.to_datetime(end).to_pydatetime()
        except Exception:
            return False
        if not cache.has_range(tag, start_dt, end_dt):
            coverage = cache.get_coverage(tag)
            if coverage is not None:
                self._log(
                    f"📦 캐시 부분 적중 — 캐시 범위 "
                    f"{coverage.first_time:%Y-%m-%d %H:%M} ~ "
                    f"{coverage.last_time:%Y-%m-%d %H:%M} (요청 기간 미포함, OPC로 재조회)"
                )
            return False
        try:
            df = cache.load_range(tag, start_dt, end_dt)
        except Exception as exc:
            self._log(f"⚠️ 캐시 로드 실패: {exc} (OPC로 재조회)")
            return False
        if df.empty:
            return False
        self._log(f"📦 캐시 적중: {len(df):,}행 (OPC 호출 생략)")
        self.progress_bar.setValue(100)
        self.progress_label.setText("캐시에서 로드 완료!")
        self._on_opc_finished(True, df, _from_cache=True)
        return True

    def _save_to_cache(self, tag: str, df) -> None:
        """전달받은 DataFrame을 data_cache/ 에 병합 저장."""
        cache = self._get_tag_cache()
        if cache is None or df is None or len(df) == 0:
            return
        try:
            total = cache.save(tag, df)
            self._log(
                f"💾 캐시 저장: {tag} — 누적 {total:,}행 → data_cache/{tag}.xlsx"
            )
        except Exception as exc:
            self._log(f"⚠️ 캐시 저장 실패: {exc}")

    def _save_to_cache_manual(self) -> None:
        """현재 전처리기에 로드된 데이터를 캐시에 수동 저장."""
        if self.preprocessor.original_df is None or self.preprocessor.original_df.empty:
            QMessageBox.information(self, "안내", "저장할 데이터가 없습니다.")
            return
        tag = self.opc_tag_edit.text().strip()
        if not tag:
            QMessageBox.warning(self, "경고", "Tag 이름이 비어있습니다.")
            return
        df = self.preprocessor.original_df.copy()
        date_col = self.preprocessor.date_column
        numeric_cols = [c for c in self.preprocessor.numeric_columns if c != date_col]
        if not date_col or not numeric_cols:
            QMessageBox.warning(
                self, "경고", "datetime/value 컬럼을 식별할 수 없습니다."
            )
            return
        cache_df = pd.DataFrame(
            {
                DATETIME_COLUMN: df[date_col],
                VALUE_COLUMN: df[numeric_cols[0]],
            }
        )
        self._save_to_cache(tag, cache_df)

    def _open_cache_dir(self) -> None:
        """OS 파일 탐색기에서 data_cache/ 열기."""
        cache_dir = Path(__file__).resolve().parent / CACHE_DIR_NAME
        cache_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform == "darwin":
            os.system(f'open "{cache_dir}"')
        elif sys.platform == "win32":
            os.startfile(str(cache_dir))  # type: ignore[attr-defined]
        else:
            os.system(f'xdg-open "{cache_dir}"')

    def _run_opc_fetch(self):
        """OPC 히스토리 불러오기 시작 (캐시 우선 사용)."""
        tag = self.opc_tag_edit.text().strip()
        start = self.opc_start_edit.text().strip()
        end = self.opc_end_edit.text().strip()
        endpoint = self.opc_endpoint_edit.text().strip()
        index_dir = self.opc_index_edit.text().strip()

        if not tag:
            QMessageBox.warning(self, "경고", "Tag 이름을 입력하세요.")
            return
        if not start or not end:
            QMessageBox.warning(self, "경고", "시작/종료 시간을 입력하세요.")
            return

        try:
            namespace = int(self.opc_ns_edit.text())
            chunk_minutes = int(self.opc_chunk_edit.text())
        except ValueError:
            QMessageBox.warning(self, "경고", "NS와 Chunk는 숫자여야 합니다.")
            return

        if HAS_TAG_CACHE and self.cache_use_check.isChecked():
            if self._try_load_from_cache(tag, start, end):
                return

        self.opc_fetch_btn.setEnabled(False)
        self.opc_cancel_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText("OPC 연결 중...")
        self._log(f"\n📡 OPC 불러오기: {tag}  {start} ~ {end}")

        self.opc_fetch_thread = OpcFetchThread(
            tag_name=tag,
            start_str=start,
            end_str=end,
            endpoint=endpoint,
            namespace=namespace,
            chunk_minutes=chunk_minutes,
            index_dir=index_dir,
        )
        self.opc_fetch_thread.progress_updated.connect(self._on_progress)
        self.opc_fetch_thread.log_message.connect(self._log)
        self.opc_fetch_thread.finished_signal.connect(self._on_opc_finished)
        self.opc_fetch_thread.start()

    def _cancel_opc_fetch(self):
        """OPC 불러오기 취소"""
        if self.opc_fetch_thread:
            self.opc_fetch_thread.is_cancelled = True
            self._log("⏹ OPC 불러오기 취소됨")

    def _on_opc_finished(self, success: bool, df, _from_cache: bool = False):
        """OPC 또는 캐시 로드 완료 처리.

        ``_from_cache`` 가 True 면 캐시에 다시 저장하지 않습니다.
        """
        self.opc_fetch_btn.setEnabled(True)
        self.opc_cancel_btn.setEnabled(False)
        if not success or df is None:
            self.progress_bar.setValue(0)
            self.progress_label.setText("OPC 불러오기 실패")
            return

        self.progress_bar.setValue(100)
        if not _from_cache:
            self.progress_label.setText("OPC 불러오기 완료!")

        tag = self.opc_tag_edit.text().strip()
        source_label = "CACHE" if _from_cache else "OPC"
        success2, msg = self.preprocessor.load_dataframe(
            df, source_name=f"{source_label}:{tag}"
        )
        if success2:
            self.current_file = None
            prefix = "📦" if _from_cache else "📡"
            self.file_label.setText(f"[{prefix} {source_label}] {tag}")
            self.file_label.setStyleSheet("color: darkblue;")
            rows = len(self.preprocessor.original_df)
            cols = len(self.preprocessor.columns)
            self.data_info_label.setText(f"📊 {rows:,}행 × {cols}열")
            self._update_preview()
            self._update_filter_columns()
            self._log(f"✅ {msg}")

            if (
                not _from_cache
                and HAS_TAG_CACHE
                and self.cache_auto_save_check.isChecked()
            ):
                self._save_to_cache(tag, df)
        else:
            self._log(f"⚠️ DataFrame 로드 실패: {msg}")

    def _load_file(self):
        """파일 로드"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "데이터 파일 선택",
            "",
            "Excel/CSV 파일 (*.xlsx *.csv);;Excel 파일 (*.xlsx);;CSV 파일 (*.csv);;모든 파일 (*.*)",
        )

        if not file_path:
            return

        # 대용량 파일 로딩 안내
        file_size = os.path.getsize(file_path)
        if file_size > DataPreprocessor.LARGE_FILE_BYTES:
            self.progress_label.setText("대용량 파일 로딩 중...")
            self.progress_bar.setValue(0)

        success, msg = self.preprocessor.load_data(file_path)

        if success:
            self.current_file = file_path
            self.file_label.setText(os.path.basename(file_path))
            self.file_label.setStyleSheet("color: black;")

            rows = len(self.preprocessor.original_df)
            cols = len(self.preprocessor.columns)
            self.data_info_label.setText(f"📊 {rows:,}행 × {cols}열")

            self._update_preview()
            self._update_filter_columns()
            self._log(f"✅ {msg}")
            self._log(
                f"   감지된 숫자 컬럼 ({len(self.preprocessor.numeric_columns)}개): {', '.join(self.preprocessor.numeric_columns[:10])}"
            )
            if len(self.preprocessor.numeric_columns) > 10:
                self._log(f"   ... 외 {len(self.preprocessor.numeric_columns) - 10}개")

            # 대용량 데이터 안내
            if rows >= DataPreprocessor.LARGE_DATA_WARNING_ROWS:
                self._log(
                    f"⚠️ 대용량 데이터 ({rows:,}행) - 처리에 시간이 소요될 수 있습니다."
                )

            self.progress_bar.setValue(100)
            self.progress_label.setText("파일 로드 완료!")
        else:
            self.progress_bar.setValue(0)
            self.progress_label.setText("파일 로드 실패")
            QMessageBox.critical(self, "오류", msg)

    def _update_preview(self):
        """미리보기 업데이트"""
        df = self.preprocessor.get_preview(5)
        if df.empty:
            return

        columns = list(df.columns)[: DataPreprocessor.MAX_PREVIEW_COLUMNS]
        self.preview_table.setColumnCount(len(columns))
        self.preview_table.setRowCount(len(df))
        self.preview_table.setHorizontalHeaderLabels(columns)

        for i, row in df.iterrows():
            for j, col in enumerate(columns):
                val = "" if pd.isna(row[col]) else str(row[col])
                self.preview_table.setItem(i, j, QTableWidgetItem(val[:20]))

        self.preview_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )

    def _update_filter_columns(self):
        """필터 컬럼 업데이트"""
        columns = self.preprocessor.numeric_columns
        for fw in self.filter_widgets:
            fw.update_columns(columns)

    def _add_filter(self):
        """필터 추가"""
        columns = (
            self.preprocessor.numeric_columns
            if self.preprocessor.numeric_columns
            else []
        )
        fw = FilterWidget(columns)
        fw.delete_requested.connect(self._remove_filter)
        self.filters_container.addWidget(fw)
        self.filter_widgets.append(fw)

    def _remove_filter(self, fw):
        """필터 제거"""
        if fw in self.filter_widgets:
            self.filter_widgets.remove(fw)
            fw.deleteLater()

    def _run_preprocessing(self):
        """전처리 실행"""
        if self.preprocessor.original_df is None:
            QMessageBox.warning(self, "경고", "먼저 데이터 파일을 로드해주세요.")
            return

        self.process_btn.setEnabled(False)
        self.validation_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

        settings = self._create_settings()
        self.processing_thread = ProcessingThread(self, settings)
        self.processing_thread.progress_updated.connect(self._on_progress)
        self.processing_thread.log_message.connect(self._log)
        self.processing_thread.finished_signal.connect(self._on_finished)
        self.processing_thread.start()

    def _on_progress(self, value, status):
        """진행률 업데이트"""
        self.progress_bar.setValue(value)
        self.progress_label.setText(status)

    def _on_finished(self, success):
        """처리 완료"""
        self.process_btn.setEnabled(True)
        self.validation_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self._update_preview()

    def _cancel_processing(self):
        """처리 취소"""
        if self.processing_thread:
            self.processing_thread.is_cancelled = True
            self._log("⏹ 취소됨")

    def _save_file(self):
        """결과 저장"""
        if self.preprocessor.processed_df is None:
            QMessageBox.warning(self, "경고", "저장할 데이터가 없습니다.")
            return

        default_name = ""
        if self.current_file:
            orig = Path(self.current_file)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"{orig.stem}_processed_{timestamp}{orig.suffix}"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "결과 저장", default_name, "CSV 파일 (*.csv);;Excel 파일 (*.xlsx)"
        )

        if not file_path:
            return

        success, result = self.preprocessor.save_data(file_path, self.current_file)

        if success:
            self._log(f"\n💾 저장 완료: {result}")
            QMessageBox.information(
                self, "저장 완료", f"파일이 저장되었습니다:\n{result}"
            )
        else:
            QMessageBox.critical(self, "저장 실패", result)

    def _log(self, message):
        """로그 추가"""
        self.result_text.append(message)

    def _save_preset(self):
        """프리셋 저장"""
        # 간단한 다이얼로그
        from PyQt5.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "프리셋 저장", "프리셋 이름:")
        if ok and name:
            settings = self._create_settings()
            if self.preset_manager.save_preset(name, settings, ""):
                self._log(f"💾 프리셋 저장: {name}")
                QMessageBox.information(
                    self, "저장 완료", f"프리셋 '{name}'이(가) 저장되었습니다."
                )

    def _load_preset(self):
        """프리셋 불러오기"""
        presets = self.preset_manager.list_presets()
        if not presets:
            QMessageBox.information(self, "알림", "저장된 프리셋이 없습니다.")
            return

        names = [p["name"] for p in presets]
        from PyQt5.QtWidgets import QInputDialog

        name, ok = QInputDialog.getItem(
            self, "프리셋 불러오기", "선택:", names, 0, False
        )
        if ok and name:
            preset = next((p for p in presets if p["name"] == name), None)
            if preset:
                data = self.preset_manager.load_preset(preset["path"])
                if data:
                    self._apply_settings(data["settings"])
                    self._log(f"📂 프리셋 로드: {name}")

    def _load_file_with_preset(self):
        """파일+프리셋 한번에"""
        presets = self.preset_manager.list_presets()
        if not presets:
            QMessageBox.information(self, "알림", "저장된 프리셋이 없습니다.")
            return

        names = [p["name"] for p in presets]
        from PyQt5.QtWidgets import QInputDialog

        name, ok = QInputDialog.getItem(
            self, "프리셋 선택", "적용할 프리셋:", names, 0, False
        )
        if not ok:
            return

        preset = next((p for p in presets if p["name"] == name), None)
        if not preset:
            return

        # 파일 선택
        self._load_file()
        if self.preprocessor.original_df is None:
            return

        # 프리셋 적용
        data = self.preset_manager.load_preset(preset["path"])
        if data:
            self._apply_settings(data["settings"])
            self._log(f"📂 프리셋 적용: {name}")
            # 자동 실행
            self._run_preprocessing()

    def _create_settings(self) -> Dict:
        """현재 GUI 상태에서 설정 딕셔너리를 추출합니다."""
        filters = []
        for fw in self.filter_widgets:
            f = fw.get_filter()
            if f:
                filters.append(f)

        return {
            "filters": filters,
            "outlier": {
                "apply": self.apply_outlier.isChecked(),
                "method": self.outlier_method_group.checkedButton().property("value")
                if self.outlier_method_group.checkedButton()
                else "2.5sigma",
                "action": "drop",
            },
            "time": {
                "normalize": self.apply_time_normalize.isChecked(),
                "realign": self.apply_time_realign.isChecked(),
                "start_time": self.start_time_edit.text(),
                "interval": self.interval_edit.text(),
            },
            "validation": {
                "ratio": self.validation_settings.get("ratio", 20),
                "segment_ratios": self.validation_settings.get(
                    "segment_ratios", [25, 25, 25, 25]
                ),
                "sigma_start": self.validation_settings.get("sigma_start", 2.5),
                "sigma_end": self.validation_settings.get("sigma_end", 4.0),
            },
        }

    def _apply_settings(self, settings: Dict):
        """설정 딕셔너리를 GUI에 적용합니다."""
        # 기존 필터 제거
        for fw in self.filter_widgets[:]:
            self._remove_filter(fw)

        # 필터 추가
        for f in settings.get("filters", []):
            self._add_filter()
            fw = self.filter_widgets[-1]
            fw.column_combo.setCurrentText(f.get("column", ""))
            fw.operator_combo.setCurrentText(f.get("operator", "range"))
            if f.get("operator") == "range":
                fw.min_edit.setText(str(f.get("min", "")))
                fw.max_edit.setText(str(f.get("max", "")))
            else:
                fw.value_edit.setText(str(f.get("value", "")))

        # 이상값 처리 설정
        outlier = settings.get("outlier", {})
        self.apply_outlier.setChecked(outlier.get("apply", True))
        self.outlier_drop.setChecked(True)

        # 이상값 방법 설정
        target_method = outlier.get("method", "2.5sigma")
        for btn in self.outlier_method_group.buttons():
            if btn.property("value") == target_method:
                btn.setChecked(True)
                break

        # 시간 처리 설정
        time_settings = settings.get("time", {})
        self.apply_time_normalize.setChecked(time_settings.get("normalize", False))
        self.apply_time_realign.setChecked(time_settings.get("realign", False))
        self.start_time_edit.setText(time_settings.get("start_time", ""))
        self.interval_edit.setText(time_settings.get("interval", "2"))

        # Validation 설정
        validation = settings.get("validation", {})
        self.validation_settings = {
            "ratio": validation.get("ratio", 20),
            "segment_ratios": validation.get("segment_ratios", [25, 25, 25, 25]),
            "sigma_start": validation.get("sigma_start", 2.5),
            "sigma_end": validation.get("sigma_end", 4.0),
        }

    def _show_manual(self):
        """매뉴얼 표시"""
        import webbrowser

        manual_path = Path(__file__).parent / "MANUAL.html"

        if manual_path.exists():
            webbrowser.open(f"file://{manual_path.absolute()}")
        else:
            QMessageBox.information(
                self,
                "알림",
                "매뉴얼 파일을 찾을 수 없습니다.\nMANUAL.html 파일을 확인하세요.",
            )

    def _show_about(self):
        """프로그램 정보 (내장 정보 사용)"""
        from version import (
            __version__,
            APP_NAME,
            FEATURES,
            CHANGELOG,
            get_developer_info,
        )

        dev = get_developer_info()

        # About 다이얼로그
        dialog = QDialog(self)
        dialog.setWindowTitle("프로그램 정보")
        dialog.resize(500, 500)
        layout = QVBoxLayout(dialog)

        # 프로그램 정보
        info_text = f"""<h2>{APP_NAME}</h2>
<p><b>버전:</b> {__version__}</p>
<p><b>플랫폼:</b> Mac (PyQt5)</p>

<h3>주요 기능</h3>
<ul>
{"".join(f"<li>{f}</li>" for f in FEATURES)}
</ul>

<h3>개발자 정보</h3>
<p><b>이름:</b> {dev.get("name", "-")}</p>
<p><b>조직:</b> {dev.get("organization", "-")}</p>
<p><b>이메일:</b> {dev.get("email", "-")}</p>
"""

        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # 패치노트 버튼
        changelog_btn = QPushButton("📋 패치노트 보기")

        def show_changelog():
            ch_dialog = QDialog(dialog)
            ch_dialog.setWindowTitle("패치노트")
            ch_dialog.resize(500, 400)
            ch_layout = QVBoxLayout(ch_dialog)
            ch_text = QTextEdit()
            ch_text.setReadOnly(True)
            ch_text.setPlainText(CHANGELOG.strip())
            ch_layout.addWidget(ch_text)
            QPushButton("닫기", clicked=ch_dialog.close).setParent(ch_dialog)
            ch_layout.addWidget(QPushButton("닫기", clicked=ch_dialog.close))
            ch_dialog.exec_()

        changelog_btn.clicked.connect(show_changelog)
        layout.addWidget(changelog_btn)

        # 닫기
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)

        dialog.exec_()

    def _get_validation_output_paths(self) -> Dict[str, str]:
        """Validation 자동 저장 파일 경로 계산"""
        if self.current_file:
            original = Path(self.current_file)
            base_dir = original.parent
            base_name = original.stem
        else:
            base_dir = Path.cwd()
            base_name = "processed_data"

        return {
            "prepro": str(base_dir / f"{base_name}_prepro.xlsx"),
            "prepro_with_valid": str(base_dir / f"{base_name}_prepro_with_valid.xlsx"),
            "valid": str(base_dir / f"{base_name}_valid.xlsx"),
        }

    def _show_simulation_dialog(self):
        """Validation 데이터 생성 다이얼로그"""
        if self.preprocessor.processed_df is None:
            QMessageBox.warning(
                self, "경고", "먼저 데이터를 로드하고 전처리를 실행하세요."
            )
            return

        # OPC 등 메모리 기반 데이터는 원본 파일 경로가 없어도 기본 경로로 저장합니다.
        # 제거된 행 확인
        summary = self.preprocessor.get_removed_rows_summary()
        if summary["total"] == 0:
            QMessageBox.warning(
                self,
                "경고",
                "제거된 이상값이 없습니다.\n필터링 또는 이상값 처리를 먼저 실행하세요.",
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("🧪 Validation 데이터 생성")
        dialog.resize(760, 680)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(5)

        # 설명
        info_label = QLabel(
            f"<b>Validation 데이터 자동 생성</b><br>"
            f"전처리 결과를 기준으로 validation 블록을 새로 만들고 원본 폴더에 3개 파일을 자동 저장합니다.<br>"
            f"<b>제거된 데이터: {summary['total']}행</b>"
        )
        info_label.setStyleSheet("padding: 5px; background: #e8f4fd; font-size: 11px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # 설정
        settings_group = QGroupBox("설정")
        settings_layout = QVBoxLayout(settings_group)

        # 대상 컬럼 선택 (다중 선택 가능)
        target_group = QGroupBox("🎯 이상값 발생 컬럼 (다중 선택 가능)")
        target_layout = QVBoxLayout(target_group)

        target_hint = QLabel(
            "Ctrl+클릭으로 다중 선택. 선택한 컬럼들만 이상값으로 변화합니다."
        )
        target_hint.setStyleSheet("color: gray; font-size: 10px;")
        target_layout.addWidget(target_hint)

        target_list = QListWidget()
        target_list.setSelectionMode(QListWidget.MultiSelection)
        target_list.setMaximumHeight(70)
        for col in self.preprocessor.numeric_columns:
            target_list.addItem(col)
        if target_list.count() > 0:
            target_list.item(0).setSelected(True)
        target_layout.addWidget(target_list)

        # 전체 선택/해제 버튼
        btn_layout2 = QHBoxLayout()
        select_all = QPushButton("전체 선택")
        select_all.clicked.connect(
            lambda: [
                target_list.item(i).setSelected(True)
                for i in range(target_list.count())
            ]
        )
        btn_layout2.addWidget(select_all)
        clear_all = QPushButton("전체 해제")
        clear_all.clicked.connect(
            lambda: [
                target_list.item(i).setSelected(False)
                for i in range(target_list.count())
            ]
        )
        btn_layout2.addWidget(clear_all)
        btn_layout2.addStretch()
        target_layout.addLayout(btn_layout2)

        settings_layout.addWidget(target_group)

        # 설명
        explain_label = QLabel(
            "💡 선택한 태그만 validation 구간에서 점진적으로 이상값으로 이동합니다.\n"
            "   다른 컬럼은 최근 추세를 최대한 유지합니다."
        )
        explain_label.setStyleSheet(
            "color: #666; font-size: 10px; padding: 5px; background: #f5f5f5;"
        )
        settings_layout.addWidget(explain_label)

        # Validation 비율 및 Sigma 설정
        ratio_layout = QHBoxLayout()

        ratio_layout.addWidget(QLabel("Validation 비율:"))
        validation_ratio_spin = QSpinBox()
        validation_ratio_spin.setRange(5, 50)
        validation_ratio_spin.setValue(int(self.validation_settings.get("ratio", 20)))
        validation_ratio_spin.setSuffix(" %")
        ratio_layout.addWidget(validation_ratio_spin)

        ratio_layout.addWidget(QLabel("Sigma 시작/끝:"))
        sigma_start_spin = QDoubleSpinBox()
        sigma_start_spin.setRange(1.0, 6.0)
        sigma_start_spin.setSingleStep(0.5)
        sigma_start_spin.setValue(
            float(self.validation_settings.get("sigma_start", 2.5))
        )
        ratio_layout.addWidget(sigma_start_spin)

        ratio_layout.addWidget(QLabel("~"))
        sigma_end_spin = QDoubleSpinBox()
        sigma_end_spin.setRange(1.5, 8.0)
        sigma_end_spin.setSingleStep(0.5)
        sigma_end_spin.setValue(float(self.validation_settings.get("sigma_end", 4.0)))
        ratio_layout.addWidget(sigma_end_spin)
        ratio_layout.addWidget(QLabel("σ"))

        ratio_layout.addStretch()
        settings_layout.addLayout(ratio_layout)

        # Validation 내부 비율 (4 세그먼트)
        segment_group = QGroupBox("Validation 내부 비율 (합계 100%)")
        segment_layout = QVBoxLayout(segment_group)

        default_segments = self.validation_settings.get(
            "segment_ratios", [25, 25, 25, 25]
        )
        segment_labels = ["정상1", "제거행", "정상2", "Sigma"]
        segment_spins = []

        for idx, label in enumerate(segment_labels):
            row_layout = QHBoxLayout()
            row_layout.addWidget(QLabel(f"{label}:"))
            spin = QSpinBox()
            spin.setRange(0, 100)
            spin.setValue(int(default_segments[idx]))
            spin.setSuffix(" %")
            segment_spins.append(spin)
            row_layout.addWidget(spin)
            row_layout.addStretch()
            segment_layout.addLayout(row_layout)

        settings_layout.addWidget(segment_group)
        layout.addWidget(settings_group)

        # 예상 결과
        preview_label = QLabel()
        preview_label.setWordWrap(True)
        layout.addWidget(preview_label)

        file_preview_label = QLabel()
        file_preview_label.setStyleSheet("color: gray; font-size: 10px;")
        file_preview_label.setWordWrap(True)
        layout.addWidget(file_preview_label)

        def update_preview():
            try:
                original_rows = len(self.preprocessor.processed_df)
                validation_rows = max(
                    4, int(round(original_rows * (validation_ratio_spin.value() / 100)))
                )
                segment_ratios = [s.value() for s in segment_spins]
                ratio_sum = sum(segment_ratios)
                segment_lengths = (
                    self.preprocessor._allocate_segment_lengths(
                        validation_rows, segment_ratios
                    )
                    if ratio_sum > 0
                    else [0, 0, 0, 0]
                )
                paths = self._get_validation_output_paths()
                preview_label.setText(
                    f"<b>예상 결과:</b> 원본 {original_rows:,}행 + validation {validation_rows:,}행 = 총 {original_rows + validation_rows:,}행<br>"
                    f"- 정상1 {segment_lengths[0]:,}행 / 제거행 {segment_lengths[1]:,}행 / 정상2 {segment_lengths[2]:,}행 / Sigma {segment_lengths[3]:,}행<br>"
                    f"- 비율 합계: {ratio_sum}%"
                )
                file_preview_label.setText(
                    f"자동 저장 파일:\n"
                    f"1) {paths['prepro']}\n"
                    f"2) {paths['prepro_with_valid']}\n"
                    f"3) {paths['valid']}"
                )
            except Exception:
                pass

        validation_ratio_spin.valueChanged.connect(update_preview)
        sigma_start_spin.valueChanged.connect(update_preview)
        sigma_end_spin.valueChanged.connect(update_preview)
        for spin in segment_spins:
            spin.valueChanged.connect(update_preview)
        update_preview()

        # 결과 표시
        result_text = QTextEdit()
        result_text.setReadOnly(True)
        result_text.setMaximumHeight(80)
        layout.addWidget(result_text)

        # 버튼
        btn_layout = QHBoxLayout()

        def generate():
            # 선택된 컬럼 수집
            selected_columns = []
            for i in range(target_list.count()):
                if target_list.item(i).isSelected():
                    selected_columns.append(target_list.item(i).text())

            if not selected_columns:
                QMessageBox.warning(
                    dialog, "경고", "이상값 발생 컬럼을 최소 1개 선택하세요."
                )
                return

            segment_ratios = [s.value() for s in segment_spins]
            if sum(segment_ratios) != 100:
                QMessageBox.warning(
                    dialog, "경고", "Validation 내부 비율의 합계는 100이어야 합니다."
                )
                return

            sigma_start = float(sigma_start_spin.value())
            sigma_end = float(sigma_end_spin.value())
            if sigma_start <= 0 or sigma_end <= 0 or sigma_end < sigma_start:
                QMessageBox.warning(
                    dialog, "경고", "Sigma 시작/끝 값을 다시 확인하세요."
                )
                return

            self.validation_settings = {
                "ratio": validation_ratio_spin.value(),
                "segment_ratios": segment_ratios,
                "sigma_start": sigma_start,
                "sigma_end": sigma_end,
            }

            result_text.setText(
                f"Validation 데이터 생성 중...\n대상 컬럼: {', '.join(selected_columns)}"
            )
            QApplication.processEvents()

            try:
                interval_minutes = int(self.interval_edit.text())
            except ValueError:
                interval_minutes = self.preprocessor._infer_interval_minutes()

            success, msg, paths = self.preprocessor.generate_validation_outputs(
                target_columns=selected_columns,
                validation_ratio=validation_ratio_spin.value() / 100,
                segment_ratios=segment_ratios,
                sigma_start=sigma_start,
                sigma_end=sigma_end,
                interval_minutes=interval_minutes,
                original_path=self.current_file,
            )

            result_text.clear()
            if success:
                result_text.setText(f"✅ {msg}")
                self._log(
                    f"✅ Validation 데이터 생성 완료 ({len(selected_columns)}개 컬럼)"
                )
                self._log(f"   - 전처리본: {paths.get('prepro', '-')}")
                self._log(
                    f"   - 전처리+Validation: {paths.get('prepro_with_valid', '-')}"
                )
                self._log(f"   - Validation 전용: {paths.get('valid', '-')}")
                QMessageBox.information(dialog, "생성 완료", msg)
            else:
                result_text.setText(f"❌ {msg}")
                QMessageBox.critical(dialog, "오류", msg)

        generate_btn = QPushButton("💾 3개 파일 자동 생성")
        generate_btn.clicked.connect(generate)
        btn_layout.addWidget(generate_btn)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(dialog.close)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        dialog.exec_()

    def _show_trend_chart(self):
        """트렌드 + 정규분포도 전처리 전/후 비교 차트"""
        if self.preprocessor.original_df is None:
            QMessageBox.warning(self, "경고", "먼저 데이터를 로드하세요.")
            return

        try:
            import matplotlib
            matplotlib.use("Qt5Agg")
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
            from matplotlib.figure import Figure
            import matplotlib.pyplot as plt
            import numpy as np
            plt.rcParams["font.family"] = ["AppleGothic", "Malgun Gothic", "NanumGothic", "sans-serif"]
            plt.rcParams["axes.unicode_minus"] = False
        except ImportError:
            QMessageBox.critical(self, "오류", "matplotlib이 설치되지 않았습니다.\npip install matplotlib")
            return

        orig_df = self.preprocessor.original_df
        proc_df = self.preprocessor.processed_df
        preprocessed = (
            proc_df is not None
            and len(proc_df) != len(orig_df)
        )

        dialog = QDialog(self)
        dialog.setWindowTitle("📊 전처리 전/후 비교")
        dialog.resize(1100, 820)
        root = QVBoxLayout(dialog)

        # ── 상단 컨트롤 ──────────────────────────────────────────
        ctrl = QHBoxLayout()

        col_group = QGroupBox("컬럼 선택 (Ctrl+클릭 다중)")
        col_vbox = QVBoxLayout(col_group)
        column_list = QListWidget()
        column_list.setSelectionMode(QListWidget.ExtendedSelection)
        column_list.addItems(self.preprocessor.numeric_columns)
        column_list.setMaximumHeight(110)
        if self.preprocessor.numeric_columns:
            column_list.item(0).setSelected(True)
        col_vbox.addWidget(column_list)
        ctrl.addWidget(col_group)

        opt_group = QGroupBox("옵션")
        opt_vbox = QVBoxLayout(opt_group)
        show_mean_chk = QCheckBox("평균선")
        show_mean_chk.setChecked(True)
        show_removed_chk = QCheckBox("제거된 점 표시 (빨간 마커)")
        show_removed_chk.setChecked(True)
        show_kde_chk = QCheckBox("정규분포 피팅 곡선")
        show_kde_chk.setChecked(True)
        for w in (show_mean_chk, show_removed_chk, show_kde_chk):
            opt_vbox.addWidget(w)
        ctrl.addWidget(opt_group)

        refresh_btn = QPushButton("🔄 업데이트")
        ctrl.addWidget(refresh_btn)
        ctrl.addStretch()
        root.addLayout(ctrl)

        # 전처리 미실행 안내
        if not preprocessed:
            notice = QLabel("ℹ️  전처리 실행 전입니다. 전처리 후 재열람하면 전/후 비교를 볼 수 있습니다.")
            notice.setStyleSheet("color: gray; font-size: 10px; padding: 2px 4px;")
            root.addWidget(notice)

        # ── 탭 ───────────────────────────────────────────────────
        tabs = QTabWidget()

        trend_widget = QWidget()
        trend_vbox = QVBoxLayout(trend_widget)
        trend_fig = Figure(figsize=(12, 5), dpi=100)
        trend_canvas = FigureCanvas(trend_fig)
        trend_vbox.addWidget(trend_canvas)
        tabs.addTab(trend_widget, "📈 트렌드 비교")

        dist_widget = QWidget()
        dist_vbox = QVBoxLayout(dist_widget)
        dist_fig = Figure(figsize=(12, 5), dpi=100)
        dist_canvas = FigureCanvas(dist_fig)
        dist_vbox.addWidget(dist_canvas)
        tabs.addTab(dist_widget, "📊 분포도 비교")

        root.addWidget(tabs)

        # ── 통계 요약 ─────────────────────────────────────────────
        stats_text = QTextEdit()
        stats_text.setReadOnly(True)
        stats_text.setMaximumHeight(85)
        stats_text.setStyleSheet("font-family: Menlo; font-size: 10px;")
        root.addWidget(stats_text)

        COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]

        def removed_index(col: str):
            """전처리에서 제거된 원본 행 인덱스."""
            if proc_df is None or not preprocessed:
                return orig_df.index[[False] * len(orig_df)]
            source_indices = self.preprocessor.get_removed_source_indices()
            if source_indices:
                return orig_df.index.intersection(source_indices)
            return orig_df.index.difference(proc_df.index)

        # ── 트렌드 탭 ─────────────────────────────────────────────
        def update_trend():
            cols = [item.text() for item in column_list.selectedItems()][:5]
            if not cols:
                return
            trend_fig.clear()
            n = len(cols)
            axes = trend_fig.subplots(n, 1, sharex=True) if n > 1 else [trend_fig.add_subplot(111)]
            date_col = self.preprocessor.date_column

            for ax, col, color in zip(axes, cols, COLORS):
                # x축 값 추출
                def x_of(df):
                    if date_col and date_col in df.columns:
                        return df[date_col]
                    return df.index.to_series()

                x_orig = x_of(orig_df)
                y_orig = orig_df[col]

                # 전처리 전 (회색)
                ax.plot(x_orig, y_orig,
                        color="#bbbbbb", linewidth=0.7, alpha=0.85,
                        label="전처리 전", zorder=1)

                # 전처리 후 (컬러)
                if proc_df is not None and col in proc_df.columns:
                    x_proc = x_of(proc_df)
                    ax.plot(x_proc, proc_df[col],
                            color=color, linewidth=0.9, alpha=0.9,
                            label="전처리 후", zorder=2)

                # 제거된 점 (빨간 마커)
                if show_removed_chk.isChecked() and preprocessed:
                    rem_idx = removed_index(col)
                    if len(rem_idx):
                        rem_mask = orig_df.index.isin(rem_idx)
                        ax.scatter(
                            x_orig[rem_mask], y_orig[rem_mask],
                            color="red", s=18, zorder=3,
                            label=f"제거 ({len(rem_idx):,}개)", alpha=0.75,
                        )

                # 평균선
                if show_mean_chk.isChecked():
                    ax.axhline(y_orig.mean(), color="#aaaaaa", linestyle="--",
                               linewidth=0.8, alpha=0.7)
                    if proc_df is not None and col in proc_df.columns:
                        ax.axhline(proc_df[col].mean(), color=color,
                                   linestyle="--", linewidth=0.8, alpha=0.55)

                ax.set_ylabel(col, fontsize=8)
                ax.legend(loc="upper right", fontsize=7)
                ax.grid(True, alpha=0.22)

            if date_col:
                trend_fig.autofmt_xdate()
            trend_fig.tight_layout(h_pad=0.4)
            trend_canvas.draw()

        # ── 분포도 탭 ─────────────────────────────────────────────
        def update_dist():
            cols = [item.text() for item in column_list.selectedItems()][:4]
            if not cols:
                return
            dist_fig.clear()
            n = len(cols)
            axes = dist_fig.subplots(1, n) if n > 1 else [dist_fig.add_subplot(111)]
            stat_lines = []

            for ax, col in zip(axes, cols):
                o = orig_df[col].dropna()
                p = proc_df[col].dropna() if proc_df is not None and col in proc_df.columns else o

                bins = min(60, max(15, len(p) // 30))
                lo = min(o.min(), p.min())
                hi = max(o.max(), p.max())
                x_fit = np.linspace(lo, hi, 300)

                # 히스토그램
                ax.hist(o, bins=bins, range=(lo, hi), alpha=0.35,
                        color="steelblue", density=True, label="전처리 전")
                ax.hist(p, bins=bins, range=(lo, hi), alpha=0.45,
                        color="darkorange", density=True, label="전처리 후")

                # 정규분포 피팅 곡선
                if show_kde_chk.isChecked():
                    try:
                        from scipy import stats as sp
                        mu_o, sd_o = sp.norm.fit(o)
                        mu_p, sd_p = sp.norm.fit(p)
                        ax.plot(x_fit, sp.norm.pdf(x_fit, mu_o, sd_o),
                                color="steelblue", linewidth=2,
                                label=f"정규분포 전  μ={mu_o:.2f} σ={sd_o:.2f}")
                        ax.plot(x_fit, sp.norm.pdf(x_fit, mu_p, sd_p),
                                color="darkorange", linewidth=2,
                                label=f"정규분포 후  μ={mu_p:.2f} σ={sd_p:.2f}")
                    except ImportError:
                        # scipy 없으면 numpy로 직접 계산
                        mu_o, sd_o = float(o.mean()), float(o.std())
                        mu_p, sd_p = float(p.mean()), float(p.std())
                        def pdf(x, m, s):
                            if s == 0:
                                return np.zeros_like(x, dtype=float)
                            return np.exp(-0.5 * ((x - m) / s) ** 2) / (s * np.sqrt(2 * np.pi))

                        ax.plot(x_fit, pdf(x_fit, mu_o, sd_o), color="steelblue", linewidth=2,
                                label=f"정규분포 전  μ={mu_o:.2f} σ={sd_o:.2f}")
                        ax.plot(x_fit, pdf(x_fit, mu_p, sd_p), color="darkorange", linewidth=2,
                                label=f"정규분포 후  μ={mu_p:.2f} σ={sd_p:.2f}")

                removed_n = len(o) - len(p)
                pct = removed_n / len(o) * 100 if len(o) else 0
                ax.set_title(f"{col}\n제거 {removed_n:,}행 ({pct:.1f}%)", fontsize=9)
                ax.legend(fontsize=7)
                ax.grid(True, alpha=0.22)
                ax.set_xlabel("값")
                ax.set_ylabel("밀도")

                d_mu = p.mean() - o.mean()
                d_sd = p.std() - o.std()
                stat_lines.append(
                    f"[{col}]  "
                    f"전: n={len(o):,}  μ={o.mean():.4f}  σ={o.std():.4f}  "
                    f"후: n={len(p):,}  μ={p.mean():.4f}  σ={p.std():.4f}  "
                    f"Δμ={d_mu:+.4f}  Δσ={d_sd:+.4f}  제거={removed_n:,}"
                )

            dist_fig.tight_layout()
            dist_canvas.draw()
            stats_text.setText("\n".join(stat_lines))

        def update_all():
            update_trend()
            update_dist()

        def on_tab_changed(idx):
            if idx == 0:
                update_trend()
            else:
                update_dist()

        refresh_btn.clicked.connect(update_all)
        column_list.itemSelectionChanged.connect(update_all)
        show_mean_chk.stateChanged.connect(update_trend)
        show_removed_chk.stateChanged.connect(update_trend)
        show_kde_chk.stateChanged.connect(update_dist)
        tabs.currentChanged.connect(on_tab_changed)

        update_all()

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(dialog.close)
        root.addWidget(close_btn)

        dialog.exec_()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # 크로스 플랫폼 스타일

    window = DataPreprocessorMac()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
