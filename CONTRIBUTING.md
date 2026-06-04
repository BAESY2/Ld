# 기여 가이드

PLC 래더 변환 멀티 에이전트에 기여해 주셔서 감사합니다.

## 개발 환경

```bash
uv venv --python 3.11 && uv pip install -e ".[dev,web]"
source .venv/bin/activate
```

## 커밋 전 체크 (CI 와 동일)

```bash
ruff check app tests scripts training   # 린트
mypy app                                 # 타입 (strict)
pytest -q                                # 단위 테스트
python scripts/eval.py                   # 골든셋 게이트 (이중코일 0 · 인터락 0)
```

네 가지가 모두 통과해야 머지됩니다.

## 절대 규칙 (CLAUDE.md 와 동일)

1. IEC 61131-3 표준 타입(BOOL/INT/DINT/REAL/TIME/WORD)만.
2. LS 디바이스 체계(P/M/T/C/D/L/K)만.
3. **이중 코일 금지** — 프롬프트가 아니라 `merge_double_coils` + verifier 로 기계적으로 막는다.
4. 새 모듈은 같은 커밋에 pytest 테스트를 동반한다.
5. LLM 호출 코드는 테스트에서 반드시 mock — **API 키 없이 CI 가 통과**해야 한다.
6. 타입 힌트 100%, ruff/mypy 통과 유지.
7. 모델 프로바이더는 `agents._llm()` 한 곳에서만 결정(vendor-agnostic).

## 라이선스/데이터 규칙

- 유출/탈취된 모델 가중치·코드는 절대 사용 금지.
- 자체 모델 튜닝은 **허용 라이선스(Apache 등) 베이스 + 자체 클린 데이터**만.
- 에러코드/명령어 데이터는 제조사 매뉴얼 본문 복제 금지, 사실 데이터+출처만, ToS 존중.

## 아키텍처

설계 배경은 [`ARCHITECTURE_REVIEW.md`](ARCHITECTURE_REVIEW.md), 빌드 플랜은 [`PLAN.md`](PLAN.md) 참조.
신뢰의 핵심은 LLM 이 아니라 **결정론 코어(메모리맵·트랜스파일러·Z3 검증)** 다.
