"""
데이터 전처리 GUI 애플리케이션
- tkinter 기반 사용자 인터페이스
- 파일 로드, 필터링, 이상값 처리, 저장 기능
- 대용량 데이터 처리를 위한 진행률 표시 및 스레딩
- 도움말 및 시간 재정렬 기능
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
import os
import threading
import time
from typing import List, Dict, Optional
from datetime import datetime
from data_preprocessor import DataPreprocessor
from preset_manager import PresetManager, create_settings_from_gui, apply_settings_to_gui


class HelpTooltip:
    """도움말 툴팁 클래스"""
    
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.widget.bind("<Enter>", self.show)
        self.widget.bind("<Leave>", self.hide)
    
    def show(self, event=None):
        x, y, _, _ = self.widget.bbox("insert") if hasattr(self.widget, 'bbox') else (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        
        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")
        
        label = tk.Label(self.tooltip, text=self.text, justify=tk.LEFT,
                        background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                        font=("맑은 고딕", 9), wraplength=400)
        label.pack()
    
    def hide(self, event=None):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None


class FilterFrame(ttk.Frame):
    """필터 조건 한 줄을 표현하는 프레임"""
    
    def __init__(self, parent, columns: List[str], on_delete):
        super().__init__(parent)
        self.on_delete = on_delete
        self.columns = columns
        
        # 컬럼 선택
        self.column_var = tk.StringVar()
        self.column_combo = ttk.Combobox(self, textvariable=self.column_var, 
                                         values=columns, state='readonly', width=20)
        self.column_combo.pack(side=tk.LEFT, padx=2)
        if columns:
            self.column_combo.current(0)
        
        # 연산자 선택
        self.operator_var = tk.StringVar(value='range')
        operators = ['>=', '<=', '>', '<', '=', '!=', 'range']
        self.operator_combo = ttk.Combobox(self, textvariable=self.operator_var,
                                           values=operators, state='readonly', width=8)
        self.operator_combo.pack(side=tk.LEFT, padx=2)
        self.operator_combo.bind('<<ComboboxSelected>>', self._on_operator_change)
        
        # 값 입력 (단일)
        self.value_frame = ttk.Frame(self)
        self.value_frame.pack(side=tk.LEFT, padx=2)
        
        self.value_entry = ttk.Entry(self.value_frame, width=10)
        self.value_entry.pack(side=tk.LEFT)
        
        # 범위 입력
        self.range_frame = ttk.Frame(self)
        
        self.min_entry = ttk.Entry(self.range_frame, width=8)
        self.min_entry.pack(side=tk.LEFT)
        ttk.Label(self.range_frame, text=" ~ ").pack(side=tk.LEFT)
        self.max_entry = ttk.Entry(self.range_frame, width=8)
        self.max_entry.pack(side=tk.LEFT)
        
        # 기본은 range 표시
        self._on_operator_change(None)
        
        # 삭제 버튼
        self.delete_btn = ttk.Button(self, text="✕", width=3, command=self._delete)
        self.delete_btn.pack(side=tk.LEFT, padx=5)
    
    def _on_operator_change(self, event):
        """연산자 변경 시 입력 필드 전환"""
        if self.operator_var.get() == 'range':
            self.value_frame.pack_forget()
            self.range_frame.pack(side=tk.LEFT, padx=2)
        else:
            self.range_frame.pack_forget()
            self.value_frame.pack(side=tk.LEFT, padx=2)
    
    def _delete(self):
        """필터 삭제"""
        self.on_delete(self)
    
    def get_filter(self) -> Optional[Dict]:
        """필터 조건 딕셔너리 반환"""
        column = self.column_var.get()
        operator = self.operator_var.get()
        
        if not column:
            return None
        
        if operator == 'range':
            try:
                min_val = float(self.min_entry.get()) if self.min_entry.get() else float('-inf')
                max_val = float(self.max_entry.get()) if self.max_entry.get() else float('inf')
                return {'column': column, 'operator': 'range', 'min': min_val, 'max': max_val}
            except ValueError:
                return None
        else:
            try:
                value = float(self.value_entry.get())
                return {'column': column, 'operator': operator, 'value': value}
            except ValueError:
                return None
    
    def update_columns(self, columns: List[str]):
        """컬럼 목록 업데이트"""
        self.columns = columns
        self.column_combo['values'] = columns
        if columns and not self.column_var.get():
            self.column_combo.current(0)


class DataPreprocessorApp:
    """메인 GUI 애플리케이션"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("시계열 데이터 전처리 프로그램")
        self.root.geometry("950x950")
        self.root.minsize(850, 850)
        
        self.preprocessor = DataPreprocessor()
        self.preset_manager = PresetManager()
        self.current_file: Optional[str] = None
        self.filter_frames: List[FilterFrame] = []
        self.is_processing = False
        self.current_preset_name: Optional[str] = None
        
        self._create_widgets()
        self._create_menu()
    
    def _create_menu(self):
        """메뉴바 생성"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="파일", menu=file_menu)
        file_menu.add_command(label="열기...", command=self._load_file, accelerator="Ctrl+O")
        file_menu.add_command(label="저장...", command=self._save_file, accelerator="Ctrl+S")
        file_menu.add_separator()
        file_menu.add_command(label="종료", command=self.root.quit)
        
        # 프리셋 메뉴
        preset_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="프리셋", menu=preset_menu)
        preset_menu.add_command(label="프리셋 저장...", command=self._save_preset, accelerator="Ctrl+P")
        preset_menu.add_command(label="프리셋 불러오기...", command=self._load_preset)
        preset_menu.add_separator()
        preset_menu.add_command(label="프리셋 관리...", command=self._manage_presets)
        preset_menu.add_separator()
        preset_menu.add_command(label="프리셋 내보내기...", command=self._export_preset)
        preset_menu.add_command(label="프리셋 가져오기...", command=self._import_preset)
        preset_menu.add_separator()
        preset_menu.add_command(label="파일+프리셋 한번에 열기...", command=self._load_file_with_preset)
        
        # 도움말 메뉴
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="도움말", menu=help_menu)
        help_menu.add_command(label="용어 설명", command=self._show_help)
        help_menu.add_separator()
        help_menu.add_command(label="프로그램 정보", command=self._show_about)
        
        self.root.bind("<Control-o>", lambda e: self._load_file())
        self.root.bind("<Control-s>", lambda e: self._save_file())
        self.root.bind("<Control-p>", lambda e: self._save_preset())
    
    def _show_help(self):
        """도움말 창 표시"""
        help_window = tk.Toplevel(self.root)
        help_window.title("용어 설명")
        help_window.geometry("500x400")
        
        text = ScrolledText(help_window, wrap=tk.WORD, font=('맑은 고딕', 10))
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        help_content = """📊 이상값 처리 방법

