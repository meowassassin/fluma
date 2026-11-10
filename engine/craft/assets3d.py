#!/usr/bin/env python3
"""3D 에셋 라이브러리 — 모델 · 재질 · 조명(HDRI)은 화풍에 맞는 라이브러리에서 가져오고, 동작 · 연출은 영상마다 새로 짠다(2026-11-10 사용자 결정).
코드로 상자 · 공부터 쌓던 3D 는 수준이 낮고 오래 걸렸다.

  python3 engine/craft/assets3d.py search <검색어> [--kind model|hdri|texture|material] [--n 12]   # Poly Haven · ambientCG(CC0)
  python3 engine/craft/assets3d.py get polyhaven:<id> [--res 1k]        # 모델(glTF+텍스처) · HDRI(.hdr) · 텍스처 세트
  python3 engine/craft/assets3d.py get ambientcg:<id> [--res 1K-JPG]    # PBR 재질(색 · 거칠기 · 노멀 …)
  python3 engine/craft/assets3d.py import <zip|폴더> --license CC0 --source "Kenney Mini Characters" --url https://kenney.nl/assets/mini-characters
        # 사용자가 받은 팩(Kenney · Quaternius · Sketchfab CC-BY …) — 기부 창 · 로그인 뒤에 있는 곳은 사람이 받아 온다
  python3 engine/craft/assets3d.py study blender-demo:eevee/mr_elephant/mr_elephant.blend
        # Blender 공식 데모(대부분 CC-BY-SA) — 영상에 넣지 않고 조명 · 색 관리 · 셰이더 설정만 배운다(설정 요약 JSON)
  python3 engine/craft/assets3d.py list                                  # 받아 둔 것 · 라이선스

화풍 → 고르는 곳(레퍼런스 나란히 보기 · 사용자 그림을 보고 에이전트가 정한다 — 콘티 direction.style3d)
  realistic  Poly Haven 모델 · HDRI · ambientCG 재질(CC0)
  lowpoly    Kenney · Quaternius 팩(CC0, import) + 단색 재질
  toon       어느 모델이든 + fluma3d.toon(물체, 색) 셰이딩 · 외곽선
  clay       어느 모델이든 + fluma3d.clay(물체) 재질 · 부드러운 HDRI
받은 파일: data/assets/3d/<출처>/<id>/ (+ CREDIT.txt — 영상 설명란에 출처). Blender 스크립트에서 F.asset(경로) · F.hdri(경로) · F.pbr(폴더).
CC-BY-SA · 비상업 라이선스는 영상에 넣지 않는다(공유 조건이 영상까지 번진다).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
LIB = ROOT / "data" / "assets" / "3d"
STUDY = ROOT / "data" / "assets" / "study"
UA = {"User-Agent": "Fluma/1.0 (3d asset fetch)"}
OK_IN_VIDEO = ("CC0", "CC-BY", "MIT", "Apache-2.0")


def _json(url: str):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60))


def _download(url: str, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r, open(dst, "wb") as f:
        shutil.copyfileobj(r, f)
    return dst


def _credit(d: Path, line: str, license_: str) -> None:
    (d / "CREDIT.txt").write_text(f"{line}\nlicense: {license_}\n", "utf-8")


def search(q: str, kind: str = "model", n: int = 12) -> list[dict]:
    q_l = q.lower()
    out = []
    if kind in ("model", "hdri", "texture"):
        t = {"model": "models", "hdri": "hdris", "texture": "textures"}[kind]
        d = _json(f"https://api.polyhaven.com/assets?t={t}")
        for k, v in d.items():
            toks = set(re.split(r"[\s_\-]+", " ".join([k, v.get("name", ""), *v.get("tags", []), *v.get("categories", [])]).lower()))
            if all(any(t == w or t.startswith(w) for t in toks) for w in q_l.split()):   # 낱말 단위(hand 가 chandelier 에 걸리지 않게)
                out.append({"id": f"polyhaven:{k}", "name": v.get("name"), "tags": v.get("tags", [])[:6], "license": "CC0",
                            "polycount": v.get("polycount"), "page": f"https://polyhaven.com/a/{k}"})
    if kind in ("material", "texture"):
        d = _json("https://ambientcg.com/api/v2/full_json?" + urllib.parse.urlencode({"type": "Material", "q": q, "limit": n, "sort": "Popular"}))
        for a in d.get("foundAssets", []):
            out.append({"id": f"ambientcg:{a['assetId']}", "name": a.get("displayName"), "tags": a.get("tags", [])[:6], "license": "CC0",
                        "page": f"https://ambientcg.com/view?id={a['assetId']}"})
    return out[:n]


def get(ref: str, res: str | None = None) -> Path:
    src, _, aid = ref.partition(":")
    if src == "polyhaven":
        files = _json(f"https://api.polyhaven.com/files/{aid}")
        info = _json(f"https://api.polyhaven.com/info/{aid}")
        d = LIB / "polyhaven" / aid
        if (d / "CREDIT.txt").exists():
            return d
        res = res or "1k"
        if "gltf" in files:                                       # 모델
            g = files["gltf"].get(res) or next(iter(files["gltf"].values()))
            g = g["gltf"]
            _download(g["url"], d / Path(g["url"]).name)
            for rel, f in (g.get("include") or {}).items():
                _download(f["url"], d / rel)
        elif "hdri" in files:                                     # HDRI
            h = files["hdri"].get(res) or next(iter(files["hdri"].values()))
            f = h.get("hdr") or h.get("exr")
            _download(f["url"], d / Path(f["url"]).name)
        else:                                                     # 텍스처 세트
            for mapname, by_res in files.items():
                if isinstance(by_res, dict) and res in by_res:
                    f = by_res[res].get("jpg") or by_res[res].get("png") or next(iter(by_res[res].values()))
                    if isinstance(f, dict) and f.get("url"):
                        _download(f["url"], d / Path(f["url"]).name)
        authors = ", ".join((info.get("authors") or {}).keys())
        _credit(d, f"{info.get('name', aid)} — {authors} — https://polyhaven.com/a/{aid}", "CC0")
        return d
    if src == "ambientcg":
        d = LIB / "ambientcg" / aid
        if (d / "CREDIT.txt").exists():
            return d
        a = _json("https://ambientcg.com/api/v2/full_json?" + urllib.parse.urlencode({"id": aid, "include": "downloadData"}))["foundAssets"][0]
        dl = a["downloadFolders"]["default"]["downloadFiletypeCategories"]["zip"]["downloads"]
        pick = next((x for x in dl if x["attribute"] == (res or "1K-JPG")), dl[0])
        z = _download(pick["fullDownloadPath"], d / "src.zip")
        with zipfile.ZipFile(z) as zf:
            for m in zf.namelist():
                if not m.endswith("/") and ".." not in m and not m.startswith("/"):
                    (d / Path(m).name).write_bytes(zf.read(m))
        z.unlink()
        _credit(d, f"{a.get('displayName', aid)} — ambientCG — https://ambientcg.com/view?id={aid}", "CC0")
        return d
    raise RuntimeError(f"모르는 출처: {src} (polyhaven · ambientcg — 다른 팩은 import)")


def import_pack(path: Path, license_: str, source: str, url: str = "") -> Path:
    """사용자가 받아 온 팩을 라이브러리에 들인다. 라이선스를 반드시 적는다 — 영상에 넣을 수 없는 라이선스면 거절"""
    lic = license_.strip()
    if not any(lic.upper().startswith(k.upper()) for k in OK_IN_VIDEO) or "SA" in lic.upper().split("-") or "NC" in lic.upper():
        raise RuntimeError(f"라이선스 {lic}: 영상에 넣을 수 있는 것은 {', '.join(OK_IN_VIDEO)}(공유 조건 SA · 비상업 NC 제외) — 공부만 하려면 study")
    name = "".join(c if c.isalnum() or c in "-_" else "-" for c in source.lower()).strip("-")[:60]
    d = LIB / "packs" / name
    d.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            for m in zf.namelist():
                if m.endswith("/") or ".." in Path(m).parts or m.startswith("/"):
                    continue
                if Path(m).suffix.lower() in (".glb", ".gltf", ".bin", ".fbx", ".obj", ".mtl", ".blend", ".png", ".jpg", ".jpeg", ".txt"):
                    t = d / m
                    t.parent.mkdir(parents=True, exist_ok=True)
                    t.write_bytes(zf.read(m))
    elif path.is_dir():
        shutil.copytree(path, d, dirs_exist_ok=True)
    else:
        raise RuntimeError("zip 또는 폴더를 주세요")
    _credit(d, f"{source} — {url}", lic)
    return d


STUDY_SCRIPT = r'''
import bpy, json, sys
sc = bpy.context.scene
out = {"engine": sc.render.engine, "fps": sc.render.fps, "view_transform": sc.view_settings.view_transform, "look": sc.view_settings.look,
       "exposure": sc.view_settings.exposure, "film_transparent": sc.render.film_transparent}
try:
    ee = sc.eevee
    out["eevee"] = {k: getattr(ee, k) for k in ("use_raytracing", "taa_render_samples", "use_shadows", "use_volumetric_shadows", "volumetric_tile_size") if hasattr(ee, k)}
except Exception:
    pass
w = sc.world
if w and w.use_nodes:
    out["world"] = [n.bl_idname for n in w.node_tree.nodes]
out["lights"] = [{"type": o.data.type, "energy": round(o.data.energy, 2), "color": [round(c, 3) for c in o.data.color],
                  "size": round(getattr(o.data, "shadow_soft_size", 0), 3), "loc": [round(v, 2) for v in o.location]}
                 for o in sc.objects if o.type == "LIGHT"]
cams = [o for o in sc.objects if o.type == "CAMERA"]
out["camera"] = [{"lens": round(c.data.lens, 1), "dof": c.data.dof.use_dof, "fstop": round(c.data.dof.aperture_fstop, 2)} for c in cams][:3]
nodes = {}
for m in bpy.data.materials:
    if m.use_nodes:
        for n in m.node_tree.nodes:
            nodes[n.bl_idname] = nodes.get(n.bl_idname, 0) + 1
out["material_nodes"] = dict(sorted(nodes.items(), key=lambda kv: -kv[1])[:25])
out["compositor"] = [n.bl_idname for n in sc.node_tree.nodes] if getattr(sc, "node_tree", None) else []
print("STUDY_JSON" + json.dumps(out))
'''


def study(ref: str) -> dict:
    """Blender 데모 파일을 받아(공부용 — 영상에 넣지 않음) 렌더 · 조명 · 색 관리 · 셰이더 설정을 요약한다"""
    if ref.startswith("blender-demo:"):
        rel = ref.split(":", 1)[1].lstrip("/")
        f = STUDY / "blender-demo" / rel
        if not f.exists():
            _download(f"https://mirror.blender.org/demo/{rel}", f)
            (f.parent / "LICENSE-확인.txt").write_text(f"https://www.blender.org/download/demo-files/ — {rel}\n대부분 CC-BY-SA: 영상에 넣지 않고 설정만 배운다\n", "utf-8")
    else:
        f = Path(ref)
    from craft.materials import cli
    tmp = STUDY / "_study.py"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(STUDY_SCRIPT, "utf-8")
    r = subprocess.run([cli("blender"), "-b", str(f), "--python", str(tmp)], capture_output=True, text=True, timeout=600)
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith("STUDY_JSON")), None)
    if not line:
        raise RuntimeError("Blender 가 파일을 읽지 못했습니다: " + (r.stderr or r.stdout)[-600:])
    res = json.loads(line[len("STUDY_JSON"):])
    (f.with_suffix(".study.json")).write_text(json.dumps(res, ensure_ascii=False, indent=1), "utf-8")
    return res


def listing() -> list[dict]:
    out = []
    for c in sorted(LIB.glob("**/CREDIT.txt")):
        lines = c.read_text("utf-8").splitlines()
        out.append({"dir": str(c.parent.relative_to(ROOT)), "credit": lines[0] if lines else "", "license": (lines[1] if len(lines) > 1 else "").replace("license: ", "")})
    return out


def main() -> int:
    sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E401,F401
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["search", "get", "import", "study", "list"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--kind", default="model", choices=["model", "hdri", "texture", "material"])
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--res")
    ap.add_argument("--license")
    ap.add_argument("--source")
    ap.add_argument("--url", default="")
    a = ap.parse_args()
    if a.cmd == "search":
        res = search(a.arg or "", a.kind, a.n)
    elif a.cmd == "get":
        res = {"ok": True, "dir": str(get(a.arg, a.res).relative_to(ROOT))}
    elif a.cmd == "import":
        if not a.license or not a.source:
            print("import 에는 --license 와 --source 가 필요합니다", file=sys.stderr)
            return 2
        res = {"ok": True, "dir": str(import_pack(Path(a.arg), a.license, a.source, a.url).relative_to(ROOT))}
    elif a.cmd == "study":
        res = study(a.arg)
    else:
        res = listing()
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
