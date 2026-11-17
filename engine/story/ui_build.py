"""ui_mock .tsx → build.mjs (품질 게이트). Agent 없이 기존 파일만 다시 빌드."""
from __future__ import annotations

import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())


def _ui_path(rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else ROOT / p


def ensure_ui_built(rel_ui: str, sb: dict, *, force: bool = False) -> bool:
    """TSX 가 있으면 build.mjs 만 — 성공 시 True."""
    ui = _ui_path(rel_ui)
    if not ui.exists():
        return False
    out_dir = ui.with_suffix("")
    png = out_dir / "1080x1920.png"
    if not png.exists():
        png = out_dir / "scene.png"
    if not force and png.exists() and png.stat().st_mtime >= ui.stat().st_mtime:
        return True
    bg = str((sb.get("direction") or {}).get("color_bg") or "#000000").lstrip("#")
    light = sum(int(bg[i : i + 2], 16) for i in (0, 2, 4)) / 765 > 0.5 if len(bg) >= 6 else False
    t0 = time.perf_counter()
    r = subprocess.run(
        ["node", str(ROOT / "tools" / "ui-scenes" / "build.mjs"), str(ui), str(out_dir), "--mode", "light" if light else "dark", "--png", "1080x1920"],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=ROOT,
    )
    ok = r.returncode == 0 and png.exists()
    print(f"[ui 빌드] {rel_ui} {round(time.perf_counter() - t0, 1)}초 · {'ok' if ok else 'fail'}", flush=True)
    return ok


def material_ui_ok(m: dict, sb: dict) -> bool:
    ui = m.get("ui")
    return bool(ui and isinstance(ui, str) and ensure_ui_built(ui, sb))


def scene_ui_satisfied(sb: dict, scene_n: int, replace_id: str | None = None) -> bool:
    sc = (sb.get("scenes") or [])[scene_n - 1]
    for m in sc.get("materials") or []:
        if m.get("type") != "ui_mock":
            continue
        if replace_id and m.get("id") != replace_id:
            continue
        if m.get("src"):
            return True
        if material_ui_ok(m, sb):
            return True
    return False


def warm_all_ui_mocks(sb: dict, *, workers: int = 3) -> list[str]:
    """콘티의 모든 ui_mock(ui 경로)을 병렬 빌드 — produce 재료 단계 전."""
    jobs: list[str] = []
    seen: set[str] = set()
    for sc in sb.get("scenes") or []:
        for m in sc.get("materials") or []:
            ui = m.get("ui")
            if m.get("type") == "ui_mock" and isinstance(ui, str) and ui not in seen:
                seen.add(ui)
                jobs.append(ui)
    if not jobs:
        return []
    ok: list[str] = []
    with ThreadPoolExecutor(max_workers=min(workers, len(jobs))) as ex:
        futs = {ex.submit(ensure_ui_built, ui, sb): ui for ui in jobs}
        for fut in as_completed(futs):
            ui = futs[fut]
            try:
                if fut.result():
                    ok.append(ui)
            except Exception as e:  # noqa: BLE001
                print(f"[ui 빌드] {ui} 예외: {e}", flush=True)
    return ok