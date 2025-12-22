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
        self.setWindowTitle("시계열 데이터 전처리 프로그램 (Mac)")
        self.setMinimumSize(900, 800)
        
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
        
        # 미리보기 테이블
        self.preview_table = QTableWidget()
        self.preview_table.setMaximumHeight(150)
        file_layout.addWidget(self.preview_table)
        
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
        
        main_layout.addWidget(time_group)
        
        # === 진행률 ===
        progress_group = QGroupBox("⏳ 진행 상황")
        progress_layout = QVBoxLayout(progress_group)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        
        self.progress_label = QLabel("대기 중...")
        progress_layout.addWidget(self.progress_label)
        
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
        self.result_text.setFont(QFont("Menlo", 10))
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
        """프로그램 정보"""
        about_text = """시계열 데이터 전처리 프로그램

Version 1.3.2 (Mac)

주요 기능:
• 다중 조건 필터링 (AND)
• 이상값 처리 (σ, IQR)
• 시간 정규화/재정렬
• 프리셋 저장/불러오기

GitHub: github.com/lee-minki/data-preprocessing-tool"""
        
        QMessageBox.about(self, "프로그램 정보", about_text)


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # 크로스 플랫폼 스타일
    
    window = DataPreprocessorMac()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
