#!/usr/bin/env python3
"""콘셉트 단계 — 콘티를 쓰기 전에 '이 분야에서 다들 하는 것'을 먼저 적고, 그것을 일부러 깨는 안을 벌려 사람이 고르게 한다.
레퍼런스는 리듬 · 훅 구조만 빌린다. 소재와 아이디어는 여기서 일부러 다르게 간다.
뻔한지 아닌지는 코드가 낱말 목록으로 재지 않는다 — 에이전트(Claude)가 레퍼런스 X-ray 를 보고 판단해 적고, 코드는 칸이 채워졌는지 · 레퍼런스가 실제로 분석됐는지 · 지난 영상과 겹치는지만 본다.

  python3 engine/story/concepts.py check <id>            # 안 검사(뻔함 지도 · 깨는 것 · 각도 · 한 방 · 근거 · 겹침)
  python3 engine/story/concepts.py sketch <id>           # 안마다 5초 시안 → data/out/concepts-<id>.mp4 · .png (몇 초)
  python3 engine/story/concepts.py pick <id> <번호|이름> <콘티.json>   # 사용자가 고른 안을 콘티 concept 에 넣는다 — 사용자가 고를 때만

안 파일: data/workspace/concepts/<id>.json
  {"topic": "…",
   "cliches": [{                                   # 뻔함 지도 — 레퍼런스 3~5편에서 다들 하는 것(3개 이상, 구조 · 제목 각 1개 이상)
     "kind": "구조|첫장면|제목|화면|말투|소리", "what": "고민 → 이점 나열 → 할인 CTA", "seen_in": ["<X-ray 한 영상 id>", …]}],
   "concepts": [{
     "name": "짧은 이름", "angle": ANGLES 중 하나,
     "promise": "시청자가 얻는 것 한 문장",
     "one_shot": "이 영상에만 있는 한 방 — 다른 영상이 못 하는 것",
     "hook": "첫 3초 말 또는 글자",
     "breaks": "cliches 의 what 그대로(또는 번호 1~) — 이 안이 일부러 깨는 것",
     "why_fresh": "왜 뻔하지 않은가 — 스스로 반박해 보고 남은 이유",
     "structure": "장면 흐름 한 줄(형식 기본 뼈대를 그대로 쓰지 않는다)",
     "evidence": "출처 URL · 직접 실험 계획 · 조사 필요",
     "trick": "화면 장치(어떤 앱 조합인가)",
     "beats": [{"big": "화면 글자", "note": "실제로 무엇이 보일지"}]   # 시안 2~4칸
  }]}
재미를 숫자로 채점하지 않는다 — 겹침 · 형식 위반만 재고, 고르는 것은 사람이다.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from result import fail, ok  # noqa: E402

STORE = ROOT / "data" / "workspace" / "concepts"
ANGLES = {"실험", "데이터", "반전", "역할극", "비유", "대결", "역사", "해부", "시점", "형식파괴"}
XRAY = ROOT / "data" / "public" / "trends" / "xray"
SIM_FAIL = 0.34     # 글자 세 묶음 겹침(자카드) — 이 이상이면 사실상 같은 말
NEED, MAX = 3, 5      # 2026-11-09: 6~8안은 기획을 늦췄다 — 서로 멀리 떨어진 3~4안이면 충분


def grams(t: str) -> set:
    t = re.sub(r"[\s\W_]+", "", str(t or "").lower())
    return {t[i:i + 3] for i in range(len(t) - 2)}


def sim(a: str, b: str) -> float:
    x, y = grams(a), grams(b)
    return len(x & y) / len(x | y) if x and y else 0.0


SIM_EMB = 0.9      # 뜻 비슷함(임베딩 코사인) — 이 이상이면 낱말이 달라도 사실상 같은 말


def same(a: str, b: str) -> bool:
    """사실상 같은 말인가 — 글자가 많이 겹치거나, '찾기 · 임베딩' 모델이 있으면 뜻이 같거나(낱말을 바꿔 쓴 뻔한 구조도 잡는다)"""
    if sim(a, b) >= SIM_FAIL:
        return True
    try:
        import embed
        v = embed.similar(a, b)
    except Exception:  # noqa: BLE001 — 키 없음 · 네트워크
        v = None
    return v is not None and v >= SIM_EMB


def past() -> list:
    """이미 만든 영상의 제목 · 첫 말 · 첫 화면 글자 — 같은 말을 되풀이하지 않게"""
    out = []
    for f in (ROOT / "data" / "storyboards").glob("*.json"):
        try:
            d = json.loads(f.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        s0 = (d.get("scenes") or [{}])[0]
        out += [(f.stem, x) for x in (d.get("title"), s0.get("narration"), s0.get("caption")) if x]
    return out


def check(d: dict, history: list | None = None, analyzed=None) -> tuple[list, list]:
    """(막는 문제, 알림). analyzed(id) → 그 영상이 X-ray 됐는가(기본: 파일 확인)"""
    analyzed = analyzed or (lambda r: (XRAY / str(r) / "xray.json").exists())
    bad, note = [], []
    cl = d.get("cliches") or []
    kinds = {c.get("kind") for c in cl}
    if len(cl) < 3:
        bad.append(f"뻔함 지도(cliches)가 {len(cl)}개 — 레퍼런스 X-ray 를 보고 이 분야에서 다들 하는 것 3개 이상(구조 · 제목 각 1개 이상)")
    for k in ("구조", "제목"):
        if cl and k not in kinds:
            bad.append(f"뻔함 지도에 '{k}' 가 없음")
    for c in cl:
        refs = c.get("seen_in") or []
        if not str(c.get("what") or "").strip():
            bad.append("뻔함 지도 한 칸의 what 이 비었음")
        elif not any(analyzed(r) for r in refs):
            bad.append(f"뻔함 '{str(c.get('what'))[:20]}': seen_in 에 X-ray 한 레퍼런스가 없음(짐작이 아니라 실제로 본 것)")
    whats = [str(c.get("what") or "").strip() for c in cl]
    cs = d.get("concepts") or []
    if not NEED <= len(cs) <= MAX:
        bad.append(f"안은 {NEED}~{MAX}개 — 지금 {len(cs)}개")
    seen: dict = {}
    broken = set()
    for c in cs:
        n = c.get("name") or "?"
        a = c.get("angle")
        if a not in ANGLES:
            bad.append(f"{n}: 각도 '{a}' 는 목록에 없음({' · '.join(sorted(ANGLES))})")
        seen[a] = seen.get(a, 0) + 1
        for k in ("promise", "one_shot", "hook", "breaks", "why_fresh", "structure", "evidence", "trick"):
            if not str(c.get(k) or "").strip():
                bad.append(f"{n}: {k} 가 비었음")
        b = str(c.get("breaks") or "").strip()
        if b:
            idx = int(b) - 1 if b.isdigit() else (whats.index(b) if b in whats else -1)
            if not 0 <= idx < len(whats):
                bad.append(f"{n}: breaks '{b[:20]}' 가 뻔함 지도에 없음(what 그대로 또는 번호)")
            else:
                broken.add(idx)
        if not 2 <= len(c.get("beats") or []) <= 4:
            bad.append(f"{n}: beats 는 2~4칸")
        if "조사 필요" in str(c.get("evidence") or ""):
            note.append(f"{n}: 근거를 아직 확인하지 않음 — 고르면 콘티 전에 조사")
        for sid, t in history if history is not None else past():
            if same(c.get("hook"), t):
                bad.append(f"{n}: 훅이 {sid} 의 '{str(t)[:24]}' 와 겹침")
        for w in whats:
            if same(c.get("hook"), w) or same(c.get("structure"), w):
                bad.append(f"{n}: 깨겠다는 뻔함 '{w[:20]}' 를 그대로 닮음")
    if cs and whats and len(broken) < min(3, len(whats)):
        bad.append(f"안들이 깨는 뻔함이 {len(broken)}가지뿐 — 서로 다른 것을 깨야 안이 벌어진다")
    if len([a for a in seen if a]) < min(3, len(cs)):          # 안마다 다른 각도(3안이면 3가지) — 비슷한 안 여럿보다 멀리 떨어진 3안
        bad.append(f"각도가 {len(seen)}가지뿐 — 안마다 다른 각도로(최소 {min(3, len(cs))}가지)")
    for a, k in seen.items():
        if k > 2:
            bad.append(f"각도 '{a}' 가 {k}개 — 2개까지")
    for i, x in enumerate(cs):
        for y in cs[i + 1:]:
            if same(x.get("hook"), y.get("hook")) or same(x.get("one_shot"), y.get("one_shot")):
                bad.append(f"{x.get('name')} · {y.get('name')}: 사실상 같은 안")
    return bad, note


def _load(cid: str) -> dict:
    f = STORE / f"{cid}.json"
    if not f.exists():
        fail("concepts", stage="concepts", error=f"안 파일이 없습니다: {f.relative_to(ROOT)}")
    return json.loads(f.read_text("utf-8"))


def _wrap(dr, text: str, font, width: int) -> list:
    out, cur = [], ""
    for ch in str(text):
        if dr.textlength(cur + ch, font=font) > width and cur:
            out.append(cur)
            cur = ""
        cur += ch
    return out + ([cur] if cur else [])


def card(c: dict, b: dict, k: int, i: int, n: int, W: int = 540, H: int = 960):
    """시안 한 칸 — 글자는 실제 크기, 아직 없는 그림은 회색 칸에 무엇이 들어갈지 적는다"""
    from PIL import Image, ImageDraw, ImageFont
    fo = ROOT / "engine" / "assets" / "fonts"
    big, mid, sm = (ImageFont.truetype(str(fo / f), s) for f, s in (("Pretendard-Black.otf", 58), ("Pretendard-Bold.otf", 26), ("Pretendard-Regular.otf", 24)))
    im = Image.new("RGB", (W, H), "#101218")
    d = ImageDraw.Draw(im)
    d.text((32, 34), f"안 {k}  {c['name']}", font=mid, fill="#ffd84d")
    d.text((32, 72), f"{c.get('angle')} · {i + 1}/{n}", font=sm, fill="#8a90a0")
    d.rounded_rectangle((32, 400, W - 32, 760), 18, fill="#2a2e38")
    y = 430
    for ln in _wrap(d, b.get("note", ""), sm, W - 104)[:12]:
        d.text((52, y), ln, font=sm, fill="#c9cdd6")
        y += 34
    y = 150
    for ln in _wrap(d, b.get("big", ""), big, W - 64)[:3]:
        d.text((32, y), ln, font=big, fill="#ffffff")
        y += 74
    d.text((32, 800), "한 방", font=sm, fill="#ffd84d")
    y = 836
    for ln in _wrap(d, c.get("one_shot", ""), sm, W - 64)[:3]:
        d.text((32, y), ln, font=sm, fill="#ffffff")
        y += 32
    return im


def sketch(cid: str, d: dict) -> tuple[Path, Path]:
    w = STORE / cid
    w.mkdir(parents=True, exist_ok=True)
    seq, thumbs = [], []
    for k, c in enumerate(d["concepts"], 1):
        bs = c["beats"]
        for i, b in enumerate(bs):
            f = w / f"c{k}b{i}.png"
            card(c, b, k, i, len(bs)).save(f)
            seq.append((f, 5.0 / len(bs)))
            if i == 0:
                thumbs.append(f)
    lst = w / "list.txt"
    lst.write_text("".join(f"file '{f}'\nduration {s:.3f}\n" for f, s in seq) + f"file '{seq[-1][0]}'\n", "utf-8")
    out = ROOT / "data" / "out" / f"concepts-{cid}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(out)], capture_output=True, text=True)
    if r.returncode != 0:
        fail("concepts", stage="concepts", error=r.stderr[-300:])
    png = out.with_suffix(".png")
    from PIL import Image
    cols = min(4, len(thumbs))
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 360, rows * 640), "#000000")
    for i, f in enumerate(thumbs):
        sheet.paste(Image.open(f).resize((356, 636)), ((i % cols) * 360, (i // cols) * 640))
    sheet.save(png)
    return out, png


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("check", "sketch"):
        sub.add_parser(n).add_argument("id")
    p = sub.add_parser("pick"); p.add_argument("id"); p.add_argument("which"); p.add_argument("storyboard")
    a = ap.parse_args()
    d = _load(a.id)
    if a.cmd == "pick":
        cs = d["concepts"]
        c = cs[int(a.which) - 1] if a.which.isdigit() and 1 <= int(a.which) <= len(cs) else next((x for x in cs if x.get("name") == a.which), None)
        if not c:
            fail("concepts", stage="concepts", error=f"그런 안이 없습니다: {a.which}")
        sp = Path(a.storyboard)
        sb = json.loads(sp.read_text("utf-8"))
        sb["concept"] = {k: c.get(k) for k in ("name", "angle", "promise", "one_shot", "breaks", "why_fresh", "structure", "trick", "evidence")}
        sb["concept"]["cliches"] = [c_.get("what") for c_ in d.get("cliches") or []]   # 제목 · 콘티를 쓸 때 피할 것
        sp.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", "utf-8")
        ok("concepts", picked=c["name"])
        return 0
    bad, note = check(d)
    if bad:
        fail("concepts", stage="concepts", error=" / ".join(bad[:12]), notes=note)
    if a.cmd == "check":
        ok("concepts", concepts=len(d["concepts"]), notes=note)
        return 0
    v, png = sketch(a.id, d)
    ok("concepts", video=v.relative_to(ROOT).as_posix(), sheet=png.relative_to(ROOT).as_posix(), notes=note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
