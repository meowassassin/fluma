"""LightCraft 어댑터 — 사진 현상 재료(type: photo_grade).

직접 찍은 사진 · 현장 스틸을 한 영상 안에서 같은 색감으로 맞추고 세로 화면에 맞게 자른다(비파괴 — 원본은 그대로).
한 번의 LightCraft 세션(run --import)에서: 룩(프리셋 + 슬라이더) → (선택) 자동 보정을 약하게 → 자르기 → 내보내기.
같은 look 을 쓴 재료는 모두 같은 설정이 걸린다 → 장면이 바뀌어도 색이 튀지 않는다.

콘티 칸:
  src       사진 경로(필수, jpg · png · RAW …)
  look      "warm" · "film" · "clean" · "mono"(Fluma 룩) 또는 LightCraft 프리셋 id "lc.warm-film" 등(기본 clean)
  strength  프리셋 세기 0~200(%, 기본 100)
  auto      true → 자동 보정(develop.auto)을 40% 세기로 더한다(clean 은 기본 true).
            자동값을 그대로 쓰면 대비 · 그림자가 과하다(시험: 대비 +68, 밝은 곳 -66) → 줄이고 상한을 둔다
  set       {"light.exposure": 0.3, …} 슬라이더 직접(마지막에 덮어씀, lightcraft-cli controls 의 id)
  crop      "9:16"(기본) · "4:5" · "1:1" · "16:9" · [w, h] · false(자르지 않음)
  focus     [x, y] 0~1 — 자를 때 가운데로 둘 곳(기본 [0.5, 0.5]: 인물이 왼쪽이면 [0.3, 0.5])
  width     내보낼 폭 px(기본 1080) — 작은 사진도 키운다(dontEnlarge=false)
  credit    출처 글(선택) — 오른쪽 위에 작은 워터마크(자막 · 아래 UI 를 피한다)

기록(info) 칸:
  app "lightcraft" · as "image" · look · preset · size [폭, 높이] · crop [x0, y0, x1, y1](0~1) · auto(더한 값)
  editable  현상 설정 JSON(work/<id>.lightcraft.json) — `lightcraft-cli render <원본> -o x.png --settings 이 파일` 로 그대로 다시 낼 수 있다
AI 마스크(하늘 · 피사체)는 모델이 필요해 쓰지 않는다(mask.add kind=sky 는 모델 없이도 ok 를 돌려줘 실패가 안 보인다).
"""
from __future__ import annotations

import json
from pathlib import Path

# Fluma 룩 = 내장 프리셋 + 몇 가지 슬라이더(JPEG 에선 프리셋만으로는 차이가 작아 조금 더한다 — 2026-11-05 시험)
LOOKS = {
    "warm": ("lc.warm-glow", {"wb.temp": 7300, "grading.highlights.hue": 40, "grading.highlights.sat": 18, "vignette.amount": -15}),
    "film": ("lc.warm-film", {"grading.shadows.hue": 200, "grading.shadows.sat": 12, "vignette.amount": -20}),
    "clean": ("lc.clean-studio", {"color.vibrance": 5, "effects.clarity": 8}),
    "mono": ("lc.bw-soft", {"light.contrast": 18, "vignette.amount": -12}),
}
RATIOS = {"9:16": (9, 16), "4:5": (4, 5), "1:1": (1, 1), "16:9": (16, 9), "3:4": (3, 4)}
# develop.auto 결과 키 → 슬라이더 id, 상한(절댓값). 세기 0.4 를 곱한 뒤 상한으로 자른다
AUTO = {"exposure": ("light.exposure", 0.6), "contrast": ("light.contrast", 15), "highlights": ("light.highlights", 30),
        "shadows": ("light.shadows", 30), "whites": ("light.whites", 15), "blacks": ("light.blacks", 15),
        "vibrance": ("color.vibrance", 8), "saturation": ("color.saturation", 8)}
AUTO_STRENGTH = 0.4


def _lines(out: str) -> list[dict]:
    res = []
    for ln in out.splitlines():
        try:
            o = json.loads(ln)
        except ValueError:
            continue
        if isinstance(o, dict) and "command" in o:
            res.append(o)
    return res


def _lc(args: list, work: Path) -> list[dict]:
    """lightcraft-cli run … → 명령마다 결과 줄. 실패한 명령이 있으면 RuntimeError"""
    from ..materials import _run, cli
    try:
        res = _lines(_run([cli("lightcraft"), "run", *args], work))
    except RuntimeError as e:
        raise RuntimeError(f"LightCraft 현상 실패: {str(e)[-300:]}") from e
    for o in res:
        if not o.get("ok"):
            raise RuntimeError(f"LightCraft {o.get('command')} 실패: {json.dumps(o.get('error'), ensure_ascii=False)[:200]}")
    return res


def look_of(look: str | None) -> tuple[str | None, dict]:
    """룩 이름 → (프리셋 id, 더할 슬라이더). 'lc.' 로 시작하면 그 프리셋만, 'none' 이면 아무것도"""
    look = (look or "clean").strip()
    if look in LOOKS:
        p, s = LOOKS[look]
        return p, dict(s)
    if look.startswith("lc."):
        return look, {}
    if look in ("none", "off", "원본"):
        return None, {}
    raise RuntimeError(f"모르는 look: {look} (warm · film · clean · mono · none 또는 lc.프리셋 — lightcraft-cli run presets.list)")


