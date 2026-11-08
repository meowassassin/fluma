#!/usr/bin/env python3
"""
로고 · 아이콘(2D, SVG) 받기 — 장면에 GitHub · Docker 같은 로고나 서비스 아이콘이 필요할 때.

  python3 engine/capture/icons.py find <낱말>                 # 받을 수 있는 곳 찾기 (로컬 팩 → Simple Icons)
  python3 engine/capture/icons.py fetch <id> <이름> [<이름> …]  # → data/compositions/<id>/<이름>.svg (scene.js 에서 "<이름>.svg" 로 쓴다)

찾는 순서
  1. 로컬 아이콘 팩 data/assets2d/icons/**/<이름>.svg — 사용자가 받아 둔 공식 팩(예: AWS 아키텍처 아이콘은 aws.amazon.com/architecture/icons
     에서 받아 data/assets2d/icons/aws/ 에 풀면 됨. AWS 약관상 아키텍처 다이어그램 용도로 쓸 수 있다)
  2. Simple Icons (CC0, 브랜드 로고 3000여 개) — https://simpleicons.org . AWS 로고는 없다
  3. Lucide (ISC, 일반 개념 아이콘 1600여 개 — 데이터베이스 · 사람 · 장바구니 · 시계 …) — https://lucide.dev
     `python3 engine/capture/icons.py concept <낱말>` 로 '회원 · 주문 · 쿼리' 같은 말에 맞는 아이콘 이름을 고른다(차트 항목 아이콘)
  못 찾으면 에이전트가 단순한 SVG 를 직접 그린다(남의 로고를 흉내 내지 말고 '서버 · 버킷 · 지구본' 같은 일반 모양으로).
로고는 상표다: 설명 · 정보 목적으로 원래 모양 · 색 그대로 쓰고, 바꿔 그리거나 우리 것처럼 보이게 쓰지 않는다.
"""
import json
import re
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
PACKS = ROOT / "data" / "assets2d" / "icons"
CACHE = ROOT / "data" / "workspace" / "asset-cache" / "icons"
SI_VER = "16.36.0"
SI = f"https://cdn.jsdelivr.net/npm/simple-icons@{SI_VER}/icons/{{slug}}.svg"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower().replace("+", "plus").replace(".", "dot"))


def local(name: str) -> list[Path]:
    if not PACKS.exists():
        return []
    s = slug(name)
    return sorted(p for p in PACKS.rglob("*.svg") if s in slug(p.stem))


