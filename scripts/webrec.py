#!/usr/bin/env python3
"""
웹 화면 녹화 — 사이트를 돌아다니는 과정을 레이어 요소로 만든다.

기본은 '단계 캡처'다. 동작(이동 · 클릭 · 입력 · 키 · 스크롤 · 마우스 올리기)마다 고해상도 화면과 대상 위치를 남기고,
커서 이동 · 클릭 · 입력 · 스크롤 · 확대 연출은 HyperFrames(Fluma Kit K.web)가 그린다.
그래서 흔들림이 없고, 클릭 순간을 나레이션 단어(c.cue)에 맞출 수 있다.
로딩 애니메이션처럼 실제 움직임이 필요한 구간만 {"do": "record"} 로 실제 녹화(CDP screencast)해 섞는다.

  python3 scripts/webrec.py run <영상 id> compositions/<id>/web/<이름>.json
  python3 scripts/webrec.py profiles
  python3 scripts/webrec.py login <프로필> --hosts console.aws.amazon.com,signin.aws.amazon.com [--allow-write]   ← 사람이 직접

녹화 계획(JSON):
  { "start": "https://github.com/aws/agent-toolkit-for-aws",
    "viewport": [1280, 800], "scale": 2,
    "profile": null,                         # 로그인 프로필 이름 (webrec.py login 으로 사람이 만든 것)
    "mask": ["css 선택자"], "mask_text": ["정규식"],   # 추가로 가릴 것 (이메일 · AWS 계정 번호 · ARN · 액세스 키는 늘 가림)
    "hide": ["#onetrust-banner-sdk"],          # 화면에서만 숨길 것(쿠키 · 광고 띠) — 동의 버튼은 누르지 않는다. 흔한 쿠키 창은 늘 숨김
    "steps": [
      {"do": "scroll", "target": "#readme"},                 # 또는 {"do": "scroll", "by": 600}
      {"do": "click", "target": "role=button[name=\"Code\"]", "label": "1. Code 버튼"},
      {"do": "type", "target": "input[name=q]", "text": "agent toolkit"},
      {"do": "press", "key": "Enter"},
      {"do": "hover", "target": "text=Releases"},
      {"do": "goto", "url": "https://..."},
      {"do": "wait", "ms": 800},
      {"do": "record", "sec": 3, "steps": [ ...위와 같은 동작... ]}   # 이 구간만 실제 녹화
    ] }
  target 은 Playwright 선택자(css · text=… · role=button[name="…"]).

결과: public/elements/<id>/<이름>/
  s000.png …            상태마다 화면 (viewport × scale)
  r01/f00001.jpg …      실제 녹화 구간 (30fps)
  meta.json             {kind:"web", viewport, scale, states[], actions[], masked, sources, license}

로그인 프로필은 ~/.shortsforge/browser/<프로필>/ 에 있고 에이전트는 읽지 못한다.
프로필로 녹화할 때는 허용한 사이트 밖으로 이동하지 않고, 사람이 --allow-write 로 허락하지 않았다면
생성 · 삭제 · 결제 같은 버튼은 실제로 누르지 않는다(화면에서는 커서만 누르는 것처럼 보이고, meta 에 blocked 로 남는다).
"""
import argparse
import base64
import json
import re
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
# 흔한 쿠키 · 동의 창(OneTrust · Cookiebot · TrustArc · Didomi …) — 화면에서만 숨김
HIDE = ["#onetrust-consent-sdk", "#onetrust-banner-sdk", "#CybotCookiebotDialog", "#truste-consent-track", "#didomi-host", ".cc-window", "#cookie-banner", "[aria-label*='cookie' i][role='dialog']"]
PUBLIC = ROOT / "public"
PROFILES = Path.home() / ".shortsforge" / "browser"
ID_RE = re.compile(r"^[A-Za-z0-9가-힣_-]{1,80}$")
FPS = 30

