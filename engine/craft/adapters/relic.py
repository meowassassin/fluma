"""실제 유물 재료(relic) — 조각 · 흉상 · 도기 사진에서 형태를 그대로 가져와 컷아웃 인물로 쓴다. 사람이 빚고 그린 진짜 그림이라 그림 수준 문제가 없다.
  {"type": "relic", "id": "hd_talk0", "src": "data/public/archive/<영상>/hd.jpg",
   "crop": [x0, y0, x1, y1],          # 0~1
   "cut": "matte" | "ink" | "shard" | "none",   # 배경 제거 / 도기의 검은 안료만 / 깨진 도기 조각 모양 / 그대로
   "keep": [x, y],                    # ink: 이 점(0~1)에서 가장 가까운 덩어리만
   "shard": [[x, y], …],              # shard: 조각 윤곽(0~1)
   "erase": [[[x, y], …], …],         # 오린 뒤 지울 곳(0~1)
   "jaw": {"poly": [[x, y], …], "mouth": [[x, y], …], "hinge": [x, y], "dark": 88}}   # poly: 수염 · 턱 결을 따라 복사할 윤곽, mouth: 입술 틈(어둡게) — base · mouth · jaw 레이어
matte · shard 는 PhotoCraft 작업이고 레이어 PSD(<재료 id>.psd)가 남는다 — 사람이 고치면 다음 렌더가 그 파일을 쓴다.
결과는 투명 PNG. 말하는 인물은 motion-relic 레시피(EffectCraft 리그), 그 밖은 motion-cast 로 놓는다. 저작자 표시는 archive 와 같이 credits.txt 에 남긴다."""
from __future__ import annotations

import json
import shutil
from pathlib import Path


def _matte(im):
    from rembg import new_session, remove
    return remove(im.convert("RGB"), session=new_session("isnet-general-use")).convert("RGBA")


def _ink(im, keep):
    import cv2
    import numpy as np
    from PIL import Image
    n = np.asarray(im.convert("RGB")).astype(np.float32)
    m = (((n.mean(2) < 78) & (n[:, :, 0] - n[:, :, 2] < 55)).astype(np.uint8)) * 255
    m = cv2.medianBlur(m, 5)
    if keep:
        k, lab, stats, cen = cv2.connectedComponentsWithStats(m)
        H, W = m.shape
        big = [i for i in range(1, k) if stats[i, cv2.CC_STAT_AREA] > 800]
        near = [q for q in big if stats[q, 0] <= keep[0] * W <= stats[q, 0] + stats[q, 2] and stats[q, 1] <= keep[1] * H <= stats[q, 1] + stats[q, 3]]
        i = max(near or big, key=lambda q: stats[q, cv2.CC_STAT_AREA])       # 그 점을 품은 가장 큰 덩어리
        m = ((lab == i).astype(np.uint8)) * 255
    a = Image.new("RGBA", im.size, (23, 17, 12, 255))
    a.putalpha(Image.fromarray(cv2.GaussianBlur(m, (0, 0), 1)))
    return a


def _px(pts, w, h):
    return [[round(x * w, 1), round(y * h, 1)] for x, y in pts]


def _parts(P: str, psd: Path, base: Path, work: Path) -> dict:
    """PSD 레이어 → <재료 id>_base · _jaw · _mouth.png(같은 캔버스 크기, EffectCraft 리그가 겹쳐 쓴다)"""
    from ..materials import _run
    tmp = work / f"{base.stem}.layers"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    _run([P, "run", psd, "--cmd", "file.export.layersToFiles", "--params", json.dumps({"dir": str(tmp), "format": "png", "prefix": "p"})], work)
    got = {}
    for f in sorted(tmp.glob("*.png")):
        for name in ("base", "jaw", "mouth"):
            if name in f.stem.lower():
                dst = base.parent / f"{base.stem}_{name}.png"
                shutil.move(str(f), dst)
                got[name] = dst.name
    shutil.rmtree(tmp, ignore_errors=True)
    return got


