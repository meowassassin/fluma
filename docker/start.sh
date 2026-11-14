#!/usr/bin/env sh
# Fluma 시작(Linux · macOS) — 운영체제 · 하드웨어를 스스로 맞춘다. 사용: sh docker/start.sh [--build]
#  - Linux 에 GPU 장치(/dev/dri)가 있으면 연결한다(그래픽 가속) — 설정 파일을 고칠 필요 없음
#  - 내 사용자 번호(uid · gid)를 넘겨 로그인 파일(~/.claude · ~/.codex) 소유자가 바뀌지 않게
#  - --build: 미리 빌드한 이미지 대신 직접 빌드(약 15분)
set -e
cd "$(dirname "$0")"
export FLUMA_UID="${FLUMA_UID:-$(id -u)}" FLUMA_GID="${FLUMA_GID:-$(id -g)}"
FILES="-f docker-compose.yml"
if [ "$(uname -s)" = "Linux" ] && [ -e /dev/dri/renderD128 ]; then
  export FLUMA_RENDER_GID="${FLUMA_RENDER_GID:-$(getent group render 2>/dev/null | cut -d: -f3 || stat -c %g /dev/dri/renderD128)}"
  FILES="$FILES -f docker-compose.gpu.yml"
  echo "[fluma] GPU 연결(/dev/dri, render 그룹 $FLUMA_RENDER_GID)"
else
  echo "[fluma] GPU 장치 없음 — CPU 로 돕니다"
fi
if [ "$1" = "--build" ]; then
  docker compose $FILES build
else
  docker compose $FILES pull || echo "[fluma] 미리 빌드한 이미지를 못 받았습니다 — 직접 빌드: sh docker/start.sh --build"
fi
docker compose $FILES up -d
echo "[fluma] http://localhost:4311   (멈추기: cd docker && docker compose down)"
