#!/usr/bin/env python3
"""
배포층: YouTube Data API v3 로 MP4 를 쇼츠로 업로드한다 (재개 가능 업로드).

- 제목: 콘티 title, 설명: caption + 출처 + 면책, 태그: hashtags('#' 제거), 카테고리 28(과학기술) 또는 22(인물·블로그)
- 공개 상태: --privacy (기본 private). --publish-at ISO8601 이면 private + publishAt 예약
- 인증: 작업 공간(설정 → YouTube)에서 연결한 계정 — ~/.shortsforge/youtube.json { client_id, client_secret, accounts: [{ id, refresh_token, channel }], default }.
        채널: --account <채널 id> → 환경변수 FLUMA_YT_ACCOUNT → 이 영상에 고른 것(data/compositions/<id>/youtube.account.json) → 기본 계정.
        연결한 계정이 없을 때만 예전 방식(환경변수 YOUTUBE_CLIENT_SECRET + ~/.shortsforge/youtube_token.json).
- 멱등성: data/storyboards/_published.jsonl 에 같은 콘티 id 가 같은 채널로(또는 채널 기록 없이) 올라가 있으면 업로드하지 않는다 (중복 업로드 방지)
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
STORE = Path.home() / ".shortsforge" / "youtube.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
DISCLAIMER = {"ad": "※ 매출·수익은 상권·입지·매장 상황에 따라 다를 수 있습니다.",
              "daily": "※ 시세는 당일 입고 기준이며 변동될 수 있습니다."}


def normalize(raw) -> dict:
    """studio/youtube.mjs normalize 와 같은 규칙 — 예전 한 계정 모양(refresh_token · channel)을 accounts[0] 로"""
    d = dict(raw) if isinstance(raw, dict) else {}
    accounts = [dict(a) for a in (d.get("accounts") if isinstance(d.get("accounts"), list) else []) if isinstance(a, dict) and a.get("id")]
    if d.get("refresh_token"):
        aid = (d.get("channel") or {}).get("id") or "legacy"
        if not any(a["id"] == aid for a in accounts):
            accounts.insert(0, {"id": aid, "refresh_token": d["refresh_token"], "channel": d.get("channel"), "connected_at": d.get("connected_at")})
    for k in ("refresh_token", "channel", "connected_at"):
        d.pop(k, None)
    ids = [a["id"] for a in accounts]
    d["accounts"] = accounts
    d["default"] = d.get("default") if d.get("default") in ids else (ids[0] if ids else None)
    return d


def load_store(path: Path = STORE) -> dict:
    try:
        return normalize(json.loads(path.read_text("utf-8")))
    except (OSError, ValueError):
        return normalize({})


def project_account(sid: str):
    """작업 공간에서 이 영상에 고른 채널 id(없으면 None)"""
    try:
        return json.loads((ROOT / "data" / "compositions" / sid / "youtube.account.json").read_text("utf-8")).get("id") or None
    except (OSError, ValueError, AttributeError):
        return None


def pick_account(store: dict, wanted):
    """고른 채널 계정(토큰 포함 — 이 프로세스 밖으로 내보내지 않는다). 고른 것이 연결돼 있지 않으면 오류, 안 골랐으면 기본"""
    accs = store.get("accounts") or []
    if wanted:
        a = next((x for x in accs if x["id"] == wanted), None)
        if not a:
            sys.exit(f"고른 YouTube 계정({wanted})이 연결돼 있지 않다 — 작업 공간 설정 → YouTube 에서 연결하거나 다른 계정을 고른다")
        return a
    return next((x for x in accs if x["id"] == store.get("default")), accs[0] if accs else None)


def already_published(sid: str, account=None):
    """같은 콘티를 같은 채널에 이미 올렸으면 그 줄. 채널 기록이 없는 예전 줄 · 채널을 모르는 업로드는 채널과 상관없이 막는다"""
    if not PUBLISHED.exists():
        return None
    for line in PUBLISHED.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if row.get("id") == sid and (not account or not row.get("account") or row.get("account") == account):
            return row
    return None


def account_credentials(store: dict, acc: dict):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    creds = Credentials(None, refresh_token=acc["refresh_token"], token_uri="https://oauth2.googleapis.com/token",
                        client_id=store.get("client_id"), client_secret=store.get("client_secret"))
    creds.refresh(Request())
    return creds


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


def source_lines(sb: dict) -> list[str]:
    """설명란 출처 — 콘티 sources(조사) + 퍼온 클립 · 짤 출처(clip.py · meme.py 가 남긴 기록)"""
    srcs = [s for s in sb.get("sources") or [] if str(s).startswith("http")]
    base = ROOT / "data" / "public" / "elements" / sb.get("id", "")
    for mp in sorted(base.glob("*/meta.json")) if base.exists() else []:          # 퍼온 클립 · 짤 출처(clip.py · meme.py 가 남긴 기록)
        try:
            m = json.loads(mp.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        so = m.get("source") or {}
        if m.get("kind") in ("clip", "meme") and so.get("url"):
            srcs.append(f"{so.get('author') or '?'} · {so.get('title') or ''} — {so['url']}")
    return list(dict.fromkeys(srcs))


def build_description(sb: dict) -> str:
    """설명란 — 완성 뒤 만든 업로드 정보(콘티 upload, engine/publish/metadata.py)가 있으면 그것, 없으면 caption + 출처 + 면책 + 해시태그"""
    if (sb.get("upload") or {}).get("description"):
        from metadata import full_description
        return full_description(sb, sb["upload"])
    parts = [(sb.get("caption") or "").strip()]
    srcs = source_lines(sb)
    if srcs:
        parts.append("출처:\n" + "\n".join(srcs))
    d = DISCLAIMER.get(sb.get("format"))
    if d and d not in parts[0]:
        parts.append(d)
    tags = " ".join(h for h in sb.get("hashtags") or [] if h.startswith("#"))
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
    ap.add_argument("--account", default=None, help="올릴 YouTube 채널 id(UC…) — 없으면 FLUMA_YT_ACCOUNT → 이 영상에 고른 채널 → 기본 계정")
    args = ap.parse_args()

    sb = json.loads(Path(args.storyboard).read_text(encoding="utf-8"))
    sid = sb["id"]
    mp4 = Path(args.mp4)
    if not mp4.exists():
        sys.exit(f"영상 파일 없음: {mp4}")
    sys.path.insert(0, str(ROOT / "engine" / "checks"))
    import quality_gate   # 품질 막음이 남은 영상은 올리지 않는다(2026-11-18)
    left = quality_gate.check(sid)
    if left:
        sys.exit(f"품질 막음 {len(left)}건이 남아 올리지 않는다 — produce 로 고친 뒤: " + " / ".join(left[:4]))
    store = load_store()
    wanted = args.account or os.environ.get("FLUMA_YT_ACCOUNT")
    if not wanted and project_account(sid) in [x["id"] for x in store["accounts"]]:
        wanted = project_account(sid)            # 이 영상에 고른 채널(끊긴 계정이면 기본 계정 — 작업 공간 서버와 같은 규칙)
    acc = pick_account(store, wanted)
    account = acc["id"] if acc else None
    prev = already_published(sid, account)
    if prev:
        sys.exit(f"이미 업로드됨: {sid} → {prev.get('url')} (중복 방지{', 채널 ' + account if account else ''}). 다시 올리려면 _published.jsonl 에서 줄을 지우세요.")

    category = args.category or "28"
    status = {"privacyStatus": args.privacy, "selfDeclaredMadeForKids": False}
    if sb.get("synthetic"):                       # 사실적인 합성 장면이 있으면 '변경 · 합성 콘텐츠' 표시 — YouTube 정책(콘티 synthetic: true)
        status["containsSyntheticMedia"] = True
    if args.publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = dt.datetime.fromisoformat(args.publish_at).astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    body = {
        "snippet": {
            "title": ((sb.get("upload") or {}).get("title") or sb["title"])[:100],          # 검색 · 추천용 제목(metadata.py) → 없으면 화면 제목
            "description": build_description(sb)[:5000],
            "tags": ((sb.get("upload") or {}).get("tags") or [h.lstrip("#") for h in sb.get("hashtags") or []])[:30],
            "categoryId": category,
            "defaultLanguage": "ko",
        },
        "status": status,
    }
    if args.dry_run:
        print(json.dumps({**body, "account": account}, ensure_ascii=False, indent=2)); return

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    yt = build("youtube", "v3", credentials=account_credentials(store, acc) if acc else credentials())
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
        f.write(json.dumps({"id": sid, "video_id": vid, "url": url, "account": account, "privacy": status["privacyStatus"],
                            "publish_at": status.get("publishAt"), "uploaded_at": dt.datetime.now().isoformat(timespec="seconds")},
                           ensure_ascii=False) + "\n")
    print(f"완료: {url}  (채널 {((acc or {}).get('channel') or {}).get('title') or account or '예전 토큰'} · 상태 {status['privacyStatus']}{', 예약 ' + status['publishAt'] if status.get('publishAt') else ''})")


if __name__ == "__main__":
    main()
