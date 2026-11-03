"""그리기 엔진 1단계 — 덩어리(거리장) · 합치기 · 외곽선 → 삼차 베지어.

설계: 볼트 02 Architecture/그리기 엔진 설계 — 구조로 그리기.md (3.3절)
에이전트는 이 모듈을 직접 부르지 않는다. 형태(form.json)를 풀이기(solve)가 이 덩어리들로 바꾼다.

  - 덩어리는 모두 부호 있는 거리장(SDF): 안쪽 < 0, 경계 = 0, 바깥 > 0. 좌표계는 SVG 와 같이 y 가 아래로.
  - 합치기 부드러움 k 는 화풍의 '둥글기'에서 온다(생물 = 부드럽게, 기계 = k≈0).
  - outline(): 격자에서 등고선(marching squares) → 모서리에서 자르기 → 삼차 베지어 맞춤(Schneider) → SVG path.
    닫힌 곡선 · 적은 핸들이라 사람이 VectorCraft 에서 열어 고치기 쉽다.
의존성은 numpy 만(가벼운 설치).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

Vec = tuple[float, float]


# ---------------------------------------------------------------- 덩어리
@dataclass
class Shape:
    """거리장 하나. sdf(X, Y) → 거리, bounds() → (x0, y0, x1, y1)"""

    def sdf(self, X: np.ndarray, Y: np.ndarray) -> np.ndarray:  # pragma: no cover - 추상
        raise NotImplementedError

    def bounds(self) -> tuple[float, float, float, float]:  # pragma: no cover - 추상
        raise NotImplementedError

    # 조합 문법: a | b (합치기), a - b (빼기), a & b (교집합). 부드럽게는 Union(..., k=)
    def __or__(self, o: "Shape") -> "Shape":
        return Union([self, o])

    def __sub__(self, o: "Shape") -> "Shape":
        return Subtract(self, o)

    def __and__(self, o: "Shape") -> "Shape":
        return Intersect(self, o)


def _rot(X, Y, c: Vec, deg: float):
    """점들을 c 기준으로 -deg 돌려 덩어리의 제 좌표로"""
    x, y = X - c[0], Y - c[1]
    if not deg:
        return x, y
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return ca * x + sa * y, -sa * x + ca * y


@dataclass
class Circle(Shape):
    c: Vec
    r: float

    def sdf(self, X, Y):
        return np.hypot(X - self.c[0], Y - self.c[1]) - self.r

    def bounds(self):
        return (self.c[0] - self.r, self.c[1] - self.r, self.c[0] + self.r, self.c[1] + self.r)


@dataclass
class Ellipse(Shape):
    c: Vec
    rx: float
    ry: float
    rot: float = 0.0

    def sdf(self, X, Y):
        # Quilez 근사(경계 근처에서 정확 — 등고선은 0 에서만 뽑으므로 충분)
        x, y = _rot(X, Y, self.c, self.rot)
        k0 = np.hypot(x / self.rx, y / self.ry)
        k1 = np.hypot(x / self.rx ** 2, y / self.ry ** 2)
        return np.where(k1 > 1e-9, k0 * (k0 - 1.0) / np.maximum(k1, 1e-9), -min(self.rx, self.ry))

    def bounds(self):
        r = max(self.rx, self.ry)
        return (self.c[0] - r, self.c[1] - r, self.c[0] + r, self.c[1] + r)


@dataclass
class Capsule(Shape):
    """a 에서 b 로 가는 관. 두 끝 반지름이 달라도 된다(팔다리 · 목 · 꼬리 · 콩 몸통)"""
    a: Vec
    b: Vec
    ra: float
    rb: float | None = None

    def sdf(self, X, Y):
        rb = self.ra if self.rb is None else self.rb
        ax, ay = self.a
        dx, dy = self.b[0] - ax, self.b[1] - ay
        h = math.hypot(dx, dy)
        if h < 1e-9 or abs(self.ra - rb) >= h:      # 한 원이 다른 원을 품음
            big = (self.a, self.ra) if self.ra >= rb else (self.b, rb)
            return np.hypot(X - big[0][0], Y - big[0][1]) - big[1]
        # 제 좌표: a 가 원점, b 가 +y 축 위 (Quilez sdUnevenCapsule)
        uy, ux = dx / h, dy / h          # 축 방향 단위(아래 식의 y), 수직(x)
        px = np.abs((X - ax) * ux - (Y - ay) * uy)
        py = (X - ax) * uy + (Y - ay) * ux
        bb = (self.ra - rb) / h
        aa = math.sqrt(1 - bb * bb)
        k = -bb * px + aa * py
        d1 = np.hypot(px, py) - self.ra
        d2 = np.hypot(px, py - h) - rb
        d3 = aa * px + bb * py - self.ra
        return np.where(k < 0, d1, np.where(k > aa * h, d2, d3))

    def bounds(self):
        rb = self.ra if self.rb is None else self.rb
        r = max(self.ra, rb)
        return (min(self.a[0], self.b[0]) - r, min(self.a[1], self.b[1]) - r, max(self.a[0], self.b[0]) + r, max(self.a[1], self.b[1]) + r)


@dataclass
class Box(Shape):
    c: Vec
    w: float
    h: float
    round: float = 0.0
    rot: float = 0.0

    def sdf(self, X, Y):
        x, y = _rot(X, Y, self.c, self.rot)
        r = min(self.round, self.w / 2, self.h / 2)
        qx = np.abs(x) - (self.w / 2 - r)
        qy = np.abs(y) - (self.h / 2 - r)
        return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r

    def bounds(self):
        r = math.hypot(self.w, self.h) / 2
        return (self.c[0] - r, self.c[1] - r, self.c[0] + r, self.c[1] + r)


@dataclass
class Polygon(Shape):
    """닫힌 다각형(원형 라이브러리 안에서만 — 에이전트 형태에는 좌표가 없다)"""
    pts: list[Vec]

    def sdf(self, X, Y):
        P = np.asarray(self.pts, float)
        d = np.full(X.shape, np.inf)
        s = np.ones(X.shape)
        n = len(P)
        for i in range(n):
            a, b = P[i], P[i - 1]
            ex, ey = b[0] - a[0], b[1] - a[1]
            wx, wy = X - a[0], Y - a[1]
            t = np.clip((wx * ex + wy * ey) / (ex * ex + ey * ey), 0, 1)
            d = np.minimum(d, (wx - ex * t) ** 2 + (wy - ey * t) ** 2)
            c1 = Y >= a[1]
            c2 = Y < b[1]
            c3 = ex * wy > ey * wx
            flip = (c1 & c2 & c3) | (~c1 & ~c2 & ~c3)
            s = np.where(flip, -s, s)
        return s * np.sqrt(d)

    def bounds(self):
        P = np.asarray(self.pts, float)
        return (P[:, 0].min(), P[:, 1].min(), P[:, 0].max(), P[:, 1].max())


@dataclass
class Leaf(Shape):
    """잎 · 날개 · 귀 · 비늘: 두 원의 교집합(끝이 뾰족). width 는 가운데 폭"""
    a: Vec
    b: Vec
    width: float

    def _circles(self):
        h = math.dist(self.a, self.b) / 2
        w = self.width / 2
        R = (h * h + w * w) / (2 * w)          # 현 길이 2h, 화살 높이 w 인 원
        mx, my = (self.a[0] + self.b[0]) / 2, (self.a[1] + self.b[1]) / 2
        nx, ny = -(self.b[1] - self.a[1]) / (2 * h), (self.b[0] - self.a[0]) / (2 * h)
        off = R - w
        return Circle((mx + nx * off, my + ny * off), R), Circle((mx - nx * off, my - ny * off), R)

    def sdf(self, X, Y):
        c1, c2 = self._circles()
        return np.maximum(c1.sdf(X, Y), c2.sdf(X, Y))

    def bounds(self):
        r = self.width / 2
        return (min(self.a[0], self.b[0]) - r, min(self.a[1], self.b[1]) - r, max(self.a[0], self.b[0]) + r, max(self.a[1], self.b[1]) + r)


@dataclass
class Sweep(Shape):
    """곡선을 따라 굵기가 변하는 관(뿔 · 줄기 · 촉수 · 머리카락 다발). pts · radii 는 같은 길이"""
    pts: list[Vec]
    radii: list[float]
    k: float = 0.0

    def _parts(self):
        return [Capsule(self.pts[i], self.pts[i + 1], self.radii[i], self.radii[i + 1]) for i in range(len(self.pts) - 1)]

    def sdf(self, X, Y):
        return Union(self._parts(), k=self.k).sdf(X, Y)

    def bounds(self):
        return Union(self._parts()).bounds()


# ---------------------------------------------------------------- 합치기
def smin(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    """부드러운 최솟값(다항식). k = 이음매가 둥글어지는 폭"""
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


@dataclass
class Union(Shape):
    parts: list[Shape]
    k: float = 0.0

    def sdf(self, X, Y):
        d = self.parts[0].sdf(X, Y)
        for p in self.parts[1:]:
            d = smin(d, p.sdf(X, Y), self.k)
        return d

    def bounds(self):
        bs = [p.bounds() for p in self.parts]
        return (min(b[0] for b in bs) - self.k, min(b[1] for b in bs) - self.k, max(b[2] for b in bs) + self.k, max(b[3] for b in bs) + self.k)


@dataclass
class Subtract(Shape):
    a: Shape
    b: Shape
    k: float = 0.0

    def sdf(self, X, Y):
        return -smin(-self.a.sdf(X, Y), self.b.sdf(X, Y), self.k)

    def bounds(self):
        return self.a.bounds()


@dataclass
class Intersect(Shape):
    a: Shape
    b: Shape
    k: float = 0.0

    def sdf(self, X, Y):
        return -smin(-self.a.sdf(X, Y), -self.b.sdf(X, Y), self.k)

    def bounds(self):
        A, B = self.a.bounds(), self.b.bounds()
        return (max(A[0], B[0]), max(A[1], B[1]), min(A[2], B[2]), min(A[3], B[3]))


@dataclass
class Offset(Shape):
    """두께 더하기(+) · 줄이기(−). 외곽선 · 테두리 · 그림자 영역용"""
    a: Shape
    d: float

    def sdf(self, X, Y):
        return self.a.sdf(X, Y) - self.d

    def bounds(self):
        b = self.a.bounds()
        m = max(self.d, 0)
        return (b[0] - m, b[1] - m, b[2] + m, b[3] + m)


# ---------------------------------------------------------------- 격자 · 등고선
def sample(shape: Shape, res: float, pad: float | None = None):
    """덩어리를 덮는 격자에서 거리장을 잰다 → (값, 원점 x0, y0)"""
    x0, y0, x1, y1 = shape.bounds()
    pad = 3 * res if pad is None else pad
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    nx, ny = int(math.ceil((x1 - x0) / res)) + 1, int(math.ceil((y1 - y0) / res)) + 1
    X, Y = np.meshgrid(x0 + np.arange(nx) * res, y0 + np.arange(ny) * res)
    return shape.sdf(X, Y), x0, y0


def contours(F: np.ndarray, x0: float, y0: float, res: float) -> list[np.ndarray]:
    """0 등고선을 닫힌 고리들로 (marching squares, 선형 보간, 안장점은 가운데 값으로).
    고리마다 (N, 2) 배열, 바깥 고리는 시계 방향(SVG 좌표 기준), 구멍은 반대 방향."""
    H, W = F.shape
    v = F
    # 칸 꼭짓점: 0 (i,j) 1 (i,j+1) 2 (i+1,j+1) 3 (i+1,j)
    a, b, c, d = v[:-1, :-1], v[:-1, 1:], v[1:, 1:], v[1:, :-1]
    code = (a < 0).astype(np.uint8) | ((b < 0) << 1) | ((c < 0) << 2) | ((d < 0) << 3)
    # 모서리 번호: 0 위(a-b) 1 오른쪽(b-c) 2 아래(d-c) 3 왼쪽(a-d). 모서리 키 = 전역 고유 id
    TABLE = {1: [(3, 0)], 2: [(0, 1)], 3: [(3, 1)], 4: [(1, 2)], 6: [(0, 2)], 7: [(3, 2)], 8: [(2, 3)],
             9: [(2, 0)], 11: [(2, 1)], 12: [(1, 3)], 13: [(1, 0)], 14: [(0, 3)]}
    ii, jj = np.nonzero((code != 0) & (code != 15))

    def key(i, j, e):
        # 가로 모서리: ('h', 행, 열), 세로 모서리: ('v', 행, 열)
        return ("h", i, j) if e == 0 else ("v", i, j + 1) if e == 1 else ("h", i + 1, j) if e == 2 else ("v", i, j)

    def point(k):
        t, i, j = k
        if t == "h":
            f0, f1 = v[i, j], v[i, j + 1]
            s = f0 / (f0 - f1)
            return (x0 + (j + s) * res, y0 + i * res)
        f0, f1 = v[i, j], v[i + 1, j]
        s = f0 / (f0 - f1)
        return (x0 + j * res, y0 + (i + s) * res)

    nxt: dict = {}
    for i, j in zip(ii.tolist(), jj.tolist()):
        cd = int(code[i, j])
        if cd in (5, 10):          # 안장점: 칸 가운데 값으로 연결 방향을 정한다
            mid = (a[i, j] + b[i, j] + c[i, j] + d[i, j]) / 4
            if cd == 5:
                segs = [(3, 0), (1, 2)] if mid >= 0 else [(1, 0), (3, 2)]
            else:
                segs = [(0, 1), (2, 3)] if mid >= 0 else [(0, 3), (2, 1)]
        else:
            segs = TABLE[cd]
        for e0, e1 in segs:
            nxt[key(i, j, e0)] = key(i, j, e1)

    loops = []
    seen = set()
    for start in list(nxt):
        if start in seen:
            continue
        ring, k = [], start
        while k not in seen and k in nxt:
            seen.add(k)
            ring.append(point(k))
            k = nxt[k]
        if len(ring) >= 3:
            R = np.asarray(ring)
            # 경계가 격자점에 정확히 걸리면 이웃 칸이 같은 점을 두 번 낸다 → 겹친 점을 걸러야 모서리 검출이 흔들리지 않음
            keep = np.linalg.norm(R - np.roll(R, 1, 0), axis=1) > res * 0.05
            R = R[keep] if keep.any() else R
            if len(R) >= 3:
                loops.append(R)
    return loops


# ---------------------------------------------------------------- 베지어 맞춤 (Schneider, Graphics Gems I)
def _bez(ctrl: np.ndarray, t: np.ndarray) -> np.ndarray:
    t = t[:, None]
    mt = 1 - t
    return mt ** 3 * ctrl[0] + 3 * mt * mt * t * ctrl[1] + 3 * mt * t * t * ctrl[2] + t ** 3 * ctrl[3]


def _bez_d(ctrl, t):
    t = t[:, None]
    mt = 1 - t
    return 3 * mt * mt * (ctrl[1] - ctrl[0]) + 6 * mt * t * (ctrl[2] - ctrl[1]) + 3 * t * t * (ctrl[3] - ctrl[2])


def _bez_dd(ctrl, t):
    t = t[:, None]
    return 6 * (1 - t) * (ctrl[2] - 2 * ctrl[1] + ctrl[0]) + 6 * t * (ctrl[3] - 2 * ctrl[2] + ctrl[1])


def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def _chord(P):
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    return d / d[-1] if d[-1] > 0 else d


def _generate(P, u, t1, t2):
    A1 = t1[None, :] * (3 * (1 - u) ** 2 * u)[:, None]
    A2 = t2[None, :] * (3 * (1 - u) * u ** 2)[:, None]
    C = np.array([[np.sum(A1 * A1), np.sum(A1 * A2)], [np.sum(A1 * A2), np.sum(A2 * A2)]])
    base = _bez(np.array([P[0], P[0], P[-1], P[-1]]), u)
    tmp = P - base
    X = np.array([np.sum(A1 * tmp), np.sum(A2 * tmp)])
    det = C[0, 0] * C[1, 1] - C[0, 1] * C[1, 0]
    seg = np.linalg.norm(P[-1] - P[0])
    if abs(det) > 1e-12:
        al1 = (X[0] * C[1, 1] - X[1] * C[0, 1]) / det
        al2 = (C[0, 0] * X[1] - C[1, 0] * X[0]) / det
    else:
        al1 = al2 = seg / 3
    if al1 < 1e-6 * seg or al2 < 1e-6 * seg:
        al1 = al2 = seg / 3
    return np.array([P[0], P[0] + t1 * al1, P[-1] + t2 * al2, P[-1]])


def _max_err(P, ctrl, u):
    d = np.sum((_bez(ctrl, u) - P) ** 2, axis=1)
    i = int(np.argmax(d))
    return float(d[i]), i


def _reparam(P, ctrl, u):
    q, q1, q2 = _bez(ctrl, u), _bez_d(ctrl, u), _bez_dd(ctrl, u)
    num = np.sum((q - P) * q1, axis=1)
    den = np.sum(q1 * q1, axis=1) + np.sum((q - P) * q2, axis=1)
    out = u - np.where(np.abs(den) > 1e-12, num / np.where(np.abs(den) > 1e-12, den, 1), 0)
    return np.clip(out, 0, 1)


def fit_cubic(P: np.ndarray, t1: np.ndarray, t2: np.ndarray, err: float, depth: int = 0) -> list[np.ndarray]:
    """점열 P 를 삼차 베지어 여러 개로. err = 허용 거리(같은 단위)"""
    if len(P) == 2:
        dist = np.linalg.norm(P[1] - P[0]) / 3
        return [np.array([P[0], P[0] + t1 * dist, P[1] + t2 * dist, P[1]])]
    # 거의 일직선이면 직선으로(상자 변이 물결지지 않게)
    ch = P[-1] - P[0]
    L = np.linalg.norm(ch)
    if L > 1e-9:
        Q = P - P[0]
        dev = np.abs(ch[0] * Q[:, 1] - ch[1] * Q[:, 0]) / L
        if dev.max() < err * 0.5:
            return [np.array([P[0], P[0] + ch / 3, P[0] + 2 * ch / 3, P[-1]])]
    u = _chord(P)
    ctrl = _generate(P, u, t1, t2)
    e2, split = _max_err(P, ctrl, u)
    if e2 < err * err:
        return [ctrl]
    if e2 < 16 * err * err:
        for _ in range(6):
            u = _reparam(P, ctrl, u)
            ctrl = _generate(P, u, t1, t2)
            e2, split = _max_err(P, ctrl, u)
            if e2 < err * err:
                return [ctrl]
    if depth > 24 or len(P) < 4:
        return [ctrl]
    split = min(max(split, 1), len(P) - 2)
    tc = _unit(P[split - 1] - P[split + 1])
    return fit_cubic(P[: split + 1], t1, tc, err, depth + 1) + fit_cubic(P[split:], -tc, t2, err, depth + 1)


def _smooth_ring(R: np.ndarray, n: int = 2) -> np.ndarray:
    """격자 계단을 지우는 가벼운 평활(닫힌 고리) — 모서리 점은 그대로 둔다"""
    out = R.copy()
    for _ in range(n):
        out = (np.roll(out, 1, 0) + 2 * out + np.roll(out, -1, 0)) / 4
    return out


def corners(R: np.ndarray, angle: float = 50.0, win: int = 3) -> list[int]:
    """닫힌 고리에서 꺾인 점(바깥 방향 전환이 angle 도 이상)"""
    n = len(R)
    if n < 2 * win + 2:
        return []
    a = R - np.roll(R, win, 0)
    b = np.roll(R, -win, 0) - R
    cos = np.sum(a * b, axis=1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1) + 1e-12)
    turn = np.degrees(np.arccos(np.clip(cos, -1, 1)))
    idx = []
    for i in np.argsort(-turn):
        if turn[i] < angle:
            break
        if all(min(abs(i - j), n - abs(i - j)) > 2 * win for j in idx):
            idx.append(int(i))
    return sorted(idx)


def _line(P: np.ndarray):
    """점들에 맞춘 직선: (중심, 방향)"""
    c = P.mean(axis=0)
    _, _, vt = np.linalg.svd(P - c)
    return c, vt[0]


def _meet(before: np.ndarray, after: np.ndarray, fallback: np.ndarray) -> np.ndarray:
    """모서리 양옆 두 직선의 교점. 거의 평행하거나 너무 멀면 원래 점"""
    (c1, d1), (c2, d2) = _line(before), _line(after)
    den = d1[0] * d2[1] - d1[1] * d2[0]
    # 직각에 가까운 모서리(상자)만 연장선 교점으로 살린다. 뾰족한 끝(그림자 끝 · 잎 끝)은 교점이 멀리 튀어 바늘이 된다
    if abs(den) < 0.75:          # |sin(사잇각)| < 0.75 ≈ 49° 보다 뾰족하거나 거의 평행
        return fallback
    t = ((c2[0] - c1[0]) * d2[1] - (c2[1] - c1[1]) * d2[0]) / den
    p = c1 + t * d1
    return p if np.linalg.norm(p - fallback) < 1.5 * np.linalg.norm(before[0] - fallback) + 1e-9 else fallback


def fit_ring(R: np.ndarray, err: float, corner_angle: float = 50.0, cs: list[int] | None = None) -> list[np.ndarray]:
    """닫힌 고리 → 베지어 조각들(모서리에서는 꺾이고, 나머지는 매끄럽게 이어짐).
    cs: 미리 찾은 모서리(손맛 흔들림 전의 외곽선에서 찾아야 물결이 모서리로 잡히지 않는다)"""
    win = 3
    cs = corners(R, corner_angle, win) if cs is None else cs
    S = _smooth_ring(R)
    if cs:
        n = len(R)
        # 격자는 꼭짓점을 깎는다 → 양옆 변을 직선으로 맞춰 만나는 점을 진짜 꼭짓점으로, 깎인 점들(±win)은 버린다
        tip = {}
        for c in cs:
            before = R[[(c - win - j) % n for j in range(1, 2 * win + 1)]]
            after = R[[(c + win + j) % n for j in range(1, 2 * win + 1)]]
            tip[c] = _meet(before, after, R[c])
        segs = []
        for k, c in enumerate(cs):
            e = cs[(k + 1) % len(cs)]
            idx = np.arange(c, e + 1) if e > c else np.r_[np.arange(c, n), np.arange(0, e + 1)]
            inner = idx[win:-win] if len(idx) > 2 * win + 1 else idx[1:-1]
            P = np.vstack([tip[c][None, :], S[inner], tip[e][None, :]])
            if len(P) < 2:
                continue
            t1 = _unit(P[min(2, len(P) - 1)] - P[0])
            t2 = _unit(P[max(-3, -len(P))] - P[-1])
            segs += fit_cubic(P, t1, t2, err)
        return segs
    # 모서리 없음: 한 점에서 열어, 양 끝 접선을 같은 방향으로 맞춰 이음매 없이
    P = np.vstack([S, S[:1]])
    t = _unit(S[1] - S[-1])
    return fit_cubic(P, t, -t, err)


def path_d(segs_per_ring: list[list[np.ndarray]], nd: int = 2) -> str:
    """베지어 조각들 → SVG path d (고리마다 M … C … Z)"""
    f = lambda v: f"{v:.{nd}f}".rstrip("0").rstrip(".")
    out = []
    for segs in segs_per_ring:
        if not segs:
            continue
        s0 = segs[0][0]
        out.append(f"M{f(s0[0])} {f(s0[1])}")
        for c in segs:
            out.append(f"C{f(c[1][0])} {f(c[1][1])} {f(c[2][0])} {f(c[2][1])} {f(c[3][0])} {f(c[3][1])}")
        out.append("Z")
    return "".join(out)


@dataclass
class Outline:
    d: str                                   # SVG path (fill-rule evenodd 로 구멍 처리)
    rings: list[list[np.ndarray]] = field(default_factory=list)
    bounds: tuple[float, float, float, float] = (0, 0, 0, 0)

    @property
    def handles(self) -> int:
        return sum(len(r) for r in self.rings)


def wobble(R: np.ndarray, amp: float, freq: float, seed: int = 0) -> np.ndarray:
    """손맛: 외곽선 점을 법선 방향으로 저주파 잡음만큼 민다(둘레당 freq 물결, 진폭 amp). 같은 씨앗이면 같은 결과"""
    if amp <= 0 or len(R) < 8:
        return R
    t = np.roll(R, -1, 0) - np.roll(R, 1, 0)
    n = np.stack([t[:, 1], -t[:, 0]], axis=1)
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(R, axis=0), axis=1))]
    L = s[-1] + np.linalg.norm(R[0] - R[-1])
    rng = np.random.default_rng(seed)
    u = 2 * math.pi * s / max(L, 1e-9)
    noise = sum(w * np.sin(k * max(1.0, round(freq)) * u + rng.uniform(0, 2 * math.pi)) for k, w in ((1, 0.6), (2, 0.3), (3, 0.1)))
    return R + n * (amp * noise)[:, None]


def outline(shape: Shape, res: float = 1.0, err: float | None = None, corner_angle: float = 50.0, min_area: float | None = None,
            wobble_amp: float = 0.0, wobble_freq: float = 3.0, seed: int = 0) -> Outline:
    """덩어리 → 닫힌 베지어 외곽선. res = 격자 간격(같은 단위), err = 맞춤 허용 거리(기본 res×0.6),
    wobble_amp > 0 이면 손맛(외곽선이 아주 살짝 흔들림)"""
    F, x0, y0 = sample(shape, res)
    loops = contours(F, x0, y0, res)
    min_area = (4 * res) ** 2 if min_area is None else min_area
    err = res * 0.6 if err is None else err
    rings, pts = [], []
    for R in loops:
        x, y = R[:, 0], R[:, 1]
        area = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
        if area < min_area:
            continue
        cs = corners(R, corner_angle)
        if wobble_amp > 0:
            R = wobble(R, wobble_amp, wobble_freq, seed + len(rings))
        rings.append(fit_ring(R, err, corner_angle, cs))
        pts.append(R)
    if pts:
        A = np.vstack(pts)
        b = (float(A[:, 0].min()), float(A[:, 1].min()), float(A[:, 0].max()), float(A[:, 1].max()))
    else:
        b = (0, 0, 0, 0)
    return Outline(path_d(rings), rings, b)


def bezier_points(rings: list[list[np.ndarray]], per: int = 16) -> list[np.ndarray]:
    """시험 · 측정용: 베지어를 다시 점으로"""
    t = np.linspace(0, 1, per, endpoint=False)
    return [np.vstack([_bez(c, t) for c in segs]) for segs in rings if segs]
