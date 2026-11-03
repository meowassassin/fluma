#!/usr/bin/env python3
"""'AI 티' 화면 검사 — scene.js 글자가 아니라 **실제로 그려진 화면**을 잰다(부품 속 효과까지).

  python3 scripts/look_check.py storyboards/<id>.json            # 장면마다 3시점(등장 · 가운데 · 끝)
  python3 scripts/look_check.py storyboards/<id>.json --json

왜: 2026-11-02 Fluma 소개 데모가 "AI 티가 확 난다"는 평가를 받았는데 lint 의 ai_tells(scene.js 글자 검사)는 0건이었다.
효과가 부품(K.pro 무대 · 카드 · 글자) 안에 있어 글자 검사로는 보이지 않았다.
재는 것(보이는 요소만 · 화면의 0.2% 이상)
  · 기울기 · 원근: transform 의 회전 각 > 1.5° · matrix3d(원근 카드)
  · 흐림: filter blur > 0.5px (등장할 때 흐렸다 또렷해지는 연출 포함)
  · 그라데이션: background-image 의 linear/radial/conic-gradient(빛번짐 무대 · 비네트 · 그라데이션 막대)
  · 빛: 퍼짐 40px 이상 색 있는 box-shadow · 퍼짐 있는 text-shadow
  · 같은 틀: 장면마다 큰 글자(60px↑) 제목이 같은 자리(가운데 위)에 있는 비율
판정: 갈래가 2개 이상 나오거나, 한 갈래가 장면의 절반 이상에서 나오면 실패. 레퍼런스(채널 카드)가 그런 화면이면 예외로 둘 수 있다(--allow blur,gradient …).
결과: workspace/render/<id>/look-check.json (lint L18 이 읽는다)
"""
from __future__ import annotations

import argparse
import hashlib

import numpy as np
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engines import ROOT, adapter, make_job  # noqa: E402

MEASURE = r"""
() => {
  const W = 1080, H = 1920, AREA = W * H * 0.002;
  const out = { tilt: [], blur: [], gradient: [], glow: [], heads: [], subs: null };
  // 자막(K.talk.subs · 콘티 자막): 보이는 글자가 있으면 위치 · 글자 크기
  for (const s of document.querySelectorAll('[data-name^="자막"], .k-cap')) {
    const sp = s.querySelector("span") || s; const txt = (sp.textContent || "").trim();
    if (!txt || !vis(sp)) continue;
    const r = sp.getBoundingClientRect(); out.subs = { y: (r.top + r.bottom) / 2 / H, fs: parseFloat(getComputedStyle(sp).fontSize) / H }; break;
  }
  const vis = (el) => {
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.display === "none" || cs.visibility === "hidden" || parseFloat(cs.opacity || "1") < 0.15) return false;
    }
    return true;
  };
  const name = (el) => { const p = el.closest("[data-name]"); return p ? p.dataset.name : (el.dataset.part || el.className || el.tagName).toString().slice(0, 40); };
  for (const el of document.querySelectorAll("#root *")) {
    const r = el.getBoundingClientRect();
    const area = Math.max(0, Math.min(W, r.right) - Math.max(0, r.left)) * Math.max(0, Math.min(H, r.bottom) - Math.max(0, r.top));
    if (area < AREA || !vis(el)) continue;
    const cs = getComputedStyle(el), nm = name(el);
    const t = cs.transform;
    if (t && t !== "none") {
      if (t.startsWith("matrix3d")) out.tilt.push({ name: nm, kind: "원근(3D)" });
      else { const m = t.match(/matrix\(([^)]+)\)/); if (m) { const [a, b] = m[1].split(",").map(Number); const deg = Math.abs(Math.atan2(b, a) * 180 / Math.PI); if (deg > 1.5) out.tilt.push({ name: nm, kind: `회전 ${deg.toFixed(1)}°` }); } }
    }
    const bm = /blur\(([\d.]+)px\)/.exec(cs.filter || ""); if (bm && parseFloat(bm[1]) > 0.5) out.blur.push({ name: nm, px: +parseFloat(bm[1]).toFixed(1) });
    if (/gradient\(/.test(cs.backgroundImage || "")) out.gradient.push({ name: nm, kind: /radial/.test(cs.backgroundImage) ? "방사형(빛번짐 · 비네트)" : "선형" });
    for (const sh of (cs.boxShadow || "").split(/,(?![^(]*\))/)) {
      const nums = (sh.match(/-?[\d.]+px/g) || []).map(parseFloat); const col = /rgba?\(([^)]+)\)/.exec(sh);
      if (nums.length >= 3 && nums[2] >= 40 && col) { const c = col[1].split(",").map(Number); const colored = Math.max(c[0], c[1], c[2]) - Math.min(c[0], c[1], c[2]) > 40; if (colored && (c[3] === undefined || c[3] > 0.15)) out.glow.push({ name: nm, kind: `색 그림자 ${nums[2]}px` }); }
    }
    if (cs.textShadow && cs.textShadow !== "none" && /\d+px\s+\d+px\s+([1-9]\d*)px/.test(cs.textShadow)) out.glow.push({ name: nm, kind: "글자 빛" });
    // 큰 제목 자리(같은 틀 판정)
    const fs = parseFloat(cs.fontSize || "0");
    if (fs >= 60 && [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) out.heads.push({ y: Math.round(r.top), cx: Math.round((r.left + r.right) / 2), fs });
  }
  return out;
}
"""

