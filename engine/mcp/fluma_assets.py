#!/usr/bin/env python3
"""재료 미리 만들기(작업) — plan_submit 이 대본 확정과 함께 띄운다. 에이전트가 장면을 설계하는 동안 캡처 · 아이콘 · 형태를 만든다(2026-11-25).

  python3 engine/mcp/fluma_assets.py <영상 id> <assets.json>
assets.json: [{"kind": "web", "name": "rfc", "plan": {webrec 계획}} ·
              {"kind": "term", "name": "curl", "cmd": ["curl", "-sI", "https://…"], "prompt": "$ curl -sI …", "mark": ["^HTTP"], "typed": true} ·
              {"kind": "icon", "names": ["python", "go"]} ·
              {"kind": "form", "name": "teapot", "form": {형태 JSON}, "style": "cel"}]
결과: data/workspace/tmp/<id>/assets.json — 이름마다 ok · 쓸 경로(설계 src) · 미리보기 · 오류
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
PY = sys.executable


def _run(args: list[str], timeout: int = 300) -> tuple[bool, str]:
    try:
        r = subprocess.run([PY, *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"{timeout}초 초과"
    out = (r.stdout or "") + (r.stderr or "")
    err = next((ln[6:] for ln in out.splitlines() if ln.startswith("error=")), "")
    return r.returncode == 0, (err or out.strip().splitlines()[-1] if out.strip() else "")[:300]


def preview(p: Path, sid: str) -> str | None:
    """에이전트가 볼 작은 그림(긴 변 640) — 원본 크기 그림을 Read 하면 캐시 쓰기 비용이 크다(2026-11-25: 1440×1800 캡처 10장)"""
    try:
        from PIL import Image
        out = ROOT / "data" / "workspace" / "tmp" / sid / "preview" / f"{p.parent.name}-{p.stem}.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(p) as im:
            im = im.convert("RGB")
            im.thumbnail((640, 640))
            im.save(out, "JPEG", quality=80)
        return str(out.relative_to(ROOT))
    except Exception:  # noqa: BLE001
        return None


def one(sid: str, a: dict) -> list[dict]:
    comp = ROOT / "data" / "compositions" / sid
    el = ROOT / "data" / "public" / "elements" / sid
    k = a.get("kind")
    if k == "web":
        name = a["name"]
        f = comp / "web" / f"{name}.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(a["plan"], ensure_ascii=False), "utf-8")
        ok, msg = _run(["engine/capture/webrec.py", "run", sid, str(f.relative_to(ROOT)), "--name", name], 300)
        shots = sorted((el / name).glob("s*.png"))
        return [{"name": name, "ok": ok and bool(shots), "src": f"capture:{name}", "shots": [f"capture:{name}/{s.name}" for s in shots],
                 "preview": preview(shots[-1], sid) if shots else None, **({} if ok else {"error": msg})}]
    if k == "term":
        name = a["name"]
        args = ["engine/capture/termrec.py", "capture", sid, name] + (["--prompt", a["prompt"]] if a.get("prompt") else [])
        for d in a.get("drop") or []:
            args += ["--drop", d]
        ok, msg = _run(args + ["--", *a["cmd"]], 120)
        if ok:
            ra = ["engine/capture/termrec.py", "render", sid, name] + (["--typed"] if a.get("typed", True) else []) + ["--hold", str(a.get("hold", 2.5))]
            for m in a.get("mark") or []:
                ra += ["--mark", m]
            ok, msg = _run(ra, 300)
        shots = sorted((el / name).glob("*.png"))
        return [{"name": name, "ok": ok, "src": f"capture:{name}", "preview": preview(shots[-1], sid) if shots else None,
                 "note": "터미널 녹화 — 설계에서 kind=capture 로 쓰면 마지막 화면, 움직임은 kind=code 로", **({} if ok else {"error": msg})}]
    if k == "icon":
        ok, msg = _run(["engine/capture/icons.py", "fetch", sid, *a["names"]], 120)
        return [{"name": n, "ok": (comp / f"{n}.svg").exists(), "src": f"{n}.svg", **({} if ok else {"error": msg})} for n in a["names"]]
    if k == "form":
        name = a["name"]
        f = comp / "forms" / f"{name}.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(a["form"], ensure_ascii=False), "utf-8")
        out = comp / "forms" / f"{name}.png"
        ok, msg = _run(["engine/craft/form_cli.py", "render", str(f.relative_to(ROOT)), "--out", str(out.relative_to(ROOT)),
                        "--style", a.get("style", "cel"), "--res", "1080"], 600)
        return [{"name": name, "ok": ok and out.exists(), "src": f"forms/{name}.png", "preview": preview(out, sid) if out.exists() else None,
                 **({} if ok else {"error": msg})}]
    return [{"name": str(a.get("name")), "ok": False, "error": f"모르는 kind '{k}' — web · term · icon · form"}]


def main() -> int:
    sid, spec = sys.argv[1], Path(sys.argv[2])
    assets = json.loads(spec.read_text("utf-8"))
    res_p = ROOT / "data" / "workspace" / "tmp" / sid / "assets.json"
    res_p.parent.mkdir(parents=True, exist_ok=True)
    out = []
    t0 = time.time()
    for i, a in enumerate(assets, 1):
        print(f"[재료 {i}/{len(assets)}] {a.get('kind')} {a.get('name') or a.get('names')}", flush=True)
        try:
            out += one(sid, a)
        except Exception as e:  # noqa: BLE001 — 하나가 깨져도 나머지는 만든다
            out.append({"name": str(a.get("name")), "ok": False, "error": f"{type(e).__name__}: {e}"[:300]})
        res_p.write_text(json.dumps({"done": False, "items": out}, ensure_ascii=False, indent=1), "utf-8")
    res_p.write_text(json.dumps({"done": True, "secs": round(time.time() - t0, 1), "items": out}, ensure_ascii=False, indent=1), "utf-8")
    bad = [x for x in out if not x.get("ok")]
    print("FLUMA_RESULT\nstatus=ok\n" + f"made={len(out) - len(bad)}\nfailed={len(bad)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