# 늘 가리는 것: 이메일 · AWS 계정 번호 · ARN · 액세스 키 (JS 정규식으로도 그대로 쓴다)
MASK_TEXT = [r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", r"\b\d{4}-\d{4}-\d{4}\b", r"\b\d{12}\b",
             r"arn:aws[a-z-]*:[^\s\"'<>]+", r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"]
# 로그인 프로필에서 사람이 허락하지 않으면 실제로 누르지 않는 동작
WRITE_RE = re.compile(r"(delete|remove|terminate|destroy|drop|purchase|buy|pay|subscribe|confirm|create|launch|deploy|submit|save|apply|"
                      r"삭제|제거|종료|해지|구매|결제|구독|확인|생성|만들기|시작|배포|제출|저장|적용|변경)", re.I)

MASK_JS = r"""
window.__flumaMask = (pats, sels) => {
  let root = document.getElementById('__fluma_mask');
  if (!root) {
    root = document.createElement('div'); root.id = '__fluma_mask';
    root.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:2147483647';
    (document.body || document.documentElement).appendChild(root);
  }
  root.textContent = '';
  const res = pats.map((p) => new RegExp(p, 'g')), rects = [];
  if (document.body) {
    const wk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = wk.nextNode())) {
      const s = n.nodeValue; if (!s || s.length < 6) continue;
      for (const re of res) { re.lastIndex = 0; let m;
        while ((m = re.exec(s))) { if (!m[0].length) { re.lastIndex++; continue; }
          const r = document.createRange(); r.setStart(n, m.index); r.setEnd(n, m.index + m[0].length);
          for (const b of r.getClientRects()) rects.push(b); } }
    }
  }
  document.querySelectorAll('input,textarea').forEach((el) => {
    const v = el.value || '';
    if ((el.type === 'password' && v) || res.some((re) => { re.lastIndex = 0; return re.test(v); })) rects.push(el.getBoundingClientRect());
  });
  for (const s of sels) { try { document.querySelectorAll(s).forEach((el) => rects.push(el.getBoundingClientRect())); } catch (e) {} }
  let k = 0;
  for (const b of rects) {
    if (b.width < 1 || b.height < 1 || b.bottom < 0 || b.top > innerHeight) continue;
    const d = document.createElement('div');
    d.style.cssText = `position:absolute;left:${b.left - 3}px;top:${b.top - 2}px;width:${b.width + 6}px;height:${b.height + 4}px;` +
      'backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);background:rgba(128,128,128,.28);border-radius:4px';
    root.appendChild(d); k++;
  }
  return k;
};
"""


# 보이는 글자 덩어리: 글자를 직접 가진 요소(블록 단위)의 [x, y, w, h] · 글자 크기 · 굵기. 많아야 400개
TEXTS_JS = r"""() => {
  const out = [], seen = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode()) && out.length < 400) {
    const t = n.textContent.replace(/\s+/g, " ").trim();
    if (t.length < 2) continue;
    const e = n.parentElement; if (!e || seen.has(e)) continue;
    const r = e.getBoundingClientRect();
    if (r.width < 4 || r.height < 4 || r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) continue;
    const cs = getComputedStyle(e); if (cs.visibility === "hidden" || cs.display === "none" || +cs.opacity === 0) continue;
    seen.add(e);
    out.push({ t: (e.innerText ?? e.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 160), b: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)], fs: parseFloat(cs.fontSize), fw: +cs.fontWeight || 400 });
  }
  return out;
}"""


def host_ok(url: str, hosts: list[str]) -> bool:
    h = (urlparse(url).hostname or "").lower()
    return any(h == x or h.endswith("." + x) for x in hosts)


def load_profile(name: str) -> dict:
    cfg = PROFILES / f"{name}.json"
    if not ID_RE.match(name) or not cfg.exists():
        sys.exit(f"[webrec] 로그인 프로필 '{name}' 이 없습니다. 사람이 먼저 만들어야 합니다: python3 scripts/webrec.py login {name} --hosts …")
    return json.loads(cfg.read_text(encoding="utf-8"))


class Recorder:
    def __init__(self, page, out: Path, spec: dict, profile: dict | None):
        self.page, self.out, self.spec, self.profile = page, out, spec, profile
        self.vw, self.vh = spec.get("viewport", [1280, 800])
        self.states, self.actions, self.masked, self.sources = [], [], 0, []
        self.pats = MASK_TEXT + list(spec.get("mask_text", []))
        self.sels = list(spec.get("mask", []))
        self.hide = HIDE + list(spec.get("hide", []))
        self.rec = None          # 실제 녹화 중이면 {"t0": 시각, "events": []}

    # ---- 상태 · 가리기 ----
    def settle(self, ms=450):
        try:
            self.page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            pass
        self.page.wait_for_timeout(ms)

    def mask(self) -> int:
        try:
            return self.page.evaluate("([p, s]) => window.__flumaMask ? window.__flumaMask(p, s) : 0", [self.pats, self.sels])
        except Exception:
            return 0

    def scroll_y(self) -> float:
        try:
            return float(self.page.evaluate("scrollY"))
        except Exception:
            return 0.0

    def hide_css(self) -> None:
        """쿠키 · 동의 창을 화면에서만 숨긴다(누르지 않으니 동의한 것이 아니다)"""
        try:
            self.page.evaluate("(sels) => { let st = document.getElementById('__fluma_hide'); if (!st) { st = document.createElement('style'); st.id = '__fluma_hide'; document.documentElement.appendChild(st); } st.textContent = sels.join(',') + '{display:none !important}'; }", self.hide)
        except Exception:
            pass

    def shot(self) -> int:
        self.hide_css()
        self.masked += self.mask()
        self.page.wait_for_timeout(60)
        k = len(self.states)
        name = f"s{k:03d}.png"
        self.page.screenshot(path=str(self.out / name), animations="disabled", caret="hide")
        url = self.page.url
        if url not in self.sources and url.startswith("http"):
            self.sources.append(url)
        self.states.append({"shot": name, "url": url, "scrollY": self.scroll_y(), "texts": self.texts()})
        return k

    def texts(self) -> list:
        """화면에 보이는 글자 덩어리와 위치(뷰포트 px) · 글자 크기 — K.web read 가 '무엇을 보여 줄지'(focus text · beats 확대)를
        좌표 대신 글자로 찾게(2026-11-02: 확대 좌표를 사람이 손으로 고르면 공수 최소화 목적과 어긋난다)"""
        try:
            return self.page.evaluate(TEXTS_JS)
        except Exception:  # noqa: BLE001 — 글자를 못 읽어도 녹화는 계속
            return []

    # ---- 동작 ----
    def locate(self, target: str):
        loc = self.page.locator(target).first
        loc.wait_for(state="visible", timeout=12000)
        return loc

    def box(self, loc):
        b = loc.bounding_box()
        return [round(b["x"], 1), round(b["y"], 1), round(b["width"], 1), round(b["height"], 1)] if b else None

    def blocked(self, loc, do: str) -> bool:
        if not self.profile or self.profile.get("allow_write"):
            return False
        if do == "press":
            return True
        try:
            label = " ".join(filter(None, [loc.inner_text(timeout=1000), loc.get_attribute("aria-label") or "", loc.get_attribute("value") or ""]))
        except Exception:
            label = ""
        return bool(WRITE_RE.search(label))

    def event(self, do, box):
        if self.rec is not None:
            self.rec["events"].append({"t": round(time.time() - self.rec["t0"], 3), "do": do, "box": box})

    def bring_into_view(self, loc, label=None):
        """대상이 화면 밖이면 스크롤한다. 단계 캡처에서는 스크롤도 하나의 동작(부드럽게 미끄러짐)으로 남긴다."""
        y0 = self.scroll_y()
        loc.scroll_into_view_if_needed(timeout=8000)
        self.page.wait_for_timeout(250)
        dy = self.scroll_y() - y0
        if abs(dy) > 2 and self.rec is None:
            frm = len(self.states) - 1
            to = self.shot()
            self.actions.append({"do": "scroll", "from": frm, "to": to, "dy": round(dy, 1), "box": None, "label": label, "auto": True})

    def step(self, s: dict):
        do = s.get("do")
        label = s.get("label")
        if do == "wait":
            self.page.wait_for_timeout(int(s.get("ms", 500)))
            return
        if do == "record":
            return self.record(s)
        frm = len(self.states) - 1
        act = {"do": do, "from": frm, "label": label, "box": None}
        if do == "goto":
            url = s["url"]
            if self.profile and not host_ok(url, self.profile["hosts"]):
                raise SystemExit(f"[webrec] 허용하지 않은 사이트: {url} (프로필 허용: {', '.join(self.profile['hosts'])})")
            self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
            self.settle(700)
            act["url"] = url
        elif do == "scroll":
            y0 = self.scroll_y()
            if s.get("target"):
                self.locate(s["target"]).scroll_into_view_if_needed(timeout=8000)
            else:
                self.page.mouse.wheel(0, float(s.get("by", 600)))
            self.page.wait_for_timeout(500 if self.rec else 350)
            act["dy"] = round(self.scroll_y() - y0, 1)
        elif do in ("click", "hover", "type"):
            loc = self.locate(s["target"])
            self.bring_into_view(loc, label)
            act["from"] = len(self.states) - 1
            act["box"] = self.box(loc)
            act["target"] = s["target"]
            if do == "type":
                act["text"] = s.get("text", "")
            if do != "hover" and self.blocked(loc, do):
                act["blocked"] = True
                print(f"[webrec] 실제로 누르지 않음(쓰기 허용 안 된 프로필): {do} {s['target']}", file=sys.stderr)
            else:
                self.event(do, act["box"])
                if do == "click":
                    if self.rec is not None:
                        b = act["box"]
                        self.page.mouse.move(b[0] + b[2] / 2, b[1] + b[3] / 2, steps=12)
                    loc.click(timeout=8000)
                elif do == "hover":
                    loc.hover(timeout=8000)
                else:
                    if self.rec is not None:
                        loc.click(timeout=8000)
                        loc.press_sequentially(act["text"], delay=70)
                    else:
                        loc.fill(act["text"], timeout=8000)
            self.settle(500)
        elif do == "press":
            act["key"] = s.get("key", "Enter")
            if self.profile and not self.profile.get("allow_write"):
                act["blocked"] = True
                print(f"[webrec] 실제로 누르지 않음(쓰기 허용 안 된 프로필): 키 {act['key']}", file=sys.stderr)
            else:
                self.event("press", None)
                self.page.keyboard.press(act["key"])
                self.settle(600)
        else:
            raise SystemExit(f"[webrec] 모르는 동작: {do}")
        if self.rec is not None:          # 실제 녹화 안의 동작은 화면을 따로 찍지 않는다(녹화가 곧 화면)
            return
        act["to"] = act["from"] if act.get("blocked") else self.shot()
        self.actions.append(act)
        if do == "hover":                 # 말풍선 · 메뉴가 다음 화면들에 남지 않게 커서를 비켜 둔다
            self.page.mouse.move(2, self.vh - 2)
            self.page.wait_for_timeout(300)

    def record(self, s: dict):
        """이 구간은 실제로 녹화한다: CDP screencast 프레임을 시각 그대로 받아 30fps 로 고르게 다시 깐다."""
        if self.rec is not None:
            raise SystemExit("[webrec] record 안에 record 는 넣을 수 없습니다.")
        self.hide_css()
        k = sum(1 for a in self.actions if a["do"] == "record") + 1
        rdir = self.out / f"r{k:02d}"
        rdir.mkdir(parents=True, exist_ok=True)
        scale = float(self.spec.get("scale", 2))
        frames: list[tuple[float, bytes]] = []
        cdp = self.page.context.new_cdp_session(self.page)

        def on_frame(p):
            frames.append((float(p["metadata"]["timestamp"]), base64.b64decode(p["data"])))
            try:
                cdp.send("Page.screencastFrameAck", {"sessionId": p["sessionId"]})
            except Exception:
                pass

        cdp.on("Page.screencastFrame", on_frame)
        frm = len(self.states) - 1
        # 녹화 중에도 가리기를 계속 다시 그린다 (화면이 바뀌어도 새로 나온 이메일 · 계정 번호를 가림)
        self.page.evaluate("([p, s]) => { window.__flumaMaskTimer = setInterval(() => window.__flumaMask && window.__flumaMask(p, s), 120); }",
                           [self.pats, self.sels])
        t0 = time.time()
        self.rec = {"t0": t0, "events": []}
        cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "everyNthFrame": 1,
                                          "maxWidth": int(self.vw * scale), "maxHeight": int(self.vh * scale)})
        try:
            for sub in s.get("steps", []):
                self.step(sub)
            remain = float(s.get("sec", 0)) - (time.time() - t0)
            if remain > 0:
                self.page.wait_for_timeout(int(remain * 1000))
        finally:
            # 화면 변화가 늦게 오면 마지막 상태(예: 터미널 마지막 줄)가 프레임으로 안 들어온다 → 끝 화면을 한 장 직접 찍어 붙인다
            try:
                last = self.page.screenshot(type="jpeg", quality=92, animations="disabled", caret="hide")
                frames.append((time.time() - 0.05, last))
            except Exception:
                pass
            dur = time.time() - t0
            try:
                cdp.send("Page.stopScreencast")
            except Exception:
                pass
            self.page.evaluate("() => clearInterval(window.__flumaMaskTimer)")
            events, self.rec = self.rec["events"], None
        frames.sort(key=lambda f: f[0])
        n = max(1, round(dur * FPS))
        if not frames:
            raise SystemExit("[webrec] 녹화 프레임을 하나도 받지 못했습니다.")
        j = 0
        for i in range(n):                 # 화면이 바뀔 때만 프레임이 오므로, 각 시각에 가장 최근 프레임을 고른다
            t = t0 + i / FPS
            while j + 1 < len(frames) and frames[j + 1][0] <= t:
                j += 1
            (rdir / f"f{i + 1:05d}.jpg").write_bytes(frames[j][1])
        to = self.shot()
        self.actions.append({"do": "record", "from": frm, "to": to, "label": s.get("label"), "box": None,
                             "clip": {"dir": rdir.name, "frames": n, "fps": FPS, "ext": "jpg", "pad": 5, "sec": round(n / FPS, 2), "events": events}})


