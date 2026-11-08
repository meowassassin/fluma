# Fluma 시작(Windows · PowerShell) — 사용: powershell -ExecutionPolicy Bypass -File docker\start.ps1 [-Build]
# Windows 의 Docker Desktop(WSL 2)은 Intel · AMD GPU 를 컨테이너에 넘기지 못한다 → 3D 렌더는 CPU(Cycles)로(느리지만 같은 결과).
# GPU 로 렌더하려면 Docker 없이 바로 설치(QUICKSTART '바로 설치')를 쓰면 Windows 의 GPU 를 그대로 쓴다.
param([switch]$Build)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if ($Build) { docker compose build } else { docker compose pull; if ($LASTEXITCODE -ne 0) { Write-Host "[fluma] 미리 빌드한 이미지를 못 받았습니다 - 직접 빌드: docker\start.ps1 -Build" } }
docker compose up -d
Write-Host "[fluma] http://localhost:4311   (멈추기: cd docker; docker compose down)"