def _craft_cut(m: dict, src: Path, out: Path, work: Path) -> dict:
    """PhotoCraft 로 오리기 · 턱 분리 — 레이어 PSD 가 남아 사람이 열어 고칠 수 있다.
    matte: Select Subject 마스크 · erase 는 올가미로 마스크에서 뺀다. shard: 올가미로 조각 모양. jaw: base · mouth(턱을 어둡게 한 입속) · jaw 세 레이어"""
    from PIL import Image
    from ..materials import ROOT, _hash, _load, _run, cli
    P = cli("photocraft")
    work.mkdir(parents=True, exist_ok=True)
    psd = out.with_suffix(".psd")
    old = _load(out.with_suffix(".json"))
    if psd.exists() and old.get("editable_hash") and _hash(psd) != old["editable_hash"]:     # 사람이 PSD 를 고쳤다 — 그 레이어를 쓴다
        _run([P, "convert", psd, out], work)
        parts = _parts(P, psd, out, work) if m.get("jaw") else {}
        return {"app": "photocraft", "editable": str(psd.relative_to(ROOT)), "editable_hash": _hash(psd), "edited_by_hand": True, "parts": parts, "size": list(Image.open(out).size)}
    W0, H0 = Image.open(src).size
    x0, y0, x1, y1 = m.get("crop") or [0, 0, 1, 1]
    cw, ch = int((x1 - x0) * W0), int((y1 - y0) * H0)
    tw = int(m.get("width") or cw)
    th = int(ch * tw / cw)
    if m.get("matte") == "ai" and m.get("cut", "matte") == "matte":
        pre = work / f"{m['id']}.matte.png"
        _matte(Image.open(src).convert("RGB").crop((int(x0 * W0), int(y0 * H0), int(x1 * W0), int(y1 * H0)))).save(pre)
        src, x0, y0, W0, H0 = pre, 0, 0, cw, ch
    a = [P, "run", src]

    def c(cid, params=None):
        a.extend(["--cmd", cid] + (["--params", json.dumps(params, ensure_ascii=False)] if params is not None else []))
    c("image.crop", {"x": int(x0 * W0), "y": int(y0 * H0), "width": cw, "height": ch})
    c("image.imageSize", {"width": tw, "height": th})
    if m.get("cut", "matte") == "matte" and m.get("matte") != "ai":
        c("layer.removeBackground", {"refine": True})
        c("layer.layerMask.apply")
    elif m.get("cut", "matte") == "matte":
        pass                                         # 배경이 복잡해 Select Subject 가 옆 인물까지 잡는 사진 — 아래에서 미리 오린 그림을 연다
    else:
        c("layer.new.layerFromBackground", {"ifPresent": True})
        c("select.lasso", {"points": _px(m["shard"], tw, th), "feather": 1})
        c("layer.layerMask.revealSelection")
        c("select.deselect")
        c("layer.layerMask.apply")
    for poly in m.get("erase") or []:                # 마스크를 덮어쓰지 않게 적용한 뒤 픽셀에서 지운다
        c("select.lasso", {"points": _px(poly, tw, th), "feather": 2})
        c("edit.clear")
        c("select.deselect")
    c("layer.setProps", {"name": "base"})
    j = m.get("jaw")
    if j:
        c("select.lasso", {"points": _px(j["poly"], tw, th), "feather": 3})
        c("layer.new.layerViaCopy")                  # 자르지 않고 복사 — 아래에 원본 수염이 남아 턱이 움직여도 입 말고는 틈이 없다
        c("layer.setProps", {"name": "jaw"})
        c("layer.select", {"name": "base"})
        c("select.lasso", {"points": _px(j["mouth"], tw, th), "feather": 2})
        c("layer.new.layerViaCopy")
        c("layer.setProps", {"name": "mouth"})
        c("select.deselect")
        c("image.adjustments.hueSaturation", {"saturation": -30, "lightness": -int(j.get("dark", 88))})
    _run([*a, "--out", psd], work)
    _run([P, "convert", psd, out], work)
    info = {"app": "photocraft", "editable": str(psd.relative_to(ROOT)), "editable_hash": _hash(psd), "size": [tw, th]}
    if j:
        info["parts"] = _parts(P, psd, out, work)
        info["jaw_hinge"] = j.get("hinge")
    return info


def relic(m: dict, out: Path, work: Path) -> dict:
    from PIL import Image, ImageChops, ImageDraw
    from ..materials import ROOT
    src = ROOT / m["src"]
    cut = m.get("cut", "matte")
    if cut in ("matte", "shard"):
        return _craft_cut(m, src, out, work)
    im = Image.open(src).convert("RGBA")
    if m.get("crop"):
        x0, y0, x1, y1 = m["crop"]
        im = im.crop((int(x0 * im.width), int(y0 * im.height), int(x1 * im.width), int(y1 * im.height)))
    a = _ink(im, m.get("keep")) if cut == "ink" else im
    for poly in m.get("erase") or []:
        e = Image.new("L", a.size, 255)
        ImageDraw.Draw(e).polygon([(x * a.width, y * a.height) for x, y in poly], fill=0)
        a.putalpha(ImageChops.multiply(a.split()[3], e))
    if m.get("width"):
        a = a.resize((int(m["width"]), int(a.height * m["width"] / a.width)), Image.LANCZOS)
    a.save(out)
    return {"app": "fluma", "as": "image", "size": list(a.size)}


ADAPTERS = {"relic": relic}
