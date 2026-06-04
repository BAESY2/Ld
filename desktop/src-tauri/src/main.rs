// PLC 래더 라이브 에디터 — Tauri 데스크톱 셸.
// 윈도는 tauri.conf.json 의 url(http://localhost:8000)을 로드한다.
// 개발: 먼저 백엔드(`./run.sh`)를 띄운 뒤 `cargo tauri dev`.
// 배포(자체 포함): 백엔드를 PyInstaller 사이드카로 번들해 startup 에서 spawn 한다
//                  (아래 spawn_backend 주석 참고 — Phase J 에서 마무리).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        // .setup(|app| { spawn_backend(app)?; Ok(()) })  // 사이드카 번들 후 활성화
        .run(tauri::generate_context!())
        .expect("Tauri 앱 실행 실패");
}

// 배포 시: 번들된 백엔드 바이너리를 사이드카로 띄운다.
//
// fn spawn_backend(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
//     use tauri_plugin_shell::ShellExt;
//     app.shell().sidecar("plc-backend")?.spawn()?;
//     Ok(())
// }
