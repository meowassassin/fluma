#!/usr/bin/env python3
"""Craft 초안 · 콘티 · 샷 클립 → 영상 편집기(VEditor / ArtCraft / OpenCut) 타임라인 프로젝트 변환기.

1. 저장 위치: data/compositions/<id>/editor/project.json
2. 타임라인 대상:
   - 비디오 클립 (Main Video Track: 장면별 클립 구간 trimStart/trimEnd/duration)
   - 나레이션 음성 (Audio Track: data/public/audio/<id>.voice.wav)
   - 자막 (Text Overlay Track: data/public/audio/<id>.captions.json 또는 dub.json 자막)
   - 원음 (클립 내 오디오 활성화 플래그)
3. 내보낸 영상: data/compositions/<id>/editor/exported.mp4 -> data/out/<id>-editor.mp4 (최종본)

  python3 engine/gen/editor_bridge.py convert <id>
  python3 engine/gen/editor_bridge.py status <id>
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import uuid
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
sys.path.insert(0, str(Path(__file__).parent))
from result import fail, ok  # noqa: E402

TICKS_PER_SECOND = 120_000
DUB_SIZES = {"S": 52, "M": 72, "L": 100, "XL": 140}   # engine/gen/dub.py SIZES 와 같은 값(1080×1920 기준 px)
FONT_SCALE_REF = 90                                     # 편집기: 실제 px = fontSize × 캔버스 높이 / 90


def px_to_font(px: float, canvas_h: int = 1920) -> float:
    return round(px * FONT_SCALE_REF / canvas_h, 2)


def sec_to_ticks(sec: float) -> int:
    return int(round(float(sec) * TICKS_PER_SECOND))


def probe_video(p: Path) -> tuple[int, int, float]:
    """ffprobe 로 실제 비디오의 가로, 세로, 재생 길이를 알아낸다"""
    if not p or not p.exists():
        return 1080, 1920, 3.0
    try:
        import subprocess
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,duration", "-of", "json", str(p)],
            capture_output=True, text=True, timeout=5,
        )
        data = json.loads(r.stdout)
        s = data.get("streams", [{}])[0]
        w = int(s.get("width") or 1080)
        h = int(s.get("height") or 1920)
        dur = float(s.get("duration") or 3.0)
        return w, h, dur
    except Exception:
        return 1080, 1920, 3.0


def editor_dir(pid: str) -> Path:
    return ROOT / "data" / "compositions" / pid / "editor"


def editor_project_path(pid: str) -> Path:
    return editor_dir(pid) / "project.json"


def editor_exported_path(pid: str) -> Path:
    return editor_dir(pid) / "exported.mp4"


def final_out_path(pid: str) -> Path:
    return ROOT / "data" / "out" / f"{pid}-editor.mp4"


def load_inputs(pid: str) -> tuple[dict | None, dict | None, dict | None]:
    sb_p = ROOT / "data" / "storyboards" / f"{pid}.json"
    sb = json.loads(sb_p.read_text("utf-8")) if sb_p.exists() else None

    dub_p = ROOT / "data" / "compositions" / pid / "dub.json"
    dub = json.loads(dub_p.read_text("utf-8")) if dub_p.exists() else None

    sp_p = ROOT / "data" / "shotplans" / f"{pid}.json"
    sp = json.loads(sp_p.read_text("utf-8")) if sp_p.exists() else None

    return sb, dub, sp


def group_words_into_phrases(words: list[dict], max_words: int = 4, max_gap_ms: int = 400) -> list[dict]:
    """단어 단위 캡션을 2~4단어 단위의 읽기 편한 구(phrase) 자막으로 묶고 시간 겹침을 방지한다."""
    if not words:
        return []
    raw_phrases = []
    curr: list[dict] = []
    for w in words:
        if not curr:
            curr.append(w)
            continue
        prev = curr[-1]
        gap = (w.get("startMs", 0) or 0) - (prev.get("endMs", 0) or 0)
        same_scene = w.get("scene") == prev.get("scene")
        if len(curr) < max_words and gap <= max_gap_ms and same_scene:
            curr.append(w)
        else:
            txt = " ".join(x.get("text", "").strip() for x in curr)
            raw_phrases.append({
                "text": txt,
                "startSec": round(float(curr[0].get("startMs", 0)) / 1000.0, 3),
                "endSec": round(float(curr[-1].get("endMs", 0)) / 1000.0, 3),
                "scene": curr[0].get("scene", 0),
            })
            curr = [w]
    if curr:
        txt = " ".join(x.get("text", "").strip() for x in curr)
        raw_phrases.append({
            "text": txt,
            "startSec": round(float(curr[0].get("startMs", 0)) / 1000.0, 3),
            "endSec": round(float(curr[-1].get("endMs", 0)) / 1000.0, 3),
            "scene": curr[0].get("scene", 0),
        })

    # 타임스탬프 겹침(오버랩) 보정: 다음 자막 시작 전까지만 표시되도록 제한
    clean_phrases = []
    for i, p in enumerate(raw_phrases):
        s = p["startSec"]
        e = p["endSec"]
        if i + 1 < len(raw_phrases):
            next_s = raw_phrases[i + 1]["startSec"]
            if e > next_s:
                e = max(s + 0.2, next_s - 0.05)
        clean_phrases.append({
            "text": p["text"],
            "startSec": round(s, 3),
            "endSec": round(max(s + 0.3, e), 3),
            "scene": p.get("scene", 0),
        })

    return clean_phrases


def convert(pid: str, write: bool = True) -> dict:
    """write=False: 파일을 쓰지 않고 만든 문서를 돌려준다(media 명령 — 잃어버린 미디어 항목 복구용)."""
    sb, dub, sp = load_inputs(pid)
    if not sb and not dub and not sp:
        fail("editor_bridge", stage="convert", error=f"프로젝트 자료 없음: {pid} (storyboard, dub, shotplan 중 하나 필요)")

    ed = editor_dir(pid)
    if write:
        ed.mkdir(parents=True, exist_ok=True)

    title = (sb or dub or sp).get("title") or (sb or dub or sp).get("topic") or pid
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    media_manifest: list[dict] = []
    main_elements: list[dict] = []
    text_elements: list[dict] = []
    audio_elements: list[dict] = []
    sfx_elements: list[dict] = []

    curr_time_sec = 0.0

    # 1. 메인 비디오 트랙 구성
    use_dub = bool(dub and dub.get("segments"))
    if sb and sb.get("scenes") and not use_dub:
        seen_media: dict[str, str] = {}
        for i, sc in enumerate(sb.get("scenes") or []):
            sc_dur = float(sc.get("sec") or 3.0)
            m_video = next((m for m in sc.get("materials") or [] if m.get("type") == "video"), None)
            clip_rel = m_video.get("src") if m_video else None
            trim_in = float(m_video.get("in", 0)) if m_video else 0.0
            trim_out = float(m_video.get("out", sc_dur)) if m_video else sc_dur
            source_dur = trim_out - trim_in

            elem_id = f"video_{i + 1}_{uuid.uuid4().hex[:6]}"
            if not clip_rel:                      # 영상 재료가 없는 장면(검은 화면 · 그림 장면) — 빈 칸으로 두고 시간만 흐른다
                curr_time_sec += sc_dur
                continue
            if clip_rel in seen_media:
                media_id = seen_media[clip_rel]
            else:
                media_id = f"media_video_{len(seen_media) + 1}"
                seen_media[clip_rel] = media_id

            # 미디어 매니페스트 등록
            clip_file = (ROOT / clip_rel).resolve() if clip_rel else None
            clip_size = clip_file.stat().st_size if clip_file and clip_file.exists() else 0
            comp_root = (ROOT / "data" / "compositions").resolve()
            if clip_file and comp_root in clip_file.parents:
                clip_url = f"/api/pipefiles/{clip_file.relative_to(comp_root)}"
            elif clip_file and clip_file.exists():
                clip_url = f"/api/projects/{pid}/studio-file?p={clip_file.relative_to(ROOT)}"
            else:
                clip_url = f"/{clip_rel}" if clip_rel else ""

            vid_w, vid_h, real_dur = probe_video(clip_file)
            source_dur = max(real_dur, sc_dur, source_dur)

            if not any(m["id"] == media_id for m in media_manifest):
              media_manifest.append({
                "id": media_id,
                "name": Path(clip_rel).name if clip_rel else f"scene_{i + 1}.mp4",
                "type": "video",
                "size": clip_size,
                "lastModified": int(clip_file.stat().st_mtime * 1000) if clip_file and clip_file.exists() else int(dt.datetime.now().timestamp() * 1000),
                "duration": round(source_dur, 2),
                "width": vid_w,
                "height": vid_h,
                "hasAudio": bool(m_video.get("audio", False)) if m_video else False,
                "url": clip_url,
            })

            main_elements.append({
                "id": elem_id,
                "name": f"Scene {i + 1} Clip",
                "type": "video",
                "mediaId": media_id,
                "startTime": sec_to_ticks(curr_time_sec),
                "duration": sec_to_ticks(sc_dur),
                "trimStart": sec_to_ticks(trim_in),
                "trimEnd": sec_to_ticks(max(0.0, source_dur - (trim_in + sc_dur))),
                "sourceDuration": sec_to_ticks(source_dur),
                "isSourceAudioEnabled": bool(m_video.get("audio", False)) if m_video else False,
                "hidden": False,
                "params": {},
            })
            curr_time_sec += sc_dur

    elif use_dub:
        clip_rel = dub.get("clip")
        clip_file = (ROOT / clip_rel).resolve() if clip_rel else None
        clip_size = clip_file.stat().st_size if clip_file and clip_file.exists() else 0
        comp_root = (ROOT / "data" / "compositions").resolve()
        if clip_file and comp_root in clip_file.parents:
            dub_clip_url = f"/api/pipefiles/{clip_file.relative_to(comp_root)}"
        elif clip_file and clip_file.exists():
            dub_clip_url = f"/api/projects/{pid}/studio-file?p={clip_file.relative_to(ROOT)}"
        else:
            dub_clip_url = f"/{clip_rel}" if clip_rel else ""

        media_id = "media_dub_clip"
        dw, dh, dub_real = probe_video(clip_file) if clip_file and clip_file.exists() else (1080, 1920, 0.0)
        media_manifest.append({
            "id": media_id,
            "name": Path(clip_rel).name if clip_rel else "clip.mp4",
            "type": "video",
            "size": clip_size,
            "lastModified": int(clip_file.stat().st_mtime * 1000) if clip_file and clip_file.exists() else int(dt.datetime.now().timestamp() * 1000),
            "duration": round(dub_real, 2),
            "width": dw,
            "height": dh,
            "hasAudio": True,
            "url": dub_clip_url,
        })

        for i, seg in enumerate(dub.get("segments") or []):
            stype = seg.get("type", "clip")
            if stype == "clip":
                in_s = float(seg.get("in", 0))
                out_s = float(seg.get("out", in_s + 2))
                seg_dur = out_s - in_s
                main_elements.append({
                    "id": f"dub_clip_{i + 1}_{uuid.uuid4().hex[:6]}",
                    "name": f"Clip segment {i + 1}",
                    "type": "video",
                    "mediaId": media_id,
                    "startTime": sec_to_ticks(curr_time_sec),
                    "duration": sec_to_ticks(seg_dur),
                    "trimStart": sec_to_ticks(in_s),
                    "trimEnd": sec_to_ticks(max(0.0, (dub_real or out_s) - out_s)),
                    "sourceDuration": sec_to_ticks(dub_real or out_s),
                    "isSourceAudioEnabled": True,
                    "hidden": False,
                    "params": {},
                })
                curr_time_sec += seg_dur
            elif stype == "insert":
                dur = float(seg.get("sec", 2))
                ins_rel = seg.get("src", "")
                ins_id = f"media_insert_{i + 1}"
                ins_file = (ROOT / ins_rel).resolve() if ins_rel else None
                ins_is_img = Path(ins_rel).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
                comp_root = (ROOT / "data" / "compositions").resolve()
                if ins_file and comp_root in ins_file.parents:
                    ins_url = f"/api/pipefiles/{ins_file.relative_to(comp_root)}"
                elif ins_file and ins_file.exists():
                    ins_url = f"/api/projects/{pid}/studio-file?p={ins_file.relative_to(ROOT)}"
                else:
                    ins_url = f"/{ins_rel}" if ins_rel else ""

                media_manifest.append({
                    "id": ins_id,
                    "name": Path(ins_rel).name if ins_rel else "insert",
                    "type": "image" if ins_is_img else "video",
                    "size": ins_file.stat().st_size if ins_file and ins_file.exists() else 0,
                    "lastModified": int(ins_file.stat().st_mtime * 1000) if ins_file and ins_file.exists() else int(dt.datetime.now().timestamp() * 1000),
                    "duration": dur,
                    "hasAudio": False,
                    "url": ins_url,
                })
                main_elements.append({
                    "id": f"insert_{i + 1}_{uuid.uuid4().hex[:6]}",
                    "name": f"Insert {i + 1}",
                    "type": "image" if ins_is_img else "video",
                    "mediaId": ins_id,
                    "startTime": sec_to_ticks(curr_time_sec),
                    "duration": sec_to_ticks(dur),
                    "trimStart": 0,
                    "trimEnd": 0,
                    "hidden": False,
                    "params": {},
                })
                curr_time_sec += dur
            elif stype == "black":                # 검은 화면(멈춤 · 뜸) — 빈 칸 = 배경색(검정)
                curr_time_sec += float(seg.get("sec", 2))

    total_duration_sec = max(curr_time_sec, 1.0)

    # 2. 오디오 트랙 구성 (나레이션 음성)
    voice_file = ROOT / "data" / "public" / "audio" / f"{pid}.voice.wav"
    if not voice_file.exists():
        voice_file = ROOT / "data" / "audio" / f"{pid}.voice.wav"
    if not voice_file.exists():
        voice_file = ROOT / "data" / "audio" / f"{pid}.wav"

    if voice_file.exists():
        import subprocess
        voice_dur = total_duration_sec
        try:
            r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(voice_file)], capture_output=True, text=True, timeout=10)
            if r.stdout.strip():
                voice_dur = float(r.stdout.strip())
        except Exception:
            pass

        media_voice_id = "media_narration_voice"
        media_manifest.append({
            "id": media_voice_id,
            "name": voice_file.name,
            "type": "audio",
            "size": voice_file.stat().st_size,
            "lastModified": int(voice_file.stat().st_mtime * 1000),
            "duration": round(voice_dur, 2),
            "hasAudio": True,
            "url": f"/api/projects/{pid}/studio-file?p={voice_file.relative_to(ROOT)}",
        })

        audio_elements.append({
            "id": f"audio_narration_{uuid.uuid4().hex[:6]}",
            "name": "나레이션 (Voice)",
            "type": "audio",
            "sourceType": "upload",
            "mediaId": media_voice_id,
            "startTime": 0,
            "duration": sec_to_ticks(voice_dur),
            "trimStart": 0,
            "trimEnd": 0,
            "sourceDuration": sec_to_ticks(voice_dur),
            "params": {"volume": 0},
        })

    # 2-2. 효과음(삐 · 장면 시작 효과음) — assemble_audio 가 나레이션과 따로 남긴 sfx.wav, 소리가 있을 때만
    sfx_file = ROOT / "data" / "public" / "audio" / f"{pid}.sfx.json"
    sfx_wav = sfx_file.with_name(f"{pid}.sfx.wav")
    try:
        has_sfx = sfx_wav.exists() and bool(json.loads(sfx_file.read_text("utf-8")))
    except Exception:
        has_sfx = False
    if has_sfx:
        media_manifest.append({"id": "media_sfx", "name": sfx_wav.name, "type": "audio", "size": sfx_wav.stat().st_size,
                               "lastModified": int(sfx_wav.stat().st_mtime * 1000), "duration": round(total_duration_sec, 2), "hasAudio": True,
                               "url": f"/api/projects/{pid}/studio-file?p={sfx_wav.relative_to(ROOT)}"})
        sfx_elements.append({"id": f"audio_sfx_{uuid.uuid4().hex[:6]}", "name": "효과음", "type": "audio", "sourceType": "upload",
                             "mediaId": "media_sfx", "startTime": 0, "duration": sec_to_ticks(total_duration_sec), "trimStart": 0, "trimEnd": 0,
                             "sourceDuration": sec_to_ticks(total_duration_sec), "params": {"volume": 0}})

    # 3. 자막 텍스트 트랙 구성
    # 3-1. dub.json 의 captions (클립 재편집 경로) 또는 콘티 상단 제목
    title_elements: list[dict] = []
    if use_dub:
        seg_start, acc = [], 0.0
        for seg in dub.get("segments") or []:
            seg_start.append(acc)
            acc += (float(seg.get("out", 0)) - float(seg.get("in", 0))) if seg.get("type", "clip") == "clip" else float(seg.get("sec", 2))
        lines = [str(x).strip() for x in (dub.get("title") or []) if str(x).strip()]
        if lines:
            title_elements.append({
                "id": f"title_{uuid.uuid4().hex[:6]}", "name": "제목", "type": "text",
                "startTime": 0, "duration": sec_to_ticks(acc), "trimStart": 0, "trimEnd": 0, "hidden": False,
                "params": {"content": "\n".join(lines[:2]), "fontSize": px_to_font(84), "fontFamily": "Pretendard", "color": "#FFFFFF",
                           "textAlign": "center", "fontWeight": "bold", "lineHeight": 1.25,
                           "transform.positionX": 0, "transform.positionY": round(230 + 84 * 1.25 / 2 - 960, 1),
                           "background.enabled": False},
            })
    elif (sb or sp) and ((sb or {}).get("title") or (sp or {}).get("title")):
        raw_title = str((sb or {}).get("title") or (sp or {}).get("title") or "").strip()
        if raw_title:
            title_elements.append({
                "id": f"title_{uuid.uuid4().hex[:6]}", "name": "상단 제목", "type": "text",
                "startTime": 0, "duration": sec_to_ticks(total_duration_sec), "trimStart": 0, "trimEnd": 0, "hidden": False,
                "params": {"content": raw_title, "fontSize": px_to_font(64), "fontFamily": "Pretendard", "color": "#FFFFFF",
                           "textAlign": "center", "fontWeight": "bold", "lineHeight": 1.25,
                           "transform.positionX": 0, "transform.positionY": -720,
                           "background.enabled": True, "background.color": "rgba(0, 0, 0, 0.55)",
                           "background.cornerRadius": 12, "background.paddingX": 22, "background.paddingY": 12},
            })
    if dub and dub.get("captions"):
        for i, cap in enumerate(dub.get("captions") or []):
            base = seg_start[cap["seg"]] if use_dub and 0 <= int(cap.get("seg", -1)) < len(seg_start) else 0.0
            t0 = base + float(cap.get("t0", 0))
            t1 = base + float(cap.get("t1", float(cap.get("t0", 0)) + 1.2))
            dur = max(0.2, t1 - t0)
            text_str = cap.get("text", "").strip()
            if not text_str:
                continue
            is_hot = bool(cap.get("hot", False))
            x_ratio = float(cap.get("x", 0.5))
            y_ratio = float(cap.get("y", 0.65))

            text_elements.append({
                "id": f"caption_{i + 1}_{uuid.uuid4().hex[:6]}",
                "name": f"자막: {text_str[:8]}",
                "type": "text",
                "startTime": sec_to_ticks(t0),
                "duration": sec_to_ticks(dur),
                "trimStart": 0,
                "trimEnd": 0,
                "hidden": False,
                "params": {
                    "content": text_str,
                    "fontSize": px_to_font(DUB_SIZES.get(cap.get("size", "M"), 72)),
                    "fontFamily": "Pretendard",
                    "color": "#FACC15" if is_hot else "#FFFFFF",
                    "textAlign": "center",
                    "fontWeight": "bold",
                    "transform.positionX": round((x_ratio - 0.5) * 1080, 1),
                    "transform.positionY": round((y_ratio - 0.5) * 1920, 1),
                    "background.enabled": True,
                    "background.color": "rgba(0, 0, 0, 0.65)",
                    "background.cornerRadius": 8,
                    "background.paddingX": 18,
                    "background.paddingY": 10,
                },
            })

    # 3-2. captions.json (단어 단위 타이밍)
    captions_file = ROOT / "data" / "public" / "audio" / f"{pid}.captions.json"
    if not text_elements and captions_file.exists():
        try:
            words = json.loads(captions_file.read_text("utf-8"))
            phrases = group_words_into_phrases(words)
            for i, p in enumerate(phrases):
                dur = max(0.3, p["endSec"] - p["startSec"])
                text_elements.append({
                    "id": f"caption_word_{i + 1}_{uuid.uuid4().hex[:6]}",
                    "name": f"자막: {p['text'][:8]}",
                    "type": "text",
                    "startTime": sec_to_ticks(p["startSec"]),
                    "duration": sec_to_ticks(dur),
                    "trimStart": 0,
                    "trimEnd": 0,
                    "hidden": False,
                    "params": {
                        "content": p["text"],
                        "fontSize": 6.5,
                        "fontFamily": "Pretendard",
                        "color": "#FFFFFF",
                        "textAlign": "center",
                        "fontWeight": "bold",
                        "transform.positionX": 0,
                        "transform.positionY": 560,  # 세로 9:16 하단 안전영역 위
                        "background.enabled": True,
                        "background.color": "rgba(0, 0, 0, 0.65)",
                        "background.cornerRadius": 8,
                        "background.paddingX": 18,
                        "background.paddingY": 10,
                    },
                })
        except Exception:
            pass

    # 3-3. 콘티 장면별 caption (폴백)
    if not text_elements and sb and sb.get("scenes"):
        t_accum = 0.0
        for i, sc in enumerate(sb.get("scenes") or []):
            sc_dur = float(sc.get("sec") or 3.0)
            cap_text = (sc.get("caption") or sc.get("narration") or "").strip()
            if cap_text:
                text_elements.append({
                    "id": f"caption_scene_{i + 1}_{uuid.uuid4().hex[:6]}",
                    "name": f"장면 {i + 1} 자막",
                    "type": "text",
                    "startTime": sec_to_ticks(t_accum),
                    "duration": sec_to_ticks(sc_dur),
                    "trimStart": 0,
                    "trimEnd": 0,
                    "hidden": False,
                    "params": {
                        "content": cap_text,
                        "fontSize": 6.5,
                        "fontFamily": "Pretendard",
                        "color": "#FFFFFF",
                        "textAlign": "center",
                        "fontWeight": "bold",
                        "transform.positionX": 0,
                        "transform.positionY": 560,
                        "background.enabled": True,
                        "background.color": "rgba(0, 0, 0, 0.65)",
                        "background.cornerRadius": 8,
                        "background.paddingX": 18,
                        "background.paddingY": 10,
                    },
                })
            t_accum += sc_dur

    # 4. 추가 에셋: 프로젝트에 생성된 키프레임 및 캐릭터 이미지 자동 등록 (에셋 패널에서 드래그 가능)
    comp_dir = ROOT / "data" / "compositions" / pid
    if comp_dir.is_dir():
        for kf in sorted((comp_dir / "keyframes").glob("*.png")):
            rel_kf = kf.resolve().relative_to(ROOT / "data" / "compositions")
            media_manifest.append({
                "id": f"media_kf_{kf.stem}",
                "name": f"키프레임: {kf.name}",
                "type": "image",
                "size": kf.stat().st_size,
                "lastModified": int(kf.stat().st_mtime * 1000),
                "duration": 3.0,
                "width": 1080,
                "height": 1920,
                "hasAudio": False,
                "url": f"/api/pipefiles/{rel_kf}",
            })
        for ch in sorted(comp_dir.glob("characters/*/*.png")):
            rel_ch = ch.resolve().relative_to(ROOT / "data" / "compositions")
            media_manifest.append({
                "id": f"media_char_{ch.parent.name}_{ch.stem}",
                "name": f"캐릭터: {ch.parent.name} ({ch.stem})",
                "type": "image",
                "size": ch.stat().st_size,
                "lastModified": int(ch.stat().st_mtime * 1000),
                "duration": 3.0,
                "width": 1080,
                "height": 1920,
                "hasAudio": False,
                "url": f"/api/pipefiles/{rel_ch}",
            })

    scene_id = f"scene_{uuid.uuid4().hex[:8]}"

    project_doc = {
        "version": 1,
        "project": {
            "metadata": {
                "id": pid,
                "name": title,
                "duration": sec_to_ticks(total_duration_sec),
                "createdAt": now_iso,
                "updatedAt": now_iso,
            },
            "scenes": [
                {
                    "id": scene_id,
                    "name": "Main scene",
                    "isMain": True,
                    "tracks": {
                        "overlay": ([
                            {
                                "id": f"track_text_{uuid.uuid4().hex[:6]}",
                                "name": "자막 (Subtitles)",
                                "type": "text",
                                "elements": text_elements,
                                "hidden": False,
                            }
                        ] if text_elements else []) + ([
                            {"id": f"track_title_{uuid.uuid4().hex[:6]}", "name": "제목 (Title)", "type": "text", "elements": title_elements, "hidden": False}
                        ] if title_elements else []),
                        "main": {
                            "id": f"track_main_{uuid.uuid4().hex[:6]}",
                            "name": "메인 영상 (Video)",
                            "type": "video",
                            "elements": main_elements,
                            "muted": False,
                            "hidden": False,
                        },
                        "audio": ([
                            {
                                "id": f"track_audio_{uuid.uuid4().hex[:6]}",
                                "name": "나레이션 (Narration)",
                                "type": "audio",
                                "elements": audio_elements,
                                "muted": False,
                            }
                        ] if audio_elements else []) + ([
                            {"id": f"track_sfx_{uuid.uuid4().hex[:6]}", "name": "효과음 (SFX)", "type": "audio", "elements": sfx_elements, "muted": False}
                        ] if sfx_elements else []),
                    },
                    "bookmarks": [],
                    "createdAt": now_iso,
                    "updatedAt": now_iso,
                }
            ],
            "currentSceneId": scene_id,
            "settings": {
                "fps": {"numerator": 30, "denominator": 1},
                "canvasSize": {"width": 1080, "height": 1920},
                "canvasSizeMode": "preset",
                "background": {"type": "color", "color": "#000000"},
            },
            "version": 1,
        },
        "media": media_manifest,
    }
    if not write:
        return project_doc

    out_p = editor_project_path(pid)
    out_p.write_text(json.dumps(project_doc, ensure_ascii=False, indent=2), "utf-8")

    return {
        "file": str(out_p.relative_to(ROOT)),
        "scenes": len(main_elements),
        "duration_sec": round(total_duration_sec, 2),
        "has_voice": bool(audio_elements),
        "captions": len(text_elements),
        "media_count": len(media_manifest),
    }


def status(pid: str) -> dict:
    ep = editor_project_path(pid)
    xp = editor_exported_path(pid)
    fp = final_out_path(pid)

    return {
        "id": pid,
        "has_editor_project": ep.exists(),
        "project_file": str(ep.relative_to(ROOT)) if ep.exists() else None,
        "has_exported": xp.exists(),
        "exported_file": str(xp.relative_to(ROOT)) if xp.exists() else None,
        "has_final_out": fp.exists(),
        "final_out_file": str(fp.relative_to(ROOT)) if fp.exists() else None,
        "mtime": int(ep.stat().st_mtime * 1000) if ep.exists() else 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)

    cv = sp.add_parser("convert")
    cv.add_argument("pid")

    st = sp.add_parser("status")
    st.add_argument("pid")

    # 편집기 저장본에서 빠진 미디어 항목(타임라인 요소는 가리키는데 media 목록에 없는 것)을 되살릴 때 서버가 부른다 — 파일은 쓰지 않음
    md = sp.add_parser("media")
    md.add_argument("pid")

    a = ap.parse_args()

    if a.cmd == "convert":
        res = convert(a.pid)
        ok("editor_bridge", **{k: str(v) for k, v in res.items()})
        return 0

    if a.cmd == "media":
        print(json.dumps(convert(a.pid, write=False)["media"], ensure_ascii=False))
        return 0

    if a.cmd == "status":
        print(json.dumps(status(a.pid), ensure_ascii=False, indent=2))
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
