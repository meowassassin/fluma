#!/usr/bin/env python3
"""
트렌드 쇼츠 찾기 (API 키 없이). 에이전트가 사용자 말을 **검색어**(YouTube 검색 → 쇼츠 필터, 관련도순) 와 해시태그로 바꿔 부른다.
구체적인 주제(AWS · 특정 제품 · 기술 이름)는 검색어가 정확하다 — 해시태그 페이지(#aws)는 아무 영상이나 섞인다.
결과는 data/public/trends/index.json 에 **검색어 · 해시태그 하나 끝날 때마다** 저장 → 웹 트렌드 화면이 바로 갱신된다.
영상은 받지 않는다. 제목 · 조회수 · 세로 썸네일(data/public/trends/thumbs)만. 패턴만 쓰고 베끼지 않는다.

  python3 engine/research/trends.py search --queries "aws build,aws 아키텍처,aws 자격증" --label "AWS" --category 테크 [--limit 8] [--request "원문"]
  python3 engine/research/trends.py search --tags "2danimation,motiongraphics" --label "2D 모션" --category "2D 애니메이션"
  (--queries 와 --tags 를 함께 써도 됨)
  python3 engine/research/trends.py list                     # 요청별 요약
  python3 engine/research/trends.py remove --request <rid>   # 한 요청의 결과 지우기
"""
import argparse
import datetime as dt
import json
import os
import re
import signal
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
DIR = ROOT / "data" / "public" / "trends"
INDEX = DIR / "index.json"
THUMBS = DIR / "thumbs"
PUBLIC = ROOT / "data" / "public"


def _alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def load() -> dict:
    if not INDEX.exists():
        return {"requests": [], "items": []}
    d = json.loads(INDEX.read_text(encoding="utf-8"))
    # 프로세스가 사라졌는데 '찾는 중'으로 남은 요청(예전 버전 · 강제 종료)은 끊김으로 정리
    stale = [r for r in d["requests"] if r.get("status") == "running" and not _alive(r.get("pid"))]
    for r in stale:
        r["status"], r["error"] = "failed", r.get("error") or "중간에 끊김"
        r.pop("pid", None)
    if stale:
        save(d)
    return d


def save(d: dict):
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = INDEX.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(INDEX)


def hook_guess(title: str) -> str:
    """제목으로 훅 유형 어림 (영상 분석 아님 — 화면에 '추정'으로 표시)."""
    t = title.lower()
    if re.search(r"\bvs\.?\b|대결|vs\b", t): return "대결"
    if re.search(r"0%|100%|단계|level|lv\.?\s*\d", t): return "단계"
    if "?" in t or re.search(r"왜|어떻게|how|why|what if", t): return "질문형"
    if re.search(r"\d", t): return "숫자"
    if re.search(r"예상|반전|plot twist|wait for it|끝까지", t): return "반전"
    return "결과 먼저"


def thumb(vid: str) -> str | None:
    THUMBS.mkdir(parents=True, exist_ok=True)
    p = THUMBS / f"{vid}.jpg"
    if p.exists():
        return f"trends/thumbs/{p.name}"
    for name in ("oardefault", "hq2", "hqdefault"):
        try:
            with urllib.request.urlopen(f"https://i.ytimg.com/vi/{vid}/{name}.jpg", timeout=15) as r:
                p.write_bytes(r.read())
            return f"trends/thumbs/{p.name}"
        except Exception:  # noqa: BLE001
            continue
    return None


def hashtag(tag: str, limit: int) -> list[dict]:
    url = f"https://www.youtube.com/hashtag/{urllib.parse.quote(tag.lstrip('#'))}/shorts"
    r = subprocess.run(["yt-dlp", "--flat-playlist", "--dump-json", "--playlist-end", str(limit), "--no-warnings", url],
                       text=True, capture_output=True, timeout=120)
    out = []
    for line in r.stdout.splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("id"):
            out.append({"id": d["id"], "title": d.get("title") or "", "views": d.get("view_count")})
    return out


UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def views_num(txt: str | None) -> int | None:
    """'조회수 1.1만회' · '6397만회' · '1.2억회' · '8.4천회' · '1,234회' → 숫자"""
    if not txt:
        return None
    m = re.search(r"([\d.,]+)\s*(억|만|천)?", txt)
    if not m:
        return None
    n = float(m.group(1).replace(",", ""))
    return int(n * {"억": 1e8, "만": 1e4, "천": 1e3}.get(m.group(2) or "", 1))