def cmd_run(a):
    from playwright.sync_api import sync_playwright
    if not ID_RE.match(a.id):
        sys.exit(f"[webrec] 잘못된 영상 id: {a.id}")
    spec_path = (ROOT / a.spec).resolve()
    if ROOT not in spec_path.parents or not spec_path.exists():
        sys.exit(f"[webrec] 녹화 계획 파일을 찾을 수 없습니다: {a.spec}")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    name = a.name or spec.get("name") or spec_path.stem
    if not ID_RE.match(name):
        sys.exit(f"[webrec] 잘못된 이름: {name}")
    profile = load_profile(spec["profile"]) if spec.get("profile") else None
    start = spec.get("start")
    if not start:
        sys.exit("[webrec] start(첫 주소)가 필요합니다.")
    if profile and not host_ok(start, profile["hosts"]):
        sys.exit(f"[webrec] 허용하지 않은 사이트: {start}")
    out = PUBLIC / "elements" / a.id / name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    if spec.get("mobile") and "viewport" not in spec:
        spec["viewport"] = [390, 844]          # iPhone 13 화면(녹화기 · meta 도 같은 크기로)
    vw, vh = spec.get("viewport", [1280, 800])
    scale = float(spec.get("scale", 2))

    with sync_playwright() as p:
        opts = dict(viewport={"width": vw, "height": vh}, device_scale_factor=scale, locale=spec.get("locale", "ko-KR"),
                    color_scheme=spec.get("theme", "light"))
        if spec.get("mobile"):   # 폰으로 보는 화면(모바일 사이트 · 터치) — 세로 영상에 가득 채운다
            dev = p.devices.get(spec.get("device", "iPhone 13"), {})
            opts.update({k: dev[k] for k in ("user_agent", "is_mobile", "has_touch") if k in dev})
            opts["viewport"] = dev.get("viewport", {"width": 390, "height": 844}) if "viewport" not in spec else opts["viewport"]
        if profile:
            ctx = p.chromium.launch_persistent_context(str(PROFILES / spec["profile"]), headless=True, **opts)
            hosts = profile["hosts"]

            def guard(route):   # 허용한 사이트 밖으로 페이지가 넘어가지 않게 (리소스 요청은 그대로)
                r = route.request
                try:
                    main = r.is_navigation_request() and r.frame.parent_frame is None
                except Exception:          # 서비스 워커 요청 등은 프레임이 없다
                    main = False
                if main and not host_ok(r.url, hosts):
                    print(f"[webrec] 허용하지 않은 사이트로의 이동을 막음: {r.url}", file=sys.stderr)
                    return route.abort()
                return route.continue_()
            ctx.route("**/*", guard)
        else:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(**opts)
        ctx.add_init_script(MASK_JS)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        rec = Recorder(page, out, spec, profile)
        err, where = None, "start"
        try:
            page.goto(start, wait_until="domcontentloaded", timeout=45000)
            rec.settle(900)
            rec.shot()
            for i, s in enumerate(spec.get("steps", [])):
                where = f"steps[{i}] {s.get('do')} {s.get('target') or s.get('url') or ''}".strip()
                rec.step(s)
        except SystemExit as e:
            err = str(e)
        except Exception as e:                       # 어디까지 됐는지 남겨 둔다
            err = f"{where}: {type(e).__name__}: {str(e).splitlines()[0]}"
        finally:
            ctx.close()

    first = out / "s000.png"
    w, h = (int(vw * scale), int(vh * scale))
    meta = {"kind": "web", "engine": "playwright", "frames": 1, "fps": FPS, "ext": "png", "pad": 3, "w": w, "h": h,
            "viewport": [vw, vh], "scale": scale, "states": rec.states, "actions": rec.actions, "mobile": bool(spec.get("mobile")),
            "masked": rec.masked, "profile": spec.get("profile"), "sources": rec.sources,
            "license": "웹 화면 캡처 — 출처: " + ", ".join(rec.sources[:5]), "commercial": "출처 표기 · 인용 범위에서"}
    if err:
        meta["error"] = err
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    blocked = [x for x in rec.actions if x.get("blocked")]
    print(f"[webrec] {out.relative_to(ROOT)}: 화면 {len(rec.states)}장, 동작 {len(rec.actions)}개"
          + (f", 가린 곳 {rec.masked}곳" if rec.masked else "") + (f", 실제로 누르지 않은 동작 {len(blocked)}개" if blocked else ""))
    print(f"[webrec] scene.js: K.web(c.root, \"elements/{a.id}/{name}\", {{ times: [ … 동작 {len(rec.actions)}개의 시각 … ] }})")
    if err:
        print(f"[webrec] 중간에 멈춤: {err}", file=sys.stderr)
        sys.exit(1)
    if not first.exists():
        sys.exit(1)


