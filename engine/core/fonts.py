#!/usr/bin/env python3
"""영상 글꼴 — 목록(engine/assets/fonts/catalog.json) · 받기 · 설치. 모두 OFL(상업 사용 가능).
저장소에 든 글꼴(bundled)은 engine/assets/fonts, 나머지는 tools/fonts 에 받는다(저장소를 무겁게 하지 않게 — Craft 앱처럼).
EffectCraft 는 EFFECTCRAFT_FONT_DIRS(두 폴더)를 보고, 다른 Craft 앱은 사용자 글꼴 폴더를 본다(install 이 복사).

  python3 engine/core/fonts.py list [--use title|subs|caption|body]   # 글꼴 · 분위기 · 쓰임 · 받았는지
  python3 engine/core/fonts.py fetch <PS 이름 …>                      # 미리 받기(보통은 필요 없음 — 렌더가 쓰는 글꼴만 그때 받는다)
  python3 engine/core/fonts.py                                        # 사용자 글꼴 폴더에 설치(받은 것 포함 · 없으면 Noto Sans CJK KR 도 받는다)
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "assets" / "fonts"
ROOT = Path(__file__).resolve().parents[2]
import sys as _sys  # noqa: E402
_sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401 — HTTPS 인증서(독립 빌드 파이썬은 CA 경로가 없다, 2026-11-20 위키미디어 검색 실패)
EXT = ROOT / "tools" / "fonts"
CATALOG = SRC / "catalog.json"
import os as _os  # noqa: E402
_OS = "windows" if _sys.platform.startswith("win") else "mac" if _sys.platform == "darwin" else "linux"
DST = (Path(_os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Microsoft" / "Windows" / "Fonts" if _OS == "windows"
       else Path.home() / "Library" / "Fonts" / "Fluma" if _OS == "mac" else Path.home() / ".local" / "share" / "fonts" / "fluma")   # 운영체제마다 사용자 글꼴 폴더
# Craft 앱(Design · Vector · Deck · Photo · Fig · Texture)의 한글 글꼴 — 시스템 글꼴 이름 'Noto Sans CJK KR' 로 찾는다(OFL, 굵기별 약 16MB).
# 2026-11-24: 설치가 이 글꼴을 깔지 않아, 글꼴이 없는 macOS · Windows · CI 에서 글자 단계가 'no font family' 로 멈췄다
NOTO_CJK = "Noto Sans CJK KR"
NOTO_URL = "https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/Korean/NotoSansCJKkr-{w}.otf"
NOTO_WEIGHTS = ("Regular", "Medium", "Bold", "Black")
NOTO_LICENSE = "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/LICENSE"
FILES = ("GowunBatang-Bold", "GowunBatang-Regular", "BlackHanSans-Regular", "NanumPenScript-Regular", "SongMyung-Regular", "Gugi-Regular")


def catalog() -> list[dict]:
    import json
    return json.loads(CATALOG.read_text("utf-8"))["fonts"]


def font_dirs() -> str:
    """EFFECTCRAFT_FONT_DIRS 값 — 저장소 글꼴 + 받은 글꼴"""
    import os
    return os.pathsep.join(str(d) for d in (SRC, EXT))


def _file(ps: str) -> str:
    return next((f.get("file") or f["ps"] for f in catalog() if f["ps"] == ps), ps)


def path_of(ps: str) -> Path | None:
    name = _file(ps)
    for d in (SRC, EXT):
        for ext in (".ttf", ".otf"):
            if (d / f"{name}{ext}").exists():
                return d / f"{name}{ext}"
    return None


def fetch(names: list[str] | None = None) -> list[str]:
    """없는 글꼴을 받는다(OFL 라이선스 파일도 함께). 받은 PostScript 이름 목록"""
    import urllib.request
    want = [f for f in catalog() if not f.get("bundled") and (not names or f["ps"] in names or f["name"] in names)]
    got = []
    EXT.mkdir(parents=True, exist_ok=True)
    (EXT / "licenses").mkdir(exist_ok=True)
    for f in want:
        if path_of(f["ps"]):
            continue
        name = f.get("file") or f["ps"]
        tmp = EXT / f"{name}.ttf.part"
        try:
            urllib.request.urlretrieve(f["url"], tmp)
            tmp.replace(EXT / f"{name}.ttf")
            lic = EXT / "licenses" / f"OFL-{name.split('-')[0].lower()}.txt"
            if f.get("license_url") and not lic.exists():
                urllib.request.urlretrieve(f["license_url"], lic)
            got.append(f["ps"])
        except OSError as e:
            tmp.unlink(missing_ok=True)
            print(f"[글꼴] {f['ps']} 받기 실패: {e}")
    return got


def used_by(sb: dict) -> list[str]:
    """콘티가 쓰는 글꼴(목록에 있는 것) — direction 의 글꼴 칸 + 장면 코드 · 재료 안에 적힌 PostScript 이름("$FILE:" 장면 파일 포함)"""
    import json
    try:
        from craft import scenefile
        text = json.dumps(scenefile.inline_safe(sb), ensure_ascii=False)
    except Exception:  # noqa: BLE001
        text = json.dumps(sb, ensure_ascii=False)
    return [f["ps"] for f in catalog() if f["ps"] in text or (f.get("file") and f["file"] in text)]


def ensure(names) -> None:
    """렌더 전에 — 콘티가 고른 글꼴이 없으면 받는다(목록에 있는 것만)"""
    known = {f["ps"] for f in catalog() if not f.get("bundled")}
    need = [n for n in dict.fromkeys(names) if n in known and not path_of(n)]
    if need:
        print(f"[글꼴] 받는 중: {', '.join(need)}")
        fetch(need)


def has_system_font(family: str = NOTO_CJK) -> bool:
    """시스템이 이 글꼴 이름을 아는가(fc-list 가 없으면 Fluma 가 깐 파일로 판단)"""
    if shutil.which("fc-list"):
        r = subprocess.run(["fc-list", family, "family"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return True
    return all((DST / f"NotoSansCJKkr-{w}.otf").exists() for w in NOTO_WEIGHTS)


def fetch_noto_cjk() -> list[Path]:
    """Noto Sans CJK KR 굵기별 OTF 를 tools/fonts 에 받는다(이미 있으면 그대로)"""
    import urllib.request
    EXT.mkdir(parents=True, exist_ok=True)
    (EXT / "licenses").mkdir(exist_ok=True)
    out = []
    for w in NOTO_WEIGHTS:
        f = EXT / f"NotoSansCJKkr-{w}.otf"
        if not f.exists():
            tmp = f.with_suffix(".otf.part")
            try:
                urllib.request.urlretrieve(NOTO_URL.format(w=w), tmp)
                tmp.replace(f)
            except OSError as e:
                tmp.unlink(missing_ok=True)
                print(f"[글꼴] {NOTO_CJK} {w} 받기 실패: {e}")
                continue
        out.append(f)
    lic = EXT / "licenses" / "OFL-notosanscjk.txt"
    if out and not lic.exists():
        try:
            urllib.request.urlretrieve(NOTO_LICENSE, lic)
        except OSError:
            pass
    return out


def _register_windows(path: Path) -> None:
    """Windows 사용자 글꼴 등록(HKCU) — 폴더에 복사만 하면 앱이 못 찾는다"""
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\Fonts", 0, winreg.KEY_SET_VALUE)
    with key:
        winreg.SetValueEx(key, f"{path.stem} (OpenType)", 0, winreg.REG_SZ, str(path))


def install(dst: Path = DST) -> int:
    """디자인 글꼴 + (시스템에 없으면) Noto Sans CJK KR 을 사용자 글꼴 폴더에 설치 → 새로 깐 개수"""
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    files = [SRC / f"{f}.ttf" for f in FILES] + sorted(EXT.glob("*.ttf"))
    if not has_system_font():
        files += fetch_noto_cjk()
    for s_ in files:
        d = dst / s_.name
        if s_.exists() and (not d.exists() or d.stat().st_size != s_.stat().st_size):
            shutil.copyfile(s_, d)
            if _OS == "windows":
                try:
                    _register_windows(d)
                except OSError as e:
                    print(f"[글꼴] {d.name} 등록 실패: {e}")
            n += 1
    if n and shutil.which("fc-cache"):
        subprocess.run(["fc-cache", "-f", str(dst)], capture_output=True)
    return n


def main() -> int:
    import sys
    a = sys.argv[1:]
    if a[:1] == ["list"]:
        use = a[a.index("--use") + 1] if "--use" in a else None
        for f in catalog():
            if use and use not in f.get("use", []):
                continue
            mark = "✓" if path_of(f["ps"]) else "·"
            print(f"{mark} {f['ps']:32} {f['name']:14} {'/'.join(f.get('use', [])):18} {f['mood']}")
        print("✓ 있음 · 받지 않음(렌더 때 자동으로 받는다). 콘티: direction.font_title · font_subs · font_body 또는 K.text(…, {font: '<PS 이름>'})")
        return 0
    if a[:1] == ["fetch"]:
        got = fetch(a[1:] or None)
        print(f"글꼴 {len(got)}개 받음 · {EXT}")
        return 0
    print(f"글꼴 {install()}개 설치 · {DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
