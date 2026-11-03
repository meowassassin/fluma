#!/usr/bin/env python3
"""화풍 시스템 만들기 — 참고 쇼츠(그림 위주)에서 화풍을 숫자로 재서 styles/<이름>/STYLE.md + style.json 으로.

open-design 의 DESIGN.md 처럼, 모든 그림이 읽는 계약이다. 숫자는 손으로 정하지 않는다.

  python3 scripts/style_card.py <영상 id> [<영상 id> …] [--name 이름]

재는 것
  palette   역할별 색: bg(바탕) · main(주조) · main_dark · accent(강조) · accent2 · light · dark · white · black
            프레임 픽셀을 k-평균으로 묶고, 테두리에 많은 색 = 바탕, 바탕 아닌 넓고 채도 있는 색 = 주조, 좁고 쨍한 색 = 강조
  values    명도 구조: 어둠 · 중간 · 밝음 넓이 비율
  outline   어두운 가는 선이 윤곽에 있는지(외곽선 화풍)
  shade     주조색과 같은 색상 · 다른 밝기 무리가 있는지 → 명암 단계 수, 그림자 색 이동(색상 · 채도 · 밝기)
  subject · detail   style_match 와 같은 값(주인공 크기 · 잔무늬 밀도)
자막 · 글자 영역(xray 의 text 상자)은 재지 않는다. 레퍼런스 그림을 따오지 않는다 — 숫자만 가져온다.
"""
from __future__ import annotations

import argparse
import colorsys
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
XR = ROOT / "public" / "trends" / "xray"
STYLES = ROOT / "styles"
W = 240


def frames(vid: str, n: int = 14) -> list[tuple[np.ndarray, np.ndarray]]:
    """(RGB 0~1 배열, 잴 칸 가림막) 목록 — 글자 상자와 자막 띠는 뺀다"""
    xr = json.loads((XR / vid / "xray.json").read_text("utf-8"))
    dur = float(xr["video"]["duration"])
    src = XR / vid / "src.mp4"
    out = []
    with tempfile.TemporaryDirectory() as d:
        for i in range(n):
            t = 0.6 + (dur - 1.2) * i / max(1, n - 1)
            f = Path(d) / f"{i}.png"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1", "-vf", f"scale={W}:-1", str(f)], check=True)
            a = np.asarray(Image.open(f).convert("RGB"), dtype=float) / 255
            h, w = a.shape[:2]
            keep = np.ones((h, w), bool)
            for tb in xr.get("text") or []:
                if tb["start"] - 0.2 <= t <= tb["end"] + 0.2:
                    x, y, bw, bh = tb["box"]
                    x0, y0 = max(0, int((x - 0.02) * w)), max(0, int((y - 0.02) * h))
                    keep[y0:int((y + bh + 0.02) * h), x0:int((x + bw + 0.02) * w)] = False
            out.append((a, keep))
    return out


