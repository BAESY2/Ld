#!/usr/bin/env python3
"""실 OpenPLC 런타임 대 우리 결정론 시뮬레이터의 *외부* 차분 검증 러너.

이 스크립트는 "외부검증 완료" 증빙을 *재현 가능하게* 만든다:
  1) 우리 레시피(wizard) → 명세 → ``synthesize_st`` 로 ST 바디를 합성하고,
  2) 그것을 OpenPLC v3 가 컴파일·구동할 수 있는 *완전한* ST 프로그램으로 감싸
     (입력은 ``%QX`` 코일로 강제 가능하게, 출력과 겹치지 않는 코일 주소에 배치),
  3) OpenPLC v3 Flask 웹폼(:8080)으로 업로드→컴파일→실행하고,
  4) 우리 ``ModbusPlcLink`` 로 입력 코일을 강제하고 출력 코일을 읽어
  5) ``app.twin.openplc_adapter.run_differential`` 로 simulate() 트레이스와
     비트 단위 대조한 뒤 PASS/FAIL 을 출력한다.

환경변수(전부 선택, 기본값은 로컬 도커 매핑):
  OPENPLC_HOST   OpenPLC 호스트          (기본 127.0.0.1)
  OPENPLC_PORT   Modbus/TCP 포트         (기본 502)
  OPENPLC_WEB    Flask 웹 UI 베이스 URL  (기본 http://{HOST}:8080)
  OPENPLC_USER   웹 로그인 사용자        (기본 openplc)
  OPENPLC_PASS   웹 로그인 비밀번호      (기본 openplc)
  OPENPLC_UNIT   Modbus unit id          (기본 1)
  OPENPLC_RECIPE 검증할 wizard 레시피 id (기본 motor_start_stop)
  OPENPLC_NL     자연어 한 줄(설정 시 레시피 대신 frame_to_spec 컴파일러 산출물 검증)
  OPENPLC_SKIP_LOAD  '1' 이면 업로드/컴파일/실행을 건너뛰고 기존 실행을 그대로 검증

핵심 발견(주소맵 주의 — docs/OPENPLC_LIVE.md 참조):
  * OpenPLC 슬레이브에서 ``%IX`` (디스크리트 입력)는 **읽기 전용**이라 Modbus
    마스터가 강제할 수 없다. 그래서 우리 입력 심볼을 ``%QX`` 코일로 선언해
    FC05/0F 로 강제한다. 출력 코일과 겹치지 않도록 입력은 출력 *다음* 바이트부터
    배치한다(코일번호 = b*8 + c, 단일 선형 코일 테이블).

재현 명령(로컬 도커 예):
  # 레시피 경로
  OPENPLC_HOST=127.0.0.1 OPENPLC_PORT=5502 python scripts/openplc_live_diff.py
  # 자연어 경로(헤드라인 — 한국어 한 줄이 실 IEC 런타임에서 비트 일치)
  OPENPLC_HOST=127.0.0.1 OPENPLC_PORT=5502 \
    OPENPLC_NL='저수위 되면 펌프 켜고 고수위 되면 펌프 끄고 비상정지 누르면 다 꺼' \
    python scripts/openplc_live_diff.py
"""

from __future__ import annotations

import os
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.cookiejar import CookieJar

from app.comms.modbus_tcp import AddressMap, ModbusPlcLink
from app.models import IODirection, StateMachineSpec
from app.synth import synthesize_st
from app.twin.openplc_adapter import InputsTimeline, SettleHook, run_differential
from app.wizard import build_spec

# ── ST 래핑 ────────────────────────────────────────────────────────────────

_ST_TEMPLATE = """\
PROGRAM prog0
{var_blocks}

{body}
END_PROGRAM


CONFIGURATION Config0

  RESOURCE Res0 ON PLC
    TASK Main(INTERVAL := T#{interval_ms}ms,PRIORITY := 0);
    PROGRAM Inst0 WITH Main : prog0;
  END_RESOURCE
END_CONFIGURATION
"""


@dataclass(frozen=True)
class CoilMap:
    """심볼 → OpenPLC 코일번호(=b*8+c) 매핑. 입력/출력 모두 코일(%QX)."""

    inputs: dict[str, int]
    outputs: dict[str, int]


# IEC 61131-3 예약어 일부(located 변수명으로 쓰면 MatIEC 파싱 실패).
_IEC_RESERVED = {
    "OUTPUT", "INPUT", "VAR", "END_VAR", "PROGRAM", "FUNCTION", "TYPE",
    "TRUE", "FALSE", "AND", "OR", "NOT", "XOR", "IF", "THEN", "ELSE",
    "FOR", "WHILE", "RETAIN", "AT", "BOOL", "INT", "TIME",
}


