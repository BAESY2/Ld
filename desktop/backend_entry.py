"""자가포함 데스크톱 백엔드 진입점.

uvicorn 으로 ``app.server`` 를 띄우고 기본 브라우저로 스튜디오를 연다 — 즉,
파이썬·인터넷 없이도 더블클릭으로 도는 단일 실행파일(오프라인 공장용)의 진입점.
PyInstaller onefile 로 번들한다(``desktop/plc-backend.spec``).

정적 프론트(``frontend/``)와 RAG 코퍼스(``data/``)는 onefile 에 함께 들어가며,
``app.server``/``app.rag`` 의 ``Path(__file__).parent.parent`` 해석이 PyInstaller
추출 루트(_MEIPASS)를 가리키므로 별도 경로 설정 없이 동작한다.

Tauri 네이티브 셸에서 사이드카로 띄울 때는 환경변수 ``LADDER_NO_BROWSER=1`` 로
브라우저 자동 열기를 끈다(네이티브 창이 대신 띄움).
"""

from __future__ import annotations

import os
import threading
import time
import urllib.request
import webbrowser

HOST = os.environ.get("LADDER_HOST", "127.0.0.1")
PORT = int(os.environ.get("LADDER_PORT", "8000"))
_STUDIO_URL = f"http://{HOST}:{PORT}/studio.html"
_HEALTH_URL = f"http://{HOST}:{PORT}/healthz"


def _open_browser_when_ready() -> None:
    """서버가 /healthz 로 살아나면 브라우저로 스튜디오를 연다(최대 ~10초 대기)."""
    if os.environ.get("LADDER_NO_BROWSER"):
        return
    for _ in range(100):
        try:
            with urllib.request.urlopen(_HEALTH_URL, timeout=0.5) as resp:
                if resp.status == 200:
                    break
        except Exception:  # noqa: BLE001 - 기동 전 연결거부는 정상
            time.sleep(0.1)
    webbrowser.open(_STUDIO_URL)


def main() -> None:
    import uvicorn

    from app.server import app

    threading.Thread(target=_open_browser_when_ready, daemon=True).start()
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
