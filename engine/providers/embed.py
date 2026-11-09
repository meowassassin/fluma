#!/usr/bin/env python3
"""찾기(임베딩) — 설정에서 '찾기 · 임베딩' 모델을 골랐으면 뜻으로 비교 · 검색하고, 아니면 None(부르는 쪽이 글자 비교로).
낱말이 달라도 같은 뜻이면 찾는다: "고민 → 장점 나열 → 할인" 과 "문제 제기 후 이점 소개하고 쿠폰" 이 같은 구조임을 안다.
쓰는 곳: 콘셉트 겹침 · 뻔함 닮음(concepts.py) · 지난 영상 제목 겹침(lint) · Craft 기능 9,000개 검색(craft_catalog.py) · 그 밖에 search() 를 부르는 곳.
벡터는 data/cache/providers/emb/<모델>.json 에 문장 해시로 모아 두고 같은 문장은 다시 돈 쓰지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401

CACHE = ROOT / "data" / "cache" / "providers" / "emb"
_mem: dict[str, dict] = {}


def model() -> str | None:
    import catalog
    return catalog.chosen("embed")


def _store(mdl: str) -> tuple[Path, dict]:
    f = CACHE / (mdl.replace("/", "__").replace(":", "_") + ".json")
    if mdl not in _mem:
        try:
            _mem[mdl] = json.loads(f.read_text("utf-8")) if f.exists() else {}
        except ValueError:
            _mem[mdl] = {}
    return f, _mem[mdl]


def _h(t: str) -> str:
    return hashlib.sha1(t.strip().encode()).hexdigest()[:16]


def vectors(texts: list[str], sid: str = "-") -> list[list[float]] | None:
    """문장들 → 벡터(캐시). 모델이 없으면 None"""
    mdl = model()
    if not mdl:
        return None
    import catalog
    import openrouter as OR
    f, st = _store(mdl)
    todo = [t for t in dict.fromkeys(t.strip() for t in texts) if t and _h(t) not in st]
    for i in range(0, len(todo), 96):
        batch = todo[i:i + 96]
        row = next((m for m in catalog.raw().get("embeddings/models") or [] if m["id"] == mdl), {})
        price = catalog._f((row.get("pricing") or {}).get("prompt")) or 0
        est = round(sum(len(t) for t in batch) / 2 * price, 6)          # 글자 2개 ≈ 토큰 1개(어림)
        catalog.guard(sid, "embed", mdl, est, f"임베딩 {len(batch)}개", True)
        r = OR.embed(mdl, batch)
        for t, v in zip(batch, r["vectors"]):
            if v:
                st[_h(t)] = v
        catalog.record(sid, "embed", mdl, r.get("cost"), f"임베딩 {len(batch)}개", est=est)
    if todo:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(st), "utf-8")
    return [st.get(_h(t)) for t in texts]


def multimodal() -> bool:
    """고른 임베딩 모델이 그림도 받는가(오픈라우터 목록의 input_modalities) — 받으면 그림과 글을 같은 공간에서 견준다(CLIP 처럼)"""
    mdl = model()
    if not mdl:
        return False
    import catalog
    row = next((m for m in catalog.raw().get("embeddings/models") or [] if m["id"] == mdl), {})
    return "image" in ((row.get("architecture") or {}).get("input_modalities") or [])


def image_vectors(paths: list, sid: str = "-") -> list[list[float]] | None:
    """그림들 → 벡터(파일 내용 해시로 캐시). 그림을 받는 모델이 아니면 None"""
    if not multimodal():
        return None
    import catalog
    import openrouter as OR
    mdl = model()
    f, st = _store(mdl)
    keys = [hashlib.sha1(Path(p).read_bytes()).hexdigest()[:16] for p in paths]
    todo = [(k, p) for k, p in zip(keys, paths) if k not in st]
    for i in range(0, len(todo), 16):
        batch = todo[i:i + 16]
        catalog.guard(sid, "embed", mdl, 0.0, f"그림 임베딩 {len(batch)}장", True)
        inp = [{"content": [{"type": "image_url", "image_url": {"url": OR.data_url(Path(p))}}]} for _k, p in batch]
        js = OR.post("embeddings", {"model": mdl, "input": inp}, timeout=180).json()
        for (k, _p), d in zip(batch, js.get("data") or []):
            if d.get("embedding"):
                st[k] = d["embedding"]
        catalog.record(sid, "embed", mdl, OR._cost(js), f"그림 임베딩 {len(batch)}장")
    if todo:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(st), "utf-8")
    return [st.get(k) for k in keys]


def zero_shot(image, labels: list[tuple[str, list[str]]]) -> list[tuple[str, float]] | None:
    """그림 하나를 글로 적은 갈래들과 견준다(제로샷) → [(갈래, 확률)] 높은 순. 그림을 받는 임베딩 모델이 없으면 None"""
    iv = image_vectors([image])
    if not iv or not iv[0]:
        return None
    phrases = [t for _n, ts in labels for t in ts]
    tv = vectors(phrases)
    if tv is None:
        return None
    k, scores = 0, []
    for name, ts in labels:
        vs = tv[k:k + len(ts)]; k += len(ts)
        scores.append((name, sum(cosine(iv[0], v) for v in vs) / max(1, len(vs))))
    mx = max(s for _n, s in scores)
    ex = [(n, math.exp(50 * (s - mx))) for n, s in scores]
    tot = sum(e for _n, e in ex) or 1
    return sorted(((n, e / tot) for n, e in ex), key=lambda x: -x[1])


def cosine(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def similar(a: str, b: str) -> float | None:
    """뜻 비슷함 0~1(코사인). 모델이 없으면 None"""
    if not str(a or "").strip() or not str(b or "").strip():
        return 0.0
    vs = vectors([str(a), str(b)])
    return None if vs is None else cosine(vs[0], vs[1])


def search(query: str, docs: list[str], n: int = 15) -> list[tuple[float, int]] | None:
    """[(점수, 문서 번호)] 높은 순. 모델이 없으면 None"""
    vs = vectors([query, *docs])
    if vs is None:
        return None
    q = vs[0]
    scored = sorted(((cosine(q, v), i) for i, v in enumerate(vs[1:])), reverse=True)
    return scored[:n]
