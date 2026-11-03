#!/usr/bin/env python3
"""
2D 생성 모델 실행기 — genmodels/<이름>/model.json 하나 = 모델 하나 (코드 없이 JSON 으로 추가).

  python3 scripts/genvideo.py list                                   # 모델 · 라이선스 · 쓸 수 있는지
  python3 scripts/genvideo.py run --task i2v --prompt "…" --image a.png [--model wan22,ltx23] [--sec 4]
  python3 scripts/genvideo.py run --task t2i --prompt "…" [--size 768x1344]

task: t2i(글 → 그림) · i2v(그림 → 영상) · t2v(글 → 영상) · interp(키 그림 두 장 사이 · 만화)
--model 을 안 주면 그 task 의 모델을 order 순서로 시도하고, 쿼터 초과 · 오류면 다음 모델로 넘어간다.
i2v 는 맨 끝에 kenburns(정지 그림 한 장 — 움직임은 HyperFrames 가 줌)가 있어 요소는 반드시 나온다.

무료 · 로컬 모델만(Hugging Face Space · 켄번스). 유료 실사 영상 API 는 2026-11-03 제품 방향에서 뺐다(archive/live-action/).

무료 실행 경로: Hugging Face ZeroGPU Space (gradio_client). 토큰 없이도 되지만 하루 몇 분뿐 →
HF_TOKEN(환경 변수) 또는 ~/.cache/huggingface/token 이 있으면 무료 계정 쿼터를 쓴다.
결과는 workspace/gen-cache/<해시> 에 남겨 같은 입력이면 다시 부르지 않는다.
마지막 줄: 결과 파일 경로 (+ 쓴 모델은 stderr)
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "genmodels"
CACHE = ROOT / "workspace" / "gen-cache"


class Skip(Exception):
    """이 모델은 지금 못 씀 (쿼터 · 꺼진 Space · 입력 부족) → 다음 모델"""


def list_models() -> list[dict]:
    out = []
    for d in sorted(MODELS.iterdir()) if MODELS.exists() else []:
        p = d / "model.json"
        if p.exists():
            m = json.loads(p.read_text(encoding="utf-8"))
            if m.get("runner", {}).get("provider") == "mock" and not os.environ.get("FLUMA_GEN_MOCK_URL"):
                continue   # 시험용 가짜 공급자는 시험 때만 보인다
            out.append(m)
    return sorted(out, key=lambda m: (m.get("order", 50), m["name"]))


def model_meta(name: str) -> dict:
    p = MODELS / name / "model.json"
    if not p.exists():
        raise SystemExit(f"생성 모델 없음: {name} ({', '.join(m['name'] for m in list_models())})")
    return json.loads(p.read_text(encoding="utf-8"))


def tasks_of(m: dict) -> set[str]:
    return set(m.get("task", "").split(","))


def hf_token() -> str | None:
    t = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    p = Path.home() / ".cache" / "huggingface" / "token"
    return t or (p.read_text().strip() if p.exists() else None)


def available(m: dict) -> bool:
    r = m["runner"]
    if r["type"] == "http-async":   # 유료 API 모델은 뺐다(archive/live-action/) — 남아 있어도 쓰지 않는다
        return False
    if r["type"] == "local":
        return bool(shutil.which("ffmpeg"))
    try:
        import gradio_client  # noqa: F401
    except ImportError:
        return False
    return True


# ---------- 실행 ----------
def _even32(v: int) -> int:
    return max(256, int(v) // 32 * 32)


def _fill(args: dict, ctx: dict) -> dict:
    from gradio_client import handle_file
    out = {}
    for k, v in args.items():
        if isinstance(v, str) and v.startswith("$"):
            v = ctx.get(v[1:])
            if k in ("input_image", "image", "image2", "input_image_filepath") and v:
                v = handle_file(str(v))
        out[k] = v
    return out


def _first_file(res) -> Path:
    x = res[0] if isinstance(res, (list, tuple)) else res
    if isinstance(x, dict):
        x = x.get("video") or x.get("path") or x.get("url")
    if not x or not Path(str(x)).exists():
        raise Skip(f"결과 파일 없음: {str(res)[:200]}")
    return Path(str(x))


def _hf_space(m: dict, ctx: dict) -> Path:
    from gradio_client import Client
    r = m["runner"]
    if r["args"].get("image2") == "$image2" and not ctx.get("image2"):
        raise Skip("키 그림 두 장이 필요 (--image2)")
    try:
        c = Client(r["space"], token=hf_token(), verbose=False)
        res = c.predict(**_fill(r["args"], ctx), api_name=r["api"])
    except Exception as e:  # noqa: BLE001  — 쿼터 · 대기열 · 꺼진 Space 는 모두 다음 모델로
        msg = str(e)
        if "quota" in msg.lower():
            msg = "ZeroGPU 쿼터 초과 — HF_TOKEN(무료 계정)을 넣으면 늘어남. " + msg[:160]
        raise Skip(msg[:400]) from e
    return _first_file(res)


def _kenburns(m: dict, ctx: dict) -> Path:
    """생성 모델이 모두 실패할 때: 그림 한 장을 그대로 요소로 쓴다.
    예전에는 ffmpeg zoompan 으로 밀고 당겼는데, 정수 좌표 반올림 때문에 그림이 떨렸다(실측 2026-10-29).
    움직임(천천히 확대 · 흐름)은 scene.js 에서 HyperFrames 가 서브픽셀로 부드럽게 준다."""
    img = ctx.get("image")
    if not img:
        raise Skip("그림이 필요 (--image)")
    src = Path(img)
    out = CACHE / f"still-{ctx['key']}{src.suffix or '.png'}"
    shutil.copy2(src, out)
    return out


def price_usd(m: dict, sec: float, res: str = "720p") -> float | None:
    """추정 비용(달러). 모르면 None"""
    if (m.get("price") or {}).get("usd_per_image") is not None:   # 그림 모델은 장당
        return round(float(m["price"]["usd_per_image"]), 4)
    per = (m.get("price") or {}).get("usd_per_sec") or {}
    v = per.get(res) if isinstance(per, dict) else per
    return round(float(v) * float(sec), 4) if v is not None else None


def _fill_json(v, ctx: dict):
    """"$이름" 을 ctx 값으로 (값이 없으면 그 칸을 뺀다)"""
    if isinstance(v, str) and v.startswith("$"):
        return ctx.get(v[1:])
    if isinstance(v, dict):
        return {k: x for k, x in ((k, _fill_json(x, ctx)) for k, x in v.items()) if x is not None}
    if isinstance(v, list):
        return [x for x in (_fill_json(x, ctx) for x in v) if x is not None and x != {}]
    return v


def run_model(m: dict, ctx: dict) -> Path:
    if not available(m):
        raise Skip("준비 안 됨 (gradio_client 설치 필요: pip install gradio_client)")
    t = m["runner"]["type"]
    return _kenburns(m, ctx) if t == "local" else _hf_space(m, ctx)


def generate(task: str, prompt: str, image: str | None = None, image2: str | None = None, sec: float = 4.0,
             size: str = "576x1024", seed: int = 7, models: list[str] | None = None, log=print, extra: dict | None = None) -> tuple[Path, dict]:
    """task 에 맞는 모델을 차례로 시도. (결과 파일, 쓴 모델 meta)"""
    w, h = (int(v) for v in size.lower().split("x"))
    cands = [model_meta(n) for n in models] if models else [m for m in list_models() if task in tasks_of(m)]
    if not cands:
        raise SystemExit(f"{task} 를 하는 모델이 없습니다")
    CACHE.mkdir(parents=True, exist_ok=True)
    errors = []
    for m in cands:
        sec_m = min(float(sec), float(m.get("out", {}).get("max_sec", sec)))
        h_in = hashlib.sha1()
        for part in (m["name"], json.dumps(m["runner"], sort_keys=True), task, prompt, sec_m, w, h, seed, json.dumps(extra or {}, sort_keys=True)):
            h_in.update(str(part).encode())
        for f in (image, image2):
            if f:
                h_in.update(Path(f).read_bytes())
        key = h_in.hexdigest()[:16]
        hit = next(iter(CACHE.glob(f"{key}.*")), None)
        if hit:
            log(f"[생성] {m['name']} 캐시 사용 · {hit.name}")
            return hit, m
        ctx = {"prompt": prompt, "image": image, "image2": image2, "sec": sec_m, "seed": int(seed), "key": key,
               "w": _even32(w), "h": _even32(h), **(extra or {})}
        log(f"[생성] {m['name']} ({m['title']}) 시도 · {sec_m:g}초")
        try:
            src = run_model(m, ctx)
        except Skip as e:
            log(f"[생성] {m['name']} 건너뜀: {e}")
            errors.append(f"{m['name']}: {e}")
            continue
        dst = CACHE / f"{key}{src.suffix or '.mp4'}"
        shutil.copy2(src, dst)
        if src.name.startswith("dl-"):
            src.unlink(missing_ok=True)   # 유료 API 에서 내려받은 임시 파일
        (CACHE / f"{key}.json").write_text(json.dumps({"model": m["name"], "task": task, "prompt": prompt, "sec": sec_m, "seed": seed,
                                                       "image": image, "image2": image2}, ensure_ascii=False), encoding="utf-8")
        return dst, m
    raise SystemExit("모든 생성 모델 실패:\n  " + "\n  ".join(errors))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    ls = sp.add_parser("list")
    ls.add_argument("--json", action="store_true")
    r = sp.add_parser("run")
    r.add_argument("--task", required=True, choices=["t2i", "i2v", "t2v", "interp"])
    r.add_argument("--prompt", required=True)
    r.add_argument("--image")
    r.add_argument("--image2")
    r.add_argument("--sec", type=float, default=4.0)
    r.add_argument("--size", default="576x1024")
    r.add_argument("--seed", type=int, default=7)
    r.add_argument("--model", help="쉼표로 여러 개 (앞부터 시도)")
    a = ap.parse_args()
    if a.cmd == "list" and a.json:
        print(json.dumps({"token": bool(hf_token()), "models": [{**m, "available": available(m)} for m in list_models()]}, ensure_ascii=False))
        return
    if a.cmd == "list":
        tok = "있음" if hf_token() else "없음 (하루 몇 분만 — HF_TOKEN 권장)"
        print(f"HF 토큰: {tok}")
        for m in list_models():
            lic = m["license"]
            print(f"{m['name']:<13} {m['task']:<8} {'○' if available(m) else '×'}  {m['title']}\n"
                  f"{'':<13} 라이선스 {lic['model']} · 상업 {lic['commercial']}\n{'':<13} {m['quality']}")
        return
    path, m = generate(a.task, a.prompt, a.image, a.image2, a.sec, a.size, a.seed,
                       a.model.split(",") if a.model else None, log=lambda s: print(s, file=sys.stderr))
    print(f"[생성] 모델 {m['name']} · 라이선스 {m['license']['model']} (상업 {m['license']['commercial']})", file=sys.stderr)
    print(path)


if __name__ == "__main__":
    main()
