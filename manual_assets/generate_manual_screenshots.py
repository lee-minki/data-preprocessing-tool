from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QColor, QFont, QPalette
from PyQt5.QtWidgets import QApplication, QDialog, QGroupBox, QListWidget, QStyleFactory

from gui_app_mac import DataPreprocessorMac


OUT_DIR = Path(__file__).resolve().parent / "screenshots"
SAMPLE_PATH = PROJECT_ROOT / "sample_data.csv"


WINDOWS_GRAY_STYLESHEET = """
QMainWindow, QWidget {
    background: #ececec;
    color: #222222;
    font-family: 'Arial';
    font-size: 11px;
}
QGroupBox {
    background: #f4f4f4;
    border: 1px solid #b9b9b9;
    border-radius: 4px;
    margin-top: 10px;
    padding-top: 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: #202020;
}
QPushButton {
    background: #e6e6e6;
    border: 1px solid #9d9d9d;
    border-radius: 3px;
    padding: 4px 10px;
}
QPushButton:hover {
    background: #efefef;
}
QPushButton:pressed {
    background: #dadada;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget, QTextEdit, QTableWidget {
    background: #ffffff;
    border: 1px solid #a8a8a8;
    border-radius: 2px;
    selection-background-color: #cfe3ff;
    selection-color: #111111;
}
QHeaderView::section {
    background: #e1e1e1;
    border: 1px solid #b2b2b2;
    padding: 4px;
}
QProgressBar {
    background: #ffffff;
    border: 1px solid #a2a2a2;
    text-align: center;
}
QProgressBar::chunk {
    background: #a9bddb;
}
QLabel {
    color: #222222;
}
"""


def apply_windows_gray_theme(app: QApplication, window: DataPreprocessorMac) -> None:
    app.setStyle(QStyleFactory.create("Fusion"))

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#ececec"))
    palette.setColor(QPalette.WindowText, QColor("#222222"))
    palette.setColor(QPalette.Base, QColor("#ffffff"))
    palette.setColor(QPalette.AlternateBase, QColor("#f6f6f6"))
    palette.setColor(QPalette.ToolTipBase, QColor("#ffffdc"))
    palette.setColor(QPalette.ToolTipText, QColor("#222222"))
    palette.setColor(QPalette.Text, QColor("#222222"))
    palette.setColor(QPalette.Button, QColor("#e6e6e6"))
    palette.setColor(QPalette.ButtonText, QColor("#222222"))
    palette.setColor(QPalette.Highlight, QColor("#cfe3ff"))
    palette.setColor(QPalette.HighlightedText, QColor("#111111"))
    app.setPalette(palette)
    app.setFont(QFont("Arial", 10))

    window.setStyleSheet(WINDOWS_GRAY_STYLESHEET)
    window.file_label.setStyleSheet("color: #666666;")
    window.data_info_label.setStyleSheet("color: #2f5f9d; font-weight: 600;")
    window.preview_table.setStyleSheet(
        "background: #ffffff; border: 1px solid #a8a8a8; font-size: 10px;"
    )
    window.process_btn.setStyleSheet(
        "font-weight: 700; padding: 8px 16px; background: #dcdcdc; border: 1px solid #909090; border-radius: 3px;"
    )


def load_sample(window: DataPreprocessorMac) -> None:
    success, msg = window.preprocessor.load_data(str(SAMPLE_PATH.resolve()))
    if not success:
        raise RuntimeError(msg)

    window.current_file = str(SAMPLE_PATH.resolve())
    window.file_label.setText(SAMPLE_PATH.name)
    window.file_label.setStyleSheet("color: #222222;")
    window.data_info_label.setText(
        f"📊 {len(window.preprocessor.original_df):,}행 × {len(window.preprocessor.columns)}열"
    )
    window._update_preview()
    window._update_filter_columns()
    window._log(f"✅ {msg}")
    window.progress_bar.setValue(100)
    window.progress_label.setText("파일 로드 완료!")


def configure_demo_filter(window: DataPreprocessorMac) -> None:
    window._add_filter()
    fw = window.filter_widgets[-1]
    fw.column_combo.setCurrentText("AMBIENT_TEMP")
    fw.operator_combo.setCurrentText(">=")
    fw.value_edit.setText("15")


