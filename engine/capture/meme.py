#!/usr/bin/env python3
"""
밈 · 짤 찾기 — 국내외 커뮤니티 인기글에서 짤(이미지 · GIF · 짧은 영상)을 모으고, 고른 것을 레이어 요소로 받는다.

  python3 engine/capture/meme.py search [--source reddit,dcbest,fmk,ruli] [--query "aws"] [--sub ProgrammerHumor] [--days 14] [--limit 30]
  python3 engine/capture/meme.py list [--query "서버"] [--source reddit]
  python3 engine/capture/meme.py fetch <영상 id> <이름> <밈 id> [--pick 0] [--sec 6] [--allow-face]
  python3 engine/capture/meme.py credits <영상 id>        # 영상에 쓴 웹 자료(짤 · 웹 녹화)의 '사용한 자료' 목록

출처
  reddit  r/ProgrammerHumor 등 (RSS · 검색 가능)
  dcbest  디시인사이드 실시간 베스트 (HIT 갤러리는 2023-09 업데이트 중지)
  4chan   /g/ (기술 · worksafe) 공식 JSON API — 검색어가 맞는 스레드는 답글 그림까지. 혐오 · 선정 낱말이 있는 글은 뺀다
  devrant devRant 공개 API — 개발자 하소연 · 밈(그림 붙은 글)
  lemmy   programming.dev 의 programmer_humor (연합형 레딧 대안)
  tenor   Tenor GIF 검색 — 반응 짤(분신술 · 기가채드 · This is fine …)을 낱말로. --query 필수
  fmk     에펨코리아 포텐 터짐 — 자동 접근을 보안 시스템(430)으로 막는다. 막히면 우회하지 않고 멈춘다(기본 출처에서 뺌)
  ruli    루리웹 유머 베스트

모은 목록은 data/public/memes/index.json, 썸네일은 data/public/memes/thumbs/ 에 둔다(트렌드처럼 웹 화면에서 볼 수 있게).
받은 짤은 data/public/elements/<id>/<이름>/ f0001.png … + meta.json(출처 · 작성자 · 날짜 · 원본 주소) → K.seq 로 바로 쓴다.

커뮤니티 짤은 대부분 저작권자가 따로 있다. 출처를 남기고, 설명의 소재로 짧게(인용 범위) 쓰고, 그 위에 우리 해설 · 주석을 얹는다.
얼굴이 크게 나온 사진(실존 인물일 가능성)은 기본으로 fetch 를 거절한다 — 사람이 보고 --allow-face 로 허락할 때만.
"""
import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import requests

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
PUBLIC = ROOT / "data" / "public"
MEMES = PUBLIC / "memes"
INDEX = MEMES / "index.json"
THUMBS = MEMES / "thumbs"
ID_RE = re.compile(r"^[A-Za-z0-9가-힣_-]{1,80}$")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
KST = timezone(timedelta(hours=9))
SUBS = ["ProgrammerHumor", "memes", "techhumor", "sysadmin", "linuxmemes", "dankmemes", "softwaregore", "programminghorror"]
# 4chan 은 업무용으로 안전한(worksafe) 게시판만 — 기술 /g/ (공식 JSON API, 1초에 1번 이하)
CHAN_BOARDS = ["g"]
# 글에 이런 말이 있으면 고르지 않는다(혐오 · 선정)
BLOCK = re.compile(r"(?i)nigg|fag+ot|retard|tranny|kike|porn|nsfw|hentai|nude|gore|rape|hitler|nazi")
FACE_RATIO = 0.04          # 얼굴 하나가 화면의 4% 넘게 차지하면 '얼굴 사진'으로 본다
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "ko,en;q=0.8"})


class Blocked(Exception):
    pass


def get(url: str, referer: str | None = None, binary=False, tries=4):
    """예의 있게: 요청 사이 0.6초, 429(너무 많음)면 점점 오래 쉬고 다시."""
    for k in range(tries):
        time.sleep(0.6)
        r = S.get(url, headers={"Referer": referer} if referer else None, timeout=20)
        if r.status_code == 430 or "보안 시스템" in r.text[:2000]:
            raise Blocked(f"{urlparse(url).hostname} 이 자동 접근을 막았습니다. 우회하지 않습니다.")
        if r.status_code == 429:
            wait = 4 * (k + 1)
            print(f"[meme] {urlparse(url).hostname} 요청이 많다고 해서 {wait}초 쉼", file=sys.stderr)
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.content if binary else r.text
    raise RuntimeError(f"429 계속: {url}")


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()