def search(query: str, limit: int) -> list[dict]:
    """YouTube 검색 결과 페이지(쇼츠 필터)의 쇼츠 목록. 사용자가 youtube.com/results?search_query=… 에서 보는 것과 같은 관련도순.
    yt-dlp 는 검색 결과의 쇼츠 칸을 거의 못 읽어서 페이지의 ytInitialData 를 직접 읽는다."""
    url = "https://www.youtube.com/results?" + urllib.parse.urlencode({"search_query": query, "sp": "EgIQCQ==", "hl": "ko", "gl": "KR"})
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"})
    html = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "replace")
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html) or re.search(r'ytInitialData"\]\s*=\s*(\{.*?\});', html)
    if not m:
        return []
    out, seen = [], set()

    def walk(o):
        if isinstance(o, dict):
            v = o.get("shortsLockupViewModel")
            if v:
                vid = (((v.get("onTap") or {}).get("innertubeCommand") or {}).get("reelWatchEndpoint") or {}).get("videoId")
                ov = v.get("overlayMetadata") or {}
                title = (ov.get("primaryText") or {}).get("content") or (v.get("accessibilityText") or "").split(", 조회수")[0]
                if vid and vid not in seen:
                    seen.add(vid)
                    out.append({"id": vid, "title": title, "views": views_num((ov.get("secondaryText") or {}).get("content"))})
            r = o.get("reelItemRenderer")
            if r and r.get("videoId") not in seen:
                seen.add(r["videoId"])
                out.append({"id": r["videoId"], "title": ((r.get("headline") or {}).get("simpleText") or ""),
                            "views": views_num(((r.get("viewCountText") or {}).get("simpleText")))})
            for x in o.values():
                walk(x)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(json.loads(m.group(1)))
    return out[:limit]


# ---------- 화풍 판별 (썸네일을 CLIP 으로 봄) — 해시태그만으로는 2D 요청에 실사가 섞인다 ----------
# 예전에는 tools/vision(torch + open_clip, 약 1GB 가상환경)을 따로 돌렸다 → engine/research/vision_tags.py(ONNX CLIP, torch 없음)로 바꿈(2026-11-02)
VIS_KO = {"2d": "2D", "pixel": "픽셀", "3d": "3D", "live": "실사", "screen": "화면 녹화 · 게임"}
# vision_tags 의 화면 종류 → 트렌드 화풍 다섯 갈래
TAG2VIS = {"애니메이션 · 일러스트": "2d", "카드(글자)": "2d", "도표": "2d", "짤": "2d", "픽셀 아트": "pixel", "3D 그래픽": "3d",
           "사람": "live", "실사 영상": "live", "음식": "live", "제품": "live", "실제 화면": "screen", "기사": "screen", "게임 화면": "screen"}


def classify(paths: list[str]) -> dict:
    """{썸네일 경로: (화풍, 확률표)}. 분류기를 못 쓰면 빈 결과 (거르지 않음)"""
    if not paths:
        return {}
    try:
        import vision_tags
    except ImportError:
        return {}
    out = {}
    for p in paths:
        try:
            r = vision_tags.classify(p)
        except Exception as e:  # noqa: BLE001 — 한 장 실패는 건너뛴다
            print(f"[화풍] 분류 실패 {p}: {e}", file=sys.stderr); continue
        prob: dict[str, float] = {}
        for kind, pr in r["top"]:
            v = TAG2VIS.get(kind, "2d"); prob[v] = round(prob.get(v, 0) + pr, 3)
        out[p] = (TAG2VIS.get(r["kind"], "2d"), prob)
    return out


def want_of(text: str) -> set[str] | None:
    """요청 말에서 원하는 화풍. 2D · 3D · 픽셀은 한 묶음(그림 · 애니메이션) — 3D 쇼츠도 X-ray 로 분해해 생성 영상 프롬프트의
    화면 문법(engine/story/look.py)으로 쓰면 되므로 나누지 않는다(2026-11-06). 실사 · 화면 녹화를 콕 집어 말할 때만 그것으로 거르고,
    아무 말이 없으면 거르지 않는다(None)"""
    t = text.lower()
    anim = {"2d", "3d", "pixel"}
    if any(w in t for w in ("픽셀", "pixel", "2d", "3d", "애니", "모션그래픽", "motion graphic", "일러스트", "블렌더", "blender", "cgi")):
        return anim
    if "실사" in t or "live action" in t:
        return {"live"}
    if "화면 녹화" in t or "게임 화면" in t or "screen record" in t:
        return {"screen"}
    return None

