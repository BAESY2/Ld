// PLC 래더 스튜디오 — Tauri 데스크톱 셸.
// 배포 빌드는 번들된 백엔드(plc-backend 사이드카)를 띄우고, 창은
// http://localhost:8000/studio.html 을 로드한다(프론트의 /api fetch 가 같은
// origin 으로 가야 하므로 창은 반드시 localhost 백엔드를 직접 로드한다).
// 개발: 먼저 `./run.sh` 로 백엔드를 띄운 뒤 `cargo tauri dev`.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // 배포 시 번들된 백엔드를 사이드카로 띄운다. 네이티브 창이 UI 를 띄우므로
            // 백엔드의 브라우저 자동 열기는 끈다(LADDER_NO_BROWSER=1).
            // 개발(dev)에서는 사이드카가 없을 수 있으니 실패해도 무시한다.
            #[cfg(not(debug_assertions))]
            {
                use tauri_plugin_shell::ShellExt;
                if let Ok(cmd) = app.shell().sidecar("plc-backend") {
                    let _ = cmd.env("LADDER_NO_BROWSER", "1").spawn();
                }
            }
            let _ = app;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("Tauri 앱 실행 실패");
}