def section(page: str, start: str, end: str) -> str:
    i = page.find(start)
    if i < 0:
        return ""
    j = page.find(end, i + len(start))
    return page[i: j if j > 0 else i + 60000]


def kind_of(url: str) -> str:
    u = url.lower().split("?")[0]
    if u.endswith((".mp4", ".webm", ".mov")):
        return "video"
    if u.endswith(".gif"):
        return "gif"
    return "image"


def media_in(seg: str, base: str, host_re: str) -> list[dict]:
    urls = []
    for m in re.finditer(r'<(?:img|video|source)[^>]+?(?:data-original|data-src|src)="([^"]+)"', seg):
        u = html.unescape(m.group(1))
        u = urljoin(base, "https:" + u if u.startswith("//") else u)
        if re.search(host_re, u) and u not in urls:
            urls.append(u)
    return [{"url": u, "kind": kind_of(u)} for u in urls]


# ---------- 출처별 ----------
def reddit(query: str | None, subs: list[str], limit: int) -> list[dict]:
    out = []
    for sub in subs:
        if query:
            url = f"https://www.reddit.com/r/{sub}/search.rss?q={quote(query)}&restrict_sr=1&sort=top&t=year"
        else:
            url = f"https://www.reddit.com/r/{sub}/top/.rss?t=week"
        try:
            feed = get(url)
        except Exception as e:
            print(f"[meme] reddit r/{sub}: {e}", file=sys.stderr)
            continue
        for ent in re.findall(r"<entry>(.*?)</entry>", feed, re.S):
            body = html.unescape(ent)
            media = []
            for u in re.findall(r'https://(?:i\.redd\.it|i\.imgur\.com)/[A-Za-z0-9_-]+\.(?:jpe?g|png|gif|webp|mp4)', body):
                if u not in [m["url"] for m in media]:
                    media.append({"url": u, "kind": kind_of(u)})
            if not media:
                continue
            link = re.search(r'<link href="([^"]+)"', ent)
            out.append({"source": "reddit", "board": f"r/{sub}", "title": clean(re.search(r"<title>(.*?)</title>", ent, re.S).group(1)),
                        "url": link.group(1) if link else url, "author": clean((re.search(r"<name>(.*?)</name>", ent) or [None, ""])[1]),
                        "date": (re.search(r"<updated>(.*?)</updated>", ent) or [None, ""])[1][:19], "media": media})
            if len(out) >= limit:
                return out
    return out


def dcbest(query: str | None, pages: int, limit: int, boards: list[str] | None) -> list[dict]:
    rows = []
    for p in range(1, pages + 1):
        page = get(f"https://gall.dcinside.com/board/lists/?id=dcbest&page={p}")
        for no, typ, href, title, date in re.findall(r'<tr class="ub-content[^"]*"[^>]*data-no="(\d+)"[^>]*data-type="([^"]*)".*?<a[^>]*href="(/board/view/[^"]+)"[^>]*>(.*?)</a>'
                                                      r'.*?<td class="gall_date" title="([^"]+)"', page, re.S):
            if "notice" in typ:
                continue
            t = clean(title)
            board = (re.match(r"\[([^\]]+)\]", t) or [None, ""])[1]
            if boards and board not in boards:          # 실시간 베스트에는 정치 · 사건 글도 섞인다 → 기본은 짤 갤러리만
                continue
            rows.append((no, href, t, date))
    out = []
    for no, href, title, date in rows:
        if query and query.lower() not in title.lower():
            continue
        url = "https://gall.dcinside.com" + html.unescape(href).split("&page")[0]
        try:
            post = get(url, referer="https://gall.dcinside.com/board/lists/?id=dcbest")
        except Exception as e:
            print(f"[meme] dcbest {no}: {e}", file=sys.stderr)
            continue
        media = media_in(section(post, 'class="write_div"', 'class="btn_recommend_box'), url, r"dcimg\d*\.dcinside\.co\.kr|dcinside\.com/.*\.mp4")
        board = (re.match(r"\[([^\]]+)\]", title) or [None, ""])[1]
        if media:
            out.append({"source": "dcbest", "board": board, "title": title, "url": url, "date": date[:16], "author": "", "media": media, "referer": url})
        if len(out) >= limit:
            break
    return out


