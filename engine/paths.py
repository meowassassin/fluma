"""Fluma 경로 — 저장소 루트 · engine 아래 묶음을 import 경로에 넣는다(모든 명령의 첫 줄이 부른다).
  ROOT   저장소 루트
  ENGINE engine/ (제작 엔진)
  DATA   data/   (실행 중 생기는 데이터: 콘티 · 제작 파일 · 음성 · 렌더 · 작업 공간)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
ROOT = ENGINE.parent
DATA = ROOT / "data"
for _d in [ENGINE, *sorted(d for d in ENGINE.iterdir() if d.is_dir() and d.name[0] not in "._")]:
    if str(_d) not in sys.path:
        sys.path.append(str(_d))

for _sp in (ROOT / ".venv" / "lib").glob("python*/site-packages"):
    if str(_sp) not in sys.path:
        sys.path.append(str(_sp))

# 저장소 글꼴을 Craft 앱이 보게 한다 — 앱들은 시스템 글꼴만 찾으므로 fontconfig 설정을 넘긴다(자식 프로세스에 물려줌)
_fc = Path(__file__).resolve().parent / "assets" / "fontconfig.conf"
if _fc.exists():
    os.environ.setdefault("FONTCONFIG_FILE", str(_fc))

# 저장소 .venv 로 다시 실행 — 에이전트 · 사람이 `python3 engine/…` 로 부르면 시스템 파이썬이라 .venv 에만 있는 패키지(rapidocr · playwright …)가 없어
# 스타일 분석 · 터미널 녹화 · 화풍 분류가 조용히 실패했다(2026-11-11). 명령으로 직접 실행된 경우만(라이브러리 import · 블렌더 내장 파이썬 · 이미 .venv 는 건드리지 않음).
def _reexec_in_venv() -> None:
    if os.environ.get("FLUMA_NO_VENV_REEXEC") or getattr(sys, "frozen", False):
        return
    vpy = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not vpy.exists() or Path(sys.prefix).resolve() == (ROOT / ".venv").resolve():
        return
    exe = Path(sys.executable).name.lower()
    if not exe.startswith("python") or "blender" in str(sys.executable).lower():
        return
    main = sys.modules.get("__main__")
    mf = Path(getattr(main, "__file__", "") or "").resolve()
    if not mf.is_file() or ENGINE not in mf.parents:
        return
    os.environ["FLUMA_NO_VENV_REEXEC"] = "1"
    os.execv(str(vpy), [str(vpy), str(mf), *sys.argv[1:]])


_reexec_in_venv()


# 하이픈으로 시작하는 유튜브 id(예: -xSh1FIbKa4)를 argparse 가 옵션으로 읽어 분석이 실패했다(2026-11-11) —
# 11자 id 모양이면 '--' 뒤로 옮겨 위치 인자로 받게 한다(이미 '--' 가 있으면 건드리지 않음)
def _dash_ids() -> None:
    import re as _re
    av = sys.argv[1:]
    if "--" in av:
        return
    ids = [x for x in av if _re.fullmatch(r"-[A-Za-z0-9_-]{10}", x)]
    if ids:
        sys.argv[1:] = [x for x in av if x not in ids] + ["--"] + ids


_dash_ids()


# 블렌더 내장 파이썬이나 독립 빌드 파이썬은 OpenSSL 기본 CA 경로가 /dev/null 로 컴파일되어 있어
# HTTPS 통신(GitHub 릴리스 · 모델 다운로드 등) 시 SSL: CERTIFICATE_VERIFY_FAILED 오류가 난다.
# certifi 또는 시스템 CA 인증서 번들이 있으면 SSL_CERT_FILE 및 기본 SSL 컨텍스트로 지정한다.
def _ensure_ca_certs() -> None:
    ca: str | None = None
    if os.environ.get("SSL_CERT_FILE") and Path(os.environ["SSL_CERT_FILE"]).is_file():
        ca = os.environ["SSL_CERT_FILE"]
    else:
        try:
            import certifi  # noqa: F401
            cand = certifi.where()
            if Path(cand).is_file():
                ca = cand
        except Exception:
            pass
        if not ca:
            for p in (
                "/etc/ssl/certs/ca-certificates.crt",
                "/etc/pki/tls/certs/ca-bundle.crt",
                "/etc/ssl/ca-bundle.pem",
                "/etc/ssl/cert.pem",
            ):
                if Path(p).is_file():
                    ca = p
                    break
        if ca:
            os.environ["SSL_CERT_FILE"] = ca

    if ca:
        try:
            import ssl
            ctx = ssl.create_default_context(cafile=ca)
            ssl._create_default_https_context = lambda: ctx
        except Exception:
            pass


_ensure_ca_certs()