def cmd_search(a):
    d = load()
    rid = dt.datetime.now().strftime("r%Y%m%d-%H%M%S")
    tags = [t.strip().lstrip("#") for t in (a.tags or "").split(",") if t.strip()]
    queries = [q.strip() for q in (a.queries or "").split(",") if q.strip()]
    if not tags and not queries:
        sys.exit("--queries 또는 --tags 가 필요합니다")
    req = {"id": rid, "text": a.request or a.label, "label": a.label, "category": a.category, "tags": tags, "queries": queries,
           "at": dt.datetime.now().isoformat(timespec="seconds"), "count": 0, "status": "running", "pid": os.getpid()}
    d["requests"].insert(0, req)
    save(d)
    # 어떤 이유로 끝나든(오류 · 멈춤 신호) 요청이 '찾는 중'으로 남지 않게
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        _search_into(a, d, req, queries, tags)
    except BaseException as e:
        req["status"] = "stopped" if isinstance(e, (KeyboardInterrupt, SystemExit)) else "failed"
        req["error"] = f"{type(e).__name__}: {e}"[:300]
        req.pop("pid", None)
        save(d)
        raise
    req.pop("pid", None)
    req["status"] = "done"
    save(d)
    rid = req["id"]
    items = [x for x in d["items"] if x["request"] == rid]
    items.sort(key=lambda x: -(x.get("views") or 0))
    print(f"\n[{a.label}] 새로 {len(items)}편 · 요청 {rid}")
    for x in items[:10]:
        v = x.get("views") or 0
        print(f"  {v:>13,}  {x['hook']:<4}  {x['title'][:60]}")


def _search_into(a, d, req, queries, tags):
    rid = req["id"]
    seen = {x["id"] for x in d["items"]}
    if a.want == "any":
        want = None
    elif a.want and a.want != "auto":
        want = {w.strip() for w in a.want.split(",") if w.strip() in VIS_KO} or None
    else:
        want = want_of(f"{a.label} {a.request or ''}")
    if want:
        print(f"[화풍] {' · '.join(VIS_KO[w] for w in sorted(want))} 만 남김 (썸네일을 보고 판별)")
    req["want"] = sorted(want) if want else None
    req["rejected"] = 0
    sources = [("search", q) for q in queries] + [("hashtag", t) for t in tags]
    for via, tag in sources:
        name = f"\"{tag}\"" if via == "search" else f"#{tag}"
        try:
            found = search(tag, a.limit * (2 if want else 1) + 4) if via == "search" else hashtag(tag, a.limit * (2 if want else 1))
        except (subprocess.TimeoutExpired, OSError) as e:
            print(f"{name}: 실패 ({e})", file=sys.stderr)
            continue
        new, fresh = 0, []
        for f in found:
            if f["id"] in seen:
                continue
            seen.add(f["id"])
            fresh.append({**f, "tag": tag, "via": via, "category": a.category, "label": a.label, "request": rid,
                          "hook": hook_guess(f["title"]), "thumb": thumb(f["id"]),
                          "url": f"https://www.youtube.com/shorts/{f['id']}"})
        vis = classify([str(PUBLIC / x["thumb"]) for x in fresh if x.get("thumb")])
        rej = 0
        for x in fresh:
            v, pr = vis.get(str(PUBLIC / x["thumb"]), (None, {})) if x.get("thumb") else (None, {})
            if v:
                x["visual"], x["visual_p"] = v, pr
            if want and v and v not in want:
                rej += 1
                continue
            if new >= a.limit:
                continue
            d["items"].insert(0, x)
            new += 1
        req["rejected"] += rej
        req["count"] += new
        save(d)  # 해시태그마다 저장 → 화면 즉시 갱신
        print(f"{name}: {len(found)}편 중 새로 {new}편" + (f" (화풍이 달라 뺀 것 {rej}편)" if rej else ""))


def cmd_list(_a):
    d = load()
    for r in d["requests"]:
        print(f"{r['id']}  {r['label']:<16} {r['count']:>3}편  #{' #'.join(r['tags'])}")


def cmd_remove(a):
    d = load()
    d["requests"] = [r for r in d["requests"] if r["id"] != a.request]
    d["items"] = [x for x in d["items"] if x["request"] != a.request]
    save(d)
    print("지움", a.request)