def run_demo_preprocessing(window: DataPreprocessorMac) -> None:
    filters = []
    for widget in window.filter_widgets:
        item = widget.get_filter()
        if item:
            filters.append(item)

    if filters:
        success, msg = window.preprocessor.apply_filters(filters)
        window._log(f"{'✅' if success else '❌'} {msg}")
    else:
        window.preprocessor.processed_df = window.preprocessor.original_df.copy()
        window._log("ℹ️ 필터 없음 - 전체 데이터 사용")

    if window.apply_outlier.isChecked():
        method = window.outlier_method_group.checkedButton().property("value")
        success, msg = window.preprocessor.remove_outliers(method=method, action="drop")
        window._log(f"{'✅' if success else '❌'} {msg}")

    window.progress_bar.setValue(100)
    window.progress_label.setText("✅ 완료!")
    window._update_preview()
    window._log(window.preprocessor.get_summary())


def save_main_group_capture(
    window: DataPreprocessorMac, title: str, file_name: str
) -> None:
    for group in window.findChildren(QGroupBox):
        if group.title() == title:
            group.grab().save(str(OUT_DIR / file_name))
            return
    raise RuntimeError(f"Group not found: {title}")


def generate() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    app = QApplication([])
    window = DataPreprocessorMac()
    window.setGeometry(80, 40, 950, 850)
    apply_windows_gray_theme(app, window)
    load_sample(window)
    configure_demo_filter(window)

    window.show()
    app.processEvents()
    window.grab().save(str(OUT_DIR / "main_overview.png"))
    save_main_group_capture(window, "🕐 시간 처리 (선택사항)", "time_processing.png")

    run_demo_preprocessing(window)
    app.processEvents()
    window.grab().save(str(OUT_DIR / "preprocessing_done.png"))

    captured = {"done": False}

    def capture_validation_dialog() -> None:
        dialogs = [
            widget
            for widget in app.topLevelWidgets()
            if isinstance(widget, QDialog)
            and widget.windowTitle() == "🧪 Validation 데이터 생성"
        ]
        if not dialogs:
            return

        dialog = dialogs[0]
        dialog.resize(760, 680)
        dialog.setStyleSheet(WINDOWS_GRAY_STYLESHEET)
        app.processEvents()
        dialog.grab().save(str(OUT_DIR / "validation_dialog.png"))
        dialog.close()
        captured["done"] = True

    QTimer.singleShot(700, capture_validation_dialog)
    window._show_simulation_dialog()
    app.processEvents()

    if not captured["done"]:
        raise RuntimeError("Validation dialog capture failed")

    chart_captured = {"done": False}

    def capture_trend_dialog() -> None:
        dialogs = [
            widget
            for widget in app.topLevelWidgets()
            if isinstance(widget, QDialog)
            and widget.windowTitle() == "📊 트렌드 차트 (다중 비교)"
        ]
        if not dialogs:
            return

        dialog = dialogs[0]
        dialog.resize(1120, 780)
        dialog.setStyleSheet(WINDOWS_GRAY_STYLESHEET)

        for list_widget in dialog.findChildren(QListWidget):
            if list_widget.count() >= 3:
                for idx in range(3):
                    list_widget.item(idx).setSelected(True)
                break

        app.processEvents()
        dialog.grab().save(str(OUT_DIR / "trend_chart.png"))
        dialog.close()
        chart_captured["done"] = True

    QTimer.singleShot(700, capture_trend_dialog)
    window._show_trend_chart()
    app.processEvents()

    if not chart_captured["done"]:
        raise RuntimeError("Trend chart capture failed")

    about_captured = {"done": False}

    def capture_about_dialog() -> None:
        dialogs = [
            widget
            for widget in app.topLevelWidgets()
            if isinstance(widget, QDialog) and widget.windowTitle() == "프로그램 정보"
        ]
        if not dialogs:
            return

        dialog = dialogs[0]
        dialog.resize(500, 500)
        dialog.setStyleSheet(WINDOWS_GRAY_STYLESHEET)
        app.processEvents()
        dialog.grab().save(str(OUT_DIR / "about_dialog.png"))
        dialog.close()
        about_captured["done"] = True

    QTimer.singleShot(700, capture_about_dialog)
    window._show_about()
    app.processEvents()

    if not about_captured["done"]:
        raise RuntimeError("About dialog capture failed")

    window.close()


if __name__ == "__main__":
    generate()