def crop_rect(size: tuple[int, int], crop, focus=None) -> list[float] | None:
    """사진 크기 · 비율 · 가운데 → 자를 사각형 [x0, y0, x1, y1](0~1). 비율이 이미 맞거나 crop=false 면 None.
    crop.aspect 는 뒤의 crop.set 에 덮여서(시험) 비율은 여기서 직접 계산한다"""
    if crop in (None, False, "none", "free", "원본"):
        return None
    if isinstance(crop, str):
        if crop not in RATIOS:
            raise RuntimeError(f"모르는 crop 비율: {crop} ({' · '.join(RATIOS)} · [w, h] · false)")
        rw, rh = RATIOS[crop]
    else:
        rw, rh = float(crop[0]), float(crop[1])
    W, H = size
    want = rw / rh
    have = W / H
    fx, fy = (list(focus) + [0.5, 0.5])[:2] if focus else (0.5, 0.5)
    if abs(want - have) < 0.005:
        return None
    if have > want:                                # 옆으로 넓다 → 폭을 줄인다
        w = want / have
        x0 = min(max(0.0, float(fx) - w / 2), 1.0 - w)
        return [round(x0, 6), 0.0, round(x0 + w, 6), 1.0]
    h = have / want                                # 위아래로 길다 → 높이를 줄인다
    y0 = min(max(0.0, float(fy) - h / 2), 1.0 - h)
    return [0.0, round(y0, 6), 1.0, round(y0 + h, 6)]


def auto_values(raw: dict, strength: float = AUTO_STRENGTH) -> dict:
    """develop.auto 결과 → 약하게 줄인 상대 조정 {슬라이더: 더할 값}"""
    out = {}
    for k, (cid, cap) in AUTO.items():
        v = raw.get(k)
        if isinstance(v, (int, float)) and v:
            d = max(-cap, min(cap, float(v) * strength))
            out[cid] = round(d, 3 if cid == "light.exposure" else 1)
    return out


def _size(src: Path) -> tuple[int, int]:
    try:
        from PIL import Image, ImageOps
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im)       # 세로로 찍은 폰 사진: 회전한 뒤 크기
            return im.size
    except Exception:  # noqa: BLE001  RAW 등 PIL 이 못 여는 사진 — 자르지 않고 LightCraft 가 정한 크기로
        return (0, 0)


def _exact(out: Path, width: int, crop) -> list | None:
    """잘린 폭이 픽셀로 딱 안 나뉘어 1080×1921 처럼 1~3px 어긋나면 가운데를 맞춰 정확한 크기로 → [폭, 높이]"""
    try:
        from PIL import Image
        with Image.open(out) as im:
            size = list(im.size)
            if not width or not crop:
                return size
            rw, rh = RATIOS[crop] if isinstance(crop, str) else (float(crop[0]), float(crop[1]))
            want = [width, round(width * rh / rw)]
            if size != want and abs(size[0] - want[0]) <= 3 and abs(size[1] - want[1]) <= 3:
                im.resize(want, Image.LANCZOS).save(out)
                size = want
            return size
    except Exception:  # noqa: BLE001
        return None


def photo_grade(m: dict, out: Path, work: Path) -> dict:
    """LightCraft: 룩(프리셋 + 슬라이더) → 자동 보정 약하게(선택) → 9:16 자르기 → PNG"""
    from ..materials import _abs, ROOT
    if not m.get("src"):
        raise RuntimeError("photo_grade 재료에는 src(사진 경로)가 필요합니다")
    src = _abs(m["src"])
    if not src.exists():
        raise RuntimeError(f"사진이 없습니다: {m['src']}")
    work.mkdir(parents=True, exist_ok=True)
    look = m.get("look") or "clean"
    preset, extra = look_of(look)
    extra.update({str(k): float(v) for k, v in (m.get("set") or {}).items()})

    cmds: list = []
    if preset:
        cmds += ["preset.apply", f"id={preset}", f"amount={float(m.get('strength', 100))}"]
    added = {}
    if m.get("auto", look == "clean"):
        # 자동 보정은 따로 한 번 돌려 값만 읽는다 → 룩 위에 약하게 더한다(develop.adjust 는 상대값)
        res = _lc(["--import", str(src), "develop.auto"], work)
        added = auto_values(next((o.get("result") or {} for o in res if o["command"] == "develop.auto"), {}))
        for cid, d in added.items():
            cmds += ["develop.adjust", f"control={cid}", f"delta={d}"]
    if extra:
        cmds += ["develop.set", "values=" + json.dumps(extra)]
    W, H = _size(src)
    rect = crop_rect((W, H), m.get("crop", "9:16"), m.get("focus")) if W else None
    if rect:
        cmds += ["crop.set", "rect=" + json.dumps(rect)]
    cmds += ["develop.get"]
    exp = ["app.export", f"path={out}", f"width={int(m.get('width', 1080))}", "dontEnlarge=false"]
    if m.get("credit"):
        exp.append("watermark=" + json.dumps({"text": str(m["credit"]), "anchor": "topRight", "size": 0.022, "opacity": 0.8, "inset": 0.04}, ensure_ascii=False))
    res = _lc(["--import", str(src), *cmds, *exp], work)
    if not out.exists():
        raise RuntimeError("LightCraft 가 사진을 내보내지 않았습니다")

    settings = next((o.get("result") for o in res if o["command"] == "develop.get"), None) or {}
    keep = work / f"{m['id']}.lightcraft.json"
    keep.write_text(json.dumps(settings, ensure_ascii=False, indent=1), "utf-8")
    try:
        ed = str(keep.relative_to(ROOT))
    except ValueError:
        ed = keep.name
    size = _exact(out, int(m.get("width", 1080)), m.get("crop", "9:16")) if rect else _exact(out, 0, None)
    return {"app": "lightcraft", "as": "image", "look": look, "preset": preset, "size": size,
            "crop": rect, "auto": added, "editable": ed}


ADAPTERS = {"photo_grade": photo_grade}
