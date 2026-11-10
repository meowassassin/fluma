"""Craft 파이프라인 — 조립 단계: 장면 렌더(무음) + 믹스 → FilmCraft 프로젝트(.fcproj) → 최종 MP4.

설계: 볼트 02 Architecture/Craft 파이프라인 설계 — 제작 도구로 영상 만들기.md (2 · 5절)
  시퀀스 1080×1920 · fps 는 렌더와 같게
  V1  EffectCraft 렌더(자막은 EffectCraft 가 이미 그림)
  A1  SoundCraft 믹스
  자막 SRT(<id>.srt)는 업로드용으로 함께 남긴다 — 화면에 다시 입히지 않는다
  마커     장면 경계마다 '장면 N · 역할' + 대사 앞부분 — 사람이 .fcproj 를 열어 고칠 곳을 바로 찾는다(<id>.markers.csv 도 남김)
  내보내기 'YouTube Shorts 1080×1920' 프리셋(-14 LUFS · -1 dBTP) — SoundCraft 가 이미 -14 로 맞췄으면(craft.json audio.lufs
           가 -15~-13) 다시 정규화하지 않는다. 9:16 이 아니거나 크기가 다르면 프레임 크기 · 비트레이트만 바꿔 같은 프리셋을 쓴다
  썸네일   훅 장면 가운데 프레임 → <id>.thumb.png (file.exportFrame)
결과: data/compositions/<id>/craft/edit/<id>.fcproj · 내보낸 영상 경로
사람이 .fcproj 를 고쳤으면(해시가 다르면) 다시 만들지 않고 그 프로젝트로 내보내기만 한다(마커도 사람이 고친 그대로).
"""
from __future__ import annotations

import hashlib
import time
import shutil
import json
import os
import subprocess
from pathlib import Path

from .audio import ROOT, cli, _sha
from .motion import chunks

TICKS = 254016000000          # FilmCraft 1초
PRESET = "YouTube Shorts 1080×1920"


def _fc(fc: Path, *args: str, cwd: Path) -> dict:
    r = subprocess.run([str(fc), "--compact", *args], cwd=str(cwd), text=True, capture_output=True, timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"filmcraft {' '.join(args[:3])}: {(r.stderr or r.stdout)[-600:]}")
    lines = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("{")]
    return json.loads(lines[-1]) if lines else {}


def _run_script(fc: Path, proj: Path, lines: list[dict], cwd: Path) -> list[dict]:
    """여러 명령을 run 한 번에(--save) — 줄마다 결과(JSON)"""
    sp = cwd / f".{proj.stem}.run.jsonl"
    sp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines), "utf-8")
    r = subprocess.run([str(fc), "--compact", "--project", str(proj), "--save", "run", str(sp)], cwd=str(cwd), text=True, capture_output=True, timeout=900)
    sp.unlink(missing_ok=True)
    if r.returncode != 0:
        raise RuntimeError(f"filmcraft run: {(r.stderr or r.stdout)[-600:]}")
    return [json.loads(ln) for ln in r.stdout.splitlines() if ln.strip().startswith("{")]


def scene_times(sb: dict) -> list[tuple[float, float]]:
    """장면마다 (시작, 끝) 초 — 렌더와 같게 sec 를 차례로 더한다"""
    t, out = 0.0, []
    for s in sb.get("scenes") or []:
        sec = float(s.get("sec") or 0)
        out.append((round(t, 3), round(t + sec, 3)))
        t += sec
    return out


def _lead(text: str, n: int = 28) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n].rstrip() + "…"


ROLE_KO = {"hook": "훅", "setup": "상황", "problem": "문제", "contrast": "대비", "item": "항목", "step": "단계", "reveal": "반전",
           "verdict": "결론", "body": "본론", "proof": "근거", "mood": "분위기", "cta": "마무리", "outro": "마무리"}


def markers(sb: dict) -> list[dict]:
    """장면 경계 마커: 이름 '3. 본론', 메모 = 대사(없으면 자막 · 장면 설명) 앞부분. 훅은 장미색 · 마지막 장면은 초록"""
    times = scene_times(sb)
    scs = sb.get("scenes") or []
    out = []
    for i, (s, (a, _b)) in enumerate(zip(scs, times)):
        role = str(s.get("role") or "")
        name = f"{i + 1}. {ROLE_KO.get(role, role) or '장면'}"
        color = "rose" if role == "hook" else ("green" if i == len(scs) - 1 else "blue")
        out.append({"id": "markers.add", "params": {"target": "program", "time": int(round(a * TICKS)), "name": name,
                                                     "comment": _lead(s.get("narration") or s.get("caption") or s.get("beat") or ""),
                                                     "color": color, "author": "Fluma"}})
    return out


