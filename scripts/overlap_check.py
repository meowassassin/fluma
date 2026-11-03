#!/usr/bin/env python3
"""화면 검사(겹침 · 화면 밖 잘림 · 글자 넘침 · 못 찾은 음성 신호): 컴포지션(HyperFrames Composed)에서 레이어 요소 · 영상 · 그림이 글자 · 자막 · 다른 부품과 겹치는지 실제 화면으로 잰다.

  python3 scripts/overlap_check.py storyboards/<id>.json                # 장면마다 3시점(들어옴 · 가운데 · 끝)
  python3 scripts/overlap_check.py storyboards/<id>.json --at 1.2 4.5   # 정한 시각만
  python3 scripts/overlap_check.py storyboards/<id>.json --json

재는 법
  · 글자: 보이는 글자 노드의 실제 줄 상자 (Range.getClientRects) — 투명도 · visibility 를 따라감
  · 레이어 요소(K.seq elements/…): 상자 전체가 아니라 meta.json 의 bbox(알파가 있는 영역)를 object-fit 에 맞춰 환산한 '보이는 부분'
  · 자막(K.captions): 지금 말하지 않아도 자막 띠 전체를 예약 구역으로 봄
  · 안전 영역: 위 safe_top · 아래 safe_bottom · 오른쪽 버튼 줄(RAIL) — 글자 · 부품 · 요소가 들어가면 문제(플랫폼 UI 에 가림)
결과
  · 시각마다 겹침 목록(누구 ↔ 누구, 겹친 넓이 %), 요소를 옮길 빈 자리 제안(x, y, w, h — 요소 비율 유지)
  · workspace/tmp/overlap/<id>-<초>.png: 화면 위에 빨강(요소) · 노랑(글자) · 파랑(자막 띠) · 초록(제안 자리) 상자 → Read 로 확인
  · 문제가 있으면 종료 코드 1
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engines import ROOT, adapter, make_job  # noqa: E402

MEASURE = r"""
() => {
  const W = 1080, H = 1920;
  const vis = (el) => {
    if (!el.isConnected) return 0;
    if (el.checkVisibility && !el.checkVisibility({ opacityProperty: true, visibilityProperty: true, contentVisibilityAuto: true })) return 0;
    let a = 1;
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) { const cs = getComputedStyle(n); if (cs.display === "none" || cs.visibility === "hidden") return 0; a *= parseFloat(cs.opacity || "1"); }
    return a;
  };
  const clip = (r) => { const x0 = Math.max(0, r.left), y0 = Math.max(0, r.top), x1 = Math.min(W, r.right), y1 = Math.min(H, r.bottom); return x1 - x0 > 2 && y1 - y0 > 2 ? [x0, y0, x1, y1] : null; };
  const owner = (n) => { const p = n.closest && n.closest("[data-part]"); return p ? (p.dataset.name || p.dataset.part) : (n.className && typeof n.className === "string" ? n.className.split(" ")[0] : n.tagName.toLowerCase()); };
  const out = { texts: [], seqs: [], parts: [], caps: [], offs: [], overflow: [], cues: window.__FLUMA_MISSING_CUES || [] };
  // 화면 밖으로 잘린 글자 · 상자 넘친 글자 (장면 전환 중 · 의도한 등장 움직임은 제외하려고 보이는 것만)
  const seen = new Set();
  for (const el of document.querySelectorAll("#root *")) {
    if (el.closest("[data-seq]") || el.closest(".k-cap") || el.classList.contains("k-scene") || el.classList.contains("k-bg")) continue;
    if (!el.childNodes.length || ![...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) continue;
    const a = vis(el); if (a < 0.6) continue;
    const r = el.getBoundingClientRect(); if (r.width < 4 || r.height < 4) continue;
    const name = owner(el), txt = el.textContent.trim().slice(0, 24);
    const cut = Math.max(0, -r.left, r.right - W, -r.top, r.bottom - H);
    if (cut > 6 && !seen.has("o" + name + txt)) { seen.add("o" + name + txt); out.offs.push({ name, text: txt, cut: Math.round(cut) }); }
    const cs = getComputedStyle(el);
    if (cs.whiteSpace === "nowrap" && el.scrollWidth > el.clientWidth + 4 && cs.overflow !== "visible" && !seen.has("w" + name + txt)) { seen.add("w" + name + txt); out.overflow.push({ name, text: txt }); }
  }
  // 글자
  const tw = document.createTreeWalker(document.getElementById("root") || document.body, NodeFilter.SHOW_TEXT);
  for (let t = tw.nextNode(); t; t = tw.nextNode()) {
    const s = t.textContent.trim(); if (!s) continue;
    const el = t.parentElement; if (!el || el.closest("[data-seq]") || el.closest(".k-cap")) continue;
    const a = vis(el); if (a < 0.15) continue;
    const r = document.createRange(); r.selectNodeContents(t);
    const pin = el.closest("[data-pin]");
    for (const q of r.getClientRects()) { const b = clip(q); if (b) out.texts.push({ name: pin ? "고정 라벨" : owner(el), text: s.slice(0, 24), box: b, alpha: +a.toFixed(2), pin: pin ? pin.dataset.pin : null }); }
  }
  // 레이어 요소 · 영상 연속 이미지
  for (const e of document.querySelectorAll("[data-seq]")) {
    const a = vis(e); if (a < 0.15) continue;
    const img = e.querySelector(":scope > canvas") || e.querySelector("img"); const r = e.getBoundingClientRect();
    const meta = (window.SF_SEQ || {})[e.dataset.seq] || {};
    let box = clip(r);
    if (box && img && (img.naturalWidth || img.width) && meta.bbox) {
      const fit = getComputedStyle(img).objectFit || "contain";
      const iw = img.naturalWidth || img.width, ih = img.naturalHeight || img.height, ew = r.width, eh = r.height;
      const k = fit === "cover" ? Math.max(ew / iw, eh / ih) : fit === "fill" ? null : Math.min(ew / iw, eh / ih);
      const kx = k ?? ew / iw, ky = k ?? eh / ih, ox = r.left + (ew - iw * kx) / 2, oy = r.top + (eh - ih * ky) / 2;
      const [bx0, by0, bx1, by1] = meta.bbox;
      box = clip({ left: Math.max(r.left, ox + bx0 * kx), top: Math.max(r.top, oy + by0 * ky), right: Math.min(r.right, ox + bx1 * kx), bottom: Math.min(r.bottom, oy + by1 * ky) });
    }
    if (box) out.seqs.push({ name: e.dataset.name || e.dataset.seq.split("/").pop(), src: e.dataset.seq, box, under: !!e.dataset.under, alpha: +a.toFixed(2), aspect: r.width / Math.max(1, r.height), el: [r.left, r.top, r.width, r.height].map(Math.round) });
  }
  // 그 밖의 2D 부품 (배경 · 무대 · 효과 제외)
  for (const e of document.querySelectorAll("[data-part]")) {
    const p = e.dataset.part; if (["bg", "seq", "stage", "particles", "rule"].includes(p) || e.dataset.seq) continue;
    if (e.parentElement && e.parentElement.closest("[data-part]")) continue;
    const a = vis(e); if (a < 0.15) continue;
    const b = clip(e.getBoundingClientRect()); if (b && (b[2] - b[0]) * (b[3] - b[1]) < W * H * 0.6) out.parts.push({ name: e.dataset.name || p, part: p, box: b });
  }
  // 자막 띠 (말하지 않는 순간에도 예약)
  for (const c of document.querySelectorAll(".k-cap")) {
    const r = c.getBoundingClientRect(); const fs = parseFloat(getComputedStyle(c).fontSize) || 78;
    out.caps.push({ name: "자막", box: [r.left, r.top - 10, r.right, r.top + Math.max(r.height, fs * 1.2 * 2) + 10].map(Math.round) });
  }
  return out;
}
"""


# 쇼츠 오른쪽 버튼 줄(좋아요 · 댓글 · 공유 · 소리): x 936 오른쪽 · y 880 아래
RAIL = [936, 880, 1080, 1920]


def area(b):
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def inter(a, b):
    return [max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])]


def free_spot(blocked: list, aspect: float, safe: tuple, W=1080, H=1920, step=20, margin=24):
    """막힌 상자(글자 · 자막 띠 · 부품)를 피해 안전 영역 안에 놓을 수 있는 가장 큰 자리 (요소 비율 유지).
    같은 크기면 화면 가운데(540, 900)에 가까운 곳. → (x, y, w, h) 또는 None"""
    top, bottom, pad = safe
    bl = [(b[0] - margin, b[1] - margin, b[2] + margin, b[3] + margin) for b in blocked]
    x_min, x_max, y_min, y_max = pad / 2, W - pad / 2, top, H - bottom
    for w in range(int(min(x_max - x_min, (y_max - y_min) * aspect)) // step * step, 199, -step):
        h = w / aspect
        best = None
        for y in range(int(y_min), int(y_max - h) + 1, step):
            for x in range(int(x_min), int(x_max - w) + 1, step):
                if any(x < c and x + w > a_ and y < d and y + h > b_ for a_, b_, c, d in bl):
                    continue
                dist = (x + w / 2 - W / 2) ** 2 + (y + h / 2 - 900) ** 2
                if not best or dist < best[0]:
                    best = (dist, x, y)
        if best:
            return (best[1], best[2], w, round(h))
    return None


def check(page, t, job, shots: Path):
    page.evaluate(f"window.__sfSeek({t})")
    page.wait_for_timeout(120)
    page.evaluate("Promise.all([...document.querySelectorAll('[data-seq] img')].map(i => i.complete ? 0 : new Promise(r => { i.onload = i.onerror = r; })))")
    m = page.evaluate(MEASURE)
    lay = job.tokens["layout"]
    safe = (int(lay.get("safe_top", 220)), int(lay.get("safe_bottom", 380)), int(lay.get("padding", 72)))
    issues, notes = [], []
    # 글자는 부품(주인) 단위로 묶는다: 단어마다 따로 말하지 않게
    groups = {}
    for o in m["texts"]:
        g = groups.setdefault((o["name"], o.get("pin")), {"name": o["name"], "pin": o.get("pin"), "boxes": [], "words": []})
        g["boxes"].append(o["box"]); g["words"].append(o["text"])
    text_owners = {k[0] for k in groups}
    for s in m["seqs"]:
        sa = area(s["box"]) or 1
        for g in groups.values():
            if g["pin"] == s["src"]:
                continue   # 이 요소의 고정점에 일부러 붙인 라벨
            ov = sum(area(inter(s["box"], b)) for b in g["boxes"])
            tot = sum(area(b) for b in g["boxes"]) or 1
            if ov / tot * 100 < 3:
                continue
            msg = f"요소 '{s['name']}' ↔ 글자 '{g['name']}' \"{' '.join(g['words'])[:30]}\" · 글자의 {ov / tot * 100:.0f}% 가 가려짐"
            (notes if s["under"] else issues).append(msg)
        for kind, items in (("자막 띠", m["caps"]), ("부품", [o for o in m["parts"] if o["name"] not in text_owners])):
            for o in items:
                ov = area(inter(s["box"], o["box"]))
                pct = ov / min(sa, area(o["box"]) or 1) * 100 if ov > 0 else 0
                if pct < 3:
                    continue
                msg = f"요소 '{s['name']}' ↔ {kind} '{o['name']}' · 겹침 {pct:.0f}%"
                (notes if s["under"] or (kind == "부품" and pct < 25) else issues).append(msg)
        if not s["under"]:
            out_v = s["box"][1] < safe[0] - 40 or s["box"][3] > 1920 - safe[1] + 40
            on_rail = area(inter(s["box"], RAIL)) / sa
            if out_v or on_rail > 0.05:
                issues.append(f"요소 '{s['name']}' 가 쇼츠 안전 영역 밖 (x {s['box'][0]:.0f}–{s['box'][2]:.0f} · y {s['box'][1]:.0f}–{s['box'][3]:.0f}) — "
                              "위 UI · 아래 채널명 · 오른쪽 버튼 줄에 가림. K.talk 판(x 72~936 · y 380~1300) 안으로, 바탕이면 under: true")
    # 글자 · 부품이 쇼츠 UI 자리에 들어가면 가린다(위 · 아래 · 오른쪽 버튼 줄)
    seen_safe = set()
    for o in m["texts"] + [x for x in m["parts"] if x["name"] not in text_owners]:
        b = o["box"]; nm = o["name"]
        bad = b[1] < safe[0] - 4 or b[3] > 1920 - safe[1] + 4 or area(inter(b, RAIL)) > 0.1 * (area(b) or 1)
        if bad and nm not in seen_safe:
            seen_safe.add(nm)
            issues.append(f"'{nm}' \"{o.get('text', '')}\" 가 쇼츠 안전 영역 밖 (x {b[0]:.0f}–{b[2]:.0f} · y {b[1]:.0f}–{b[3]:.0f}) — 위 {safe[0]} · 아래 {1920 - safe[1]} · 오른쪽 {RAIL[0]} 안으로")
    for o in m["offs"]:
        issues.append(f"글자 '{o['name']}' \"{o['text']}\" 가 화면 밖으로 {o['cut']}px 잘림 — 크기를 줄이거나 w 를 지정해 줄바꿈")
    for o in m["overflow"]:
        issues.append(f"글자 '{o['name']}' \"{o['text']}\" 가 상자를 넘침(잘림) — 글자를 줄이거나 상자를 넓힘")
    # 요소가 아닌 글자끼리 겹침도 같이 (흔한 실수)
    tx = m["texts"]
    for i in range(len(tx)):
        for j in range(i + 1, len(tx)):
            a, b = tx[i], tx[j]
            if a["name"] == b["name"]:
                continue
            ov = area(inter(a["box"], b["box"]))
            if ov and ov / min(area(a["box"]), area(b["box"])) > 0.2:
                issues.append(f"글자 '{a['name']}' \"{a['text']}\" ↔ '{b['name']}' \"{b['text']}\" 겹침")
    blocked = [o["box"] for o in m["texts"] + m["caps"] + m["parts"]]
    spots = []
    for s in m["seqs"]:
        if s["under"]:
            continue
        bx = s["box"]; ex, ey, ew, eh = s["el"]
        vis = free_spot(blocked, (bx[2] - bx[0]) / max(1, bx[3] - bx[1]), safe)   # 보이는 요소가 들어갈 자리
        if not vis:
            spots.append({"for": s["name"], "suggest": None, "visible": None}); continue
        fx0, fy0 = (bx[0] - ex) / ew, (bx[1] - ey) / eh
        fw, fh = (bx[2] - bx[0]) / ew, (bx[3] - bx[1]) / eh
        w, h = vis[2] / fw, vis[3] / fh                                           # 투명 여백까지 포함한 K.seq 상자
        spots.append({"for": s["name"], "visible": vis, "suggest": (round(vis[0] - fx0 * w), round(vis[1] - fy0 * h), round(w), round(h))})
    png = shots / f"{job.sb['id']}-{t:g}.png"
    page.screenshot(path=str(png))
    try:
        from PIL import Image, ImageDraw
        im = Image.open(png).convert("RGB"); d = ImageDraw.Draw(im, "RGBA")
        for o in m["texts"]:
            d.rectangle(o["box"], outline=(255, 214, 0, 255), width=3)
        for o in m["caps"]:
            d.rectangle(o["box"], outline=(80, 160, 255, 255), fill=(80, 160, 255, 40), width=3)
        for s in m["seqs"]:
            d.rectangle(s["box"], outline=(255, 60, 80, 255), fill=(255, 60, 80, 50), width=5)
        for sp in spots:
            if sp["visible"]:
                x, y, w, h = sp["visible"]; d.rectangle([x, y, x + w, y + h], outline=(40, 220, 120, 255), width=5)
        d.rectangle([0, 0, 1080, safe[0]], fill=(0, 0, 0, 90)); d.rectangle([0, 1920 - safe[1], 1080, 1920], fill=(0, 0, 0, 90)); d.rectangle(RAIL, fill=(0, 0, 0, 90))
        im.save(png)
    except ImportError:
        pass
    return {"t": t, "issues": issues, "notes": notes, "cues": m["cues"], "seqs": [{k: s[k] for k in ("name", "src", "box", "el", "under")} for s in m["seqs"]],
            "spots": spots, "png": str(png.relative_to(ROOT))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("storyboard")
    ap.add_argument("--at", nargs="*", type=float)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    job = make_job(Path(a.storyboard))
    if job.engine != "hyperframes":
        sys.exit(f"겹침 검사는 hyperframes 컴포지션용입니다 (이 콘티: {job.engine}).")
    adapter("hyperframes").build(job)
    times = a.at or sorted({round(min(s["end"] - .05, s["start"] + f * s["sec"]), 2) for s in job.scenes for f in (0.35, 0.65, 0.95)})
    shots = ROOT / "workspace" / "tmp" / "overlap"; shots.mkdir(parents=True, exist_ok=True)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:   # 시스템 파이썬으로 불렸으면 프로젝트 가상환경으로 다시 실행
        import os
        from platform_util import venv_python
        vp = venv_python(ROOT)
        if vp.exists() and Path(sys.executable).resolve() != vp.resolve():
            os.execv(str(vp), [str(vp), *sys.argv])
        sys.exit("playwright 가 없습니다: .venv 에 pip install playwright && playwright install chromium")
    res = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--allow-file-access-from-files"])
        page = b.new_page(viewport={"width": 1080, "height": 1920})
        page.goto((job.work / "index.html").as_uri())
        page.wait_for_function("typeof window.__sfSeek === 'function'", timeout=15000)
        page.evaluate("document.fonts.ready")
        for t in times:
            res.append(check(page, t, job, shots))
        b.close()
    missing = {(c["scene"], c["text"]) for r in res for c in r.get("cues", [])}
    bad = sum(len(r["issues"]) for r in res) + len(missing)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        for r in res:
            if not (r["issues"] or r["notes"] or r["seqs"]):
                continue
            print(f"[{r['t']:g}s] {r['png']}")
            for s in r["seqs"]:
                print(f"   요소 '{s['name']}' 보이는 영역 x{s['box'][0]:.0f}–{s['box'][2]:.0f} y{s['box'][1]:.0f}–{s['box'][3]:.0f} (상자 x,y,w,h = {s['el']})")
            for i in r["issues"]:
                print("   ✗ " + i)
            for n in r["notes"]:
                print("   · " + n)
            for sp in r["spots"]:
                if sp["suggest"] and r["issues"]:
                    x, y, w, h = sp["suggest"]
                    print(f"   → '{sp['for']}' 빈 자리 제안 (K.seq 값, 투명 여백 포함): x: {x}, y: {y}, w: {w}, h: {h}  — 초록 상자에 요소가 꽉 참. 또는 글자를 옮기거나 under: true 로 배경 처리")
        for sc, tx in sorted(missing):
            print(f"✗ 장면 {sc + 1}: 음성 신호 c.cue(\"{tx}\") 를 나레이션에서 못 찾음 — 실제 나레이션 단어로 고치기(지금은 대체 시각으로 움직임)")
        print(f"화면 검사(겹침 · 잘림 · 넘침 · 음성 신호) 문제 {bad}건 · {len(res)}시점" + (" — 고친 뒤 다시 실행하세요" if bad else " — 통과"))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