def _check_reserved(spec: StateMachineSpec) -> None:
    """심볼이 IEC 예약어와 충돌하면 친절한 메시지로 거부(MatIEC 파싱 실패 예방)."""
    inputs, outputs = _spec_io(spec)
    bad = sorted(
        {s for s in (*inputs, *outputs) if s.upper() in _IEC_RESERVED}
    )
    if bad:
        raise ValueError(
            f"심볼 {bad} 이(가) IEC 61131-3 예약어와 충돌해 OpenPLC 가 컴파일하지 "
            "못합니다. 레시피 답변으로 다른 이름을 주세요(예: on_delay 의 OUTPUT → LAMP)."
        )


def _spec_io(spec: StateMachineSpec) -> tuple[list[str], list[str]]:
    """명세에서 입력·출력 심볼을 선언 순서대로(중복 제거) 뽑는다."""
    seen_in: dict[str, None] = {}
    seen_out: dict[str, None] = {}
    for io in spec.io_points:
        if io.direction == IODirection.INPUT:
            seen_in.setdefault(io.symbol, None)
        elif io.direction == IODirection.OUTPUT:
            seen_out.setdefault(io.symbol, None)
    return list(seen_in), list(seen_out)


def build_coil_map(spec: StateMachineSpec) -> CoilMap:
    """출력은 코일 0..부터, 입력은 출력 다음 *바이트 경계*부터 코일에 배치.

    OpenPLC 코일 테이블은 단일 선형(코일번호 = b*8 + c). 입력을 출력과 겹치지
    않게 다음 바이트(b 경계)에 두어 충돌(이중 의미)을 원천 차단한다.
    """
    inputs, outputs = _spec_io(spec)
    out_map = {sym: i for i, sym in enumerate(outputs)}
    # 입력은 출력이 차지한 바이트 다음 바이트부터 시작(가독성·충돌방지).
    next_byte = ((len(outputs) + 7) // 8) if outputs else 0
    in_start = max(next_byte * 8, len(outputs))
    in_map = {sym: in_start + i for i, sym in enumerate(inputs)}
    return CoilMap(inputs=in_map, outputs=out_map)


def _coil_to_qx(coil: int) -> str:
    """코일번호 → ``%QXb.c`` (b = coil//8, c = coil%8)."""
    return f"%QX{coil // 8}.{coil % 8}"


def _ascii_body(body: str) -> str:
    """합성 ST 바디에서 ``//`` 줄 주석을 제거한다.

    우리 합성기는 한국어 주석(예: ``// 타이머 T1 ...``)을 넣는데, MatIEC(iec2c)
    렉서는 ASCII C 렉서라 주석 안의 UTF-8 멀티바이트에서 파싱이 깨진다
    (래더 의미와 무관한 주석이므로 안전하게 떼어낸다). 따옴표 안 문자열 리터럴은
    우리 ST 에 등장하지 않으므로 단순 분리로 충분하다.
    """
    out: list[str] = []
    for line in body.splitlines():
        code = line.split("//", 1)[0].rstrip()
        if code:
            out.append(_iec_fb_params(code))
    return "\n".join(out)


# 우리 합성기의 CTU 호출은 비표준 파라미터명 ``RESET`` 을 쓴다(우리 simulate() 와는
# 합치하지만 표준 IEC/MatIEC 의 CTU 인자는 ``R`` 이라 OpenPLC 컴파일이 거부한다).
# 이 차이는 *우리 synth 의 이식성 버그*다(docs/OPENPLC_LIVE.md 의 발견 §참조).
# 리드에게 보고하되(app/ 무수정 규칙), OpenPLC 로 보내는 ST 사본에서만 표준명으로
# 번역해 카운터 *로직*의 일치를 그대로 검증할 수 있게 한다.
_FB_PARAM_RE = re.compile(r"\bRESET\s*:=")


def _iec_fb_params(line: str) -> str:
    """OpenPLC(MatIEC) 호환을 위해 비표준 FB 파라미터명을 표준명으로 번역."""
    return _FB_PARAM_RE.sub("R :=", line)


def wrap_st_for_openplc(
    spec: StateMachineSpec, body: str, coils: CoilMap, *, interval_ms: int = 50
) -> str:
    """합성 ST 바디를 OpenPLC v3 가 컴파일 가능한 완전한 ST 프로그램으로 감싼다.

    입력/출력 심볼을 ``AT %QXb.c`` 로케이티드 코일로 선언한다(Modbus 강제 가능).
    선언 순서는 코일번호 오름차순으로 맞춰 사람이 매핑을 검증하기 쉽게 한다.
    """
    decls: list[tuple[int, str]] = []
    for sym, coil in coils.outputs.items():
        decls.append((coil, f"    {sym} AT {_coil_to_qx(coil)} : BOOL;"))
    for sym, coil in coils.inputs.items():
        decls.append((coil, f"    {sym} AT {_coil_to_qx(coil)} : BOOL;"))
    decls.sort(key=lambda p: p[0])
    located = "\n".join(d for _, d in decls)
    # MatIEC(iec2c)는 로케이티드(AT %QX) 변수와 FB 인스턴스를 같은 VAR 블록에
    # 섞으면 파싱에 실패한다("invalid located variable declaration"). 그래서
    # 로케이티드 I/O 와 타이머/카운터 FB 인스턴스를 *별도의* VAR 블록으로 나눈다.
    blocks = [f"  VAR\n{located}\n  END_VAR"]
    fb_lines = [f"    {t.name} : {t.timer_type};" for t in spec.timers]
    fb_lines += [f"    {c.name} : {c.counter_type};" for c in spec.counters]
    if fb_lines:
        blocks.append("  VAR\n" + "\n".join(fb_lines) + "\n  END_VAR")
    var_blocks = "\n".join(blocks)
    indented_body = "\n".join(
        "  " + ln if ln.strip() else ln for ln in _ascii_body(body).splitlines()
    )
    return _ST_TEMPLATE.format(
        var_blocks=var_blocks, body=indented_body, interval_ms=interval_ms
    )


# ── OpenPLC v3 웹 적재 (Flask :8080) ────────────────────────────────────────


class OpenPlcWeb:
    """OpenPLC v3 Flask 웹 UI 클라이언트(업로드→컴파일→실행). stdlib 전용."""

    def __init__(self, base_url: str, user: str, password: str) -> None:
        self._base = base_url.rstrip("/")
        self._user = user
        self._pass = password
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar())
        )

    def _get(self, path: str) -> str:
        with self._opener.open(self._base + path, timeout=15) as resp:
            text: str = resp.read().decode("utf-8", "replace")
        return text

    def login(self) -> None:
        data = urllib.parse.urlencode(
            {"username": self._user, "password": self._pass}
        ).encode()
        req = urllib.request.Request(self._base + "/login", data=data)
        with self._opener.open(req, timeout=15) as resp:
            resp.read()

    def upload_compile_run(self, st_text: str, name: str) -> str:
        """ST 를 업로드→컴파일→실행. 컴파일 로그 문자열을 반환(성공 검증용)."""
        filename = self._upload_file(st_text)
        self._register(filename, name)
        self._get(f"/compile-program?file={filename}")
        log = self._await_compile()
        if "Compilation finished successfully!" not in log:
            raise RuntimeError(f"OpenPLC 컴파일 실패:\n{log}")
        self._get("/start_plc")
        return log

    def _upload_file(self, st_text: str) -> str:
        boundary = "----openplclivediff"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="prog.st"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
            f"{st_text}\r\n--{boundary}--\r\n"
        ).encode()
        req = urllib.request.Request(
            self._base + "/upload-program",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with self._opener.open(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", "replace")
        m = re.search(r"(\d+\.st)", html)
        if not m:
            raise RuntimeError("업로드 응답에서 생성된 .st 파일명을 찾지 못했습니다.")
        return m.group(1)

    def _register(self, filename: str, name: str) -> None:
        data = urllib.parse.urlencode(
            {
                "prog_name": name,
                "prog_descr": "openplc_live_diff",
                "prog_file": filename,
                "epoch_time": str(int(time.time())),
            }
        ).encode()
        req = urllib.request.Request(
            self._base + "/upload-program-action", data=data
        )
        with self._opener.open(req, timeout=15) as resp:
            resp.read()

    def _await_compile(self, attempts: int = 30, delay: float = 1.0) -> str:
        log = ""
        for _ in range(attempts):
            log = self._get("/compilation-logs")
            if (
                "Compilation finished successfully!" in log
                or "Compilation finished with errors!" in log
                or "Error" in log
            ):
                return log
            time.sleep(delay)
        return log


# ── 차분 검증 ────────────────────────────────────────────────────────────────


def _has_timing(spec: StateMachineSpec) -> bool:
    """타이머/카운터가 있으면 스캔-타이밍(벽시계) 검증이 필요하다."""
    return bool(spec.timers) or bool(spec.counters)


def default_timeline(spec: StateMachineSpec) -> tuple[InputsTimeline, int, int]:
    """레시피별 의미있는 입력 타임라인(+ duration_ms, step_ms)을 만든다.

    조합/래치 레시피: 모든 입력을 100ms 간격으로 순차 펄스(누름→떼기).
    타이머/카운터 레시피: 첫 입력(보통 START/기동)을 *최장 프리셋을 넘기도록*
    길게 유지해 타이머가 실제로 만료되게 한다. 이때 step_ms 를 키워(250ms)
    표본당 실시간을 늘리고, settle 훅이 그만큼 벽시계를 진행시켜 OpenPLC 의
    TON(벽시계)과 우리 simulate()(논리시각)를 lockstep 으로 맞춘다.
    """
    inputs, _ = _spec_io(spec)
    if not _has_timing(spec):
        timeline: InputsTimeline = [(0, {s: False for s in inputs})]
        t = 100
        for sym in inputs:
            timeline.append((t, {sym: True}))
            t += 100
            timeline.append((t, {sym: False}))
            t += 100
        return timeline, t + 200, 100

    # 스캔-타이밍 검증의 핵심(발견): 우리 simulate() 는 TON 누산을 step_ms 로
    # *양자화*하고, 실 OpenPLC 는 독립 벽시계(50ms task)로 TON 을 돌린다. step 이
    # 스캔주기보다 크면 타이머 만료가 표본 사이에 떨어져 *전이 표본 1개*가 어긋난다
    # (논리 오차 아님, 표본화 양자화). step 을 OpenPLC 스캔주기(50ms)에 맞추면
    # 만료가 같은 표본에 떨어져 비트 단위로 일치한다. 따라서 타이밍 경로는 50ms.
    step = 50
    timeline2: InputsTimeline = [(0, {s: False for s in inputs})]

    if spec.counters:
        # 카운터 경로: count 입력(상승에지)을 PV+1 번 펄스해 만료를 넘긴다.
        # 펄스 폭은 여러 스캔(>= 4*step)으로 잡아 에지를 확실히 잡게 한다.
        c = spec.counters[0]
        count_sym = c.count_condition.strip()
        pw = 4 * step
        t = pw
        for _ in range(c.preset + 1):
            timeline2.append((t, {count_sym: True}))
            t += pw
            timeline2.append((t, {count_sym: False}))
            t += pw
        duration = t + 4 * pw
        return timeline2, duration, step

    # 타이머 경로: 최장 프리셋을 넘기도록 첫 입력(보통 START/기동)을 길게 유지.
    max_preset = max((t.preset_ms for t in spec.timers), default=0)
    start_sym = inputs[0] if inputs else None
    stop_sym = inputs[-1] if len(inputs) > 1 else None
    hold_until = max_preset + 1000  # 만료 후에도 출력 유지 확인
    if start_sym is not None:
        timeline2.append((4 * step, {start_sym: True}))
    if stop_sym is not None and stop_sym != start_sym:
        timeline2.append((hold_until, {stop_sym: True}))
        timeline2.append((hold_until + 4 * step, {stop_sym: False}))
    duration = hold_until + 8 * step
    return timeline2, duration, step


def make_settle_hook(step_ms: int, *, realtime: bool) -> SettleHook:
    """스캔 안정화 훅.

    realtime=False(조합/래치): 한 스캔(50ms task) 이상 돌도록 짧게 대기.
    realtime=True(타이머/카운터): OpenPLC 벽시계 TON 을 우리 논리시각과 lockstep
    으로 맞춘다. **절대 스케줄**(t0 + n*step)에 표본 n 을 정렬해, 한 표본의 통신
    지연이 step 을 넘겨도 다음 표본에서 자기보정되게 한다(증분 누적 드리프트 방지).
    이 절대 정렬이 체인 타이머 시퀀서를 호스트 부하 지터에 강건하게 만든다.
    """
    if not realtime:
        def settle_fixed() -> None:
            time.sleep(0.12)
        return settle_fixed

    target = step_ms / 1000.0
    # 첫 호출에서 t0 를 잡고, 이후 n 번째 호출은 t0 + n*step 까지 잔다.
    state: dict[str, float] = {}

    def settle_rt() -> None:
        if "t0" not in state:
            state["t0"] = time.monotonic()
            state["n"] = 0.0
        state["n"] += 1.0
        deadline = state["t0"] + state["n"] * target
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)

    return settle_rt


def run(recipe: str) -> int:
    host = os.environ.get("OPENPLC_HOST", "127.0.0.1")
    port = int(os.environ.get("OPENPLC_PORT", "502"))
    web_base = os.environ.get("OPENPLC_WEB", f"http://{host}:8080")
    user = os.environ.get("OPENPLC_USER", "openplc")
    password = os.environ.get("OPENPLC_PASS", "openplc")
    unit = int(os.environ.get("OPENPLC_UNIT", "1"))
    skip_load = os.environ.get("OPENPLC_SKIP_LOAD") == "1"

    # OPENPLC_ANSWERS="output=LAMP,delay_sec=2" 로 레시피 기본 답변 덮어쓰기.
    answers: dict[str, str] = {}
    raw_answers = os.environ.get("OPENPLC_ANSWERS", "").strip()
    if raw_answers:
        for pair in raw_answers.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                answers[k.strip()] = v.strip()

    # 자연어 경로(OPENPLC_NL) — 레시피 대신 *컴파일러* 산출물을 실 PLC 에 올려 대조한다.
    # 제조사 재현용 헤드라인 경로: 한국어 한 줄 → frame_to_spec → 실 IEC 런타임 비트 일치.
    nl = os.environ.get("OPENPLC_NL", "").strip()
    label = recipe
    if nl:
        from app.compile_frame import frame_to_spec
        result = frame_to_spec(nl)
        if not result.confident:
            print(f"자연어 컴파일 보류(confident=False): {result.unresolved}")
            return 2
        spec = result.spec
        label = "nl"
    else:
        spec = build_spec(recipe, answers)
    _check_reserved(spec)
    body = synthesize_st(spec)
    coils = build_coil_map(spec)
    st_text = wrap_st_for_openplc(spec, body, coils)

    print("=" * 68)
    print(f"OpenPLC LIVE 차분 검증 — {'자연어' if nl else 'recipe'}={nl or recipe}")
    print(f"  host={host} modbus_port={port} web={web_base} unit={unit}")
    print("-" * 68)
    print("심볼 → 코일 매핑(%QX):")
    for sym, c in sorted(coils.outputs.items(), key=lambda p: p[1]):
        print(f"  OUTPUT {sym:14} = coil {c:3}  ({_coil_to_qx(c)})")
    for sym, c in sorted(coils.inputs.items(), key=lambda p: p[1]):
        print(f"  INPUT  {sym:14} = coil {c:3}  ({_coil_to_qx(c)})  [강제]")
    print("-" * 68)

    if not skip_load:
        web = OpenPlcWeb(web_base, user, password)
        web.login()
        print("업로드→컴파일→실행 중...")
        web.upload_compile_run(st_text, f"livediff_{label}")
        print("OpenPLC 컴파일 성공 + 실행 시작.")
        time.sleep(1.0)  # 런타임 부팅·Modbus 서버 기동 여유
    else:
        print("OPENPLC_SKIP_LOAD=1 — 적재 생략, 기존 실행을 검증.")

    amap = AddressMap(
        inputs=dict(coils.inputs), outputs=dict(coils.outputs), output_kind="coil"
    )
    link = ModbusPlcLink(host, port, address_map=amap, unit_id=unit)
    try:
        # 시작 상태 정렬: 모든 입력 코일 OFF.
        link.write_inputs({s: False for s in coils.inputs})
        time.sleep(0.2)
        timeline, duration, step = default_timeline(spec)
        realtime = _has_timing(spec)
        if realtime:
            print(
                f"타이머/카운터 감지 → 실시간 lockstep 검증(step={step}ms, "
                f"duration={duration}ms). 약 {duration / 1000:.1f}초 소요."
            )
        report = run_differential(
            body,
            spec,
            link,
            timeline,
            duration_ms=duration,
            step_ms=step,
            settle_hook=make_settle_hook(step, realtime=realtime),
        )
    finally:
        link.close()

    print(report.summary)
    print(f"비교 출력: {', '.join(report.outputs)}")
    print(f"표본 수: {report.n_samples}")
    if report.mismatches:
        print("불일치(최대 20건):")
        for m in report.mismatches[:20]:
            print(f"  t={m.t_ms}ms {m.symbol}: sim={m.sim_val} plc={m.plc_val}")
    print("=" * 68)
    if report.agreement:
        print("RESULT: PASS — 실 OpenPLC 와 우리 시뮬레이터가 비트 단위로 일치합니다.")
        return 0
    print("RESULT: FAIL — 실 OpenPLC 와 시뮬레이터가 갈라졌습니다(위 불일치 참조).")
    return 1


def main(argv: list[str]) -> int:
    recipe = os.environ.get("OPENPLC_RECIPE", "motor_start_stop")
    if len(argv) > 1:
        recipe = argv[1]
    return run(recipe)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
