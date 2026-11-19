#!/usr/bin/env python3
"""Craft 앱 전체 기능 목록 — 설치된 앱 16개의 명령 · 효과 · 프리셋을 한 형식으로 모아 두고, 하고 싶은 일로 찾는다.
에이전트가 아는 몇 가지 기능만 되풀이하지 않게(편향) — 만들기 전에 '이 일을 하는 기능이 있나'를 먼저 찾는다.

  python3 engine/craft/craft_catalog.py build                     # 목록 다시 뽑기(앱을 설치 · 업데이트한 뒤) → .claude/skills/crafts/catalog/<앱>.jsonl
  python3 engine/craft/craft_catalog.py search "곡선 화살표" [--app vectorcraft] [--n 15]   # 한국어 · 영어 낱말 모두
  python3 engine/craft/craft_catalog.py stats                     # 앱별 명령 · 효과 · 프리셋 수
  python3 engine/craft/craft_catalog.py show <앱> <명령 id>       # 한 명령의 params 전체
  python3 engine/craft/craft_catalog.py coverage [--id <영상 id>]  # 영상들이 실제로 쓴 기능 — 앱별 사용 비율 · 한 번도 안 쓴 앱(편향 보기)

한 줄 = {"app", "kind": command|effect|preset|tool, "id", "label", "menu", "params", "summary"}
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
OUT = ROOT / ".claude" / "skills" / "crafts" / "catalog"
TOOLS = ROOT / "tools" / "crafts"

# 한국어로 찾을 때 — 자주 쓰는 낱말을 영어 검색어로 넓힌다
KO = {
    "화살표": "arrow", "곡선": "curve bezier", "박스": "box rectangle", "상자": "box rectangle", "글자": "text type", "자막": "caption subtitle",
    "그림자": "shadow drop", "흐림": "blur", "흐리게": "blur gaussian", "확대": "zoom scale magnify", "줌": "zoom scale", "색": "color colour",
    "보정": "correct grade adjust", "누끼": "cutout remove background mask", "배경": "background", "지우기": "remove erase delete", "제거": "remove reduce removal", "등장": "in reveal intro appear", 
    "마스크": "mask", "추적": "track tracker", "전환": "transition", "퇴장": "out exit",
    "애니메이션": "animation animate preset", "프리셋": "preset", "템플릿": "template", "형광펜": "highlight", "강조": "highlight emphasis",
    "표": "table", "차트": "chart graph", "도표": "diagram smartart chart", "구조도": "diagram smartart hierarchy", "흐름도": "flowchart diagram process",
    "음량": "loudness volume gain", "소음": "noise denoise hum", "덕킹": "duck ducking", "페이드": "fade", "효과음": "sfx sound effect",
    "목소리": "voice dialogue speech", "녹음": "record", "잡음": "noise", "리버브": "reverb", "이퀄라이저": "eq equalizer",
    "회전": "rotate turntable orbit", "3d": "3d camera extrude", "재질": "material texture", "도면": "drawing dimension plot",
    "썸네일": "thumbnail export frame", "내보내기": "export render", "카드": "card frame", "레이어": "layer", "손그림": "brush pencil width sketch",
    "붓": "brush", "선": "stroke line path", "점선": "dash dashed stroke", "패턴": "pattern", "그라데이션": "gradient ramp", "빛": "light glow",
    "흔들림": "wiggle shake stabilize", "속도": "speed time remap", "빨리": "speed fast", "자르기": "crop trim cut", "맞추기": "fit align",
    # 영상 · 모션그래픽 낱말(2026-11-19: '필름 그레인' · '네온' · '글리치' · '파티클' 이 '없음' — 사전이 작아 24개 중 3개만 찾았다)
    "빛나": "glow", "빛남": "glow", "광채": "glow", "후광": "glow halo", "네온": "neon glow", "발광": "glow",
    "그레인": "grain", "필름": "film grain", "노이즈": "noise grain", "질감": "texture grain noise paper", "종이": "paper", "먼지": "dust scratches",
    "타이핑": "typewriter", "타자": "typewriter", "한 글자씩": "typewriter", "글리치": "glitch digital chromatic rgb", "치지직": "glitch",
    "숫자": "numbers number", "카운트": "numbers count", "올라가": "numbers", "물결": "wave ripple", "출렁": "wave warp",
    "왜곡": "distort warp", "파티클": "particle", "입자": "particle", "반짝": "particle star sparkle glint", "별": "star",
    "빛줄기": "light rays", "줄기": "rays", "훑": "sweep", "스윕": "sweep", "번쩍": "flash burst exposure", "플레어": "lens flare", "렌즈": "lens",
    "블러": "blur", "흐림": "blur", "흐리": "blur", "방사": "radial", "속도감": "radial motion blur", "모션블러": "motion blur",
    "따뜻": "warm photo filter balance", "차갑": "cool photo filter balance", "톤": "color grade tone", "색감": "color grade look",
    "거품": "bubbles", "비눗방울": "bubbles", "그려지": "write scribble stroke", "그려": "write scribble stroke", "손글씨": "write scribble",
    "번개": "lightning", "전기": "lightning", "모자이크": "mosaic", "픽셀": "mosaic pixel", "카메라": "camera", "궤도": "orbit",
    "그림자": "shadow drop", "외곽선": "stroke outline", "테두리": "stroke outline border", "말풍선": "callout speech balloon",
    "튀어": "pop bounce", "통통": "bounce", "탄력": "bounce elastic", "스르륵": "fade dissolve", "녹아": "dissolve",
    "타원": "ellipse", "원": "circle ellipse", "사각형": "rectangle", "다각형": "polygon", "구름": "cloud fractal", "연기": "smoke fractal turbulent",
    "불": "fire flame", "비": "rain", "눈송이": "snow", "물": "water caustics", "유리": "glass refraction", "거울": "mirror reflect",
}
# 영상 장면에 잘 안 쓰는 앱(문서 · CAD · 3D) — 질의가 그 뜻을 말할 때만 올린다
APP_PRIOR = {"effectcraft": 3.0, "filmcraft": 1.5, "photocraft": 1.0, "vectorcraft": 1.0, "lightcraft": 0.5, "figcraft": 0.0, "soundcraft": 0.0,
             "designcraft": -1.0, "deckcraft": -2.0, "wordcraft": -2.0, "gridcraft": -2.0, "pdfcraft": -2.0, "craft-anything": -1.0,
             "cadcraft": -4.0, "solidcraft": -4.0, "texturecraft": -3.0}
APP_WORDS = {"cadcraft": ("도면", "cad", "치수", "평면도"), "solidcraft": ("3d 제품", "모형", "제품 3d", "solid", "분해"), "texturecraft": ("재질", "texture 3d", "pbr"),
             "deckcraft": ("슬라이드", "발표"), "wordcraft": ("문서", "워드"), "gridcraft": ("표", "엑셀", "스프레드"), "pdfcraft": ("pdf",)}
UI_CMD = re.compile(r"^(view|pref|learn|help|window|time\.|file\.(run|new|open|close|recent)|edit\.(undo|redo)|markers\.|tool\.)")

EXTRAS = {   # 효과 · 프리셋 목록(명령 목록에 안 나오는 실제 기능 이름들)
    "effectcraft": [("effect", ["exec", "effect.list", "--json"]), ("preset", ["exec", "anim.builtinPresets", "--json"]), ("preset", ["exec", "text.presets", "--json"])],
    "filmcraft": [("effect", ["--compact", "exec", "effects.list"]), ("preset", ["--compact", "exec", "lumetri.presets"]), ("preset", ["export", "--list-presets"])],
}


def cli(app: str) -> Path | None:
    f = TOOLS / app / "installed.json"
    if f.exists():
        p = ROOT / json.loads(f.read_text("utf-8")).get("cli", "")
        if p.is_file():
            return p
    found = sorted(TOOLS.glob(f"{app}/**/bin/{app}-cli"))
    return found[0] if found else None


def _sh(args: list, timeout: int = 90) -> str:
    try:
        r = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=timeout, cwd=str(ROOT),
                           env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home()), "DO_NOT_TRACK": "1", "SOUNDCRAFT_NO_PREFS": "1", "VECTORCRAFT_NO_PREFS": "1"})
        return r.stdout
    except (subprocess.TimeoutExpired, OSError):
        return ""


def _json_tail(s: str):
    """출력 안의 JSON(배열 · 객체) — 앞에 안내 문장이 있어도"""
    for i, ch in enumerate(s):
        if ch in "[{":
            try:
                return json.loads(s[i:])
            except ValueError:
                continue
    return None


def _list_of(d):
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        for v in d.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
        for v in d.values():
            r = _list_of(v)
            if r:
                return r
    return []


def _row(app: str, kind: str, c: dict) -> dict:
    cid = c.get("id") or c.get("command") or c.get("name") or c.get("matchName") or ""
    params = c.get("params") if c.get("params") is not None else c.get("inputSchema") or c.get("schema") or c.get("args")
    if not isinstance(params, str) and params is not None:
        params = json.dumps(params, ensure_ascii=False)[:1500]
    menu = c.get("menu") or c.get("location") or c.get("panel") or c.get("category") or c.get("folder")
    if isinstance(menu, list):
        menu = " > ".join(str(x) for x in menu)
    return {"app": app, "kind": kind, "id": str(cid), "label": c.get("label") or c.get("name") or c.get("title") or "",
            "menu": menu or "", "params": params or "", "summary": (c.get("summary") or c.get("description") or "")[:400]}


def _text_rows(app: str, s: str) -> list[dict]:
    """텍스트 목록: 'id — 라벨: params' · 'id   라벨   메뉴' 같은 줄"""
    rows = []
    for ln in s.splitlines():
        m = re.match(r"^\s*([a-z][\w-]*(?:[._][\w-]+)+)\s+(?:[—-]\s*)?(.*)$", ln)
        if not m:
            continue
        rest = m.group(2).strip()
        label, params = rest, ""
        if ": {" in rest or ":{" in rest:
            label, params = rest.split(":", 1)
        elif "  " in rest:
            parts = [p for p in re.split(r"\s{2,}", rest) if p]
            label = parts[0]
            params = " | ".join(parts[1:])
        rows.append({"app": app, "kind": "command", "id": m.group(1), "label": label.strip(), "menu": "", "params": params.strip(), "summary": ""})
    return rows


def collect(app: str) -> list[dict]:
    b = cli(app)
    if not b:
        return []
    rows: list[dict] = []
    if app == "pdfcraft":
        d = _json_tail(_sh([b, "tools"]))
        # run --script 가 받는 것은 도구 이름(name: doc_open …) — command(메뉴 id)는 별칭으로 메뉴 칸에
        rows = [{**_row(app, "tool", {**c, "id": c.get("name"), "command": None, "params": c.get("input_schema")}), "menu": c.get("command") or ""}
                for c in _list_of(d) or (d if isinstance(d, list) else [])]
    else:
        d = _json_tail(_sh([b, "commands", "--json"]))
        items = _list_of(d)
        if items:
            rows = [_row(app, "command", c) for c in items]
        else:
            t = _sh([b, "commands"])
            d = _json_tail(t) if t.lstrip().startswith(("[", "{")) else None
            rows = [_row(app, "command", c) for c in _list_of(d)] if d else _text_rows(app, t)
    for kind, args in EXTRAS.get(app, []):
        d = _json_tail(_sh([b, *args]))
        rows += [_row(app, kind, c) for c in _list_of(d)]
    seen, out = set(), []
    for r in rows:
        k = (r["kind"], r["id"], r["label"])
        if r["id"] and k not in seen:
            seen.add(k)
            out.append(r)
    return out


def build() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    stats = {}
    for d in sorted(TOOLS.iterdir()) if TOOLS.exists() else []:
        if not d.is_dir():
            continue
        rows = collect(d.name)
        if not rows:
            print(f"[목록] {d.name}: 명령을 읽지 못함(설치 확인)", file=sys.stderr)
            continue
        with (OUT / f"{d.name}.jsonl").open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        stats[d.name] = {k: sum(1 for r in rows if r["kind"] == k) for k in ("command", "tool", "effect", "preset")}
        print(f"[목록] {d.name}: " + " · ".join(f"{k} {v}" for k, v in stats[d.name].items() if v))
    return stats


def load(app: str | None = None) -> list[dict]:
    rows = []
    for f in sorted(OUT.glob("*.jsonl")):
        if app and f.stem != app:
            continue
        rows += [json.loads(ln) for ln in f.read_text("utf-8").splitlines() if ln.strip()]
    return rows


def _concepts(q: str) -> list[list[str]]:
    """검색어 낱말마다 한 '뜻' — 한국어 낱말은 영어 검색어 여러 개로 넓힌다(그중 하나만 맞아도 그 뜻은 맞음)"""
    out = []
    for w in (w.lower() for w in re.findall(r"[\w.]+", q)):
        alts = [w] if re.search(r"[a-z0-9]", w) else []
        keys = [k for k in KO if k in w]
        keys = [k for k in keys if not any(k != o and k in o for o in keys)]     # '곡선' 이 맞으면 그 안의 '선' 은 빼기
        for k in keys:
            alts += KO[k].split()
        if alts:
            out.append(alts)
    return out


_PROBE: dict = {}


def probe(app: str, cid: str) -> dict:
    """engine/craft/probe.py 의 시험 결과(조건 · 실행 결과 · 오류 문구 · 견본 그림) — 없으면 {}"""
    if app not in _PROBE:
        f = ROOT / ".claude" / "skills" / "crafts" / "probe" / f"{app}.jsonl"
        _PROBE[app] = {}
        if f.exists():
            for ln in f.read_text("utf-8").splitlines():
                try:
                    r = json.loads(ln)
                    _PROBE[app][r["id"]] = r
                except (ValueError, KeyError):
                    pass
    return _PROBE[app].get(cid) or {}


def probe_note(app: str, cid: str) -> str:
    r = probe(app, cid)
    if not r:
        return ""
    bits = []
    st = r.get("states") or {}
    no = {k: v for k, v in st.items() if v is not True}
    yes = [k for k, v in st.items() if v is True]
    if st and no:
        bits.append(f"되는 상태: {', '.join(yes) or '없음'}" + (f" · 안 될 때: {next(iter(set(map(str, no.values()))))}" if no else ""))
    run = r.get("run")
    if run == "ok":
        bits.append("견본에서 실행됨" + (" · 화면 바뀜 " + r["thumb"] if r.get("visible") and r.get("thumb") else " · 기본값으로는 화면 변화 없음" if "visible" in r else ""))
    elif run in ("needs_params", "needs_context", "error", "timeout"):
        bits.append(f"{run}: {(r.get('msg') or '')[-160:]}")
    return " | ".join(bits)


def search(q: str, app: str | None = None, n: int = 15) -> list[tuple[float, dict]]:
    """맞은 뜻의 수가 먼저(여러 뜻을 함께 맞춘 항목이 위), 같으면 이름 · 라벨에 맞은 것이 위"""
    cons = _concepts(q)
    ql = q.lower()
    scored = []
    for r in load(app):
        head = f"{r['id']} {r['label']}".lower()
        rest = f"{r['menu']} {r['params']} {r['summary']}".lower()
        hit, s = 0, 0.0
        label = str(r.get("label") or "").lower().strip(" .…")
        for alts in cons:
            best = max((10.0 if re.search(rf"\b{re.escape(t)}", head) else 2.0 if re.search(rf"\b{re.escape(t)}", rest) else 0.0) for t in alts)
            if best:
                hit += 1
                s += best
                s += 1.5 * (sum(1 for t in alts if re.search(rf"\b{re.escape(t)}", head)) - 1 if best >= 10 else 0)   # 'Drop Shadow' 처럼 한 뜻의 낱말을 여럿 맞춤
                if label in alts or label == " ".join(alts[:2]):
                    s += 6.0                                                                    # 이름이 검색어 그 자체('Glow' · 'Shake' · 'Arrow')
        if hit:
            if hit < len(cons):                      # 뜻을 일부만 맞춘 항목은 덜(모든 뜻을 맞춘 항목이 위)
                s *= 0.6
            s += 3.0 if r["kind"] in ("effect", "preset") else 0.0     # 화면을 바꾸는 효과 · 프리셋 먼저(명령은 대개 조작 · 설정)
            s += APP_PRIOR.get(r["app"], 0.0)
            if any(w in ql for w in APP_WORDS.get(r["app"], ())):
                s += 8.0
            if r["kind"] == "command" and UI_CMD.search(r["id"]):
                s -= 6.0
            if ".obsolete." in r["id"]:
                s -= 5.0
            if (".audio." in r["id"] or r["app"] == "soundcraft") and not re.search(r"소리|음향|오디오|audio|sound|voice|목소리", ql):
                s -= 5.0                                 # 화면 효과를 찾는데 소리 효과가 위로 오지 않게('wave distortion' → 오디오 왜곡)
            scored.append((s, r))
    scored.sort(key=lambda x: (-x[0], x[1]["kind"] == "command", x[1]["app"], x[1]["id"]))
    return scored[:n]


def used() -> dict[str, dict[str, int]]:
    """재료 기록(data/compositions/<id>/craft/materials/sNN/*.json)의 "app" · "steps_run" · "features" 와 craft.json 의 단계 기록 → {앱: {기능 id: 횟수}}"""
    out: dict[str, dict[str, int]] = {}

    def add(app, fid):
        if app and fid:
            out.setdefault(app, {}).setdefault(fid, 0)
            out[app][fid] += 1
    for f in ROOT.glob(COVER_GLOB):
        try:
            r = json.loads(f.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(r, dict):
            continue
        for k in ("steps_run", "features"):
            for x in r.get(k) or []:
                if isinstance(x, dict):
                    add(x.get("app") or r.get("app"), x.get("id"))
                else:
                    add(r.get("app"), str(x))
        if r.get("editable") and r.get("app") and not r.get("steps_run"):     # 고정 어댑터 재료: 편집 파일에 남은 기능
            for fid in scan_file(r["app"], ROOT / r["editable"]):
                add(r["app"], fid)
        for stage in ("audio", "edit", "motion"):
            st = r.get(stage) if isinstance(r.get(stage), dict) else None
            for x in (st or {}).get("features") or []:
                add(st.get("app"), x if isinstance(x, str) else x.get("id"))
    sid_glob = COVER_GLOB.split("/")[1]
    for app, f in stage_files(sid_glob):
        for fid in scan_file(app, f):
            add(app, fid)
    return out


COVER_GLOB = "data/compositions/*/craft/**/*.json"
_IDS: dict[str, set] = {}


def _ids(app: str) -> set:
    if app not in _IDS:
        _IDS[app] = {r["id"] for r in load(app) if len(r["id"]) >= 3}
    return _IDS[app]


def scan_file(app: str, f: Path) -> set[str]:
    """단계가 남긴 파일(motion.jsx · .scraft · .fcproj · 편집 파일) 안에 따옴표로 나오는 이름 중 그 앱의 명령 · 효과 · 프리셋 id"""
    try:
        if not f.is_file() or f.stat().st_size > 20 * 1024 * 1024:
            return set()
        t = f.read_text("utf-8", errors="ignore")
    except OSError:
        return set()
    toks = set(re.findall(r"[\"']([A-Za-z][\w.\-]{2,80})[\"']", t))
    return toks & _ids(app)


def stage_files(sid_glob: str = "*") -> list[tuple[str, Path]]:
    """영상별 단계 파일 → (앱, 파일)"""
    out = [("effectcraft", f) for f in ROOT.glob(f"data/workspace/render/{sid_glob}/craft/*/motion.jsx")]
    out += [("soundcraft", f) for f in ROOT.glob(f"data/compositions/{sid_glob}/craft/audio/*.scraft")]
    out += [("filmcraft", f) for f in ROOT.glob(f"data/compositions/{sid_glob}/craft/edit/*.fcproj")]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    sub.add_parser("stats")
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("--app"); s.add_argument("--n", type=int, default=15)
    sh = sub.add_parser("show"); sh.add_argument("app"); sh.add_argument("id")
    cv = sub.add_parser("coverage"); cv.add_argument("--id", help="이 영상만")
    a = ap.parse_args()
    if a.cmd == "build":
        st = build()
        print(f"앱 {len(st)}개 · 항목 {sum(sum(v.values()) for v in st.values())}개 → {OUT.relative_to(ROOT)}")
        return 0 if st else 1
    if a.cmd == "stats":
        rows = load()
        by: dict = {}
        for r in rows:
            by.setdefault(r["app"], {}).setdefault(r["kind"], 0)
            by[r["app"]][r["kind"]] += 1
        for k, v in sorted(by.items()):
            print(f"{k:15s} " + " · ".join(f"{kk} {vv}" for kk, vv in v.items()))
        print(f"합계 {len(rows)}")
        return 0
    if a.cmd == "coverage":
        global COVER_GLOB
        if a.id:
            COVER_GLOB = f"data/compositions/{a.id}/craft/**/*.json"
        u, rows = used(), load()
        total: dict[str, int] = {}
        for r in rows:
            total[r["app"]] = total.get(r["app"], 0) + 1
        for app in sorted(total):
            fs = u.get(app, {})
            pct = 100 * len(fs) / total[app]
            top = ", ".join(f"{k}×{v}" for k, v in sorted(fs.items(), key=lambda x: -x[1])[:6])
            print(f"{app:15s} {len(fs):4d}/{total[app]:<5d} ({pct:4.1f}%)  {top or '— 안 씀'}")
        print("기록은 재료 · 단계 기록의 steps_run / features 칸 — 어댑터가 쓴 기능을 남겨야 보인다")
        return 0
    if a.cmd == "show":
        hit = [r for r in load(a.app) if r["id"] == a.id]
        if not hit:
            print("없음 — search 로 찾으세요")
            return 1
        for r in hit:
            print(json.dumps(r, ensure_ascii=False, indent=1))
            pr = probe(r["app"], r["id"])
            if pr:
                print("시험(engine/craft/probe.py): " + json.dumps({k: v for k, v in pr.items() if k not in ("id", "kind", "label", "menu")}, ensure_ascii=False, indent=1))
        return 0
    res = search(a.query, a.app, a.n)
    if not res:
        print("없음 — 영어 낱말로도 찾아보세요(앱 기능 이름은 영어)")
        return 1
    for s_, r in res:
        p = (r["params"] or "")[:140]
        print(f"{r['app']:12s} {r['kind']:7s} {r['id']:38s} {r['label'][:40]:40s} {p}")
        note = probe_note(r["app"], r["id"])
        if note:
            print(f"{'':12s} ↳ 시험: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
