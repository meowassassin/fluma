#!/usr/bin/env python3
"""
증거층 1: 화면 캡처 + 에셋 배치.

콘티의 장면 중 visual.kind 가 "screenshot" 이고 asset 이 "captures/<slug>/<name>.png" 인 것은
Playwright(크로미움, 데스크톱 화면)로 페이지를 찍어 public/<asset> 에 둔다.
still / footage / price_tag / audio_demo 처럼 파일이 필요한 에셋은 assets/ stills/ footage/ audio/ 아래에서 찾아
public/<asset> 으로 복사한다 (렌더 엔진들이 읽는 공용 자산 위치).

URL 결정 순서:
  1) --set captures/x/y.png=https://... 명시
  2) captures/urls.json  {asset_path: url}
  3) research/<topic slug>.json 의 facts[].source 중 호스트에 <slug> 가 들어가는 첫 URL
  4) 콘티 sources[] 중 호스트에 <slug> 가 들어가는 첫 URL

없는 에셋은 건너뛰고(Overlay 템플릿이 플레이스홀더를 그림) storyboards/_assets/<id>.json 에 목록을 남긴다.
종료 코드는 항상 0 — 에셋 부족은 렌더를 막지 않는다.

사용:
  python scripts/capture.py storyboards/example.json
  python scripts/capture.py storyboards/example.json --set captures/elevenlabs/pricing-free.png=https://elevenlabs.io/pricing
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
URLMAP = ROOT / "captures" / "urls.json"
ASSET_DIRS = [ROOT, ROOT / "assets"]          # "stills/..", "footage/..", "audio/.." 는 ROOT 기준 상대경로

HIDE_OVERLAYS_CSS = """
[id*="cookie" i], [class*="cookie" i], [id*="consent" i], [class*="consent" i], [id*="onetrust" i],
[class*="CookieBanner" i], [aria-label*="cookie" i], [role="dialog"][aria-modal="true"] { display: none !important; }
html, body { overflow: auto !important; }
"""

COOKIE_SELECTORS = [
    "button#onetrust-accept-btn-handler",
    "button[aria-label*='accept' i]",
    "button:has-text('Accept all')", "button:has-text('Accept')",
    "button:has-text('동의')", "button:has-text('확인')", "button:has-text('모두 허용')",
    "[data-testid='cookie-policy-manage-dialog-accept-button']",
]


def slug_of(topic: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "-", topic or "").strip("-")[:60]


def host_matches(url: str, slug: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    s = slug.lower()
    return bool(s) and (s in host or host.split(".")[0] in s)


def resolve_url(asset: str, sb: dict, overrides: dict) -> str | None:
    if asset in overrides:
        return overrides[asset]
    if URLMAP.exists():
        m = json.loads(URLMAP.read_text(encoding="utf-8"))
        if asset in m:
            return m[asset]
    parts = asset.split("/")
    slug = parts[1] if len(parts) >= 3 else ""
    rp = ROOT / "research" / f"{slug_of(sb.get('topic', ''))}.json"
    if rp.exists():
        for f in json.loads(rp.read_text(encoding="utf-8")).get("facts", []):
            src = str(f.get("source", ""))
            if src.startswith("http") and host_matches(src, slug):
                return src
    for src in sb.get("sources", []):
        if str(src).startswith("http") and host_matches(src, slug):
            return src
    return None


def find_local(asset: str) -> Path | None:
    for base in ASSET_DIRS:
        p = base / asset
        if p.is_file():
            return p
    return None


def place(src: Path, asset: str) -> Path:
    dst = PUBLIC / asset
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        shutil.copy2(src, dst)
    return dst


def screenshot(url: str, asset: str) -> Path:
    from playwright.sync_api import sync_playwright  # 지연 import: 캡처가 없을 땐 playwright 불필요
    dst = PUBLIC / asset
    dst.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # 데스크톱 화면을 세로로 길게 찍는다: Overlay 의 브라우저 프레임(가로 900px)이 이 이미지를 천천히 스크롤한다
        ctx = browser.new_context(viewport={"width": 1280, "height": 2000}, device_scale_factor=1.5,
                                  locale="ko-KR", user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"))
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        page.wait_for_timeout(1200)
        for sel in COOKIE_SELECTORS:                      # 쿠키 배너는 되면 닫고, 안 되면 무시
            try:
                page.locator(sel).first.click(timeout=800)
                page.wait_for_timeout(400)
                break
            except Exception:
                pass
        # 쿠키·동의·언어 선택 레이어는 숨기고 맨 위에서 찍는다 (클릭으로 못 닫는 배너가 많다)
        page.add_style_tag(content=HIDE_OVERLAYS_CSS)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(500)
        page.screenshot(path=str(dst), full_page=False)
        browser.close()
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("storyboard")
    ap.add_argument("--set", action="append", default=[], help="asset=url 덮어쓰기 (여러 번 가능)")
    ap.add_argument("--force", action="store_true", help="이미 있는 캡처도 다시 찍음")
    args = ap.parse_args()

    sb = json.loads(Path(args.storyboard).read_text(encoding="utf-8"))
    overrides = dict(s.split("=", 1) for s in args.set if "=" in s)
    PUBLIC.mkdir(parents=True, exist_ok=True)

    rows, missing = [], []
    for i, sc in enumerate(sb.get("scenes", [])):
        v = sc.get("visual", {}) or {}
        asset = v.get("asset")
        if not asset:
            continue
        kind = v.get("kind")
        dst = PUBLIC / asset
        if dst.exists() and not args.force:
            rows.append((i, kind, asset, "있음"));  continue
        if kind == "screenshot" and asset.startswith("captures/"):
            url = resolve_url(asset, sb, overrides)
            if not url:
                rows.append((i, kind, asset, "URL 없음")); missing.append({"scene": i, "asset": asset, "reason": "url"}); continue
            try:
                screenshot(url, asset)
                rows.append((i, kind, asset, f"캡처 ← {url}"))
            except Exception as e:                    # 네트워크 차단·타임아웃 등
                rows.append((i, kind, asset, f"실패: {str(e)[:60]}")); missing.append({"scene": i, "asset": asset, "reason": "capture", "url": url})
            continue
        local = find_local(asset)
        if local:
            place(local, asset); rows.append((i, kind, asset, f"복사 ← {local.relative_to(ROOT)}"))
        else:
            rows.append((i, kind, asset, "파일 없음")); missing.append({"scene": i, "asset": asset, "reason": "file"})

    print(f"{'장면':>4}  {'종류':<11} {'에셋':<48} 상태")
    for i, k, a, st in rows:
        print(f"{i:>4}  {k or '-':<11} {a:<48} {st}")
    out = ROOT / "storyboards" / "_assets"
    out.mkdir(exist_ok=True)
    (out / f"{sb['id']}.json").write_text(json.dumps({"id": sb["id"], "missing": missing}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n없는 에셋 {len(missing)}개 → {out / (sb['id'] + '.json')} (렌더는 플레이스홀더로 진행)")


if __name__ == "__main__":
    main()