def kmeans(X: np.ndarray, k: int, iters: int = 25, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    C = X[rng.choice(len(X), k, replace=False)]
    for _ in range(iters):
        lab = np.argmin(((X[:, None, :] - C[None]) ** 2).sum(-1), axis=1)
        C2 = np.array([X[lab == j].mean(0) if (lab == j).any() else C[j] for j in range(k)])
        if np.allclose(C, C2, atol=1e-4):
            break
        C = C2
    return C, lab


def hls(c) -> tuple[float, float, float]:
    return colorsys.rgb_to_hls(*[float(x) for x in c])


def hexc(c) -> str:
    return "#" + "".join(f"{int(round(max(0, min(1, x)) * 255)):02x}" for x in c)


def hue_dist(a: float, b: float) -> float:
    d = abs(a - b) % 1.0
    return min(d, 1 - d)


def measure(vids: list[str]) -> dict:
    fr = [x for v in vids for x in frames(v)]
    pix, border = [], []
    for a, keep in fr:
        pix.append(a[keep])
        b = np.zeros(keep.shape, bool)
        b[:6, :] = b[-6:, :] = True
        b[:, :6] = b[:, -6:] = True
        border.append(a[b & keep])
    P = np.vstack(pix)
    rng = np.random.default_rng(1)
    S = P[rng.choice(len(P), min(len(P), 60000), replace=False)]
    C, lab = kmeans(S, 10)
    share = np.bincount(lab, minlength=len(C)) / len(lab)
    B = np.vstack(border)
    blab = np.argmin(((B[:, None, :] - C[None]) ** 2).sum(-1), axis=1)
    bshare = np.bincount(blab, minlength=len(C)) / max(1, len(blab))
    info = [{"i": i, "c": C[i], "share": float(share[i]), "border": float(bshare[i]), "h": hls(C[i])[0], "l": hls(C[i])[1], "s": hls(C[i])[2]} for i in range(len(C))]

    bg = max(info, key=lambda x: x["border"] * 2 + x["share"])
    rest = [x for x in info if x is not bg]
    sat = [x for x in rest if x["s"] > 0.3 and 0.15 < x["l"] < 0.85]
    main = max(sat or rest, key=lambda x: x["share"])
    acc = sorted([x for x in sat if x is not main and hue_dist(x["h"], main["h"]) > 0.08], key=lambda x: (-x["s"] * (1 - x["share"]), -x["s"]))
    accent = acc[0] if acc else None
    accent2 = next((x for x in acc[1:] if hue_dist(x["h"], accent["h"]) > 0.08), None) if accent else None
    same = [x for x in rest if x is not main and hue_dist(x["h"], main["h"]) < 0.06 and abs(x["l"] - main["l"]) > 0.08]
    darker = [x for x in same if x["l"] < main["l"]]
    light = max(info, key=lambda x: x["l"])
    dark = min(info, key=lambda x: x["l"])

    def shifted(c, dl):
        h, l, s = hls(c)
        return colorsys.hls_to_rgb(h, max(0, min(1, l + dl)), s)

    pal = {
        "bg": hexc(bg["c"]), "main": hexc(main["c"]),
        "main_dark": hexc(min(darker, key=lambda x: x["l"])["c"]) if darker else hexc(shifted(main["c"], -0.14)),
        "accent": hexc(accent["c"]) if accent else hexc(shifted(main["c"], 0.2)),
        "accent2": hexc(accent2["c"]) if accent2 else hexc(shifted(bg["c"], 0.25)),
        "light": hexc(light["c"]) if light["l"] > 0.7 else "#f4f1e8",
        "dark": hexc(dark["c"]) if dark["l"] < 0.3 else "#23213a",
        "white": "#ffffff", "black": hexc(dark["c"]) if dark["l"] < 0.15 else "#14141f",
    }
    # 그림자 이동: 주조색과 같은 색상의 더 어두운 무리가 있으면 그 차이
    if darker:
        d = min(darker, key=lambda x: x["l"])
        dh = ((d["h"] - main["h"] + 0.5) % 1.0) - 0.5
        shade = {"tones": 2, "shift": {"h": round(abs(dh), 3), "s": round(d["s"] - main["s"], 3), "l": round(d["l"] - main["l"], 3)}}
    else:
        shade = {"tones": 1}
    # 명도 구조
    L = 0.2126 * S[:, 0] + 0.7152 * S[:, 1] + 0.0722 * S[:, 2]
    values = {"dark": round(float((L < 0.33).mean()), 3), "mid": round(float(((L >= 0.33) & (L < 0.66)).mean()), 3), "light": round(float((L >= 0.66).mean()), 3)}
    # 외곽선: 윤곽(밝기 기울기 큰 곳) 중 아주 어두운 픽셀 비율
    dark_edge = []
    for a, keep in fr:
        l = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
        gy, gx = np.gradient(l)
        edge = (np.hypot(gx, gy) > 0.08) & keep
        if edge.any():
            dark_edge.append(float((l[edge] < 0.14).mean()))
    outline = bool(np.mean(dark_edge) > 0.35) if dark_edge else False
    return {"palette": pal, "shade": shade, "values": values, "outline": {"on": outline, "width": 0.025, "color": "dark"},
            "clusters": [{"hex": hexc(x["c"]), "share": round(x["share"], 3), "border": round(x["border"], 3)} for x in sorted(info, key=lambda x: -x["share"])]}


def write(name: str, vids: list[str], m: dict) -> Path:
    d = STYLES / name
    d.mkdir(parents=True, exist_ok=True)
    st = {"preset": "flat-bright", "system": name, "from": vids, "palette": {k: v for k, v in m["palette"].items() if k != "bg"},
          "bg": m["palette"]["bg"], "outline": m["outline"], "shade": {**{"light": 135, "depth": 0.12}, **m["shade"]}, "values": m["values"]}
    if m["shade"].get("tones", 1) < 2:
        st["shade"] = {"tones": 1}
    (d / "style.json").write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", "utf-8")
    sw = "\n".join(f"| {k} | `{v}` | " + ("바탕" if k == "bg" else "") + " |" for k, v in m["palette"].items())
    md = f"""# {name} — 화풍 시스템

참고 쇼츠 {", ".join(vids)} 에서 잰 값(`scripts/style_card.py`). 모든 그림이 이 계약을 읽는다 — 부품은 역할로만 색을 받는다.
그림 · 캐릭터를 따오지 않았다. 숫자와 규칙만 가져왔다. 보편 규칙은 `rules/illustration/`.

## 팔레트 (역할)
| 역할 | 색 | 비고 |
|---|---|---|
{sw}

## 명도 구조
어둠 {m['values']['dark']:.0%} · 중간 {m['values']['mid']:.0%} · 밝음 {m['values']['light']:.0%} — 주인공과 바로 뒤 배경은 밝기 차 0.25 이상.

## 선 · 명암
- 외곽선: {"있음(어두운 같은 색)" if m['outline']['on'] else "없음 — 면과 면의 색 차이로 형태를 나눈다"}
- 명암: {m['shade'].get('tones', 1)}단{(" · 그림자 이동 " + json.dumps(m['shade'].get('shift'), ensure_ascii=False)) if m['shade'].get('shift') else ""}

## 측정한 색 무리 (넓이순)
""" + "\n".join(f"- `{c['hex']}` 넓이 {c['share']:.0%} · 테두리 {c['border']:.0%}" for c in m["clusters"]) + "\n"
    (d / "STYLE.md").write_text(md, "utf-8")
    return d


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("vids", nargs="+")
    ap.add_argument("--name")
    a = ap.parse_args()
    name = a.name or f"ref-{a.vids[0]}"
    d = write(name, a.vids, measure(a.vids))
    print(json.dumps({"ok": True, "style": str((d / "style.json").relative_to(ROOT)), "doc": str((d / "STYLE.md").relative_to(ROOT))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
