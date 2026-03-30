"""
웹 서버 기반 데이터 전처리 애플리케이션
- Flask 기반 REST API
- 윈도우 서버에서 포트를 지정해 실행
- 기존 data_preprocessor.py 엔진 그대로 활용
- Excel/CSV 파일 업로드 및 다운로드 지원
"""

import os
import sys
import json
import uuid
import argparse
import tempfile
import traceback
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# Flask
from flask import (
    Flask,
    request,
    jsonify,
    send_file,
    render_template_string,
    session,
)

import pandas as pd

# 기존 모듈 임포트
from data_preprocessor import DataPreprocessor
from preset_manager import PresetManager
from version import __version__, APP_NAME, CHANGELOG, FEATURES, get_developer_info

# ──────────────────────────────────────────────
# Flask 앱 설정
# ──────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200MB

# 세션별 전처리 인스턴스 관리
sessions: Dict[str, Dict[str, Any]] = {}

# 업로드/다운로드 임시 디렉토리
UPLOAD_DIR = Path(tempfile.gettempdir()) / "dp_web_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "dp_web_downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 프리셋 매니저 (서버 공용)
preset_manager = PresetManager()


def get_session_data() -> Dict[str, Any]:
    """현재 세션의 전처리 인스턴스를 반환/생성"""
    sid = session.get("sid")
    if not sid or sid not in sessions:
        sid = str(uuid.uuid4())
        session["sid"] = sid
        sessions[sid] = {
            "preprocessor": DataPreprocessor(),
            "current_file": None,
            "original_filename": None,
            "created": datetime.now().isoformat(),
        }
    return sessions[sid]


# ──────────────────────────────────────────────
# API 엔드포인트
# ──────────────────────────────────────────────


@app.route("/")
def index():
    """메인 페이지"""
    html_path = Path(__file__).parent / "web_app_server.html"
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


@app.route("/api/info")
def api_info():
    """앱 정보"""
    dev = get_developer_info()
    return jsonify(
        {
            "name": APP_NAME,
            "version": __version__,
            "features": FEATURES,
            "developer": dev,
            "changelog": CHANGELOG,
        }
    )


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """파일 업로드 및 로드"""
    if "file" not in request.files:
        return jsonify({"success": False, "message": "파일이 없습니다."}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"success": False, "message": "파일이 선택되지 않았습니다."}), 400

    # 확장자 검증
    allowed = {".csv", ".xlsx", ".xls"}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed:
        return (
            jsonify(
                {
                    "success": False,
                    "message": f"지원하지 않는 형식입니다: {ext} (CSV, XLSX, XLS만 지원)",
                }
            ),
            400,
        )

    # 임시 파일로 저장
    save_name = f"{uuid.uuid4()}{ext}"
    save_path = UPLOAD_DIR / save_name
    file.save(str(save_path))

    # 데이터 로드
    sd = get_session_data()
    pp: DataPreprocessor = sd["preprocessor"]
    success, msg = pp.load_data(str(save_path))

    if success:
        sd["current_file"] = str(save_path)
        sd["original_filename"] = file.filename

        # 미리보기 데이터 (10행)
        preview = pp.get_preview(10)
        preview_data = []
        for _, row in preview.iterrows():
            row_dict = {}
            for col in preview.columns:
                val = row[col]
                if pd.isna(val):
                    row_dict[col] = ""
                elif isinstance(val, (pd.Timestamp, datetime)):
                    row_dict[col] = str(val)
                else:
                    row_dict[col] = val
            preview_data.append(row_dict)

        return jsonify(
            {
                "success": True,
                "message": msg,
                "data": {
                    "rows": len(pp.original_df),
                    "cols": len(pp.columns),
                    "columns": pp.columns,
                    "numeric_columns": pp.numeric_columns,
                    "date_column": pp.date_column,
                    "preview": preview_data,
                },
            }
        )
    else:
        return jsonify({"success": False, "message": msg}), 400