KINDS = {"tilt": "기울기 · 원근 카드", "blur": "흐림(등장할 때 흐렸다 또렷해짐)", "gradient": "그라데이션(빛번짐 무대 · 비네트 · 그라데이션 칠)", "glow": "색 빛(글로우)"}
FIX = {"tilt": "카드는 평평하게, 회전 없이 — 원근 · 반사광은 레퍼런스가 그럴 때만",
       "blur": "등장은 컷(바로 나타남) 또는 짧은 이동만 — 흐림 등장은 빼기",
       "gradient": "단색 바탕(또는 실사 · 실제 화면) — 방사형 빛번짐 · 비네트 · 그라데이션 막대 빼기",
       "glow": "그림자는 짧고 검게 — 색 글로우 빼기"}


def run(sb_path: Path, allow: set[str]) -> dict:
    job = make_job(sb_path)
    if job.engine != "hyperframes":
        sys.exit(f"화면 검사는 hyperframes 컴포지션용입니다 (이 콘티: {job.engine})")
    adapter("hyperframes").build(job)
    from playwright.sync_api import sync_playwright
    per_scene = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--allow-file-access-from-files"])
        page = b.new_page(viewport={"width": 1080, "height": 1920})
        page.goto((job.work / "index.html").as_uri())
        page.wait_for_function("typeof window.__sfSeek === 'function'", timeout=15000)
        page.evaluate("document.fonts.ready")
        for i, sc in enumerate(job.scenes):
            found = {k: [] for k in KINDS}
            heads = []
            subs = []
            for f in (0.12, 0.5, 0.92):
                t = round(sc["start"] + f * sc["sec"], 2)
                page.evaluate(f"window.__sfSeek({t})"); page.wait_for_timeout(80)
                m = page.evaluate(MEASURE)
                for k in KINDS:
                    found[k] += m[k]
                subs.append(m["subs"])
                if f == 0.5:
                    heads = m["heads"]
            per_scene.append({"scene": i, "found": {k: sorted({json.dumps(x, ensure_ascii=False) for x in v}) for k, v in found.items()}, "heads": heads, "subs": subs})
        b.close()
    n = len(per_scene)
    cats = {}
    for k in KINDS:
        if k in allow:
            continue
        sc_hit = [s["scene"] for s in per_scene if s["found"][k]]
        if sc_hit:
            ex = sorted({json.loads(x)["name"] for s in per_scene for x in s["found"][k]})[:4]
            cats[k] = {"scenes": sc_hit, "examples": ex}
    # 같은 틀: 장면마다 가장 위 큰 제목의 자리
    tops = [min(s["heads"], key=lambda h: h["y"]) for s in per_scene if s["heads"]]
    same = 0
    if len(tops) >= 3:
        ref = sorted(h["y"] for h in tops)[len(tops) // 2]
        same = sum(1 for h in tops if abs(h["y"] - ref) <= 60 and abs(h["cx"] - 540) <= 80)
    template = same >= max(3, round(n * 0.7))
    if template and "template" not in allow:
        cats["template"] = {"scenes": list(range(n)), "examples": [f"{same}/{n} 장면이 같은 자리(가운데 위) 큰 제목"]}
    # 형식 프리셋과의 거리: 자막을 쓰는 형식인지 · 자막 위치 · 글자 크기(사람이 편집한 실제 쇼츠의 숫자)
    pr = (job.sb.get("preset") or {}).get("layout", {}).get("captions") or {}
    if pr and "preset" not in allow:
        seen = [x for s in per_scene for x in s["subs"]]
        on = [x for x in seen if x]
        share = len(on) / max(1, len(seen))
        probs = []
        if (pr.get("share") or 0) < 0.2 and share > 0.3:
            probs.append(f"이 형식(프리셋 {job.sb['preset'].get('name')})은 나레이션 자막을 거의 안 쓰는데 시간의 {int(share * 100)}%에 자막")
        elif (pr.get("share") or 0) >= 0.2 and on and pr.get("y") is not None:
            y = float(np.median([x["y"] for x in on])); fs = float(np.median([x["fs"] for x in on]))
            if abs(y - pr["y"]) > 0.07:
                probs.append(f"자막 위치 y {y:.2f} — 프리셋 {pr['y']:.2f}")
            if pr.get("height") and not (0.6 <= fs / (pr["height"] * 0.95) <= 1.6):
                probs.append(f"자막 글자 크기 {fs * 1920:.0f}px — 프리셋 약 {pr['height'] * 1920 * 0.95:.0f}px")
        if probs:
            cats["preset"] = {"scenes": list(range(n)), "examples": probs}
    many = [k for k, v in cats.items() if len(v["scenes"]) >= max(1, n / 2)]
    fail = len(cats) >= 2 or bool(many)
    return {"ok": not fail, "scenes": n, "categories": cats, "allow": sorted(allow),
            "scene_js_sha": hashlib.sha1((ROOT / "compositions" / job.sb["id"] / "scene.js").read_bytes()).hexdigest()[:12]
            if (ROOT / "compositions" / job.sb["id"] / "scene.js").exists() else None}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("storyboard")
    ap.add_argument("--allow", default="", help="레퍼런스가 그런 화면일 때 허용할 갈래(쉼표): tilt,blur,gradient,glow,template")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    sp = Path(a.storyboard)
    sb = json.loads(sp.read_text(encoding="utf-8"))
    res = run(sp, {x.strip() for x in a.allow.split(",") if x.strip()})
    d = ROOT / "workspace" / "render" / sb["id"]; d.mkdir(parents=True, exist_ok=True)
    (d / "look-check.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        for k, v in res["categories"].items():
            label = KINDS.get(k, {"template": "모든 장면이 같은 틀", "preset": "형식 프리셋과 다른 배치"}.get(k, k))
            print(f"✗ {label} — 장면 {', '.join(str(s + 1) for s in v['scenes'])} · 예: {', '.join(v['examples'])}")
            print(f"   → {FIX.get(k, {'preset': '자막은 K.talk.subs(프리셋 숫자)로 — 위치 · 크기를 손으로 정하지 않기'}.get(k, '장면마다 화면 구성을 바꾸기(제목 위치 · 크기 · 실제 화면 · 컷)'))}")
        print(f"'AI 티' 화면 검사 {'통과' if res['ok'] else '실패'} · 갈래 {len(res['categories'])}개 · {res['scenes']}장면")
    sys.exit(0 if res["ok"] else 1)


if __name__ == "__main__":
    main()
