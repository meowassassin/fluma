#!/usr/bin/env python3
"""
트렌드 쇼츠를 실제로 '보고' 패턴을 잰다 (사용자가 요청할 때만 — 영상은 분석 뒤 지운다, 패턴만 남김).

  python3 scripts/trend_analyze.py <영상 id 또는 URL> [...]

저 화질(≤360p) 앞 30초만 받아서:
  - 컷: ffmpeg 장면 변화 감지 → 컷 시각 · 평균 샷 길이 · 첫 컷까지 시간(훅 속도)
  - 색: 1초마다 프레임 → 주요 색 5개 · 밝기 · 채도
  - 글자 자리: 가로 띠별 고대비 가장자리 밀도 → 자막/제목이 주로 놓이는 높이(위 · 가운데 · 아래)
  - 움직임: 연속 프레임 차이 평균(정적 · 보통 · 빠름)
  - 밀착 시트: 1초 간격 프레임 12장 한 장(에이전트가 직접 열어 본다)
결과: public/trends/analysis/<id>.json + <id>.jpg, index.json 의 항목에 analysis 표시.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat

ROOT = Path(__file__).resolve().parents[1]
TR = ROOT / "public" / "trends"
OUT = TR / "analysis"


def vid_of(s: str) -> str:
    m = re.search(r"(?:shorts/|v=|youtu\.be/)([A-Za-z0-9_-]{11})", s)
    return m.group(1) if m else s


def download(vid: str, d: Path) -> Path:
    url = f"https://www.youtube.com/shorts/{vid}"
    r = subprocess.run(["yt-dlp", "-q", "--no-warnings", "-f", "bv*[height<=480][vcodec^=avc1]/bv*[height<=480]/worst",
                        "-o", str(d / "v.%(ext)s"), url], capture_output=True, text=True, timeout=180)
    files = list(d.glob("v.*"))
    if not files:
        raise SystemExit(f"{vid}: 받기 실패 {r.stderr[-300:]}")
    return files[0]


def cuts(video: Path) -> list[float]:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-vf", "select='gt(scene,0.32)',showinfo", "-an", "-f", "null", "-"], capture_output=True, text=True)
    return [round(float(x), 2) for x in re.findall(r"pts_time:([\d.]+)", r.stderr)]


def frames(video: Path, d: Path, n=30) -> list[Path]:
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", "fps=2,scale=180:-2", "-t", "30", "-frames:v", str(n * 2), str(d / "f%03d.png")], check=True)
    return sorted(d.glob("f*.png"))


def palette(imgs):
    acc = {}
    for p in imgs[::2]:
        q = Image.open(p).convert("RGB").quantize(colors=5, method=Image.Quantize.MEDIANCUT)
        pal = q.getpalette()
        for cnt, i in q.getcolors():
            rgb = tuple(pal[i * 3:i * 3 + 3]); key = tuple(v // 24 for v in rgb)
            a = acc.setdefault(key, [0, rgb]); a[0] += cnt
    top = sorted(acc.values(), key=lambda x: -x[0])[:5]
    tot = sum(x[0] for x in top) or 1
    return [{"hex": "#%02X%02X%02X" % x[1], "w": round(x[0] / tot, 2)} for x in top]


def text_bands(imgs):
    """가로 8띠: 가장자리(글자 · 테두리) 밀도. 자막 · 제목이 놓이는 높이 추정."""
    bands = [0.0] * 8
    for p in imgs:
        g = Image.open(p).convert("L").filter(ImageFilter.FIND_EDGES)
        w, h = g.size
        for k in range(8):
            band = g.crop((0, k * h // 8, w, (k + 1) * h // 8))
            bands[k] += sum(1 for v in band.tobytes() if v > 90) / (w * h / 8)
    m = max(bands) or 1
    return [round(b / m, 2) for b in bands]


def motion(imgs):
    from PIL import ImageChops
    ds = []
    for a, b in zip(imgs, imgs[1:]):
        ds.append(ImageStat.Stat(ImageChops.difference(Image.open(a).convert("L"), Image.open(b).convert("L"))).mean[0])
    return round(sum(ds) / max(1, len(ds)), 1)


def sheet(imgs, dst: Path):
    pick = imgs[::2][:12]
    if not pick:
        return
    w, h = Image.open(pick[0]).size
    S = Image.new("RGB", (w * 6, h * 2), "black")
    for i, p in enumerate(pick):
        S.paste(Image.open(p).convert("RGB"), ((i % 6) * w, (i // 6) * h))
    S.save(dst, quality=82)


def analyze(arg: str):
    vid = vid_of(arg)
    OUT.mkdir(parents=True, exist_ok=True)
    d = Path(tempfile.mkdtemp(prefix="fluma-tr-", dir=ROOT / "workspace" / "tmp" if (ROOT / "workspace" / "tmp").exists() else None))
    try:
        v = download(vid, d)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(v)], capture_output=True, text=True).stdout or 0)
        cs = cuts(v)
        fs = frames(v, d)
        bands = text_bands(fs)
        lum = [ImageStat.Stat(Image.open(p).convert("L")).mean[0] for p in fs]
        sat = [ImageStat.Stat(Image.open(p).convert("HSV")).mean[1] for p in fs]
        mot = motion(fs)
        shots = [b - a for a, b in zip([0.0] + cs, cs + [dur])] if dur else []
        zone = ["위", "위", "위-가운데", "가운데", "가운데", "가운데-아래", "아래", "아래"]
        top2 = sorted(range(8), key=lambda k: -bands[k])[:2]
        res = {
            "id": vid, "analyzed_sec": round(dur, 1),
            "cuts": cs, "cut_count": len(cs), "avg_shot_sec": round(sum(shots) / len(shots), 2) if shots else None,
            "first_cut_sec": cs[0] if cs else None,
            "rhythm": "빠름" if shots and sum(shots) / len(shots) < 1.6 else "보통" if shots and sum(shots) / len(shots) < 3.5 else "느림",
            "palette": palette(fs), "brightness": round(sum(lum) / len(lum)), "saturation": round(sum(sat) / len(sat)),
            "text_bands": bands, "text_zone": " · ".join(dict.fromkeys(zone[k] for k in top2)),
            "motion": mot, "motion_level": "빠름" if mot > 22 else "보통" if mot > 9 else "정적",
            "sheet": f"trends/analysis/{vid}.jpg",
        }
        sheet(fs, OUT / f"{vid}.jpg")
        (OUT / f"{vid}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        idx = TR / "index.json"
        if idx.exists():
            data = json.loads(idx.read_text(encoding="utf-8"))
            for it in data["items"]:
                if it["id"] == vid:
                    it["analysis"] = {k: res[k] for k in ("avg_shot_sec", "first_cut_sec", "rhythm", "text_zone", "motion_level", "palette")}
            tmp = idx.with_suffix(".tmp"); tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"); tmp.replace(idx)
        print(f"{vid}: 컷 {len(cs)}번 · 평균 샷 {res['avg_shot_sec']}s ({res['rhythm']}) · 첫 컷 {res['first_cut_sec']}s · 글자 자리 {res['text_zone']} · 움직임 {res['motion_level']} · 색 {' '.join(p['hex'] for p in res['palette'])}")
        print(f"   밀착 시트: public/{res['sheet']}  (열어서 화면 구성을 직접 볼 것)")
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for a in sys.argv[1:]:
        try:
            analyze(a)
        except SystemExit as e:
            print(e)
