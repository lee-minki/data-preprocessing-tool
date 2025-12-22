"""
데이터 전처리 GUI 애플리케이션
- tkinter 기반 사용자 인터페이스
- 파일 로드, 필터링, 이상값 처리, 저장 기능
- 대용량 데이터 처리를 위한 진행률 표시 및 스레딩
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
import os
import threading
import time
from typing import List, Dict, Optional
from data_preprocessor import DataPreprocessor


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
        self.root.geometry("900x850")
        self.root.minsize(800, 750)
        
        self.preprocessor = DataPreprocessor()
        self.current_file: Optional[str] = None
        self.filter_frames: List[FilterFrame] = []
        self.is_processing = False
        
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
        
        self.root.bind("<Control-o>", lambda e: self._load_file())
        self.root.bind("<Control-s>", lambda e: self._save_file())
    
    def _create_widgets(self):
        """위젯 생성"""
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
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
            ttk.Radiobutton(method_frame, text=text, variable=self.outlier_method, 
                           value=value).pack(side=tk.LEFT, padx=10)
        
        # 처리 방법
        action_frame = ttk.Frame(outlier_frame)
        action_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(action_frame, text="처리:").pack(side=tk.LEFT)
        
        self.outlier_action = tk.StringVar(value='nan')
        ttk.Radiobutton(action_frame, text="해당 값만 NaN으로", variable=self.outlier_action, 
                       value='nan').pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(action_frame, text="행 전체 삭제", variable=self.outlier_action, 
                       value='drop').pack(side=tk.LEFT, padx=10)
        
        # 이상값 처리 체크박스
        self.apply_outlier = tk.BooleanVar(value=True)
        ttk.Checkbutton(outlier_frame, text="이상값 처리 적용", 
                       variable=self.apply_outlier).pack(anchor=tk.W, pady=2)
        
        # === 정규화 섹션 ===
        norm_frame = ttk.LabelFrame(main_frame, text="📈 정규화 (선택사항)", padding=10)
        norm_frame.pack(fill=tk.X, pady=5)
        
        self.apply_normalize = tk.BooleanVar(value=False)
        ttk.Checkbutton(norm_frame, text="정규화 적용", 
                       variable=self.apply_normalize).pack(side=tk.LEFT)
        
        self.normalize_method = tk.StringVar(value='zscore')
        ttk.Radiobutton(norm_frame, text="Z-Score", variable=self.normalize_method, 
                       value='zscore').pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(norm_frame, text="Min-Max (0~1)", variable=self.normalize_method, 
                       value='minmax').pack(side=tk.LEFT, padx=10)
        
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
            self._log(f"   감지된 숫자 컬럼: {', '.join(self.preprocessor.numeric_columns)}")
            
            # 대용량 데이터 안내
            if rows >= 100000:
                self._log(f"⚠️ 대용량 데이터 ({rows:,}행) - 처리에 시간이 소요될 수 있습니다.")
        else:
            self._update_progress(0, "파일 로드 실패")
            messagebox.showerror("오류", msg)
            self._log(f"❌ {msg}")
    
    def _update_preview(self):
        """미리보기 테이블 업데이트"""
        # 기존 데이터 삭제
        self.preview_tree.delete(*self.preview_tree.get_children())
        
        df = self.preprocessor.get_preview(10)
        if df.empty:
            return
        
        # 컬럼 설정
        columns = list(df.columns)
        self.preview_tree['columns'] = columns
        
        for col in columns:
            self.preview_tree.heading(col, text=col)
            self.preview_tree.column(col, width=100, minwidth=50)
        
        # 데이터 추가
        for _, row in df.iterrows():
            values = [str(v)[:20] for v in row.values]  # 값 길이 제한
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
            
            self._update_progress(90, "결과 정리 중...", time.time() - start_time)
            
            # 4. 결과 표시
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
            from datetime import datetime
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


def main():
    root = tk.Tk()
    app = DataPreprocessorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
