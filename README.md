# Ladder AI (Ld)

Ladder AI 프로젝트 저장소입니다.

이 저장소는 코딩 에이전트로 **[OpenCode](https://opencode.ai)** 를 사용합니다.
OpenCode는 터미널 기반의 오픈소스 AI 코딩 에이전트로, Claude Code의 오픈소스 대안입니다.
(도입 배경과 영상 분석은 [`docs/opencode-분석.md`](docs/opencode-분석.md) 참고)

## OpenCode 시작하기

### 1. 설치

```bash
# npm
npm install -g opencode-ai

# 또는 설치 스크립트
curl -fsSL https://opencode.ai/install | bash
```

### 2. 로그인 / 프로바이더 인증

```bash
opencode auth login
```

Anthropic, OpenAI, OpenRouter, 로컬 모델(Ollama) 등 다양한 프로바이더를 지원합니다.

### 3. 실행

```bash
# 프로젝트 루트에서
opencode
```

프로젝트별 설정은 [`opencode.json`](opencode.json), 에이전트 규칙은 [`AGENTS.md`](AGENTS.md) 에 정의되어 있습니다.

## 저장소 구조

| 파일 | 설명 |
|------|------|
| `opencode.json` | OpenCode 프로젝트 설정 (모델, 권한, 포맷터 등) |
| `AGENTS.md` | 에이전트에게 주는 프로젝트 규칙/컨벤션 |
| `docs/opencode-분석.md` | OpenCode 영상 분석 및 도입 배경 정리 |
