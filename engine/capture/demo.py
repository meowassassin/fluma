#!/usr/bin/env python3
"""실제 화면 자동화 — 예제를 실제로 돌려 터미널 녹화 · 코드 화면 · 공식 문서 녹화를 한 번에 만든다(개발 · IT 설명 영상).
꾸민 로그 · 그림 대신 '진짜로 실행한 화면' 이 기본이 되게(2026-11-05 경쟁력 정리: 실제 화면을 주제마다 자동으로).

  python3 engine/capture/demo.py run <영상 id>            # data/compositions/<id>/demo/demo.json 대로 전부
  python3 engine/capture/demo.py run <영상 id> --only run-n1,code-service
  python3 engine/capture/demo.py toolchain java           # JDK 21 · Maven 을 tools/toolchains/ 에(공식 배포판 · 확인값 검사)

demo.json (예제 소스는 data/compositions/<id>/demo/ 아래 — 에이전트가 쓴다)
{
  "project": "shop",                                  # data/compositions/<id>/demo/shop/
  "build": "maven",                                   # maven · gradle · npm · pip · 또는 ["명령", "인자"] · 없으면 빌드 안 함
  "variants": {"eager": {"file": "src/main/java/com/example/shop/Order.java", "replace": ["FetchType.LAZY", "FetchType.EAGER"]}},
  "runs": [                                           # 실제 실행 → 터미널 녹화(engine/capture/termrec.py)
    {"name": "run-n1", "cmd": ["java", "-jar", "target/shop-0.0.1.jar", "n-plus-1"], "prompt": "$ java -jar shop.jar",
     "title": "Run: shop — LAZY", "mark": ["실행된 쿼리"], "drop": ["^Hibernate: (drop|create|alter) table"], "line_ms": 17, "hold": 1.8},
    {"name": "run-eager", "variant": "eager", "cmd": [...], ...}
  ],
  "code": [                                           # 실제 파일의 일부 → 코드 화면(줄 번호 · 강조 줄)
    {"name": "code-service", "file": "src/main/java/com/example/shop/OrderService.java", "lines": "16-21", "mark": [18]}
  ],
  "docs": [                                           # 공식 문서의 그 절 → 웹 녹화(쿠키 창은 누르지 않고 숨김)
    {"name": "docs-graph", "url": "https://docs.spring.io/…", "find": "It is also possible to define ad hoc entity graphs"}
  ]
}
결과: data/public/elements/<id>/<name>/ 요소 폴더들 · 콘티에 붙일 재료 줄(FLUMA_RESULT 의 material=)
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
from result import fail, ok  # noqa: E402

TC = ROOT / "tools" / "toolchains"
PY = sys.executable
UA = {"User-Agent": "Fluma/1.0 (+https://github.com/meowassassin/fluma)"}
MAVEN = "3.9.11"


# ---------------------------------------------------------------- 도구(공식 배포판 · 확인값)
def _open(url: str, timeout: int = 120):
    """네트워크가 잠깐 끊겨도(SSL 시간 초과 등) 세 번까지 다시"""
    import time
    for k in range(3):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout)
        except OSError:
            if k == 2:
                raise
            time.sleep(3 * (k + 1))


def _download(url: str, dst: Path, sha: str, algo: str) -> None:
    h = hashlib.new(algo)
    with _open(url, 600) as r, open(dst, "wb") as o:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            h.update(b); o.write(b)
    if h.hexdigest().lower() != sha.lower():
        dst.unlink(missing_ok=True)
        raise RuntimeError(f"확인값이 맞지 않습니다: {url}")


def _unpack(arc: Path, dst: Path) -> Path:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    if arc.suffix == ".zip":
        with zipfile.ZipFile(arc) as z:
            for m in z.namelist():
                if m.startswith("/") or ".." in Path(m).parts:
                    raise RuntimeError(f"압축 안의 경로가 이상합니다: {m}")
            z.extractall(dst)
    else:
        with tarfile.open(arc) as t:
            t.extractall(dst, filter="data")
    kids = [p for p in dst.iterdir() if p.is_dir()]
    return kids[0] if len(kids) == 1 else dst


def java_home() -> Path:
    """JDK 21(Eclipse Temurin, Adoptium API 의 SHA-256 확인) — 시스템 JDK 가 21 이상이면 그것을 쓴다"""
    sys_java = shutil.which("java")
    if sys_java:
        v = subprocess.run([sys_java, "-version"], capture_output=True, text=True).stderr
        m = re.search(r'version "(\d+)', v)
        if m and int(m.group(1)) >= 21:
            return Path(sys_java).resolve().parent.parent
    d = TC / "jdk21"
    if (d / "home.txt").exists():
        return Path((d / "home.txt").read_text().strip())
    osn = {"Linux": "linux", "Darwin": "mac", "Windows": "windows"}[platform.system()]
    arch = {"x86_64": "x64", "AMD64": "x64", "arm64": "aarch64", "aarch64": "aarch64"}[platform.machine()]
    info = json.loads(_open(f"https://api.adoptium.net/v3/assets/latest/21/hotspot?os={osn}&architecture={arch}&image_type=jdk", 60).read())
    pkg = info[0]["binary"]["package"]
    TC.mkdir(parents=True, exist_ok=True)
    arc = TC / pkg["name"]
    print(f"[demo] JDK 21 받기 — {pkg['name']} ({pkg['size'] // 1_000_000}MB, Adoptium · SHA-256 확인)", flush=True)
    _download(pkg["link"], arc, pkg["checksum"], "sha256")
    home = _unpack(arc, d)
    if (home / "Contents" / "Home").exists():          # macOS
        home = home / "Contents" / "Home"
    arc.unlink(missing_ok=True)
    (d / "home.txt").write_text(str(home))
    return home


def maven_bin() -> Path:
    if shutil.which("mvn"):
        return Path(shutil.which("mvn"))
    d = TC / f"maven-{MAVEN}"
    exe = "mvn.cmd" if platform.system() == "Windows" else "mvn"
    found = list(d.glob(f"*/bin/{exe}")) if d.exists() else []
    if found:
        return found[0]
    base = f"https://archive.apache.org/dist/maven/maven-3/{MAVEN}/binaries/apache-maven-{MAVEN}-bin.tar.gz"
    sha = _open(base + ".sha512", 60).read().decode().split()[0]
    TC.mkdir(parents=True, exist_ok=True)
    arc = TC / f"apache-maven-{MAVEN}-bin.tar.gz"
    print(f"[demo] Maven {MAVEN} 받기 — Apache 공식 · SHA-512 확인", flush=True)
    _download(base, arc, sha, "sha512")
    home = _unpack(arc, d)
    arc.unlink(missing_ok=True)
    return home / "bin" / exe


def tool_env(need_java: bool) -> dict:
    env = dict(os.environ)
    if need_java:
        jh = java_home()
        env["JAVA_HOME"] = str(jh)
        env["PATH"] = str(jh / "bin") + os.pathsep + env.get("PATH", "")
    return env


# ---------------------------------------------------------------- 빌드 · 실행
def build(proj: Path, spec, env: dict) -> None:
    if not spec:
        return
    if spec == "maven":
        cmd = [str(maven_bin()), "-q", f"-Dmaven.repo.local={TC / 'm2'}", "-DskipTests", "package"]
    elif spec == "gradle":
        cmd = ["./gradlew" if (proj / "gradlew").exists() else "gradle", "-q", "build", "-x", "test"]
    elif spec == "npm":
        cmd = ["npm", "install", "--no-audit", "--no-fund"]
    elif spec == "pip":
        cmd = [PY, "-m", "pip", "install", "-q", "-r", "requirements.txt", "--target", str(proj / ".deps")]
    else:
        cmd = list(spec)
    print(f"[demo] 빌드 {proj.name}: {' '.join(cmd[:3])} …", flush=True)
    r = subprocess.run(cmd, cwd=proj, env=env, capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(f"빌드 실패: {(r.stderr or r.stdout).strip()[-400:]}")


def variant_dir(proj: Path, name: str, v: dict, spec, env: dict) -> Path:
    """바꾼 버전(예: LAZY → EAGER): 사본을 만들어 글자만 바꾸고 다시 빌드. 바꾼 글자가 실제로 있어야 한다"""
    d = proj.parent / f".variant-{name}"
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(proj, d, ignore=shutil.ignore_patterns("target", "build", "node_modules", ".deps"))
    f = d / v["file"]
    a, b = v["replace"]
    s = f.read_text("utf-8")
    if a not in s:
        raise RuntimeError(f"버전 '{name}': {v['file']} 에 '{a}' 가 없습니다")
    f.write_text(s.replace(a, b), "utf-8")
    build(d, spec, env)
    return d


def run_one(sid: str, r: dict, cwd: Path, env: dict) -> str:
    cap = [PY, str(ROOT / "engine" / "capture" / "termrec.py"), "capture", sid, r["name"], "--cwd", str(cwd), "--prompt", r.get("prompt") or "$ " + " ".join(r["cmd"])]
    for d in r.get("drop") or []:
        cap += ["--drop", d]
    p = subprocess.run(cap + ["--", *r["cmd"]], env=env, capture_output=True, text=True, timeout=600)
    if p.returncode not in (0,):
        raise RuntimeError(f"{r['name']} 실행 실패: {(p.stdout + p.stderr).strip()[-300:]}")
    rnd = [PY, str(ROOT / "engine" / "capture" / "termrec.py"), "render", sid, r["name"], "--font", str(r.get("font", 13)),
           "--line-ms", str(r.get("line_ms", 20)), "--hold", str(r.get("hold", 1.8)), "--title", r.get("title") or r["name"]]
    for m in r.get("mark") or []:
        rnd += ["--mark", m]
    p = subprocess.run(rnd, capture_output=True, text=True, timeout=900)
    if p.returncode != 0:
        raise RuntimeError(f"{r['name']} 녹화 실패: {(p.stdout + p.stderr).strip()[-300:]}")
    return f"data/public/elements/{sid}/{r['name']}"


# ---------------------------------------------------------------- 코드 화면
KW = {"java": r"\b(public|private|protected|class|interface|void|return|for|if|else|new|static|final|import|package|extends|implements)\b",
      "py": r"\b(def|class|return|for|in|if|else|elif|import|from|with|as|async|await|None|True|False)\b",
      "js": r"\b(function|const|let|var|return|for|if|else|import|from|export|async|await|new|class)\b"}
CODE_PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
html,body{{margin:0;height:100%;background:#1e1f22}} body{{display:flex;flex-direction:column}}
.wrap{{flex:1;display:flex;align-items:center}} .wrap pre{{width:100%}}
.bar{{display:flex;justify-content:space-between;padding:11px 14px;background:#2b2d30;border-bottom:1px solid #393b40;font:600 12.5px "Pretendard","Noto Sans CJK KR",sans-serif;color:#b9bcc2}}
pre{{margin:0;padding:10px 0;font:{fs}px/1.6 "DejaVu Sans Mono","Noto Sans Mono CJK KR",monospace;color:#d4d4d4;white-space:pre-wrap;overflow-wrap:anywhere}}
pre{{white-space:pre}} .ln{{display:flex}} .ln > span{{white-space:pre-wrap;overflow-wrap:anywhere}} .ln > i{{flex:none;width:2.6em;padding-right:.8em;text-align:right;color:#6f737a;font-style:normal}} .ln > span{{flex:1;padding-right:12px}}
.ln.m{{background:rgba(255,214,10,.16)}} .ln.m i{{color:#ffd60a}}
.k{{color:#cc7832}} .s{{color:#6a8759}} .c{{color:#808080}} .a{{color:#bbb529}}
</style><div class="bar"><span>{title}</span><span>{where}</span></div><div class="wrap"><pre>{body}</pre></div>"""


