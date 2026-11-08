"""스크립트 결과 규약 — 에이전트가 출력을 읽고 짐작하지 않게, 오래 걸리는 스크립트는 같은 형식으로 끝난다.

종료 코드
  0   성공 · FLUMA_RESULT 블록에 결과(file · media · …)
  11  아직 도는 중(서버 작업) — 같은 명령을 다시 부르면 그 작업에 붙어 이어서 기다린다. 폴링(sleep · ls · tail)하지 않는다
  10  사용자 입력이 필요 — FLUMA_NEEDS_INPUT 블록의 needs(무엇) · how(어디서). 에이전트는 한 번에 묶어 한 번만 묻는다
  1   오류 — FLUMA_ERROR 블록의 stage(어느 단계) · error(짧은 이유) · log(있으면). 에이전트는 이 짧은 이유만 읽고 고쳐 한 번 다시
출력(맨 끝, 한 줄에 key=value — 값의 줄바꿈은 ⏎ 로)
  FLUMA_RESULT
  status=ok
  file=data/out/<id>-….mp4
  media=data/out/<id>-….mp4 | 설명            ← 채팅에 붙일 media 줄(여러 개 가능)
같은 내용을 data/workspace/results/<스크립트>-latest.json 에도 남긴다 — 출력이 잘려도 이 파일을 한 번 읽으면 된다.

  from result import ok, needs_input, fail
  ok("render", file="data/out/x.mp4", media=["data/out/x.mp4 | 초안"])        # 종료 코드 0 으로 끝냄
  needs_input("stock", needs=["PEXELS_API_KEY"], how="설정 → API 키")  # 10
  fail("render", stage="effectcraft", error="…")                       # 1
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
RESULTS = ROOT / "data" / "workspace" / "results"
OK, ERROR, NEEDS_INPUT, RUNNING = 0, 1, 10, 11


def _flat(v) -> str:
    return str(v).replace("\r", "").replace("\n", "⏎")


def emit(script: str, status: str, head: str, fields: dict) -> None:
    """결과 블록을 출력하고 결과 파일을 쓴다(끝내지는 않음)"""
    rec = {"script": script, "status": status, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), **fields}
    try:
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / f"{script}-latest.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), "utf-8")
    except OSError:
        pass
    out = [head, f"status={status}"]
    for k, v in fields.items():
        for item in (v if isinstance(v, (list, tuple)) else [v]):
            if item is None or item == "":
                continue
            out.append(f"{k}={_flat(item)}")
    out.append(f"result_file={(RESULTS / f'{script}-latest.json').relative_to(ROOT)}")
    sys.stdout.flush()
    print("\n" + "\n".join(out), flush=True)


def ok(script: str, **fields) -> None:
    emit(script, "ok", "FLUMA_RESULT", fields)
    sys.exit(OK)


def needs_input(script: str, needs: list[str], how: str = "", **fields) -> None:
    emit(script, "needs_input", "FLUMA_NEEDS_INPUT", {"needs": needs, "how": how, **fields})
    sys.exit(NEEDS_INPUT)


def running(script: str, **fields) -> None:
    emit(script, "running", "FLUMA_RUNNING", fields)
    sys.exit(RUNNING)


def fail(script: str, stage: str, error: str, **fields) -> None:
    emit(script, "error", "FLUMA_ERROR", {"stage": stage, "error": str(error)[-400:], **fields})
    sys.exit(ERROR)


def run_main(script: str, fn) -> None:
    """main 을 감싼다: 문장으로 끝낸 sys.exit("…") · 잡히지 않은 예외도 FLUMA_ERROR 블록(종료 코드 1)으로.
    정수 종료 코드(0 · 10 · 1)는 그대로 둔다"""
    try:
        r = fn()
    except SystemExit as e:
        if e.code is None or isinstance(e.code, int):
            raise
        print(str(e.code), file=sys.stderr)
        fail(script, stage="main", error=str(e.code))
    except KeyboardInterrupt:
        raise
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        fail(script, stage="main", error=f"{type(e).__name__}: {e}")
    if isinstance(r, int) and r:
        sys.exit(r)
