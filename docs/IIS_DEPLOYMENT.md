# PreprocessingWeb IIS 배포 절차

## 배포 목표

- IIS 사이트명: `PreprocessingWeb`
- 서버: `192.9.88.241` / IIS Manager 기준 `RIMS-WEB`
- 바인딩: `http://192.9.88.241:8511/`
- 물리 경로: `C:\PreprocessingWeb`
- 배포 형태: 정적 웹 패키지 ZIP을 서버담당자에게 전달 후 IIS 사이트 경로에 교체

## 서버담당자에게 전달할 산출물

1. `PreprocessingWeb_iis_YYYYMMDD_HHMMSS.zip`
2. 같은 이름의 `.sha256` 체크섬 파일
3. 이 문서 또는 아래 작업 요청 문구

패키지 생성 명령:

```bash
cd /Users/mk/worksapces/Preprocessing
python3 scripts/package_iis_deploy.py
```

생성 위치:

```text
/Users/mk/worksapces/Preprocessing/dist_iis/
```

## ZIP 내부 구성

필수 파일만 포함합니다.

- `Preprocessing.html` — 기본 실행 화면
- `MANUAL.html` — 사용자 매뉴얼
- `program_intro.html` — 프로그램 소개
- `web.config` — IIS 기본문서/보안 헤더/차단 확장자 설정
- `assets/vendor/chart.umd.min.js`
- `assets/vendor/xlsx.full.min.js`
- 소개/매뉴얼용 이미지·영상
- `manual_assets/screenshots/*`
- `DEPLOY_MANIFEST.txt`

다음 항목은 패키지에 넣지 않습니다.

- `.git`, `.omx`, `.playwright-mcp`, `.ruff_cache`
- Python 소스/테스트 파일
- 작업용 ZIP, JSON, MD, 스크립트 파일
- 샘플/임시 데이터

## IIS 배포 작업 순서

### 1. 백업

서버에서 기존 경로를 백업합니다.

```powershell
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
Copy-Item C:\PreprocessingWeb "C:\PreprocessingWeb_backup_$stamp" -Recurse
```

### 2. 사이트 정지

IIS 관리자에서:

- 사이트 > `PreprocessingWeb` 선택
- 오른쪽 작업 > 중지

또는 PowerShell:

```powershell
Import-Module WebAdministration
Stop-Website -Name "PreprocessingWeb"
```

### 3. 파일 교체

ZIP을 임시 폴더에 풀고 `C:\PreprocessingWeb`에 복사합니다.

권장 방식:

```powershell
Remove-Item C:\PreprocessingWeb\* -Recurse -Force
Expand-Archive .\PreprocessingWeb_iis_YYYYMMDD_HHMMSS.zip -DestinationPath C:\PreprocessingWeb -Force
```

주의:

- ZIP 내부 파일들이 `C:\PreprocessingWeb\Preprocessing.html` 형태로 바로 풀려야 합니다.
- `C:\PreprocessingWeb\PreprocessingWeb_iis_...\Preprocessing.html`처럼 한 단계 더 들어가면 IIS 기본문서가 안 열립니다.

### 4. 사이트 시작

IIS 관리자에서:

- 사이트 > `PreprocessingWeb` 선택
- 오른쪽 작업 > 시작

또는 PowerShell:

```powershell
Start-Website -Name "PreprocessingWeb"
```

### 5. 확인 URL

브라우저에서 확인:

```text
http://192.9.88.241:8511/
http://192.9.88.241:8511/Preprocessing.html
http://192.9.88.241:8511/MANUAL.html
http://192.9.88.241:8511/program_intro.html
```

## 배포 후 점검표

서버담당자 또는 검수자가 아래를 확인합니다.

- [ ] `http://192.9.88.241:8511/` 접속 시 `Preprocessing.html`이 기본으로 열린다.
- [ ] 화면 상단 메뉴에서 메인/소개/매뉴얼 이동이 된다.
- [ ] XLSX 업로드가 된다.
- [ ] 데이터 미리보기 테이블이 표시된다.
- [ ] 전처리 실행 버튼이 동작한다.
- [ ] 결과 XLSX 다운로드가 된다.
- [ ] 매뉴얼 이미지가 깨지지 않는다.
- [ ] 소개 페이지 영상이 재생되거나 최소한 깨진 링크로 보이지 않는다.
- [ ] `http://192.9.88.241:8511/web.config` 접근이 차단된다.
- [ ] `http://192.9.88.241:8511/DEPLOY_MANIFEST.txt` 접근은 서버 정책에 따라 허용/차단 여부를 결정한다. 외부 공유 서버라면 제거 권장.

## 보안 기준

이번 배포 패키지는 정적 웹 중심입니다. IIS에 Python 포털 서버를 같이 붙이는 방식은 기본 배포안에서 제외합니다.

이유:

- 정적 웹은 IIS만으로 운영 가능해서 장애 면적이 작습니다.
- OPC endpoint/API 기능은 별도 인증·망분리·allowlist가 필요한 서버 기능입니다.
- 서버담당자에게 넘기는 1차 배포물은 `정적 파일 + web.config`가 가장 안전합니다.

OPC helper API까지 운영하려면 별도 배포안이 필요합니다.

- Windows 서비스 또는 작업 스케줄러로 Python backend 실행
- localhost reverse proxy 구성
- endpoint allowlist 설정
- Origin/Host 제한 확인
- 방화벽에서 외부 접근 차단

## 서버담당자 전달 문구 예시

```text
PreprocessingWeb IIS 정적 웹 배포 요청드립니다.

- 대상 서버: 192.9.88.241 / RIMS-WEB
- IIS 사이트: PreprocessingWeb
- 바인딩: 192.9.88.241:8511(http)
- 물리 경로: C:\PreprocessingWeb
- 요청 작업:
  1) 기존 C:\PreprocessingWeb 백업
  2) 사이트 PreprocessingWeb 중지
  3) 전달 ZIP을 C:\PreprocessingWeb에 바로 압축 해제
  4) 사이트 시작
  5) http://192.9.88.241:8511/ 접속 확인

주의: ZIP 내부 파일이 C:\PreprocessingWeb 바로 아래에 위치해야 합니다.
```

## 롤백

문제 발생 시:

```powershell
Stop-Website -Name "PreprocessingWeb"
Remove-Item C:\PreprocessingWeb\* -Recurse -Force
Copy-Item C:\PreprocessingWeb_backup_YYYYMMDD_HHMMSS\* C:\PreprocessingWeb -Recurse
Start-Website -Name "PreprocessingWeb"
```
