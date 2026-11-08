"""다듬기(refine) — 고정 어댑터가 만든 초벌 위에, 에이전트가 앱의 '전체' 명령에서 골라 디테일을 얹는다(전문가의 작업 세션).

초벌(어댑터 · JSX · 소리 세션 · 편집 프로젝트)은 매번 새로 만들어진다. 손댄 것이 사라지지 않게, 다듬기는 콘티에 '기록'으로 남기고
각 단계가 초벌을 만든 뒤 그 기록을 다시 적용한다(콘티가 곧 작업 기록 — 다시 만들어도 같은 결과).

다듬기 한 번(pass):
  { "layer": "typo",                      # 디테일 층(LAYERS) — 무엇을 다듬었나
    "app": "photocraft",                  # 재료 다듬기에서만: 어느 앱으로(없으면 재료를 만든 앱 · 편집 파일)
    "steps": [ {"id": "명령 id", "params": {...}}, ... ],   # catalog 의 명령(engine/craft/craft_catalog.py search)
    "why": "왜 — 레퍼런스의 무엇 · 사용자 요청" }

어디에 적나:
  재료       scenes[i].materials[j].refine = [pass, …]  → 재료 파일(PNG · 편집 파일)을 열어 이어서 다듬는다. 앞 pass 결과가 다음 pass 입력.
             app 이 재료를 만든 앱과 같으면 그 편집 파일(.vectorcraft · .psd …)을, 다르면 결과 그림(PNG)을 연다 → 앱을 넘나든다
  움직임     scenes[i].refine = [{"target": "motion", …}]  → EffectCraft 장면 컴프("S01 훅" …) 안 레이어 이름으로(Mat <id> · Sub 01 · Title 1 · BG · Camera …)
  소리       scenes[i].refine = [{"target": "sound", …}]   → SoundCraft 세션(트랙 Voice · Music · SFX · Master 1)
  편집       scenes[i].refine = [{"target": "edit", …}]    → FilmCraft 프로젝트(V1 · A1 · 마커)
  영상 전체  sb["refine"] = [{"target": "sound" | "edit" | "motion", …}]   (장면 시각 자리표시자 없음 · motion 은 "$COMP" = Main)

params 안 자리표시자(문자열 전체가 자리표시자면 숫자로 바뀐다):
  "$COMP" 장면 컴프 이름 · "$START" "$END" "$MID" 장면 시작 · 끝 · 가운데(영상 전체 기준 초) · "$SEC" 장면 길이
  "$START_SMP" "$END_SMP" SoundCraft 샘플(48 kHz) · "$START_TICKS" "$END_TICKS" FilmCraft 틱
  EffectCraft 장면 컴프 안은 장면 시작이 0초다(컴프 시간) — 움직임 pass 의 time 은 그냥 장면 안 초를 쓴다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())

# 디테일 층 — 전문가가 한 컷을 볼 때 따지는 것. 장면 계획(scenes[i].detail)과 다듬기 기록이 이 이름을 쓴다
LAYERS = {
    "composition": "구도 · 배치 · 여백 · 시선 흐름",
    "typo": "타이포 — 위계 · 자간 · 굵기 · 글자 효과 · 글자 애니메이션",
    "color": "색 — 그레이딩 · 대비 · 팔레트 · 강조색",
    "light": "빛 — 조명 · 그림자 · 광택 · 빛 번짐",
    "texture": "질감 — 그레인 · 종이 · 노이즈 · 재질",
    "motion": "움직임 — 이징 · 시차 · 카메라 · 2.5D 깊이",
    "transition": "전환 — 컷 사이 연결 · 매치 컷 · 마스크 닦기",
    "sound": "소리 — 공간감 · 효과음 · 전환음 · 음색",
}
TARGETS = {"motion": "effectcraft", "sound": "soundcraft", "edit": "filmcraft"}
RATE, TICKS = 48000, 254016000000
_PH = re.compile(r"^\$(COMP|START|END|MID|SEC|START_SMP|END_SMP|START_TICKS|END_TICKS)$")


# ---------------------------------------------------------------- 공통
def scene_times(sb: dict) -> list[tuple[float, float]]:
    t, out = 0.0, []
    for s in sb.get("scenes") or []:
        sec = float(s.get("sec") or 0)
        out.append((round(t, 3), round(t + sec, 3)))
        t += sec
    return out


def comp_name(sb: dict, i: int, num: int | None = None) -> str:
    """장면 컴프 이름(motion.py 와 같게). num = 원래 장면 번호(1부터) — 장면 일부만 렌더할 때 콘티는 잘려 오지만 컴프 이름은 원래 번호"""
    from craft.motion import ROLE_KO
    sc = (sb.get("scenes") or [])[i]
    return f"S{num or i + 1:02d} {ROLE_KO.get(sc.get('role'), sc.get('role') or '')}".strip()


def vars_for(sb: dict, i: int | None, num: int | None = None) -> dict:
    if i is None:
        return {"COMP": "Main"}
    a, b = scene_times(sb)[i]
    return {"ROOT": str(ROOT), "MATDIR": str(ROOT / "data" / "compositions" / sb["id"] / "craft" / "materials" / f"s{(num or i + 1):02d}"), "COMP": comp_name(sb, i, num), "START": a, "END": b, "MID": round((a + b) / 2, 3), "SEC": round(b - a, 3),
            "START_SMP": int(round(a * RATE)), "END_SMP": int(round(b * RATE)),
            "START_TICKS": int(round(a * TICKS)), "END_TICKS": int(round(b * TICKS))}


_INLINE = re.compile(r"\$(COMP|ROOT|MATDIR)\b")


def script_failures(out: str) -> list[str]:
    """EffectCraft run 은 스크립트 오류에도 종료 코드 0 이다 — 결과의 ok: false 를 찾아 실패로 만든다.
    찾지 않으면 다듬기가 조용히 빠진 영상이 성공으로 나온다"""
    fails, dec, i = [], json.JSONDecoder(), 0
    while True:
        j = out.find("{", i)
        if j < 0:
            return fails
        try:
            d, i = dec.raw_decode(out, j)
        except ValueError:
            i = j + 1
            continue
        if isinstance(d, dict) and d.get("ok") is False:
            e = d.get("error")
            fails.append(f"{e.get('file')}: {e.get('message')}" if isinstance(e, dict) else str(e))


def subst(o, v: dict):
    if isinstance(o, str):
        m = _PH.match(o)
        if m:
            if m.group(1) not in v:
                raise ValueError(f"{o} 는 장면 다듬기에서만 씁니다(영상 전체 pass 에는 장면 시각이 없음)")
            return v[m.group(1)]
        return _INLINE.sub(lambda q: str(v.get(q.group(1), q.group(0))), o)          # 스크립트 코드 안의 $COMP · $ROOT
    if isinstance(o, dict):
        return {k: subst(x, v) for k, x in o.items()}
    if isinstance(o, list):
        return [subst(x, v) for x in o]
    return o


def passes(sb: dict, target: str) -> list[tuple[int | None, dict]]:
    """(장면 번호 0부터 | None=영상 전체, pass) — 콘티 순서대로(전체 pass 가 마지막)"""
    out = [(i, p) for i, s in enumerate(sb.get("scenes") or []) for p in (s.get("refine") or []) if p.get("target") == target]
    out += [(None, p) for p in (sb.get("refine") or []) if p.get("target") == target]
    return out


def key(sb: dict, target: str) -> str:
    return json.dumps([[i, p] for i, p in passes(sb, target)], sort_keys=True, ensure_ascii=False)


def _ids(app: str) -> set:
    from craft.adapters.craft_script import known_ids
    return known_ids(app)


# ---------------------------------------------------------------- 단계별 명령
SUBS_TOP = """var C=null;for(var i=1;i<=app.project.numItems;i++){var it=app.project.item(i);if(it instanceof CompItem&&it.name=="@COMP@")C=it;}
var a=[];for(var i=1;i<=C.numLayers;i++){var n=C.layer(i).name;if(n.indexOf("Sub")==0)a.push(C.layer(i));}
for(var i=a.length-1;i>=0;i--){if(a[i].name.indexOf("SubBox")==0)a[i].moveToBeginning();}
for(var i=a.length-1;i>=0;i--){if(a[i].name.indexOf("SubBox")!=0)a[i].moveToBeginning();}"""


def motion_steps(sb: dict, nums: list[int] | None = None) -> list[dict]:
    """EffectCraft run --commands 형식. pass 마다 장면 컴프를 먼저 연다. nums = 잘린 콘티 장면마다 원래 번호(1부터)"""
    out = []
    seen = []
    for i, p in passes(sb, "motion"):
        v = vars_for(sb, i, nums[i] if nums and i is not None else None)
        out.append({"command": "comp.open", "params": {"comp": v["COMP"]}})
        out += [{"command": s["id"], "params": subst(s.get("params") or {}, v)} for s in p.get("steps") or []]
        if i is not None and v["COMP"] not in seen:
            seen.append(v["COMP"])
    for c in seen:                                  # 다듬기로 얹은 인물 · 글자가 자막을 덮지 않게 — 자막은 늘 맨 위
        out.append({"command": "script.run", "params": {"name": "subs-top", "code": SUBS_TOP.replace("@COMP@", c)}})
    return out


def sound_cmds(sb: dict) -> list[str]:
    """SoundCraft run --cmd 형식("id=JSON")"""
    return [f"{s['id']}={json.dumps(subst(s.get('params') or {}, vars_for(sb, i)), ensure_ascii=False)}"
            for i, p in passes(sb, "sound") for s in p.get("steps") or []]


def edit_lines(sb: dict) -> list[dict]:
    """FilmCraft run 스크립트 줄({"id","params"})"""
    return [{"id": s["id"], "params": subst(s.get("params") or {}, vars_for(sb, i))}
            for i, p in passes(sb, "edit") for s in p.get("steps") or []]


# ---------------------------------------------------------------- 재료
def apply_material(rec: dict, m: dict, d: Path) -> dict:
    """재료 기록 rec 의 결과 파일을 m.refine 대로 이어서 다듬는다 → rec(file · refined_editable · refined 갱신).
    rec["editable"] 는 그대로 둔다(사람이 고친 편집 파일 알아보기가 처음 만든 파일 해시를 쓴다)"""
    from craft.adapters.craft_script import craft
    cur_file = ROOT / rec["file"]
    cur_ed = ROOT / rec["editable"] if rec.get("editable") else None
    cur_app = rec.get("app")
    done = []
    for k, p in enumerate(m.get("refine") or [], 1):
        app = p.get("app") or cur_app or "photocraft"
        video = cur_file.suffix.lower() == ".mp4"
        if app == cur_app and cur_ed and cur_ed.exists():
            src = cur_ed
        elif video:
            raise RuntimeError(f"재료 {m['id']} 다듬기 {k}: 영상 재료는 만든 앱({cur_app})의 편집 파일로만 다듬습니다")
        else:
            src = cur_file
        out = d / f"{m['id']}.r{k}.png"
        ex = dict(p.get("export") or {})
        if video:
            ex.setdefault("format", "mp4")
        info = craft({"type": "craft", "id": f"{m['id']}.r{k}", "app": app, "open": str(src.relative_to(ROOT)),
                      "steps": p.get("steps") or [], "export": ex}, out, d)
        new = out.with_suffix(info.get("file_suffix") or (".mp4" if ex.get("format") == "mp4" else ".png"))
        if not new.exists():
            raise RuntimeError(f"재료 {m['id']} 다듬기 {k}({app}): 결과 파일이 없습니다")
        cur_file, cur_app = new, app
        cur_ed = ROOT / info["editable"] if info.get("editable") else None
        done.append({"layer": p.get("layer"), "app": app, "steps": info.get("steps_run") or [], "why": p.get("why")})
    if done:
        rec = {**rec, "file": str(cur_file.relative_to(ROOT)), "refined": done}
        if cur_ed:
            rec["refined_editable"] = str(cur_ed.relative_to(ROOT))
        if cur_app and cur_app != rec.get("app"):
            rec["refined_app"] = cur_app
    return rec


# ---------------------------------------------------------------- 검사 · 기록
def validate(sb: dict) -> list[str]:
    """다듬기 기록의 잘못(층 · 대상 · 명령 id) — lint L40"""
    errs = []

    def chk(where: str, p: dict, app: str | None):
        if p.get("recipe") and not p.get("steps"):         # 레시피만 적은 칸 — 렌더 때 펼친다
            return
        if p.get("layer") not in LAYERS:
            errs.append(f"{where}: layer '{p.get('layer')}' 는 {' · '.join(LAYERS)} 중 하나")
        if not p.get("steps") and not p.get("recipe"):
            errs.append(f"{where}: steps 가 비었습니다")
        if not str(p.get("why") or "").strip():
            errs.append(f"{where}: why(근거 — 레퍼런스의 무엇 · 사용자 요청)를 적습니다")
        if app:
            ids = _ids(app)
            for s in p.get("steps") or []:
                if ids and s.get("id") not in ids:
                    errs.append(f"{where}: {app} 에 '{s.get('id')}' 명령이 없습니다(craft_catalog.py search)")
    for i, s in enumerate(sb.get("scenes") or []):
        for k, p in enumerate(s.get("refine") or [], 1):
            t = p.get("target")
            if t not in TARGETS:
                errs.append(f"{i + 1}장면 refine {k}: target '{t}' — {' · '.join(TARGETS)} 중 하나(재료 다듬기는 재료 칸의 refine)")
                continue
            chk(f"{i + 1}장면 refine {k}", p, TARGETS[t])
        for m in s.get("materials") or []:
            for k, p in enumerate(m.get("refine") or [], 1):
                chk(f"{i + 1}장면 재료 {m.get('id')} refine {k}", p, p.get("app"))
        for ly in (s.get("detail") or {}):
            if ly not in LAYERS:
                errs.append(f"{i + 1}장면 detail: '{ly}' 는 {' · '.join(LAYERS)} 중 하나")
    for k, p in enumerate(sb.get("refine") or [], 1):
        t = p.get("target")
        if t not in TARGETS:
            errs.append(f"영상 전체 refine {k}: target '{t}' — {' · '.join(TARGETS)} 중 하나")
            continue
        chk(f"영상 전체 refine {k}", p, TARGETS[t])
    return errs


def coverage(sb: dict) -> dict:
    """앱 × 디테일 층 → 다듬기 횟수 · 명령 수. 장면마다 계획한 층(detail) 중 다듬지 않은 것"""
    grid: dict = {}

    def add(app, layer, n):
        c = grid.setdefault(app or "?", {}).setdefault(layer or "?", [0, 0])
        c[0] += 1
        c[1] += n
    missing = []
    for i, s in enumerate(sb.get("scenes") or []):
        got = set()
        for p in s.get("refine") or []:
            add(TARGETS.get(p.get("target")), p.get("layer"), len(p.get("steps") or []))
            got.add(p.get("layer"))
        for m in s.get("materials") or []:
            for p in m.get("refine") or []:
                add(p.get("app") or "(재료 앱)", p.get("layer"), len(p.get("steps") or []))
                got.add(p.get("layer"))
        for ly in (s.get("detail") or {}):
            if ly not in got:
                missing.append((i + 1, ly))
    for p in sb.get("refine") or []:
        add(TARGETS.get(p.get("target")), p.get("layer"), len(p.get("steps") or []))
    return {"grid": grid, "missing": missing}
