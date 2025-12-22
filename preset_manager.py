"""
프리셋 관리 모듈 (Preset Manager)
- 전처리 옵션을 JSON 파일로 저장/로드
- 프리셋 즐겨찾기 관리
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any


class PresetManager:
    """전처리 프리셋 관리 클래스"""
    
    # 프리셋 저장 기본 경로
    DEFAULT_PRESET_DIR = Path.home() / ".data_preprocessor" / "presets"
    
    def __init__(self, preset_dir: Optional[str] = None):
        """
        Args:
            preset_dir: 프리셋 저장 디렉토리 경로 (None이면 기본 경로 사용)
        """
        self.preset_dir = Path(preset_dir) if preset_dir else self.DEFAULT_PRESET_DIR
        self._ensure_preset_dir()
    
    def _ensure_preset_dir(self):
        """프리셋 디렉토리 생성"""
        self.preset_dir.mkdir(parents=True, exist_ok=True)
    
    def save_preset(self, 
                   name: str, 
                   settings: Dict[str, Any],
                   description: str = "") -> bool:
        """
        프리셋을 저장합니다.
        
        Args:
            name: 프리셋 이름
            settings: 설정 딕셔너리
            description: 프리셋 설명
            
        Returns:
            성공 여부
        """
        try:
            preset_data = {
                "name": name,
                "description": description,
                "created_at": datetime.now().isoformat(),
                "version": "1.2.0",
                "settings": settings
            }
            
            # 파일명에서 특수문자 제거
            safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
            file_path = self.preset_dir / f"{safe_name}.json"
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(preset_data, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            print(f"프리셋 저장 실패: {e}")
            return False
    
    def load_preset(self, name_or_path: str) -> Optional[Dict[str, Any]]:
        """
        프리셋을 로드합니다.
        
        Args:
            name_or_path: 프리셋 이름 또는 파일 경로
            
        Returns:
            프리셋 딕셔너리 또는 None
        """
        try:
            # 전체 경로인 경우
            if os.path.isfile(name_or_path):
                file_path = Path(name_or_path)
            else:
                # 이름으로 검색
                safe_name = "".join(c for c in name_or_path if c.isalnum() or c in (' ', '-', '_')).strip()
                file_path = self.preset_dir / f"{safe_name}.json"
            
            if not file_path.exists():
                return None
            
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"프리셋 로드 실패: {e}")
            return None
    
    def list_presets(self) -> List[Dict[str, str]]:
        """
        저장된 프리셋 목록을 반환합니다.
        
        Returns:
            프리셋 정보 목록 [{"name": str, "path": str, "description": str, "created_at": str}]
        """
        presets = []
        
        for file_path in self.preset_dir.glob("*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    presets.append({
                        "name": data.get("name", file_path.stem),
                        "path": str(file_path),
                        "description": data.get("description", ""),
                        "created_at": data.get("created_at", "")
                    })
            except:
                continue
        
        # 생성일 기준 역순 정렬
        presets.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return presets
    
    def delete_preset(self, name_or_path: str) -> bool:
        """
        프리셋을 삭제합니다.
        
        Args:
            name_or_path: 프리셋 이름 또는 파일 경로
            
        Returns:
            성공 여부
        """
        try:
            if os.path.isfile(name_or_path):
                os.remove(name_or_path)
                return True
            
            safe_name = "".join(c for c in name_or_path if c.isalnum() or c in (' ', '-', '_')).strip()
            file_path = self.preset_dir / f"{safe_name}.json"
            
            if file_path.exists():
                os.remove(file_path)
                return True
            
            return False
        except Exception as e:
            print(f"프리셋 삭제 실패: {e}")
            return False
    
    def export_preset(self, name: str, export_path: str) -> bool:
        """
        프리셋을 외부 경로로 내보냅니다.
        
        Args:
            name: 프리셋 이름
            export_path: 내보낼 경로
            
        Returns:
            성공 여부
        """
        try:
            preset = self.load_preset(name)
            if not preset:
                return False
            
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(preset, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            print(f"프리셋 내보내기 실패: {e}")
            return False
    
    def import_preset(self, import_path: str) -> Optional[str]:
        """
        외부 프리셋 파일을 가져옵니다.
        
        Args:
            import_path: 가져올 파일 경로
            
        Returns:
            가져온 프리셋 이름 또는 None
        """
        try:
            with open(import_path, 'r', encoding='utf-8') as f:
                preset_data = json.load(f)
            
            name = preset_data.get("name", Path(import_path).stem)
            
            # 기존 디렉토리에 저장
            safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
            file_path = self.preset_dir / f"{safe_name}.json"
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(preset_data, f, ensure_ascii=False, indent=2)
            
            return name
        except Exception as e:
            print(f"프리셋 가져오기 실패: {e}")
            return None


def create_settings_from_gui(app) -> Dict[str, Any]:
    """
    GUI 앱에서 현재 설정을 추출합니다.
    
    Args:
        app: DataPreprocessorApp 인스턴스
        
    Returns:
        설정 딕셔너리
    """
    # 필터 조건 추출
    filters = []
    for ff in app.filter_frames:
        f = ff.get_filter()
        if f:
            filters.append(f)
    
    return {
        "filters": filters,
        "outlier": {
            "apply": app.apply_outlier.get(),
            "method": app.outlier_method.get(),
            "action": app.outlier_action.get()
        },
        "normalize": {
            "apply": app.apply_normalize.get(),
            "method": app.normalize_method.get()
        },
        "time": {
            "normalize": app.apply_time_normalize.get(),
            "realign": app.apply_time_realign.get(),
            "start_time": app.start_time_entry.get(),
            "interval": app.interval_entry.get()
        }
    }


def apply_settings_to_gui(app, settings: Dict[str, Any]):
    """
    설정을 GUI 앱에 적용합니다.
    
    Args:
        app: DataPreprocessorApp 인스턴스
        settings: 설정 딕셔너리
    """
    # 기존 필터 제거
    for ff in app.filter_frames[:]:
        app._remove_filter(ff)
    
    # 필터 추가
    filters = settings.get("filters", [])
    for f in filters:
        app._add_filter()
        ff = app.filter_frames[-1]
        ff.column_var.set(f.get("column", ""))
        ff.operator_var.set(f.get("operator", "range"))
        ff._on_operator_change(None)
        
        if f.get("operator") == "range":
            ff.min_entry.delete(0, "end")
            ff.min_entry.insert(0, str(f.get("min", "")))
            ff.max_entry.delete(0, "end")
            ff.max_entry.insert(0, str(f.get("max", "")))
        else:
            ff.value_entry.delete(0, "end")
            ff.value_entry.insert(0, str(f.get("value", "")))
    
    # 이상값 처리 설정
    outlier = settings.get("outlier", {})
    app.apply_outlier.set(outlier.get("apply", True))
    app.outlier_method.set(outlier.get("method", "2.5sigma"))
    app.outlier_action.set(outlier.get("action", "drop"))
    
    # 정규화 설정
    normalize = settings.get("normalize", {})
    app.apply_normalize.set(normalize.get("apply", False))
    app.normalize_method.set(normalize.get("method", "zscore"))
    
    # 시간 처리 설정
    time_settings = settings.get("time", {})
    app.apply_time_normalize.set(time_settings.get("normalize", False))
    app.apply_time_realign.set(time_settings.get("realign", False))
    
    app.start_time_entry.delete(0, "end")
    app.start_time_entry.insert(0, time_settings.get("start_time", ""))
    
    app.interval_entry.delete(0, "end")
    app.interval_entry.insert(0, time_settings.get("interval", "2"))


if __name__ == "__main__":
    # 테스트
    manager = PresetManager()
    
    # 테스트 프리셋 저장
    test_settings = {
        "filters": [
            {"column": "AMBIENT_TEMP", "operator": ">=", "value": 15},
            {"column": "FAN_CURRENT", "operator": "range", "min": 30, "max": 50}
        ],
        "outlier": {
            "apply": True,
            "method": "2.5sigma",
            "action": "drop"
        },
        "normalize": {
            "apply": False,
            "method": "zscore"
        },
        "time": {
            "normalize": True,
            "realign": False,
            "start_time": "",
            "interval": "2"
        }
    }
    
    manager.save_preset("테스트 프리셋", test_settings, "테스트용 프리셋입니다")
    
    # 프리셋 목록
    print("저장된 프리셋:")
    for p in manager.list_presets():
        print(f"  - {p['name']}: {p['description']}")
    
    # 프리셋 로드
    loaded = manager.load_preset("테스트 프리셋")
    print(f"\n로드된 프리셋: {loaded['name']}")
