"""벤더별 명령어 RAG 코퍼스 + vendor 필터 테스트 (Phase G 확장).

원칙(과제 제약 준수):
  * LLM 호출 없음 — 순수 BM25-lite/키워드, API 키 불필요·결정론적.
  * 공개 API(``InstructionRetriever.retrieve`` / ``get_instruction_context``)만 사용.
  * vendor 필터는 하위호환(선택 인자)이며 None 이면 기존 동작과 동일함을 검증.

검증 대상:
  1. retrieve()/get_instruction_context() 가 키 없이 동작한다(USE_RAG=true).
  2. 한국어 질의("타이머"/"상승엣지"/"정역")가 벤더-정확 청크를 표면화한다.
  3. vendor 필터가 해당 벤더 항목만 반환한다(타 벤더 배제).
  4. 모든 벤더 청크가 vendor + source(URL) 필드를 가진다(수집 원칙).
"""

from __future__ import annotations

import dataclasses

import pytest

import app.rag as rag_module
from app.rag import InstructionRetriever, get_instruction_context

# ---------------------------------------------------------------------------
# 헬퍼 (test_rag.py 와 동일 패턴: frozen Settings 우회 없이 새 인스턴스 교체)
# ---------------------------------------------------------------------------


def _set_use_rag(monkeypatch: pytest.MonkeyPatch, value: bool) -> None:
    """app.rag.settings.use_rag 를 패치하고 corpus 캐시를 무효화한다."""
    import app.config as config_module
    from app.config import Settings

    original = config_module.settings
    new_settings = Settings.__new__(Settings)
    for f in dataclasses.fields(original):
        object.__setattr__(new_settings, f.name, getattr(original, f.name))
    object.__setattr__(new_settings, "use_rag", value)

    monkeypatch.setattr(config_module, "settings", new_settings)
    monkeypatch.setattr(rag_module, "settings", new_settings)
    # 재로드 보장 (결정론)
    monkeypatch.setattr(rag_module, "_corpus_cache", None)


# ---------------------------------------------------------------------------
# 1. 키 없이 동작 / 한국어 질의가 벤더-정확 청크를 표면화
# ---------------------------------------------------------------------------


