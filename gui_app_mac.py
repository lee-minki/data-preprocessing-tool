"""
데이터 전처리 GUI 애플리케이션 - Mac 버전 (PyQt5)
- PyQt5 기반 사용자 인터페이스
- macOS 호환
- 파일 로드, 필터링, 이상값 처리, 저장 기능
"""

import sys
import os
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QPushButton, QLabel, QComboBox, QLineEdit, QCheckBox,
    QRadioButton, QButtonGroup, QProgressBar, QTextEdit, QTableWidget,
    QTableWidgetItem, QFileDialog, QMessageBox, QDialog, QDialogButtonBox,
    QListWidget, QMenuBar, QMenu, QAction, QScrollArea, QFrame,
    QSplitter, QHeaderView
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

# 핵심 로직 임포트
from data_preprocessor import DataPreprocessor
from preset_manager import PresetManager, create_settings_from_gui, apply_settings_to_gui
from version import __version__, APP_NAME


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
        self.operator_combo.addItems(['>=', '<=', '>', '<', '=', '!=', 'range'])
        self.operator_combo.setCurrentText('range')
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
        self._on_operator_changed('range')
    
    def _on_operator_changed(self, operator: str):
        """연산자 변경 시"""
        is_range = operator == 'range'
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
        
        if operator == 'range':
            try:
                min_val = float(self.min_edit.text()) if self.min_edit.text() else float('-inf')
                max_val = float(self.max_edit.text()) if self.max_edit.text() else float('inf')
                return {'column': column, 'operator': 'range', 'min': min_val, 'max': max_val}
            except ValueError:
                return None
        else:
            try:
                value = float(self.value_edit.text())
                return {'column': column, 'operator': operator, 'value': value}
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
    
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.is_cancelled = False
    
    def run(self):
        """전처리 실행"""
        try:
            start_time = time.time()
            
            self.log_message.emit("\n" + "="*50)
            self.log_message.emit(f"🔄 전처리 시작...")
            
            # 1. 필터링
            self.progress_updated.emit(10, "필터링 적용 중...")
            
            filters = []
            for fw in self.app.filter_widgets:
                f = fw.get_filter()
                if f:
                    filters.append(f)
            
            if filters:
                success, msg = self.app.preprocessor.apply_filters(filters)
                self.log_message.emit(f"{'✅' if success else '❌'} {msg}")
            else:
                self.app.preprocessor.processed_df = self.app.preprocessor.original_df.copy()
                self.log_message.emit("ℹ️ 필터 없음 - 전체 데이터 사용")
            
            if self.is_cancelled:
                return
            
            # 2. 이상값 처리
            self.progress_updated.emit(40, "이상값 처리 중...")
            
            if self.app.apply_outlier.isChecked():
                method = self.app.outlier_method_group.checkedButton().property('value')
                action = 'drop' if self.app.outlier_drop.isChecked() else 'nan'
                
                success, msg = self.app.preprocessor.remove_outliers(method=method, action=action)
                self.log_message.emit(f"{'✅' if success else '❌'} {msg}")
            
            if self.is_cancelled:
                return
            
            # 3. 정규화
            self.progress_updated.emit(60, "정규화 중...")
            
            if self.app.apply_normalize.isChecked():
                method = 'zscore' if self.app.norm_zscore.isChecked() else 'minmax'
                success, msg = self.app.preprocessor.normalize_data(method=method)
                self.log_message.emit(f"{'✅' if success else '❌'} {msg}")
            
            # 4. 시간 정규화
            self.progress_updated.emit(75, "시간 처리 중...")
            
            if self.app.apply_time_normalize.isChecked():
                interval = int(self.app.interval_edit.text() or 2)
                success, msg = self.app.preprocessor.normalize_timestamps(interval)
                self.log_message.emit(f"{'✅' if success else '❌'} {msg}")
            
            # 5. 시간 재정렬
            if self.app.apply_time_realign.isChecked():
                start_time_str = self.app.start_time_edit.text()
                interval = int(self.app.interval_edit.text() or 2)
                success, msg = self.app.preprocessor.realign_timestamps(start_time_str, interval)
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


