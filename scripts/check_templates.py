#!/usr/bin/env python3
"""
템플릿 검사 (엔진 무관): 에이전트가 템플릿을 만들거나 고친 뒤 실행한다.

  python3 scripts/check_templates.py                         # 설치된 모든 엔진의 모든 템플릿
  python3 scripts/check_templates.py --engine hyperframes --template Overlay [--storyboard storyboards/example.json]

검사: meta.json(이름·mood·captions) → 예시 콘티로 엔진 build → 정지 화면 1장(snapshot). 하나라도 실패하면 exit 1.
HTML 템플릿은 하드코딩 색(#rrggbb)이 있으면 경고 (룩 토큰 var(--accent) 등을 쓰는 게 원칙).
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engines import ENGINES, ROOT, adapter, list_engines, list_templates, make_job  # noqa: E402


def check(engine: str, template: str, sb: Path) -> tuple[bool, str]:
    tdir = ENGINES / engine / "templates" / template
    problems, warns = [], []
    meta = tdir / "meta.json"
    if not meta.exists():
        problems.append("meta.json 없음")
    else:
        try:
            m = json.loads(meta.read_text(encoding="utf-8"))
            if m.get("captions") not in ("self", "finish"):
                problems.append('meta.captions 는 "self" 또는 "finish"')
            if not m.get("mood"):
                warns.append("meta.mood 없음")
        except Exception as e:  # noqa: BLE001
            problems.append(f"meta.json 파싱 실패: {e}")
    for f in list(tdir.glob("*.css")) + list(tdir.glob("*.js")):
        lines = [i + 1 for i, l in enumerate(f.read_text(encoding="utf-8").splitlines())
                 if re.search(r"#[0-9A-Fa-f]{6}\b", l) and "var(--" not in l and not l.strip().startswith(("/*", "//", "*", "--"))]
        if lines:
            warns.append(f"{f.name}: 색 하드코딩 {len(lines)}줄")
    if not problems:
        try:
            job = make_job(sb, engine, template)
            eng = adapter(engine)
            if not eng.available():
                problems.append("엔진 미설치")
            else:
                png = eng.snapshot(job, [min(1.0, job.duration / 2)])[0]
                warns.append(f"스냅샷 {png.relative_to(ROOT)}")
        except SystemExit as e:
            problems.append(str(e)[-600:])
        except Exception as e:  # noqa: BLE001
            problems.append(f"{type(e).__name__}: {e}"[-600:])
    ok = not problems
    return ok, (" / ".join(problems) if problems else "통과") + (f"  ({'; '.join(warns)})" if warns else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine")
    ap.add_argument("--template")
    ap.add_argument("--storyboard", default=str(ROOT / "storyboards" / "example.json"))
    a = ap.parse_args()
    engines = [a.engine] if a.engine else list_engines()
    all_ok = True
    for e in engines:
        names = [a.template] if a.template else [t["name"] for t in list_templates(e)]
        for t in names:
            ok, msg = check(e, t, Path(a.storyboard))
            print(f"[{e}/{t}] {msg}")
            all_ok &= ok
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
