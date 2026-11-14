#!/usr/bin/env python3
"""Craft 앱(ArtCraft 의 오픈소스 Photoshop · Illustrator · After Effects 류 등) 붙이기.

engine/craft/apps/<이름>/craft.json 하나가 앱 하나다. 이 스크립트는 GitHub 최신 릴리스에서
  - 이 컴퓨터용 데스크톱 앱 + <이름>-cli (헤드리스 · MCP 서버)
  - 브라우저 빌드(web zip)
를 받아 SHA256SUMS.txt 로 확인한 뒤 tools/crafts/<이름>/ 에 푼다.

  python3 engine/craft/crafts.py list [--json]          # 등록된 앱과 설치 상태
  python3 engine/craft/crafts.py plan [이름|all]        # 받을 파일 · 크기만 보여 줌(받지 않음)
  python3 engine/craft/crafts.py install 이름|all [--no-web] [--no-app]
  python3 engine/craft/crafts.py remove 이름

설치된 앱은 에이전트 실행 때 MCP 서버로 붙는다(studio/mcp.mjs) — 읽기는 저장소, 쓰기는 data/compositions/ 만.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import urllib.parse
import urllib.error
import zipfile
from pathlib import Path

# Windows 콘솔 · 파이프의 기본 인코딩(cp1252 등)에서 한글 출력이 깨지지 않게
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
REG = ROOT / "engine" / "craft" / "apps"
DEST = ROOT / "tools" / "crafts"
UA = {"User-Agent": "fluma-crafts", "Accept": "application/vnd.github+json"}
# GitHub API 는 로그인 없이 시간당 60번 — 토큰이 있으면 쓴다(CI · 여러 앱을 한 번에 받을 때). 값은 출력하지 않는다
if os.environ.get("GITHUB_TOKEN"):
    UA["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"


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


def _urlopen(req, timeout: int = 30):
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.URLError as e:
        import ssl
        if isinstance(e.reason, ssl.SSLError):
            try:
                import certifi
                ctx = ssl.create_default_context(cafile=certifi.where())
                return urllib.request.urlopen(req, timeout=timeout, context=ctx)
            except Exception:
                pass
        raise e


def get_json(url: str):
    with _urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.load(r)


def release(app: dict) -> dict:
    try:
        return get_json(f"https://api.github.com/repos/{app['repo']}/releases/latest")
    except urllib.error.HTTPError as e:
        if e.code not in (403, 429):
            raise
        return release_from_web(app["repo"])     # API 한도(로그인 없이 시간당 60번)에 걸려도 설치는 계속된다


def release_from_web(repo: str) -> dict:
    """API 대신 공개 릴리스 페이지에서 최신 태그 · 파일 목록을 읽는다(API 와 같은 모양으로, 크기는 모름)"""
    req = urllib.request.Request(f"https://github.com/{repo}/releases/latest", headers={"User-Agent": UA["User-Agent"]})
    with _urlopen(req, timeout=30) as r:
        tag = urllib.parse.unquote(r.geturl().rstrip("/").rsplit("/", 1)[1])
    req = urllib.request.Request(f"https://github.com/{repo}/releases/expanded_assets/{urllib.parse.quote(tag)}", headers={"User-Agent": UA["User-Agent"]})
    with _urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", "replace")
    pre = f"/{repo}/releases/download/{tag}/"
    names = sorted({urllib.parse.unquote(m) for m in re.findall(r'href="' + re.escape(pre) + r'([^"?#]+)"', html)})
    if not names:
        raise RuntimeError(f"{repo} 릴리스 파일 목록을 읽지 못했습니다(GitHub API 한도 — 잠시 뒤 다시, 또는 GITHUB_TOKEN)")
    return {"tag_name": tag, "assets": [{"name": n, "size": 0, "browser_download_url": f"https://github.com{pre}{urllib.parse.quote(n)}"} for n in names]}


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
    with _urlopen(urllib.request.Request(a["browser_download_url"], headers={"User-Agent": UA["User-Agent"]}), timeout=30) as r:
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
    with _urlopen(req, timeout=60) as r, open(to, "wb") as f:
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
    if archive.name.endswith((".tar.gz", ".tar.xz")):
        def link_ok(m) -> bool:                         # 공유 라이브러리는 링크로 온다(libtbb.so.12 → …) — 폴더 안을 가리키는 것만 둔다
            if m.isdev():
                return False
            if m.issym():
                return ok(str(Path(m.name).parent / m.linkname))
            if m.islnk():
                return ok(m.linkname)
            return True
        with tarfile.open(archive) as t:
            members = [m for m in t.getmembers() if ok(m.name) and link_ok(m)]
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


def _system_app(name: str) -> str | None:
    """이미 설치된 앱(PATH · macOS /Applications · Windows Program Files)"""
    found = shutil.which(name)
    if found:
        return found
    cands = [Path(f"/Applications/{name.title()}.app/Contents/MacOS/{name.title()}")]
    for env in ("ProgramFiles", "ProgramFiles(x86)"):
        if os.environ.get(env):
            cands += sorted(Path(os.environ[env]).glob(f"{name.title()} Foundation/{name.title()}*/{name}.exe"), reverse=True)
    return next((str(c) for c in cands if c.exists()), None)


def _register(name: str, version: str, files: list, binpath: str) -> None:
    try:
        rel = str(Path(binpath).resolve().relative_to(ROOT))
    except ValueError:
        rel = binpath          # 시스템에 깔린 앱 — 절대 경로 그대로
    (DEST / name).mkdir(parents=True, exist_ok=True)
    (DEST / name / "installed.json").write_text(json.dumps({"name": name, "version": version, "files": files,
                                                             "bin": rel, "cli": rel, "web": None}, ensure_ascii=False, indent=1) + "\n", "utf-8")


def direct_build(dx: dict) -> dict | None:
    sysname = platform.system().lower().replace("darwin", "macos")
    arch = {"amd64": "x86_64", "arm64": "aarch64"}.get(platform.machine().lower(), platform.machine().lower())
    return (dx.get("builds") or {}).get(f"{sysname}-{arch}")


def install_direct(app: dict) -> bool:
    """GitHub 릴리스가 아닌 앱: craft.json 의 direct 칸 — 이 운영체제 · CPU 용 공식 빌드를 받아 공식 sha256 과 대조한 뒤 푼다.
    공식 빌드가 없는 곳(Linux ARM · macOS)은 이미 설치된 앱을 찾아 쓰고, 그것도 없으면 건너뛴다(그 앱이 필요한 장면만 못 만든다)"""
    name, dx = app["name"], app["direct"]
    build = direct_build(dx)
    if not build:
        have = _system_app(name)
        if have:
            r = subprocess.run([have, "--version"], capture_output=True, text=True, timeout=60)
            ver = (r.stdout.split("\n")[0].split()[-1] if r.returncode == 0 and r.stdout.split() else "system")
            _register(name, ver, [], have)
            print(f"[{name}] 이 컴퓨터에 설치된 것을 씁니다: {have}")
        else:
            print(f"[{name}] {platform.system()}-{platform.machine()} 용 공식 빌드가 없어 건너뜁니다 — {app.get('homepage', '')} 에서 설치하면 자동으로 찾습니다(이 앱이 필요한 3D 장면만 못 만듦)")
        return True
    d = DEST / name
    dl = d / ".dl"; dl.mkdir(parents=True, exist_ok=True)
    dx = {**dx, **build}
    fname = dx["url"].rsplit("/", 1)[1]
    p = dl / fname
    got = download({"name": fname, "browser_download_url": dx["url"]}, p)
    with _urlopen(urllib.request.Request(dx["sha256_url"], headers={"User-Agent": "fluma-crafts"}), timeout=30) as r:
        sums_txt = r.read().decode()
    want = next((ln.split()[0] for ln in sums_txt.splitlines() if ln.strip().endswith(fname)), None)
    if not want or got != want:
        p.unlink(missing_ok=True)
        print(f"[{name}] {fname} 확인값이 맞지 않아 버렸습니다"); return False
    part = d / "app"
    if part.exists():
        shutil.rmtree(part)
    part.mkdir(parents=True)
    safe_extract(p, part)
    shutil.rmtree(dl, ignore_errors=True)
    rel = (part / dx["bin"]).relative_to(ROOT)
    r = subprocess.run([str(part / dx["bin"]), "--version"], capture_output=True, text=True, timeout=60)     # 풀렸다고 끝이 아니다 — 실제로 뜨는지 본다
    if r.returncode != 0:
        print(f"[{name}] 설치했지만 실행되지 않습니다: {(r.stderr or r.stdout)[-300:]}"); return False
    _register(name, dx["version"], [{"name": fname, "sha256": got, "verified": True}], str(ROOT / rel))
    print(f"[{name}] 설치됨 {dx['version']}")
    return True


def install(app: dict, web: bool = False, desk: bool = True, keep_gui: bool = False) -> bool:
    name = app["name"]
    if app.get("direct"):
        return install_direct(app)
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
        info["cli"] = find(app_dir, app.get("cli", f"{name}-cli"))
        info["bin"] = find(app_dir, app.get("bin", name))
        if not keep_gui and info["cli"] and info["bin"] and info["bin"] != info["cli"]:
            try:
                (ROOT / info["bin"]).unlink(missing_ok=True)
                info["bin"] = None
            except OSError:
                pass
    if (d / "web").exists():
        if web:
            info["web"] = find_web(d / "web")
        else:
            shutil.rmtree(d / "web", ignore_errors=True)
    (d / "installed.json").write_text(json.dumps(info, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"[{name}] 설치됨 {info['version']} · cli={'있음' if info['cli'] else '없음'} · web={'있음' if info['web'] else '없음'}")
    return True


def slim() -> dict:
    """이미 설치된 Craft 폴더에서 에이전트/엔진이 쓰지 않는 중복 데스크톱 GUI 실행 파일 · 웹 번들 · 구형 blender 폴더를 정리해 경량화한다."""
    freed = 0
    cleaned = []
    blender_dir = DEST / "blender"
    if blender_dir.exists():
        sz = sum(f.stat().st_size for f in blender_dir.rglob("*") if f.is_file() and not f.is_symlink())
        shutil.rmtree(blender_dir, ignore_errors=True)
        freed += sz
        cleaned.append("blender")
    for a in apps():
        name = a["name"]
        d = DEST / name
        inst_file = d / "installed.json"
        if not inst_file.exists():
            continue
        info = installed(name) or {}
        changed = False
        app_dir = d / "app"
        cli_rel = info.get("cli") or (find(app_dir, a.get("cli", f"{name}-cli")) if app_dir.exists() else None)
        bin_rel = info.get("bin") or (find(app_dir, a.get("bin", name)) if app_dir.exists() else None)
        if cli_rel and bin_rel and bin_rel != cli_rel:
            bp = ROOT / bin_rel
            if bp.is_file():
                freed += bp.stat().st_size
                bp.unlink(missing_ok=True)
                changed = True
            info["bin"] = None
        web_dir = d / "web"
        if web_dir.exists():
            freed += sum(f.stat().st_size for f in web_dir.rglob("*") if f.is_file() and not f.is_symlink())
            shutil.rmtree(web_dir, ignore_errors=True)
            info["web"] = None
            changed = True
        if changed:
            inst_file.write_text(json.dumps(info, ensure_ascii=False, indent=1) + "\n", "utf-8")
            cleaned.append(name)
    return {"freed_mb": round(freed / 1048576, 1), "cleaned": cleaned}


def ensure(name: str) -> dict | None:
    """필요한 순간 설치(CLI 실행 파일만 · 확인값 검사 그대로) — 엔진이 부른다. 사용자에게 '설치해 주세요' 를 부탁하지 않기 위해.
    이미 있으면 그대로, 이 운영체제용 릴리스가 없거나 받지 못하면 None"""
    have = installed(name)
    if have and have.get("cli"):
        return have
    app = next((x for x in apps() if x["name"] == name), None)
    if not app:
        return None
    print(f"[{name}] 없어서 설치합니다(한 번만 · CLI 경량 모드)", file=sys.stderr, flush=True)
    try:
        ok = install(app, web=False, desk=True, keep_gui=False)
    except Exception as e:          # 네트워크 · 압축 오류 — 호출한 쪽이 대체 경로로
        print(f"[{name}] 설치 실패: {e}", file=sys.stderr, flush=True)
        return None
    return installed(name) if ok else None


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
    s = sub.add_parser("plan"); s.add_argument("name", nargs="?", default="all"); s.add_argument("--no-web", action="store_true"); s.add_argument("--with-web", action="store_true"); s.add_argument("--no-app", action="store_true")
    s = sub.add_parser("install"); s.add_argument("name", nargs="+"); s.add_argument("--no-web", action="store_true"); s.add_argument("--with-web", action="store_true"); s.add_argument("--with-gui", action="store_true"); s.add_argument("--no-app", action="store_true")
    s = sub.add_parser("slim", help="중복 데스크톱 GUI · 웹 번들 · 구형 blender 정리 (CLI/MCP 전용 경량화)")
    s = sub.add_parser("remove"); s.add_argument("name")
    # 에이전트는 python3 engine/… 만 돌릴 수 있다 — Craft 앱 CLI(vectorcraft-cli convert … 등)는 이걸로(없으면 설치부터)
    s = sub.add_parser("run", help="설치된 앱의 CLI 실행: crafts.py run vectorcraft convert a.svg b.png"); s.add_argument("name"); s.add_argument("args", nargs=argparse.REMAINDER)
    a = ap.parse_args()

    if a.cmd == "slim":
        res = slim()
        print(json.dumps(res, ensure_ascii=False))
        return

    if a.cmd == "run":
        rec = ensure(a.name)
        if not rec or not rec.get("cli"):
            sys.exit(f"{a.name}: CLI 를 찾지 못했습니다")
        exe = ROOT / rec["cli"] if not Path(rec["cli"]).is_absolute() else Path(rec["cli"])
        sys.exit(subprocess.run([str(exe), *a.args]).returncode)

    if a.cmd == "list":
        r = rows()
        if a.json:
            print(json.dumps(r, ensure_ascii=False)); return
        for x in r:
            i = x["installed"]
            print(f"{x['name']:15} {'설치됨 ' + str(i.get('version')) if i else '-':18} {'에이전트' if x.get('agent') else '':6} {x['kind']}")
        return

    names = a.name if isinstance(a.name, list) else [a.name]
    chosen = [x for x in apps() if not x.get("optional")] if "all" in names else [x for x in apps() if x["name"] in names]   # 선택 앱(optional)은 이름으로만
    unknown = [n for n in names if n != "all" and n not in {x["name"] for x in apps()}]
    if unknown or not chosen:
        raise SystemExit(f"없는 앱입니다: {', '.join(unknown or names)} (engine/craft/apps/ 아래 이름)")

    if a.cmd == "plan":
        total = 0
        for x in chosen:
            if x.get("direct"):
                dx = x["direct"]; b = direct_build(dx)
                print(f"{x['name']:15} {(b['url'].rsplit('/', 1)[1] if b else '(이 컴퓨터용 공식 빌드 없음 — 설치된 것을 찾음)'):52}  {b['url'] if b else ''}")
                continue
            rel = release(x)
            for f in pick(x, rel, bool(a.with_web and not a.no_web), not a.no_app):
                total += f.get("size", 0)
                print(f"{x['name']:15} {f['name']:52} {f.get('size', 0) / 1048576:7.0f}MB  {f['browser_download_url']}")
        print(f"합계 {total / 1048576:.0f}MB")
        return

    if a.cmd == "install":
        bad = [x["name"] for x in chosen if not install(x, bool(a.with_web and not a.no_web), not a.no_app, keep_gui=bool(a.with_gui))]
        if bad:
            raise SystemExit(f"설치 실패: {', '.join(bad)}")
        return

    if a.cmd == "remove":
        shutil.rmtree(DEST / a.name, ignore_errors=True)
        print(f"[{a.name}] 지웠습니다")


if __name__ == "__main__":
    main()
