# 빠른 시작

[English](QUICKSTART.md) · **한국어**

Fluma 는 로컬에서 돕니다: 웹 스튜디오(Node) + 파이썬 파이프라인이 오픈소스 Craft 앱을 부립니다.

## 나에게 맞는 방법 고르기

| 원하는 것 | 방법 | 시간 |
|---|---|---|
| 내 에이전트에게 맡기기 | Claude Code · Codex 에게: *이 스킬을 써 줘: https://raw.githubusercontent.com/meowassassin/fluma/main/docs/skill/SKILL.md — "…" 쇼츠를 만들어 줘* | 손 안 댐 |
| 가장 쉽게, 어느 운영체제든(Linux · macOS · Windows) | [Docker](#docker) — 명령 두 줄, 전부 들어 있음 | 처음 약 15GB 받기 |
| 내 컴퓨터에 바로 설치 | [설치](#2-설치) — `doctor.py --fix` | 약 10분 + 내려받기 |
| Fluma 자체를 고치기 | 설치 후 `npm --prefix studio run dev` 와 [시험](#확인--문제-해결) | — |

어느 쪽이든 에이전트가 필요합니다: 내 컴퓨터에 로그인된 **Claude Code** 나 **Codex**(Docker 도 그 로그인을 그대로 씀),
또는 API 키(Anthropic · OpenAI · Gemini · 로컬 Ollama)를 **설정 → 모델 · 공급자**에 넣습니다.

### 컴퓨터 사양

| | Docker | 바로 설치 |
|---|---|---|
| 디스크 | 약 15GB(이미지) + 만든 영상 | 약 6GB(.venv 1.3 · Craft 앱 3.6 · 모델 약 1 · Chromium 0.7) |
| 메모리 | 8GB 이상(16GB 에서 시험) | 같음 |
| CPU | 64비트면 됨. 분석 · 렌더는 코어를 모두 씀(8코어에서 시험) | 같음 |
| GPU | 필요 없음 | 필요 없음 |

작게: `PROFILE=lite CRAFTS=core MODELS=0 docker compose build` 또는 `doctor.py --fix --profile lite --core` — 빠진 것은 처음 쓸 때 스스로 설치됩니다.

## 1. 준비물

| 도구 | 버전 | 설치 |
|---|---|---|
| Python | 3.10+ | 패키지 관리자 또는 [python.org](https://www.python.org) |
| Node.js | 20+ | [nodejs.org](https://nodejs.org) |
| ffmpeg | 최근 버전 | `sudo apt install ffmpeg` · `sudo dnf install ffmpeg` · `brew install ffmpeg` · `winget install ffmpeg` |

에이전트도 필요합니다: 로그인된 **Claude Code** 또는 **Codex** CLI, 또는 API 키(Anthropic · OpenAI ·
Gemini · 로컬 Ollama) — 나중에 **설정 → 모델 · 공급자**에 넣습니다.

## 2. 설치

```bash
git clone https://github.com/meowassassin/fluma && cd fluma
python3 engine/doctor.py --fix
```

이 명령 하나로 **전부** 설치합니다: `.venv` 와 파이썬 패키지 전체(`requirements-full.txt`), Chromium, 오픈소스
[Craft 앱](https://github.com/storytold)(MIT / Apache-2.0) 16개 전부(약 1.4GB, SHA256SUMS 로 검증해 `tools/crafts/` 에),
분석 · 누끼 모델, npm 패키지. Node · ffmpeg 는 설치 방법만 *알려 주며* 관리자 권한이 필요 없습니다.

용량이 부족하면 `python3 engine/doctor.py --fix --profile lite --core` 로 최소만(핵심 Craft 앱 7개, 모델 없음) 설치합니다.
빠진 것은 처음 쓰는 순간 자동으로 설치됩니다.

## 3. 실행

```bash
npm --prefix studio run dev     # API 127.0.0.1:4310, 스튜디오 http://localhost:4311
```

'화면 패키지가 없습니다'가 나오면 2단계(`doctor.py --fix`)를 건너뛴 것입니다 — `npm --prefix studio install` 을 한 번 실행하고 다시 시작하세요. Windows · macOS · Linux 같은 명령입니다.

스튜디오의 홈에서 주제를 적고 대화로 기획합니다. 콘티가 괜찮으면 **제작 시작** — 에이전트가 레퍼런스 쇼츠를 분석하고
장면을 만들어 초안을 렌더합니다. 편집기 왼쪽 탐색기에 영상이 무엇으로 이루어졌는지 나오고, 고칠 것은 오른쪽 에이전트에게 말합니다.

### 파일은 어디에

| 무엇 | 바로 설치 | Docker |
|---|---|---|
| 완성 영상 | `data/out/<id>-….mp4` | 볼륨 `fluma_out` |
| 콘티 | `data/storyboards/<id>.json` | 볼륨 `fluma_storyboards` |
| 고칠 수 있는 프로젝트(EffectCraft · SoundCraft · FilmCraft) | `data/compositions/<id>/craft/` | 볼륨 `fluma_compositions` |
| 레퍼런스 분석 | `data/public/trends/` | 볼륨 `fluma_trends` |
| API 키 · YouTube 로그인 | `~/.shortsforge/`(0600, 저장소에 안 들어감, 에이전트는 못 읽음) | 볼륨 `fluma_keys` |

가장 쉬운 방법(어떤 설치든): 편집기 **렌더** 옆 **내려받기** 를 누르면 영상 제목 이름으로 내 컴퓨터에 저장됩니다. 터미널에서(Docker): `docker compose cp fluma:/app/data/out ./videos`

그림 · 정지 화면 · 영상은 에이전트가 채팅에 바로 띄웁니다 — 파일을 찾으러 다닐 필요가 없어야 합니다.

### 업데이트

```bash
git pull
python3 engine/doctor.py --fix                   # 바로 설치: 새 패키지 · Craft 앱 버전
(cd docker && docker compose pull && docker compose up -d)   # Docker: 작업물은 볼륨에 그대로
```

## 3-1. API 키(선택)

없어도 처음부터 끝까지 영상이 나옵니다(무료 · 로컬 경로). 유료 음성(Typecast · ElevenLabs)은 **설정 → 미디어 → 음성**,
무료 스톡 영상 키(Pexels · Pixabay)는 **설정 → 미디어 → 스톡 영상**, 유행 음악 찾기용 YouTube Data API 키는 **설정 → 미디어 → 음악**에 넣습니다.
키는 `~/.shortsforge/api-keys.json`(0600)에 저장되고 에이전트는 읽지 못합니다.

## 4. YouTube 연결(선택)

업로드와 장면별 통계에는 내 Google OAuth 클라이언트가 필요합니다 — 처음 한 번, 약 10분:

1. [Google Cloud 콘솔](https://console.cloud.google.com): 프로젝트를 만들고 **YouTube Data API v3** 와 **YouTube Analytics API** 를 사용 설정.
2. **Google 인증 플랫폼**(OAuth 동의 화면): 외부 · 테스트, **테스트 사용자**에 내 Google 계정 추가(**소문자로** 입력).
3. **클라이언트 → 클라이언트 만들기 → 웹 애플리케이션**, 승인된 리디렉션 URI 에 `http://127.0.0.1:4310/api/youtube/callback`(정확히 이대로).
4. 스튜디오 → **설정 → YouTube**: 클라이언트 ID · 비밀 붙여 넣기 → **저장** → **YouTube 연결**, 권한 3개 모두 허용.

참고: 테스트 모드에서는 7일 뒤 로그인이 만료될 수 있어요 — 다시 '연결'을 누르면 됩니다. 확인받지 않은 앱으로 올린 영상은
'비공개'로 묶일 수 있어 YouTube Studio 에서 바꿉니다. 분석 숫자는 게시 1~2일 뒤부터 채워집니다.

| 증상 | 해결 |
|---|---|
| `redirect_uri_mismatch` | 리디렉션 URI 가 정확히 `http://127.0.0.1:4310/api/youtube/callback` 이어야 함 |
| "액세스 차단됨: 앱이 테스트 중" | 그 계정이 *이* 프로젝트의 테스트 사용자가 아님(클라이언트 ID 앞 숫자 = 프로젝트 번호) |
| 테스트 사용자 추가 시 "부적격 계정" | 주소를 소문자로 입력 |

## Docker

시작 스크립트가 운영체제 · 하드웨어를 스스로 맞춥니다(GPU 가 있으면 연결, 없으면 CPU 로 — 결과는 같고 3D 렌더만 느림).

```bash
sh docker/start.sh                                              # Linux · macOS → http://localhost:4311
powershell -ExecutionPolicy Bypass -File docker\start.ps1        # Windows
```

미리 빌드한 이미지(약 15GB, 처음 한 번)를 받습니다. 직접 빌드하려면 `sh docker/start.sh --build`(약 15분) · `docker\start.ps1 -Build`.
멈추기: `cd docker && docker compose down`. 다른 Docker 명령도 `docker/` 폴더에서 실행합니다(`docker-compose.yml` 이 거기 있음).
CPU 종류도 상관없습니다: 이미지는 Intel · AMD(amd64)와 Apple Silicon · ARM(arm64) 둘 다라 Docker 가 맞는 것을 받습니다.
GPU 로 3D 렌더: Linux 는 스크립트가 자동으로 연결합니다. macOS · Windows 의 Docker 는 GPU 를 컨테이너에 넘기지 못해 CPU 로 돕니다 — GPU 가 꼭 필요하면 아래 '바로 설치'(그 컴퓨터의 GPU 를 그대로 씀).

끝입니다. 에이전트는 내 컴퓨터의 Claude Code · Codex 로그인(`~/.claude` · `~/.codex`)을 그대로 쓰고, 작업물은 Docker 볼륨에 남습니다.
이미지에 전부(파이썬 패키지 전체 · Craft 앱 16개 · 분석 모델) 들어 있습니다.
작게 빌드하려면: `PROFILE=lite CRAFTS=core MODELS=0 docker compose build`.

Docker 가 없으면: [Docker Desktop](https://www.docker.com/products/docker-desktop/)(macOS · Windows), Linux 는 Docker Engine.
Windows 의 Docker Desktop 은 WSL 2 를 씁니다 — 물어보면 [WSL 설치](https://learn.microsoft.com/ko-kr/windows/wsl/install)부터.

<details><summary>문제 해결</summary>

- **`Bind for 127.0.0.1:4311 failed: port is already allocated`** — 다른 Fluma(또는 개발 서버)가 돌고 있습니다. `docker ps` 로 어느 것인지 보고, *그것을 띄운 폴더*에서 `docker compose down` 하거나 개발 서버를 끄세요.
- **`service "fluma" is not running`** — Fluma 를 띄운 폴더와 다른 폴더에서 명령을 실행했습니다(compose 는 폴더 이름으로 프로젝트를 나눔). `docker/` 폴더에서 실행하거나 `docker ps` 로 컨테이너 이름을 찾으세요.
- **에이전트가 로그인되지 않았다고 함**(예: Mac 의 Claude Code 는 로그인을 키체인에 둠): `docker compose exec -it fluma claude` → `/login` 한 번
- **컨테이너가 만든 파일의 주인이 다름(Linux)** — `id -u` 가 1000 이 아니면 `.env` 에 `FLUMA_UID=…` · `FLUMA_GID=…` 를 넣고 다시 빌드

</details>

## 확인 · 문제 해결

```bash
python3 engine/doctor.py           # 무엇이 설치됐고 무엇이 빠졌나
python3 engine/doctor.py --sizes   # 무엇이 디스크를 차지하고 무엇을 지워도 되나
python3 engine/craft/crafts.py list      # 설치된 Craft 앱
python -m pytest tests              # 핵심 시험
```

- **`ffmpeg: command not found`** — 운영체제 패키지 관리자로 설치하세요(위 표). `doctor.py` 가 정확한 명령을 알려 줍니다.
- **모델 내려받기 실패(Hugging Face)** — 네트워크를 확인하고 `python3 engine/core/prefetch_models.py` 를 다시 실행하세요. 빠진 것만 다시 받습니다.
- **렌더에 소리가 없음** — 기본 음성이 *무음(시험용)*일 수 있어요. 설정 → 미디어 → 음성에서 목소리를 고르세요.
- **Windows 에서 스크립트를 직접 돌릴 때 한글 오류** — 파이썬 UTF-8 모드를 한 번 켜세요: `setx PYTHONUTF8 1`(새 터미널부터 적용). 스튜디오는 이미 그렇게 실행합니다.
- **CI 로 Linux · macOS · Windows 를 시험**(설치 · 시험 · 화면 빌드 · 서버 · Craft 앱 하나) — 실제 사용은 아직 주로 Linux 입니다. 문제가 있으면 `doctor.py` 출력과 함께 이슈를 열어 주세요.
