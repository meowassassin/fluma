#!/usr/bin/env python3
"""Craft 앱(ArtCraft 의 오픈소스 Photoshop · Illustrator · After Effects 류 등) 붙이기.

crafts/<이름>/craft.json 하나가 앱 하나다. 이 스크립트는 GitHub 최신 릴리스에서
  - 이 컴퓨터용 데스크톱 앱 + <이름>-cli (헤드리스 · MCP 서버)
  - 브라우저 빌드(web zip)
를 받아 SHA256SUMS.txt 로 확인한 뒤 tools/crafts/<이름>/ 에 푼다.

  python3 scripts/crafts.py list [--json]          # 등록된 앱과 설치 상태
  python3 scripts/crafts.py plan [이름|all]        # 받을 파일 · 크기만 보여 줌(받지 않음)
  python3 scripts/crafts.py install 이름|all [--no-web] [--no-app]
  python3 scripts/crafts.py remove 이름

설치된 앱은 에이전트 실행 때 MCP 서버로 붙는다(web/mcp.mjs) — 읽기는 저장소, 쓰기는 compositions/ 만.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "crafts"
DEST = ROOT / "tools" / "crafts"
UA = {"User-Agent": "fluma-crafts", "Accept": "application/vnd.github+json"}


def apps() -> list[dict]:
    out = []
    for f in sorted(REG.glob("*/craft.json")):
        try:
            out.append(json.loads(f.read_text("utf-8")))
        except (OSError, json.JSONDecodeError) as e:
            print(f"[crafts] {f} 읽기 실패: {e}", file=sys.stderr)
    return sorted(out, key=lambda a: a.get("order", 99))


def installed(name: str) -> dict | None:
    f = DEST / name / "installed.json"
    try:
        return json.loads(f.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def target() -> tuple[str, str]:
    """릴리스 파일 이름의 플랫폼 부분과 묶음 종류"""
    sysname, arch = platform.system(), platform.machine().lower()
    arch = {"amd64": "x86_64", "arm64": "aarch64"}.get(arch, arch)
    if sysname == "Linux":
        return f"linux-{arch}", "tar"
    if sysname == "Darwin":
        return "macos-universal", "cli-zip"   # 맥은 데스크톱 .app 이 dmg 라 CLI zip 만 받는다
    if sysname == "Windows":
        return f"windows-{'x64' if arch == 'x86_64' else arch}-portable", "zip"
    raise SystemExit(f"지원하지 않는 운영체제입니다: {sysname}")


def get_json(url: str):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.load(r)


def release(app: dict) -> dict:
    return get_json(f"https://api.github.com/repos/{app['repo']}/releases/latest")


def pick(app: dict, rel: dict, web: bool, desk: bool) -> list[dict]:
    plat, kind = target()
    name = app["name"]
    assets = {a["name"]: a for a in rel.get("assets", [])}
    want = []
    if desk:
        if kind == "cli-zip":
            want += [n for n in assets if n.startswith(f"{name}-cli-") and n.endswith(f"-{plat}.zip")]
        else:
            ext = ".tar.gz" if kind == "tar" else ".zip"
            want += [n for n in assets if n.startswith(f"{name}-") and not n.startswith(f"{name}-cli-") and "-server-" not in n and n.endswith(f"-{plat}{ext}")]
    if web:
        want += [n for n in assets if n.startswith(f"{name}-web-") and n.endswith(".zip")]
    return [assets[n] for n in want]


def sums(rel: dict) -> dict[str, str]:
    a = next((x for x in rel.get("assets", []) if x["name"] == "SHA256SUMS.txt"), None)
    if not a:
        return {}
    with urllib.request.urlopen(urllib.request.Request(a["browser_download_url"], headers={"User-Agent": UA["User-Agent"]}), timeout=30) as r:
        txt = r.read().decode("utf-8", "replace")
    out = {}
    for line in txt.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            out[parts[-1].lstrip("*")] = parts[0].lower()
    return out


def download(asset: dict, to: Path) -> str:
    h = hashlib.sha256()
    req = urllib.request.Request(asset["browser_download_url"], headers={"User-Agent": UA["User-Agent"]})
    size, done, last = asset.get("size", 0), 0, -1
    with urllib.request.urlopen(req, timeout=60) as r, open(to, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk); h.update(chunk); done += len(chunk)
            pct = int(done * 100 / size) if size else 0
            if pct // 5 != last:
                last = pct // 5
                print(f"@progress {pct / 100:.2f} {asset['name']} 받는 중", flush=True)
    return h.hexdigest()


def safe_extract(archive: Path, out: Path) -> None:
    """경로 밖으로 나가는 항목(../ · 절대 경로 · 링크)은 풀지 않는다"""
    out = out.resolve()
    def ok(p: str) -> bool:
        dest = (out / p).resolve()
        return dest == out or out in dest.parents
    if archive.name.endswith(".tar.gz"):
        with tarfile.open(archive) as t:
            members = [m for m in t.getmembers() if ok(m.name) and not m.issym() and not m.islnk() and not m.isdev()]
            t.extractall(out, members=members, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
    else:
        with zipfile.ZipFile(archive) as z:
            for m in z.infolist():
                if ok(m.filename):
                    z.extract(m, out)
                    mode = (m.external_attr >> 16) & 0o777
                    if mode:
                        os.chmod(out / m.filename, mode)


def find(base: Path, exe: str) -> str | None:
    names = [exe, f"{exe}.exe"]
    for p in sorted(base.rglob("*")):
        if p.name in names and p.is_file():
            return str(p.relative_to(ROOT))
    return None


def find_web(base: Path) -> str | None:
    """브라우저 빌드의 index.html 이 있는 폴더"""
    idx = sorted(base.rglob("index.html"), key=lambda p: len(p.parts))
    return str(idx[0].parent.relative_to(ROOT)) if idx else None


def install(app: dict, web: bool, desk: bool) -> bool:
    name = app["name"]
    rel = release(app)
    files = pick(app, rel, web, desk)
    if not files:
        print(f"[{name}] 이 컴퓨터용 릴리스 파일이 없습니다 ({target()[0]})"); return False
    sha = sums(rel)
    d = DEST / name
    dl = d / ".dl"; dl.mkdir(parents=True, exist_ok=True)
    info = {"name": name, "version": rel.get("tag_name"), "files": [], "bin": None, "cli": None, "web": None}
    for a in files:
        p = dl / a["name"]
        got = download(a, p)
        want = sha.get(a["name"])
        if want and got != want:
            p.unlink(missing_ok=True)
            print(f"[{name}] {a['name']} 확인값이 맞지 않아 버렸습니다"); return False
        part = d / ("web" if "-web-" in a["name"] else "app")
        if part.exists():
            shutil.rmtree(part)
        part.mkdir(parents=True)
        safe_extract(p, part)
        p.unlink(missing_ok=True)
        info["files"].append({"name": a["name"], "size": a.get("size"), "sha256": got, "verified": bool(want)})
    shutil.rmtree(dl, ignore_errors=True)
    app_dir = d / "app"
    if app_dir.exists():
        info["bin"] = find(app_dir, app.get("bin", name))
        info["cli"] = find(app_dir, app.get("cli", f"{name}-cli"))
    if (d / "web").exists():
        info["web"] = find_web(d / "web")
    (d / "installed.json").write_text(json.dumps(info, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"[{name}] 설치됨 {info['version']} · cli={'있음' if info['cli'] else '없음'} · web={'있음' if info['web'] else '없음'}")
    return True


def rows() -> list[dict]:
    out = []
    for a in apps():
        i = installed(a["name"])
        out.append({**a, "installed": i})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("list"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("plan"); s.add_argument("name", nargs="?", default="all"); s.add_argument("--no-web", action="store_true"); s.add_argument("--no-app", action="store_true")
    s = sub.add_parser("install"); s.add_argument("name"); s.add_argument("--no-web", action="store_true"); s.add_argument("--no-app", action="store_true")
    s = sub.add_parser("remove"); s.add_argument("name")
    a = ap.parse_args()

    if a.cmd == "list":
        r = rows()
        if a.json:
            print(json.dumps(r, ensure_ascii=False)); return
        for x in r:
            i = x["installed"]
            print(f"{x['name']:15} {'설치됨 ' + str(i.get('version')) if i else '-':18} {'에이전트' if x.get('agent') else '':6} {x['kind']}")
        return

    pick_apps = lambda n: apps() if n == "all" else [x for x in apps() if x["name"] == n]
    chosen = pick_apps(a.name)
    if not chosen:
        raise SystemExit(f"없는 앱입니다: {a.name} (crafts/ 아래 이름)")

    if a.cmd == "plan":
        total = 0
        for x in chosen:
            rel = release(x)
            for f in pick(x, rel, not a.no_web, not a.no_app):
                total += f.get("size", 0)
                print(f"{x['name']:15} {f['name']:52} {f.get('size', 0) / 1048576:7.0f}MB  {f['browser_download_url']}")
        print(f"합계 {total / 1048576:.0f}MB")
        return

    if a.cmd == "install":
        bad = [x["name"] for x in chosen if not install(x, not a.no_web, not a.no_app)]
        if bad:
            raise SystemExit(f"설치 실패: {', '.join(bad)}")
        return

    if a.cmd == "remove":
        shutil.rmtree(DEST / a.name, ignore_errors=True)
        print(f"[{a.name}] 지웠습니다")


if __name__ == "__main__":
    main()
