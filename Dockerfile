# Fluma — 컨테이너로 돌리기(Linux · macOS · Windows 공통). 기본은 가벼운 시작(lite).
#   docker compose up --build            → http://localhost:4311
#   PROFILE=analysis docker compose build   레퍼런스 분석(받아쓰기 · OCR · 화면 분류)까지
FROM node:22-bookworm

ARG PROFILE=lite
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 FLUMA_HOST=0.0.0.0
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv python3-pip ffmpeg fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
# .venv · Chromium(+ 시스템 의존성) · npm 패키지
RUN python3 -m venv .venv \
    && .venv/bin/pip install --no-cache-dir -r scripts/$( [ "$PROFILE" = lite ] && echo requirements.txt || echo requirements-$PROFILE.txt ) \
    && .venv/bin/python -m playwright install --with-deps chromium \
    && npm --prefix web ci --no-audit --no-fund \
    && npm --prefix engines/hyperframes install --no-audit --no-fund

EXPOSE 4310 4311
WORKDIR /app/web
CMD ["sh", "-c", "node server.mjs & exec npx vite --host 0.0.0.0 --port 4311"]