■ 2σ (2 표준편차)
  평균에서 ±2 표준편차 범위.
  정규분포 기준 약 95.4%의 데이터 포함.
  엄격한 필터링에 적합.

■ 2.5σ (2.5 표준편차) [권장]
  평균에서 ±2.5 표준편차 범위.
  정규분포 기준 약 98.8%의 데이터 포함.

■ 3σ (3 표준편차)
  평균에서 ±3 표준편차 범위.
  정규분포 기준 약 99.7%의 데이터 포함.
  느슨한 필터링에 적합.

■ IQR (사분위 범위)
  Q1-1.5×IQR ~ Q3+1.5×IQR 범위.
  비대칭 분포에 적합.
  극단적 이상값 탐지에 효과적.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 정규화 방법

■ Z-Score 정규화
  (값 - 평균) / 표준편차
  평균=0, 표준편차=1로 변환.
  데이터 비교 시 유용.

■ Min-Max 정규화
  (값 - 최소) / (최대 - 최소)
  0~1 범위로 변환.
  신경망 입력에 적합.
"""
        text.insert(tk.END, help_content)
        text.config(state=tk.DISABLED)
    
    def _show_about(self):
        """프로그램 정보 창 표시"""
        about_window = tk.Toplevel(self.root)
        about_window.title("프로그램 정보")
        about_window.geometry("400x350")
        about_window.resizable(False, False)
        about_window.transient(self.root)
        
        # 버전 정보
        version_frame = ttk.LabelFrame(about_window, text="버전 정보", padding=15)
        version_frame.pack(fill=tk.X, padx=15, pady=10)
        
        ttk.Label(version_frame, text="시계열 데이터 전처리 프로그램", 
                 font=('맑은 고딕', 12, 'bold')).pack()
        ttk.Label(version_frame, text="Version 1.3.0", font=('맑은 고딕', 10)).pack()
        ttk.Label(version_frame, text="").pack()  # 빈 줄
        
        features = "• 다중 조건 필터링 (AND)\n• 이상값 처리 (σ, IQR)\n• 시간 정규화/재정렬\n• 프리셋 저장/불러오기"
        ttk.Label(version_frame, text=features, justify=tk.LEFT).pack(anchor=tk.W)
        
        # 개발자 정보 (외부 파일에서 로드)
        dev_frame = ttk.LabelFrame(about_window, text="개발자 정보", padding=15)
        dev_frame.pack(fill=tk.X, padx=15, pady=10)
        
        # developer_info.json 파일에서 로드
        dev_info = self._load_developer_info()
        
        if dev_info:
            ttk.Label(dev_frame, text=f"개발자: {dev_info.get('name', '')}").pack(anchor=tk.W)
            if dev_info.get('company'):
                ttk.Label(dev_frame, text=f"회사: {dev_info.get('company', '')}").pack(anchor=tk.W)
            if dev_info.get('phone'):
                ttk.Label(dev_frame, text=f"전화: {dev_info.get('phone', '')}").pack(anchor=tk.W)
            if dev_info.get('email'):
                ttk.Label(dev_frame, text=f"이메일: {dev_info.get('email', '')}").pack(anchor=tk.W)
        else:
            ttk.Label(dev_frame, text="개발자 정보가 설정되지 않았습니다.").pack(anchor=tk.W)
            ttk.Label(dev_frame, text="developer_info.json 파일을 생성하세요.", 
                     foreground="gray").pack(anchor=tk.W)
        
        # GitHub 링크
        link_frame = ttk.Frame(about_window)
        link_frame.pack(fill=tk.X, padx=15, pady=10)
        
        ttk.Label(link_frame, text="GitHub:", font=('맑은 고딕', 9)).pack(side=tk.LEFT)
        github_link = ttk.Label(link_frame, text="github.com/lee-minki/data-preprocessing-tool", 
                               foreground="blue", cursor="hand2", font=('맑은 고딕', 9))
        github_link.pack(side=tk.LEFT, padx=5)
        
        # 닫기 버튼
        ttk.Button(about_window, text="닫기", command=about_window.destroy).pack(pady=10)
    
    def _load_developer_info(self) -> Optional[Dict]:
        """개발자 정보 로드 (developer_info.json)"""
        import json
        from pathlib import Path
        
        # 실행 파일 위치에서 찾기
        possible_paths = [
            Path(__file__).parent / "developer_info.json",
            Path.cwd() / "developer_info.json",
            Path.home() / ".data_preprocessor" / "developer_info.json"
        ]
        
        for path in possible_paths:
            if path.exists():
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        return data.get('developer', {})
                except:
                    continue
        
        return None
    
    def _create_widgets(self):
        """위젯 생성"""
        # 스크롤 가능한 메인 프레임
        canvas = tk.Canvas(self.root)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, padding=10)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        
        main_frame = scrollable_frame
        
        # === 파일 선택 섹션 ===
        file_frame = ttk.LabelFrame(main_frame, text="📁 파일 선택", padding=10)
        file_frame.pack(fill=tk.X, pady=5)
        
        file_btn_frame = ttk.Frame(file_frame)
        file_btn_frame.pack(fill=tk.X)
        
        self.load_btn = ttk.Button(file_btn_frame, text="파일 불러오기", command=self._load_file)
        self.load_btn.pack(side=tk.LEFT)
        
        self.file_label = ttk.Label(file_btn_frame, text="파일을 선택해주세요", foreground="gray")
        self.file_label.pack(side=tk.LEFT, padx=10)
        
        # 데이터 정보 라벨
        self.data_info_label = ttk.Label(file_btn_frame, text="", foreground="blue")
        self.data_info_label.pack(side=tk.RIGHT, padx=10)
        
        # 미리보기 테이블
        preview_frame = ttk.Frame(file_frame)
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.preview_tree = ttk.Treeview(preview_frame, show='headings', height=5)
        preview_scroll_y = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=self.preview_tree.yview)
        preview_scroll_x = ttk.Scrollbar(preview_frame, orient=tk.HORIZONTAL, command=self.preview_tree.xview)
        self.preview_tree.configure(yscrollcommand=preview_scroll_y.set, xscrollcommand=preview_scroll_x.set)
        
        preview_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        preview_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.preview_tree.pack(fill=tk.BOTH, expand=True)
        
        # === 필터 조건 섹션 ===
        filter_frame = ttk.LabelFrame(main_frame, text="🔧 필터 조건 (AND 결합)", padding=10)
        filter_frame.pack(fill=tk.X, pady=5)
        
        self.filters_container = ttk.Frame(filter_frame)
        self.filters_container.pack(fill=tk.X)
        
        self.add_filter_btn = ttk.Button(filter_frame, text="+ 필터 추가", command=self._add_filter)
        self.add_filter_btn.pack(anchor=tk.W, pady=5)
        
        # === 이상값 처리 섹션 ===
        outlier_frame = ttk.LabelFrame(main_frame, text="📊 이상값 처리", padding=10)
        outlier_frame.pack(fill=tk.X, pady=5)
        
        # 방법 선택
        method_frame = ttk.Frame(outlier_frame)
        method_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(method_frame, text="방법:").pack(side=tk.LEFT)
        
        self.outlier_method = tk.StringVar(value='2.5sigma')
        methods = [('2σ (95.4%)', '2sigma'), ('2.5σ (98.8%)', '2.5sigma'), 
                   ('3σ (99.7%)', '3sigma'), ('IQR', 'iqr')]
        
        for text, value in methods:
            rb = ttk.Radiobutton(method_frame, text=text, variable=self.outlier_method, value=value)
            rb.pack(side=tk.LEFT, padx=10)
            # 도움말 툴팁 추가
            HelpTooltip(rb, DataPreprocessor.get_help_text(value))
        
        # 도움말 버튼
        help_btn = ttk.Button(method_frame, text="?", width=2, command=self._show_help)
        help_btn.pack(side=tk.RIGHT, padx=5)
        
        # 처리 방법 (기본값: 행 전체 삭제)
        action_frame = ttk.Frame(outlier_frame)
        action_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(action_frame, text="처리:").pack(side=tk.LEFT)
        
        self.outlier_action = tk.StringVar(value='drop')  # 기본값: 행 전체 삭제
        ttk.Radiobutton(action_frame, text="행 전체 삭제", variable=self.outlier_action, 
                       value='drop').pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(action_frame, text="해당 값만 NaN으로", variable=self.outlier_action, 
                       value='nan').pack(side=tk.LEFT, padx=10)
        
        # 이상값 처리 체크박스
        self.apply_outlier = tk.BooleanVar(value=True)
        ttk.Checkbutton(outlier_frame, text="이상값 처리 적용", 
                       variable=self.apply_outlier).pack(anchor=tk.W, pady=2)
        
        # === 정규화 섹션 ===
        norm_frame = ttk.LabelFrame(main_frame, text="📈 정규화 (선택사항)", padding=10)
        norm_frame.pack(fill=tk.X, pady=5)
        
        norm_inner = ttk.Frame(norm_frame)
        norm_inner.pack(fill=tk.X)
        
        self.apply_normalize = tk.BooleanVar(value=False)
        ttk.Checkbutton(norm_inner, text="정규화 적용", 
                       variable=self.apply_normalize).pack(side=tk.LEFT)
        
        self.normalize_method = tk.StringVar(value='zscore')
        
        rb_zscore = ttk.Radiobutton(norm_inner, text="Z-Score", variable=self.normalize_method, value='zscore')
        rb_zscore.pack(side=tk.LEFT, padx=10)
        HelpTooltip(rb_zscore, DataPreprocessor.get_help_text('zscore'))
        
        rb_minmax = ttk.Radiobutton(norm_inner, text="Min-Max (0~1)", variable=self.normalize_method, value='minmax')
        rb_minmax.pack(side=tk.LEFT, padx=10)
        HelpTooltip(rb_minmax, DataPreprocessor.get_help_text('minmax'))
        
        # === 시간 처리 섹션 ===
        time_frame = ttk.LabelFrame(main_frame, text="🕐 시간 처리 (선택사항)", padding=10)
        time_frame.pack(fill=tk.X, pady=5)
        
        # 시간 정규화 (2분 간격으로 스냅)
        self.apply_time_normalize = tk.BooleanVar(value=False)
        time_norm_check = ttk.Checkbutton(time_frame, text="시간 정규화 (2분 간격으로 스냅)", 
                       variable=self.apply_time_normalize)
        time_norm_check.pack(anchor=tk.W)
        HelpTooltip(time_norm_check, "엑셀 자동채우기로 인한 시간 밀림 보정\n예: 00:01:00 → 00:00:00, 00:05:59 → 00:06:00")
        
        ttk.Label(time_frame, text="   ※ 00:01:00, 00:02:01 같은 틀어진 시간을 정확한 2분 간격으로 보정",
                 foreground="gray").pack(anchor=tk.W)
        
        ttk.Separator(time_frame, orient='horizontal').pack(fill=tk.X, pady=5)
        
        # 시간 재정렬
        self.apply_time_realign = tk.BooleanVar(value=False)
        ttk.Checkbutton(time_frame, text="시간 재정렬 (새 시작 시간부터 재배열)", 
                       variable=self.apply_time_realign).pack(anchor=tk.W)
        
        time_inner = ttk.Frame(time_frame)
        time_inner.pack(fill=tk.X, pady=5)
        
        ttk.Label(time_inner, text="   시작 시간:").pack(side=tk.LEFT)
        self.start_time_entry = ttk.Entry(time_inner, width=20)
        self.start_time_entry.pack(side=tk.LEFT, padx=5)
        self.start_time_entry.insert(0, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        ttk.Label(time_inner, text="간격(분):").pack(side=tk.LEFT, padx=(20, 0))
        self.interval_entry = ttk.Entry(time_inner, width=5)
        self.interval_entry.pack(side=tk.LEFT, padx=5)
        self.interval_entry.insert(0, "2")
        
        ttk.Label(time_frame, text="   ※ 필터링된 데이터를 지정된 시작 시간부터 일정 간격으로 재배열",
                 foreground="gray").pack(anchor=tk.W)
        
        # === 진행률 표시 섹션 ===
        progress_frame = ttk.LabelFrame(main_frame, text="⏳ 진행 상황", padding=10)
        progress_frame.pack(fill=tk.X, pady=5)
        
        # 진행률 바
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, 
                                            maximum=100, mode='determinate', length=400)
        self.progress_bar.pack(fill=tk.X, pady=5)
        
        # 진행 상태 라벨
        self.progress_label = ttk.Label(progress_frame, text="대기 중...", font=('맑은 고딕', 10))
        self.progress_label.pack(anchor=tk.W)
        
        # 예상 시간 라벨
        self.time_label = ttk.Label(progress_frame, text="", foreground="gray")
        self.time_label.pack(anchor=tk.W)
        
        # === 실행 버튼 ===
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, pady=10)
        
        self.process_btn = ttk.Button(action_frame, text="🚀 전처리 실행", 
                                      command=self._run_preprocessing_threaded, style='Accent.TButton')
        self.process_btn.pack(side=tk.LEFT, padx=5)
        
        self.save_btn = ttk.Button(action_frame, text="💾 결과 저장", command=self._save_file)
        self.save_btn.pack(side=tk.LEFT, padx=5)
        
        # 취소 버튼 (처리 중에만 활성화)
        self.cancel_btn = ttk.Button(action_frame, text="⏹ 취소", command=self._cancel_processing, 
                                     state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=5)
        
        # === 결과 표시 ===
        result_frame = ttk.LabelFrame(main_frame, text="📋 처리 결과", padding=10)
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.result_text = ScrolledText(result_frame, height=8, wrap=tk.WORD, font=('Consolas', 10))
        self.result_text.pack(fill=tk.BOTH, expand=True)
        self.result_text.config(state=tk.DISABLED)
        
        # 스타일 설정
        style = ttk.Style()
        style.configure('Accent.TButton', font=('맑은 고딕', 10, 'bold'))
    
    def _load_file(self):
        """파일 불러오기"""
        if self.is_processing:
            messagebox.showwarning("경고", "처리 중에는 파일을 불러올 수 없습니다.")
            return
            
        file_path = filedialog.askopenfilename(
            title="데이터 파일 선택",
            filetypes=[
                ("Excel/CSV 파일", "*.xlsx *.xls *.csv"),
                ("Excel 파일", "*.xlsx *.xls"),
                ("CSV 파일", "*.csv"),
                ("모든 파일", "*.*")
            ]
        )
        
        if not file_path:
            return
        
        # 대용량 파일 로딩 안내
        file_size = os.path.getsize(file_path)
        if file_size > 10 * 1024 * 1024:  # 10MB 이상
            self._update_progress(0, "대용량 파일 로딩 중...")
        
        self._update_progress(10, "파일 읽는 중...")
        success, msg = self.preprocessor.load_data(file_path)
        
        if success:
            self.current_file = file_path
            self.file_label.config(text=os.path.basename(file_path), foreground="black")
            
            # 데이터 정보 표시
            rows = len(self.preprocessor.original_df)
            cols = len(self.preprocessor.columns)
            self.data_info_label.config(text=f"📊 {rows:,}행 × {cols}열")
            
            self._update_progress(100, "파일 로드 완료!")
            self._update_preview()
            self._update_filter_columns()
            self._log(f"✅ {msg}")
            self._log(f"   감지된 숫자 컬럼 ({len(self.preprocessor.numeric_columns)}개): {', '.join(self.preprocessor.numeric_columns[:10])}")
            if len(self.preprocessor.numeric_columns) > 10:
                self._log(f"   ... 외 {len(self.preprocessor.numeric_columns) - 10}개")
            
            # 대용량 데이터 안내
            if rows >= 100000:
                self._log(f"⚠️ 대용량 데이터 ({rows:,}행) - 처리에 시간이 소요될 수 있습니다.")
        else:
            self._update_progress(0, "파일 로드 실패")
            messagebox.showerror("오류", msg)
            self._log(f"❌ {msg}")
    
    def _update_preview(self):
        """미리보기 테이블 업데이트 (실제 컬럼만 표시)"""
        # 기존 데이터 삭제
        self.preview_tree.delete(*self.preview_tree.get_children())
        
        df = self.preprocessor.get_preview(10)
        if df.empty:
            return
        
        # 실제 존재하는 컬럼만 표시 (최대 30개)
        columns = list(df.columns)[:30]
        self.preview_tree['columns'] = columns
        
        # 컬럼 너비 자동 조절
        col_width = max(80, min(120, 800 // max(1, len(columns))))
        
        for col in columns:
            self.preview_tree.heading(col, text=col)
            self.preview_tree.column(col, width=col_width, minwidth=50)
        
        # 데이터 추가
        for _, row in df.iterrows():
            values = [str(v)[:15] if pd.notna(v) else '' for v in row.values[:30]]
            self.preview_tree.insert('', tk.END, values=values)
    
    def _update_filter_columns(self):
        """필터의 컬럼 목록 업데이트"""
        columns = self.preprocessor.numeric_columns
        for filter_frame in self.filter_frames:
            filter_frame.update_columns(columns)
    
    def _add_filter(self):
        """필터 추가"""
        columns = self.preprocessor.numeric_columns if self.preprocessor.numeric_columns else []
        
        filter_frame = FilterFrame(self.filters_container, columns, self._remove_filter)
        filter_frame.pack(fill=tk.X, pady=2)
        self.filter_frames.append(filter_frame)
    
    def _remove_filter(self, filter_frame: FilterFrame):
        """필터 삭제"""
        if filter_frame in self.filter_frames:
            self.filter_frames.remove(filter_frame)
            filter_frame.destroy()
    
    def _update_progress(self, value: float, status: str, elapsed: float = None):
        """진행률 업데이트"""
        self.progress_var.set(value)
        self.progress_label.config(text=status)
        
        if elapsed is not None:
            if value > 0 and value < 100:
                remaining = (elapsed / value) * (100 - value)
                self.time_label.config(text=f"⏱ 경과: {elapsed:.1f}초 | 예상 남은 시간: {remaining:.1f}초")
            else:
                self.time_label.config(text=f"⏱ 총 소요 시간: {elapsed:.1f}초")
        else:
            self.time_label.config(text="")
        
        self.root.update_idletasks()
    
    def _cancel_processing(self):
        """처리 취소"""
        self.is_processing = False
        self._update_progress(0, "취소됨")
        self._log("⏹ 처리가 취소되었습니다.")
    
    def _set_processing_state(self, processing: bool):
        """처리 중 상태 설정"""
        self.is_processing = processing
        state = tk.DISABLED if processing else tk.NORMAL
        
        self.process_btn.config(state=state)
        self.load_btn.config(state=state)
        self.save_btn.config(state=state)
        self.add_filter_btn.config(state=state)
        
        self.cancel_btn.config(state=tk.NORMAL if processing else tk.DISABLED)
    
    def _run_preprocessing_threaded(self):
        """스레드에서 전처리 실행"""
        if self.preprocessor.original_df is None:
            messagebox.showwarning("경고", "먼저 데이터 파일을 로드해주세요.")
            return
        
        if self.is_processing:
            return
        
        # 백그라운드 스레드에서 실행
        thread = threading.Thread(target=self._run_preprocessing, daemon=True)
        thread.start()
    
    def _run_preprocessing(self):
        """전처리 실행"""
        self._set_processing_state(True)
        start_time = time.time()
        
        try:
            total_rows = len(self.preprocessor.original_df)
            
            self._log("\n" + "="*50)
            self._log(f"🔄 전처리 시작... (총 {total_rows:,}행)")
            
            # 1. 필터링 (30%)
            self._update_progress(5, "필터 조건 준비 중...", time.time() - start_time)
            
            if not self.is_processing:
                return
            
            filters = []
            for ff in self.filter_frames:
                f = ff.get_filter()
                if f:
                    filters.append(f)
            
            self._update_progress(10, "필터링 적용 중...", time.time() - start_time)
            
            if filters:
                success, msg = self.preprocessor.apply_filters(filters)
                self.root.after(0, lambda: self._log(f"{'✅' if success else '❌'} {msg}"))
                if not success:
                    self._set_processing_state(False)
                    return
            else:
                # 필터 없으면 원본 복사
                self.preprocessor.processed_df = self.preprocessor.original_df.copy()
                self.root.after(0, lambda: self._log("ℹ️ 필터 조건 없음 - 전체 데이터 사용"))
            
            self._update_progress(40, "필터링 완료", time.time() - start_time)
            
            if not self.is_processing:
                return
            
            # 2. 이상값 처리 (60%)
            if self.apply_outlier.get():
                self._update_progress(45, "이상값 분석 중...", time.time() - start_time)
                
                success, msg = self.preprocessor.remove_outliers(
                    method=self.outlier_method.get(),
                    action=self.outlier_action.get()
                )
                self.root.after(0, lambda m=msg, s=success: self._log(f"{'✅' if s else '❌'} {m}"))
            
            self._update_progress(70, "이상값 처리 완료", time.time() - start_time)
            
            if not self.is_processing:
                return
            
            # 3. 정규화 (20%)
            if self.apply_normalize.get():
                self._update_progress(75, "정규화 적용 중...", time.time() - start_time)
                
                success, msg = self.preprocessor.normalize_data(
                    method=self.normalize_method.get()
                )
                self.root.after(0, lambda m=msg, s=success: self._log(f"{'✅' if s else '❌'} {m}"))
            
            self._update_progress(85, "정규화 완료", time.time() - start_time)
            
            # 4. 시간 정규화 (2분 간격으로 스냅)
            if self.apply_time_normalize.get():
                self._update_progress(87, "시간 정규화 중...", time.time() - start_time)
                
                try:
                    interval = int(self.interval_entry.get())
                    success, msg = self.preprocessor.normalize_timestamps(interval)
                    self.root.after(0, lambda m=msg, s=success: self._log(f"{'✅' if s else '❌'} {m}"))
                except Exception as e:
                    self.root.after(0, lambda e=e: self._log(f"⚠️ 시간 정규화 실패: {str(e)}"))
            
            # 5. 시간 재정렬
            if self.apply_time_realign.get():
                self._update_progress(90, "시간 재정렬 중...", time.time() - start_time)
                
                try:
                    start_time_str = self.start_time_entry.get()
                    interval = int(self.interval_entry.get())
                    
                    success, msg = self.preprocessor.realign_timestamps(start_time_str, interval)
                    self.root.after(0, lambda m=msg, s=success: self._log(f"{'✅' if s else '❌'} {m}"))
                except Exception as e:
                    self.root.after(0, lambda: self._log(f"⚠️ 시간 재정렬 실패: {str(e)}"))
            
            self._update_progress(90, "결과 정리 중...", time.time() - start_time)
            
            # 5. 결과 표시
            elapsed = time.time() - start_time
            self._update_progress(100, "✅ 전처리 완료!", elapsed)
            
            self.root.after(0, lambda: self._log(""))
            self.root.after(0, lambda: self._log(self.preprocessor.get_summary()))
            self.root.after(0, self._update_preview)
            
            self.root.after(0, lambda e=elapsed: self._log(f"\n⏱ 총 소요 시간: {e:.2f}초"))
            self.root.after(0, lambda: self._log("✅ 전처리 완료! '결과 저장' 버튼을 눌러 파일을 저장하세요."))
            
        except Exception as e:
            self._update_progress(0, f"오류 발생: {str(e)}")
            self.root.after(0, lambda: self._log(f"❌ 오류: {str(e)}"))
        
        finally:
            self._set_processing_state(False)
    
    def _save_file(self):
        """결과 저장"""
        if self.is_processing:
            messagebox.showwarning("경고", "처리 중에는 저장할 수 없습니다.")
            return
            
        if self.preprocessor.processed_df is None:
            messagebox.showwarning("경고", "저장할 데이터가 없습니다.")
            return
        
        # 기본 파일명 생성
        if self.current_file:
            from pathlib import Path
            orig = Path(self.current_file)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            default_name = f"{orig.stem}_processed_{timestamp}{orig.suffix}"
        else:
            default_name = "processed_data.csv"
        
        file_path = filedialog.asksaveasfilename(
            title="결과 저장",
            initialfile=default_name,
            defaultextension=".csv",
            filetypes=[
                ("CSV 파일", "*.csv"),
                ("Excel 파일", "*.xlsx"),
                ("모든 파일", "*.*")
            ]
        )
        
        if not file_path:
            return
        
        self._update_progress(50, "파일 저장 중...")
        success, result = self.preprocessor.save_data(file_path, self.current_file)
        
        if success:
            self._update_progress(100, "저장 완료!")
            self._log(f"\n💾 저장 완료: {result}")
            messagebox.showinfo("저장 완료", f"파일이 저장되었습니다:\n{result}")
        else:
            self._update_progress(0, "저장 실패")
            self._log(f"\n❌ {result}")
            messagebox.showerror("저장 실패", result)
    
    def _log(self, message: str):
        """결과 텍스트에 메시지 추가 (스레드 안전)"""
        def _do_log():
            self.result_text.config(state=tk.NORMAL)
            self.result_text.insert(tk.END, message + "\n")
            self.result_text.see(tk.END)
            self.result_text.config(state=tk.DISABLED)
        
        # 메인 스레드에서 실행되도록 보장
        if threading.current_thread() is threading.main_thread():
            _do_log()
        else:
            self.root.after(0, _do_log)
    
    # ===== 프리셋 관련 메서드 =====
    
    def _save_preset(self):
        """현재 설정을 프리셋으로 저장"""
        # 프리셋 저장 다이얼로그
        dialog = tk.Toplevel(self.root)
        dialog.title("프리셋 저장")
        dialog.geometry("400x200")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="프리셋 이름:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        name_entry = ttk.Entry(dialog, width=40)
        name_entry.pack(padx=10, pady=5)
        name_entry.focus()
        
        ttk.Label(dialog, text="설명 (선택):").pack(anchor=tk.W, padx=10)
        desc_entry = ttk.Entry(dialog, width=40)
        desc_entry.pack(padx=10, pady=5)
        
        def save():
            name = name_entry.get().strip()
            if not name:
                messagebox.showwarning("경고", "프리셋 이름을 입력하세요.")
                return
            
            settings = create_settings_from_gui(self)
            description = desc_entry.get().strip()
            
            if self.preset_manager.save_preset(name, settings, description):
                self.current_preset_name = name
                self._log(f"💾 프리셋 저장 완료: {name}")
                messagebox.showinfo("저장 완료", f"프리셋 '{name}'이(가) 저장되었습니다.")
                dialog.destroy()
            else:
                messagebox.showerror("오류", "프리셋 저장에 실패했습니다.")
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=20)
        ttk.Button(btn_frame, text="저장", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="취소", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        dialog.bind("<Return>", lambda e: save())
    
    def _load_preset(self):
        """프리셋 불러오기"""
        presets = self.preset_manager.list_presets()
        
        if not presets:
            messagebox.showinfo("알림", "저장된 프리셋이 없습니다.")
            return
        
        # 프리셋 선택 다이얼로그
        dialog = tk.Toplevel(self.root)
        dialog.title("프리셋 불러오기")
        dialog.geometry("500x350")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="불러올 프리셋을 선택하세요:").pack(anchor=tk.W, padx=10, pady=10)
        
        # 프리셋 목록
        list_frame = ttk.Frame(dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10)
        
        listbox = tk.Listbox(list_frame, height=10)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox.pack(fill=tk.BOTH, expand=True)
        
        for p in presets:
            display = f"{p['name']}"
            if p['description']:
                display += f" - {p['description'][:30]}"
            listbox.insert(tk.END, display)
        
        if presets:
            listbox.selection_set(0)
        
        # 자동 전처리 옵션
        auto_process = tk.BooleanVar(value=False)
        ttk.Checkbutton(dialog, text="불러온 후 자동으로 전처리 실행", 
                       variable=auto_process).pack(anchor=tk.W, padx=10, pady=5)
        
        def load():
            selection = listbox.curselection()
            if not selection:
                return
            
            preset = presets[selection[0]]
            preset_data = self.preset_manager.load_preset(preset['path'])
            
            if preset_data:
                settings = preset_data.get('settings', {})
                apply_settings_to_gui(self, settings)
                self.current_preset_name = preset['name']
                self._log(f"📂 프리셋 로드 완료: {preset['name']}")
                dialog.destroy()
                
                if auto_process.get() and self.preprocessor.original_df is not None:
                    self._run_preprocessing_threaded()
            else:
                messagebox.showerror("오류", "프리셋을 불러오는데 실패했습니다.")
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="불러오기", command=load).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="취소", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        listbox.bind("<Double-Button-1>", lambda e: load())
    
    def _manage_presets(self):
        """프리셋 관리 다이얼로그"""
        presets = self.preset_manager.list_presets()
        
        dialog = tk.Toplevel(self.root)
        dialog.title("프리셋 관리")
        dialog.geometry("600x400")
        dialog.transient(self.root)
        
        ttk.Label(dialog, text="저장된 프리셋 목록:").pack(anchor=tk.W, padx=10, pady=10)
        
        # 프리셋 목록
        columns = ('name', 'description', 'created')
        tree = ttk.Treeview(dialog, columns=columns, show='headings', height=12)
        tree.heading('name', text='이름')
        tree.heading('description', text='설명')
        tree.heading('created', text='생성일')
        tree.column('name', width=150)
        tree.column('description', width=250)
        tree.column('created', width=150)
        
        scrollbar = ttk.Scrollbar(dialog, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=5)
        scrollbar.pack(side=tk.LEFT, fill=tk.Y, pady=5)
        
        def refresh():
            tree.delete(*tree.get_children())
            for p in self.preset_manager.list_presets():
                created = p.get('created_at', '')[:10] if p.get('created_at') else ''
                tree.insert('', tk.END, values=(p['name'], p['description'], created), 
                           tags=(p['path'],))
        
        refresh()
        
        def delete_selected():
            selection = tree.selection()
            if not selection:
                return
            
            item = tree.item(selection[0])
            name = item['values'][0]
            path = item['tags'][0]
            
            if messagebox.askyesno("확인", f"프리셋 '{name}'을(를) 삭제하시겠습니까?"):
                if self.preset_manager.delete_preset(path):
                    refresh()
                    self._log(f"🗑️ 프리셋 삭제: {name}")
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btn_frame, text="삭제", command=delete_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="새로고침", command=refresh).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="닫기", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
    
    def _export_preset(self):
        """프리셋 내보내기"""
        presets = self.preset_manager.list_presets()
        
        if not presets:
            messagebox.showinfo("알림", "내보낼 프리셋이 없습니다.")
            return
        
        # 간단히 현재 프리셋 또는 선택
        if self.current_preset_name:
            name = self.current_preset_name
        else:
            # 첫 번째 프리셋
            name = presets[0]['name']
        
        file_path = filedialog.asksaveasfilename(
            title="프리셋 내보내기",
            initialfile=f"{name}.json",
            defaultextension=".json",
            filetypes=[("JSON 파일", "*.json")]
        )
        
        if file_path:
            if self.preset_manager.export_preset(name, file_path):
                self._log(f"📤 프리셋 내보내기 완료: {file_path}")
                messagebox.showinfo("완료", f"프리셋이 내보내졌습니다:\n{file_path}")
            else:
                messagebox.showerror("오류", "프리셋 내보내기에 실패했습니다.")
    
    def _import_preset(self):
        """프리셋 가져오기"""
        file_path = filedialog.askopenfilename(
            title="프리셋 가져오기",
            filetypes=[("JSON 파일", "*.json")]
        )
        
        if file_path:
            name = self.preset_manager.import_preset(file_path)
            if name:
                self._log(f"📥 프리셋 가져오기 완료: {name}")
                messagebox.showinfo("완료", f"프리셋 '{name}'을(를) 가져왔습니다.")
            else:
                messagebox.showerror("오류", "프리셋 가져오기에 실패했습니다.")
    
    def _load_file_with_preset(self):
        """파일과 프리셋을 한번에 열고 자동 전처리"""
        presets = self.preset_manager.list_presets()
        
        if not presets:
            messagebox.showinfo("알림", "저장된 프리셋이 없습니다.\n먼저 프리셋을 저장하세요.")
            return
        
        # 프리셋 선택 다이얼로그
        dialog = tk.Toplevel(self.root)
        dialog.title("파일 + 프리셋 열기")
        dialog.geometry("500x400")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="1. 적용할 프리셋을 선택하세요:", font=('맑은 고딕', 10, 'bold')).pack(anchor=tk.W, padx=10, pady=10)
        
        # 프리셋 목록
        list_frame = ttk.Frame(dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10)
        
        listbox = tk.Listbox(list_frame, height=8)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox.pack(fill=tk.BOTH, expand=True)
        
        for p in presets:
            display = f"{p['name']}"
            if p['description']:
                display += f" - {p['description'][:30]}"
            listbox.insert(tk.END, display)
        
        listbox.selection_set(0)
        
        ttk.Label(dialog, text="2. 파일 선택 후 자동 전처리가 진행됩니다.", 
                 font=('맑은 고딕', 10, 'bold')).pack(anchor=tk.W, padx=10, pady=(15, 5))
        
        auto_save = tk.BooleanVar(value=False)
        ttk.Checkbutton(dialog, text="전처리 후 자동 저장 (원본파일명_processed_...)", 
                       variable=auto_save).pack(anchor=tk.W, padx=10)
        
        def proceed():
            selection = listbox.curselection()
            if not selection:
                messagebox.showwarning("경고", "프리셋을 선택하세요.")
                return
            
            preset = presets[selection[0]]
            dialog.destroy()
            
            # 파일 선택
            file_path = filedialog.askopenfilename(
                title="데이터 파일 선택",
                filetypes=[
                    ("Excel/CSV 파일", "*.xlsx *.xls *.csv"),
                    ("Excel 파일", "*.xlsx *.xls"),
                    ("CSV 파일", "*.csv"),
                    ("모든 파일", "*.*")
                ]
            )
            
            if not file_path:
                return
            
            # 파일 로드
            success, msg = self.preprocessor.load_data(file_path)
            if not success:
                messagebox.showerror("오류", msg)
                return
            
            self.current_file = file_path
            self.file_label.config(text=os.path.basename(file_path), foreground="black")
            rows = len(self.preprocessor.original_df)
            cols = len(self.preprocessor.columns)
            self.data_info_label.config(text=f"📊 {rows:,}행 × {cols}열")
            
            self._update_preview()
            self._update_filter_columns()
            self._log(f"✅ {msg}")
            
            # 프리셋 적용
            preset_data = self.preset_manager.load_preset(preset['path'])
            if preset_data:
                settings = preset_data.get('settings', {})
                apply_settings_to_gui(self, settings)
                self.current_preset_name = preset['name']
                self._log(f"📂 프리셋 적용: {preset['name']}")
                
                # 자동 전처리 실행
                def auto_process():
                    time.sleep(0.5)  # UI 업데이트 대기
                    self._run_preprocessing()
                    
                    # 자동 저장
                    if auto_save.get():
                        from pathlib import Path
                        orig = Path(self.current_file)
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        output_path = orig.parent / f"{orig.stem}_processed_{timestamp}{orig.suffix}"
                        
                        success, result = self.preprocessor.save_data(str(output_path), self.current_file)
                        if success:
                            self.root.after(0, lambda: self._log(f"💾 자동 저장 완료: {result}"))
                
                thread = threading.Thread(target=auto_process, daemon=True)
                thread.start()
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text="파일 선택 및 시작", command=proceed).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="취소", command=dialog.destroy).pack(side=tk.LEFT, padx=5)


# pandas import for preview
import pandas as pd


def main():
    root = tk.Tk()
    app = DataPreprocessorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
