# 프로젝트 규칙 (Claude Code 필독)

## 정체성
산업 자동화(LS일렉트릭/메카피온) PLC 래더 변환 멀티 에이전트 백엔드.
자연어(한국어) → 상태머신 명세 → IEC 61131-3 ST → 정형 검증 → 래더 JSON.

## 절대 규칙
1. 모든 변수는 IEC 61131-3 표준 타입(BOOL/INT/DINT/REAL/TIME/WORD)만 사용.
2. 디바이스 클래스는 LS 체계(P=입출력, M=내부릴레이, T=타이머, C=카운터, D=데이터)만.
3. 동일 출력 심볼을 두 번 이상 코일로 대입(이중 코일)하지 않는다.
4. 새 모듈을 만들면 반드시 같은 커밋에 pytest 테스트를 추가한다.
5. LLM을 호출하는 코드는 테스트에서 반드시 mock 한다 (API 키 없이 CI 통과해야 함).
6. 타입 힌트 100%, ruff/mypy 통과 상태 유지.
7. 모델 프로바이더는 `_llm()` 한 곳에서만 결정한다(anthropic/openai_compatible/local). vendor-agnostic 유지.

## 빌드 순서 (PLAN.md 참조)
결정론적 코어 → LLM 에이전트 → LangGraph → API → RAG → 프론트 연동.
각 Task는 "완료 기준"의 명령이 통과해야 다음으로 넘어간다.

## 테스트 명령
- 단위: `pytest -q`
- 타입: `mypy app`
- 린트: `ruff check app`
