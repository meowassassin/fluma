"""Blender -P 로 실행: 사용자 3D 스크립트 하나를 지어 연속 이미지(또는 정지 화면)로 렌더.
환경변수: FL_SCRIPT(스크립트) FL_OUT(출력 폴더) FL_CTX(ctx JSON) FL_STILLS("초,초" 면 정지 화면만 s00.png …) FL_PAD(프레임 번호 자릿수)"""
import json
import os
import sys

sys.path.insert(0, os.environ["FL_LIB"])
import bpy  # noqa: E402
import fluma3d as F  # noqa: E402
import guard  # noqa: E402

c = json.loads(os.environ["FL_CTX"])
OUT = os.environ["FL_OUT"]
STILLS = [float(x) for x in os.environ.get("FL_STILLS", "").split(",") if x]
PAD = int(os.environ.get("FL_PAD", "4"))
ctx = guard.context(**c)
F.FONTS = c.get("fonts", "")
mod = guard.load(os.environ["FL_SCRIPT"], writable=[OUT, c.get("work", "")])
F.reset(c["w"], c["h"], c["fps"], c["sec"], transparent=c["transparent"], draft=c["draft"])
guard.call(mod.build, ctx)
sc = bpy.context.scene
if sc.camera is None:
    F.camera()
F.finalize()
os.makedirs(OUT, exist_ok=True)
if STILLS:
    for k, t in enumerate(STILLS):
        F.render_still(os.path.join(OUT, f"s{k:02d}.png"), t)
else:
    F.render_sequence(OUT, pad=PAD)
print(f"[3D] {sc.frame_end} 프레임 · {sc.render.resolution_x}x{sc.render.resolution_y}", flush=True)
