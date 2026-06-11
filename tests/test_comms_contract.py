"""Stage 3 통신 계약(PlcLink/WriteRejected) 스모크 테스트."""

from __future__ import annotations

from app.comms import PlcLink, WriteRejected


class _FakeLink:
    """PlcLink 구조적 준수 확인용 최소 가짜 링크."""

    def __init__(self) -> None:
        self._out: dict[str, bool] = {}

    def write_inputs(self, values: dict[str, bool]) -> None:
        self._out.update(values)

    def read_outputs(self) -> dict[str, bool]:
        return dict(self._out)

    def close(self) -> None:
        self._out.clear()


def test_fake_link_is_plclink() -> None:
    link = _FakeLink()
    assert isinstance(link, PlcLink)  # runtime_checkable Protocol
    link.write_inputs({"START": True})
    assert link.read_outputs()["START"] is True
    link.close()
    assert link.read_outputs() == {}


def test_write_rejected_is_exception() -> None:
    assert issubclass(WriteRejected, Exception)
    try:
        raise WriteRejected("인터락 위반: FWD+REV")
    except WriteRejected as exc:
        assert "인터락" in str(exc)
