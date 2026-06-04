"""CLI: 자연어/ST 에서 래더 프로젝트 파일 생성 (`python -m app.gen` / `plc-gen`)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.generate import GenEvent, generate_project
from app.vendors.profiles import DEFAULT_PROFILE, available_profiles

_MARK = {"start": "▶", "ok": "✓", "error": "✗", "skip": "·"}


def _print_event(ev: GenEvent) -> None:
    line = f"{_MARK.get(ev.status, ' ')} {ev.stage}"
    if ev.file:
        line += f"  {ev.file}"
    if ev.detail.get("vendor"):
        line += f"  [{ev.detail['vendor']}]"
    if ev.message:
        line += f"  — {ev.message}"
    print(line, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m app.gen",
        description="명세/ST/자연어에서 래더 프로젝트 파일 일괄 생성",
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--st", help="ST 코드 문자열 (결정론, 키 불필요)")
    src.add_argument("--request", help="자연어 요구 (LLM 사용)")
    src.add_argument("--file", help="입력 파일 (.st → ST, 그 외 → 자연어)")
    p.add_argument("--out", default="out", help="출력 루트 (기본: out)")
    p.add_argument("--name", help="프로젝트 슬러그")
    p.add_argument("--title", default="", help="프로그램 타이틀")
    p.add_argument(
        "--vendors",
        default=DEFAULT_PROFILE.name,
        help=f"콤마구분 벤더. 가능: {', '.join(available_profiles())}",
    )
    p.add_argument("--no-llm", action="store_true", help="LLM 금지(자연어 입력이면 에러)")
    p.add_argument("--force", action="store_true", help="기존 디렉터리 덮어쓰기")
    p.add_argument("-q", "--quiet", action="store_true", help="진행 이벤트 숨김")
    args = p.parse_args(argv)

    if args.st is not None:
        source, from_nl = args.st, False
    elif args.request is not None:
        source, from_nl = args.request, True
    else:
        path = Path(args.file)
        source = path.read_text(encoding="utf-8")
        from_nl = path.suffix.lower() != ".st"

    if from_nl and args.no_llm:
        p.error("--no-llm 인데 자연어 입력입니다. --st 또는 .st 파일을 쓰세요.")

    vendors = [v.strip() for v in args.vendors.split(",") if v.strip()]
    on_progress = None if args.quiet else _print_event
    try:
        manifest = generate_project(
            source, out_dir=args.out, from_nl=from_nl, vendors=vendors,
            name=args.name, title=args.title, force=args.force,
            allow_llm=not args.no_llm, on_progress=on_progress,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"생성 실패: {exc}", file=sys.stderr)
        return 1
    print(
        f"{args.out}/{manifest.project}  ({len(manifest.files)} files, "
        f"verify={'OK' if manifest.verification_passed else 'FAIL'})"
    )
    return 0 if manifest.verification_passed and not manifest.error else 2


if __name__ == "__main__":
    raise SystemExit(main())
