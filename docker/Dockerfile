# Fluma — 컨테이너로 돌리기(Linux · macOS · Windows 공통). 기본으로 전부 들어 있다: 파이썬 패키지(full) · Craft 앱 16개 · 분석 · 누끼 모델
#   docker compose build && docker compose up -d     → http://localhost:4311
#   PROFILE=lite CRAFTS=core MODELS=0 docker compose build   가볍게(빠진 것은 처음 쓸 때 자동 설치)
# 에이전트: 이미지에 든 Claude Code · Codex(Linux 판)가 내 컴퓨터의 로그인(~/.claude · ~/.codex, compose 가 연결)을 쓴다
FROM node:22-bookworm

ARG PROFILE=full
# 에이전트 CLI — 컨테이너는 Linux 라 내 컴퓨터(Mac · Windows)의 실행 파일은 못 돌린다. 로그인 정보는 버전과 상관없이 쓸 수 있다.
# 버전을 고정하려면 --build-arg AGENT_CLIS="@anthropic-ai/claude-code@x.y.z @openai/codex@x.y.z", 빼려면 ""
ARG AGENT_CLIS="@anthropic-ai/claude-code @openai/codex"
# Craft 앱(렌더 엔진) — 기본은 전부(all). core = 핵심 7개
ARG CRAFTS=all
# 분석 · 누끼 모델 미리 받기(1) · 처음 쓸 때 받기(0)
ARG MODELS=1
# Codex 샌드박스(bubblewrap)는 컨테이너 안에서 namespace 를 못 만든다 → 컨테이너 자체가 샌드박스(호스트 파일은 안 보임)
# Chromium 은 /ms-playwright 에(node 사용자도 쓰게) · CLI 자동 업데이트는 끈다(이미지를 다시 빌드하면 최신)
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 FLUMA_HOST=0.0.0.0 FLUMA_CODEX_SANDBOX=danger-full-access \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright DISABLE_AUTOUPDATER=1 FLUMA_IN_DOCKER=1
# Craft 앱의 GL 렌더용 그래픽 라이브러리. bookworm 의 Mesa 22 는 최신 Intel GPU(Lunar Lake)를 몰라 → 백포트 Mesa 25
RUN echo "deb http://deb.debian.org/debian bookworm-backports main" > /etc/apt/sources.list.d/backports.list \
    && apt-get update && apt-get install -y --no-install-recommends python3 python3-venv python3-pip ffmpeg fonts-noto-cjk \
    libegl1 libgl1 libgles2 libxi6 libxxf86vm1 libxfixes3 libxrender1 libxkbcommon0 libsm6 \
    && apt-get install -y --no-install-recommends -t bookworm-backports libgl1-mesa-dri libegl-mesa0 libglx-mesa0 mesa-libgallium libgbm1 \
    && rm -rf /var/lib/apt/lists/*
RUN if [ -n "$AGENT_CLIS" ]; then npm install -g --no-audit --no-fund $AGENT_CLIS; fi

WORKDIR /app
COPY . .
# .venv · Chromium(+ 시스템 의존성) · npm 패키지
RUN python3 -m venv .venv \
    && .venv/bin/pip install --no-cache-dir -r engine/$( [ "$PROFILE" = lite ] && echo requirements.txt || echo requirements-$PROFILE.txt ) \
    && .venv/bin/python engine/doctor.py --hook \
    && .venv/bin/python engine/craft/crafts.py install $( [ "$CRAFTS" = core ] && echo effectcraft soundcraft filmcraft vectorcraft gridcraft pdfcraft photocraft || echo $CRAFTS ) --no-web \
    && .venv/bin/python -m playwright install --with-deps chromium \
    && npm --prefix studio ci --no-audit --no-fund \
    && mkdir -p data/storyboards data/compositions data/audio data/public/audio data/public/uploads data/public/elements data/public/trends data/research data/characters data/briefs data/scenes data/out data/workspace data/cache data/public/clips \
    && mkdir -p /home/node/.shortsforge /home/node/.claude /home/node/.codex \
    && chown -R node:node /app /ms-playwright /home/node   # node = uid 1000(볼륨도 처음 만들 때 이 소유자를 따른다)

# 내 사용자(uid 1000)로 — root 로 돌면 연결한 ~/.claude 의 로그인 파일이 root 소유가 되어 내 컴퓨터의 CLI 가 깨진다
USER node
# 모델은 node 사용자의 캐시(~/.cache)에 — 처음 쓰는 순간 멈추지 않게
# 디자인 글꼴 — Craft 앱은 시스템 글꼴 폴더만 본다
RUN .venv/bin/python engine/core/fonts.py
RUN if [ "$MODELS" = 1 ]; then .venv/bin/python engine/core/prefetch_models.py || true; fi

EXPOSE 4310 4311
WORKDIR /app/studio
CMD ["sh", "-c", "node server.mjs & exec npx vite --host 0.0.0.0 --port 4311"]
