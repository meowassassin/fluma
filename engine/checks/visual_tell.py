#!/usr/bin/env python3
"""화면 AI 티 검사 — 장면 코드(data/compositions/<id>/scenes/*.jsx)만 읽어 렌더 없이 몇 초 안에 잰다(2026-11-21).

기준은 AI 티가 없다고 고른 레퍼런스 쇼츠 13편(설명 애니메이션 · 손그림 · 스톱모션 · 편집 모션그래픽, 한 채널 3편 이하)을
shorts_xray 로 잰 값과 우리 영상 실측을 나란히 놓고 정했다:
  어두운 바탕 비율   레퍼런스 0~32%  · 우리 92%      바탕이 장면마다 바뀌는 비율  50~90% · 우리 15%
  카메라 줌 · 이동    13편 중 9편     · 우리 0        빛번짐(glow)               1편 한 단어 · 우리 장면당 1.3번
  화면 글자(10초당)  설명형 1~4.6번 · 우리 6.4번     최근 장면 59개: pop 166 · glow 75 · shake 22 · draw 3
레퍼런스는 핵심어를 그 물건 옆 라벨(손글씨 · 스탬프)로 붙이고, 자막은 상자 없이 작은 흰 글자, 움직임은 뜻이 있는 동작이다.
특정 화풍을 정하지 않는다 — 한 영상 안에서 같은 장치만 되풀이하는 것(단조로움)과 의미 없는 꾸밈을 잰다.

  python3 engine/checks/visual_tell.py data/storyboards/<id>.json     # 찾은 것(JSON)
막음(block)은 produce 가 빌드 직후 · LLM 검토 전에 멈춘다(렌더 · 검토를 낭비하지 않게). 면제는 사용자 말이 있을 때만(waivers).
"""
from __future__ import annotations

import colorsys
import json
import re
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())

NUM = r"-?\d+(?:\.\d+)?"


def _rgb(h: str):
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def _bg(code: str):
    """K.scene(초, '#hex' | ['#위', '#아래']) → (초, 평균 rgb | None)"""
    m = re.search(r"K\.scene\(\s*(" + NUM + r")\s*(?:,\s*(\[[^\]]*\]|'[^']*'|\"[^\"]*\"))?", code)
    if not m:
        return None, None
    sec = float(m.group(1))
    cols = re.findall(r"#[0-9a-fA-F]{3,6}\b", m.group(2) or "")
    if not cols:
        return sec, _rgb("#101218")                      # 옛 기본값(어두운 남색)
    rgbs = [_rgb(c) for c in cols]
    return sec, [sum(c[i] for c in rgbs) / len(rgbs) for i in range(3)]


def _group(rgb):
    h, l, s = colorsys.rgb_to_hls(*rgb)
    lb = 0 if l < 0.22 else 1 if l < 0.62 else 2
    return ("무채", lb) if s < 0.15 or l < 0.08 else (round(h * 12) % 12, lb)


def _covered(code: str) -> bool:
    """화면을 덮는 실제 자료(이미지 · 영상)가 바탕을 가리는 장면 — 바탕색 통계에서 뺀다"""
    for m in re.finditer(r"K\.image\(([^;]*?),\s*(" + NUM + r")\s*,\s*(" + NUM + r")\s*,\s*(" + NUM + r")\s*\)", code):
        if ".anim/" in m.group(1):
            continue
        if float(m.group(4)) >= 95 and abs(float(m.group(2)) - 540) < 120:
            return True
    return "K.footage(" in code or "fullscreen" in code


def _anim_json(sid: str, code: str) -> list[dict]:
    out = []
    for name in re.findall(r"([\w-]+)\.anim/", code):
        p = ROOT / "data" / "compositions" / sid / "forms" / f"{name}.json"
        try:
            out.append(json.loads(p.read_text("utf-8")))
        except Exception:  # noqa: BLE001
            pass
    return out


def _camera_moves(code: str, anims: list[dict]) -> bool:
    if re.search(r"K\.S\([^)]*\)\.setValueAtTime", code) or re.search(r"\bcam\w*\s*=", code, re.I):
        return True
    for a in anims:                                       # 따라가기(follow)는 인물을 화면 같은 자리에 붙잡아 둘 뿐 — 샷이 바뀌는 카메라로 세지 않는다
        if ((a.get("anim") or {}).get("tracks") or {}).get("camera"):
            return True
    return False


