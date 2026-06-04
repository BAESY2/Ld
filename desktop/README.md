# 데스크톱 앱 (Tauri) — 맥 .app

웹앱(FastAPI + `frontend/`)을 그대로 감싸는 Tauri v2 셸이다. 동일한 코드를 웹과 데스크톱에서 함께 쓴다.

> ⚠️ 이 디렉터리는 **스캐폴드**다. 빌드에는 Rust 툴체인 + Tauri CLI 가 필요하며,
> 이 저장소의 CI(파이썬)에서는 빌드/검증하지 않는다. 맥에서 직접 빌드한다.

## 사전 준비 (맥)

```bash
# Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
# Tauri CLI
cargo install tauri-cli --version "^2"
```

## 개발 실행

```bash
# 1) 백엔드 먼저 (저장소 루트에서)
./run.sh                      # http://localhost:8000

# 2) 데스크톱 셸
cd desktop/src-tauri
cargo tauri dev               # 윈도가 localhost:8000 을 로드
```

## 배포(.app/.dmg) — 자체 포함 패키징

현재 셸은 `localhost:8000` 의 백엔드가 떠 있어야 동작한다. 백엔드까지 포함한
단일 `.app` 으로 만들려면:

1. 백엔드를 단일 실행파일로 번들: `pyinstaller -F -n plc-backend app/server.py` 류로
   uvicorn 진입점을 패키징.
2. 산출 바이너리를 `desktop/src-tauri/binaries/plc-backend-<target-triple>` 로 배치.
3. `src/main.rs` 의 `spawn_backend` 주석을 해제하고 `tauri.conf.json` 의
   `bundle.externalBin` 에 사이드카를 등록.
4. `cargo tauri build` → `.app` / `.dmg` 생성.

> 아이콘(`icons/icon.png`)은 추가 필요. `cargo tauri icon path/to/logo.png` 로 생성.

## 구조

```
desktop/src-tauri/
  tauri.conf.json   창/번들 설정, devUrl=localhost:8000, frontendDist=../../frontend
  Cargo.toml        Rust 의존성 (tauri 2, shell 플러그인)
  build.rs          tauri-build
  src/main.rs       앱 진입점 (+ 사이드카 spawn 자리)
```