PROBE_JS = r"""
() => {
  const q = (s) => JSON.stringify(s);
  const name = (e) => (e.getAttribute('aria-label') || e.innerText || e.value || e.placeholder || e.title || '').replace(/\s+/g, ' ').trim().slice(0, 60);
  const roleOf = (e) => { const t = e.tagName.toLowerCase(); const r = e.getAttribute('role');
    if (r) return r; if (t === 'a') return 'link'; if (t === 'button' || t === 'summary') return 'button';
    if (t === 'input' || t === 'textarea') return ['checkbox', 'radio'].includes(e.type) ? e.type : 'textbox'; if (t === 'select') return 'combobox';
    if (/^h[1-4]$/.test(t)) return 'heading'; return t; };
  const els = [...document.querySelectorAll('a[href],button,summary,input:not([type=hidden]),textarea,select,[role=button],[role=link],[role=tab],[role=menuitem],h1,h2,h3')];
  const out = [];
  for (const e of els) {
    const b = e.getBoundingClientRect(); if (b.width < 4 || b.height < 4) continue;
    const st = getComputedStyle(e); if (st.visibility === 'hidden' || st.display === 'none' || +st.opacity === 0) continue;
    const n = name(e), role = roleOf(e);
    let sel = e.id && /^[A-Za-z][\w-]*$/.test(e.id) ? '#' + e.id
      : (e.getAttribute('data-testid') ? `[data-testid=${q(e.getAttribute('data-testid'))}]`
      : (e.name && /input|textarea|select/i.test(e.tagName) ? `${e.tagName.toLowerCase()}[name=${q(e.name)}]`
      : (n ? `role=${role}[name=${q(n.slice(0, 40))}]` : null)));
    if (!sel) continue;
    out.push({ role, name: n, selector: sel, box: [Math.round(b.x), Math.round(b.y + scrollY), Math.round(b.width), Math.round(b.height)], inView: b.top >= 0 && b.bottom <= innerHeight });
  }
  return out;
}
"""


