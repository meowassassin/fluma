"""WordCraft 어댑터 — 실제 문서 화면 재료(type: document).

약관 · 공지 · 공문 · 대본처럼 "문서 그 자체"를 보여 줄 때. 문구를 다시 그리지 않고 WordCraft 가 문서를 9:16 쪽으로
다시 배치해 렌더한다(원문 그대로 · 진짜 형광펜 · 진짜 변경 추적 · 진짜 메모 말풍선).

순서(work 폴더에서, 모두 창 없이):
  1. 바탕 문서: src(.docx · .odt · .rtf · .md · .html · .txt) 를 docx 로 열거나, title + text 로 새로 쓴다 → 쪽 크기 9:16
  2. 변경 추적(track): 고친 판을 따로 만들어(edit.replaceAll) review.compare 로 비교 → 삭제는 취소선 · 새 글은 밑줄.
     비교가 변경을 못 만들면 변경 추적을 켜고 바로 바꾼다(edit.replaceAll — edit.replace 는 조용히 아무것도 안 해서 쓰지 않는다)
  3. 형광펜(highlight) · 메모(comments)
  4. 글자 크기 맞추기: 한 쪽짜리 문서는 쪽을 넘지 않는 데까지 글자를 키운다(쇼츠 화면에서 읽히게)
  5. 렌더: 메모가 있으면 말풍선 칸까지 그린다(쪽 360×1024pt + 말풍선 칸 216pt = 576×1024pt → 1080×1920)
     형광펜이 칠해진 쪽을 고른다(여러 쪽 문서)

콘티 칸:
  src        문서 경로(.docx · .md · .odt · .rtf · .html · .txt) — 또는
  text       본문(줄바꿈 = 문단) · title 제목(Heading 1, 선택)
  highlight  ["문장", …] — 노란 형광펜(원문과 글자가 같아야 한다). color: yellow(기본) · brightGreen · turquoise · pink
  bold       true → 형광펜 문장을 굵게도
  track      {"from": "7일 이내", "to": "14일 이내"} 또는 그 목록 — 바뀐 부분을 변경 추적으로
  author     변경 · 메모 작성자 이름(기본 "편집자")
  comments   [{"at": "문장", "text": "메모"}, …] — 오른쪽 말풍선(문서 폭이 화면의 62% 로 줄어든다)
  font_scale 글자 크기 늘림 %(기본 auto: 한 쪽 문서는 넘치지 않는 데까지, 여러 쪽은 +30)
  page       보여 줄 쪽(1부터, 기본: 형광펜 · 변경이 있는 첫 쪽)

기록(info) 칸:
  app "wordcraft" · as "image" · page · pages · size [1080, 1920] · font_scale · changes(변경 추적 개수) · comments(개수)
  highlight  [[x, y, w, h], …] 형광펜 줄마다 픽셀 상자 · focus 전체를 감싸는 상자(움직임 단계가 확대해 들어갈 곳)
  highlighted true — 형광펜이 이미 그려져 있다(움직임 단계는 가짜 형광펜을 그리지 않는다)
  editable   완성 문서(work/<id>.docx) — 사람이 WordCraft · Word 로 열어 고칠 수 있다
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

PAGE = (360, 640)            # pt — scale 3 → 1080×1920
PAGE_MARKUP = (360, 1024)    # pt — 말풍선 칸(216pt)을 더하면 576×1024 → scale 1.875 → 1080×1920
MARGINS = {"top": 40, "bottom": 40, "left": 30, "right": 30}
HL_RGB = {"yellow": (255, 255, 0), "brightGreen": (0, 255, 0), "turquoise": (0, 255, 255), "pink": (255, 0, 255)}
FIT_STEPS = (0, 20, 40, 60, 80, 100, 130)     # 한 쪽 문서 글자 키우기 후보(%)
FILL = 0.86                                  # 글이 쪽 높이의 이만큼까지 차면 멈춘다


def _wc(args: list, work: Path, timeout: int = 120) -> str:
    from ..materials import cli
    env = {**os.environ, "DO_NOT_TRACK": "1", "WORDCRAFT_REGION": "ko-KR"}   # 종이 기본값이 지역을 따라가서 고정
    r = subprocess.run([cli("wordcraft"), *[str(a) for a in args]], cwd=str(work), text=True, capture_output=True, timeout=timeout, env=env)
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip().splitlines()
        raise RuntimeError(f"WordCraft 실패: {(msg[-1] if msg else '')[-300:]}")
    return r.stdout


def _script(work: Path, name: str, commands: list, file: Path | None = None, save: list | None = None, author: str | None = None) -> list:
    """명령 목록을 스크립트 JSON 으로 돌린다 → [(명령 id, 결과), …] 차례대로"""
    sp = work / name
    body: dict = {"commands": commands}
    if file:
        body["file"] = str(file)
    if save:
        body["save"] = [str(s) for s in save]
    sp.write_text(json.dumps(body, ensure_ascii=False), "utf-8")
    args = ["run", "--script", sp, "--print"]
    if author:
        args += ["--author", author]
    res = []
    for ln in _wc(args, work).splitlines():
        k, sep, v = ln.partition(": ")
        if sep and not k.startswith("wrote") and " " not in k.strip():
            try:
                res.append((k.strip(), json.loads(v)))
            except ValueError:
                res.append((k.strip(), v))
    return res


def _last(res: list, cmd: str):
    return next((v for k, v in reversed(res) if k == cmd), None)


def _cmd(c: str, **p) -> dict:
    return {"command": c, "params": p}


def _pairs(track) -> list[tuple[str, str]]:
    if not track:
        return []
    items = [track] if isinstance(track, dict) else list(track)
    out = []
    for t in items:
        if not isinstance(t, dict) or not t.get("from"):
            raise RuntimeError("track 은 {\"from\": \"원래 글\", \"to\": \"바뀐 글\"} 또는 그 목록입니다")
        out.append((str(t["from"]), str(t.get("to") or "")))
    return out


def _comments(cs) -> list[tuple[str, str]]:
    out = []
    for c in cs or []:
        if not isinstance(c, dict) or not c.get("at") or not c.get("text"):
            raise RuntimeError("comments 는 [{\"at\": \"문장\", \"text\": \"메모\"}, …] 입니다")
        out.append((str(c["at"]), str(c["text"])))
    return out


def _pages(f: Path, work: Path) -> int:
    try:
        return int(json.loads(_wc(["info", f], work)).get("pages") or 1)
    except (ValueError, AttributeError):
        return 1


# ---------------------------------------------------------------- 그림 다듬기 · 재기
def _arr(png: Path):
    import numpy as np
    from PIL import Image
    with Image.open(png) as im:
        return np.asarray(im.convert("RGB")).astype(np.int16)


def content_bottom(png: Path) -> float:
    """글이 끝나는 높이(0~1) — 흰 바탕이 아닌 마지막 줄"""
    a = _arr(png)
    rows = (a.min(axis=2) < 235).any(axis=1).nonzero()[0]
    return float(rows[-1] + 1) / a.shape[0] if len(rows) else 0.0


def seal_seams(png: Path, rgb: tuple) -> int:
    """형광펜 글자 경계마다 생기는 1px 밝은 세로 이음선(배율 3에서 보임)을 형광펜 색으로 메운다.
    좌우가 모두 형광펜 색이고 자신은 형광펜과 흰색 사이(더 밝은 섞임)인 픽셀만 — 글자 잉크(더 어두움)는 건드리지 않는다"""
    import numpy as np
    from PIL import Image
    a = _arr(png)
    c = np.array(rgb, dtype=np.int16)
    hit = (np.abs(a - c).max(axis=2) <= 6)
    left, right = np.zeros_like(hit), np.zeros_like(hit)
    left[:, 1:], right[:, :-1] = hit[:, :-1], hit[:, 1:]
    lighter = (a >= c - 2).all(axis=2) & ~hit
    fix = left & right & lighter
    n = int(fix.sum())
    if n:
        a[fix] = c
        Image.fromarray(a.astype("uint8")).save(png)
    return n


def highlight_boxes(png: Path, rgb: tuple) -> list[list[int]]:
    """형광펜 색 픽셀 → 줄마다 [x, y, w, h](px)"""
    import numpy as np
    a = _arr(png)
    hit = (np.abs(a - np.array(rgb, dtype=np.int16)).max(axis=2) <= 24)
    rows = hit.sum(axis=1) >= 6
    boxes, y = [], 0
    H = hit.shape[0]
    while y < H:
        if not rows[y]:
            y += 1
            continue
        y0 = y
        while y < H and rows[y]:
            y += 1
        if y - y0 >= 6:                           # 6px 보다 얇은 건 밑줄 · 잡음
            cols = hit[y0:y].any(axis=0).nonzero()[0]
            boxes.append([int(cols[0]), y0, int(cols[-1] - cols[0] + 1), y - y0])
    return boxes


# ---------------------------------------------------------------- 어댑터
def document(m: dict, out: Path, work: Path) -> dict:
    """WordCraft: 문서(원문 그대로) → 9:16 쪽 → 형광펜 · 변경 추적 · 메모 → PNG"""
    from ..materials import _abs, ROOT
    mid = m["id"]
    work.mkdir(parents=True, exist_ok=True)
    author = str(m.get("author") or "편집자")
    track = _pairs(m.get("track"))
    notes = _comments(m.get("comments"))
    hls = [str(h) for h in ([m["highlight"]] if isinstance(m.get("highlight"), str) else (m.get("highlight") or []))]
    color = m.get("color") or "yellow"
    if color not in HL_RGB:
        raise RuntimeError(f"형광펜 색은 {' · '.join(HL_RGB)} 중 하나입니다")
    pw, ph = PAGE_MARKUP if notes else PAGE
    layout = [_cmd("layout.size", width=pw, height=ph), _cmd("layout.margins", **MARGINS)]
    base = work / f"{mid}.base.docx"

    # 1. 바탕 문서
    if m.get("src"):
        src = _abs(m["src"])
        if not src.exists():
            raise RuntimeError(f"문서가 없습니다: {m['src']}")
        if src.suffix.lower() == ".txt":
            body = src.read_text("utf-8", errors="replace").strip()
            _script(work, f"{mid}.base.json", layout + [_cmd("text.insert", text=body, paragraphs=True)], save=[base])
        else:
            first = src
            if src.suffix.lower() not in (".docx", ".dotx"):
                first = work / f"{mid}.src.docx"   # md · odt · rtf · html → docx
                _wc(["convert", src, first], work)
            _script(work, f"{mid}.base.json", layout, file=first, save=[base])
    elif m.get("text") or m.get("title"):
        cmds = list(layout)
        if m.get("title"):
            cmds += [_cmd("styles.apply", style="Heading 1"), _cmd("text.insert", text=str(m["title"])), _cmd("text.newParagraph"),
                     _cmd("styles.apply", style="Normal")]
        if m.get("text"):
            cmds.append(_cmd("text.insert", text=str(m["text"]).strip(), paragraphs=True))
        _script(work, f"{mid}.base.json", cmds, save=[base])
    else:
        raise RuntimeError("document 재료에는 src(문서 경로) 또는 text(본문)가 필요합니다")

    # 2. 변경 추적: 고친 판 → 비교
    cmds, changes = [], 0
    if track:
        rev = work / f"{mid}.rev.docx"
        res = _script(work, f"{mid}.rev.json", [_cmd("edit.replaceAll", text=a, **{"with": b}) for a, b in track], file=base, save=[rev])
        done = [v for k, v in res if k == "edit.replaceAll"]
        for (a, _b), r in zip(track, done):
            if not isinstance(r, dict) or not r.get("replaced"):
                raise RuntimeError(f"track: 문서에서 바꿀 글 '{a}' 이(가) 없습니다(원문과 글자가 같아야 합니다)")
        cmds.append(_cmd("review.compare", path=str(rev), formatting=False, author=author))
    # 3. 형광펜 · 메모
    for h in hls:
        cmds += [_cmd("select.text", text=h), _cmd("format.highlight", color=color)]
        if m.get("bold"):
            cmds.append(_cmd("format.bold", value=True))
    for at, txt in notes:
        cmds += [_cmd("select.text", text=at), _cmd("review.newComment", text=txt)]
    final = work / f"{mid}.docx"
    try:
        res = _script(work, f"{mid}.mark.json", cmds + [_cmd("review.changes")], file=base, save=[final], author=author)
    except RuntimeError as e:
        if "not found" in str(e):
            raise RuntimeError(f"문서에서 문장을 찾지 못했습니다(highlight · comments 는 원문과 글자가 같아야 합니다): {e}") from e
        raise
    changes = len([c for c in _last(res, "review.changes") or [] if isinstance(c, dict) and c.get("kind") in ("insert", "delete")])
    if track and not changes:
        # 비교가 변경을 못 만들었다 → 변경 추적을 켜고 바로 바꾼다(새 글이 먼저, 지운 글이 뒤에 붙는다)
        fb = [_cmd("review.trackChanges", value=True)] + [_cmd("edit.replaceAll", text=a, **{"with": b}) for a, b in track] + \
             [_cmd("review.trackChanges", value=False)] + cmds[1:]
        res = _script(work, f"{mid}.mark.json", fb + [_cmd("review.changes")], file=base, save=[final], author=author)
        changes = len([c for c in _last(res, "review.changes") or [] if isinstance(c, dict) and c.get("kind") in ("insert", "delete")])

    # 4. 글자 크기
    pages0 = _pages(final, work)
    scale = 1080 / (pw + 216) if notes else 1080 / pw
    probe = work / f"{mid}.probe.png"

    def shot(doc: Path, png: Path, page: int = 1):
        _script(work, f"{mid}.shot.json", [_cmd("file.exportPng", path=str(png), page=page, scale=scale, markup=bool(notes))], file=doc)

    fs = m.get("font_scale", "auto")
    chosen = final
    if fs == "auto" and pages0 == 1:
        best = 0
        for p in FIT_STEPS[1:]:
            cand = work / f"{mid}.fit.docx"
            _script(work, f"{mid}.fit.json", [_cmd("design.scaleFontSizes", percent=p)], file=final, save=[cand])
            if _pages(cand, work) > 1:
                break
            shot(cand, probe)
            if content_bottom(probe) > FILL:
                break
            best = p
            shutil.copyfile(cand, work / f"{mid}.best.docx")
        if best:
            shutil.move(str(work / f"{mid}.best.docx"), final)
        fs = best
        (work / f"{mid}.fit.docx").unlink(missing_ok=True)
    else:
        fs = 30 if fs == "auto" else float(fs)
        if fs:
            _script(work, f"{mid}.fit.json", [_cmd("design.scaleFontSizes", percent=fs)], file=final, save=[final])
    probe.unlink(missing_ok=True)

    # 5. 렌더 — 쪽 고르기(형광펜 > 변경 표시가 있는 첫 쪽)
    pages = _pages(chosen, work)
    rgb = HL_RGB[color]
    page = int(m.get("page") or 0)
    if page:
        if page > pages:
            raise RuntimeError(f"문서는 {pages}쪽입니다(page {page})")
        shot(chosen, out, page)
    else:
        pick = None
        for p in range(1, min(pages, 40) + 1):
            shot(chosen, out, p)
            if not hls or highlight_boxes(out, rgb):
                pick = p
                break
        if pick is None:
            pick = 1
            shot(chosen, out, 1)
        page = pick
    if hls:
        seal_seams(out, rgb)
    boxes = highlight_boxes(out, rgb) if hls else []
    for f in work.glob(f"{mid}.*.json"):
        f.unlink(missing_ok=True)
    for f in (base, work / f"{mid}.rev.docx", work / f"{mid}.src.docx"):
        f.unlink(missing_ok=True)

    from PIL import Image
    with Image.open(out) as im:
        size = list(im.size)
    info = {"app": "wordcraft", "as": "image", "page": page, "pages": pages, "size": size, "font_scale": fs,
            "changes": changes, "comments": len(notes), "highlighted": bool(boxes)}
    if boxes:
        x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
        info["highlight"] = boxes
        info["focus"] = [x0, y0, max(b[0] + b[2] for b in boxes) - x0, max(b[1] + b[3] for b in boxes) - y0]
    try:
        info["editable"] = str(final.relative_to(ROOT))
    except ValueError:
        info["editable"] = final.name
    return info


ADAPTERS = {"document": document}
