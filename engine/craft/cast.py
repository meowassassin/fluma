#!/usr/bin/env python3
"""실험 — 인물을 쓰는 기본 경로가 아니다. 사양으로 조립한 인물은 어색하고 복장이 맞지 않아 슬롭으로 보인다(2026-11-07 사용자 평가).
인물은 illustrate 스킬로 펜 곡선으로 직접 그린다. 이 모듈은 아주 작은 군중 · 멀리 있는 실루엣에만 쓴다.

캐스팅 — 사양(체형 · 머리 · 수염 · 복장 · 코)으로 인물을 만들고, 자세 · 표정 · 입모양을 계산해 VectorCraft 명령으로 낸다.
인물을 영상마다 새로 그리지 않는다. 사양만 바꾸면 다른 사람이 되고, 같은 사양은 어느 장면에서도 같은 사람이다.

  look = {"skin": "#e8b98f", "hair": "#2b2118", "hair_style": "short|long|bun|bald|curly", "beard": "none|full|stubble|moustache",
          "hat": "none|hoplite|cap|wreath|headband", "garment": "tunic|toga|uniform|suit", "color": "#8e2a1c", "trim": "#e0b95f",
          "build": .8~1.25, "tall": .85~1.1, "nose": "round|long|hook", "glasses": false}
  POSES: stand · talk · think · shock · point · laugh · run(달리기 8칸)
콘티: {"type": "cast", "id": "kim", "look": {…}, "poses": ["stand", "talk", "shock"]} → 자세마다 PNG(<id>_<자세>0.png …), 화면에는 레시피로 놓는다.
"""
from __future__ import annotations

import math

LINE = "#231a14"


def _pt(o, ang, l):
    return (o[0] + l * math.sin(math.radians(ang)), o[1] + l * math.cos(math.radians(ang)))


def _limb(a, b, w0, w1):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy) or 1
    ux, uy = -dy / n, dx / n
    return [(a[0] + ux * w0, a[1] + uy * w0), (b[0] + ux * w1, b[1] + uy * w1), (b[0] - ux * w1, b[1] - uy * w1), (a[0] - ux * w0, a[1] - uy * w0)]


def _oval(c, rx, ry, n=28, a0=0.0, a1=360.0, rot=0.0):
    r = math.radians(rot)
    out = []
    for i in range(n + (0 if a1 - a0 >= 360 else 1)):
        t = math.radians(a0 + (a1 - a0) * i / n)
        x, y = rx * math.cos(t), ry * math.sin(t)
        out.append((c[0] + x * math.cos(r) - y * math.sin(r), c[1] + x * math.sin(r) + y * math.cos(r)))
    return out


# 자세: 팔(어깨 각 · 팔꿈치 각, 앞팔 / 뒷팔) · 머리 기울기 · 몸 기울기 · 표정
POSES = {
    "stand": dict(arm=(8, 12), back=(-6, -10), tilt=0, lean=0, brow=0, eye="open", mouth="closed"),
    "talk": dict(arm=(50, 110), back=(-8, -12), tilt=3, lean=2, brow=4, eye="open", mouth="open"),
    "think": dict(arm=(38, 150), back=(-4, 20), tilt=-7, lean=-2, brow=-8, eye="side", mouth="flat"),
    "shock": dict(arm=(120, 150), back=(-120, -150), tilt=-4, lean=-5, brow=16, eye="wide", mouth="o"),
    "point": dict(arm=(96, 100), back=(-6, -8), tilt=2, lean=3, brow=-6, eye="open", mouth="smile"),
    "laugh": dict(arm=(30, 120), back=(-30, -120), tilt=-10, lean=-4, brow=10, eye="closed", mouth="wide"),
}


