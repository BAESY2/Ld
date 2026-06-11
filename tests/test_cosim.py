"""코시뮬레이션 세션·WebSocket 엔드포인트 테스트 (LLM/키 불필요)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.cosim import CosimError, CosimSession, handle_message
from app.server import app

MOTOR_ST = "MOTOR := ((START AND NOT STOP) OR MOTOR) AND NOT ((STOP));"
TIMER_ST = (
    "// 타이머 T0 (TON, 100ms)\n"
    "T0(IN := RUN, PT := T#100ms);\n"
    "LAMP := T0.Q;"
)
COUNTER_ST = "C1(CU := S, R := RST, PV := 2);\nOUT := C1.Q;"


class TestCosimSession:
    def test_motor_self_hold(self) -> None:
        ses = CosimSession(MOTOR_ST, step_ms=10)
        assert ses.inputs == ["START", "STOP"]
        assert ses.outputs == ["MOTOR"]
        ses.set_inputs({"START": True})
        ses.step()
        assert ses.state()["outputs"]["MOTOR"] is True
        ses.set_inputs({"START": False})  # 자기유지
        ses.step()
        assert ses.state()["outputs"]["MOTOR"] is True
        ses.set_inputs({"STOP": True})
        ses.step()
        assert ses.state()["outputs"]["MOTOR"] is False

    def test_timer_accumulates_per_scan(self) -> None:
        ses = CosimSession(TIMER_ST, step_ms=10)
        ses.set_inputs({"RUN": True})
        ses.step(scans=5)  # 엣지 스캔 acc=0 → 이후 누적 = 40ms
        st = ses.state()
        assert st["timers"]["T0"]["acc_ms"] == 40
        assert st["outputs"]["LAMP"] is False
        ses.step(scans=7)  # 누적 100ms 도달
        st = ses.state()
        assert st["timers"]["T0"]["q"] is True
        assert st["outputs"]["LAMP"] is True
        assert st["t_ms"] == 120

    def test_counter_edge_and_reset(self) -> None:
        ses = CosimSession(COUNTER_ST, step_ms=10)
        for _ in range(2):  # 상승 엣지 2회
            ses.set_inputs({"S": True})
            ses.step()
            ses.set_inputs({"S": False})
            ses.step()
        st = ses.state()
        assert st["counters"]["C1"]["cnt"] == 2
        assert st["outputs"]["OUT"] is True
        ses.set_inputs({"RST": True})
        ses.step()
        assert ses.state()["counters"]["C1"]["cnt"] == 0

    def test_rejects_bad_init(self) -> None:
        for st_code, step in [("", 10), (MOTOR_ST, 0), (MOTOR_ST, 9999)]:
            try:
                CosimSession(st_code, step_ms=step)
            except CosimError:
                continue
            raise AssertionError(f"거부되어야 함: {st_code!r}, step={step}")

    def test_rejects_unknown_input_and_bad_scans(self) -> None:
        ses = CosimSession(MOTOR_ST)
        for bad in [{"NOPE": True}, {"START": 1}]:
            try:
                ses.set_inputs(bad)  # type: ignore[arg-type]
            except CosimError:
                continue
            raise AssertionError(f"거부되어야 함: {bad}")
        try:
            ses.step(scans=0)
        except CosimError:
            pass
        else:
            raise AssertionError("scans=0 은 거부되어야 함")


class TestHandleMessage:
    def test_full_flow(self) -> None:
        ses, ready = handle_message(None, {"type": "init", "st_code": MOTOR_ST})
        assert ready["type"] == "ready"
        assert ready["inputs"] == ["START", "STOP"]
        ses, st = handle_message(ses, {"type": "set", "inputs": {"START": True}})
        ses, st = handle_message(ses, {"type": "step", "scans": 1})
        assert st["outputs"]["MOTOR"] is True

    def test_step_before_init_is_error(self) -> None:
        _, reply = handle_message(None, {"type": "step"})
        assert reply["type"] == "error"

    def test_unknown_type_is_error(self) -> None:
        ses, _ = handle_message(None, {"type": "init", "st_code": MOTOR_ST})
        _, reply = handle_message(ses, {"type": "??"})
        assert reply["type"] == "error"


class TestCosimWebSocket:
    def test_ws_motor_flow(self) -> None:
        client = TestClient(app)
        with client.websocket_connect("/api/cosim") as ws:
            ws.send_json({"type": "init", "st_code": MOTOR_ST, "step_ms": 10})
            ready = ws.receive_json()
            assert ready["type"] == "ready"
            ws.send_json({"type": "set", "inputs": {"START": True}})
            assert ws.receive_json()["type"] == "state"
            ws.send_json({"type": "step", "scans": 3})
            st = ws.receive_json()
            assert st["outputs"]["MOTOR"] is True
            assert st["t_ms"] == 30

    def test_ws_error_paths(self) -> None:
        client = TestClient(app)
        with client.websocket_connect("/api/cosim") as ws:
            ws.send_json({"type": "step"})
            assert ws.receive_json()["type"] == "error"
            ws.send_json({"type": "init", "st_code": ""})
            assert ws.receive_json()["type"] == "error"


class TestTrace:
    def test_trace_records_every_scan(self) -> None:
        ses = CosimSession(MOTOR_ST, step_ms=10)
        ses.set_inputs({"START": True})
        ses.step(scans=3)
        ses.set_inputs({"START": False})
        ses.step(scans=2)
        assert len(ses.trace) == 5
        assert ses.trace[0]["t_ms"] == 10
        assert ses.trace[0]["o"]["MOTOR"] is True
        assert ses.trace[-1]["i"]["START"] is False
        assert ses.trace[-1]["o"]["MOTOR"] is True  # 자기유지 기록

    def test_trace_cap_drops_oldest(self) -> None:
        import app.cosim as cosim_mod

        orig = cosim_mod.MAX_TRACE_SCANS
        cosim_mod.MAX_TRACE_SCANS = 4
        try:
            ses = CosimSession(MOTOR_ST, step_ms=10)
            ses.step(scans=10)
            assert len(ses.trace) == 4
            assert ses.trace_truncated is True
            assert ses.trace[0]["t_ms"] == 70  # 앞부분 탈락
        finally:
            cosim_mod.MAX_TRACE_SCANS = orig

    def test_trace_message(self) -> None:
        ses, _ = handle_message(None, {"type": "init", "st_code": MOTOR_ST})
        ses, _ = handle_message(ses, {"type": "step", "scans": 2})
        _, reply = handle_message(ses, {"type": "trace"})
        assert reply["type"] == "trace"
        assert len(reply["samples"]) == 2
        assert reply["truncated"] is False
