#!/usr/bin/env python3
"""
검사층: 콘티 JSON을 코드로 검사한다. LLM 없음, 0원, 즉시.
실패는 (코드, 장면 인덱스 또는 None, 메시지) 로 돌려주고, 생성층은 실패한 칸만 다시 만든다.

규칙 번호는 rules/rulebook.md 4절과 같다.
"""
import difflib
import hashlib
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINAL = "--final" in sys.argv   # 렌더 직전 검사: 단계와 상관없이 화면 구성이 있어야 한다
TOKENS = json.loads((ROOT / "tokens" / "default.json").read_text(encoding="utf-8"))
LIM = TOKENS["limits"]
# L14: 실측 음성이 장면보다 이 배수 넘게 길면 실패. assemble_audio 는 최대 1.25배까지 빠르게 하고 그 뒤는 자르므로,
#      1.15배를 넘으면 말이 급하게 들리거나 끝이 잘린다 (2026-10-27 회전초밥 광고에서 CTA 잘림 확인).
AUDIO_FIT_MAX = 1.15
BANNED = ["충격", "경악", "미쳤다", "역대급", "꼭 보세요"]

try:
    import jsonschema
    SCHEMA = json.loads((ROOT / "schema" / "storyboard.schema.json").read_text(encoding="utf-8"))
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
    if t in ("chart", "text", "stat", "icon"):
        return "그래픽"
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
    base = ROOT / "compositions" / sid / "craft" / "materials"
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
    recs = [r for r in recs if not r.get("missing")]
    # 일부 장면만 렌더한 기록으로 영상 전체를 판단하지 않는다(재료는 렌더가 만든다 — 전체 기록이 모자라면 다음 전체 렌더 뒤에 본다)
    planned = sum(1 for sc in sb.get("scenes") or [] for m in sc.get("materials") or [] if isinstance(m, dict) and m.get("type") not in ("text", "stat"))
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
        out.append(("L35", None, f"재료 종류가 {len(set(kinds))}가지({', '.join(sorted(set(kinds)))}) — 레퍼런스 쇼츠는 화면 종류를 섞는다. 문서 캡처 · 그래픽(stat · chart · icon) · 그림/사진 · 화면/영상(web · screen) · 짤(meme) 중 3가지 이상"))
    # L37 재료 개수: 레퍼런스 설명 쇼츠는 10초에 4번 남짓 화면이 바뀐다 → 3초에 하나 이상(같은 파일은 한 번만 셈)
    seen_src: dict[str, int] = {}
    for r in recs:
        key = (r.get("spec") or {}).get("src") or (r.get("spec") or {}).get("csv") or f"{r.get('scene')}/{r.get('id')}"
        seen_src[key] = max(seen_src.get(key, 0), screen_changes(r))
    uniq = sum(seen_src.values())          # 같은 파일은 한 번 · 녹화 재료는 그 안의 화면 전환 수만큼
    need = int(dur // 3)
    if dur >= 15 and uniq < need:
        out.append(("L37", None, f"화면 전환 {uniq}번(서로 다른 재료 · 녹화 안의 전환 포함) / {dur:.0f}초 — {need}개 이상 필요(문장마다 하나: 짤 · 웹 녹화 · 아이콘 · 수치 카드 · 그림을 섞어서, cue 로 그 낱말에 등장)"))
    # T37 같은 종류가 네 번 연속
    run_k, run_n = None, 0
    for k in kinds:
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
        if difflib.SequenceMatcher(None, sb.get("title", ""), t).ratio() >= 0.8:
            fails.append(("L10", None, f"최근 제목과 유사: '{t}'"))
            break

    # L14 실측 음성 길이 (audio/<id>.timing.json 이 있고, 그 음성이 지금 나레이션으로 만든 것일 때만)
    fails += audio_fit(sb)

    # L32 · T32~T34 템포: 마지막 렌더를 잰 결과(scripts/tempo_check.py, render.py 가 남김). 피드에서 넘기지 않게 하는 기본기
    tp = ROOT / "workspace" / "render" / sb.get("id", "") / "tempo.json"
    if sb.get("id") and tp.exists():
        try:
            sys.path.insert(0, str(ROOT / "scripts"))
            import tempo_check
            for code, msg in tempo_check.problems(json.loads(tp.read_text("utf-8")), any(str(x.get("narration") or "").strip() for x in sb.get("scenes") or [])):
                fails.append((code, None, f"[마지막 렌더] {msg}"))
        except (ValueError, OSError, ImportError):
            pass

    # L33 ~ L35 · T35 재료(시청자 기준): 재료 단계가 남긴 기록(compositions/<id>/craft/materials/sNN/*.json, 글자 인식 포함)으로 본다.
    #     재료를 만들기 전이면 건너뛴다. (2026-11-03: 영어 문서 캡처 9장 · 같은 그래프 3번 → '슬라이드 넘기기' 같은 영상)
    fails += material_checks(sb)
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

    # L30 레퍼런스: 같은 주제 · 형식의 실제 쇼츠를 분석(scripts/shorts_xray.py → public/trends/xray/<id>/xray.json)하고 콘티 reference 에 건다.
    #     조사 없이 '그냥 만들면' 대사 · 리듬 · 화면이 어색하다(2026-11-03 사용자 평가). 사용자가 레퍼런스 없이 만들라고 했을 때만 reference_skip 에 그 말을 적는다
    refs = [r for r in (sb.get("reference") or []) if isinstance(r, str)]
    analyzed = [r for r in refs if (ROOT / "public" / "trends" / "xray" / r / "xray.json").exists()]
    if not analyzed and not str(sb.get("reference_skip") or "").strip():
        fails.append(("L30", None, "레퍼런스 쇼츠 분석 없음: trends 스킬로 같은 주제 · 형식 쇼츠 3~5편을 찾고 shorts_xray.py · ref_channel.py 로 분해한 뒤 콘티 reference 에 영상 id 를 건다(말투 · 컷 길이 · 화면 종류를 거기서 가져온다)"
                      + (f" — reference {refs} 는 아직 X-ray 안 됨" if refs else "")))

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

    # L15 화면 구성: Composed 인데 compositions/<id>/scene.js 가 없으면 화면이 비어 나온다
    sid = sb.get("id", "")
    #     단계에 맞춰: 제작 순서는 콘티 → 검사 → 음성 → 화면 구성이라, 음성 전(콘티 · 기획 단계)에는 '실패'가 아니라 알림(T15).
    #     콘티 단계에서 실패로 내면 '검사 통과 → 제작 시작'과 '제작해야 검사 통과'가 서로를 기다린다
    if sb.get("template") == "Composed" and sid and not (ROOT / "compositions" / sid / "scene.js").exists() and not (ROOT / "compositions" / sid / "graph.js").exists():
        voiced = (ROOT / "audio" / f"{sid}.timing.json").exists()
        if voiced or FINAL:
            fails.append(("L15", None, f"화면 구성 없음: compositions/{sid}/scene.js 를 compose 스킬로 짜야 함"))
        else:
            fails.append(("T15", None, "화면 구성은 음성 다음 단계(제작 시작)에서 만듭니다"))
    # T16 디자인 방향: 영상마다 다른 화면이 나오도록 scripts/direct.py --write 로 정한다 (권고)
    if sb.get("template") == "Composed" and not sb.get("direction"):
        fails.append(("T16", None, "디자인 방향(direction) 없음: python3 scripts/direct.py storyboards/<id>.json --write"))
    # L18/T18 'AI 티' — 화면: 생성 · 자동 연출의 버릇을 scene.js 에서 센다.
    #   디자인 방향이 motion: minimal(레퍼런스 스타일 카드 등)이면 실패(L18), 아니면 권고(T18)
    if sid and (ROOT / "compositions" / sid / "scene.js").exists():
        strict = (sb.get("direction") or {}).get("motion") == "minimal"
        for msg in ai_tells((ROOT / "compositions" / sid / "scene.js").read_text(encoding="utf-8"), len(sb.get("scenes", []))):
            fails.append(("L18" if strict else "T18", None, msg))
        # 실제 화면 검사(scripts/look_check.py — 부품 속 효과까지 렌더 화면에서 잰다). 글자 검사(ai_tells)로는 못 보는 것
        lc = ROOT / "workspace" / "render" / sid / "look-check.json"
        js_sha = hashlib.sha1((ROOT / "compositions" / sid / "scene.js").read_bytes()).hexdigest()[:12]
        if not lc.exists():
            fails.append(("T18", None, f"'AI 티' 화면 검사 안 함 — python3 scripts/look_check.py storyboards/{sid}.json"))
        else:
            r = json.loads(lc.read_text(encoding="utf-8"))
            if r.get("scene_js_sha") != js_sha:
                fails.append(("T18", None, f"화면 구성이 바뀐 뒤 'AI 티' 화면 검사를 안 함 — python3 scripts/look_check.py storyboards/{sid}.json"))
            elif not r.get("ok"):
                cats = ", ".join({"tilt": "기울기 · 원근", "blur": "흐림 등장", "gradient": "그라데이션 · 빛번짐", "glow": "색 빛", "template": "같은 틀", "preset": "프리셋과 다른 배치"}.get(k, k) for k in r.get("categories", {}))
                fails.append(("L18", None, f"'AI 티' 화면 검사 실패: {cats} — scripts/look_check.py 출력대로 고치기(레퍼런스가 그런 화면이면 --allow)"))
    # L28 편집 밀도: 초안 렌더를 사람 쇼츠 기준과 견준 결과(scripts/edit_density.py, render.py --draft 가 남김) — '슬라이드 같음'
    if sb.get("template") == "Composed" and (ROOT / "compositions" / sid / "scene.js").exists():
        dp = ROOT / "workspace" / "render" / sid / "density.json"
        if not dp.exists():
            fails.append(("T28", None, f"편집 밀도 안 잼 — 초안 렌더(python3 scripts/render.py storyboards/{sid}.json --draft)가 잰다"))
        else:
            d = json.loads(dp.read_text(encoding="utf-8"))
            if d.get("scene_js_sha") != hashlib.sha1((ROOT / "compositions" / sid / "scene.js").read_bytes()).hexdigest()[:12]:
                fails.append(("T28", None, "화면 구성이 바뀐 뒤 편집 밀도를 안 잼 — 초안을 다시 렌더"))
            elif d.get("problems") and not d.get("allowed"):
                for x in d["problems"]:
                    fails.append(("L28", None, x))
    # T19 말투: 문장 끝 비율을 레퍼런스 채널(여러 편)과 견준다(권고). L21/T21/T22 구성: 화면 종류 · 농담 박자
    for code, msg in speech_tells(sb) + structure_tells(sb) + plan_density(sb):
        fails.append((code, None, msg))
    # T27 배치 기준: 레퍼런스도 형식 프리셋도 없으면 손으로 정한 기본값(가운데 판 · 고정 자막)이 쓰인다 = AI 틀
    if sb.get("template") == "Composed" and not sb.get("preset") and not (sb.get("reference") or []):
        fails.append(("T27", None, "형식 프리셋 없음 — python3 scripts/format_presets.py pick storyboards/<id>.json (사람이 편집한 실제 쇼츠의 배치 숫자)"))
    # T25/T26 재료: 장면 화면이 직접 그린 그래픽뿐이면 템플릿 티. 실제 화면은 정지 캡처 카드보다 조작 녹화(webrec · K.web)
    for code, msg in material_tells(sb):
        fails.append((code, None, msg))
    # L17 레이어 요소: scene.js 가 부르는 elements/<id>/<이름> 이 실제로 있어야 한다. T17 상업 이용이 '가능'이 아닌 생성 모델 요소는 알림
    scene_js = ROOT / "compositions" / str(sid) / "scene.js"
    if sid and scene_js.exists():
        for rel in sorted(set(re.findall(r"[\"'`](elements/[A-Za-z0-9가-힣_.-]+/[A-Za-z0-9가-힣_.-]+)[\"'`]", scene_js.read_text(encoding="utf-8")))):
            mp = ROOT / "public" / rel / "meta.json"
            if not mp.exists():
                fails.append(("L17", None, f"레이어 요소 없음: {rel} — python3 scripts/element.py … 로 만들기"))
                continue
            em = json.loads(mp.read_text(encoding="utf-8"))
            if em.get("commercial") and em["commercial"] != "가능":
                fails.append(("T17", None, f"{rel}: 모델 {em.get('model')} 상업 이용 '{em['commercial']}' — 발행 전 확인"))

    return fails


FORMAL = ("습니다", "입니다", "합니다", "됩니다", "있습니다")
CASUAL = ("고요", "는데", "거든요", "대요", "네요", "어요", "아요", "예요", "에요", "죠", "잖아요", "더라고요")


def style_card_of(sb: dict) -> dict | None:
    for rid in sb.get("reference") or []:
        p = ROOT / "public" / "trends" / "xray" / str(rid) / "style" / "style.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return None


def channel_card_of(sb: dict) -> dict | None:
    """레퍼런스 스타일 카드에 달린 채널 카드(scripts/ref_channel.py) — 여러 편에서 뽑은 말투 · 구조"""
    c = style_card_of(sb)
    cid = (c or {}).get("channel")
    p = ROOT / "public" / "trends" / "channels" / str(cid) / "channel.json" if cid else None
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
            out.append(("T19", f"문장 끝 비율이 채널과 다름(차이 {tv:.2f}): 채널 {top(want)} · 대본 {top(got)} — 어미만 고칠 땐 scripts/tone_edit.py"))
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
    sid = sb.get("id")
    js = ROOT / "compositions" / str(sid) / "scene.js"
    if sid and js.exists() and any(m == "실제 화면" for m in marked):
        txt = js.read_text(encoding="utf-8")
        if not re.search(r"K\.web\(|k\.shot\(|K\.talk\.shot\(|\bshot\(", txt) and re.search(r"\.card\(|K\.image\(", txt):
            out.append(("T26", "실제 화면 장면이 정지 캡처 카드뿐 — 조작이 보이게 녹화(python3 scripts/webrec.py run … → K.web: 커서 · 클릭 · 반응 · 확대)하거나 화면 띠(K.talk.shot)에 강조"))
    return out


def plan_density(sb: dict) -> list:
    """L29 계획 단계의 편집 밀도: 장면 screen + beats(재료) 순서로 재료가 몇 번 바뀌는지 · 몇 가지인지를 사람 쇼츠 기준(presets/density.json)과 견준다.
    렌더 뒤에 재는 L28 보다 먼저 — 콘티에서 이미 '문장마다 그림 한 장'이면 화면을 짜기 전에 막는다"""
    if sb.get("template") != "Composed" or (sb.get("intent") or {}).get("density_ok"):
        return []
    scenes = sb.get("scenes", [])
    dur = sum(float(sc.get("sec") or 0) for sc in scenes) or 1
    # 기준은 렌더 검사와 같은 곳에서(참고 쇼츠가 있으면 그 영상 자체 → 형식 프리셋 → 사람 쇼츠 중앙값)
    import edit_density
    full = edit_density.base_of(sb)
    base = {k: v for k, v in full.items() if k in ("kinds", "kind_switch")}
    from_ref = bool(full.get("_from"))
    seq, out = [], []
    for i, sc in enumerate(scenes):
        main = sc.get("screen")
        if main:
            seq.append(main)
        bts = sc.get("beats") or []
        # 렌더 측정(edit_density)과 같은 셈: 핵심 단어 화면(do:글자)은 '카드(글자)'로 보이고, 짤 · 글자가 끝나면 장면 화면으로 돌아온다(그것도 전환)
        for b in sorted(bts, key=lambda b: str(sc.get("narration") or "").find(b.get("at", ""))):
            k = b.get("screen") if b.get("do") == "재료" else ("카드(글자)" if b.get("do") == "글자" else None)
            if not k:
                continue
            seq.append(k)
            if main and (b.get("hold") or 0) < 90:
                seq.append(main)
        nar = str(sc.get("narration") or "")
        for b in bts:
            if b.get("at") and b["at"] not in nar:
                out.append(("L29", f"장면 {i + 1} beats 의 '{b['at']}' 가 나레이션에 없음 — 들리는 단어에 맞춘다"))
        if float(sc.get("sec") or 0) >= 4 and not bts:
            out.append(("T29", f"장면 {i + 1}({sc.get('sec')}초)에 beats 없음 — 4초 넘게 한 화면이면 슬라이드처럼 보인다"))
    sw = sum(1 for a, b in zip(seq, seq[1:]) if a != b)
    rate = sw / dur * 10
    # 참고 쇼츠가 기준이면 전환 횟수는 렌더 뒤(L28)에만 — 참고 영상의 전환은 자막이 커질 때 화면이 '글자 카드'로 분류되는 것까지 포함이라
    #  콘티의 재료 이름으로는 같은 잣대가 안 된다(2026-11-02 꽁트 형식에서 확인)
    if not from_ref and rate < base["kind_switch"] * 0.8:
        out.append(("L29", f"계획한 재료 전환 {rate:.1f}번/10초 — 사람 편집 {base['kind_switch']}번(장면 beats 에 do: 재료 로 짤 · 사람 · 기사 · 사진을 단어에 맞춰)"))
    need = max(1, min(round(base["kinds"]), round(base["kinds"] * (0.4 if dur < 15 else 0.6)) or 1))
    if len(set(seq)) < need:
        out.append(("L29", f"재료 종류 {len(set(seq))}가지({', '.join(sorted(set(seq)))}) — 사람 편집 {base['kinds']:.0f}가지, 최소 {need}가지"))
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
        out.append(("T23", f"채널 카드의 농담 줄이 확정 전(자동 후보만) — 대사 시트를 보고 python3 scripts/ref_channel.py note {ch.get('channel')} --jokes <json>"))
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
        p = ROOT / "public" / "trends" / "xray" / str(rid) / "style" / "style.json"
        if p.exists():
            return float(json.loads(p.read_text(encoding="utf-8")).get("rhythm", {}).get("first_shot_sec") or 0)
    return 0.0


def ai_tells(js: str, n_scenes: int) -> list:
    """영상이 'AI 가 만든 것처럼' 보이게 하는 연출 버릇 — 하나하나는 괜찮지만 겹치면 티가 난다"""
    out, n = [], max(1, n_scenes)
    if re.search(r"camera\s*:\s*K\.camera\.drift", js):
        out.append("화면 전체가 영상 내내 둥둥 떠다님(camera.drift) — 멈춰 있는 순간이 있어야 사람이 찍은 것처럼 보임. 움직임은 이유 있는 순간에만")
    if re.search(r"camera\s*:\s*K\.camera\.punch", js):
        out.append("장면마다 펀치 줌(camera.punch) — 매 컷 같은 확대는 자동 편집 티. 강조할 1~2컷에만")
    bounce = len(re.findall(r"back\.out|E\.back|elastic|anim\s*:\s*[\"']pop[\"']", js))
    if bounce >= n * 2:
        out.append(f"튀어 오르는 등장(back · pop)이 {bounce}번 — 모든 것이 통통 튀면 AI 티. 주인공 한 개만 튀고 나머지는 담백하게(power2 · 컷)")
    floats = len(re.findall(r"float\s*:\s*\d", js))
    if floats >= 3:
        out.append(f"계속 흔들리는 요소(float) {floats}개 — 정지가 리듬을 만든다. 1개 이하로")
    trs = re.findall(r"[\"'](glitch|flash|zoom|circle)[\"']", js)
    if len(trs) >= max(3, n // 2):
        out.append(f"화려한 전환({', '.join(sorted(set(trs)))}) {len(trs)}번 — 대부분은 컷, 전환은 의미가 바뀔 때만")
    stag = len(re.findall(r"stagger|i\s*\*\s*0?\.\d+", js))
    if stag >= n * 2:
        out.append("모든 묶음이 같은 간격으로 차례차례 등장(stagger) — 말(c.cue)에 맞춰 등장 시각을 다르게")
    if re.search(r"(mesh|bokeh|rays)", js) and re.search(r"glow|blur\(", js):
        out.append("빛번짐 · 흐린 그라데이션 배경 + 글로우 — 흔한 AI 룩. 단색 · 종이 · 실사 바탕을 고려")
    return out


def _timing(sb: dict) -> list:
    p = ROOT / "audio" / f"{sb.get('id')}.timing.json"
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
    timing_path = ROOT / "audio" / f"{sb.get('id')}.timing.json"
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
    files = sorted((ROOT / "storyboards").glob("*.json"))[-n:]
    out = []
    for f in files:
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")).get("title", ""))
        except Exception:
            pass
    return out


if __name__ == "__main__":
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    p = Path(args[0]) if args else ROOT / "storyboards" / "example.json"
    sb = json.loads(p.read_text(encoding="utf-8"))
    fails = lint(sb, [t for t in recent_titles() if t != sb.get("title")])
    if not fails:
        print("통과")
    for code, idx, msg in fails:
        print(f"{code} scene={idx} {msg}")
    hard = [f for f in fails if not f[0].startswith("T")]
    sys.exit(1 if hard else 0)