def cmd_probe(a):
    """페이지에서 누르거나 가리킬 수 있는 요소와 선택자를 뽑는다. 녹화 계획을 쓰기 전에 먼저 본다.
    번호를 매긴 스크린샷을 workspace/tmp/webrec-probe.png 에 남긴다."""
    from playwright.sync_api import sync_playwright
    vw, vh = a.viewport
    tmp = ROOT / "workspace" / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        if a.profile:
            prof = load_profile(a.profile)
            if not host_ok(a.url, prof["hosts"]):
                sys.exit(f"[webrec] 허용하지 않은 사이트: {a.url}")
            ctx = p.chromium.launch_persistent_context(str(PROFILES / a.profile), headless=True, viewport={"width": vw, "height": vh})
        else:
            ctx = p.chromium.launch(headless=True).new_context(viewport={"width": vw, "height": vh})
        ctx.add_init_script(MASK_JS)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(a.url, wait_until="domcontentloaded", timeout=45000)
        try:
            page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            pass
        page.wait_for_timeout(800)
        items = page.evaluate(PROBE_JS)
        # 선택자가 정말 하나를 가리키는지 확인 (여럿이면 >> nth=0 을 붙여 알려 줌)
        for it in items:
            try:
                n = page.locator(it["selector"]).count()
            except Exception:
                n = 0
            it["matches"] = n
            if n > 1:
                it["selector"] += " >> nth=0"
        items = [it for it in items if it["matches"]][: a.limit]
        # 번호표 붙인 스크린샷
        page.evaluate("""(items) => { const r = document.createElement('div'); r.style.cssText = 'position:absolute;left:0;top:0;pointer-events:none;z-index:2147483647';
          items.forEach((it, k) => { const [x, y, w, h] = it.box; const d = document.createElement('div');
            d.style.cssText = `position:absolute;left:${x}px;top:${y}px;width:${w}px;height:${h}px;outline:2px solid #e11d48`;
            const t = document.createElement('span'); t.textContent = k; t.style.cssText = 'position:absolute;left:-2px;top:-18px;background:#e11d48;color:#fff;font:700 12px sans-serif;padding:1px 4px';
            d.appendChild(t); r.appendChild(d); }); document.body.appendChild(r); }""", items)
        page.evaluate("([p, s]) => window.__flumaMask && window.__flumaMask(p, s)", [MASK_TEXT, []])
        shot = tmp / "webrec-probe.png"
        page.screenshot(path=str(shot), full_page=True)
        ctx.close()
    for k, it in enumerate(items):
        print(f"{k:3d}  {'화면 안' if it['inView'] else '아래   '}  {it['role']:<9} {it['name'][:40]:<40}  {it['selector']}")
    print(f"[webrec] 번호표 스크린샷: {shot.relative_to(ROOT)}")