def fmk(query: str | None, pages: int, limit: int) -> list[dict]:
    rows = []
    for p in range(1, pages + 1):
        page = get(f"https://www.fmkorea.com/best?page={p}")
        for srl, title in re.findall(r'<h3 class="title"[^>]*>\s*<a href="/best/(\d+)"[^>]*>(.*?)</a>', page, re.S):
            rows.append((srl, clean(re.sub(r'<span class="comment_count">.*?</span>', "", title))))
    out = []
    for srl, title in rows:
        if query and query.lower() not in title.lower():
            continue
        url = f"https://www.fmkorea.com/best/{srl}"
        try:
            post = get(url, referer="https://www.fmkorea.com/best")
        except Blocked:
            raise
        except Exception as e:
            print(f"[meme] fmk {srl}: {e}", file=sys.stderr)
            continue
        media = media_in(section(post, 'class="xe_content"', '<!--AfterDocument'), url, r"fmkorea\.com/files/attach")
        date = (re.search(r'<span class="date m_no">([^<]+)', post) or [None, ""])[1]
        if media:
            out.append({"source": "fmk", "board": "포텐", "title": title, "url": url, "date": date.replace(".", "-")[:16], "author": "", "media": media, "referer": url})
        if len(out) >= limit:
            break
    return out


def ruli(query: str | None, pages: int, limit: int) -> list[dict]:
    rows = []
    for p in range(1, pages + 1):
        page = get(f"https://bbs.ruliweb.com/best/humor?page={p}")
        for href, title in re.findall(r'<a class="subject_link[^"]*" href="([^"]+)"[^>]*>(.*?)</a>', page, re.S):
            if "/best/board/" not in href:
                continue
            rows.append((href, re.sub(r"^\d+\s+", "", clean(title))))
    out = []
    for href, title in rows:
        if query and query.lower() not in title.lower():
            continue
        url = urljoin("https://bbs.ruliweb.com", html.unescape(href))
        try:
            post = get(url)
        except Exception as e:
            print(f"[meme] ruli: {e}", file=sys.stderr)
            continue
        media = media_in(section(post, "view_content", 'class="notice_read_bottom"'), url, r"i\d*\.ruliweb\.com/(?:img|ori|mp4)|\.mp4")
        date = (re.search(r'class="regdate">([^<]+)', post) or [None, ""])[1]
        if media:
            out.append({"source": "ruli", "board": "유머 베스트", "title": title, "url": url, "date": re.sub(r"[.\s()]+", "-", date).strip("-")[:16],
                        "author": "", "media": media, "referer": url})
        if len(out) >= limit:
            break
    return out


def fourchan(query: str | None, limit: int) -> list[dict]:
    """4chan /g/ (worksafe) — 공식 JSON API 의 카탈로그에서 글 · 첫 그림, 검색어가 맞는 스레드는 답글 그림까지"""
    import time as _t
    out = []
    for b in CHAN_BOARDS:
        cat = json.loads(get(f"https://a.4cdn.org/{b}/catalog.json"))
        for page in cat:
            for th in page.get("threads", []):
                text = clean(html.unescape(re.sub(r"<[^>]+>", " ", (th.get("sub") or "") + " " + (th.get("com") or ""))))
                if BLOCK.search(text) or (query and query.lower() not in text.lower()):
                    continue
                media = []
                if th.get("tim") and th.get("ext"):
                    media.append({"url": f"https://i.4cdn.org/{b}/{th['tim']}{th['ext']}", "kind": kind_of(th["ext"])})
                if query:   # 맞는 스레드: 답글 그림도
                    _t.sleep(1.1)
                    try:
                        posts = json.loads(get(f"https://a.4cdn.org/{b}/thread/{th['no']}.json")).get("posts", [])
                        for po in posts[1:]:
                            t2 = clean(html.unescape(re.sub(r"<[^>]+>", " ", po.get("com") or "")))
                            if po.get("tim") and po.get("ext") and not BLOCK.search(t2):
                                media.append({"url": f"https://i.4cdn.org/{b}/{po['tim']}{po['ext']}", "kind": kind_of(po["ext"])})
                    except Exception:
                        pass
                if media:
                    from datetime import datetime as _d
                    out.append({"source": "4chan", "board": f"/{b}/", "title": text[:120] or f"/{b}/ {th['no']}", "url": f"https://boards.4chan.org/{b}/thread/{th['no']}",
                                "date": _d.fromtimestamp(th.get("time", 0), KST).strftime("%Y-%m-%d"), "author": "Anonymous", "media": media[:12], "referer": f"https://boards.4chan.org/{b}/"})
                if len(out) >= limit:
                    return out
    return out


