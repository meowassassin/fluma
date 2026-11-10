#!/usr/bin/env python3
"""
검사층: 콘티 JSON을 코드로 검사한다. LLM 없음, 0원, 즉시.
실패는 (코드, 장면 인덱스 또는 None, 메시지) 로 돌려주고, 생성층은 실패한 칸만 다시 만든다.

규칙 번호는 engine/spec/rules/rulebook.md 4절과 같다.
"""
import difflib
import hashlib
import json
import math
import re
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
FINAL = "--final" in sys.argv   # 렌더 직전 검사: 단계와 상관없이 화면 구성이 있어야 한다
TOKENS = json.loads((ROOT / "engine" / "spec" / "tokens" / "default.json").read_text(encoding="utf-8"))
LIM = TOKENS["limits"]
# L14: 실측 음성이 장면보다 이 배수 넘게 길면 실패. assemble_audio 는 최대 1.25배까지 빠르게 하고 그 뒤는 자르므로,
#      1.15배를 넘으면 말이 급하게 들리거나 끝이 잘린다 (2026-10-27 회전초밥 광고에서 CTA 잘림 확인).
AUDIO_FIT_MAX = 1.15
BANNED = ["충격", "경악", "미쳤다", "역대급", "꼭 보세요"]

try:
    import jsonschema
    SCHEMA = json.loads((ROOT / "engine" / "spec" / "schema" / "storyboard.schema.json").read_text(encoding="utf-8"))
except ImportError:
    jsonschema = None
    SCHEMA = None



def syllables(text: str) -> int:
    """말 속도 계산용 음절 수. 한글 · 한자 · 가나는 글자 하나가 한 음절, 라틴 문자 단어는 모음 덩어리로 센다
    (영어 나레이션을 글자 수로 세면 3~4배 부풀어 L04 가 늘 실패했다, 2026-11-02). 숫자는 자리마다 한 음절로 어림"""
    n = len(re.findall(r"[가-힣\u3040-\u30ff\u4e00-\u9fff]", text)) + len(re.findall(r"[0-9]", text))
    for w in re.findall(r"[A-Za-z']+", text):
        w = w.lower().rstrip("'s")
        g = len(re.findall(r"[aeiouy]+", w)) - (1 if w.endswith("e") and not w.endswith(("le", "ee")) and len(w) > 2 else 0)
        n += max(1, g)
    return n


def _keywords(text: str):
    # 2글자 이상 한글/영문 토큰
    return {t for t in re.findall(r"[가-힣A-Za-z0-9]{2,}", text)}