class DataPreprocessorMac(QMainWindow):
    """Mac용 데이터 전처리 애플리케이션"""
    
    def __init__(self):
        super().__init__()
        self.preprocessor = DataPreprocessor()
        self.preset_manager = PresetManager()
        self.current_file = None
        self.filter_widgets: List[FilterWidget] = []
        self.processing_thread = None
        
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
        for text, value in [('2σ (95.4%)', '2sigma'), ('2.5σ (98.8%)', '2.5sigma'), 
                           ('3σ (99.7%)', '3sigma'), ('IQR', 'iqr')]:
            rb = QRadioButton(text)
            rb.setProperty('value', value)
            self.outlier_method_group.addButton(rb)
            method_layout.addWidget(rb)
            if value == '2.5sigma':
                rb.setChecked(True)
        
        method_layout.addStretch()
        outlier_layout.addLayout(method_layout)
        
        action_layout = QHBoxLayout()
        action_layout.addWidget(QLabel("처리:"))
        self.outlier_drop = QRadioButton("행 전체 삭제")
        self.outlier_drop.setChecked(True)
        self.outlier_nan = QRadioButton("해당 값만 NaN으로")
        action_layout.addWidget(self.outlier_drop)
        action_layout.addWidget(self.outlier_nan)
        action_layout.addStretch()
        outlier_layout.addLayout(action_layout)
        
        self.apply_outlier = QCheckBox("이상값 처리 적용")
        self.apply_outlier.setChecked(True)
        outlier_layout.addWidget(self.apply_outlier)
        
        outlier_group.setMaximumHeight(100)
        main_layout.addWidget(outlier_group)
        
        # === 정규화 ===
        norm_group = QGroupBox("📈 정규화 (선택사항)")
        norm_layout = QHBoxLayout(norm_group)
        
        self.apply_normalize = QCheckBox("정규화 적용")
        norm_layout.addWidget(self.apply_normalize)
        
        self.norm_zscore = QRadioButton("Z-Score")
        self.norm_zscore.setChecked(True)
        self.norm_minmax = QRadioButton("Min-Max (0~1)")
        norm_layout.addWidget(self.norm_zscore)
        norm_layout.addWidget(self.norm_minmax)
        norm_layout.addStretch()
        
        norm_group.setMaximumHeight(50)
        main_layout.addWidget(norm_group)
        
        # === 시간 처리 ===
        time_group = QGroupBox("🕐 시간 처리 (선택사항)")
        time_layout = QVBoxLayout(time_group)
        
        self.apply_time_normalize = QCheckBox("시간 정규화 (2분 간격 스냅)")
        time_layout.addWidget(self.apply_time_normalize)
        
        self.apply_time_realign = QCheckBox("시간 재정렬 (새 시작 시간부터)")
        time_layout.addWidget(self.apply_time_realign)
        
        time_input_layout = QHBoxLayout()
        time_input_layout.addWidget(QLabel("   시작 시간:"))
        self.start_time_edit = QLineEdit(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
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
    
    def _load_file(self):
        """파일 로드"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "데이터 파일 선택", "",
            "Excel/CSV 파일 (*.xlsx *.xls *.csv);;모든 파일 (*.*)"
        )
        
        if not file_path:
            return
        
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
        else:
            QMessageBox.critical(self, "오류", msg)
    
    def _update_preview(self):
        """미리보기 업데이트"""
        df = self.preprocessor.get_preview(5)
        if df.empty:
            return
        
        columns = list(df.columns)[:30]
        self.preview_table.setColumnCount(len(columns))
        self.preview_table.setRowCount(len(df))
        self.preview_table.setHorizontalHeaderLabels(columns)
        
        for i, row in df.iterrows():
            for j, col in enumerate(columns):
                val = str(row[col]) if not (hasattr(row[col], '__iter__') and str(row[col]) == 'nan') else ''
                self.preview_table.setItem(i, j, QTableWidgetItem(val[:20]))
        
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    
    def _update_filter_columns(self):
        """필터 컬럼 업데이트"""
        columns = self.preprocessor.numeric_columns
        for fw in self.filter_widgets:
            fw.update_columns(columns)
    
    def _add_filter(self):
        """필터 추가"""
        columns = self.preprocessor.numeric_columns if self.preprocessor.numeric_columns else []
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
        self.cancel_btn.setEnabled(True)
        
        self.processing_thread = ProcessingThread(self)
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
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            default_name = f"{orig.stem}_processed_{timestamp}{orig.suffix}"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "결과 저장", default_name,
            "CSV 파일 (*.csv);;Excel 파일 (*.xlsx)"
        )
        
        if not file_path:
            return
        
        success, result = self.preprocessor.save_data(file_path, self.current_file)
        
        if success:
            self._log(f"\n💾 저장 완료: {result}")
            QMessageBox.information(self, "저장 완료", f"파일이 저장되었습니다:\n{result}")
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
            settings = self._get_current_settings()
            if self.preset_manager.save_preset(name, settings, ""):
                self._log(f"💾 프리셋 저장: {name}")
                QMessageBox.information(self, "저장 완료", f"프리셋 '{name}'이(가) 저장되었습니다.")
    
    def _load_preset(self):
        """프리셋 불러오기"""
        presets = self.preset_manager.list_presets()
        if not presets:
            QMessageBox.information(self, "알림", "저장된 프리셋이 없습니다.")
            return
        
        names = [p['name'] for p in presets]
        from PyQt5.QtWidgets import QInputDialog
        name, ok = QInputDialog.getItem(self, "프리셋 불러오기", "선택:", names, 0, False)
        if ok and name:
            preset = next((p for p in presets if p['name'] == name), None)
            if preset:
                data = self.preset_manager.load_preset(preset['path'])
                if data:
                    self._apply_settings(data['settings'])
                    self._log(f"📂 프리셋 로드: {name}")
    
    def _load_file_with_preset(self):
        """파일+프리셋 한번에"""
        presets = self.preset_manager.list_presets()
        if not presets:
            QMessageBox.information(self, "알림", "저장된 프리셋이 없습니다.")
            return
        
        names = [p['name'] for p in presets]
        from PyQt5.QtWidgets import QInputDialog
        name, ok = QInputDialog.getItem(self, "프리셋 선택", "적용할 프리셋:", names, 0, False)
        if not ok:
            return
        
        preset = next((p for p in presets if p['name'] == name), None)
        if not preset:
            return
        
        # 파일 선택
        self._load_file()
        if self.preprocessor.original_df is None:
            return
        
        # 프리셋 적용
        data = self.preset_manager.load_preset(preset['path'])
        if data:
            self._apply_settings(data['settings'])
            self._log(f"📂 프리셋 적용: {name}")
            # 자동 실행
            self._run_preprocessing()
    
    def _get_current_settings(self) -> Dict:
        """현재 설정 추출"""
        filters = []
        for fw in self.filter_widgets:
            f = fw.get_filter()
            if f:
                filters.append(f)
        
        return {
            'filters': filters,
            'outlier': {
                'apply': self.apply_outlier.isChecked(),
                'method': self.outlier_method_group.checkedButton().property('value') if self.outlier_method_group.checkedButton() else '2.5sigma',
                'action': 'drop' if self.outlier_drop.isChecked() else 'nan'
            },
            'normalize': {
                'apply': self.apply_normalize.isChecked(),
                'method': 'zscore' if self.norm_zscore.isChecked() else 'minmax'
            },
            'time': {
                'normalize': self.apply_time_normalize.isChecked(),
                'realign': self.apply_time_realign.isChecked(),
                'start_time': self.start_time_edit.text(),
                'interval': self.interval_edit.text()
            }
        }
    
    def _apply_settings(self, settings: Dict):
        """설정 적용"""
        # 기존 필터 제거
        for fw in self.filter_widgets[:]:
            self._remove_filter(fw)
        
        # 필터 추가
        for f in settings.get('filters', []):
            self._add_filter()
            fw = self.filter_widgets[-1]
            fw.column_combo.setCurrentText(f.get('column', ''))
            fw.operator_combo.setCurrentText(f.get('operator', 'range'))
            if f.get('operator') == 'range':
                fw.min_edit.setText(str(f.get('min', '')))
                fw.max_edit.setText(str(f.get('max', '')))
            else:
                fw.value_edit.setText(str(f.get('value', '')))
        
        # 이상값
        outlier = settings.get('outlier', {})
        self.apply_outlier.setChecked(outlier.get('apply', True))
        if outlier.get('action') == 'nan':
            self.outlier_nan.setChecked(True)
        else:
            self.outlier_drop.setChecked(True)
        
        # 정규화
        normalize = settings.get('normalize', {})
        self.apply_normalize.setChecked(normalize.get('apply', False))
        if normalize.get('method') == 'minmax':
            self.norm_minmax.setChecked(True)
        else:
            self.norm_zscore.setChecked(True)
        
        # 시간
        time_settings = settings.get('time', {})
        self.apply_time_normalize.setChecked(time_settings.get('normalize', False))
        self.apply_time_realign.setChecked(time_settings.get('realign', False))
        self.start_time_edit.setText(time_settings.get('start_time', ''))
        self.interval_edit.setText(time_settings.get('interval', '2'))
    
    def _show_manual(self):
        """매뉴얼 표시"""
        manual_path = Path(__file__).parent / "MANUAL.md"
        content = ""
        if manual_path.exists():
            with open(manual_path, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            content = "매뉴얼 파일을 찾을 수 없습니다.\nGitHub에서 MANUAL.md를 확인하세요."
        
        dialog = QDialog(self)
        dialog.setWindowTitle("사용자 매뉴얼")
        dialog.resize(700, 500)
        layout = QVBoxLayout(dialog)
        
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(content)
        layout.addWidget(text)
        
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
        
        dialog.exec_()
    
    def _show_about(self):
        """프로그램 정보 (내장 정보 사용)"""
        from version import __version__, APP_NAME, FEATURES, CHANGELOG, get_developer_info
        
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
<p><b>이름:</b> {dev.get('name', '-')}</p>
<p><b>조직:</b> {dev.get('organization', '-')}</p>
<p><b>이메일:</b> {dev.get('email', '-')}</p>
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
    
    def _show_trend_chart(self):
        """트렌드 차트 표시 (다중 컬럼 지원)"""
        if self.preprocessor.processed_df is None:
            QMessageBox.warning(self, "경고", "먼저 데이터를 로드하고 전처리를 실행하세요.")
            return
        
        try:
            import matplotlib
            matplotlib.use('Qt5Agg')
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
            from matplotlib.figure import Figure
            import matplotlib.pyplot as plt
            
            # 한글 폰트 설정 (Mac)
            plt.rcParams['font.family'] = ['AppleGothic', 'Malgun Gothic', 'NanumGothic', 'sans-serif']
            plt.rcParams['axes.unicode_minus'] = False  # 마이너스 기호 깨짐 방지
        except ImportError:
            QMessageBox.critical(self, "오류", "matplotlib이 설치되지 않았습니다.\npip install matplotlib")
            return
        
        # 트렌드 차트 다이얼로그
        dialog = QDialog(self)
        dialog.setWindowTitle("📊 트렌드 차트 (다중 비교)")
        dialog.resize(1000, 750)
        layout = QVBoxLayout(dialog)
        
        # 상단 컨트롤 영역
        control_layout = QHBoxLayout()
        
        # 컬럼 선택 (다중 선택 리스트)
        column_frame = QGroupBox("컬럼 선택 (Ctrl+클릭으로 다중 선택)")
        column_layout = QVBoxLayout(column_frame)
        
        column_list = QListWidget()
        column_list.setSelectionMode(QListWidget.ExtendedSelection)
        column_list.addItems(self.preprocessor.numeric_columns)
        column_list.setMaximumHeight(120)
        if self.preprocessor.numeric_columns:
            column_list.item(0).setSelected(True)
        column_layout.addWidget(column_list)
        
        control_layout.addWidget(column_frame)
        
        # 옵션
        option_frame = QGroupBox("옵션")
        option_layout = QVBoxLayout(option_frame)
        
        auto_scale_check = QCheckBox("자동 스케일 (여유 20%)")
        auto_scale_check.setChecked(True)
        option_layout.addWidget(auto_scale_check)
        
        show_mean_check = QCheckBox("평균선 표시")
        show_mean_check.setChecked(True)
        option_layout.addWidget(show_mean_check)
        
        normalize_check = QCheckBox("정규화하여 비교 (0~1)")
        normalize_check.setToolTip("스케일이 다른 컬럼을 비교할 때 유용")
        option_layout.addWidget(normalize_check)
        
        control_layout.addWidget(option_frame)
        
        # 버튼
        btn_frame = QGroupBox("실행")
        btn_layout = QVBoxLayout(btn_frame)
        
        refresh_btn = QPushButton("🔄 차트 업데이트")
        btn_layout.addWidget(refresh_btn)
        
        control_layout.addWidget(btn_frame)
        control_layout.addStretch()
        
        layout.addLayout(control_layout)
        
        # matplotlib Figure
        fig = Figure(figsize=(12, 5), dpi=100)
        canvas = FigureCanvas(fig)
        layout.addWidget(canvas)
        
        # 통계 정보
        stats_text = QTextEdit()
        stats_text.setReadOnly(True)
        stats_text.setMaximumHeight(100)
        stats_text.setStyleSheet("font-family: Menlo; font-size: 10px;")
        layout.addWidget(stats_text)
        
        # 색상 팔레트
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
        
        def update_chart():
            """차트 업데이트"""
            selected_items = column_list.selectedItems()
            if not selected_items:
                return
            
            selected_columns = [item.text() for item in selected_items][:5]  # 최대 5개
            
            df = self.preprocessor.processed_df
            
            fig.clear()
            ax = fig.add_subplot(111)
            
            # X축: 날짜 또는 인덱스
            if self.preprocessor.date_column and self.preprocessor.date_column in df.columns:
                x_data = df[self.preprocessor.date_column]
                ax.set_xlabel("시간")
            else:
                x_data = range(len(df))
                ax.set_xlabel("인덱스")
            
            stats_lines = []
            all_min, all_max = float('inf'), float('-inf')
            
            for i, column in enumerate(selected_columns):
                data = df[column].dropna()
                if len(data) == 0:
                    continue
                
                color = colors[i % len(colors)]
                
                # 정규화 옵션
                if normalize_check.isChecked():
                    min_v, max_v = data.min(), data.max()
                    if max_v - min_v > 0:
                        plot_data = (data - min_v) / (max_v - min_v)
                    else:
                        plot_data = data * 0
                    ylabel = "정규화 값 (0~1)"
                else:
                    plot_data = data
                    ylabel = "값"
                
                # 플롯
                ax.plot(x_data[:len(plot_data)], plot_data.values, 
                       color=color, linewidth=0.8, alpha=0.8, label=column)
                
                # 평균선
                if show_mean_check.isChecked():
                    mean_val = plot_data.mean()
                    ax.axhline(y=mean_val, color=color, linestyle='--', alpha=0.3)
                
                # 통계
                min_val = data.min()
                max_val = data.max()
                all_min = min(all_min, plot_data.min())
                all_max = max(all_max, plot_data.max())
                
                stats_lines.append(
                    f"📊 {column}: 최소={min_val:.4f}, 최대={max_val:.4f}, "
                    f"평균={data.mean():.4f}, 표준편차={data.std():.4f}, 데이터={len(data):,}개"
                )
            
            # 자동 스케일
            if auto_scale_check.isChecked() and all_min != float('inf'):
                range_val = all_max - all_min
                margin = range_val * 0.2
                ax.set_ylim(all_min - margin, all_max + margin)
            
            # 스타일
            title = ", ".join(selected_columns[:3])
            if len(selected_columns) > 3:
                title += f" 외 {len(selected_columns)-3}개"
            ax.set_title(f"트렌드: {title}", fontsize=11, fontweight='bold')
            ax.set_ylabel(ylabel)
            ax.grid(True, alpha=0.3)
            ax.legend(loc='upper right', fontsize=9)
            
            if self.preprocessor.date_column:
                fig.autofmt_xdate()
            
            fig.tight_layout()
            canvas.draw()
            
            # 인터랙티브 커서 추가
            try:
                import mplcursors
                cursor = mplcursors.cursor(ax, hover=True)
                
                @cursor.connect("add")
                def on_add(sel):
                    line = sel.artist
                    label = line.get_label()
                    x_val = sel.target[0]
                    y_val = sel.target[1]
                    sel.annotation.set(
                        text=f"{label}\nValue: {y_val:.4f}\nIndex: {int(x_val)}",
                        fontsize=9,
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.9, edgecolor=line.get_color())
                    )
            except ImportError:
                pass  # mplcursors 없으면 기본 동작
            
            # 통계 정보 업데이트
            stats_text.setText("\n".join(stats_lines))
        
        # 이벤트 연결
        refresh_btn.clicked.connect(update_chart)
        column_list.itemSelectionChanged.connect(update_chart)
        auto_scale_check.stateChanged.connect(update_chart)
        show_mean_check.stateChanged.connect(update_chart)
        normalize_check.stateChanged.connect(update_chart)
        
        # 초기 차트
        update_chart()
        
        # 닫기 버튼
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
        
        dialog.exec_()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # 크로스 플랫폼 스타일
    
    window = DataPreprocessorMac()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