def measure(sid: str) -> list[dict]:
    d = ROOT / "data" / "compositions" / sid / "scenes"
    files = sorted(d.glob("s*.jsx"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
    rows = []
    for f in files:
        code = f.read_text("utf-8", errors="ignore")
        sec, rgb = _bg(code)
        anims = _anim_json(sid, code)
        chars = [(float(x), float(y), float(s)) for x, y, s in
                 re.findall(r"K\.image\([^;]*?\.anim/[^;]*?,\s*(" + NUM + r")\s*,\s*(" + NUM + r")\s*,\s*(" + NUM + r")\s*\)", code)]
        rows.append({
            "scene": int(re.sub(r"\D", "", f.stem) or 0), "sec": sec or 0.0, "bg": rgb, "covered": _covered(code),
            "glow": len(re.findall(r"glow|ADBE Glo2", code, re.I)), "shake": code.count("K.shake("), "pop": code.count("K.pop("),
            "cards": len(re.findall(r"K\.shape\(\s*'rect'[^;]*round\s*:\s*[1-9]", code)),
            "texts": code.count("K.text("), "camera": _camera_moves(code, anims), "chars": chars,
        })
    return rows


def find(sb: dict, sid: str) -> list[dict]:
    rows = measure(sid)
    scs = sb.get("scenes") or []
    for r in rows:                                        # 감독 샷 기능 · 확대 박자 · 스틸 움직임도 카메라(motion.py 가 카메라 Null 에 키를 넣는다)
        sc = scs[r["scene"] - 1] if 0 < r["scene"] <= len(scs) else {}
        if str(sc.get("shot_fn") or "") in ("충격", "변화", "디테일") or any((b or {}).get("do") == "확대" for b in sc.get("beats") or []) \
                or (sc.get("visual") or {}).get("motion") in ("kenburns_in", "kenburns_out", "pan_left", "pan_right"):
            r["camera"] = True
    n = len(rows)
    if n < 3:
        return []
    out = []

    def add(code, scene, msg, block):
        out.append({"code": code, "scene": scene, "msg": msg, "block": block})

    bgs = [r for r in rows if r["bg"] is not None and not r["covered"]]
    if len(bgs) >= 3:
        dark = [r["scene"] for r in bgs if colorsys.rgb_to_hls(*r["bg"])[1] < 0.22]
        if len(dark) / len(bgs) > 0.5:
            add("V01", None, f"어두운 바탕이 {len(dark)}/{len(bgs)}장면(장면 {', '.join(map(str, dark[:8]))}) — 레퍼런스 13편은 0~32%. "
                "'테크 영상' 남색 · 검정 기본값이 AI 티의 첫인상이다 → 장면 내용의 장소 · 물건 색에서 바탕을 고른다(K.scene 두 번째 인자)", True)
        groups = {_group(r["bg"]) for r in bgs}
        if len(bgs) >= 5 and len(groups) / len(bgs) < 0.35:
            add("V02", None, f"바탕색이 {len(bgs)}장면 동안 {len(groups)}가지뿐 — 레퍼런스는 단계가 넘어갈 때 바탕을 통째로 바꾼다(컷의 50~90%). "
                "이야기의 장 · 장소가 바뀌는 장면에서 바탕을 바꾼다", True)
    glow = [r["scene"] for r in rows if r["glow"]]
    if len(glow) / n > 0.2:
        add("V03", None, f"빛번짐(glow)이 {len(glow)}/{n}장면 — 레퍼런스 13편 중 한 편이 한 단어에만 썼다. 빛나는 글자 · 카드는 AI 티 → 빼고, "
            "강조는 크기 · 색 대비 · 그 물건에 붙인 라벨로", True)
    sh = sum(r["shake"] for r in rows)
    if sh > 2:
        add("V04", None, f"흔들기(K.shake) {sh}번 — 레퍼런스는 흔들림이 거의 없다. 놀람 · 경고는 표정 · 멈춤 · 소리로", False)
    card_sc = [r["scene"] for r in rows if r["cards"] >= 2]
    if len(card_sc) / n > 0.5:
        add("V05", None, f"둥근 카드 · 알약이 두 개 이상인 장면이 {len(card_sc)}/{n} — 앱 UI 부품을 화면에 띄운 모양(AI 티). "
            "정보는 장면 속 실제 물건(전광판 · 탑승권 · 표지판 · 손글씨 라벨)에 쓰고, 상자는 그 물건을 닮게", True)
    total = sum(r["sec"] for r in rows) or 1.0
    dens = sum(r["texts"] for r in rows) / total * 10
    if dens > 7:
        add("V06", None, f"화면 글자 {dens:.1f}번/10초(자막 제외) — 레퍼런스 설명형은 1~4.6번. 말이 하는 것을 글자로 또 쓰지 말고 핵심어 하나만 그 물건 옆에",
            dens > 10)
    if n >= 4 and not any(r["camera"] for r in rows):
        add("V07", None, f"{n}장면 동안 카메라가 한 번도 움직이지 않는다 — 레퍼런스 13편 중 9편이 줌 · 크기 비교로 장면을 옮긴다. "
            "이유 있는 카메라(다가가 숫자를 보여 줌 · 물러나 전체를 드러냄 · 따라가기)를 장면 묶음(cam 부모 레이어 크기 · 위치 키)이나 "
            "형태 anim 의 camera 트랙(focus 'hero.head' · radius)으로", True)
    chars = [(r["scene"], c) for r in rows for c in r["chars"][:1]]
    if len(chars) >= 3:
        med = [sorted(c[k] for _, c in chars)[len(chars) // 2] for k in range(3)]
        same = [sc for sc, c in chars if abs(c[0] - med[0]) < 130 and abs(c[1] - med[1]) < 120 and abs(c[2] / med[2] - 1) < 0.18]
        if len(same) / len(chars) >= 0.75:
            add("V08", None, f"주인공 그림이 {len(same)}/{len(chars)}장면에서 같은 자리 · 크기(약 x {med[0]:.0f}, y {med[1]:.0f}, {med[2]:.0f}%) — 같은 구도 반복. "
                "샷 크기(전신 · 상반신 · 얼굴 · 손)와 자리(3분할 · 프레임 가장자리 · 전경)를 장면마다 바꾼다(형태 anim 의 camera radius · azimuth)", True)
    pops = sum(r["pop"] for r in rows)
    if pops / n > 3:
        add("V09", None, f"튀어나오기(K.pop) 장면당 {pops / n:.1f}번 — 모든 요소가 같은 방식으로 튀어나오면 기계적이다. 말에서 그 물건이 나오는 순간에만, "
            "나머지는 뜻이 있는 동작(놓이기 · 그려지기 · 따라 움직이기)으로", False)
    return out


def main() -> int:
    p = Path(sys.argv[1])
    sb = json.loads(p.read_text("utf-8"))
    sid = sb.get("id") or p.stem
    print(json.dumps({"measure": measure(sid), "found": find(sb, sid)}, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
