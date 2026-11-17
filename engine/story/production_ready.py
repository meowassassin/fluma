"""콘티가 produce(오븐)에 들어갈 준비 — lint L=0."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())


def _lint_hard(sb: dict) -> tuple[bool, list[tuple[str, int | None, str]]]:
    sys.path.insert(0, str(ROOT / "engine" / "checks"))
    from lint import lint  # noqa: E402

    fails = lint(sb)
    hard = [f for f in fails if not f[0].startswith("T")]
    return (not hard, hard)


def touch_production_ready(sbp: Path) -> bool:
    sbp = sbp if sbp.is_absolute() else ROOT / sbp
    from material_evidence import apply_file  # noqa: E402

    apply_file(sbp, write=True)
    sb = json.loads(sbp.read_text("utf-8"))
    ok, hard = _lint_hard(sb)
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    meta = sb.setdefault("meta", {})
    if not isinstance(meta, dict):
        meta = {}
        sb["meta"] = meta
    meta["production_ready"] = ok
    meta["production_ready_at"] = ts
    if ok:
        meta.pop("production_lint_fail", None)
    else:
        meta["production_lint_fail"] = [f"{c} {msg}" for c, idx, msg in hard[:8]]
    # 루트 칸은 스키마 밖이라 다음 lint L01 — 제거
    sb.pop("production_ready", None)
    sb.pop("production_ready_at", None)
    sb.pop("production_lint_fail", None)
    sbp.write_text(json.dumps(sb, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return ok


if __name__ == "__main__":
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not p or not p.exists():
        print("usage: python3 engine/story/production_ready.py data/storyboards/<id>.json", file=sys.stderr)
        sys.exit(2)
    sys.exit(0 if touch_production_ready(p) else 1)