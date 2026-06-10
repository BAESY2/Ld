# 3D 에셋 라이선스 / 출처 (frontend/vendor)

## 현재 동봉 에셋: **없음 (0개)**

`frontend/plant3d.js` 의 모든 기기·구조·배관·캐비닛 메시는 **100% 절차 생성**
(THREE.js 지오메트리: Box/Cylinder/Torus/**Lathe**/**Extrude(베벨)**/**Capsule**)
이며, 외부 glTF/GLB·텍스처·HDRI 바이너리를 일절 포함하지 않는다. 환경맵은
`PMREMGenerator` 로 절차 생성한다(외부 에셋 0). 따라서 본 디렉터리에는 별도의
서드파티 에셋 라이선스 고지 대상이 없다.

### 왜 절차 고품질화인가 (CC0 glTF 를 동봉하지 않은 이유)
- 산업 기기(모터·펌프·밸브·탱크·컨베이어·로봇암·제어반) 전 품목을 커버하는
  **검증된 CC0/공개도메인 glTF 세트**를 단일 출처에서 안정적으로(라이선스 명확 +
  직접 다운로드 가능) 확보하지 못했다. Poly Haven / Kenney / Quaternius /
  ambientCG / Khronos glTF-Sample-Assets 는 CC0 자산을 제공하나, 산업 설비
  품목 매칭이 부분적이고 품목별 라이선스를 개별 확인해야 한다.
- r160 UMD 빌드(`three.min.js`)와 함께 쓸 **UMD 호환 GLTFLoader 가 r160 에서
  제거**되었다(legacy `examples/js` 삭제, `examples/jsm` ES 모듈만 존재).
  헤드리스 스모크(`scripts/js_smoke.js`)는 스크립트를 `eval`/CommonJS `require`
  로 로드하므로 ES 모듈 로더를 빌드 없이 끼워 넣으면 회귀 위험이 크다.
- 결론: **절차 메시를 고품질화**(베벨 ExtrudeGeometry 라운드 박스, Lathe 곡면
  바디/볼류트/토리스페리컬 헤드, Capsule 라운드 케이싱, 마운팅 풋·요크 볼트·
  플린스 등 디테일)하여 "모형 같다"는 피드백을 해소했다.

## 향후 CC0 glTF 드롭인 방법 (훅 준비 완료)
`plant3d.js` 에 비동기 에셋 훅이 내장되어 있다. 깨짐 없이(생성 시 throw 금지)
다음 절차로 실제 CC0 모델을 끼울 수 있다.

1. CC0/공개도메인 GLB 를 `frontend/vendor/assets/<kind>.glb` 에 둔다.
2. r160 호환 GLTFLoader 를 전역으로 노출(`window.GLTFLoader` 또는
   `THREE.GLTFLoader`). UMD 래퍼가 필요하며, 가져온 로더의 라이선스(three.js =
   MIT)를 이 파일에 추가 고지한다.
3. `create()` 호출 전에 매니페스트를 채운다:
   ```js
   window.Plant3D.ASSETS.motor = { url: "vendor/assets/motor.glb", scale: 1, yaw: 0, y: 0 };
   ```
4. 동작: 생성 시 절차 메시를 즉시 배치 → 로더+GLB 가 있으면 로드 완료 시 절차
   메시를 GLB 로 **교체**(라벨 스프라이트는 보존). 로더 없음/로드 실패/헤드리스
   → 절차 메시 그대로 유지(예외 0).

### 드롭인 시 라이선스 고지 양식 (예시 — 현재 미적용)
| kind | 파일 | 출처(URL) | 저작자 | 라이선스 |
|------|------|-----------|--------|----------|
| (없음) | — | — | — | — |

> CC0 외 라이선스(예: CC-BY) 에셋을 추가할 경우, 저작자 표기(attribution)를
> 본 표와 배포물에 반드시 포함할 것. 현재는 동봉 에셋이 없어 표기 의무 없음.

## 조사한 CC0/공개도메인 소스 (참고)
- Khronos glTF-Sample-Assets — https://github.com/KhronosGroup/glTF-Sample-Models (다수 CC0)
- Poly Haven — https://polyhaven.com (CC0)
- Kenney — https://kenney.nl/assets (CC0)
- Quaternius — https://quaternius.com (CC0)
- ambientCG — https://ambientcg.com (CC0, 주로 텍스처/HDRI)
- awesome-cc0 — https://github.com/madjin/awesome-cc0

## 동봉 라이브러리
- `three.min.js` — three.js r160, **MIT License** (Copyright 2010-2023 Three.js Authors).
