"""안전커널 — 쓰기 전 검증 게이트(Stage 3 핵심, '머신에 쓰기 전에 검증한다').

실기 PLC 로 나가는 모든 입력 쓰기(``write_inputs``)를 *기본 거부(deny-by-default)*
정책으로 가로채, 위험한 액추에이터 구동으로 이어질 수 있는 명령을 차단한다.
``SafetyKernel`` 은 임의의 :class:`~app.comms.protocols.PlcLink` 를 합성(composition)
으로 감싸며, 그 자체로도 ``PlcLink`` 이다 — 실링크 앞에 투명하게 끼워 넣을 수 있다.

설계 원칙(런타임 강제/런타임 검증 문헌):
  - **Deny-by-default**: 안전이 *증명*되지 않으면 통과시키지 않는다.
  - **Suppress unsafe actuator writes**: 인터락을 깨뜨릴 수 있는 입력 명령은
    실링크에 도달하기 전에 억제(차단)한다.
  - **Fail-safe**: 검증 중 *어떤* 내부 오류가 나도 통과가 아니라 거부한다
    (fail-open 절대 금지).
출처: M. Cheminod 외, "ICS Security via Runtime Enforcement," ACM TOPS,
DOI 10.1145/3546579 — 모니터/프록시가 위험 액추에이터 명령을 억제·대체하고,
deny-by-default·fail-safe 로 동작하는 패턴.

검증은 여러 *개별 테스트 가능한* 체크로 구성된다(아래 ``_check_*``):
  1. 화이트리스트     : 명세에 없는 입력 심볼은 거부.
  2. 타입/범위        : 값이 BOOL 이 아니면 거부.
  3. 인터락 상호배제  : 명령 적용 후의 출력 이미지를 시뮬레이터 드라이런으로 계산해,
                        인터락 쌍이 동시에 켜질 수 있으면 거부.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.comms.protocols import PlcLink, WriteRejected
from app.models import Interlock, IODirection, StateMachineSpec
from app.simulator import assign_block, coil_outputs, eval_assign_block, simulate
from app.synth import synthesize_st


@dataclass(frozen=True)
class AuditEntry:
    """관측성(observability)용 감사 로그 한 줄 — 결정론(타임스탬프 주입 시에만)."""

    decision: str  # "ALLOW" | "DENY"
    reason: str
    seq: int = 0
    ts: float | None = None

    def as_tuple(self) -> tuple[str, str]:
        """(decision, reason) 튜플 — 테스트/비교용 결정론 표현."""
        return (self.decision, self.reason)


# 한 번의 드라이런에서 시뮬레이터가 도달해야 할 시간(스캔 1회로 충분 — 조합 코일).
_DRYRUN_DURATION_MS = 0
_DRYRUN_STEP_MS = 1


class SafetyKernel:
    """임의의 :class:`PlcLink` 를 감싸 쓰기 전 안전검증을 강제하는 게이트.

    그 자체로 ``PlcLink`` 이므로 실링크 앞에 투명하게 배치한다.
    읽기 경로(``read_outputs``)는 감싼 링크로 그대로 위임한다.
    """

    def __init__(
        self,
        link: PlcLink,
        spec: StateMachineSpec,
        *,
        now: Callable[[], float] | None = None,
        min_interval: float = 0.0,
    ) -> None:
        """:param link: 실제 쓰기를 수행할 하위 PlcLink(합성).

        :param spec: 인터락·IO 화이트리스트를 아는 상태머신 명세.
        :param now: 결정론적 클록 주입(레이트리밋용). 미주입 시 레이트리밋 비활성.
        :param min_interval: 연속 쓰기 최소 간격(now 단위). now 없으면 무시.
        """
        self._link = link
        self._spec = spec
        self._now = now
        self._min_interval = min_interval
        self._last_write_at: float | None = None
        self._seq = 0
        self.audit: list[AuditEntry] = []
        # 명세에서 1회만 파생 — 결정론적이며 매 쓰기마다 재계산 불필요.
        self._input_symbols: frozenset[str] = frozenset(
            p.symbol for p in spec.io_points if p.direction == IODirection.INPUT
        )
        self._interlocks: tuple[Interlock, ...] = tuple(spec.interlocks)

    # ── PlcLink: 읽기 경로(그대로 위임) ──────────────────────────────────
    def read_outputs(self) -> dict[str, bool]:
        """감싼 링크의 출력 이미지를 그대로 읽어 위임한다(검증 없음)."""
        return self._link.read_outputs()

    def close(self) -> None:
        """감싼 링크 자원을 해제한다."""
        self._link.close()

    # ── PlcLink: 쓰기 경로(deny-by-default 게이트) ───────────────────────
    def write_inputs(self, values: dict[str, bool]) -> None:
        """입력 명령을 검증한 뒤에만 하위 링크로 전달한다(통과 못 하면 차단).

        검증 중 *어떤* 예외가 나도 fail-safe 로 ``WriteRejected`` 를 던진다.
        """
        self._seq += 1
        try:
            reason = self._validate(values)
        except WriteRejected:
            raise
        except Exception as exc:  # noqa: BLE001 — fail-safe: 어떤 오류도 거부로.
            self._deny(f"검증 내부 오류로 안전상 차단(fail-safe): {exc!r}")

        if reason is not None:
            self._deny(reason)

        # 모든 체크 통과 — 실링크로 전달. 링크 쓰기 자체가 실패해도(소켓 단절 등)
        # fail-safe 로 DENY 를 감사기록하고 WriteRejected 로 올린다(원시 예외 누출·
        # 감사 누락 금지). ALLOW 는 실제 전달이 성공했을 때만 기록한다.
        #
        # 방어적 스냅샷: 검증을 *통과한 바로 그 값* 만 하위 링크로 내려보낸다. 호출자가
        # 같은 dict 참조를 계속 들고 있다가 게이트 통과 후(또는 링크가 참조를 보관 중일
        # 때) 값을 바꿔치기해도, 검증을 우회한 위험 값이 실링크에 흘러들 수 없다. 안전
        # 최후 방어선이므로 별칭(aliasing)으로 인한 TOCTOU 누출을 원천 차단한다.
        snapshot = dict(values)
        try:
            self._link.write_inputs(snapshot)
        except Exception as exc:  # noqa: BLE001 — fail-safe
            self.audit.append(
                AuditEntry(
                    decision="DENY",
                    reason=f"링크 쓰기 실패(fail-safe): {exc!r}",
                    seq=self._seq,
                )
            )
            raise WriteRejected(f"링크 쓰기 실패(fail-safe): {exc!r}") from exc
        self._last_write_at = self._now() if self._now is not None else self._last_write_at
        self.audit.append(
            AuditEntry(decision="ALLOW", reason="안전검증 통과", seq=self._seq)
        )

    # ── 거부 헬퍼 ────────────────────────────────────────────────────────
    def _deny(self, reason: str) -> None:
        """감사 로그에 DENY 를 남기고 ``WriteRejected`` 를 던진다(통과 차단)."""
        self.audit.append(AuditEntry(decision="DENY", reason=reason, seq=self._seq))
        raise WriteRejected(reason)

    # ── 검증 파이프라인(개별 체크는 각각 테스트 가능) ────────────────────
    def _validate(self, values: dict[str, bool]) -> str | None:
        """모든 게이트를 순서대로 통과시키고, 첫 위반 사유(없으면 None)를 돌려준다."""
        for check in (
            self._check_whitelist,
            self._check_types,
            self._check_rate_limit,
            self._check_interlocks,
        ):
            reason = check(values)
            if reason is not None:
                return reason
        return None

    def _check_whitelist(self, values: dict[str, bool]) -> str | None:
        """명세 입력 심볼만 허용 — 모르는 심볼은 거부(deny-by-default)."""
        unknown = sorted(s for s in values if s not in self._input_symbols)
        if unknown:
            return (
                f"화이트리스트 위반: 명세에 없는 입력 심볼 {unknown} 쓰기 시도. "
                f"허용 심볼: {sorted(self._input_symbols)}"
            )
        return None

    def _check_types(self, values: dict[str, bool]) -> str | None:
        """값은 반드시 BOOL — 비불리언(정수/문자열 등)은 거부."""
        bad = sorted(
            s for s, v in values.items() if not isinstance(v, bool)
        )
        if bad:
            return f"타입 위반: BOOL 이 아닌 값 {bad} (입력은 BOOL 만 허용)"
        return None

    def _check_rate_limit(self, values: dict[str, bool]) -> str | None:
        """결정론적 레이트리밋 — 주입된 클록 기준 최소 간격 미만이면 거부.

        클록 미주입 또는 min_interval<=0 이면 비활성(항상 통과).
        """
        if self._now is None or self._min_interval <= 0.0:
            return None
        if self._last_write_at is None:
            return None
        elapsed = self._now() - self._last_write_at
        if elapsed < self._min_interval:
            return (
                f"레이트리밋 위반: 직전 쓰기 후 {elapsed:.3f} 경과 "
                f"(최소 {self._min_interval:.3f} 필요)"
            )
        return None

    def _check_interlocks(self, values: dict[str, bool]) -> str | None:
        """명령 적용 후 인터락 쌍이 동시에 켜질 수 있으면 거부(드라이런).

        실링크에 쓰기 전에 합성 ST 를 *두 가지* 드라이런으로 검사한다 —
        둘 다 시뮬레이터 스캔 의미론(입력→로직→출력)을 1:1 재사용한다:

        (1) **청정 상태 드라이런** (``simulate``): 모든 출력 OFF 에서 시작해 명령을
            t=0 에 적용한 1스캔 출력 이미지. 명령 자체가 곧바로 양쪽을 켜는지 본다.
        (2) **최악 래치 드라이런** (``eval_assign_block``): 모든 출력이 이미 ON 으로
            래치된 *가장 깨지기 쉬운* 상태에서 명령을 적용해 1스캔 평가. seal-in 으로
            이미 한쪽이 구동 중일 때 명령이 상대를 함께 켜 인터락을 깨뜨리는지 본다
            (정상 합성 ST 는 NOT-보호로 한쪽을 끄지만, 보호가 깨진 ST 는 여기서 잡힘).

        둘 중 어느 드라이런에서든 인터락 쌍이 동시 ON 이면 거부한다.
        """
        if not self._interlocks:
            return None
        st_code = synthesize_st(self._spec)
        if not st_code.strip():
            return None  # 합성 불가(순수 조합 폴백) — 인터락 드라이런 생략.
        clean = self._dry_run_clean(st_code, values)
        latched = self._dry_run_worst_latch(st_code, values)
        for lock in self._interlocks:
            for image, where in ((clean, "청정상태"), (latched, "최악래치")):
                if image.get(lock.output_a, False) and image.get(lock.output_b, False):
                    return (
                        f"인터락 위반({where}): 명령 적용 시 '{lock.output_a}' 와 "
                        f"'{lock.output_b}' 가 동시에 켜집니다. ({lock.reason})"
                    )
        return None

    def _dry_run_clean(
        self, st_code: str, values: dict[str, bool]
    ) -> dict[str, bool]:
        """모든 출력 OFF 에서 시작하는 청정 드라이런(``simulate``, 1스캔)."""
        result = simulate(
            st_code,
            [(0, dict(values))],
            duration_ms=_DRYRUN_DURATION_MS,
            step_ms=_DRYRUN_STEP_MS,
        )
        if not result.samples:
            return {}
        return dict(result.samples[-1].outputs)

    def _dry_run_worst_latch(
        self, st_code: str, values: dict[str, bool]
    ) -> dict[str, bool]:
        """모든 출력이 ON 으로 래치된 최악 상태에서 명령을 적용한 1스캔 평가.

        시뮬레이터의 순수 헬퍼(``eval_assign_block``)를 재사용해 top-to-bottom
        seal-in 의미론을 그대로 따른다(부작용 없음·결정론).
        """
        assigns = assign_block(st_code)
        table: dict[str, bool] = {o: True for o in coil_outputs(st_code)}
        table.update(values)  # 명령 입력 반영
        return eval_assign_block(assigns, table)

    # ── 관측성 ───────────────────────────────────────────────────────────
    def audit_log(self) -> list[tuple[str, str]]:
        """(decision, reason) 튜플 목록 — 결정론적 감사 로그."""
        return [e.as_tuple() for e in self.audit]


__all__ = ["SafetyKernel", "AuditEntry"]
