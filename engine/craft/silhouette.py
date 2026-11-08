"""흑회식 인물 — 관절 각도(자세)에서 검은 실루엣과 긁어낸 선을 계산해 VectorCraft 명령으로 낸다"""
import math

BLACK, LINE, CLAY = "#17110c", "#c9743a", "#c9743a"


def pt(o, ang, l):
    return (o[0] + l * math.sin(math.radians(ang)), o[1] + l * math.cos(math.radians(ang)))


def limb(a, b, w0, w1):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy) or 1
    ux, uy = -dy / n, dx / n
    return [(a[0] + ux * w0, a[1] + uy * w0), (b[0] + ux * w1, b[1] + uy * w1), (b[0] - ux * w1, b[1] - uy * w1), (a[0] - ux * w0, a[1] - uy * w0)]


def pose(t, cx=256, ground=470, s=1.0, shorts=False):
    """t: 0~1 달리기 주기. 머리는 오른쪽. 어깨 넓고 허리 잘록, 다리가 길고 보폭이 크다(그리스 도기 주자의 비례)"""
    ph = t * 2 * math.pi
    TH, SH = 122 * s, 120 * s                      # 허벅지 · 정강이
    hip = (cx - 10 * s, ground - 228 * s - 10 * s * abs(math.sin(ph)))
    lean = 16                                      # 앞으로 기울기(도)
    chest = pt(hip, 180 - lean, 92 * s)
    neck = pt(chest, 180 - lean, 62 * s)
    polys, lines = [], []
    for p_, near in ((ph + math.pi, False), (ph, True)):
        th = 16 + 46 * math.sin(p_)                 # 허벅지: 뒤로 -30 ~ 앞으로 62
        flex = 26 + 58 * max(0.0, math.sin(p_ - 1.5))  # 뒤로 찰 때 무릎이 접힌다
        knee = pt(hip, th, TH)
        ank = pt(knee, th - flex - 14, SH)
        foot = (ank[0] + 42 * s, ank[1] + 4 * s)
        polys += [limb(hip, knee, 30 * s, 15 * s), limb(knee, ank, 16 * s, 7 * s), limb(ank, foot, 8 * s, 4 * s)]
        calf = pt(knee, th - flex - 14, 48 * s)
        polys.append([(knee[0] - 15 * s, knee[1]), (calf[0] - 20 * s, calf[1]), (ank[0] - 6 * s, ank[1] - 16 * s), (ank[0] + 6 * s, ank[1] - 16 * s), (calf[0] + 8 * s, calf[1])])  # 종아리
        if near:
            m = pt(hip, th, TH * .55)
            lines.append([(m[0] - 13 * s, m[1] - 12 * s), (m[0] + 2 * s, m[1] + 3 * s), (knee[0] - 6 * s, knee[1] - 4 * s)])
            lines.append([(knee[0] - 11 * s, knee[1] + 3 * s), (knee[0] + 11 * s, knee[1])])
    for p_ in (ph, ph + math.pi):                   # 팔: 뛰는 다리와 반대로 크게
        sh = pt(neck, 0, 18 * s)
        a = 8 + 58 * math.sin(p_)
        elb = pt(sh, a, 78 * s)
        h = pt(elb, a + 92, 66 * s)
        polys += [limb(sh, elb, 15 * s, 9 * s), limb(elb, h, 9 * s, 5 * s)]
    x, y = hip
    polys.append([(x - 26 * s, y + 26 * s), (x + 30 * s, y + 24 * s), (x + 22 * s, y - 28 * s),
                  (chest[0] + 40 * s, chest[1] + 8 * s), (neck[0] + 26 * s, neck[1] + 6 * s), (neck[0] - 38 * s, neck[1] + 10 * s), (chest[0] - 38 * s, chest[1] + 10 * s), (x - 22 * s, y - 30 * s)])
    head = pt(neck, 180 - lean - 4, 44 * s)
    head = (head[0] + 14 * s, head[1])
    r = 33 * s
    polys.append([(head[0] + r * math.cos(i / 20 * 6.283), head[1] + r * 1.08 * math.sin(i / 20 * 6.283)) for i in range(20)])
    polys.append([(head[0] + 24 * s, head[1] - 16 * s), (head[0] + 46 * s, head[1] + 7 * s), (head[0] + 26 * s, head[1] + 13 * s)])
    polys.append([(head[0] + 8 * s, head[1] + 24 * s), (head[0] + 32 * s, head[1] + 20 * s), (head[0] + 28 * s, head[1] + 58 * s), (head[0] - 6 * s, head[1] + 34 * s)])
    polys.append(limb((neck[0], neck[1] + 12 * s), (head[0] - 8 * s, head[1] + 18 * s), 21 * s, 17 * s))
    polys.append([(head[0] - 28 * s, head[1] + 2 * s), (head[0] - 52 * s, head[1] + 8 * s), (head[0] - 26 * s, head[1] + 26 * s)])   # 뒤로 묶은 머리
    lines.append([(head[0] - 31 * s, head[1] - 7 * s), (head[0] + 28 * s, head[1] - 16 * s)])
    e = (head[0] + 14 * s, head[1] - 2 * s)
    lines.append([(e[0] - 9 * s, e[1]), (e[0], e[1] - 5 * s), (e[0] + 9 * s, e[1]), (e[0], e[1] + 4 * s), (e[0] - 9 * s, e[1])])
    c = chest
    lines.append([(c[0] - 4 * s, c[1] - 30 * s), (c[0] + 6 * s, c[1] + 2 * s), (x + 8 * s, y - 34 * s)])      # 가슴 · 배 선
    lines.append([(c[0] + 26 * s, c[1] - 8 * s), (c[0] + 4 * s, c[1] + 4 * s)])
    lines.append([(x - 20 * s, y + 16 * s), (x + 26 * s, y + 13 * s)])                                        # 허리띠
    return polys, lines


def steps(polys, lines, st, weight=4.5):
    for q in polys:
        st.append({"id": "path.create", "params": {"anchors": [{"x": round(x, 1), "y": round(y, 1)} for x, y in q], "closed": True}})
        i = len(st) - 1
        st.append({"id": "paint.setFill", "params": {"id": f"${i}.id", "color": BLACK}})
        st.append({"id": "paint.setStroke", "params": {"id": f"${i}.id", "color": BLACK}})
        st.append({"id": "stroke.set", "params": {"id": f"${i}.id", "weight": 7, "cap": "round", "join": "round"}})   # 모서리를 둥글게
    for q in lines:
        st.append({"id": "path.create", "params": {"anchors": [{"x": round(x, 1), "y": round(y, 1)} for x, y in q], "closed": False}})
        i = len(st) - 1
        st.append({"id": "paint.setFill", "params": {"id": f"${i}.id", "none": True}})
        st.append({"id": "paint.setStroke", "params": {"id": f"${i}.id", "color": LINE}})
        st.append({"id": "stroke.set", "params": {"id": f"${i}.id", "weight": weight, "cap": "round", "join": "round", "profile": "lens"}})