def _element_meta(rec: dict) -> dict:
    src = (rec.get("spec") or {}).get("src")
    if not src:
        return {}
    try:
        return json.loads((ROOT / src / "meta.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def screen_changes(rec: dict) -> int:
    """이 재료 안에서 화면이 바뀌는 횟수 — 웹 녹화는 상태 화면 수 + 실제 녹화 구간 3초마다 한 번(줄이 쏟아지는 터미널 · 말풍선이 올라오는 대화창)"""
    if rec.get("layers") and rec.get("type") in ("overlay", "diagram"):
        return len(rec["layers"])     # 주석 · 도식 항목이 낱말마다 하나씩 나온다 — 나올 때마다 화면이 바뀐다
    if rec.get("type") != "web":
        return 1
    meta = _element_meta(rec)
    n = len(meta.get("states") or []) or 1
    import math
    n += sum(math.ceil(float(a.get("sec") or 0) / 3) for a in meta.get("actions") or [] if a.get("do") == "record")
    return max(1, n - 1)          # 첫 상태는 등장 자체


def material_kind(rec: dict) -> str:
    """재료 종류(시청자가 보는 화면의 종류): 문서 캡처 · 그래픽 · 그림/사진 · 화면/영상"""
    t = rec.get("type")
    if t in ("chart", "text", "stat", "icon", "diagram", "info_card", "template_card", "thumbnail"):
        return "그래픽"
    if t == "model3d":
        return "3D 제품"
    if t == "drawing":
        return "도면"
    if t == "document":
        return "문서 캡처"
    if t == "photo_grade":
        return "그림 · 사진"
    if t == "ui_mock":
        # 실제 캡처를 폰 · 브라우저 틀에 넣은 것은 앱 화면, 설명으로 그린 가상 화면(mock)은 그래픽
        return "그래픽" if rec.get("mock") or (rec.get("spec") or {}).get("mock") else "앱 화면"
    if t == "meme":
        return "짤 · 반응"
    if t == "web":
        # 웹 녹화 요소(webrec · termrec)는 무엇을 찍었는지로 나눈다 — 실제 실행 화면 · 실제 사이트 · 직접 만든 화면은 시청자에게 다른 화면이다
        meta = _element_meta(rec)
        if meta.get("terminal"):
            return "실행 화면(터미널)"
        if any(str(u).startswith("http") for u in meta.get("sources") or []):
            return "웹 화면"
        return "앱 화면"
    if t == "stock":
        return "실사 영상(스톡)"
    if t in ("screen", "video"):
        return "화면 · 영상"
    if t == "doc_quote":
        return "문서 캡처"
    if t == "illustration":
        return "그림 · 사진"
    ocr = rec.get("ocr") or []
    chars = sum(len(o.get("text") or "") for o in ocr)
    area = sum((o.get("box") or [0, 0, 0, 0])[2] * (o.get("box") or [0, 0, 0, 0])[3] for o in ocr)
    if len(ocr) >= 4 and (chars >= 60 or area >= 0.12):
        return "문서 캡처"
    return "그림 · 사진" if t in ("image", "photo") else "그래픽"


def material_checks(sb: dict) -> list:
    """L33 같은 재료 반복 · L34 글자 캡처 위주 · L35 재료 종류 부족 · T35 외국어 캡처 — 재료 단계의 기록(글자 인식 포함)으로"""
    sid = sb.get("id", "")
    base = ROOT / "data" / "compositions" / sid / "craft" / "materials"
    if not sid or not base.exists():
        return []
    recs = []
    for n, sc in enumerate(sb.get("scenes") or [], 1):
        for k, m in enumerate(sc.get("materials") or []):
            f = base / f"s{n:02d}" / f"{m.get('id') or f'm{k + 1}'}.json"
            if f.exists():
                try:
                    r = json.loads(f.read_text("utf-8"))
                    if isinstance(r, dict):
                        recs.append(r)
                except ValueError:
                    pass
    out = []
    # L36 사용자 녹화 대기: 자동으로 못 찍는 화면 — 사용자에게 부탁하고(무엇을 · 몇 초 · 어디에 올리는지) 받은 뒤 다시 렌더
    for r in recs:
        if r.get("missing"):
            out.append(("L36", r.get("scene"), f"사용자 녹화가 필요: {r.get('ask')} → 편집기에 파일을 올려 달라고 부탁(이름에 '{r.get('id')}' 포함). 받기 전 초안은 이 재료 없이 렌더됨"))
    # 주석 오버레이는 대상 화면 위에 얹힐 뿐 새 화면이 아니다 — 종류 · 개수 · 전환 수에 세지 않는다
    notes = [r for r in recs if not r.get("missing") and r.get("type") == "overlay"]
    recs = [r for r in recs if not r.get("missing") and r.get("type") != "overlay"]
    # 일부 장면만 렌더한 기록으로 영상 전체를 판단하지 않는다(재료는 렌더가 만든다 — 전체 기록이 모자라면 다음 전체 렌더 뒤에 본다)
    planned = sum(1 for sc in sb.get("scenes") or [] for m in sc.get("materials") or [] if isinstance(m, dict) and m.get("type") not in ("text", "stat", "overlay"))
    built = sum(1 for r in recs if r.get("type") not in ("text", "stat"))
    if len(recs) < 2 or (planned and built < planned * 0.8):
        return out
    by_src: dict[str, set] = {}
    for r in recs:
        sp = r.get("spec") or {}
        src = sp.get("src") or sp.get("csv") or r.get("file")
        if src:
            by_src.setdefault(src, set()).add(r.get("scene"))
    for src, scs in by_src.items():
        if len(scs) >= 3:
            out.append(("L33", None, f"같은 재료가 {len(scs)}개 장면에 반복: {Path(src).name} (장면 {', '.join(str(x) for x in sorted(scs))}) — 장면마다 다른 화면으로"))
    kinds = [material_kind(r) for r in recs]
    docs = kinds.count("문서 캡처")
    if docs * 2 > len(kinds):
        out.append(("L34", None, f"재료 {len(kinds)}개 중 {docs}개가 글자 빽빽한 문서 캡처 — 세로 화면에서 안 읽힌다. 핵심 수치는 그래픽(chart)으로, 근거는 문장 하나만 짚는 doc_quote 로, 나머지는 실제 화면 · 사진 · 그림으로"))
    dur = sum(float(x.get("sec") or 0) for x in sb.get("scenes") or [])
    if dur >= 20 and len(set(kinds)) < 3:
        out.append(("L35", None, f"재료 종류가 {len(set(kinds))}가지({', '.join(sorted(set(kinds)))}) — 레퍼런스 쇼츠는 화면 종류를 섞는다. 문서 캡처(doc_quote · document) · 그래픽(stat · chart · diagram · info_card) · 그림/사진(photo · photo_grade) · 화면/영상(web · screen · ui_mock) · 3D 제품(model3d) · 도면(drawing) · 짤(meme) 중 3가지 이상"))
    # L37 재료 개수: 레퍼런스 설명 쇼츠는 10초에 4번 남짓 화면이 바뀐다 → 3초에 하나 이상(같은 파일은 한 번만 셈)
    seen_src: dict[str, int] = {}
    for r in recs + notes:            # 주석은 새 화면 종류는 아니지만 짚을 때마다 화면이 바뀐다
        key = (r.get("spec") or {}).get("src") or (r.get("spec") or {}).get("csv") or f"{r.get('scene')}/{r.get('id')}"
        seen_src[key] = max(seen_src.get(key, 0), screen_changes(r))
    uniq = sum(seen_src.values())          # 같은 파일은 한 번 · 녹화 재료는 그 안의 화면 전환 수만큼
    need = int(dur // 3)
    spoken = any((s.get("narration") or "").strip() for s in sb.get("scenes") or [])    # 문장마다 화면이 바뀌는 규칙 — 음악 주도 영상은 해당 없음
    if spoken and dur >= 15 and uniq < need:
        out.append(("L37", None, f"화면 전환 {uniq}번(서로 다른 재료 · 녹화 안의 전환 포함) / {dur:.0f}초 — {need}개 이상 필요(문장마다 하나: 짤 · 웹 녹화 · 아이콘 · 수치 카드 · 그림을 섞어서, cue 로 그 낱말에 등장)"))
    # T37 같은 종류가 네 번 연속(클립 모음 형식은 실사 클립이 이어지는 게 형식)
    run_k, run_n = None, 0
    for k in (kinds if sb.get("format") not in ("ranking", "clip") else []):
        run_n = run_n + 1 if k == run_k else 1
        run_k = k
        if run_n == 4:
            out.append(("T37", None, f"'{k}' 가 네 번 연속 — 사이에 다른 종류(짤 · 그래픽 · 화면)를 끼우기"))
            break
    if sb.get("language", "ko") == "ko":
        def latin_heavy(r):
            txt = "".join(o.get("text") or "" for o in (r.get("ocr") or []))
            lat, han = len(re.findall(r"[A-Za-z]", txt)), len(re.findall(r"[가-힣]", txt))
            return len(txt) >= 30 and lat > han * 3
        en = sum(1 for r in recs if latin_heavy(r))
        if en * 3 >= len(recs):
            out.append(("T35", None, f"영어 글자가 대부분인 캡처가 {en}개 — 한국어 시청자에게 안 읽힌다. 핵심 수치는 한국어 그래픽으로 다시 그리기"))
    return out


IMAGE_LIKE = {"chart", "doc_quote", "illustration", "icon", "photo", "screen", "web", "video", "stock", "meme", "image",
              "photo_grade", "document", "diagram", "ui_mock", "info_card", "template_card", "model3d", "drawing", "live"}   # 그림 · 영상 파일이 생기는 재료(주석을 얹을 수 있음)


def material_spec_checks(sb: dict) -> list:
    """L39 재료 칸: 재료 단계(앱 어댑터)가 실패할 콘티를 렌더 전에 잡는다 — 필수 칸 · 같은 장면 참조 순서 · 가상 화면 표시 · 파일 존재"""
    out = []
    for i, sc in enumerate(sb.get("scenes") or []):
        mats = [m for m in sc.get("materials") or [] if isinstance(m, dict)]
        seen: dict[str, str] = {}
        for k, m in enumerate(mats):
            mid, t = str(m.get("id") or f"m{k + 1}"), m.get("type")
            tag = f"재료 {mid}({t})"
            if "." in mid or "/" in mid:
                out.append(("L39", i, f"{tag}: id 에 '.' · '/' 를 쓰지 않는다(재료 폴더 정리가 파일 이름의 첫 '.' 앞을 id 로 본다)"))
            if mid in seen:
                out.append(("L39", i, f"{tag}: 같은 장면에 id 가 겹침"))
            if m.get("gen"):                   # 생성(실사 영상 · 그림) 경로는 없앴다(2026-11-09) — 완전 로컬: 퍼온 클립 · 스톡 · 사진 · 화면 녹화 · Craft 그림으로
                out.append(("L39", i, f"{tag}: 생성 재료(gen)는 쓰지 않는다 — 퍼온 클립(clip.py) · 스톡(stock) · 사진 · 화면 녹화(web) · Craft 그림(illustration · figure)으로 바꾼다"))
            def need(*keys, what=""):
                if not any(m.get(x) not in (None, "", [], {}) for x in keys):
                    out.append(("L39", i, f"{tag}: {' 또는 '.join(keys)} 가 필요{(' — ' + what) if what else ''}"))
            def exists(key):
                v = m.get(key)
                if isinstance(v, str) and v and not m.get("ask") and not (Path(v) if Path(v).is_absolute() else ROOT / v).exists():
                    out.append(("L39", i, f"{tag}: {key} 파일이 없음 — {v}"))
            if t == "overlay":
                tg = str(m.get("target") or "")
                if not tg:
                    out.append(("L39", i, f"{tag}: target(주석을 얹을 같은 장면 재료 id)이 필요"))
                elif tg not in seen:
                    later = any(str(x.get("id") or "") == tg for x in mats[k + 1:])
                    out.append(("L39", i, f"{tag}: 대상 {tg} 가 " + ("overlay 보다 뒤에 있음 — materials 에서 대상을 앞으로(대상 기록을 읽어 그린다)" if later else "이 장면에 없음")))
                elif seen[tg] not in IMAGE_LIKE:
                    out.append(("L39", i, f"{tag}: 대상 {tg}({seen[tg]})는 그림 · 화면이 아니라 주석을 얹을 수 없음"))
                need("marks", what="[{kind: box|arrow|label, box:[x,y,w,h], text, cue}]")
            elif t == "doc_quote":
                need("pdf"); need("find"); exists("pdf")
            elif t in ("photo", "photo_grade"):
                need("src"); exists("src")
            elif t == "document":
                need("src", "text", what="원문 파일 또는 본문"); exists("src")
            elif t == "diagram":
                need("kind", what="steps · compare · cycle · hierarchy · pyramid · timeline · list")
                if len(m.get("items") or []) < 2:
                    out.append(("L39", i, f"{tag}: items 가 2개 이상 필요"))
            elif t == "ui_mock":
                need("src", "screen", what="실제 캡처(src) 또는 가상 화면 설명(screen + mock:true)"); exists("src")
                if m.get("screen") and not m.get("src") and not m.get("mock"):
                    out.append(("L39", i, f"{tag}: 설명으로 그린 가상 화면이면 mock: true 를 적는다(실제 서비스 설명에는 실제 캡처)"))
            elif t == "info_card":
                need("title", "rows", "csv"); exists("csv")
            elif t == "template_card":
                need("csv", "values"); exists("csv"); exists("template")
            elif t == "live":
                need("src", what="실사 · 생성 영상"); exists("src")
                if not (m.get("items") or m.get("cuts")):
                    out.append(("L39", i, f"{tag}: live 는 items 또는 cuts 가 있어야 함 — 없으면 video 재료로"))
                for it in m.get("items") or []:
                    k = it.get("kind")
                    if k == "model3d" and not (it.get("script") and it.get("at")):
                        out.append(("L39", i, f"{tag}: {it.get('id')} — model3d 는 script · at(바닥 픽셀)이 필요"))
                    elif k in ("text", "image") and not it.get("follow"):
                        out.append(("L39", i, f"{tag}: {it.get('id')} — {k} 는 follow 가 필요(at 또는 cut)"))
                    elif k == "text" and it.get("follow", {}).get("cut") and it["follow"]["cut"] not in (m.get("cuts") or {}):
                        out.append(("L39", i, f"{tag}: {it.get('id')} — cuts 에 {it['follow']['cut']} 이 없음"))
                    if it.get("behind") and it["behind"] not in (m.get("cuts") or {}):
                        out.append(("L39", i, f"{tag}: {it.get('id')} — behind {it['behind']} 이 cuts 에 없음"))
                for n_, c_ in (m.get("cuts") or {}).items():
                    if not any(x.get("kind", "fg") == "fg" for x in c_.get("strokes") or []):
                        out.append(("L39", i, f"{tag}: cuts.{n_} — fg 획이 필요"))
            elif t == "model3d":
                ids = [x.get("id") for x in sc.get("materials") or []]
                for k, v in (m.get("uses") or {}).items():
                    if v not in ids[:ids.index(m.get("id"))] if m.get("id") in ids else True:
                        out.append(("L39", i, f"{tag}: uses '{k}' 의 재료 {v} 가 같은 장면 앞쪽에 없습니다"))
                need("script", "shape", "commands", "src", what="Blender 스크립트 · 내장 형태 · SolidCraft 명령 · STEP/STL 원본"); exists("src"); exists("script")
                if m.get("turntable") and m.get("exploded"):
                    out.append(("L39", i, f"{tag}: turntable 과 exploded 는 하나만(재료 하나 = 영상 하나)"))
            elif t == "drawing":
                need("src", "cmd", "commands", "model", what="DXF · CADCraft 명령 · 3D 모형"); exists("src")
                mo = m.get("model")
                if isinstance(mo, str) and mo and seen.get(mo) != "model3d":
                    out.append(("L39", i, f"{tag}: model {mo} 은 이 장면에서 도면보다 앞선 model3d 재료여야 함(다른 장면이면 model 에 형태 칸을 다시 쓴다)"))
            elif t == "video" and m.get("in") is not None and m.get("out") is not None and float(m["out"]) <= float(m["in"]):
                out.append(("L39", i, f"{tag}: out 이 in 보다 뒤여야 함"))
            if m.get("method"):                        # 같은 재료를 다른 앱으로(materials.methods)
                try:
                    import sys as _s
                    _s.path.insert(0, str(ROOT / "engine"))
                    from craft.materials import methods, plugins
                    ad, _ = plugins()
                    ok_apps = [a for a in methods().get(str(t), []) if a == (methods().get(str(t)) or [None])[0] or f"{t}@{a}" in ad]
                    if m["method"] not in ok_apps:
                        out.append(("L39", i, f"{tag}: method '{m['method']}' 로는 {t} 를 만들 수 없음 — 가능: {', '.join(ok_apps) or '없음'}"))
                except Exception:  # noqa: BLE001
                    pass
            if t == "craft" or m.get("recipe"):
                try:
                    import sys as _s
                    _s.path.insert(0, str(ROOT / "engine"))
                    from craft.materials import expand_recipe
                    from craft.adapters.craft_script import validate
                    validate(expand_recipe(dict(m)))
                except RuntimeError as e:
                    out.append(("L39", i, f"{tag}: {e}"))
                except Exception:  # noqa: BLE001  (앱 미설치 등 — 렌더 때 다시 본다)
                    pass
            seen[mid] = str(t)
    return out


def lint(sb: dict, recent_titles=None) -> list:
    fails = []

    # T00 템플릿 콘티 ({{치환자}} 포함) 는 값을 채운 뒤 검사한다 (daily 형식 등)
    if "{{" in json.dumps(sb, ensure_ascii=False):
        return [("T00", None, "템플릿 콘티 — fill_template.py 로 값을 채운 뒤 검사")]

    fmt = sb.get("format")
    music_led = fmt == "emotional"   # 감성은 음악 주도: 나레이션이 짧거나 없어도 됨

    # L01 스키마
    if jsonschema and SCHEMA:
        try:
            jsonschema.validate(sb, SCHEMA)
        except jsonschema.ValidationError as e:
            path = "/".join(str(p) for p in e.absolute_path)
            idx = e.absolute_path[1] if len(e.absolute_path) > 1 and e.absolute_path[0] == "scenes" else None
            fails.append(("L01", idx, f"스키마: {path}: {e.message}"))

    scenes = sb.get("scenes", [])

    # L02 길이 합계
    total = sum(s.get("sec", 0) for s in scenes)
    if abs(total - sb.get("duration_sec", 0)) > 1:
        fails.append(("L02", None, f"장면 합계 {total}s != duration {sb.get('duration_sec')}s"))

    lo, hi = LIM["narration_chars_per_sec"]
    if (sb.get("language") or "ko") != "ko":   # 음절 속도는 언어마다 다르다 — 영어 · 중국어 나레이션은 초당 2.5~5.5음절
        lo, hi = LIM.get("narration_syllables_per_sec_other", [2.5, 5.5])
    measured = measured_scenes(sb)
    numbers = 0
    captions_seen = {}
    for i, s in enumerate(scenes):
        cap = s.get("caption", "")
        nar = s.get("narration", "")
        sec = s.get("sec", 1) or 1

        # L03 자막 길이·줄 수
        if len(cap.replace("\n", "")) > LIM["caption_max_chars"] or cap.count("\n") + 1 > LIM["caption_max_lines"]:
            fails.append(("L03", i, f"자막 {len(cap)}자/{cap.count(chr(10))+1}줄 초과"))

        # L04 말 속도 (실측 음성이 있으면 L14 가 대신 본다 — 글자 수 추정보다 정확)
        n_syl = syllables(nar)
        if i in measured:
            pass
        else:
            cps = n_syl / sec
            lo_eff = 0 if (music_led or not nar) else lo     # 감성·무음 장면은 하한 없음, 상한만
            if not (lo_eff <= cps <= hi):
                fails.append(("L04", i, f"음성 {n_syl}자/{sec}s = {cps:.1f}자/초 (허용 {lo_eff}~{hi}, 공백 제외)"))

        # L05 훅 길이 — 레퍼런스 스타일 카드가 있으면 그 영상의 첫 컷 길이(+0.5초)까지 허용
        hook_max = max(LIM["hook_sec_max"], ref_first_shot(sb) + 0.5)
        if s.get("role") == "hook" and sec > hook_max:
            # 시청자는 3초 안에 '화면 글자'로 무엇인지 안다 — 훅 제목이 뜨면 나레이션은 4.6초까지 권고로만
            # (2026-11-03: 3초를 맞추려 문장을 자르고 1.35배속 → '너무 빠르다')
            titled = any(isinstance(e, dict) and re.search(r"훅 제목|제목", str(e.get("name", ""))) for e in (s.get("elements") or []))
            if titled and sec <= hook_max + 1.6:
                fails.append(("T05", i, f"hook {sec}s > {hook_max:g}s — 훅 제목이 3초 안에 뜨면 괜찮음(나레이션을 자르거나 배속을 올리지 말 것)"))
            else:
                fails.append(("L05", i, f"hook {sec}s > {hook_max:g}s"))

        # L06 금칙어
        for b in BANNED:
            if b in cap or b in nar:
                fails.append(("L06", i, f"금칙어 '{b}'"))

        # L07 숫자 장면 수
        if s.get("visual", {}).get("kind") == "number":
            numbers += 1

        # L09 자막 반복
        key = cap.strip()
        if key and key in captions_seen:
            fails.append(("L09", i, f"자막이 장면 {captions_seen[key]}과 같음"))
        captions_seen.setdefault(key, i)

    # L11 구체성: hook·outro 외 장면에 숫자 또는 고유명사(영문 대문자 시작 / 한글 2자+ 이름)가 하나 이상
    for i, s in enumerate(scenes):
        if s.get("role") in ("hook", "outro", "cta", "mood"):   # mood(감성)는 숫자 없는 게 정상
            continue
        vis = s.get("visual", {}) or {}
        blob = " ".join([
            s.get("caption", ""), s.get("narration", ""),
            str(vis.get("primary", "")), str(vis.get("secondary", "")),
            " ".join(vis.get("items", []) or []), str(vis.get("before", "")), str(vis.get("after", "")),
        ])
        has_number = bool(re.search(r"\d", blob))
        has_name = bool(re.search(r"\b[A-Z][A-Za-z0-9]{2,}\b", blob))  # ElevenLabs, GA4 ...
        has_brand = bool(sb.get("brand")) and sb.get("brand") in blob
        if not (has_number or has_name or has_brand or vis.get("kind") in ("screenshot", "code", "chart", "footage", "still", "price_tag")):
            fails.append(("L11", i, "구체적 정보 없음 (숫자·이름·화면 중 하나 필요)"))

    # L12 증거: 툴·현장 형식(compare, fix, ad, emotional, daily)의 본문 장면은 실제 장면이 있어야 한다
    #      (screenshot/still/footage/price_tag/audio_demo). 분석(2026-10-26): 패널만 있는 영상은 세 분야 모두에서 졌다.
    EVIDENCE = {"screenshot", "still", "footage", "price_tag", "audio_demo", "code", "chart"}
    if sb.get("format") in ("compare", "fix", "ad", "emotional", "daily"):
        body = [(i, s) for i, s in enumerate(scenes) if s.get("role") not in ("hook", "outro", "cta")]
        missing = [i for i, s in body if (s.get("visual", {}) or {}).get("kind") not in EVIDENCE]
        # 본문의 절반 이상이 증거 장면이어야 통과 (전부 강제하면 verdict 같은 정리 장면이 막힘)
        if body and len(missing) > len(body) // 2:
            fails.append(("L12", missing[0], f"증거 장면 부족: 본문 {len(body)}개 중 {len(body)-len(missing)}개만 실제 화면"))

    # L13 감성 형식은 숫자 장면 1개 이하, 자막 14자 이하 (분석: 감성은 짧은 문장이 이김)
    if sb.get("format") == "emotional":
        for i, s in enumerate(scenes):
            if s.get("role") == "mood" and len(s.get("caption", "").replace("\n", "")) > 14:
                fails.append(("L13", i, f"감성 자막 {len(s.get('caption',''))}자 > 14자"))

    if numbers > LIM["numbers_per_video_max"]:
        fails.append(("L07", None, f"숫자 장면 {numbers}개 > {LIM['numbers_per_video_max']}"))

    # L08 루프: outro가 hook의 핵심어를 하나 이상 담는가
    hooks = [s for s in scenes if s.get("role") == "hook"]
    outros = [s for s in scenes if s.get("role") in ("outro", "cta")]
    if hooks and outros:
        hk = _keywords(hooks[0].get("caption", "") + " " + hooks[0].get("narration", ""))
        ok = _keywords(outros[0].get("caption", "") + " " + outros[0].get("narration", ""))
        if not (hk & ok):
            fails.append(("L08", len(scenes) - 1, "outro가 hook과 이어지지 않음 (공통 핵심어 없음)"))

    # L10 최근 제목과 중복
    for t in recent_titles or []:
        try:                                   # '찾기 · 임베딩' 모델이 있으면 뜻으로도(낱말만 바꾼 같은 제목)
            import embed
            emb = embed.similar(sb.get("title", ""), t)
        except Exception:  # noqa: BLE001
            emb = None
        if difflib.SequenceMatcher(None, sb.get("title", ""), t).ratio() >= 0.8 or (emb is not None and emb >= 0.92):
            fails.append(("L10", None, f"최근 제목과 유사: '{t}'"))
            break

    # L14 실측 음성 길이 (data/audio/<id>.timing.json 이 있고, 그 음성이 지금 나레이션으로 만든 것일 때만)
    fails += audio_fit(sb)

    # L32 · T32~T34 템포: 마지막 렌더를 잰 결과(engine/checks/tempo_check.py, render.py 가 남김). 피드에서 넘기지 않게 하는 기본기
    tp = ROOT / "data" / "workspace" / "render" / sb.get("id", "") / "tempo.json"
    if sb.get("id") and tp.exists():
        try:
            import tempo_check
            for code, msg in tempo_check.problems(json.loads(tp.read_text("utf-8")), any(str(x.get("narration") or "").strip() for x in sb.get("scenes") or []), sb):
                fails.append((code, None, f"[마지막 렌더] {msg}"))
        except (ValueError, OSError, ImportError):
            pass

    # L33 ~ L35 · T35 재료(시청자 기준): 재료 단계가 남긴 기록(data/compositions/<id>/craft/materials/sNN/*.json, 글자 인식 포함)으로 본다.
    #     재료를 만들기 전이면 건너뛴다. (2026-11-03: 영어 문서 캡처 9장 · 같은 그래프 3번 → '슬라이드 넘기기' 같은 영상)
    fails += material_checks(sb)
    # L39 재료 칸(필수 칸 · overlay 대상 · drawing 모형 · 가상 화면 표시) — 렌더 전에 콘티만으로
    fails += material_spec_checks(sb)
    # L53 가상 앱 화면(ui_mock · mock)은 Astryx 장면(ui 칸)으로 — 손으로 그린 표 · 버튼은 '진짜 앱' 느낌이 안 났다(2026-11-10)
    for i, sc in enumerate(sb.get("scenes") or [], 1):
        for m in sc.get("materials") or []:
            if m.get("type") == "ui_mock" and m.get("mock") and not m.get("ui") and not m.get("src"):
                fails.append(("L53", i, f"{m.get('id')}: 가상 앱 화면은 Astryx 장면으로 — ui: data/compositions/<id>/ui/<이름>.tsx (컴포넌트 문서: npm --prefix tools/ui-scenes run -s astryx -- component <이름>)"))
    # L50 화면 변화 간격 · L51 구절 길이 · L52 접속어 강의체 · T50 말 속도 — 레퍼런스 X-ray 수치와 견준다(engine/checks/refnorm.py)
    try:
        from refnorm import check as _refnorm
    except ImportError:
        from checks.refnorm import check as _refnorm
    fails += _refnorm(sb)
    # L41 감독 없음 — 나레이션이 없으면 강조(확대 · 멈춤)가 저절로 생기지 않는다. 화면 녹화 장면에 감독이 짚은 곳이 하나도 없으면 같은 구도의 같은 창이 이어진다(2026-11-09 git 영상: 슬롭)
    if not any(str(x.get("narration") or "").strip() for x in sb.get("scenes") or []):
        flat = []
        for i, sc in enumerate(sb.get("scenes") or []):
            mats = [m for m in sc.get("materials") or [] if isinstance(m, dict)]
            screens = [m for m in mats if m.get("type") in ("web", "screen")]
            directed = any(b.get("do") == "확대" for b in sc.get("beats") or [] if isinstance(b, dict)) or any(m.get("zoom") or m.get("focus") or m.get("highlight") for m in screens)
            if screens and not directed:
                flat.append(i + 1)
        if len(flat) >= 2:
            fails.append(("L41", None, f"나레이션 없는 영상인데 화면 장면 {', '.join(map(str, flat))} 에 감독이 짚은 곳이 없음 — 장면마다 보는 사람이 봐야 할 한 곳을 정해 "
                                       "재료 zoom([{t, box, dur}]) 또는 장면 beats [{\"do\": \"확대\", \"t\": 초}] 로 다가가고, 반전은 멈춤 · 소리로(director 스킬)"))
    # L38 스톡 영상 재료: 검색어(영어가 잘 찾힘)가 있어야 받는다 · 키가 없으면 미리 알린다(렌더 중에 멈추지 않게)
    stocks = [(i, m) for i, sc in enumerate(sb.get("scenes") or []) for m in (sc.get("materials") or []) if isinstance(m, dict) and m.get("type") == "stock"]
    for i, m in stocks:
        if not str(m.get("query") or "").strip():
            fails.append(("L38", i, f"스톡 영상 재료 {m.get('id')}: query(영어 검색어)가 없음 — 예: \"subway commute morning\""))
    if stocks:
        try:
            import apikeys
            if not (apikeys.get("PEXELS_API_KEY") or apikeys.get("PIXABAY_API_KEY")):
                fails.append(("L38", None, "스톡 영상 키가 없음 — 사용자에게 설정 → API 키에서 Pexels 또는 Pixabay 키(무료)를 넣어 달라고 부탁(채팅에 키를 붙이지 말라고)"))
        except ImportError:
            pass

    # L30 레퍼런스: 같은 주제 · 형식의 실제 쇼츠를 분석(engine/research/shorts_xray.py → data/public/trends/xray/<id>/xray.json)하고 콘티 reference 에 건다.
    #     조사 없이 '그냥 만들면' 대사 · 리듬 · 화면이 어색하다(2026-11-03 사용자 평가). 사용자가 레퍼런스 없이 만들라고 했을 때만 reference_skip 에 그 말을 적는다
    refs = [r for r in (sb.get("reference") or []) if isinstance(r, str)]
    analyzed = [r for r in refs if (ROOT / "data" / "public" / "trends" / "xray" / r / "xray.json").exists()]
    #     한두 편만 보면 그 영상의 버릇을 따라 한다 → 최소 MIN_REFS 편(2026-11-09 사용자: "분석 개수가 너무 적다"). 그 분야에 쇼츠가 정말 적으면 reference_skip 에 이유
    MIN_REFS = 3
    if len(analyzed) < MIN_REFS and not str(sb.get("reference_skip") or "").strip():
        missing = [r for r in refs if r not in analyzed]
        fails.append(("L30", None, f"레퍼런스 분석 {len(analyzed)}편 — 최소 {MIN_REFS}편(3~5편 권장): trends 스킬로 같은 주제 · 형식 쇼츠를 찾고(브랜드면 trends.py channels 로 공식 채널을 골라 --channel 로) "
                      "shorts_xray.py · ref_channel.py 로 분해한 뒤 콘티 reference 에 영상 id 를 건다(말투 · 컷 길이 · 화면 종류를 거기서 가져온다)"
                      + (f" — {missing} 는 아직 X-ray 안 됨" if missing else "")))

    # L31 대사 자연스러움: 나레이션은 말이다 — 명사로 뚝 끊긴 문장(…쓴 말. / …의 별명.)과 존댓말 · 반말 섞임을 막는다
    ENDS = set("다요죠까네지야어아게고래군세요니데걸가나")
    polite = casual = 0
    for i, sc_ in enumerate(scenes):
        for sent in re.split(r"(?<=[.!?…])\s+", (sc_.get("narration") or "").strip()):
            core = re.sub(r"[\s.!?…,'\"’”)\]]+$", "", sent)
            if len(core) < 4 or not re.search(r"[가-힣]", core[-1:]) or sent.rstrip().endswith("!"):   # 외침(스팸, 스팸!)은 일부러
                continue
            if core[-1] not in ENDS:
                fails.append(("L31", i, f"말이 명사로 끊김: '…{core[-12:]}' — 말하듯 끝맺기(…였어요 · …였죠 · …래요)"))
            if re.search(r"(요|니다|니까|죠)$", core):
                polite += 1
            elif re.search(r"(다|야|어|아|지|네|군|래)$", core):
                casual += 1
    if polite and casual and min(polite, casual) >= 1 and not sb.get("tone_mix_ok"):
        fails.append(("L31", None, f"존댓말 {polite}문장 · 반말 {casual}문장이 섞임 — 레퍼런스 채널 말투 하나로(섞는 게 채널 스타일이면 tone_mix_ok: true)"))

    sid = sb.get("id", "")
    # T16 디자인 방향: 영상마다 다른 화면이 나오도록 engine/story/direct.py --write 로 정한다 (권고)
    if not sb.get("direction"):
        fails.append(("T16", None, "디자인 방향(direction) 없음: python3 engine/story/direct.py data/storyboards/<id>.json --write"))
    # T19 말투: 문장 끝 비율을 레퍼런스 채널(여러 편)과 견준다(권고). L21/T21/T22 구성: 화면 종류 · 농담 박자
    for code, msg in speech_tells(sb) + structure_tells(sb):
        fails.append((code, None, msg))
    # T27 배치 기준: 레퍼런스도 형식 프리셋도 없으면 손으로 정한 기본값(가운데 판 · 고정 자막)이 쓰인다 = AI 틀
    if not sb.get("preset") and not (sb.get("reference") or []):
        fails.append(("T27", None, "형식 프리셋 없음 — python3 engine/research/format_presets.py pick data/storyboards/<id>.json (사람이 편집한 실제 쇼츠의 배치 숫자)"))
    # T25/T26 재료: 장면 화면이 직접 그린 그래픽뿐이면 템플릿 티. 실제 화면은 정지 캡처 카드보다 조작 녹화(webrec · K.web)
    for code, msg in material_tells(sb):
        fails.append((code, None, msg))
    # L40 다듬기 기록(engine/craft/refine.py): 층 · 대상 · 근거 · 명령 id 가 맞아야 제작이 그 기록을 다시 적용할 수 있다
    try:
        from craft.refine import validate as _rv
        for msg in _rv(sb):
            fails.append(("L40", None, msg))
    except ImportError:
        pass

    return fails


FORMAL = ("습니다", "입니다", "합니다", "됩니다", "있습니다")
CASUAL = ("고요", "는데", "거든요", "대요", "네요", "어요", "아요", "예요", "에요", "죠", "잖아요", "더라고요")


def style_card_of(sb: dict) -> dict | None:
    for rid in sb.get("reference") or []:
        p = ROOT / "data" / "public" / "trends" / "xray" / str(rid) / "style" / "style.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return None


def channel_card_of(sb: dict) -> dict | None:
    """레퍼런스 스타일 카드에 달린 채널 카드(engine/research/ref_channel.py) — 여러 편에서 뽑은 말투 · 구조"""
    c = style_card_of(sb)
    cid = (c or {}).get("channel")
    p = ROOT / "data" / "public" / "trends" / "channels" / str(cid) / "channel.json" if cid else None
    return json.loads(p.read_text(encoding="utf-8")) if p and p.exists() else None


def _ending(sent: str) -> str:
    import ref_channel
    return ref_channel.ending_of(sent)


def speech_tells(sb: dict) -> list:
    """대본 말투를 레퍼런스와 견준다 — 모두 권고(T19). 표본이 작은 통계를 실패 조건으로 쓰면 한쪽 끝맺음으로 몰아 쓰게 된다(2026-11-02).
    채널 카드가 있으면 문장 끝 비율을 채널(여러 편)과 견주고, 없으면 단조로운 끝맺음만 본다"""
    sents = [x.strip() for sc in sb.get("scenes", []) for x in re.split(r"(?<=[.?!])\s+", (sc.get("narration") or "").strip()) if x.strip()]
    if len(sents) < 3:
        return []
    end = lambda x: re.sub(r"[.?!,\s]+$", "", x)
    lasts = [end(x)[-2:] for x in sents]
    same = max(lasts.count(l) for l in set(lasts)) / len(sents)
    out = []
    ch = channel_card_of(sb)
    if ch and ch.get("lang", "ko") == "ko" and (ch.get("tone") or {}).get("sentences", 0) >= 15:
        want = ch["tone"]["endings"]
        got = {}
        for x in sents:
            e = _ending(x); got[e] = got.get(e, 0) + 1 / len(sents)
        keys = set(want) | set(got)
        tv = sum(abs(want.get(k, 0) - got.get(k, 0)) for k in keys) / 2      # 0 = 같음 · 1 = 완전히 다름
        if tv > 0.45:
            top = lambda d: ", ".join(f"~{k} {int(v * 100)}%" for k, v in sorted(d.items(), key=lambda x: -x[1])[:4])
            out.append(("T19", f"문장 끝 비율이 채널과 다름(차이 {tv:.2f}): 채널 {top(want)} · 대본 {top(got)} — 어미만 고칠 땐 engine/story/tone_edit.py"))
    else:
        card = style_card_of(sb)
        links = (card or {}).get("voice", {}).get("connectives", {})
        if sum(links.values()) >= 3 and not re.search("|".join(map(re.escape, links)), " ".join(sents)):
            out.append(("T19", f"레퍼런스는 이음말({', '.join(list(links)[:4])})로 문장을 잇는데 대본에는 없음"))
    if same > 0.7:
        out.append(("T19", f"문장 끝이 거의 같음('~{max(set(lasts), key=lasts.count)}' {int(same * 100)}%) — 끝맺음을 섞는다"))
    return out


GRAPHIC = {"카드(글자)", "도표", "아이콘 · 그래픽", "애니메이션 · 일러스트", "3D 그래픽", "픽셀 아트"}


def material_tells(sb: dict) -> list:
    """재료가 먼저 — 장면마다 무엇을 보여 줄지(실제 화면 녹화 · 실사 · 사람 · 생성 영상)가 정해지고, 그래픽은 그 위에서 관계를 설명할 때.
    코드로 그린 카드 · 막대 · 글자만으로 채운 영상은 템플릿처럼 보인다(2026-11-02 데모 평가)"""
    scenes = sb.get("scenes", [])
    marked = [sc.get("screen") for sc in scenes if sc.get("screen")]
    out = []
    if len(marked) >= 3:
        g = sum(1 for m in marked if m in GRAPHIC) / len(marked)
        ch = channel_card_of(sb)
        theirs = sum(v for k, v in ((ch or {}).get("structure") or {}).get("screens", {}).items() if k in GRAPHIC) if ch else 0.0
        if g >= 0.6 and g - theirs >= 0.3:
            out.append(("T25", f"그래픽 위주 재료: 장면 {int(g * 100)}%가 직접 그린 카드 · 도표 · 글자" + (f"(채널은 {int(theirs * 100)}%)" if ch else "")
                        + " — 실제 화면 녹화 · 실사 · 사람 · 생성 영상을 주인공으로, 그래픽은 그 위에서 관계를 설명할 때만"))
    return out


def structure_tells(sb: dict) -> list:
    """레퍼런스 채널의 구성과 견준다: 화면 종류(기사 캡처 위주인지) · 농담 박자"""
    ch = channel_card_of(sb)
    if not ch:
        return []
    scenes = sb.get("scenes", [])
    out = []
    marked = [sc.get("screen") for sc in scenes if sc.get("screen")]
    if len(marked) < len(scenes):
        out.append(("T21", f"장면 screen(화면 종류) 칸이 {len(scenes) - len(marked)}곳 비어 있음 — 채널 구성(실제 화면 · 기사 · 짤 비율)과 견줄 수 없다"))
    if marked:
        # 화면 종류 분포가 채널과 얼마나 다른가(0 = 같음 · 1 = 완전히 다름) — 어떤 형식이든 같은 잣대
        want = (ch.get("structure") or {}).get("screens", {})
        got = {}
        for m in marked:
            got[m] = got.get(m, 0) + 1 / len(marked)
        tv = sum(abs(want.get(k, 0) - got.get(k, 0)) for k in set(want) | set(got)) / 2
        if want and tv > 0.5:
            top = lambda d: ", ".join(f"{k} {int(v * 100)}%" for k, v in sorted(d.items(), key=lambda x: -x[1])[:3])
            out.append(("T21", f"화면 구성이 채널과 다름(차이 {tv:.2f}): 채널 {top(want)} · 대본 {top(got)}"))
        mine = sum(1 for m in marked if m == "기사") / len(marked)
        theirs = (ch.get("structure") or {}).get("screens", {}).get("기사", 0)
        if mine >= 0.4 and mine - theirs >= 0.25:
            out.append(("L21", f"기사 캡처 위주: 대본 {int(mine * 100)}%가 기사 화면인데 채널은 {int(theirs * 100)}% — 이야기하는 대상 자체(사이트 · 앱 화면 · 실제 사진)로 바꾸고 기사는 근거 한두 곳만"))
    if not ch.get("jokes") and ch.get("lang", "ko") == "ko":
        out.append(("T23", f"채널 카드의 농담 줄이 확정 전(자동 후보만) — 대사 시트를 보고 python3 engine/research/ref_channel.py note {ch.get('channel')} --jokes <json>"))
    if (ch.get("structure") or {}).get("lead") == "음악 · 화면":
        talk = sum(len((sc.get("narration") or "").strip()) for sc in scenes)
        if talk > 6 * max(1, sum(float(sc.get("sec") or 0) for sc in scenes)) * 0.5:
            out.append(("T24", "채널은 말이 거의 없는(음악 · 화면 주도) 형식인데 대본 나레이션이 많음 — 나레이션을 줄이고 음악 · 자막 · 화면으로"))
        return out
    rate = ch.get("joke_rate_per_10s") or 0
    dur = sum(float(sc.get("sec") or 0) for sc in scenes)
    jokes = sum(1 for sc in scenes if re.match(r"(joke|농담)", str(sc.get("beat") or ""), re.I))
    if rate >= 0.15 and dur and jokes < round(rate * dur / 10 * 0.5):
        out.append(("T22", f"농담 박자가 적음: 채널은 10초에 {rate}번꼴인데 대본은 {jokes}번(기대 {round(rate * dur / 10)}번) — 화면 · 앞말을 살짝 비트는 한마디(beat: joke)"))
    return out


def ref_first_shot(sb: dict) -> float:
    """콘티 reference 의 스타일 카드에 적힌 첫 컷 길이(없으면 0)"""
    for rid in sb.get("reference") or []:
        p = ROOT / "data" / "public" / "trends" / "xray" / str(rid) / "style" / "style.json"
        if p.exists():
            return float(json.loads(p.read_text(encoding="utf-8")).get("rhythm", {}).get("first_shot_sec") or 0)
    return 0.0


def _timing(sb: dict) -> list:
    p = ROOT / "data" / "audio" / f"{sb.get('id')}.timing.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    except Exception:
        return []


def _hash(text: str) -> str:
    return hashlib.sha1(text.strip().encode("utf-8")).hexdigest()[:8]


def measured_scenes(sb: dict) -> set:
    """지금 나레이션으로 만든 실측 음성이 있는 장면 번호."""
    scenes = sb.get("scenes", [])
    out = set()
    for t in _timing(sb):
        i = t.get("scene")
        if i is not None and i < len(scenes):
            nar = (scenes[i].get("narration") or "").strip()
            if nar and t.get("text_hash") == _hash(nar):
                out.add(i)
    return out


def audio_fit(sb: dict) -> list:
    timing_path = ROOT / "data" / "audio" / f"{sb.get('id')}.timing.json"
    if not timing_path.exists():
        return []
    try:
        timing = json.loads(timing_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    scenes = sb.get("scenes", [])
    for t in timing:
        i = t.get("scene")
        if i is None or i >= len(scenes):
            continue
        nar = (scenes[i].get("narration") or "").strip()
        if not nar or t.get("text_hash") != hashlib.sha1(nar.encode("utf-8")).hexdigest()[:8]:
            continue   # 나레이션이 바뀌었으면 옛 음성으로 판단하지 않는다 (음성을 다시 만든 뒤 검사)
        sec = scenes[i].get("sec", 1) or 1
        real = t.get("narration_ms", 0) / 1000
        if real > sec * AUDIO_FIT_MAX:
            n = syllables(nar)
            cut = max(1, math.ceil(n * (1 - sec * 1.05 / real)))
            out.append(("L14", i, f"실측 음성 {real:.2f}s > 장면 {sec}s×{AUDIO_FIT_MAX} — 나레이션을 약 {cut}자 줄이거나 sec 를 늘리세요"))
    return out


def recent_titles(n=30):
    files = sorted((ROOT / "data" / "storyboards").glob("*.json"))[-n:]
    out = []
    for f in files:
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")).get("title", ""))
        except Exception:
            pass
    return out


if __name__ == "__main__":
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    p = Path(args[0]) if args else ROOT / "data" / "storyboards" / "example.json"
    sb = json.loads(p.read_text(encoding="utf-8"))
    fails = lint(sb, [t for t in recent_titles() if t != sb.get("title")])
    if not fails:
        print("통과")
    for code, idx, msg in fails:
        print(f"{code} scene={idx} {msg}")
    hard = [f for f in fails if not f[0].startswith("T")]
    sys.exit(1 if hard else 0)