def devrant(query: str | None, limit: int) -> list[dict]:
    """devRant(개발자 하소연 · 밈) 공개 API — 그림이 붙은 글만"""
    try:   # 검색 API 가 자주 500 → 실패하면 이번 달 인기 글에서 낱말로 거른다
        d = json.loads(get(f"https://devrant.com/api/devrant/search?app=3&term={quote(query)}")) if query else None
    except Exception:
        d = None
    if not d or not d.get("results"):
        d = json.loads(get("https://devrant.com/api/devrant/rants?app=3&sort=top&range=week&limit=50"))
    out = []
    for r in d.get("results") or d.get("rants") or []:
        img = r.get("attached_image")
        img = img.get("url") if isinstance(img, dict) else None
        if not img or BLOCK.search(r.get("text", "")) or (query and not d.get("results") and query.lower() not in r.get("text", "").lower() and query.lower() not in " ".join(r.get("tags", [])).lower()):
            continue
        from datetime import datetime as _d
        out.append({"source": "devrant", "board": "devRant", "title": clean(r.get("text", ""))[:120], "url": f"https://devrant.com/rants/{r['id']}",
                    "date": _d.fromtimestamp(r.get("created_time", 0), KST).strftime("%Y-%m-%d"), "author": r.get("user_username", ""),
                    "media": [{"url": img, "kind": kind_of(img)}], "referer": "https://devrant.com/"})
        if len(out) >= limit:
            break
    return out


def lemmy(query: str | None, limit: int) -> list[dict]:
    """Lemmy programmer_humor (programming.dev) — 연합형 레딧 대안. 그림 링크 글만"""
    base = "https://programming.dev/api/v3"
    url = (f"{base}/search?q={quote(query)}&type_=Posts&community_name=programmer_humor&sort=TopYear&limit=50" if query
           else f"{base}/post/list?community_name=programmer_humor&sort=TopWeek&limit=50")
    d = json.loads(get(url))
    out = []
    for p_ in d.get("posts", []):
        po = p_["post"]; u = po.get("url") or ""
        if not re.search(r"\.(png|jpe?g|gif|webp|mp4|webm)(\?|$)", u, re.I) or BLOCK.search(po.get("name", "")) or po.get("nsfw"):
            continue
        out.append({"source": "lemmy", "board": "programmer_humor", "title": clean(po.get("name", ""))[:120], "url": po.get("ap_id") or u,
                    "date": (po.get("published") or "")[:10], "author": (p_.get("creator") or {}).get("name", ""), "media": [{"url": u, "kind": kind_of(u)}], "referer": "https://programming.dev/"})
        if len(out) >= limit:
            break
    return out