def cmd_profiles(a):
    PROFILES.mkdir(parents=True, exist_ok=True)
    rows = []
    for cfg in sorted(PROFILES.glob("*.json")):
        c = json.loads(cfg.read_text(encoding="utf-8"))
        rows.append({"profile": cfg.stem, "hosts": c.get("hosts", []), "allow_write": bool(c.get("allow_write")), "created": c.get("created")})
    print(json.dumps(rows, ensure_ascii=False, indent=1) if rows else "[webrec] 로그인 프로필이 없습니다.")


def cmd_login(a):
    """사람이 직접 실행: 창이 뜨면 로그인하고 창을 닫는다. 에이전트는 이 프로필 폴더를 읽지 못한다."""
    from playwright.sync_api import sync_playwright
    if not ID_RE.match(a.profile):
        sys.exit("[webrec] 프로필 이름은 영문 · 숫자 · _ · - 만 쓸 수 있습니다.")
    hosts = [h.strip().lower() for h in a.hosts.split(",") if h.strip()]
    if not hosts:
        sys.exit("[webrec] --hosts 로 녹화를 허용할 사이트를 적어 주세요.")
    data = PROFILES / a.profile
    data.mkdir(parents=True, exist_ok=True)
    PROFILES.chmod(0o700)
    data.chmod(0o700)
    url = a.url or f"https://{hosts[0]}"
    print(f"[webrec] 브라우저 창에서 로그인한 뒤, 창을 닫으면 프로필 '{a.profile}' 이 저장됩니다.")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(data), headless=False, viewport=None, locale="ko-KR")
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url)
        ctx.wait_for_event("close", timeout=0)
    cfg = PROFILES / f"{a.profile}.json"
    cfg.write_text(json.dumps({"hosts": hosts, "allow_write": bool(a.allow_write), "created": time.strftime("%Y-%m-%d %H:%M")},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    cfg.chmod(0o600)
    print(f"[webrec] 저장했습니다: 허용 사이트 {', '.join(hosts)}" + (" · 쓰기 동작 허용" if a.allow_write else " · 읽기 전용(생성 · 삭제 · 결제 버튼은 누르지 않음)"))


def main():
    ap = argparse.ArgumentParser(description="웹 화면 녹화 → 레이어 요소")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="녹화 계획대로 사이트를 돌며 단계 화면 · 실제 녹화 구간을 만든다")
    r.add_argument("id")
    r.add_argument("spec")
    r.add_argument("--name")
    r.set_defaults(fn=cmd_run)
    pr = sub.add_parser("probe", help="페이지의 누를 수 있는 요소 · 선택자 목록과 번호표 스크린샷")
    pr.add_argument("url")
    pr.add_argument("--profile")
    pr.add_argument("--viewport", type=int, nargs=2, default=[1280, 800])
    pr.add_argument("--limit", type=int, default=120)
    pr.set_defaults(fn=cmd_probe)
    sub.add_parser("profiles", help="로그인 프로필 목록(비밀 정보 없음)").set_defaults(fn=cmd_profiles)
    lg = sub.add_parser("login", help="(사람이 직접) 로그인 프로필 만들기")
    lg.add_argument("profile")
    lg.add_argument("--hosts", required=True, help="녹화를 허용할 사이트, 쉼표로 구분 (하위 도메인 포함)")
    lg.add_argument("--url", help="처음 열 주소 (기본: 첫 사이트)")
    lg.add_argument("--allow-write", action="store_true", help="생성 · 삭제 · 결제 같은 버튼도 실제로 누르게 허용")
    lg.set_defaults(fn=cmd_login)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
