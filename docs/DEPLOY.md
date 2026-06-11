# 배포 가이드 (DEPLOY)

PLC 래더 에이전트를 **한 줄로** 띄워서 바로 쓰는 방법.
결정론 경로(자연어 매칭·마법사·ST→래더·정형검증·가상 PLC 시뮬)는 **API 키 없이** 동작한다.

## 한 줄 배포

```bash
docker compose up --build
```

띄운 뒤 브라우저에서 **http://localhost:8000** 을 열면 마법사 웹 UI가 나온다.
중지는 `Ctrl-C`, 정리는 `docker compose down`.

> 사내 TLS 가로채기 프록시 환경에서 빌드가 인증서 오류로 실패하면 CA 번들을 넘긴다:
> ```bash
> DOCKER_BUILDKIT=1 docker build \
>   --secret id=cabundle,src=/etc/ssl/certs/ca-certificates.crt \
>   -t plc-ladder-agent:latest .
> ```
> 일반 네트워크에서는 시크릿 없이 그대로 빌드된다(`required=false`).

## 무엇이 뜨는가

| 서비스 | 포트 | 설명 | 기본 활성 |
|---|---|---|---|
| `plc-ladder` (엔진) | `8000` | FastAPI + 정적 프론트(마법사 UI) + 결정론 코어 | O |
| `openplc` (가상 PLC) | `502`, `8080` | OpenPLC v3 런타임(Modbus 슬레이브 샌드박스) | X (프로필) |

- 엔진은 컨테이너 내 `/healthz` 헬스체크로 `healthy` 판정된다.
- **비루트(uid 10001)** 로 실행, 런타임 생성물은 컨테이너 내 `/app/out`.

## 환경 변수 (전부 선택)

| 변수 | 기본 | 의미 |
|---|---|---|
| `ANTHROPIC_API_KEY` | (빈값) | **자연어 생성**(`/api/generate`)에만 필요. 비우면 그 경로만 비활성, 나머지는 정상. |
| `LLM_PROVIDER` | `anthropic` | `anthropic` \| `openai_compatible` \| `local`(자체 호스팅). |
| `USE_Z3` | `true` | Z3 정형검증 사용. |
| `USE_RAG` | `false` | RAG 검색 사용. |
| `CORS_ORIGINS` | `*` | 데모 기본 `*`. **운영 노출 시 신뢰 도메인으로 좁힐 것.** |
| `LOG_LEVEL` | `INFO` | 로그 레벨. |
| `OPENPLC_HOST` | (빈값) | 가상 PLC 어댑터가 붙을 OpenPLC 호스트(아래 샌드박스). |

키 없이 그냥 띄우려면 그대로 `docker compose up --build` 만 하면 된다.
키를 줄 땐 `.env` 에 `ANTHROPIC_API_KEY=sk-...` 한 줄을 두거나
`ANTHROPIC_API_KEY=sk-... docker compose up --build` 로 인라인 지정한다.

## 가상 PLC(OpenPLC) 샌드박스 — 선택

Docker Hub 에 유지보수되는 공식 OpenPLC 이미지가 없어(소스 전용 프로젝트)
**빌드 컨텍스트**로 제공한다. 기본 비활성(`profiles: ["sandbox"]`).

```bash
docker compose --profile sandbox up --build      # OpenPLC v3 를 GitHub 에서 빌드(첫 빌드 수 분)
```

- OpenPLC Modbus 슬레이브 `:502`, 웹 UI `:8080`(기본 로그인 `openplc`/`openplc`).
- 엔진이 가리키게 하려면 `OPENPLC_HOST=openplc` 를 함께 준다:
  ```bash
  OPENPLC_HOST=openplc docker compose --profile sandbox up --build
  ```
- 이미 OpenPLC 이미지를 보유했다면 `docker-compose.yml` 의 `openplc.build` 를
  `image: <your-openplc-image>` 로 교체하면 된다.

라이선스 격리: 엔진과 OpenPLC 는 **Modbus/REST 프로세스 경계로만** 통신한다(링크 금지).
세부는 `docs/OPENPLC_STRATEGY.md` 참조.

## 실제 PLC(OpenPLC/LS XGT)로 지향

가상 샌드박스 대신 **실 장비**를 쓰려면 그 장비의 Modbus TCP 슬레이브를 가리킨다:

```bash
OPENPLC_HOST=192.168.0.50 docker compose up --build   # 실 OpenPLC/LS PLC 의 IP
```

- LS XGT/XGB: FEnet/Cnet 의 Modbus 설정 주소(`%MX`/`%MW`)로 매핑(로드맵: FEnet `:2004` 네이티브).
- 엔진 컨테이너에서 대상 PLC 네트워크가 라우팅 가능해야 한다(같은 LAN/VPN).

## 보안 / 안전 고지

- **인터넷에 인증 없이 노출 금지.** 기본 구성에는 인증/TLS 가 없다 — 사내망 또는
  리버스 프록시(인증·TLS) 뒤에서만 공개하고, `CORS_ORIGINS` 를 좁힌다.
- OpenPLC `:8080`/`:502` 와 엔진 `:8000` 을 공인 IP 에 바인딩하지 말 것.
- **안전 면책:** 본 도구의 검증/시뮬은 *논리 보조*이며 **안전 인증이 아니다**.
  실기의 비상정지(E-stop)·인터락은 소프트웨어 밖 **하드와이어 릴레이**로 구현한다.
  생성 결과는 현장 적용 전 반드시 자격 있는 엔지니어가 검토할 것.

## 검증(스모크)

Docker 없이 CI 안전 스모크:

```bash
pytest tests/test_deploy_smoke.py -q     # /healthz, 정적 프론트, /api/recipes
```
