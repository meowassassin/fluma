#!/usr/bin/env python3
"""
그 시각 화면에 무엇이 있나 — "12초부터 나오는 서버를 키워 줘" 같은 시각 기준 요청을 장면 · 요소 · 코드 위치로 바꾼다.

  python3 scripts/frame_at.py storyboards/<id>.json 12            # 12초: 장면 번호 · 장면 안 시각 · 그때 나레이션 · 보이는 요소(이름 · 위치 · 크기 · 손 수정 키)
  python3 scripts/frame_at.py storyboards/<id>.json 12 --png      # + 그 순간 PNG (Read 로 보기)

요소 이름은 scene.js 의 name: "…" / K.name(el, "…") 그대로라 코드에서 바로 찾을 수 있다. '키'는 overrides.json 의 손 수정 키(장면:자식 순서).
고칠 때는 그 장면 함수만, 그 요소만 바꾼다. 움직임 속도는 그 요소의 at · dur · 이징을, 크기는 w · h · size 를.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engines import PUBLIC, ROOT, adapter, make_job  # noqa: E402

LIST = r"""
(t) => {
  const vis = (el) => { for (let n = el; n && n.nodeType === 1; n = n.parentElement) { const cs = getComputedStyle(n); if (cs.display === "none" || cs.visibility === "hidden" || parseFloat(cs.opacity) < 0.05) return false; } return true; };
  const scenes = [...document.querySelectorAll(".k-scene")];
  const out = [];
  scenes.forEach((host, si) => {
    if (getComputedStyle(host).visibility === "hidden") return;
    const walk = (el, path, depth) => [...el.children].forEach((c, k) => {
      const p = path ? `${path}.${k}` : `${k}`;
      if (!vis(c)) return;
      const r = c.getBoundingClientRect();
      const name = c.dataset.name || (c.dataset.seq ? "요소 " + c.dataset.seq.split("/").pop() : "");
      const txt = (c.textContent || "").trim().replace(/\s+/g, " ").slice(0, 30);
      if ((name || txt) && r.width > 2 && r.height > 2 && r.right > 0 && r.bottom > 0 && r.left < 1080 && r.top < 1920)
        out.push({ scene: si, key: `${si}:${p}`, name: name || txt, part: c.dataset.part || c.tagName.toLowerCase(), seq: c.dataset.seq || null,
                   box: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)], text: name && txt && txt !== name ? txt : "" });
      if (depth < 2 && c.children.length && c.children.length < 12 && !c.dataset.seq) walk(c, p, depth + 1);
    });
    walk(host, "", 0);
  });
  return out;
}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("storyboard")
    ap.add_argument("sec", type=float)
    ap.add_argument("--png", action="store_true")
    a = ap.parse_args()
    job = make_job(Path(a.storyboard))
    sb = job.sb
    t = max(0.0, min(job.duration - 0.02, a.sec))
    sc = next((s for s in job.scenes if s["start"] <= t < s["end"]), job.scenes[-1])
    i, lt = sc["index"], t - sc["start"]
    scene = sb["scenes"][i]
    print(f"[{t:.2f}초] 장면 {i + 1}/{len(sb['scenes'])} ({scene.get('role')}) · 장면 안 {lt:.2f}초 / {sc['sec']:.2f}초")
    print(f"  화면 글자: {scene.get('caption', '').replace(chr(10), ' / ')}")
    cp = PUBLIC / "audio" / f"{sb['id']}.captions.json"
    if cp.exists():
        words = [w for w in json.loads(cp.read_text(encoding="utf-8")) if w.get("scene") == i]
        now = [w["text"].strip() for w in words if w["startMs"] <= t * 1000 + 600 and w["endMs"] >= t * 1000 - 600]
        print(f"  그때 나레이션: …{' '.join(now)}…   (장면 전체: {scene.get('narration', '')})")
        print("  단어 시각(장면 안, c.cue 로 맞추기): " + " · ".join(f"{w['text'].strip()} {w['startMs'] / 1000 - sc['start']:.2f}" for w in words))
    if job.engine != "hyperframes":
        return
    adapter("hyperframes").build(job)
    ovr_p = ROOT / "compositions" / sb["id"] / "overrides.json"
    ovr = json.loads(ovr_p.read_text(encoding="utf-8") or "{}") if ovr_p.exists() else {}
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--allow-file-access-from-files"])
        page = b.new_page(viewport={"width": 1080, "height": 1920})
        page.goto((job.work / "index.html").as_uri())
        page.wait_for_function("typeof window.__sfSeek === 'function'", timeout=15000)
        page.evaluate("document.fonts.ready")
        page.evaluate(f"window.__sfSeek({t})")
        page.wait_for_timeout(150)
        items = page.evaluate(LIST, t)
        print(f"  보이는 요소 {len(items)}개 (x, y, 폭, 높이 · 1080×1920 기준):")
        for o in items:
            hand = " · 손 수정 있음" if o["key"] in ovr else ""
            extra = f" \"{o['text']}\"" if o["text"] else ""
            print(f"   - {o['name']}{extra}  [{o['part']}]  {o['box']}  키 {o['key']}{hand}")
        if a.png:
            out = ROOT / "workspace" / "tmp" / f"frame-{sb['id']}-{t:g}.png"
            page.screenshot(path=str(out))
            print(out.relative_to(ROOT))
        b.close()


if __name__ == "__main__":
    main()
