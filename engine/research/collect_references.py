#!/usr/bin/env python3
"""
트렌드 층 1단계: 최근 N일 안에 올라온 쇼츠를 키워드로 수집하고 성과 비율을 계산한다.

출력: references/<week>/shorts.csv
  video_id, title, channel, subs, views, likes, comments, duration_sec,
  published, views_per_sub, hook_text(제목 기반 추정), url

필요: YOUTUBE_API_KEY (Google Cloud > YouTube Data API v3, 무료 10,000 units/day)
쿼터: search.list 100 units/회, videos.list 1, channels.list 1
      키워드 5개 × 페이지 1 = 약 500 units. 매일 돌려도 넉넉.
"""
import argparse
import csv
import datetime as dt
import os
import re
import sys
from pathlib import Path

try:
    from googleapiclient.discovery import build
except ImportError:
    sys.exit("pip install -r engine/requirements-full.txt 먼저 실행하세요.")

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
def iso_week(d: dt.date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def parse_duration(iso: str) -> int:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def search_shorts(yt, keyword: str, published_after: str, max_results: int):
    ids = []
    req = yt.search().list(
        part="id",
        q=keyword,
        type="video",
        videoDuration="short",          # < 4분. 아래에서 60초 이하로 다시 거름
        order="viewCount",
        publishedAfter=published_after,
        relevanceLanguage="ko",
        regionCode="KR",
        maxResults=min(max_results, 50),
    )
    res = req.execute()
    ids += [i["id"]["videoId"] for i in res.get("items", [])]
    return ids


def video_details(yt, ids):
    out = []
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        res = yt.videos().list(part="snippet,statistics,contentDetails", id=",".join(chunk)).execute()
        out += res.get("items", [])
    return out


def channel_subs(yt, channel_ids):
    subs = {}
    ids = list(set(channel_ids))
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        res = yt.channels().list(part="statistics", id=",".join(chunk)).execute()
        for c in res.get("items", []):
            st = c.get("statistics", {})
            subs[c["id"]] = int(st.get("subscriberCount", 0)) if not st.get("hiddenSubscriberCount") else 0
    return subs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keywords", nargs="+", required=True, help='예: "개발자 팁" "마케팅 꿀팁" "AI 툴"')
    ap.add_argument("--days", type=int, default=7, help="최근 N일 (트렌드 층 기본 7)")
    ap.add_argument("--max", type=int, default=40, help="키워드당 최대 수집 수")
    ap.add_argument("--max-sec", type=int, default=60, help="이 길이 이하만 쇼츠로 인정")
    ap.add_argument("--min-views", type=int, default=1000)
    ap.add_argument("--out", default=None, help="출력 폴더 (기본 references/<week>)")
    args = ap.parse_args()

    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        sys.exit("환경변수 YOUTUBE_API_KEY 가 없습니다.")
    yt = build("youtube", "v3", developerKey=key)

    today = dt.date.today()
    after = (dt.datetime.utcnow() - dt.timedelta(days=args.days)).replace(microsecond=0).isoformat() + "Z"
    out_dir = Path(args.out) if args.out else ROOT / "references" / iso_week(today)
    out_dir.mkdir(parents=True, exist_ok=True)

    ids = []
    for kw in args.keywords:
        found = search_shorts(yt, kw, after, args.max)
        print(f"[{kw}] {len(found)}개")
        ids += found
    ids = list(dict.fromkeys(ids))  # 중복 제거, 순서 유지

    items = video_details(yt, ids)
    items = [v for v in items if parse_duration(v["contentDetails"]["duration"]) <= args.max_sec]
    subs = channel_subs(yt, [v["snippet"]["channelId"] for v in items])

    rows = []
    for v in items:
        st = v.get("statistics", {})
        views = int(st.get("viewCount", 0))
        if views < args.min_views:
            continue
        ch = v["snippet"]["channelId"]
        s = subs.get(ch, 0)
        rows.append({
            "video_id": v["id"],
            "title": v["snippet"]["title"],
            "channel": v["snippet"]["channelTitle"],
            "channel_id": ch,
            "subs": s,
            "views": views,
            "likes": int(st.get("likeCount", 0)),
            "comments": int(st.get("commentCount", 0)),
            "duration_sec": parse_duration(v["contentDetails"]["duration"]),
            "published": v["snippet"]["publishedAt"][:10],
            # 구독자 대비 조회: 작은 채널의 '터진' 영상을 찾는 지표. subs 0(비공개)이면 views 그대로.
            "views_per_sub": round(views / s, 2) if s else views,
            "url": f"https://www.youtube.com/shorts/{v['id']}",
        })

    rows.sort(key=lambda r: r["views_per_sub"], reverse=True)
    out = out_dir / "shorts.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["video_id"])
        w.writeheader()
        w.writerows(rows)
    print(f"저장: {out} ({len(rows)}개, 최근 {args.days}일)")
    if len(rows) < 30:
        print("경고: 표본 30개 미만. 트렌드 갱신에는 쓰지 않는다 (볼트 2026bix/03 Development/트렌드층).")


if __name__ == "__main__":
    main()