def thumb_time(sb: dict, words: list[dict] | None = None) -> float:
    """썸네일 후보 시각 = 훅 장면(role=hook, 없으면 첫 장면) 가운데.
    훅의 핵심어(visual.primary, 예: '101번')를 말하는 단어가 있으면 그 0.7초 뒤(화면에 그 내용이 떠 있을 때)"""
    times = scene_times(sb)
    if not times:
        return 0.0
    scs = sb.get("scenes") or []
    k = next((i for i, s in enumerate(scs) if s.get("role") == "hook"), 0)
    a, b = times[k]
    key = "".join(str((scs[k].get("visual") or {}).get("primary") or "").split())
    if key and words:
        for w in words:
            t = float(w.get("startMs", 0)) / 1000
            txt = "".join(str(w.get("text") or "").split())
            if a <= t < b and txt and (key in txt or (len(txt) >= 2 and txt in key)):
                return round(min(b - 0.1, t + 0.7), 3)
    return round((a + b) / 2, 3)


def export_settings(width: int, height: int, lufs: float | None, keep_level: bool = False) -> dict:
    """Shorts 프리셋 위에 겹칠 설정. 소리가 이미 -14 근처면 다시 정규화하지 않는다(두 번 하면 리미터가 또 걸림).
    keep_level: SoundCraft 가 일부러 키우지 않은 소리(효과음만 · 사람이 고친 세션, 기록 target_lufs 가 null) — 정규화하지 않는다"""
    st: dict = {}
    if (width, height) != (1080, 1920):
        st["frameSize"] = [width, height]
        st["bitrateKbps"] = max(2000, int(12000 * width * height / (1080 * 1920)))
        st["maxBitrateKbps"] = int(st["bitrateKbps"] * 4 / 3)
    if (lufs is not None and -15.0 <= float(lufs) <= -13.0) or (lufs is not None and keep_level):
        st["effects"] = {"loudness": {"enabled": False}}
    return st