def cmd_remove_item(a):
    """쇼츠 하나를 목록에서 뺀다 (썸네일 · 분석 결과도 함께). 요청의 편 수도 줄인다"""
    d = load()
    ids = set(a.id)
    gone = [x for x in d["items"] if x["id"] in ids]
    d["items"] = [x for x in d["items"] if x["id"] not in ids]
    for x in gone:
        for r in d["requests"]:
            if r["id"] == x.get("request"):
                r["count"] = max(0, int(r.get("count", 0)) - 1)
        if x.get("thumb"):
            (PUBLIC / x["thumb"]).unlink(missing_ok=True)
        (DIR / "analysis" / f"{x['id']}.json").unlink(missing_ok=True)
        (DIR / "analysis" / f"{x['id']}.jpg").unlink(missing_ok=True)
    save(d)
    print("지움", ", ".join(x["id"] for x in gone) or "(없음)")


def cmd_classify(a):
    """이미 모은 쇼츠의 화풍을 판별하고, --prune 이면 요청과 맞지 않는 것을 지운다"""
    d = load()
    todo = [x for x in d["items"] if x.get("thumb") and (a.all or not x.get("visual"))]
    vis = classify([str(PUBLIC / x["thumb"]) for x in todo])
    for x in todo:
        v = vis.get(str(PUBLIC / x["thumb"]))
        if v and v[0]:
            x["visual"], x["visual_p"] = v
    for r in d["requests"]:   # 예전 요청에도 원하는 화풍을 적어 둔다 (화면에서 맞지 않는 것을 기본으로 숨김)
        if "want" not in r:
            w = want_of(f"{r.get('label', '')} {r.get('text', '')}")
            r["want"] = sorted(w) if w else None
    removed = 0
    if a.prune:
        reqs = {r["id"]: r for r in d["requests"]}
        keep = []
        for x in d["items"]:
            r = reqs.get(x["request"], {})
            w = set(r.get("want") or []) or want_of(f"{r.get('label', '')} {r.get('text', '')}")
            if w and x.get("visual") and x["visual"] not in w:
                removed += 1
                continue
            keep.append(x)
        d["items"] = keep
        for r in d["requests"]:
            r["count"] = sum(1 for x in keep if x["request"] == r["id"])
    save(d)
    from collections import Counter
    print(f"판별 {len(todo)}편 · 화풍 분포 {dict(Counter(x.get('visual') for x in d['items']))}" + (f" · 요청과 맞지 않아 뺀 것 {removed}편" if a.prune else ""))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("search")
    s.add_argument("--queries", help="쉼표로 구분한 검색어 (YouTube 검색 → 쇼츠, 관련도순). 구체적인 주제는 이것")
    s.add_argument("--tags", help="쉼표로 구분한 해시태그 (한국어 · 영어 섞기). 넓은 분야 · 스타일 탐색용")
    s.add_argument("--label", required=True, help="화면에 보일 요청 이름 (예: IT 관련)")
    s.add_argument("--category", default="기타")
    s.add_argument("--limit", type=int, default=8)
    s.add_argument("--request", help="사용자가 한 말 원문")
    s.add_argument("--want", default="auto", help="남길 화풍: auto(요청 말로 판단 — 기본은 거르지 않음, 2D · 3D · 픽셀은 한 묶음) · any · 2d,pixel,3d,live,screen")
    s.set_defaults(fn=cmd_search)
    sp.add_parser("list").set_defaults(fn=cmd_list)
    r = sp.add_parser("remove")
    r.add_argument("--request", required=True)
    r.set_defaults(fn=cmd_remove)
    ri = sp.add_parser("remove-item", help="쇼츠 하나(또는 여럿)를 목록에서 뺀다")
    ri.add_argument("--id", action="append", required=True)
    ri.set_defaults(fn=cmd_remove_item)
    c = sp.add_parser("classify", help="모은 쇼츠의 화풍(2D · 3D · 실사 …)을 썸네일로 판별")
    c.add_argument("--all", action="store_true", help="이미 판별한 것도 다시")
    c.add_argument("--prune", action="store_true", help="애니메이션 요청에 섞인 실사처럼 요청과 맞지 않는 것을 지움(2D · 3D 는 같은 묶음)")
    c.set_defaults(fn=cmd_classify)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
