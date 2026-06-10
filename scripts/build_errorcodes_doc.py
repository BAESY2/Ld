#!/usr/bin/env python3
"""에러코드 지식베이스 → docs/ERRORCODES.md 자료화 (브랜드→목차(분류)→상세).

DB(error_codes + error_kb)가 단일 원천 — 이 스크립트가 문서를 결정론 생성하므로
문서와 코드가 어긋날 수 없다(테스트가 재생성 일치를 강제).
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.error_codes import DB, ErrorCode, Vendor  # noqa: E402

_VENDOR_KO = {
    Vendor.LS_ELECTRIC: "LS ELECTRIC (XGT/XGK/XGB)",
    Vendor.MITSUBISHI: "MITSUBISHI (MELSEC FX/Q)",
    Vendor.SIEMENS: "SIEMENS (S7-300/400/1200/1500)",
    Vendor.OMRON: "OMRON (CJ/CP)",
    Vendor.GENERIC: "공통(브랜드 무관) 진단 수칙",
}
_CAT_KO = {
    "SYSTEM": "CPU/시스템", "POWER": "전원/배터리", "IO": "I/O·모듈",
    "COMM": "통신", "PROGRAM": "프로그램/연산", "WATCHDOG": "워치독/스캔",
    "WARNING": "경고", "": "기타",
}
_SEV_BADGE = {"FATAL": "🔴 정지급", "WARNING": "🟡 경고", "INFO": "🔵 절차/지식", "": "—"}


def _anchor(s: str) -> str:
    return s.lower().replace(" ", "-").replace("(", "").replace(")", "").replace("/", "")


def _entry_md(e: ErrorCode) -> str:
    lines = [f"#### `{e.code}` — {e.title}", ""]
    meta = f"**심각도**: {_SEV_BADGE.get(e.severity, e.severity)}"
    if e.series:
        meta += f" · **시리즈**: {e.series}"
    lines.append(meta)
    lines.append("")
    if e.likely_cause:
        lines.append(f"- **원인**: {e.likely_cause}")
    if e.suggested_action:
        lines.append(f"- **조치(실무)**: {e.suggested_action}")
    if e.source_url:
        doc = e.source_doc or e.source_url
        lines.append(f"- **근거/출처**: [{doc}]({e.source_url})")
    if e.keywords:
        lines.append(f"- **키워드**: {', '.join(e.keywords)}")
    lines.append("")
    return "\n".join(lines)


def build() -> str:
    entries = DB.search("")
    by_vendor: dict[Vendor, dict[str, list[ErrorCode]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for e in entries:
        by_vendor[e.vendor][e.category].append(e)

    out: list[str] = [
        "# PLC 에러코드 해결 자료집 — 제조사별·목차별",
        "",
        "> 코드값/현상은 사실 데이터로 구조화하고, 원인·조치는 공식 문서와 실무자",
        "> 공개 글을 연구해 **자체 작성**했다(매뉴얼 본문 복제 없음). 항목마다 근거",
        "> 출처를 남긴다. 숫자 코드가 시리즈별로 달라 단정 불가한 항목은 LED/플래그",
        "> 기호로 표기한다 — 틀린 숫자를 지어내지 않는 것이 원칙.",
        "",
        f"총 {len(entries)}건 · 자동 생성: `python scripts/build_errorcodes_doc.py`",
        "(원천: `app/error_codes.py` + `app/error_kb.py` — 문서/코드 불일치 불가)",
        "",
        "## 목차",
        "",
    ]
    vendor_order = [Vendor.LS_ELECTRIC, Vendor.MITSUBISHI, Vendor.SIEMENS,
                    Vendor.OMRON, Vendor.GENERIC]
    for v in vendor_order:
        if v not in by_vendor:
            continue
        out.append(f"- [{_VENDOR_KO[v]}](#{_anchor(_VENDOR_KO[v])})")
        for cat in sorted(by_vendor[v]):
            n = len(by_vendor[v][cat])
            out.append(f"  - {_CAT_KO.get(cat, cat)} ({n})")
    out.append("")

    for v in vendor_order:
        if v not in by_vendor:
            continue
        out.append(f"## {_VENDOR_KO[v]}")
        out.append("")
        for cat in sorted(by_vendor[v]):
            out.append(f"### {_CAT_KO.get(cat, cat)}")
            out.append("")
            sev_rank = {"FATAL": 0, "WARNING": 1, "INFO": 2, "": 3}
            for e in sorted(by_vendor[v][cat],
                            key=lambda x: (sev_rank.get(x.severity, 3), x.code)):
                out.append(_entry_md(e))
    return "\n".join(out) + "\n"


def main() -> int:
    doc = build()
    out = Path(__file__).resolve().parent.parent / "docs" / "ERRORCODES.md"
    out.write_text(doc, encoding="utf-8")
    print(f"wrote {out} ({len(doc)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
