#!/usr/bin/env python3
"""앱 전체 기능 시험 — 기능 목록(catalog)의 명령 · 효과를 견본 문서에서 실제로 돌려 '되는 것 · 조건 · 결과 모습'을 기록한다.
에이전트가 앱을 전문가처럼 쓰려면 명령 이름만이 아니라 언제 되는지(조건) · 무엇이 필요한지(인자) · 어떻게 보이는지(견본)를 알아야 한다.

  python3 engine/craft/probe.py <앱> [--part states|commands|effects] [--limit N] [--jobs 4]

결과
  .claude/skills/crafts/probe/<앱>.jsonl   명령 · 효과 한 줄씩: {id, kind, states: {상태: 되나/이유}, run: ok|needs_params|needs_context|error|timeout,
                                          msg(오류 문구 — 필요한 인자 · 조건이 적혀 있다), visible(견본 화면이 바뀌었나), thumb}
  .claude/skills/crafts/probe/<앱>.md      요약(분류별 수 · 조건별로 묶은 명령 · 효과 견본 판 경로)
  data/workspace/probe/<앱>/               견본 그림 · 효과 견본 판(분류마다 한 장 — 에이전트가 Read 로 본다)

앱 설정이 바뀌지 않게 HOME · XDG 설정 폴더를 임시 폴더로 돌린다. 명령은 견본 사본에만 실행한다(원본 · 사용자 파일을 건드리지 않음).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from craft.materials import cli  # noqa: E402

CAT = ROOT / ".claude" / "skills" / "crafts" / "catalog"
OUT = ROOT / ".claude" / "skills" / "crafts" / "probe"
WORK = ROOT / "data" / "workspace" / "probe"
SANDBOX = Path(tempfile.gettempdir()) / "fluma-probe-home"
# 견본 사본에서도 돌리지 않는 것: 창 · 대화상자 · 앱 종료 · 외부 열기(브라우저) · 설정 저장
SKIP = re.compile(r"^(app\.(quit|exit)|help\.|learn\.|window\.|scriptui\.|shortcuts\.|prefs\.(set|reset|import)|file\.(quit|exit|revealIn|openInBrowser))")


def env() -> dict:
    SANDBOX.mkdir(parents=True, exist_ok=True)
    return {**os.environ, "HOME": str(SANDBOX), "XDG_CONFIG_HOME": str(SANDBOX / ".config"), "XDG_DATA_HOME": str(SANDBOX / ".local"),
            "DO_NOT_TRACK": "1", "EFFECTCRAFT_FONT_DIRS": str(ROOT / "engine" / "assets" / "fonts"),
            "SOUNDCRAFT_NO_PREFS": "1", "VECTORCRAFT_NO_PREFS": "1"}


def catalog(app: str) -> list[dict]:
    return [json.loads(ln) for ln in (CAT / f"{app}.jsonl").read_text("utf-8").splitlines() if ln.strip()]


def json_docs(text: str) -> list:
    """앞뒤로 이어진 JSON 문서들(단계마다 결과)"""
    dec, i, out = json.JSONDecoder(), 0, []
    while i < len(text):
        j = min([k for k in (text.find("{", i), text.find("[", i)) if k >= 0], default=-1)
        if j < 0:
            break
        try:
            o, i = dec.raw_decode(text, j)
            out.append(o)
        except ValueError:
            i = j + 1
    return out


def classify(rc: int, text: str) -> str:
    if rc == 0:
        return "ok"
    t = text.lower()
    if "not available right now" in t or "select" in t and "first" in t or "no active" in t or "needs a" in t or "need a" in t:
        return "needs_context"
    if any(k in t for k in ("invalid parameters", "bad parameters", "bad `", "missing", "required", "expected", "unknown", "must be", "invalid value", "out of range")):
        return "needs_params"
    if any(k in t for k in ("no character", "nothing to", "nothing is", "no selection", "is empty", "no document", "not found in the",
                            "not available", "no matches", "no active", "there is no", "has no ")):
        return "needs_context"
    return "error"


def diff(a: Path, b: Path) -> float:
    from PIL import Image, ImageChops, ImageStat
    x, y = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    if x.size != y.size:
        y = y.resize(x.size)
    return round(sum(ImageStat.Stat(ImageChops.difference(x, y)).mean) / 3, 2)


def sheet(items: list[tuple[str, Path]], out: Path, cols: int = 6, w: int = 200) -> None:
    """견본 판: 썸네일 + 이름"""
    from PIL import Image, ImageDraw, ImageFont
    if not items:
        return
    ims = [(n, Image.open(p).convert("RGB")) for n, p in items]
    h = int(ims[0][1].height * w / ims[0][1].width)
    rows = (len(ims) + cols - 1) // cols
    board = Image.new("RGB", (cols * (w + 8) + 8, rows * (h + 34) + 8), (245, 245, 245))
    d = ImageDraw.Draw(board)
    try:
        font = ImageFont.truetype(str(next((ROOT / "engine" / "assets" / "fonts").glob("Pretendard-Medium*"))), 15)
    except (StopIteration, OSError):
        font = ImageFont.load_default()
    for k, (n, im) in enumerate(ims):
        x, y = 8 + (k % cols) * (w + 8), 8 + (k // cols) * (h + 34)
        board.paste(im.resize((w, h)), (x, y))
        d.text((x, y + h + 4), n[:26], fill=(20, 20, 20), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    board.save(out)


# ---------------------------------------------------------------- EffectCraft
class EffectCraft:
    app = "effectcraft"
    STATES = {"none": [], "image": ["Image"], "text": ["Title"], "shape": ["Shape"], "solid": ["BG"]}

    def __init__(self, work: Path):
        self.cli = str(cli(self.app))
        self.work = work
        self.proj = work / "sample.ecproj"

    def setup(self) -> None:
        from PIL import Image, ImageDraw
        card = self.work / "card.png"
        im = Image.new("RGB", (900, 1200), (236, 230, 220))
        d = ImageDraw.Draw(im)
        for k, c in enumerate([(220, 60, 60), (60, 140, 220), (250, 200, 40), (40, 170, 110)]):
            d.rectangle([80 + k * 190, 120, 230 + k * 190, 520], fill=c)
        d.ellipse([200, 620, 700, 1120], fill=(30, 40, 60))
        d.rectangle([380, 780, 520, 960], fill=(255, 255, 255))
        im.save(card)
        js = f"""
