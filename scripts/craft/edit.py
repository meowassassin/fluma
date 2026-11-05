"""Craft 파이프라인 — 조립 단계: 장면 렌더(무음) + 믹스 → FilmCraft 프로젝트(.fcproj) → 최종 MP4.

설계: 볼트 02 Architecture/Craft 파이프라인 설계 — 제작 도구로 영상 만들기.md (2 · 5절)
  시퀀스 1080×1920 · fps 는 렌더와 같게
  V1  EffectCraft 렌더(자막은 EffectCraft 가 이미 그림)
  A1  SoundCraft 믹스
  자막 SRT(<id>.srt)는 업로드용으로 함께 남긴다 — 화면에 다시 입히지 않는다
결과: compositions/<id>/craft/edit/<id>.fcproj · 내보낸 영상 경로
사람이 .fcproj 를 고쳤으면(해시가 다르면) 다시 만들지 않고 그 프로젝트로 내보내기만 한다.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from .audio import ROOT, cli, _sha
from .motion import chunks


def _fc(fc: Path, *args: str, cwd: Path) -> dict:
    r = subprocess.run([str(fc), "--compact", *args], cwd=str(cwd), text=True, capture_output=True, timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"filmcraft {' '.join(args[:3])}: {(r.stderr or r.stdout)[-600:]}")
    lines = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("{")]
    return json.loads(lines[-1]) if lines else {}


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
    d = ROOT / "compositions" / sid / "craft" / "edit"
    d.mkdir(parents=True, exist_ok=True)
    proj = d / f"{sid}.fcproj"
    man_p = d.parent / "craft.json"
    man = json.loads(man_p.read_text("utf-8")) if man_p.exists() else {}
    ed = man.get("edit") or {}
    caps_p = ROOT / "public" / "audio" / f"{sid}.captions.json"
    if caps_p.exists():
        (d / f"{sid}.srt").write_text(srt(json.loads(caps_p.read_text("utf-8"))), "utf-8")
    edited = proj.exists() and ed.get("hash") and _sha(proj) != ed["hash"]
    try:
        if not edited:
            proj.unlink(missing_ok=True)
            _fc(fc, "--save-as", str(proj), "exec", "file.newSequence", json.dumps({"name": sb.get("title") or sid, "width": width, "height": height, "fps": fps}), cwd=d)
            vid = _fc(fc, "--project", str(proj), "--save", "import", str(video.resolve()), cwd=d)["items"][0]
            _fc(fc, "--project", str(proj), "--save", "exec", "timeline.place", json.dumps({"item": vid, "track": "V1", "seconds": 0, "insert": False, "audio": False}), cwd=d)
            if audio and audio.exists():
                aid = _fc(fc, "--project", str(proj), "--save", "import", str(audio.resolve()), cwd=d)["items"][0]
                _fc(fc, "--project", str(proj), "--save", "exec", "timeline.place", json.dumps({"item": aid, "track": "A1", "seconds": 0, "insert": False, "video": False}), cwd=d)
            ed = {"file": os.path.relpath(proj, ROOT), "hash": _sha(proj), "app": "filmcraft", "by": "craft"}
        else:
            print(f"[조립] {os.path.relpath(proj, ROOT)} 은 사람이 고쳤습니다 — 그 프로젝트로 내보냅니다")
            ed["edited"] = True
        out.parent.mkdir(parents=True, exist_ok=True)
        _fc(fc, "--project", str(proj), "export", str(out.resolve()), "--format", "h264", cwd=d)
    except (RuntimeError, KeyError, IndexError, subprocess.TimeoutExpired) as e:
        print(f"[조립] FilmCraft 실패 — ffmpeg 로 대신 마무리합니다: {e}")
        return None
    man["edit"] = ed
    man_p.write_text(json.dumps(man, ensure_ascii=False, indent=1), "utf-8")
    return out if out.exists() else None


def ensure(sid: str) -> Path | None:
    """편집기 미리보기 = FilmCraft. 이 영상의 FilmCraft 편집 프로젝트가 늘 있게 한다.
    - Craft 엔진 렌더가 만든 것(사람이 고친 것 포함)은 그대로 둔다
    - 아직 렌더 전이면: 시퀀스 + 나레이션(audio/<id>.wav)만으로 만든다 → 콘티가 생기자마자 FilmCraft 로 연다
    - 다른 엔진으로 렌더한 영상이면: 마지막 렌더(영상 · 소리 분리)로 만든다. 더 새 렌더가 나오면 다시(사람이 고치지 않았을 때만)"""
    d = ROOT / "compositions" / sid / "craft"
    man_p = d / "craft.json"
    man = json.loads(man_p.read_text("utf-8")) if man_p.exists() else {}
    ed = man.get("edit") or {}
    proj_old = ROOT / ed["file"] if ed.get("file") else None
    sb_p = ROOT / "storyboards" / f"{sid}.json"
    fc = cli("filmcraft")
    if not fc or not sb_p.exists():
        return proj_old if proj_old and proj_old.exists() else None
    sb = json.loads(sb_p.read_text("utf-8"))
    outs = sorted((p for p in (ROOT / "out").glob(f"{sid}*.mp4") if "-craft-" not in p.name), key=lambda p: p.stat().st_mtime)
    voice = ROOT / "audio" / f"{sid}.wav"
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
    _s.path.insert(0, str(ROOT / "scripts"))
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