@app.route("/api/process", methods=["POST"])
def api_process():
    """전처리 실행"""
    sd = get_session_data()
    pp: DataPreprocessor = sd["preprocessor"]

    if pp.original_df is None:
        return jsonify({"success": False, "message": "먼저 파일을 업로드하세요."}), 400

    params = request.get_json() or {}
    logs = []

    try:
        pp.reset_processing_state()
        logs.append(f"🔄 전처리 시작... (총 {len(pp.original_df):,}행)")

        # 1. 필터링
        filters = params.get("filters", [])
        if filters:
            success, msg = pp.apply_filters(filters)
            logs.append(f"{'✅' if success else '❌'} {msg}")
            if not success:
                return jsonify({"success": False, "message": msg, "logs": logs})
        else:
            pp.processed_df = pp.original_df.copy()
            pp.stats["filtered_rows"] = len(pp.original_df)
            pp.stats["filter_removed"] = 0
            logs.append("ℹ️ 필터 조건 없음 - 전체 데이터 사용")

        # 2. 이상값 처리
        outlier = params.get("outlier", {})
        if outlier.get("apply", True):
            method = outlier.get("method", "2.5sigma")
            success, msg = pp.remove_outliers(method=method, action="drop")
            logs.append(f"{'✅' if success else '❌'} {msg}")

        # 3. 시간 정규화
        time_opts = params.get("time", {})
        interval = int(time_opts.get("interval", 2))

        if time_opts.get("normalize", False):
            success, msg = pp.normalize_timestamps(interval)
            logs.append(f"{'✅' if success else '❌'} {msg}")

        # 4. 시간 재정렬
        if time_opts.get("realign", False):
            start_time = time_opts.get("start_time", "")
            if start_time:
                success, msg = pp.realign_timestamps(start_time, interval)
                logs.append(f"{'✅' if success else '❌'} {msg}")

        # 결과 요약
        logs.append("")
        logs.append(pp.get_summary())
        logs.append("✅ 전처리 완료! '결과 저장' 버튼을 눌러 저장하세요.")

        # 미리보기
        preview = pp.get_preview(10)
        preview_data = []
        for _, row in preview.iterrows():
            row_dict = {}
            for col in preview.columns:
                val = row[col]
                if pd.isna(val):
                    row_dict[col] = ""
                elif isinstance(val, (pd.Timestamp, datetime)):
                    row_dict[col] = str(val)
                else:
                    row_dict[col] = val
            preview_data.append(row_dict)

        return jsonify(
            {
                "success": True,
                "message": "전처리 완료",
                "logs": logs,
                "stats": pp.stats,
                "preview": preview_data,
                "final_rows": len(pp.processed_df),
            }
        )

    except Exception as e:
        logs.append(f"❌ 오류: {str(e)}")
        return (
            jsonify(
                {
                    "success": False,
                    "message": str(e),
                    "logs": logs,
                    "traceback": traceback.format_exc(),
                }
            ),
            500,
        )


@app.route("/api/download", methods=["POST"])
def api_download():
    """전처리 결과 다운로드"""
    sd = get_session_data()
    pp: DataPreprocessor = sd["preprocessor"]

    if pp.processed_df is None:
        return jsonify({"success": False, "message": "저장할 데이터가 없습니다."}), 400

    params = request.get_json() or {}
    fmt = params.get("format", "csv")  # csv or xlsx

    original_name = sd.get("original_filename", "data")
    base_name = Path(original_name).stem if original_name else "data"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if fmt == "xlsx":
        out_name = f"{base_name}_processed_{timestamp}.xlsx"
    else:
        out_name = f"{base_name}_processed_{timestamp}.csv"

    out_path = DOWNLOAD_DIR / out_name

    try:
        success, result = pp.save_data(str(out_path), sd.get("current_file"))
        if success:
            return jsonify(
                {
                    "success": True,
                    "download_url": f"/api/download_file/{out_name}",
                    "filename": out_name,
                }
            )
        else:
            return jsonify({"success": False, "message": result}), 500
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/download_file/<filename>")
def api_download_file(filename):
    """파일 다운로드 실행"""
    file_path = DOWNLOAD_DIR / filename
    if not file_path.exists():
        return jsonify({"success": False, "message": "파일을 찾을 수 없습니다."}), 404
    return send_file(str(file_path), as_attachment=True, download_name=filename)


