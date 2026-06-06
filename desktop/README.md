# 데스크톱 / 오프라인 앱

웹앱(FastAPI + `frontend/`)을 **인터넷·파이썬 설치 없이 더블클릭으로 도는 단일 앱**으로
패키징한다. 두 단계가 있다:

1. **자가포함 백엔드(필수)** — PyInstaller 로 백엔드+정적 프론트+RAG 코퍼스를 하나의
   실행파일로 묶는다. 실행하면 로컬 서버를 띄우고 브라우저로 스튜디오를 연다.
   Rust 불필요, 맥/윈도/리눅스 공통.
2. **Tauri 네이티브 창(선택)** — 위 백엔드를 사이드카로 감싸 네이티브 `.app`/`.dmg`/`.exe`
   창으로 만든다. Rust 툴체인 필요.

> 산출물은 오프라인 공장(폐쇄망)에서 그대로 동작한다. 결정론 코어(레시피·합성·검증·
> 시뮬·벤더 에미터)는 키 없이 돌고, 자연어 생성(LLM)만 `ANTHROPIC_API_KEY` 가 필요하다.

## 한 번에 빌드

```bash
# 저장소 루트에서. 먼저 web 의존성이 있어야 한다: pip install -e ".[web]"
bash scripts/build_desktop.sh            # → dist/plc-backend  (자가포함 단일 실행파일)
bash scripts/build_desktop.sh --tauri    # → 위 + 네이티브 창(.app/.dmg/.exe)
```

- `dist/plc-backend` 를 실행 → 자동으로 `http://127.0.0.1:8000/studio.html` 이 열린다.
- `--tauri` 는 PyInstaller 산출물을 `desktop/src-tauri/binaries/plc-backend-<target-triple>`
  로 배치하고 `cargo tauri icon` + `cargo tauri build` 까지 수행한다.

## 사전 준비

- 백엔드 번들: `pip install -e ".[web]"` (현재 venv 에 fastapi/uvicorn). 빌드 스크립트가
  `pyinstaller` 는 자동 설치한다.
- Tauri(선택): Rust + Tauri CLI
  ```bash
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
  cargo install tauri-cli --version "^2"
  ```

## 개발 실행(번들 없이)

```bash
./run.sh                       # 백엔드: http://localhost:8000
cd desktop/src-tauri && cargo tauri dev   # 네이티브 창이 localhost:8000/studio.html 로드
```

## 동작 원리

- `desktop/backend_entry.py` — uvicorn 으로 `app.server` 를 띄우는 진입점. PyInstaller
  onefile 의 추출 루트(`_MEIPASS`)가 `app`/`frontend`/`data` 를 모두 담으므로, 경로 설정
  없이 정적 프론트·RAG 코퍼스가 함께 로드된다. `LADDER_NO_BROWSER=1` 이면 브라우저
  자동 열기를 끈다(네이티브 창이 대신 띄움).
- `desktop/plc-backend.spec` — PyInstaller 스펙(z3 등 네이티브 의존성 포함 수집).
- `src/main.rs` — 배포 빌드에서 `plc-backend` 사이드카를 `LADDER_NO_BROWSER=1` 로 spawn.
- `tauri.conf.json` — 창은 `http://localhost:8000/studio.html`(프론트의 `/api` fetch 가
  같은 origin 으로 가야 하므로 백엔드를 직접 로드), `bundle.externalBin` 에 사이드카 등록.

## 구조

```
desktop/
  backend_entry.py     자가포함 백엔드 진입점(uvicorn + 브라우저 열기)
  plc-backend.spec     PyInstaller 스펙(frontend/·data/ 동봉, z3 수집)
  src-tauri/
    tauri.conf.json    창/번들/사이드카 설정 (url=localhost:8000/studio.html)
    Cargo.toml         Rust 의존성 (tauri 2 + shell 플러그인)
    build.rs           tauri-build
    src/main.rs         앱 진입점 + 사이드카 spawn
    icons/icon.png     시드 아이콘(빌드 시 cargo tauri icon 이 전체셋 생성)
```

> CI(파이썬)에서는 데스크톱 빌드를 검증하지 않는다(Rust/네이티브 툴체인 필요).
> 백엔드 진입점 자체는 `python desktop/backend_entry.py` 로 로컬에서 바로 확인 가능.