class TestKeyFreeKoreanQueries:
    def test_retrieve_is_key_free_and_deterministic(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM·API 키 없이 동작하고, 같은 질의는 같은 결과를 준다."""
        _set_use_rag(monkeypatch, True)
        r = InstructionRetriever()
        first = r.retrieve("타이머", k=4)
        second = r.retrieve("타이머", k=4)
        assert isinstance(first, str) and first
        assert first == second  # 결정론

    def test_timer_query_surfaces_timer_chunk(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_use_rag(monkeypatch, True)
        result = get_instruction_context("타이머 시간베이스")
        assert "TON" in result or "TIM" in result or "타이머" in result

    def test_rising_edge_query_surfaces_oneshot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """'상승엣지' 질의는 원샷/엣지 명령(PLS/OUTP/DIFU/R_TRIG 류)을 표면화."""
        _set_use_rag(monkeypatch, True)
        result = get_instruction_context("상승엣지 원샷")
        assert any(
            tok in result
            for tok in ("PLS", "OUTP", "DIFU", "R_TRIG", "엣지", "ONS", "P접점")
        ), f"엣지/원샷 청크가 표면화되지 않음: {result[:200]}"

    def test_interlock_query_surfaces_self_hold_or_interlock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """'정역'/'인터락' 질의는 인터락·자기유지 idiom 을 표면화."""
        _set_use_rag(monkeypatch, True)
        result = get_instruction_context("정역 인터락 상호배제")
        assert "인터락" in result or "정역" in result or "자기유지" in result

    def test_mov_query_surfaces_data_transfer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_use_rag(monkeypatch, True)
        result = get_instruction_context("데이터 이동 MOV 전송")
        assert "MOV" in result or "이동" in result


# ---------------------------------------------------------------------------
# 2. vendor 필터: 해당 벤더 항목만 반환
# ---------------------------------------------------------------------------


class TestVendorFilter:
    @pytest.mark.parametrize(
        ("vendor", "marker"),
        [
            ("LS", "LS"),
            ("MITSUBISHI", "미쓰비시"),
            ("SIEMENS", "지멘스"),
            ("OMRON", "옴론"),
            ("ROCKWELL", "로크웰"),
        ],
    )
    def test_filter_returns_only_that_vendor(
        self, monkeypatch: pytest.MonkeyPatch, vendor: str, marker: str
    ) -> None:
        """vendor 필터 적용 시 그 벤더 마커가 모든 청크에 나타나야 한다."""
        _set_use_rag(monkeypatch, True)
        r = InstructionRetriever()
        # 일부러 다른 벤더의 명령(타이머)을 질의해도 필터가 격리해야 함
        result = r.retrieve("타이머 카운터 이동 비교", k=4, vendor=vendor)
        assert result, f"{vendor} 필터 결과가 비어있음"
        # 폴백으로 떨어지지 않았는지(폴백엔 벤더 마커 없음) 확인
        assert marker in result, f"{vendor} 필터 결과에 마커 '{marker}' 없음: {result[:200]}"

    def test_filter_excludes_other_vendors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LS 필터 결과에 타 벤더 고유 마커가 섞이면 안 된다."""
        _set_use_rag(monkeypatch, True)
        r = InstructionRetriever()
        result = r.retrieve("타이머 이동 비교 카운터", k=6, vendor="LS")
        for foreign in ("미쓰비시", "지멘스", "옴론", "로크웰"):
            assert foreign not in result, (
                f"LS 필터 결과에 타 벤더 마커 '{foreign}' 누출: {result[:300]}"
            )

    def test_filter_case_insensitive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_use_rag(monkeypatch, True)
        r = InstructionRetriever()
        upper = r.retrieve("타이머", k=4, vendor="OMRON")
        lower = r.retrieve("타이머", k=4, vendor="omron")
        assert upper == lower
        assert "옴론" in lower

    def test_unknown_vendor_falls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """존재하지 않는 벤더는 예외 없이 폴백을 반환한다."""
        _set_use_rag(monkeypatch, True)
        r = InstructionRetriever()
        result = r.retrieve("타이머", k=4, vendor="NONEXISTENT")
        assert result == rag_module._FALLBACK_INSTRUCTIONS

    def test_vendor_none_is_backward_compatible(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """vendor=None 은 vendor 인자 미지정과 동일(하위호환)."""
        _set_use_rag(monkeypatch, True)
        r = InstructionRetriever()
        without = r.retrieve("타이머 카운터", k=4)
        with_none = r.retrieve("타이머 카운터", k=4, vendor=None)
        assert without == with_none

    def test_get_instruction_context_vendor_kwarg(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """모듈 진입점도 vendor 선택 인자를 받는다."""
        _set_use_rag(monkeypatch, True)
        result = get_instruction_context("타이머 감산", vendor="OMRON")
        assert "옴론" in result


# ---------------------------------------------------------------------------
# 3. 벤더-정확성: 고가치 사실(시간베이스/진법/엣지)이 올바른 벤더에 매핑
# ---------------------------------------------------------------------------


class TestVendorCorrectFacts:
    def test_omron_timer_is_countdown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """옴론 TIM 은 감산(카운트다운) 타이머라는 사실이 표면화."""
        _set_use_rag(monkeypatch, True)
        result = get_instruction_context("옴론 TIM 타이머", vendor="OMRON")
        assert "감산" in result or "TIM" in result

    def test_mitsubishi_octal_io_fact(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """미쓰비시 X/Y 가 8진(octal) 이라는 진법 사실이 표면화."""
        _set_use_rag(monkeypatch, True)
        result = get_instruction_context("미쓰비시 입출력 주소 진법", vendor="MITSUBISHI")
        assert "8진" in result or "octal" in result.lower()

    def test_siemens_instance_db_timer_fact(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """지멘스 IEC 타이머가 인스턴스 DB 를 요구한다는 사실이 표면화."""
        _set_use_rag(monkeypatch, True)
        result = get_instruction_context("지멘스 타이머 TON", vendor="SIEMENS")
        assert "인스턴스" in result or "DB" in result

    def test_ls_edge_oneshot_outp(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LS 상승엣지 원샷이 OUTP 라는 사실이 표면화."""
        _set_use_rag(monkeypatch, True)
        result = get_instruction_context("LS 상승엣지 원샷 펄스", vendor="LS")
        assert "OUTP" in result


# ---------------------------------------------------------------------------
# 4. 수집 원칙: 모든 벤더 청크는 vendor + source(URL) 를 가진다
# ---------------------------------------------------------------------------


def test_all_vendor_chunks_have_vendor_and_source() -> None:
    """vendor 가 있는 모든 청크는 source 필드(출처 URL)를 가져야 한다.

    (제조사 매뉴얼 산문 복제 금지 — 사실 데이터 + 출처 URL 만 저장하는 원칙.)
    """
    corpus = rag_module._load_corpus()
    assert corpus, "corpus 가 비어있음"
    vendor_entries = [e for e in corpus if e.get("vendor")]
    assert vendor_entries, "벤더 청크가 하나도 없음"
    for e in vendor_entries:
        assert isinstance(e.get("vendor"), str) and e["vendor"].strip(), (
            f"vendor 필드 누락/빈값: {e.get('name')}"
        )
        src = e.get("source")
        assert isinstance(src, str) and src.strip(), (
            f"source(출처) 필드 누락: {e.get('name')}"
        )


def test_corpus_covers_required_vendors() -> None:
    """LS/Mitsubishi/Siemens/Omron 4대 벤더가 모두 코퍼스에 존재해야 한다."""
    corpus = rag_module._load_corpus()
    vendors = {e.get("vendor") for e in corpus if e.get("vendor")}
    for required in ("LS", "MITSUBISHI", "SIEMENS", "OMRON"):
        assert required in vendors, f"필수 벤더 누락: {required} (현재: {vendors})"


def test_all_entries_are_valid_json_schema() -> None:
    """기존+신규 모든 항목이 최소 스키마(name/category/description)를 만족한다."""
    corpus = rag_module._load_corpus()
    for e in corpus:
        for field in ("name", "category", "description"):
            assert isinstance(e.get(field), str) and e[field], (
                f"필수 필드 '{field}' 누락: {e.get('name')}"
            )