def code_html(text: str, lang: str) -> str:
    out = []
    for line in text.split("\n"):
        t = html.escape(line, quote=False)           # 따옴표는 그대로 — &#x27; 의 # 을 주석으로 보지 않게
        # 키워드를 먼저(나중에 넣는 class="…" 속성의 'class' 를 키워드로 다시 칠하지 않게) → 문자열 → 주석 → 애노테이션
        t = re.sub(KW.get(lang, KW["java"]), r'<span class="k">\1</span>', t)
        t = re.sub(r'("[^"]*"(?![^<]*>))', r'<span class="s">\1</span>', t)
        t = re.sub(r"(#.*)$" if lang == "py" else r"(//.*)$", r'<span class="c">\1</span>', t)
        t = re.sub(r"(@\w+)", r'<span class="a">\1</span>', t)
        out.append(t)
    return out


def code_one(sid: str, c: dict, proj: Path) -> str:
    from playwright.sync_api import sync_playwright
    f = proj / c["file"]
    lines = f.read_text("utf-8").split("\n")
    a, b = (int(x) for x in str(c.get("lines") or f"1-{len(lines)}").split("-"))
    chunk = lines[a - 1:b]
    ind = min((len(l) - len(l.lstrip()) for l in chunk if l.strip()), default=0)       # 발췌는 공통 들여쓰기만 덜어 낸다(글자는 그대로)
    chunk = [l[ind:] for l in chunk]
    lang = {".py": "py", ".js": "js", ".ts": "js", ".tsx": "js"}.get(f.suffix, "java")
    marks = set(int(x) for x in c.get("mark") or [])
    rows = code_html("\n".join(chunk), lang)
    body = "".join(f'<div class="ln{" m" if a + i in marks else ""}"><i>{a + i}</i><span>{r or " "}</span></div>' for i, r in enumerate(rows))
    # 가장 긴 줄이 한 줄에 들어가는 글자 크기(고정폭 글자 폭 ≈ 0.6em, 줄 번호 칸 빼고 약 330px) — 11~14px, 그래도 길면 줄을 넘긴다
    longest = max((len(x) for x in chunk), default=20)
    fs = c.get("font") or max(11.0, min(14.0, round(330 / (max(longest, 1) * 0.6), 1)))
    page = CODE_PAGE.format(fs=fs, title=html.escape(c.get("title") or f.name), where=html.escape(f"{f.name}:{a}-{b}"), body=body)
    dst = ROOT / "data" / "public" / "elements" / sid / c["name"]
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    vw, vh = 390, 620
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page(viewport={"width": vw, "height": vh}, device_scale_factor=3, is_mobile=True)
        pg.set_content(page, wait_until="load")
        pg.screenshot(path=str(dst / "s000.png"))
        br.close()
    meta = {"kind": "web", "viewport": [vw, vh], "scale": 3, "mobile": True, "states": ["s000.png"], "actions": [], "masked": 0, "sources": [],
            "license": "예제 프로젝트의 실제 파일", "code": {"file": c["file"], "lines": [a, b], "mark": sorted(marks)}}
    (dst / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")
    return f"data/public/elements/{sid}/{c['name']}"


# ---------------------------------------------------------------- 문서
def docs_one(sid: str, d: dict) -> str:
    plan = {"name": d["name"], "start": d["url"], "mobile": True, "viewport": [390, 620], "scale": 3,
            "steps": [{"do": "wait", "ms": 1200}] + ([{"do": "scroll", "target": f"text={d['find']}"}] if d.get("find") else []) + [{"do": "scroll", "by": int(d.get("then", 0))}] * (1 if d.get("then") else 0)}
    pd = ROOT / "data" / "compositions" / sid / "demo" / f"{d['name']}.rec.json"
    pd.write_text(json.dumps(plan, ensure_ascii=False), "utf-8")
    p = subprocess.run([PY, str(ROOT / "engine" / "capture" / "webrec.py"), "run", sid, str(pd.relative_to(ROOT))], capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        raise RuntimeError(f"{d['name']} 문서 녹화 실패: {(p.stdout + p.stderr).strip()[-300:]}")
    return f"data/public/elements/{sid}/{d['name']}"


# ---------------------------------------------------------------- 실행
def cmd_run(a) -> None:
    sid = a.id
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,80}", sid):
        fail("demo", stage="id", error="영상 id 가 올바르지 않음")
    base = ROOT / "data" / "compositions" / sid / "demo"
    spec_p = base / "demo.json"
    if not spec_p.exists():
        fail("demo", stage="plan", error=f"{spec_p.relative_to(ROOT)} 가 없습니다 — 예제 소스와 실행 계획을 먼저 쓰세요(engine/capture/demo.py 맨 위 설명)")
    spec = json.loads(spec_p.read_text("utf-8"))
    only = set(a.only.split(",")) if a.only else None
    proj = base / spec.get("project", "")
    runs = [r for r in spec.get("runs") or [] if not only or r["name"] in only]
    codes = [c for c in spec.get("code") or [] if not only or c["name"] in only]
    docs = [d for d in spec.get("docs") or [] if not only or d["name"] in only]
    need_java = spec.get("build") == "maven" or any((r.get("cmd") or [""])[0] in ("java", "mvn") for r in runs)
    made, errors = [], []
    try:
        env = tool_env(need_java)
        if runs:
            build(proj, spec.get("build"), env)
    except Exception as e:  # noqa: BLE001
        fail("demo", stage="build", error=str(e))
    vdirs: dict[str, Path] = {}
    for r in runs:
        try:
            cwd = proj
            if r.get("variant"):
                if r["variant"] not in vdirs:
                    vdirs[r["variant"]] = variant_dir(proj, r["variant"], spec["variants"][r["variant"]], spec.get("build"), env)
                cwd = vdirs[r["variant"]]
            made.append((r["name"], run_one(sid, r, cwd, env), "실제 실행 터미널"))
            print(f"[demo] {r['name']} 녹화", flush=True)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{r['name']}: {e}")
    for c in codes:
        try:
            made.append((c["name"], code_one(sid, c, proj), f"코드 {c['file']}:{c.get('lines', '')}"))
            print(f"[demo] {c['name']} 코드 화면", flush=True)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{c['name']}: {e}")
    for d in docs:
        try:
            made.append((d["name"], docs_one(sid, d), f"문서 {d['url']}"))
            print(f"[demo] {d['name']} 문서", flush=True)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{d['name']}: {e}")
    for vd in vdirs.values():
        shutil.rmtree(vd, ignore_errors=True)
    if errors and not made:
        fail("demo", stage="run", error=" / ".join(errors)[:400])
    media = []
    for name, src, what in made:
        el = ROOT / src
        pic = el / "s001.png" if (el / "s001.png").exists() else el / "s000.png"
        if pic.exists():
            media.append(f"{pic.relative_to(ROOT)} | {name} — {what}")
    ok("demo", material=[json.dumps({"id": n, "type": "web", "src": s, "place": "full", "what": w}, ensure_ascii=False) for n, s, w in made],
       media=media, error=errors or None, next="material= 줄을 콘티 장면 materials 에 넣고(나레이션이 없으면 start · holds), python3 engine/produce.py")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("id"); r.add_argument("--only", help="이 이름만(쉼표)")
    t = sub.add_parser("toolchain"); t.add_argument("lang", choices=["java"])
    a = ap.parse_args()
    if a.cmd == "toolchain":
        jh = java_home(); mv = maven_bin()
        ok("demo", java_home=str(jh), maven=str(mv))
    cmd_run(a)
    return 0


if __name__ == "__main__":
    from result import run_main
    run_main("demo", main)
