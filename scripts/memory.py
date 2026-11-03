#!/usr/bin/env python3
"""
Fluma 공유 기억 — 메뉴(트렌드 · 브랜드 · 캐릭터 · 룩 · 스튜디오)를 넘나드는 LLM 기억.
Nimbalyst 기억 엔진 구조를 참고(2026-10-28 REA 분석): 기억 = 맥락을 품은 '페이지'(한 문장 아님),
유형 · 범위 · 상태 · 출처를 갖고, 자주 쓰이는 수치(회상 횟수)는 본문과 따로 둔다. 회상은 BM25,
질문이 없으면 우선순위 × 최근순. 자동 승격 없음(사람이 승인).

저장:  workspace/memory/pages/<id>.md   (앞머리 + 본문)      ← 내용(잘 안 바뀜)
       workspace/memory/stats.json                            ← 회상 횟수 · 마지막 회상 · 세션 수(자주 바뀜)

  python3 scripts/memory.py remember --type preference --scope global --title "2D 위주" --body "사용자는 ..." [--menu trends] [--session S]
  python3 scripts/memory.py recall --query "IT 영상 스타일" [--scope trends] [--limit 6] [--json] [--session S]
  python3 scripts/memory.py top [--scope brand] [--limit 8] [--json]       # 대화 시작 때 넣을 것
  python3 scripts/memory.py list [--json] · forget --id <id> · supersede --id <old> --by <new>

유형(type): preference(취향) · decision(결정) · instruction(지시) · convention(관례) · constraint(제약) · fact(사실) · error(실패 교훈)
범위(scope): global · trends · brand · character · look · studio · project:<콘티 id>
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEM = ROOT / "workspace" / "memory"
PAGES = MEM / "pages"
STATS = MEM / "stats.json"
TYPES = ["preference", "decision", "instruction", "convention", "constraint", "fact", "error"]
PRIORITY = {"instruction": 3, "constraint": 3, "decision": 2, "preference": 2, "convention": 2, "error": 1, "fact": 1}
SECRET = [re.compile(p) for p in (r"sk-[A-Za-z0-9_-]{16,}", r"AIza[0-9A-Za-z_-]{20,}", r"ghp_[A-Za-z0-9]{20,}", r"(?i)(api[_-]?key|password|secret|token)\s*[:=]\s*\S{6,}",
                                   r"-----BEGIN [A-Z ]*PRIVATE KEY-----")]


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def redact_check(text: str):
    """키 · 비밀번호는 기억에 남기지 않는다 (Nimbalyst redaction screen 과 같은 자리)."""
    for p in SECRET:
        if p.search(text):
            raise SystemExit("거절: 비밀 값(키 · 토큰 · 비밀번호)으로 보이는 내용은 기억하지 않습니다.")


def parse(p: Path) -> dict:
    s = p.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n(.*)", s, re.S)
    meta = json.loads(m.group(1)) if m else {}
    meta["body"] = (m.group(2) if m else s).strip()
    meta["file"] = p.name
    return meta


def pages(include_inactive=False) -> list[dict]:
    if not PAGES.exists():
        return []
    out = [parse(p) for p in sorted(PAGES.glob("*.md"))]
    return out if include_inactive else [x for x in out if x.get("status", "active") == "active"]


def load_stats() -> dict:
    return json.loads(STATS.read_text(encoding="utf-8")) if STATS.exists() else {}


def save_stats(st: dict):
    MEM.mkdir(parents=True, exist_ok=True)
    tmp = STATS.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STATS)


def tokens(text: str) -> list[str]:
    """한글은 2글자 조각(조사 붙은 말도 걸리게), 영문 · 숫자는 단어."""
    text = text.lower()
    out = re.findall(r"[a-z0-9]+", text)
    for w in re.findall(r"[가-힣]+", text):
        out += [w] if len(w) <= 2 else [w[i:i + 2] for i in range(len(w) - 1)]
    return out


def bm25(query: str, docs: list[dict], k1=1.4, b=0.75) -> list[tuple[float, dict]]:
    q = tokens(query)
    if not q or not docs:
        return []
    toks = [tokens(d.get("title", "") + " " + d.get("title", "") + " " + d["body"] + " " + " ".join(d.get("tags", []))) for d in docs]
    avg = sum(map(len, toks)) / len(toks)
    df = {}
    for t in toks:
        for w in set(t):
            df[w] = df.get(w, 0) + 1
    N = len(docs)
    res = []
    for d, t in zip(docs, toks):
        tf = {}
        for w in t:
            tf[w] = tf.get(w, 0) + 1
        s = 0.0
        for w in set(q):
            if w in tf:
                idf = math.log(1 + (N - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * len(t) / avg))
        if s > 0:
            res.append((s, d))
    return sorted(res, key=lambda x: -x[0])


def in_scope(d: dict, scope: str | None) -> bool:
    return not scope or d.get("scope") in ("global", scope) or (scope.startswith("project:") and d.get("scope") == "studio")


def bump(found: list[dict], session: str | None):
    st = load_stats()
    for d in found:
        x = st.setdefault(d["id"], {"recallCount": 0, "sessions": []})
        x["recallCount"] += 1
        x["lastRecalledAt"] = now()
        if session and session not in x["sessions"]:
            x["sessions"] = (x["sessions"] + [session])[-50:]
    save_stats(st)


def show(found, as_json):
    if as_json:
        print(json.dumps([{k: d.get(k) for k in ("id", "type", "scope", "title", "body", "created", "provenance")} for d in found], ensure_ascii=False))
        return
    for d in found:
        print(f"[{d['type']}·{d['scope']}] {d['title']}  ({d['id']})\n  {d['body'][:300]}")


def cmd_remember(a):
    redact_check(a.title + " " + a.body)
    if a.type not in TYPES:
        raise SystemExit(f"type 은 {TYPES} 중 하나")
    pid = hashlib.sha1((a.scope + a.title + a.body).encode()).hexdigest()[:10]
    PAGES.mkdir(parents=True, exist_ok=True)
    p = PAGES / f"{pid}.md"
    if p.exists():
        print(f"이미 있음 {pid}")
        return
    # 같은 범위에서 제목이 같은 기억은 새 것으로 대체(결정이 바뀐 경우)
    for old in pages():
        if old["scope"] == a.scope and old["title"].strip() == a.title.strip():
            set_status(old["id"], "superseded", by=pid)
    meta = {"id": pid, "type": a.type, "scope": a.scope, "title": a.title, "status": "active", "created": now(),
            "tags": [t for t in (a.tags or "").split(",") if t], "provenance": {"kind": a.kind, "menu": a.menu, "session": a.session}}
    p.write_text("---\n" + json.dumps(meta, ensure_ascii=False) + "\n---\n" + a.body.strip() + "\n", encoding="utf-8")
    print(f"기억함 {pid} [{a.type}·{a.scope}] {a.title}")


def set_status(pid: str, status: str, by: str | None = None):
    p = PAGES / f"{pid}.md"
    if not p.exists():
        raise SystemExit(f"없음 {pid}")
    d = parse(p)
    body = d.pop("body"); d.pop("file")
    d["status"] = status
    if by:
        d["supersededBy"] = by
    p.write_text("---\n" + json.dumps(d, ensure_ascii=False) + "\n---\n" + body + "\n", encoding="utf-8")


def cmd_recall(a):
    docs = [d for d in pages() if in_scope(d, a.scope)] if not a.any_scope else pages()
    found = [d for _, d in bm25(a.query, docs)][: a.limit] if a.query else top(docs, a.limit)
    bump(found, a.session)
    show(found, a.json)


def top(docs, limit):
    def key(d):
        return (PRIORITY.get(d["type"], 1), d.get("created", ""))
    return sorted(docs, key=key, reverse=True)[:limit]


def cmd_top(a):
    show(top([d for d in pages() if in_scope(d, a.scope)], a.limit), a.json)


def cmd_list(a):
    st = load_stats()
    ps = pages(include_inactive=True)
    if a.json:
        print(json.dumps([{**{k: d.get(k) for k in ("id", "type", "scope", "title", "body", "status", "created", "provenance", "supersededBy")}, "stats": st.get(d["id"], {})} for d in ps], ensure_ascii=False))
        return
    for d in ps:
        s = st.get(d["id"], {})
        print(f"{d['id']} {d['status']:<10} [{d['type']}·{d['scope']}] {d['title']}  · 회상 {s.get('recallCount', 0)}회/{len(s.get('sessions', []))}세션")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("remember")
    r.add_argument("--type", required=True); r.add_argument("--scope", default="global"); r.add_argument("--title", required=True)
    r.add_argument("--body", required=True); r.add_argument("--tags"); r.add_argument("--menu"); r.add_argument("--session")
    r.add_argument("--kind", default="distilled", choices=["user", "distilled", "imported"])
    r.set_defaults(fn=cmd_remember)
    q = sp.add_parser("recall")
    q.add_argument("--query"); q.add_argument("--scope"); q.add_argument("--any-scope", action="store_true"); q.add_argument("--limit", type=int, default=6)
    q.add_argument("--json", action="store_true"); q.add_argument("--session")
    q.set_defaults(fn=cmd_recall)
    t = sp.add_parser("top")
    t.add_argument("--scope"); t.add_argument("--limit", type=int, default=8); t.add_argument("--json", action="store_true")
    t.set_defaults(fn=cmd_top)
    l = sp.add_parser("list"); l.add_argument("--json", action="store_true"); l.set_defaults(fn=cmd_list)
    f = sp.add_parser("forget"); f.add_argument("--id", required=True); f.set_defaults(fn=lambda a: (set_status(a.id, "archived"), print("보관함", a.id)))
    s = sp.add_parser("supersede"); s.add_argument("--id", required=True); s.add_argument("--by", required=True)
    s.set_defaults(fn=lambda a: (set_status(a.id, "superseded", a.by), print("대체됨", a.id)))
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
