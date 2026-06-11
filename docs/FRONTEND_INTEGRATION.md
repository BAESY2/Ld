# 프런트 통합 설계 — WASM 스튜디오 × 디지털트윈 (WebGL 전환 포함)

> 분석일 2026-06-11 · 대상 브랜치: `claude/nlang-plc-design-8oYP1`(스튜디오) ↔ 본 브랜치(트윈)

## 1. 자산 분석

| | 스튜디오 `docs/web.html` + `frontend/plant3d.js` | 트윈 `docs/demo/index.html` |
|---|---|---|
| 렌더 | **Three.js**(1,090줄 프리팹 라이브러리) — 콘크리트/해저드 텍스처, roundedBox·capsule·lathe·I빔·플랜지 배관, 라벨 스프라이트, 그림자 | 캔버스 아이소메트릭(의존성 0) — 깊이 정렬 큐 |
| 설비 표현 | 프리팹 `{group, anim(on,t,dt)}` — bMotor/bPump/bValve… kind별 | 씬 함수 9종 — beltUnit/cyl3/fence/로봇/지게차 프리팹 |
| 물리/생산 | 없음(출력 ON/OFF 애니만) | **라인 물리**(부품 흐름·폐루프 센서·고장 주입) + KPI/OEE/알람 |
| 엔진 | Pyodide(WASM)로 실엔진 — 자유 자연어 설계 | 내장 레시피 9종 + 가상 PLC 9대 병렬 + 서버 코사임 |
| 계약 | `Plant3D.create(el, plant, {onToggle}) → {update(simResult), resize, destroy}` · `PlantLayout{devices(kind,role,tag), connections(pipe/signal)}` | `SCENES[id]{init,sense,tick,draw,prod,quality,…}` + `LINES` 런타임 |

결론: **스튜디오의 렌더 품질 + 트윈의 물리·운영 데이터**가 정확히 상호보완. 계약이 둘 다
명확해 어댑터 통합이 가능하다.

## 2. 통합 단계

### P-A. 트윈 엔진 모듈화 — ✅ 완료 (frontend/twin-engine.js 161KB 추출, scripts/build_demo.py 인라인 빌드, 동기화 강제 pytest 3건)
- 가동 화면의 PLC/SCENES/KPI/알람 코드를 `frontend/twin-engine.js`(`window.TwinEngine`)로 추출.
- 가동 화면은 이를 `<script src>`로 로드(file:// 호환 위해 인라인 폴백 유지 또는 빌드 시 인라인).
- 산출: 양쪽 페이지가 같은 엔진을 공유할 수 있는 단일 소스.

### P-B. 스튜디오 3D 탭 어댑터
- `web.html`의 `ensure3D()`에서: 설계가 내장 레시피와 매칭(nlmatch recipe_id)되면
  `TwinEngine.mount(container, recipeId)` — 물리 트윈 + KPI 미니 패널.
- 미지/자유 설계면 기존 `Plant3D.create` 유지(일반 렌더). 사용자는 차이를 모르게 폴백.

### P-C. WebGL 이식 — 🚧 1단계 완료(three.min.js 벤더링 + `frontend/twin3d-poc.html`: beltUnit 프리팹 1:1 포팅, 실그림자·궤도 카메라·헤드리스 검증)
- 트윈 프리팹을 plant3d.js 스타일 `{group, anim}`으로 1:1 포팅:
  beltUnit→BoxGeometry+텍스처 벨트, cyl3→CylinderGeometry, fence→I빔+해저드 텍스처,
  로봇 암→본 체인(또는 단순 조인트 그룹), 지게차/작업자→그룹 애니.
- 물리 `tick()`은 그대로(렌더만 교체) — 깊이 정렬 큐 폐기(z-buffer), OrbitControls
  자유 회전/줌, 그림자 맵, 라벨 스프라이트 재사용.
- `frontend/vendor/three.min.js`를 본 브랜치로 복사(오프라인 원칙 유지 — 그 브랜치 방식 그대로).
- 성능: 활성 라인만 WebGL 렌더, 백그라운드 8라인은 현행 헤드리스 tick 유지(구조 이미 분리됨).

### P-D. 자유 설계 → 물리 트윈 자동 합성
- `plant_from_spec` devices의 kind→트윈 프리팹 매핑표(motor→컨베이어 유닛, pump→펌프+탱크,
  valve→배관 밸브, robot→용접 셀, conveyor→벨트…) + connections(pipe)로 배관 자동 배선.
- 레시피가 아닌 자유 자연어 설계도 부품 흐름 물리를 갖는 트윈 생성 — 공장 편집기의 전 단계.

## 3. 리스크·결정

- three.min.js(~600KB) 벤더링: GitHub Pages 용량 무관, 오프라인 원칙 유지 가능 — 채택.
- 트윈 엔진 추출 시 file:// 단독 실행 회귀 금지: 추출 후 `docs/demo`는 빌드 스크립트로
  인라인 병합(현행 단일 파일 배포 유지).
- 두 브랜치 평행 개발 충돌: 통합은 본 브랜치에서 진행, 스튜디오 브랜치는 읽기 소스로만.

## 4. 작업량 추정

| 단계 | 규모 | 산출물 |
|---|---|---|
| P-A | 세션 0.5 | twin-engine.js + 빌드 인라인 스크립트 |
| P-B | 세션 0.5 | web.html 어댑터 + 폴백 |
| P-C | 세션 2~3 | WebGL 트윈(프리팹 12종 포팅 + OrbitControls) |
| P-D | 세션 1~2 | kind→프리팹 매핑 + 자동 배치 휴리스틱 |