var c = app.project.items.addComp('Probe', 1080, 1920, 1, 4, 30);
var bg = c.layers.addSolid([0.12, 0.14, 0.2], 'BG', 1080, 1920, 1);
var f = app.project.importFile(new ImportOptions(new File({json.dumps(str(card))}))); var im = c.layers.add(f); im.name = 'Image';
im.property('Transform').property('Position').setValue([540, 900]);
var sh = c.layers.addShape(); sh.name = 'Shape'; var g = sh.property('Contents').addProperty('ADBE Vector Group');
g.property('Contents').addProperty('ADBE Vector Shape - Ellipse').property('Size').setValue([260, 260]);
g.property('Contents').addProperty('ADBE Vector Graphic - Fill').property('Color').setValue([1, 0.84, 0.04]);
sh.property('Transform').property('Position').setValue([820, 1600]);
var t = c.layers.addText('견본 제목 Probe'); t.name = 'Title'; t.property('Transform').property('Position').setValue([540, 300]);
app.project.save(new File({json.dumps(str(self.proj))}));
"""
        sp = self.work / "sample.jsx"
        sp.write_text(js, "utf-8")
        r = subprocess.run([self.cli, "script", str(sp)], capture_output=True, text=True, env=env(), timeout=120)
        if r.returncode != 0 or not self.proj.exists():
            raise SystemExit(f"견본 프로젝트를 못 만들었습니다: {(r.stderr or r.stdout)[-400:]}")
        self.base = self.render(self.proj, self.work / "base.png")

    def render(self, proj: Path, out: Path, t: float = 1.0) -> Path:
        subprocess.run([self.cli, "render-frame", "--project", str(proj), "--comp", "Probe", "--time", str(t), "--max-side", "480", "--out", str(out)],
                       capture_output=True, text=True, env=env(), timeout=120)
        return out

    def _sel(self, layers: list[str]) -> list[str]:
        a = [self.cli, "run", "comp.open", json.dumps({"comp": "Probe"})]
        if layers:
            a += ["layer.select", json.dumps({"layers": layers})]
        return a

    def states(self) -> dict[str, dict]:
        out = {}
        for st, layers in self.STATES.items():
            r = subprocess.run(self._sel(layers) + ["command.list", "{}", "--project", str(self.proj)], capture_output=True, text=True, env=env(), timeout=120)
            docs = [d for d in json_docs(r.stdout) if isinstance(d, list) and d and isinstance(d[0], dict) and "enabled" in d[0]]
            for c in (docs[-1] if docs else []):
                out.setdefault(c["id"], {})[st] = True if c.get("enabled") else (c.get("why") or False)
        return out

    def run_command(self, row: dict, d: Path) -> dict:
        cp = d / f"{row['id']}.ecproj"
        shutil.copyfile(self.proj, cp)
        a = self._sel(["Image"]) + [row["id"], "{}", "--project", str(cp), "--save"]
        try:
            r = subprocess.run(a, capture_output=True, text=True, env=env(), timeout=40, cwd=d)
        except subprocess.TimeoutExpired:
            return {"run": "timeout"}
        text = (r.stderr + "\n" + r.stdout).strip()
        res = {"run": classify(r.returncode, text)}
        if r.returncode != 0:
            res["msg"] = re.sub(r"\s+", " ", text)[-300:]
        else:
            th = d / f"{row['id']}.png"
            self.render(cp, th)
            if th.exists():
                res["visible"] = diff(self.base, th) > 0.3
                if res["visible"]:
                    res["thumb"] = str(th.relative_to(ROOT))
        cp.unlink(missing_ok=True)
        return res

    def run_effect(self, row: dict, d: Path) -> dict:
        cp = d / f"{row['id']}.ecproj"
        shutil.copyfile(self.proj, cp)
        a = self._sel(["Image"]) + ["effect.apply", json.dumps({"effect": row["label"]}), "--project", str(cp), "--save"]
        try:
            r = subprocess.run(a, capture_output=True, text=True, env=env(), timeout=60, cwd=d)
        except subprocess.TimeoutExpired:
            return {"run": "timeout"}
        if r.returncode != 0:
            return {"run": classify(r.returncode, r.stderr + r.stdout), "msg": re.sub(r"\s+", " ", (r.stderr + r.stdout))[-300:]}
        th = d / f"{row['id']}.png"
        self.render(cp, th)
        cp.unlink(missing_ok=True)
        if not th.exists():
            return {"run": "error", "msg": "렌더 실패"}
        v = diff(self.base, th)
        return {"run": "ok", "visible": v > 0.3, "diff": v, "thumb": str(th.relative_to(ROOT))}

    PRESET_AT = {"Transitions": ("Image", [0.1, 0.3, 0.6]), "Backgrounds": ("BG", [0.5, 1.5, 3.0]),
                 "Behaviors": ("Image", [0.5, 1.5, 2.5]), "": ("Title", [0.2, 0.6, 1.2])}

    def run_preset(self, row: dict, d: Path) -> dict:
        """프리셋은 움직임 — 세 시점 프레임을 띠로 이어 남긴다"""
        from PIL import Image
        layer, ts = self.PRESET_AT.get(str(row.get("menu") or ""), ("Image", [0.3, 1.0, 2.0]))
        cp = d / f"{row['id']}.ecproj"
        shutil.copyfile(self.proj, cp)
        if not row.get("menu"):
            cmd = ["layer.applyTextPreset", json.dumps({"layer": layer, "preset": row["id"]})]
        else:
            cmd = ["anim.applyBuiltinPreset", json.dumps({"preset": row["id"], "layers": [layer]})]
        r = subprocess.run(self._sel([layer]) + ["time.set", json.dumps({"time": 0})] + cmd + ["--project", str(cp), "--save"],
                           capture_output=True, text=True, env=env(), timeout=60, cwd=d)
        if r.returncode != 0:
            return {"run": classify(r.returncode, r.stderr + r.stdout), "msg": re.sub(r"\s+", " ", (r.stderr + r.stdout))[-300:]}
        fr = [self.render(cp, d / f"{row['id']}.{k}.png", t) for k, t in enumerate(ts)]
        cp.unlink(missing_ok=True)
        ims = [Image.open(f).convert("RGB") for f in fr if f.exists()]
        if not ims:
            return {"run": "error", "msg": "렌더 실패"}
        strip = Image.new("RGB", (sum(i.width for i in ims) + 6 * (len(ims) - 1), ims[0].height), (255, 255, 255))
        x = 0
        for i in ims:
            strip.paste(i, (x, 0)); x += i.width + 6
        th = d / f"{row['id']}.png"
        strip.save(th)
        for f in fr:
            f.unlink(missing_ok=True)
        from PIL import ImageChops, ImageStat
        moving = any(sum(ImageStat.Stat(ImageChops.difference(ims[0], j)).mean) / 3 > 0.3 for j in ims[1:])
        return {"run": "ok", "visible": True, "moving": moving, "at": ts, "layer": layer, "thumb": str(th.relative_to(ROOT))}


# ---------------------------------------------------------------- PhotoCraft
class PhotoCraft:
    app = "photocraft"
    STATES = {"none": None, "pixel": "Layer 0", "text": "Title", "shape": "Shape"}

    def __init__(self, work: Path):
        self.cli = str(cli(self.app))
        self.work = work
        self.doc = work / "sample.psd"

    def setup(self) -> None:
        from PIL import Image, ImageDraw
        card = self.work / "card.png"
        im = Image.new("RGB", (600, 800), (236, 230, 220))
        d = ImageDraw.Draw(im)
        for k, c in enumerate([(220, 60, 60), (60, 140, 220), (250, 200, 40), (40, 170, 110)]):
            d.rectangle([50 + k * 130, 80, 150 + k * 130, 350], fill=c)
        d.ellipse([150, 420, 450, 720], fill=(30, 40, 60))
        im.save(card)
        r = subprocess.run([self.cli, "run", str(card), "--cmd", "layer.new.layerFromBackground", "--params", '{"ifPresent":true}',
                            "--cmd", "type.create", "--params", json.dumps({"x": 300, "y": 60, "text": "견본 Probe", "name": "Title"}),
                            "--cmd", "shape.create", "--params", json.dumps({"kind": "ellipse", "rect": [420, 600, 140, 140], "name": "Shape"}),
                            "--out", str(self.doc)], capture_output=True, text=True, env=env(), timeout=120)
        if r.returncode != 0 or not self.doc.exists():
            raise SystemExit(f"견본 문서를 못 만들었습니다: {(r.stderr or r.stdout)[-400:]}")
        self.base = self.png(self.doc, self.work / "base.png")

    def png(self, doc: Path, out: Path) -> Path:
        subprocess.run([self.cli, "convert", str(doc), str(out)], capture_output=True, text=True, env=env(), timeout=120)
        return out

    def _sel(self, name: str | None) -> list[str]:
        return ["--cmd", "layer.select", "--params", json.dumps({"name": name})] if name else []

    def states(self) -> dict[str, dict]:
        out = {}
        for st, name in self.STATES.items():
            a = [self.cli, "run", str(self.doc)] + (self._sel(name) if name else ["--cmd", "select.deselectLayers", "--params", "{}"]) + ["--cmd", "command.list", "--params", "{}"]
            r = subprocess.run(a, capture_output=True, text=True, env=env(), timeout=120)
            rows = []
            for o in json_docs(r.stdout):
                if isinstance(o, dict) and o.get("command") == "command.list":
                    rows = o["result"] if isinstance(o["result"], list) else o["result"].get("commands", [])
            for c in rows:
                out.setdefault(c["id"], {})[st] = True if c.get("enabled") else (c.get("disabledReason") or False)
        return out

    def run_command(self, row: dict, d: Path) -> dict:
        cp = d / f"{row['id']}.psd"
        a = [self.cli, "run", str(self.doc)] + self._sel("Layer 0") + ["--cmd", row["id"], "--params", "{}", "--out", str(cp)]
        try:
            r = subprocess.run(a, capture_output=True, text=True, env=env(), timeout=40, cwd=d)
        except subprocess.TimeoutExpired:
            return {"run": "timeout"}
        text = (r.stderr + "\n" + r.stdout).strip()
        res = {"run": classify(r.returncode, text)}
        if r.returncode != 0:
            res["msg"] = re.sub(r"\s+", " ", text)[-300:]
        elif cp.exists():
            th = self.png(cp, d / f"{row['id']}.png")
            if th.exists():
                res["visible"] = diff(self.base, th) > 0.3
                if res["visible"]:
                    res["thumb"] = str(th.relative_to(ROOT))
        cp.unlink(missing_ok=True)
        return res

    def run_effect(self, row: dict, d: Path) -> dict:
        return {"run": "untested"}


# ---------------------------------------------------------------- 나머지 앱: 범용 실행기(craft_script)로 명령 하나씩
EXT = {"vectorcraft": "vectorcraft", "soundcraft": "scraft", "filmcraft": "fcproj", "figcraft": "figcraft", "designcraft": "designcraft",
       "deckcraft": "deckcraft", "pdfcraft": "pdf", "solidcraft": "sc", "cadcraft": "dxf", "texturecraft": "tcraft", "gridcraft": "xlsx",
       "wordcraft": "docx", "lightcraft": "lcraft"}


class Generic:
    def __init__(self, work: Path, app: str):
        self.app, self.work = app, work
        self.sample = None

    def setup(self) -> None:
        from craft.adapters.craft_script import craft
        self.craft = craft
        ext = EXT.get(self.app)
        cands = sorted((ROOT / "data" / "compositions").rglob(f"*.{ext}"), key=lambda f: f.stat().st_size) if ext else []
        cands = [f for f in cands if f.stat().st_size < 5_000_000 and "/try" not in str(f)]
        if self.app == "lightcraft":                      # 사진 보정: 견본 사진을 연다
            from PIL import Image, ImageDraw
            self.sample = self.work / "sample.png"
            im = Image.new("RGB", (900, 1200), (180, 150, 120))
            d = ImageDraw.Draw(im)
            for k, c in enumerate([(220, 60, 60), (60, 140, 220), (250, 200, 40), (40, 170, 110)]):
                d.rectangle([80 + k * 190, 120, 230 + k * 190, 520], fill=c)
            d.ellipse([200, 620, 700, 1120], fill=(30, 40, 60))
            im.save(self.sample)
        elif self.app == "filmcraft":                     # 영상 연결이 끊기지 않게 견본 클립을 절대 경로로 넣어 새로 만든다
            clip = self.work / "clip.mp4"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=4",
                            "-pix_fmt", "yuv420p", str(clip)], check=True)
            fc = str(cli("filmcraft"))
            self.sample = self.work / "sample.fcproj"
            subprocess.run([fc, "--save-as", str(self.sample), "exec", "file.newSequence", json.dumps({"name": "Probe", "width": 1080, "height": 1920, "fps": 30})],
                           capture_output=True, text=True, env=env(), timeout=120, check=True)
            r = subprocess.run([fc, "--compact", "--project", str(self.sample), "--save", "import", str(clip)], capture_output=True, text=True, env=env(), timeout=120)
            item = json.loads(r.stdout[r.stdout.index("{"):])["items"][0]
            subprocess.run([fc, "--project", str(self.sample), "--save", "exec", "timeline.place", json.dumps({"item": item, "track": "V1", "seconds": 0, "insert": False, "audio": False})],
                           capture_output=True, text=True, env=env(), timeout=120, check=True)
            r = subprocess.run([fc, "--compact", "--project", str(self.sample), "exec", "sequence.inspect", "{}"], capture_output=True, text=True, env=env(), timeout=120)
            seq = json.loads(r.stdout[r.stdout.index("{"):])
            self.clip = next((c.get("clip", c.get("id")) for t in seq.get("video") or [] for c in t.get("items") or []), None)
        elif cands:
            self.sample = self.work / f"sample.{ext}"
            shutil.copyfile(cands[len(cands) // 2], self.sample)
        self.base = None
        try:
            info = self._craft("base", [], self.work / "base.png")
            self.base = self.work / "base.png" if (self.work / "base.png").exists() else None
        except Exception as e:  # noqa: BLE001
            print(f"[시험] 견본 렌더 실패(화면 비교 없이 진행): {str(e)[-200:]}")

    def _craft(self, sid: str, steps: list, out: Path) -> dict:
        m = {"type": "craft", "id": sid, "app": self.app, "steps": steps, "timeout": 40}
        if self.sample:
            m["open"] = str(self.sample.relative_to(ROOT))
        return self.craft(m, out, out.parent)

    def states(self) -> dict:
        return {}

    def run_command(self, row: dict, d: Path) -> dict:
        sid = re.sub(r"[^A-Za-z0-9_-]+", "_", row.get("_sid") or row["id"])
        out = d / f"{sid}.png"
        try:
            info = self._craft(sid, [{"id": row["id"], "params": row.get("_p") or {}}], out)
        except Exception as e:  # noqa: BLE001
            t = re.sub(r"\s+", " ", str(e))
            return {"run": "timeout" if "시간 제한" in t else classify(1, t), "msg": t[-300:]}
        finally:
            for f in d.glob(f"{sid}.*"):
                if f.suffix != ".png":
                    shutil.rmtree(f, ignore_errors=True) if f.is_dir() else f.unlink(missing_ok=True)
        res = {"run": "ok"}
        if self.base and out.exists():
            res["visible"] = diff(self.base, out) > 0.3
            if res["visible"]:
                res["thumb"] = str(out.relative_to(ROOT))
        return res

    def run_effect(self, row: dict, d: Path) -> dict:
        if self.app == "filmcraft" and getattr(self, "clip", None) is not None:   # 효과는 명령이 아니다 — 견본 클립에 적용
            return self.run_command({**row, "id": "effects.apply", "_p": {"clips": [self.clip], "effect": row["id"]}, "_sid": "fx_" + row["id"]}, d)
        return self.run_command(row, d)


DRIVERS = {"effectcraft": EffectCraft, "photocraft": PhotoCraft, **{a: (lambda w, a=a: Generic(w, a)) for a in EXT}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("app", choices=sorted(DRIVERS))
    ap.add_argument("--part", action="append", choices=["states", "commands", "effects", "presets"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    parts = a.part or ["states", "commands", "effects", "presets"]
    work = WORK / a.app
    for k in ("cmd", "fx", "pre"):           # 이번에 돌리는 부분의 견본만 새로(다른 부분 견본은 남긴다)
        sub = work / k
        if {"cmd": "commands", "fx": "effects", "pre": "presets"}[k] in parts:
            shutil.rmtree(sub, ignore_errors=True)
        sub.mkdir(parents=True, exist_ok=True)
    os.environ.update(env())
    drv = DRIVERS[a.app](work)
    drv.setup()
    rows = catalog(a.app)
    prev = {}
    out_f = OUT / f"{a.app}.jsonl"
    if out_f.exists():
        prev = {r["id"]: r for r in (json.loads(x) for x in out_f.read_text("utf-8").splitlines() if x.strip())}
    res = {r["id"]: {**prev.get(r["id"], {}), "id": r["id"], "kind": r["kind"], "label": r["label"], "menu": r.get("menu")} for r in rows}
    for v in res.values():                                  # 지난 기록도 오류 문구로 다시 분류(분류 규칙이 늘었을 때)
        if v.get("msg") and v.get("run") in ("error", "needs_params", "needs_context"):
            v["run"] = classify(1, v["msg"])
    if "states" in parts:
        print("[시험] 상태별 조건(command.list)…", flush=True)
        st = drv.states()
        for i, s in st.items():
            if i in res:
                res[i]["states"] = s
    todo = []
    if "commands" in parts:
        todo += [("cmd", r) for r in rows if r["kind"] in ("command", "tool") and not SKIP.match(r["id"])]
    if "effects" in parts:
        todo += [("fx", r) for r in rows if r["kind"] == "effect"]
    if "presets" in parts and hasattr(drv, "run_preset"):
        todo += [("pre", r) for r in rows if r["kind"] == "preset"]
    if a.limit:
        todo = todo[: a.limit]
    print(f"[시험] {len(todo)}개 실행(동시 {a.jobs})…", flush=True)
    done = 0
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        fn = {"cmd": drv.run_command, "fx": drv.run_effect, "pre": getattr(drv, "run_preset", None)}
        futs = {ex.submit(fn[k], r, work / k): r for k, r in todo}
        for f in cf.as_completed(futs):
            r = futs[f]
            try:
                res[r["id"]].update(f.result())
            except Exception as e:  # noqa: BLE001
                res[r["id"]].update({"run": "error", "msg": str(e)[-300:]})
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(todo)}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for v in res.values():                                  # 오류 문구의 내 컴퓨터 경로는 감춘다(기록은 저장소에 올라간다)
        if v.get("msg"):
            v["msg"] = v["msg"].replace(str(ROOT), "<repo>").replace(str(SANDBOX), "<home>").replace(str(Path.home()), "~")
    out_f.write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in res.values()), "utf-8")
    # 효과 견본 판(분류마다)
    by: dict[str, list] = {}
    for v in res.values():
        if v.get("thumb") and v.get("visible"):
            menu = v.get("menu") or []
            m = " ".join(menu[:2]) if isinstance(menu, list) else str(menu)
            m = m or ".".join(v["id"].split(".")[:2 if v["id"].count(".") >= 2 else 1])
            by.setdefault(f"{v['kind']} {m or '기타'}", []).append((v["label"], ROOT / v["thumb"]))
    sheets = []
    for m, items in sorted(by.items()):
        p = work / "sheets" / f"{re.sub(r'[^A-Za-z0-9]+', '_', m)}.png"
        sheet(items, p, *((2, 620) if m.startswith("preset") else (6, 200)))
        sheets.append((m, len(items), p))
    from collections import Counter
    cnt = Counter((v["kind"], v.get("run", "untested")) for v in res.values())
    lines = [f"# {a.app} 기능 시험 결과(engine/craft/probe.py)", "", "| 종류 | 결과 | 수 |", "|---|---|---|"]
    lines += [f"| {k} | {r} | {n} |" for (k, r), n in sorted(cnt.items())]
    if sheets:
        lines += ["", "## 견본 판(기본값 그대로 · 이미지 · 픽셀 레이어에 적용해 화면이 바뀐 것) — Read 로 본다"]
        lines += [f"- {m} ({n}개): `{p.relative_to(ROOT)}`" for m, n, p in sheets]
    why = Counter(str(s) for v in res.values() for s in (v.get("states") or {}).values() if s is not True and s)
    if why:
        lines += ["", "## 안 될 때 이유(상태별 command.list — 많은 순)"] + [f"- {w} — {n}" for w, n in why.most_common(15)]
    (OUT / f"{a.app}.md").write_text("\n".join(lines) + "\n", "utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