def tenor(query: str | None, limit: int) -> list[dict]:
    """Tenor 검색(GIF) — 반응 짤(나루토 분신술 · 기가채드 · This is fine · 놀란 피카츄 …)을 낱말로 찾는다. 검색어가 꼭 필요.
    검색 페이지에 박힌 GIF 주소와 그 GIF 의 제목(슬러그)을 모은다. 날짜가 없어 found 날짜를 쓴다."""
    if not query:
        return []
    slug = re.sub(r"[^0-9a-z가-힣]+", "-", query.lower()).strip("-")
    page = get(f"https://tenor.com/search/{slug}-gifs")
    urls = list(dict.fromkeys(re.findall(r"https://media1?\.tenor\.com/m/[A-Za-z0-9_-]+AAAAC/[A-Za-z0-9_-]+\.gif", page)))
    out = []
    for u in urls[:limit]:
        name = Path(urlparse(u).path).stem.replace("-", " ")
        out.append({"source": "tenor", "board": f"검색 '{query}'", "title": name, "url": u, "date": datetime.now(KST).strftime("%Y-%m-%d"),
                    "author": "", "media": [{"url": u, "kind": "gif"}], "referer": f"https://tenor.com/search/{slug}-gifs"})
    return out


# ---------- 썸네일 · 얼굴 ----------
_face = None


