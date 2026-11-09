#!/usr/bin/env python3
"""
배포층: YouTube Data API v3 로 MP4 를 쇼츠로 업로드한다 (재개 가능 업로드).

- 제목: 콘티 title, 설명: caption + 출처 + 면책, 태그: hashtags('#' 제거), 카테고리 28(과학기술) 또는 22(인물·블로그)
- 공개 상태: --privacy (기본 private). --publish-at ISO8601 이면 private + publishAt 예약
- 인증: 환경변수 YOUTUBE_CLIENT_SECRET (Google Cloud OAuth 데스크톱 앱 client_secret.json 경로),
        토큰은 ~/.shortsforge/youtube_token.json 에 캐시
- 멱등성: data/storyboards/_published.jsonl 에 같은 콘티 id 가 있으면 업로드하지 않는다 (중복 업로드 방지 — 기존 채널에서 재업로드가 잦았음)
- 쿼터: videos.insert 는 2025-12 이후 약 100 units (하루 10,000) — 하루 2편은 여유

사용:
  export YOUTUBE_CLIENT_SECRET=~/client_secret.json
  python engine/publish/upload_youtube.py data/storyboards/<id>.json data/out/<id>-<엔진>-<템플릿>.mp4 [--privacy public|unlisted|private] [--publish-at 2026-11-03T12:00:00+09:00] [--category 28]
첫 실행 시 브라우저가 열려 구글 로그인 → 이후 토큰 재사용.
"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
PUBLISHED = ROOT / "data" / "storyboards" / "_published.jsonl"
TOKEN = Path.home() / ".shortsforge" / "youtube_token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
DISCLAIMER = {"ad": "※ 매출·수익은 상권·입지·매장 상황에 따라 다를 수 있습니다.",
              "daily": "※ 시세는 당일 입고 기준이며 변동될 수 있습니다."}


def already_published(sid: str):
    if not PUBLISHED.exists():
        return None
    for line in PUBLISHED.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if row.get("id") == sid:
            return row
    return None


def credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
            if not secret or not Path(secret).expanduser().exists():
                sys.exit("환경변수 YOUTUBE_CLIENT_SECRET 에 client_secret.json 경로를 넣으세요 (Google Cloud > OAuth 데스크톱 앱).")
            flow = InstalledAppFlow.from_client_secrets_file(str(Path(secret).expanduser()), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN.parent.mkdir(parents=True, exist_ok=True)
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def build_description(sb: dict) -> str:
    parts = [sb.get("caption", "").strip()]
    srcs = [s for s in sb.get("sources", []) if str(s).startswith("http")]
    base = ROOT / "data" / "public" / "elements" / sb.get("id", "")
    for mp in sorted(base.glob("*/meta.json")) if base.exists() else []:          # 퍼온 클립 · 짤 출처(clip.py · meme.py 가 남긴 기록)
        try:
            m = json.loads(mp.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        so = m.get("source") or {}
        if m.get("kind") in ("clip", "meme") and so.get("url"):
            srcs.append(f"{so.get('author') or '?'} · {so.get('title') or ''} — {so['url']}")
    if srcs:
        parts.append("출처:\n" + "\n".join(dict.fromkeys(srcs)))
    d = DISCLAIMER.get(sb.get("format"))
    if d and d not in parts[0]:
        parts.append(d)
    tags = " ".join(h for h in sb.get("hashtags", []) if h.startswith("#"))
    if tags:
        parts.append(tags + " #Shorts")
    return "\n\n".join(p for p in parts if p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("storyboard"); ap.add_argument("mp4")
    ap.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    ap.add_argument("--publish-at", default=None, help="ISO8601, 예약 공개 (privacy 는 private 로 강제)")
    ap.add_argument("--category", default=None, help="YouTube 카테고리 id (기본 28=과학기술, 22=인물·블로그, 26=노하우·스타일)")
    ap.add_argument("--dry-run", action="store_true", help="업로드 없이 메타데이터만 출력")
    args = ap.parse_args()

    sb = json.loads(Path(args.storyboard).read_text(encoding="utf-8"))
    sid = sb["id"]
    mp4 = Path(args.mp4)
    if not mp4.exists():
        sys.exit(f"영상 파일 없음: {mp4}")
    prev = already_published(sid)
    if prev:
        sys.exit(f"이미 업로드됨: {sid} → {prev.get('url')} (중복 방지). 다시 올리려면 _published.jsonl 에서 줄을 지우세요.")

    category = args.category or "28"
    status = {"privacyStatus": args.privacy, "selfDeclaredMadeForKids": False}
    from genclip import has_generated            # 실사 생성 컷(engine/gen)이 있으면 자동으로
    if sb.get("synthetic") or has_generated(sb):  # 사실적인 합성 장면이 있으면 '변경 · 합성 콘텐츠' 표시 — YouTube 정책
        status["containsSyntheticMedia"] = True
    if args.publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = dt.datetime.fromisoformat(args.publish_at).astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    body = {
        "snippet": {
            "title": sb["title"][:100],
            "description": build_description(sb)[:5000],
            "tags": [h.lstrip("#") for h in sb.get("hashtags", [])][:30],
            "categoryId": category,
            "defaultLanguage": "ko",
        },
        "status": status,
    }
    if args.dry_run:
        print(json.dumps(body, ensure_ascii=False, indent=2)); return

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    yt = build("youtube", "v3", credentials=credentials())
    media = MediaFileUpload(str(mp4), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        progress, resp = req.next_chunk()
        if progress:
            print(f"업로드 {int(progress.progress() * 100)}%")
    vid = resp["id"]
    url = f"https://www.youtube.com/shorts/{vid}"
    with PUBLISHED.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": sid, "video_id": vid, "url": url, "privacy": status["privacyStatus"],
                            "publish_at": status.get("publishAt"), "uploaded_at": dt.datetime.now().isoformat(timespec="seconds")},
                           ensure_ascii=False) + "\n")
    print(f"완료: {url}  (상태 {status['privacyStatus']}{', 예약 ' + status['publishAt'] if status.get('publishAt') else ''})")


if __name__ == "__main__":
    main()