def srt(words: list[dict]) -> str:
    def ts(s: float) -> str:
        ms = int(round(s * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    out = []
    for i, c in enumerate(chunks(words), 1):
        out.append(f"{i}\n{ts(c['start'])} --> {ts(c['end'])}\n{c['text']}\n")
    return "\n".join(out)


def assemble(sb: dict, video: Path, audio: Path | None, out: Path, fps: int = 30, width: int = 1080, height: int = 1920) -> Path | None:
    """프로젝트를 만들고(또는 사람이 고친 것을 쓰고) 내보낸다. FilmCraft 가 없으면 None"""
    fc = cli("filmcraft")
    if not fc:
        return None
    sid = sb["id"]
    d = ROOT / "data" / "compositions" / sid / "craft" / "edit"
    d.mkdir(parents=True, exist_ok=True)
    proj = d / f"{sid}.fcproj"
    man_p = d.parent / "craft.json"
    man = json.loads(man_p.read_text("utf-8")) if man_p.exists() else {}
    ed = man.get("edit") or {}
    caps_p = ROOT / "data" / "public" / "audio" / f"{sid}.captions.json"
    words = json.loads(caps_p.read_text("utf-8")) if caps_p.exists() else []
    if caps_p.exists():
        (d / f"{sid}.srt").write_text(srt(words), "utf-8")
    edited = proj.exists() and ed.get("hash") and _sha(proj) != ed["hash"]
    if edited and not ed.get("keep"):
        # 해시만 다르다고 '사람이 고친 것'으로 계속 쓰면, 그 프로젝트에 박힌 예전 영상 타임라인으로 내보내 화면이 멈추거나 검게 나왔다
        # (2026-11-10 DB 인덱스 영상: 에이전트가 앱 도구로 열어 다시 저장한 뒤 '45초 내내 같은 화면'). 고친 판은 백업하고 새 영상으로 다시 짓는다.
        # 사람이 고친 조립을 그대로 쓰려면 craft.json 의 edit.keep = true
        bak = proj.with_name(f"{proj.stem}.edited-{time.strftime('%Y%m%d-%H%M%S')}{proj.suffix}")
        shutil.copy2(proj, bak)
        print(f"[조립] {os.path.relpath(proj, ROOT)} 이 바뀌어 있어 백업({bak.name})하고 새 영상으로 다시 짓습니다 — 고친 판을 그대로 쓰려면 craft.json edit.keep=true")
        edited = False
    try:
        if not edited:
            proj.unlink(missing_ok=True)
            _fc(fc, "--save-as", str(proj), "exec", "file.newSequence", json.dumps({"name": sb.get("title") or sid, "width": width, "height": height, "fps": fps}), cwd=d)
            vid = _fc(fc, "--project", str(proj), "--save", "import", str(video.resolve()), cwd=d)["items"][0]
            _fc(fc, "--project", str(proj), "--save", "exec", "timeline.place", json.dumps({"item": vid, "track": "V1", "seconds": 0, "insert": False, "audio": False}), cwd=d)
            if audio and audio.exists():
                aid = _fc(fc, "--project", str(proj), "--save", "import", str(audio.resolve()), cwd=d)["items"][0]
                _fc(fc, "--project", str(proj), "--save", "exec", "timeline.place", json.dumps({"item": aid, "track": "A1", "seconds": 0, "insert": False, "video": False}), cwd=d)
            if sb.get("scenes"):
                _run_script(fc, proj, markers(sb), cwd=d)      # 장면 경계 마커(사람이 고칠 곳 찾기)
            from .refine import edit_lines
            rl = edit_lines(sb)                                 # 다듬기(FilmCraft 명령 — 전환 · 색 · 제목 등)
            if rl:
                _run_script(fc, proj, rl, cwd=d)
            ed = {"file": os.path.relpath(proj, ROOT), "hash": _sha(proj), "app": "filmcraft", "by": "craft"}
        else:
            print(f"[조립] {os.path.relpath(proj, ROOT)} 은 사람이 고쳤습니다 — 그 프로젝트로 내보냅니다")
            ed["edited"] = True
        out.parent.mkdir(parents=True, exist_ok=True)
        arec = (man.get("audio") or {}) if audio else {}
        lufs = arec.get("lufs")
        st = export_settings(width, height, lufs, keep_level="target_lufs" in arec and arec.get("target_lufs") is None)
        args = ["--project", str(proj), "export", str(out.resolve()), "--preset", PRESET]
        _fc(fc, *args, *(["--settings", json.dumps(st)] if st else []), cwd=d)
        ed["export"] = {"preset": PRESET, "loudness": "skip" if (st.get("effects") or {}).get("loudness") else -14.0}
    except (RuntimeError, KeyError, IndexError, subprocess.TimeoutExpired) as e:
        print(f"[조립] FilmCraft 실패 — ffmpeg 로 대신 마무리합니다: {e}")
        return None
    # 마커 목록 · 썸네일 후보: 실패해도 영상은 그대로 쓴다(저장하지 않는 실행 — 프로젝트 해시가 그대로)
    try:
        mcsv, thumb = d / f"{sid}.markers.csv", d / f"{sid}.thumb.png"
        tt = thumb_time(sb, words)
        sp = d / f".{sid}.side.jsonl"
        sp.write_text(json.dumps({"id": "markers.exportCsv", "params": {"path": str(mcsv.resolve())}}) + "\n"
                      + json.dumps({"id": "file.exportFrame", "params": {"path": str(thumb.resolve()), "format": "png", "time": int(round(tt * TICKS))}}) + "\n", "utf-8")
        _fc(fc, "--project", str(proj), "run", str(sp), cwd=d)
        sp.unlink(missing_ok=True)
        ed["markers"] = os.path.relpath(mcsv, ROOT) if mcsv.exists() else None
        ed["thumb"] = {"file": os.path.relpath(thumb, ROOT), "t": tt} if thumb.exists() else None
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        print(f"[조립] 마커 목록 · 썸네일을 못 뽑았습니다(영상은 그대로): {e}")
    man["edit"] = ed
    man_p.write_text(json.dumps(man, ensure_ascii=False, indent=1), "utf-8")
    return out if out.exists() else None


def ensure(sid: str) -> Path | None:
    """편집기 미리보기 = FilmCraft. 이 영상의 FilmCraft 편집 프로젝트가 늘 있게 한다.
    - Craft 엔진 렌더가 만든 것(사람이 고친 것 포함)은 그대로 둔다
    - 아직 렌더 전이면: 시퀀스 + 나레이션(data/audio/<id>.wav)만으로 만든다 → 콘티가 생기자마자 FilmCraft 로 연다
    - 다른 엔진으로 렌더한 영상이면: 마지막 렌더(영상 · 소리 분리)로 만든다. 더 새 렌더가 나오면 다시(사람이 고치지 않았을 때만)"""
    d = ROOT / "data" / "compositions" / sid / "craft"
    man_p = d / "craft.json"
    man = json.loads(man_p.read_text("utf-8")) if man_p.exists() else {}
    ed = man.get("edit") or {}
    proj_old = ROOT / ed["file"] if ed.get("file") else None
    sb_p = ROOT / "data" / "storyboards" / f"{sid}.json"
    fc = cli("filmcraft")
    if not fc or not sb_p.exists():
        return proj_old if proj_old and proj_old.exists() else None
    sb = json.loads(sb_p.read_text("utf-8"))
    outs = sorted((p for p in (ROOT / "data" / "out").glob(f"{sid}*.mp4") if "-craft-" not in p.name), key=lambda p: p.stat().st_mtime)
    voice = ROOT / "data" / "audio" / f"{sid}.wav"
    src = outs[-1] if outs else (voice if voice.exists() else None)
    want = f"{src.name}:{int(src.stat().st_mtime)}" if src else "empty"
    if proj_old and proj_old.exists():
        edited = ed.get("hash") and _sha(proj_old) != ed["hash"]
        if edited or ed.get("source") in (None, want) or ed.get("by") == "craft":
            return proj_old                      # Craft 렌더가 만든 것 · 사람이 고친 것 · 이미 최신
    ed_dir = d / "edit"
    ed_dir.mkdir(parents=True, exist_ok=True)
    proj = ed_dir / f"{sid}.fcproj"
    proj.unlink(missing_ok=True)
    import sys as _s
    _s.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
    from engines import aspect_size
    sw, sh = aspect_size(sb)
    _fc(fc, "--save-as", str(proj), "exec", "file.newSequence", json.dumps({"name": sb.get("title") or sid, "width": sw, "height": sh, "fps": 30}), cwd=ed_dir)
    vpath = apath = None
    if src and src.suffix == ".mp4":
        # 영상 · 소리를 나눠 넣는다 — FilmCraft 웹 빌드는 mp4 안의 AAC 를 못 읽어 영상 전체를 '지원 안 함'으로 본다
        vpath, apath = ed_dir / f"{sid}.video.mp4", ed_dir / f"{sid}.audio.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-an", "-c:v", "copy", "-movflags", "+faststart", str(vpath)], check=True)
        if subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(src)], capture_output=True, text=True).stdout.strip():
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "2", "-ar", "48000", str(apath)], check=True)
        else:
            apath = None
    elif src:
        apath = src
    if vpath:
        vid = _fc(fc, "--project", str(proj), "--save", "import", str(vpath.resolve()), cwd=ed_dir)["items"][0]
        _fc(fc, "--project", str(proj), "--save", "exec", "timeline.place", json.dumps({"item": vid, "track": "V1", "seconds": 0, "insert": False, "audio": False}), cwd=ed_dir)
    if apath:
        aid = _fc(fc, "--project", str(proj), "--save", "import", str(apath.resolve()), cwd=ed_dir)["items"][0]
        _fc(fc, "--project", str(proj), "--save", "exec", "timeline.place", json.dumps({"item": aid, "track": "A1", "seconds": 0, "insert": False, "video": False}), cwd=ed_dir)
    man["edit"] = {"file": os.path.relpath(proj, ROOT), "hash": _sha(proj), "app": "filmcraft", "source": want}
    man_p.parent.mkdir(parents=True, exist_ok=True)
    man_p.write_text(json.dumps(man, ensure_ascii=False, indent=1), "utf-8")
    return proj


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "ensure":
        r = ensure(sys.argv[2])
        print(os.path.relpath(r, ROOT) if r else "")