class Fig:
    def __init__(self, look: dict, cx=256, ground=620):
        self.l = {"skin": "#e8b98f", "hair": "#2b2118", "hair_style": "short", "beard": "none", "hat": "none", "garment": "tunic", "color": "#8e2a1c", "trim": "#e0b95f",
                  "build": 1.0, "tall": 1.0, "nose": "round", "glasses": False, **look}
        self.cx, self.g = cx, ground
        self.items: list = []

    def fill(self, pts, color, line=True):
        self.items.append(("fill", pts, color, line))

    def stroke(self, pts, color=LINE, w=5):
        self.items.append(("line", pts, color, w))

    def tube(self, pts, color, w):
        """매끈한 팔다리 — 윤곽선 굵기로 한 번, 색으로 한 번 그어 관절 없이 잇는다"""
        self.items.append(("line", pts, LINE, w + 10))
        self.items.append(("line", pts, color, w))

    def leg(self, hip, th, flex, near):
        l = self.l
        k = l["tall"]
        knee = _pt(hip, th, 118 * k)
        ank = _pt(knee, th - flex, 118 * k)
        toe = (ank[0] + 38, ank[1] + 2)
        skin = l["skin"] if l["garment"] in ("tunic", "toga") else (l["color"] if l["garment"] != "suit" else "#2c2f38")
        self.tube([hip, knee, ank], skin, 36 * (0.9 + .1 * l["build"]))
        self.fill([(ank[0] - 17, ank[1] - 8), (ank[0] + 14, ank[1] - 10), (toe[0] + 8, toe[1] + 6), (toe[0] + 4, toe[1] + 15), (ank[0] - 18, ank[1] + 15)], "#3a2a1c")
        return knee, ank

    def arm(self, sh, a, e, hand=True):
        l = self.l
        elb = _pt(sh, a, 88)
        h = _pt(elb, a + e, 78)
        sl = l["skin"] if l["garment"] == "tunic" else (l["color"] if l["garment"] != "suit" else "#2c2f38")
        self.tube([sh, elb, h], sl, 26)
        if hand:
            self.fill(_oval(_pt(h, a + e, 9), 16, 16, 14), l["skin"])

    def head(self, neck, tilt, p):
        l = self.l
        c = _pt(neck, 180 + tilt, 62)
        R = 58
        rot = tilt
        # 얼굴 윤곽: 턱이 살짝 좁다
        face = [(c[0] + R * math.cos(t) * (1 if math.sin(t) < 0 else .9), c[1] + R * 1.08 * math.sin(t)) for t in [i / 28 * 6.283 for i in range(28)]]
        self.fill(face, l["skin"])
        self.fill(_oval((c[0] - 56, c[1] + 6), 10, 16, 12), l["skin"])         # 귀
        hs, H = l["hair_style"], l["hair"]
        if hs == "short":
            self.fill(_oval((c[0] - 4, c[1] - 26), 60, 38, 24, 180, 360) + [(c[0] + 50, c[1] - 18), (c[0] + 28, c[1] - 30), (c[0] - 34, c[1] - 26), (c[0] - 56, c[1] + 2)], H)
        elif hs == "curly":
            for i in range(9):
                t = math.radians(170 + i * 24)
                self.fill(_oval((c[0] + 50 * math.cos(t), c[1] - 8 + 50 * math.sin(t)), 21, 21, 12), H)
        elif hs == "long":
            self.fill([(c[0] - 62, c[1] - 30), (c[0] - 76, c[1] + 90), (c[0] - 40, c[1] + 96), (c[0] - 38, c[1] + 8)], H)
            self.fill(_oval((c[0] - 4, c[1] - 26), 62, 40, 24, 180, 360) + [(c[0] + 52, c[1] - 12), (c[0] - 54, c[1] - 12)], H)
        elif hs == "bun":
            self.fill(_oval((c[0] - 40, c[1] - 58), 24, 22, 14), H)
            self.fill(_oval((c[0] - 4, c[1] - 26), 60, 38, 24, 180, 360) + [(c[0] + 50, c[1] - 18), (c[0] - 56, c[1] - 6)], H)
        # 눈 · 눈썹
        for s, dx in ((1, 30), (-1, -8)):
            ex, ey = c[0] + dx, c[1] - 6
            b = p["brow"] * s * -1
            self.stroke([(ex - 16, ey - 22 + (b * .3)), (ex + 16, ey - 22 - (b * .3))], H if hs != "bald" else LINE, 8)
            e = p["eye"]
            if e == "closed":
                self.stroke(_oval((ex, ey + 2), 11, 8, 8, 200, 340), LINE, 5)
            elif e == "wide":
                self.fill(_oval((ex, ey), 15, 17, 14), "#ffffff"); self.fill(_oval((ex + 1, ey), 4, 5, 10), LINE, False)
            elif e == "side":
                self.fill(_oval((ex, ey), 12, 12, 14), "#ffffff"); self.fill(_oval((ex + 5, ey - 4), 5, 6, 10), LINE, False)
            else:
                self.fill(_oval((ex, ey), 12, 13, 14), "#ffffff"); self.fill(_oval((ex + 3, ey + 1), 6, 7, 10), LINE, False)
        if l["glasses"]:
            for dx in (30, -8):
                self.stroke(_oval((c[0] + dx, c[1] - 6), 19, 18, 18), LINE, 4)
            self.stroke([(c[0] + 2, c[1] - 8), (c[0] + 20, c[1] - 8)], LINE, 4)
        # 코
        nx, ny = c[0] + 22, c[1] + 12
        if l["nose"] == "long":
            self.stroke([(nx, ny - 14), (nx + 28, ny + 12), (nx + 2, ny + 14)], LINE, 5)
        elif l["nose"] == "hook":
            self.stroke(_oval((nx + 8, ny + 2), 15, 14, 12, -70, 130) , LINE, 5)
        else:
            self.stroke(_oval((nx + 2, ny + 4), 10, 8, 10, -60, 120), LINE, 5)
        # 수염 · 입
        by = c[1] + 34
        if l["beard"] == "full":
            self.fill([(c[0] - 52, c[1] + 10), (c[0] + 52, c[1] + 16), (c[0] + 44, c[1] + 62), (c[0] + 14, c[1] + 94), (c[0] - 22, c[1] + 86), (c[0] - 50, c[1] + 50)], H)
        elif l["beard"] == "moustache":
            self.fill([(c[0] + 2, by - 10), (c[0] + 22, by - 18), (c[0] + 46, by - 6), (c[0] + 24, by - 4)], H)
        m = p["mouth"]
        mc = (c[0] + 16, by + (6 if l["beard"] == "moustache" else 0))
        if m == "open":
            self.fill(_oval(mc, 15, 11, 14), "#5a1d1d")
        elif m == "o":
            self.fill(_oval(mc, 11, 16, 14), "#5a1d1d")
        elif m == "wide":
            self.fill(_oval(mc, 24, 18, 18, 0, 180) + [(mc[0] - 24, mc[1])], "#5a1d1d")
        elif m == "smile":
            self.stroke(_oval((mc[0], mc[1] - 6), 19, 13, 12, 25, 155), LINE, 6)
        elif m == "flat":
            self.stroke([(mc[0] - 14, mc[1] + 2), (mc[0] + 14, mc[1] - 2)], LINE, 6)
        else:
            self.stroke([(mc[0] - 12, mc[1]), (mc[0] + 12, mc[1])], LINE, 6)
        # 모자
        hat = l["hat"]
        if hat == "hoplite":
            self.fill(_oval((c[0], c[1] - 16), 66, 62, 26, 165, 375) + [(c[0] + 66, c[1] + 2), (c[0] + 20, c[1] + 8), (c[0] + 20, c[1] - 14), (c[0] - 62, c[1] - 6), (c[0] - 66, c[1] + 50), (c[0] - 44, c[1] + 50)], "#c48a2c")
            self.fill([(c[0] - 80, c[1] - 56), (c[0] - 40, c[1] - 104), (c[0] + 30, c[1] - 112), (c[0] + 62, c[1] - 74), (c[0] + 8, c[1] - 84)], l["color"])
        elif hat == "cap":
            self.fill(_oval((c[0] - 2, c[1] - 34), 66, 30, 24, 180, 360), l["color"])
            self.fill([(c[0] - 64, c[1] - 34), (c[0] + 66, c[1] - 34), (c[0] + 92, c[1] - 22), (c[0] + 40, c[1] - 22), (c[0] - 60, c[1] - 26)], "#1e1e22")
            self.fill(_oval((c[0] + 10, c[1] - 46), 8, 8, 10), l["trim"])
        elif hat == "wreath":
            for i in range(11):
                t = math.radians(190 + i * 16)
                q = (c[0] + 58 * math.cos(t), c[1] - 16 + 42 * math.sin(t))
                self.fill(_oval(q, 15, 8, 10, rot=math.degrees(t) + 60), "#5f7d3a")
        elif hat == "headband":
            self.fill([(c[0] - 60, c[1] - 30), (c[0] + 56, c[1] - 36), (c[0] + 58, c[1] - 22), (c[0] - 60, c[1] - 16)], l["trim"])

    def body(self, hip, lean, p):
        l = self.l
        b = l["build"]
        neck = _pt(hip, 180 - lean, 164 * l["tall"])
        c1, c2 = l["color"], l["trim"]
        x, y = hip
        nx, ny = neck
        if l["garment"] in ("tunic", "toga"):
            torso = [(nx - 62 * b, ny + 12), (nx + 58 * b, ny + 12), (x + 46 * b, y - 14), (x + 66 * b, y + 62), (x - 66 * b, y + 62), (x - 46 * b, y - 14)]
        else:
            torso = [(nx - 62 * b, ny + 12), (nx + 58 * b, ny + 12), (x + 48 * b, y + 18), (x - 48 * b, y + 18)]
        self.fill(torso, c1)
        if l["garment"] == "tunic":
            self.fill([(x - 50 * b, y - 10), (x + 50 * b, y - 12), (x + 50 * b, y + 8), (x - 50 * b, y + 10)], c2)
        elif l["garment"] == "toga":
            self.fill([(nx - 60 * b, ny + 14), (nx - 20, ny + 12), (x + 60 * b, y + 58), (x + 26, y + 62)], "#efe3cc")
        elif l["garment"] == "uniform":
            self.stroke([(nx, ny + 14), (x, y + 16)], LINE, 4)
            for k in (.3, .55, .8):
                self.fill(_oval((nx + (x - nx) * k, ny + 14 + (y - ny) * k), 6, 6, 8), c2)
            self.fill([(nx + 10, ny + 56), (nx + 46, ny + 54), (nx + 44, ny + 74), (nx + 12, ny + 76)], c2)
        elif l["garment"] == "suit":
            self.fill([(nx - 18, ny + 12), (nx + 16, ny + 12), (nx, ny + 74)], "#efe3cc"); self.fill([(nx - 7, ny + 18), (nx + 7, ny + 18), (nx + 3, ny + 66), (nx - 3, ny + 66)], c2)
        return neck

    def pose(self, name: str, t: float = 0.0):
        p = POSES.get(name) or POSES["stand"]
        k = self.l["tall"]
        if name == "run":
            ph = t * 6.283
            hip = (self.cx - 14, self.g - 236 * k - 12 * abs(math.sin(ph)))
            lean = 12
            p = dict(POSES["talk"], mouth="open", brow=-4)
            for pp in (ph + math.pi, ph):
                th, flex = 14 + 46 * math.sin(pp), 24 + 66 * max(0, math.sin(pp - 1.5))
                self.leg(hip, th, flex + 12, False)
            neck = self.body(hip, lean, p)
            sh = (neck[0], neck[1] + 26)
            self.arm(sh, 10 + 52 * math.sin(ph), 80)
            self.arm(sh, 10 - 52 * math.sin(ph), 80)
            self.head(neck, 2, p)
            return self
        hip = (self.cx, self.g - 236 * k)
        self.leg((hip[0] - 22, hip[1]), -6, 4, False); self.leg((hip[0] + 22, hip[1]), 6, 4, True)
        neck = self.body(hip, p["lean"], p)
        sh = (neck[0], neck[1] + 26)
        self.arm((sh[0] - 44 * self.l["build"], sh[1]), p["back"][0], p["back"][1])
        self.head(neck, p["tilt"], p)
        self.arm((sh[0] + 42 * self.l["build"], sh[1]), p["arm"][0], p["arm"][1])
        return self

    def steps(self):
        st = []
        for kind, pts, color, x in self.items:
            st.append({"id": "path.create", "params": {"anchors": [{"x": round(a, 1), "y": round(b, 1)} for a, b in pts], "closed": kind == "fill"}})
            i = len(st) - 1
            if kind == "fill":
                st.append({"id": "paint.setFill", "params": {"id": f"${i}.id", "color": color}})
                st.append({"id": "paint.setStroke", "params": {"id": f"${i}.id", "color": LINE}} if x else {"id": "paint.setStroke", "params": {"id": f"${i}.id", "none": True}})
                if x:
                    st.append({"id": "stroke.set", "params": {"id": f"${i}.id", "weight": 5, "cap": "round", "join": "round"}})
            else:
                st.append({"id": "paint.setFill", "params": {"id": f"${i}.id", "none": True}})
                st.append({"id": "paint.setStroke", "params": {"id": f"${i}.id", "color": color}})
                st.append({"id": "stroke.set", "params": {"id": f"${i}.id", "weight": x, "cap": "round", "join": "round"}})
        return st


def materials(m: dict) -> list[dict]:
    """콘티 cast 재료 → 자세별 craft 재료. 달리기는 8칸, 나머지는 입을 벌린 칸과 다문 칸"""
    out = []
    W, H = 512, 640
    for pose in m.get("poses") or ["stand"]:
        frames = [(pose, k / 8) for k in range(8)] if pose == "run" else [(pose, 0)]
        if pose == "talk":
            frames = [("stand", 0), ("talk", 0)]
        for k, (name, t) in enumerate(frames):
            st = Fig(m.get("look") or {}, cx=W / 2 - 20, ground=H - 14).pose(name, t).steps()
            out.append({"id": f"{m['id']}_{pose}{k}", "type": "craft", "app": "vectorcraft", "show": False, "new": {"width": W, "height": H, "units": "Pixels"}, "steps": st, "export": {"format": "png", "size": [W, H]}})
    return out