def simple_icon(name: str) -> Path | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    s = slug(name)
    dst = CACHE / f"{s}.svg"
    if dst.exists():
        return dst
    try:
        with urllib.request.urlopen(SI.format(slug=s), timeout=20) as r:
            svg = r.read().decode("utf-8")
    except Exception:  # noqa: BLE001  (없는 이름 · 오프라인)
        return None
    # Simple Icons 는 검정 단색 path → 공식 브랜드 색을 채운다(없으면 흰색)
    color = "#FFFFFF"
    try:
        with urllib.request.urlopen(f"https://cdn.jsdelivr.net/npm/simple-icons@{SI_VER}/data/simple-icons.json", timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        items = data if isinstance(data, list) else data.get("icons", [])
        hit = next((i for i in items if slug(i.get("slug") or i.get("title", "")) == s), None)
        if hit and hit.get("hex"):
            color = "#" + hit["hex"]
    except Exception:  # noqa: BLE001
        pass
    svg = svg.replace("<svg ", f'<svg fill="{color}" ', 1)
    dst.write_text(svg, encoding="utf-8")
    return dst


LUCIDE_VER = "1.68.0"
LUCIDE = f"https://cdn.jsdelivr.net/npm/lucide-static@{LUCIDE_VER}/icons/{{name}}.svg"

# 낱말 → Lucide 아이콘(차트 항목 · 목록에 붙일 일반 모양). 앞에 있는 것이 먼저 맞는다
CONCEPTS = [
    (r"쿼리|query|sql|select", "database-zap"), (r"db|데이터베이스|database|테이블|table", "database"),
    (r"회원|사용자|유저|user|member|사람|고객|customer|명\b", "users"), (r"주문|order|구매|결제|payment|checkout", "shopping-cart"),
    (r"상품|product|item|재고", "package"), (r"서버|server|인스턴스|instance|컨테이너|container", "server"),
    (r"요청|request|api|호출|call|트래픽|traffic", "arrow-left-right"), (r"응답|response|지연|latency|시간|time|초\b|ms\b", "timer"),
    (r"속도|speed|성능|performance|처리량|throughput", "gauge"), (r"메모리|memory|ram", "memory-stick"), (r"cpu|프로세서", "cpu"),
    (r"디스크|disk|저장|storage", "hard-drive"), (r"네트워크|network", "network"), (r"캐시|cache", "layers"),
    (r"비용|요금|돈|원\b|달러|cost|price|비싸", "wallet"), (r"오류|에러|error|장애|실패|fail|버그|bug", "triangle-alert"),
    (r"성공|success|통과|해결|fix|정상", "circle-check"), (r"코드|code|함수|function|메서드|method", "code"),
    (r"파일|file|문서|document", "file-text"), (r"로그|log", "scroll-text"), (r"보안|security|권한|auth|로그인|login", "shield"),
    (r"메시지|message|채팅|chat|알림|notification", "message-circle"), (r"이메일|email|메일", "mail"), (r"검색|search", "search"),
    (r"목록|list|페이지|page", "list"), (r"반복|loop|루프|for\b", "repeat"), (r"배포|deploy|릴리스|release", "rocket"),
    (r"모바일|mobile|앱|app", "smartphone"), (r"웹|web|브라우저|browser", "globe"), (r"ai|모델|model|gpt|llm", "sparkles"),
    (r"사진|이미지|image|photo", "image"), (r"영상|video|동영상", "video"), (r"음악|music|소리|audio", "music"),
    (r"날짜|date|일정|calendar|월\b|년\b", "calendar"), (r"증가|상승|up|growth|늘", "trending-up"), (r"감소|하락|down|줄", "trending-down"),
]


def concept(word: str) -> str | None:
    w = (word or "").lower()
    return next((name for pat, name in CONCEPTS if re.search(pat, w)), None)


def lucide(name: str, color: str = "#FFFFFF", stroke: float = 2.0) -> Path | None:
    """Lucide 아이콘(선 그림)을 색 · 선 굵기를 정해 받는다(캐시)"""
    if not re.fullmatch(r"[a-z0-9-]{1,60}", name or ""):
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    dst = CACHE / f"lucide-{name}-{color.strip('#').lower()}-{stroke:g}.svg"
    if dst.exists():
        return dst
    try:
        with urllib.request.urlopen(LUCIDE.format(name=name), timeout=20) as r:
            svg = r.read().decode("utf-8")
    except Exception:  # noqa: BLE001  (없는 이름 · 오프라인)
        return None
    svg = svg.replace('stroke="currentColor"', f'stroke="{color}"').replace('stroke-width="2"', f'stroke-width="{stroke:g}"')
    dst.write_text(svg, encoding="utf-8")
    return dst


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("find", "fetch", "concept"):
        sys.exit(__doc__)
    if sys.argv[1] == "concept":
        for w in sys.argv[2:]:
            n = concept(w)
            print(f"{w}\t{n or '없음'}\t{'Lucide (ISC)' if n and lucide(n) else ''}")
        return
    if sys.argv[1] == "find":
        name = sys.argv[2]
        hits = local(name)
        for h in hits[:20]:
            print(f"로컬 팩  {h.relative_to(ROOT)}")
        si = simple_icon(name)
        print(f"Simple Icons (CC0)  {slug(name)}  {'있음' if si else '없음'}")
        if not hits and not si:
            print("→ 없음: 일반 모양 SVG 를 직접 그리거나, 공식 아이콘 팩을 data/assets2d/icons/ 에 받아 두세요")
        return
    sid, names = sys.argv[2], sys.argv[3:]
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,80}", sid):
        sys.exit("영상 id 가 올바르지 않음")
    out_dir = ROOT / "data" / "compositions" / sid
    out_dir.mkdir(parents=True, exist_ok=True)
    for n in names:
        src = (local(n) or [None])[0] or simple_icon(n)
        if not src:
            print(f"✗ {n}: 못 찾음 — 일반 모양 SVG 를 data/compositions/{sid}/{slug(n)}.svg 로 직접 그리세요", file=sys.stderr)
            continue
        dst = out_dir / f"{slug(n)}.svg"
        shutil.copy2(src, dst)
        origin = "로컬 팩" if PACKS in src.parents else "Simple Icons (CC0)"
        print(f"{dst.name}\t{origin}\t← scene.js 에서 \"{dst.name}\" (K.image 나 <img>)")


if __name__ == "__main__":
    main()
