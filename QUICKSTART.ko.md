# 빠른 시작

[English](QUICKSTART.md) · **한국어**

Fluma 는 로컬에서 돕니다: 웹 스튜디오(Node) + 파이썬 파이프라인이 오픈소스 Craft 앱을 부립니다. 새 Linux 컴퓨터 기준 약 10분(Craft 앱 내려받기 시간 별도).

## 1. 준비물

| 도구 | 버전 | 설치 |
|---|---|---|
| Python | 3.10+ | 패키지 관리자 또는 [python.org](https://www.python.org) |
| Node.js | 20+ | [nodejs.org](https://nodejs.org) |
| ffmpeg | 최근 버전 | `sudo apt install ffmpeg` · `sudo dnf install ffmpeg` · `brew install ffmpeg` · `winget install ffmpeg` |

에이전트도 필요합니다: 로그인된 **Claude Code** 또는 **Codex** CLI, 또는 API 키(Anthropic · OpenAI · OpenRouter ·
Gemini · 로컬 Ollama) — 나중에 **설정 → 모델 · 공급자**에 넣습니다.

## 2. 설치

```bash
git clone https://github.com/meowassassin/fluma && cd fluma
python3 scripts/doctor.py --fix
```

`doctor.py` 는 `.venv` 를 만들고 파이썬 패키지(`scripts/requirements.txt`)를 설치하고, Chromium 을 받고, 웹 앱과
HyperFrames 대체 엔진의 `npm install` 을 돌립니다. Node · ffmpeg 는 설치 방법만 *알려 주며* 관리자 권한이 필요 없습니다.

| 프로필 | 더하는 것 | 명령 |
|---|---|---|
| `lite`(기본) | 콘티 · 무료 음성 · 렌더 · 검사 | `python3 scripts/doctor.py --fix` |
| `analysis` | 레퍼런스 분석: 받아쓰기 · OCR · 화면 분류 | `--profile analysis` |
| `full` | 누끼 · 생성 API | `--profile full` |

## 3. Craft 앱 설치

파이프라인은 모든 장면을 오픈소스 [Craft 앱](https://github.com/storytold)(MIT / Apache-2.0)으로 만듭니다.
저장소에 들어 있지 않으니 쓸 앱을 받습니다:

```bash
python3 scripts/crafts.py plan all       # 받을 파일 · 크기만 보기(받지 않음)
python3 scripts/crafts.py install effectcraft soundcraft filmcraft vectorcraft gridcraft pdfcraft photocraft
# 전부(16개, 약 1.7GB):  python3 scripts/crafts.py install all
```

릴리스를 SHA256SUMS 로 검증해 `tools/crafts/`(git 제외)에 풉니다. 스튜디오에서도 설치할 수 있습니다(⌘K → *Craft 앱*).
Craft 앱이 없으면 HyperFrames 로 대신 렌더합니다.

## 4. 실행

```bash
npm --prefix web run dev     # API 127.0.0.1:4310, 스튜디오 http://localhost:4311
```

스튜디오의 홈에서 주제를 적고 대화로 기획합니다. 콘티가 괜찮으면 **제작 시작** — 에이전트가 레퍼런스 쇼츠를 분석하고
장면을 만들어 초안을 렌더합니다. 편집기 왼쪽 탐색기에 영상이 무엇으로 이루어졌는지 나오고, 고칠 것은 오른쪽 에이전트에게 말합니다.

## 5. YouTube 연결(선택)

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

```bash
docker compose up --build
```

그다음 http://localhost:4311 을 엽니다. 에이전트 CLI 로그인은 컨테이너 안에 없으니 설정에서 API 키를 쓰세요.

## 확인 · 문제 해결

```bash
python3 scripts/doctor.py           # 무엇이 설치됐고 무엇이 빠졌나
python3 scripts/doctor.py --sizes   # 무엇이 디스크를 차지하고 무엇을 지워도 되나
python3 scripts/crafts.py list      # 설치된 Craft 앱
python -m pytest tests              # 핵심 시험
```

- **렌더에 소리가 없음** — 기본 음성이 *무음(시험용)*일 수 있어요. 설정 → 미디어 → 음성에서 목소리를 고르세요.
- **무료 2D 모델 할당량 초과** — 설정 → 미디어 → 2D 생성에 무료 Hugging Face 토큰을 넣으세요.
- **Linux 에서만 시험함** — macOS · Windows 에서는 `doctor.py` 출력과 함께 이슈를 열어 주세요.