@app.route("/api/validation", methods=["POST"])
def api_validation():
    """Validation 데이터 생성"""
    sd = get_session_data()
    pp: DataPreprocessor = sd["preprocessor"]

    if pp.processed_df is None:
        return (
            jsonify({"success": False, "message": "먼저 전처리를 실행하세요."}),
            400,
        )

    params = request.get_json() or {}
    target_columns = params.get("target_columns", [])
    validation_ratio = params.get("ratio", 0.20)
    segment_ratios = params.get("segment_ratios", [25, 25, 25, 25])
    sigma_start = params.get("sigma_start", 2.5)
    sigma_end = params.get("sigma_end", 4.0)
    interval = params.get("interval", None)

    original_name = sd.get("original_filename", "data")
    base_name = Path(original_name).stem if original_name else "data"

    # DOWNLOAD_DIR에 저장
    original_path = DOWNLOAD_DIR / f"{base_name}.tmp"

    try:
        success, msg, paths = pp.generate_validation_outputs(
            target_columns=target_columns,
            validation_ratio=validation_ratio / 100.0
            if validation_ratio > 1
            else validation_ratio,
            segment_ratios=segment_ratios,
            sigma_start=sigma_start,
            sigma_end=sigma_end,
            interval_minutes=interval,
            original_path=str(original_path),
        )

        if success:
            # 파일 경로를 다운로드 URL로 변환
            download_files = {}
            for key, path in paths.items():
                fname = Path(path).name
                # 파일을 DOWNLOAD_DIR로 이동
                dest = DOWNLOAD_DIR / fname
                if Path(path).exists() and str(Path(path).parent) != str(DOWNLOAD_DIR):
                    import shutil

                    shutil.move(str(path), str(dest))
                download_files[key] = {
                    "filename": fname,
                    "url": f"/api/download_file/{fname}",
                }

            return jsonify(
                {
                    "success": True,
                    "message": msg,
                    "files": download_files,
                }
            )
        else:
            return jsonify({"success": False, "message": msg}), 400

    except Exception as e:
        return (
            jsonify(
                {
                    "success": False,
                    "message": str(e),
                    "traceback": traceback.format_exc(),
                }
            ),
            500,
        )


# ──────────────────────────────────────────────
# 프리셋 API
# ──────────────────────────────────────────────


@app.route("/api/presets", methods=["GET"])
def api_presets_list():
    """프리셋 목록"""
    presets = preset_manager.list_presets()
    return jsonify({"presets": presets})


@app.route("/api/presets", methods=["POST"])
def api_presets_save():
    """프리셋 저장"""
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    settings = data.get("settings", {})
    description = data.get("description", "")

    if not name:
        return jsonify({"success": False, "message": "이름을 입력하세요."}), 400

    success = preset_manager.save_preset(name, settings, description)
    return jsonify({"success": success})


@app.route("/api/presets/<name>", methods=["GET"])
def api_presets_load(name):
    """프리셋 로드"""
    preset = preset_manager.load_preset(name)
    if preset:
        return jsonify({"success": True, "preset": preset})
    return jsonify({"success": False, "message": "프리셋을 찾을 수 없습니다."}), 404


@app.route("/api/presets/<name>", methods=["DELETE"])
def api_presets_delete(name):
    """프리셋 삭제"""
    success = preset_manager.delete_preset(name)
    return jsonify({"success": success})


# ──────────────────────────────────────────────
# 정리 (오래된 세션/파일)
# ──────────────────────────────────────────────


def cleanup_old_files(directory: Path, max_age_hours: int = 24):
    """오래된 임시 파일 정리"""
    import time

    now = time.time()
    for f in directory.iterdir():
        if f.is_file():
            age_hours = (now - f.stat().st_mtime) / 3600
            if age_hours > max_age_hours:
                try:
                    f.unlink()
                except OSError:
                    pass


# ──────────────────────────────────────────────
# 메인 실행
# ──────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} - 웹 서버 (v{__version__})"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8511,
        help="서버 포트 (기본: 8511)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="바인드 주소 (기본: 0.0.0.0 = 모든 인터페이스)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="디버그 모드",
    )

    args = parser.parse_args()

    # 시작 시 오래된 파일 정리
    cleanup_old_files(UPLOAD_DIR)
    cleanup_old_files(DOWNLOAD_DIR)

    print(f"\n{'='*60}")
    print(f"  {APP_NAME} v{__version__} - 웹 서버")
    print(f"{'='*60}")
    print(f"  🌐 http://{args.host}:{args.port}")
    print(f"  📁 업로드 디렉토리: {UPLOAD_DIR}")
    print(f"  💾 다운로드 디렉토리: {DOWNLOAD_DIR}")
    print(f"{'='*60}\n")

    app.run(host=args.host, port=args.port, debug=args.debug)