def faces_of(path: Path) -> float:
    """가장 큰 얼굴이 화면에서 차지하는 비율 (0 = 없음). OpenCV 가 없으면 -1."""
    global _face
    try:
        import cv2
    except ImportError:
        return -1.0
    if _face is None:
        _face = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return 0.0
    h, w = img.shape[:2]
    found = _face.detectMultiScale(img, scaleFactor=1.1, minNeighbors=6, minSize=(max(24, w // 20), max(24, w // 20)))
    return round(max((fw * fh for (_, _, fw, fh) in found), default=0) / float(w * h), 4)


def thumb_of(item: dict) -> None:
    THUMBS.mkdir(parents=True, exist_ok=True)
    m = item["media"][0]
    dst = THUMBS / f"{item['id']}.jpg"
    try:
        if m["kind"] == "video":
            hdr = f"Referer: {item.get('referer', item['url'])}\r\nUser-Agent: {UA}\r\n"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-headers", hdr, "-ss", "0.5", "-i", m["url"], "-frames:v", "1",
                            "-vf", "scale=360:-2", str(dst)], check=True, timeout=60)
        else:
            from io import BytesIO
            from PIL import Image
            data = get(m["url"], referer=item.get("referer"), binary=True)
            im = Image.open(BytesIO(data))
            im.seek(0)
            im = im.convert("RGB")
            im.thumbnail((360, 640))
            im.save(dst, quality=85)
        item["thumb"] = f"memes/thumbs/{dst.name}"
        item["face"] = faces_of(dst)
    except Exception as e:
        print(f"[meme] 썸네일 실패 {item['url']}: {e}", file=sys.stderr)


# ---------- 목록 ----------
def load() -> dict:
    if INDEX.exists():
        try:
            return json.loads(INDEX.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"items": []}


def save(d: dict):
    MEMES.mkdir(parents=True, exist_ok=True)
    d["updated"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    tmp = INDEX.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(INDEX)


def recent(item: dict, days: int) -> bool:
    try:
        d = datetime.fromisoformat(item["date"].replace("T", " ")[:16])
    except ValueError:
        return True
    return d >= datetime.now() - timedelta(days=days)


def show(items: list[dict]):
    for it in items:
        kinds = ",".join(sorted({m["kind"] for m in it["media"]}))
        face = " 얼굴!" if it.get("face", 0) > FACE_RATIO else ""
        print(f"{it['id']}  {it['source']:<6} {it['date'][:10]}  [{kinds} ×{len(it['media'])}]{face}  {it['title'][:50]}")


def cmd_search(a):
    d = load()
    have = {it["id"] for it in d["items"]}
    srcs = [s.strip() for s in a.source.split(",") if s.strip()]
    if a.query and a.days == 14:   # 낱말로 찾을 때는 오래된 명작 짤도 — 1년 안
        a.days = 365
    found = []
    for src in srcs:
        try:
            if src == "reddit":
                items = reddit(a.query, a.sub.split(",") if a.sub else SUBS, a.limit)
            elif src == "dcbest":
                items = dcbest(a.query, a.pages, a.limit, None if a.boards == "all" else a.boards.split(","))
            elif src == "fmk":
                items = fmk(a.query, a.pages, a.limit)
            elif src == "ruli":
                items = ruli(a.query, a.pages, a.limit)
            elif src == "tenor":
                items = tenor(a.query, a.limit)
            elif src == "4chan":
                items = fourchan(a.query, a.limit)
            elif src == "devrant":
                items = devrant(a.query, a.limit)
            elif src == "lemmy":
                items = lemmy(a.query, a.limit)
            else:
                print(f"[meme] 모르는 출처: {src}", file=sys.stderr)
                continue
        except Blocked as e:
            print(f"[meme] {src}: {e}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"[meme] {src} 실패: {e}", file=sys.stderr)
            continue
        new = []
        for it in items:
            it["id"] = hashlib.sha1(it["url"].encode()).hexdigest()[:10]
            it["query"] = a.query or ""
            it["found"] = datetime.now(KST).strftime("%Y-%m-%d")
            if not recent(it, a.days):
                continue
            if it["id"] not in have:
                thumb_of(it)
                new.append(it)
                have.add(it["id"])
            found.append(it)
        d["items"] = new + d["items"]
        save(d)                                  # 출처 하나 끝날 때마다 저장
        print(f"[meme] {src}: {len(items)}개 중 새로 {len(new)}개", file=sys.stderr)
    show(found)
    print(f"[meme] 목록: data/public/memes/index.json · 썸네일은 data/public/memes/thumbs/<id>.jpg 를 Read 로 본다")


def cmd_list(a):
    items = load()["items"]
    if a.source:
        items = [it for it in items if it["source"] == a.source]
    if a.query:
        items = [it for it in items if a.query.lower() in (it["title"] + it.get("query", "")).lower()]
    show(items[: a.limit])


def cmd_fetch(a):
    if not ID_RE.match(a.id) or not ID_RE.match(a.name):
        sys.exit("[meme] 잘못된 영상 id 또는 이름")
    it = next((x for x in load()["items"] if x["id"] == a.meme), None)
    if not it:
        sys.exit(f"[meme] 목록에 없는 밈 id: {a.meme} (먼저 search)")
    if it.get("face", 0) > FACE_RATIO and not a.allow_face:
        sys.exit("[meme] 얼굴이 크게 나온 짤입니다(실존 인물일 수 있음). 사용자에게 보여 주고 허락을 받은 뒤 --allow-face 로 받으세요.")
    if not (0 <= a.pick < len(it["media"])):
        sys.exit(f"[meme] --pick 은 0~{len(it['media']) - 1}")
    m = it["media"][a.pick]
    out = PUBLIC / "elements" / a.id / a.name
    if out.exists():
        for f in out.iterdir():
            f.unlink()
    out.mkdir(parents=True, exist_ok=True)
    ref = it.get("referer", it["url"])
    raw = out / ("src" + (Path(urlparse(m["url"]).path).suffix or ".bin"))
    raw.write_bytes(get(m["url"], referer=ref, binary=True))
    fps = 1
    if m["kind"] == "image":
        from PIL import Image
        im = Image.open(raw)
        im.seek(0)
        im.convert("RGBA").save(out / "f0001.png")
    else:   # GIF · 영상 → 프레임 (최대 a.sec 초, 30fps 이하, 긴 변 1080px 이하)
        fps = 30 if m["kind"] == "video" else 15
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(raw), "-t", str(a.sec),
                        "-vf", f"fps={fps},scale='min(1080,iw)':-2", str(out / "f%04d.png")], check=True)
    raw.unlink()
    frames = sorted(out.glob("f*.png"))
    if not frames:
        sys.exit("[meme] 프레임을 만들지 못했습니다.")
    from PIL import Image
    w, h = Image.open(frames[0]).size
    meta = {"frames": len(frames), "fps": fps, "ext": "png", "pad": 4, "w": w, "h": h, "size": max(w, h), "bbox": [0, 0, w, h],
            "transparent": False, "role": "meme", "engine": "web", "kind": "meme",
            "source": {"site": it["source"], "board": it.get("board"), "title": it["title"], "url": it["url"], "media": m["url"],
                       "author": it.get("author"), "date": it["date"]},
            "license": f"커뮤니티 게시물 — 출처: {it['url']}", "commercial": "불명확 (출처 표기 · 인용 범위에서)"}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[meme] {out.relative_to(ROOT)}: {len(frames)}프레임 {w}×{h}")
    print(f'[meme] 재료: {{"type": "meme", "src": "data/public/elements/{a.id}/{a.name}"}}')


def cmd_credits(a):
    """영상에 쓴 웹 자료의 출처 목록 — 영상 설명란 '사용한 자료' 에 붙인다."""
    if not ID_RE.match(a.id):
        sys.exit("[meme] 잘못된 영상 id")
    base = PUBLIC / "elements" / a.id
    lines = []
    for mp in sorted(base.glob("*/meta.json")) if base.exists() else []:
        m = json.loads(mp.read_text(encoding="utf-8"))
        if m.get("kind") == "meme":
            s = m["source"]
            lines.append(f"{s['title']} — {s['url']}")
        elif m.get("kind") == "clip":                    # clip.py 로 받은 영상 구간
            s = m["source"]
            lines.append(f"{s.get('author') or '?'} · {s.get('title') or ''} — {s['url']}")
        elif m.get("kind") == "web":
            lines += [u for u in m.get("sources", [])]
        elif m.get("license") and "CC-BY" in str(m.get("license")):
            lines.append(str(m["license"]))
    # 스톡 영상(Pexels · Pixabay) — 재료 기록의 credit
    mats = ROOT / "data" / "compositions" / a.id / "craft" / "materials"
    for mp in sorted(mats.glob("s*/*.json")) if mats.exists() else []:
        try:
            c = json.loads(mp.read_text(encoding="utf-8")).get("credit")
        except (OSError, ValueError, AttributeError):
            c = None
        if isinstance(c, dict) and c.get("page"):
            lines.append(f"{c.get('provider', '').capitalize()} · {c.get('author') or '작성자 미상'} — {c['page']}")
    seen = []
    for ln in lines:
        if ln not in seen:
            seen.append(ln)
    print("사용한 자료\n" + "\n".join(seen) if seen else "[meme] 출처를 표기할 웹 자료가 없습니다.")


def main():
    ap = argparse.ArgumentParser(description="커뮤니티 밈 · 짤 찾기 → 레이어 요소")
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("search", help="커뮤니티 인기글에서 짤 모으기")
    s.add_argument("--source", default="reddit,lemmy,devrant,tenor,dcbest,ruli", help="reddit, lemmy, devrant, 4chan(/g/ 만), tenor(반응 GIF · --query 필수), dcbest, ruli, fmk(자동 접근을 막는 경우가 많음)")
    s.add_argument("--boards", default="싱갤", help="디시 실시간 베스트에서 볼 갤러리 말머리, 쉼표로 (all = 전부)")
    s.add_argument("--query", help="제목 · 검색어 (reddit 은 검색, 국내는 인기글 제목에서 거름)")
    s.add_argument("--sub", help="reddit 서브레딧, 쉼표로 (기본: " + ",".join(SUBS) + ")")
    s.add_argument("--pages", type=int, default=2, help="국내 게시판 목록 페이지 수")
    s.add_argument("--days", type=int, default=14)
    s.add_argument("--limit", type=int, default=20, help="출처마다 최대 개수")
    s.set_defaults(fn=cmd_search)
    ls = sp.add_parser("list")
    ls.add_argument("--query")
    ls.add_argument("--source")
    ls.add_argument("--limit", type=int, default=60)
    ls.set_defaults(fn=cmd_list)
    f = sp.add_parser("fetch", help="고른 짤을 레이어 요소로 받기 (출처 기록)")
    f.add_argument("id")
    f.add_argument("name")
    f.add_argument("meme")
    f.add_argument("--pick", type=int, default=0, help="글 안의 몇 번째 이미지 · 영상인지")
    f.add_argument("--sec", type=float, default=6, help="GIF · 영상 최대 길이(초)")
    f.add_argument("--allow-face", action="store_true", help="얼굴이 크게 나온 짤도 받기 (사람이 확인한 뒤에만)")
    f.set_defaults(fn=cmd_fetch)
    c = sp.add_parser("credits", help="영상에 쓴 웹 자료 출처 목록")
    c.add_argument("id")
    c.set_defaults(fn=cmd_credits)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
