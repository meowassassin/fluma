#!/usr/bin/env python3
"""agent-only Flow 화면(#799)에서 i2v(시작 프레임 → 영상) · i2i(참조 이미지 → 이미지)를 직접 몬다.

gflow 의 부품을 그대로 쓴다: 브라우저 · 프로필(UiAutomationTransport), 편집 화면(ensure_editor_for),
에이전트 설정(apply_defaults: 비율 · 1개 · 모델), 제출 · 크레딧 확인 창 승인(요청보다 많이 청구하면 거부) · 완료 감지(generate),
다운로드(download_video / _download_image). 새로 하는 일은 제출 전에 '+ → 미디어 업로드 → 프롬프트에 추가'로 참조 이미지를 붙이는 것뿐.

  tools/gflow/.venv/bin/python engine/gen/flow_agent_i2v.py --project <uuid> --image s01.png --prompt "..." --out take.mp4 \
      [--sec 4] [--model veo_3_1_lite] [--profile poi-happywha]
  tools/gflow/.venv/bin/python engine/gen/flow_agent_i2v.py --kind image --prompt "..." --out out.png \
      [--ref style.png::style] [--aspect 9:16] [--model nano-pro] [--project <uuid>]
크레딧을 쓴다(--dry 는 붙이기까지만, $0). 결과 JSON 한 줄(ok · stage · path · media_id · ...)을 마지막에 찍는다.
stage: attach(제출 전 실패 — 청구 없음) · generate(제출 뒤 실패 — 청구됐을 수 있음) · done.
gflow 의 gflow-cli venv 파이썬으로 돌린다(gflow_cli 를 불러 쓴다). engine/gen/video.py · engine/gen/image.py 가 부른다.
측정(2026-11-14): Veo 3.1 Lite 의 첫 프레임 i2v 는 8초만 된다 — 다른 길이는 에이전트가 되묻고(선택 질문) 그 뒤 확인 창을 gflow 가 거부한다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

from gflow_cli.api.image import Aspect as ImageAspect, Model as ImageModel
from gflow_cli.api.transports import agent_only_composer as agent
from gflow_cli.api.transports.migrated_composer import (
    ASPECT_LIGATURE,
    IMAGE_ASPECT_LIGATURE,
    IMAGE_MODEL_MENU_MATCHERS,
    MIGRATED_PROJECT_URL,
    VIDEO_MODEL_MENU_MATCHERS,
    MigratedComposer,
    create_project,
)
from gflow_cli.api.transports.ui_automation import (
    UiAutomationTransport,
    _is_allowed_download_host,
)
from gflow_cli.api.video import Aspect, VideoModel
from gflow_cli.paths import default_home, profile_subdir

BOX = "flow-creative-agent-prompt-box"
ADD = f"{BOX} button:has(mat-icon:text-is('add'))"
CHIP_IMG = f"{BOX} flow-image-ingredient-chip img"
#: 칩이 '불러오는 중' 자리표시가 아니라 실제 그림을 띄웠는지(측정: 붙인 직후엔 placeholder 아이콘만 보인다)
CHIP_READY_JS = f"""() => [...document.querySelectorAll("{BOX} flow-image-ingredient-chip")].map(c => {{
  const i = c.querySelector('img'); return !!(i && i.complete && i.naturalWidth > 0 && !c.querySelector('.chip-placeholder')); }})"""


async def chips_ready(page) -> list[bool]:
    return await page.evaluate(CHIP_READY_JS)
ADD_TO_PROMPT = ("프롬프트에 추가", "Add to prompt")


_COUNT_RE = re.compile(
    r"(\d+)\s*(?:개|편|장|videos?\b|clips?\b|generations?\b|images?\b|pictures?\b|photos?\b|видео|изображ\w*)",
    re.I,
)
_CREDIT_RE = re.compile(r"(\d+)\s*(?:크레딧|credits?\b|бонус)|(?:크레딧|credits?|бонус\w*)\s*\(?\s*(\d+)", re.I)


def gate_quotes_more(title: str, count: int) -> bool | None:
    """gflow 의 판독(숫자 순서 '개수 먼저, 크레딧 끝')은 한국어 문구에서 틀린다 — '10 크레딧을 사용하여 1개 동영상…'을
    10개로 읽고 거부(#988 오판). 숫자 옆 낱말로 개수를 찾는다. 개수 · 크레딧 둘 다 못 읽으면 None(승인하지 않음)."""
    counts = [int(m) for m in _COUNT_RE.findall(title)]
    credits = [int(a or b) for a, b in _CREDIT_RE.findall(title)]
    if not counts or not credits:
        return None
    return any(n > count for n in counts)


agent.gate_quotes_more = gate_quotes_more   # 확인 창 판독만 바꾼다 — 한 번만 승인 · 두 번째 창 거부는 gflow 그대로


def directive(prompt: str, sec: int, aspect: str) -> str:
    return ("Use the attached image as the exact first frame of the video — image-to-video: keep its character, "
            "composition, colours and art style, do not redraw or restyle it. "
            f"Make me a {sec} second video in a {aspect} aspect ratio: {prompt}")


def image_directive(prompt: str, aspect: str, refs: list[tuple[Path, str]] | None = None) -> str:
    if not refs:
        return f"Make me a single picture in a {aspect} aspect ratio of: {prompt}"
    ref_lines = "\n".join(
        f"- Attached image {i + 1} (Image {i + 1}): {role}"
        for i, (_, role) in enumerate(refs)
    )
    return (
        f"Using the {len(refs)} attached reference image(s) strictly by their role below, "
        f"make me ONE single image in a {aspect} aspect ratio (do not generate multiple variations).\n"
        f"{ref_lines}\n\n"
        f"Prompt: {prompt}"
    )


async def _chips_ok(page, expected_count: int) -> bool:
    ready = await chips_ready(page)
    return len(ready) == expected_count and all(ready)


async def _dismiss_overlay(page) -> None:
    if await page.locator(".cdk-overlay-pane").count():
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)


async def clear_chips(page) -> None:
    """지난 시도에서 채팅 칸에 남은 이미지 칩을 모두 지운다."""
    chips = page.locator(f"{BOX} flow-image-ingredient-chip")
    while await chips.count():
        n = await chips.count()
        await page.locator(
            f"{BOX} flow-ingredient-bar ~ button:has(mat-icon:text-is('close')), {BOX} button:has(mat-icon:text-is('close'))"
        ).first.click()
        await page.wait_for_timeout(600)
        if await chips.count() >= n:
            raise RuntimeError("채팅 칸에 남은 첨부를 지우지 못함")


async def attach_one(
    page, image: Path, expected_count: int, timeout_s: float = 90, shots: Path | None = None, tag_prefix: str = ""
) -> str:
    """단일 이미지를 채팅 칸에 추가로 붙인다(기존 칩 유지). 칩 개수가 expected_count 에 도달하고 로드되면 반환."""
    async def snap(tag: str) -> None:
        if shots:
            await page.screenshot(path=str(shots / f"{tag_prefix}{tag}.png"))

    await _dismiss_overlay(page)
    await page.locator(ADD).first.click()
    await page.wait_for_timeout(1000)
    async with page.expect_file_chooser(timeout=15_000) as fc:
        await page.locator("button:has(mat-icon:text-is('upload'))").last.click()
    await (await fc.value).set_files(str(image))
    await snap("1-uploading")
    # 측정(2026-11-14): 채팅 칸 '+'에서 올리면 업로드가 끝날 때 칸에 자동으로 붙고 메뉴가 닫힌다.
    # 붙지 않고 목록에 남는 경우만 골라서 '프롬프트에 추가'를 누른다.
    item = page.locator(
        f".cdk-overlay-pane :is([role=menuitem], [role=option], button, li, div[tabindex]):has-text('{image.name}')"
    ).last
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        if await _chips_ok(page, expected_count):
            await _dismiss_overlay(page)
            await snap("3-added")
            return image.name
        if await item.count() and await item.is_visible():
            txt = await item.inner_text()
            if "업로드 중" not in txt and "Uploading" not in txt:
                break
        await page.wait_for_timeout(1000)
    else:
        await snap("1-upload-timeout")
        raise TimeoutError(f"업로드한 그림이 {timeout_s:.0f}초 안에 채팅 칸에 붙지 않음: {image.name}")

    await item.click()
    await page.wait_for_timeout(800)
    await snap("2-selected")
    btn = page.get_by_role("button", name=ADD_TO_PROMPT[0]).or_(page.get_by_role("button", name=ADD_TO_PROMPT[1])).first
    end = time.monotonic() + 30
    while time.monotonic() < end:
        if await _chips_ok(page, expected_count):
            await _dismiss_overlay(page)
            await snap("3-added")
            return image.name
        if await btn.count() and await btn.is_enabled():
            await btn.click()
            break
        await page.wait_for_timeout(500)
    else:
        await snap("2-add-disabled")
        raise TimeoutError("그림이 붙지도 않고 '프롬프트에 추가'도 켜지지 않음")

    await snap("3-added")
    end = time.monotonic() + 60
    while time.monotonic() < end:
        if await _chips_ok(page, expected_count):
            await _dismiss_overlay(page)
            return image.name
        await page.wait_for_timeout(1000)
    raise TimeoutError("채팅 칸에 이미지 칩이 붙지 않음")


async def attach_many(page, images: list[Path], timeout_s: float = 90, shots: Path | None = None) -> list[str]:
    """기존 칩을 비운 뒤 images 를 순서대로 모두 채팅 칸에 붙인다."""
    await clear_chips(page)
    names: list[str] = []
    for idx, img in enumerate(images, start=1):
        prefix = f"r{idx}-" if len(images) > 1 else ""
        names.append(await attach_one(page, img, idx, timeout_s=timeout_s, shots=shots, tag_prefix=prefix))
    return names


async def attach(page, image: Path, timeout_s: float = 90, shots: Path | None = None) -> str:
    """시작 이미지를 채팅 칸에 붙인다. 업로드 이름(고유)을 돌려준다."""
    names = await attach_many(page, [image], timeout_s=timeout_s, shots=shots)
    return names[0]


async def _download_image(page, src: str, out: Path) -> Path:
    """생성된 이미지(/asb/ → =s0)를 authenticated page.request 로 내려받는다."""
    url = agent._full_size_src(src)  # noqa: SLF001
    if not _is_allowed_download_host(url):
        raise RuntimeError(f"허용되지 않은 이미지 호스트: {url}")
    resp = await page.request.get(url, timeout=120_000, max_redirects=5)
    if not _is_allowed_download_host(str(resp.url)):
        raise RuntimeError(f"허용되지 않은 리다이렉트 호스트: {resp.url}")
    if resp.status >= 300:
        raise RuntimeError(f"이미지 다운로드 HTTP {resp.status}")
    body = await resp.body()
    if not body or body[4:8] == b"ftyp" or body[:4] == b"\x1a\x45\xdf\xa3":
        raise RuntimeError(f"이미지 응답이 비었거나 동영상 바이너리입니다 ({len(body)} B)")
    out.write_bytes(body)
    return out


_IMAGE_ASPECT_FALLBACK = {"2:3": "3:4"}
_IMAGE_MODEL_ALIAS = {
    "nano-pro": "nano-pro",
    "pro": "nano-pro",
    "nano2": "nano2",
    "nano21": "nano2",
    "flash": "nano2",
    "nano2-lite": "nano2-lite",
    "flash_lite": "nano2-lite",
    "image4": "nano-pro",
    "imagen4": "nano-pro",
}


def _resolve_image_aspect(aspect: str | None) -> tuple[ImageAspect, str]:
    raw = (aspect or "9:16").strip()
    mapped = _IMAGE_ASPECT_FALLBACK.get(raw, raw)
    return ImageAspect.from_cli(mapped), raw


def _resolve_image_model(model: str | None) -> ImageModel:
    key = (model or "nano-pro").strip().lower()
    alias = _IMAGE_MODEL_ALIAS.get(key, key)
    img_model = ImageModel.from_cli(alias)
    if img_model not in IMAGE_MODEL_MENU_MATCHERS:
        return ImageModel.GEM_PIX_2
    return img_model


def first_frame_diff(video: Path, image: Path) -> float | None:
    """결과 첫 프레임과 시작 이미지의 평균 차이(0~255, 작을수록 같다) — 시작 프레임을 지켰는지"""
    import subprocess
    try:
        f = video.with_suffix(".first.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-frames:v", "1", str(f)], check=False)
        if not f.exists():
            return None
        try:
            from PIL import Image, ImageChops, ImageStat
            a = Image.open(f).convert("L").resize((90, 160))
            b = Image.open(image).convert("L").resize((90, 160))
            return round(sum(ImageStat.Stat(ImageChops.difference(a, b)).mean), 1)
        except ImportError:
            # tools/gflow/.venv 에 PIL 이 없을 때는 ffmpeg rawvideo(90x160 gray)로 직접 비교
            r1 = subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-vf", "scale=90:160,format=gray", "-f", "rawvideo", "-"], capture_output=True, check=False)
            r2 = subprocess.run(["ffmpeg", "-v", "error", "-i", str(image), "-vf", "scale=90:160,format=gray", "-f", "rawvideo", "-"], capture_output=True, check=False)
            if r1.stdout and len(r1.stdout) == len(r2.stdout):
                return round(sum(abs(x - y) for x, y in zip(r1.stdout, r2.stdout)) / len(r1.stdout), 1)
            return None
    except Exception:
        return None


stage = {"at": "start"}


def default_profile() -> str:
    import tomllib
    f = default_home() / "config.toml"
    return (tomllib.loads(f.read_text("utf-8")).get("default_profile") if f.exists() else None) or "default"


async def _ensure_agent_project(page, state: dict, proj: str | None) -> str:
    """agent-only 편집 화면과 활성 Flow 프로젝트 UUID 를 보장한다(없으면 새 프로젝트 생성)."""
    if not proj:
        if state.get("project"):
            return str(state["project"])
        info = await create_project(page, "fluma")
        proj = info.project_id
    if state.get("project") != proj:
        await page.goto(MIGRATED_PROJECT_URL.format(project_id=proj), wait_until="domcontentloaded", timeout=60_000)
        ui_kind = await MigratedComposer().ensure_editor_for(page, proj, needs_classic=False)
        if ui_kind != "agent_only":
            raise RuntimeError(f"이 계정은 {ui_kind} 화면 — gflow 의 일반 경로를 쓴다")
        state["project"] = proj
    return proj


def _normalize_refs(job: dict) -> list[tuple[Path, str]]:
    raw_refs = job.get("refs")
    if raw_refs:
        out: list[tuple[Path, str]] = []
        for item in raw_refs:
            if isinstance(item, dict):
                out.append((Path(item["path"]), str(item.get("role") or "reference")))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                out.append((Path(item[0]), str(item[1])))
            else:
                out.append((Path(item), "reference"))
        return out
    if job.get("image"):
        return [(Path(job["image"]), "reference")]
    return []


async def _run_job(page, state: dict, job: dict) -> dict:
    """이미 열린 page 에서 단일 i2v / i2i 요청 실행 (단발 · 상주 워커 공용)."""
    cur_stage = {"at": "start"}
    job_kind = (job.get("kind") or "video").strip().lower()
    if job_kind not in ("video", "image"):
        return {"ok": False, "stage": "start", "error": f"지원하지 않는 kind: {job_kind}"}
    out = Path(job["out"]).resolve(); out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp())
    ts = time.strftime("%H%M%S")
    refs = _normalize_refs(job)
    if job_kind == "video" and not refs:
        return {"ok": False, "stage": "start", "error": "video i2v 에는 시작 이미지가 필요합니다"}
    copied: list[tuple[Path, str]] = []
    for idx, (src_p, role) in enumerate(refs, start=1):
        up = tmp / f"fluma_{ts}_{idx}_{src_p.name}"     # 같은 이름 에셋과 헷갈리지 않게
        shutil.copy(src_p, up)
        copied.append((up, role))

    try:
        try:
            proj = await _ensure_agent_project(page, state, job.get("project"))
        except Exception as e:
            return {"ok": False, "stage": "start", "error": str(e)[:400]}

        composer = agent.AgentOnlyComposer()
        shots = out.parent / "steps"; shots.mkdir(exist_ok=True)
        if job_kind == "video":
            v_aspect = Aspect.LANDSCAPE if job.get("aspect") == "16:9" else Aspect.PORTRAIT
            v_model = VideoModel(job.get("model", "veo_3_1_lite"))
            snap = await composer.apply_defaults(
                page, section="video", aspect_ligature=ASPECT_LIGATURE[v_aspect], count=1,
                model=VIDEO_MODEL_MENU_MATCHERS[v_model], confirm=agent._confirm_setting(),  # noqa: SLF001
            )
            prompt_text = directive(job["prompt"], int(job.get("sec", 4)), v_aspect.value)
            budget_s = float(job.get("timeout", 900))
        else:
            img_aspect_enum, img_aspect_label = _resolve_image_aspect(job.get("aspect"))
            img_model = _resolve_image_model(job.get("model"))
            snap = await composer.apply_defaults(
                page, section="image", aspect_ligature=IMAGE_ASPECT_LIGATURE[img_aspect_enum], count=1,
                model=IMAGE_MODEL_MENU_MATCHERS[img_model], confirm=agent._confirm_setting(),  # noqa: SLF001
            )
            prompt_text = image_directive(job["prompt"], img_aspect_label, refs)
            budget_s = float(job.get("timeout", 600))

        cur_stage["at"] = "attach"
        try:
            try:
                if copied:
                    uploaded_names = await attach_many(page, [p for p, _ in copied], shots=shots)
                else:
                    await clear_chips(page)
                    uploaded_names = []
            except Exception:
                await page.screenshot(path=str(shots / "fail.png"))
                raise
            if job.get("dry"):                                   # $0 — 붙이기까지만, 제출하지 않는다
                await page.screenshot(path=str(shots / "dry-attached.png"))
                return {
                    "ok": True, "dry": True, "kind": job_kind,
                    "uploaded": uploaded_names[0] if len(uploaded_names) == 1 else uploaded_names,
                    "uploaded_list": uploaded_names, "project_id": proj, "steps": str(shots),
                }
            cur_stage["at"] = "generate"
            (media,) = await composer.generate(page, prompt_text, kind=job_kind, count=1, budget_s=budget_s)
        finally:
            await agent._restore_quietly(composer, page, snap)  # noqa: SLF001

        cur_stage["at"] = "download"
        if job_kind == "video":
            async def save(_uuid: str, data: bytes) -> Path:
                out.write_bytes(data)
                return out
            await agent.download_video(page, media.src, media.uuid, save)
            cur_stage["at"] = "done"
            diff_val = None
            try:
                diff_val = first_frame_diff(out, refs[0][0])
            except Exception:
                pass
            return {
                "ok": True, "stage": "done", "kind": "video", "path": str(out), "media_id": media.uuid,
                "project_id": proj, "uploaded": uploaded_names[0], "first_frame_diff": diff_val,
            }

        await _download_image(page, media.src, out)
        cur_stage["at"] = "done"
        return {
            "ok": True, "stage": "done", "kind": "image", "path": str(out), "media_id": media.uuid,
            "project_id": proj, "uploaded": uploaded_names,
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "stage": cur_stage["at"], "error": f"{type(e).__name__}: {str(e)[:400]}"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _job_from_args(a: argparse.Namespace) -> dict:
    refs = []
    for raw in a.ref or []:
        if "::" in raw:
            p, r = raw.split("::", 1)
            refs.append({"path": p, "role": r})
        else:
            refs.append({"path": raw, "role": "reference"})
    if not refs and a.image:
        refs.append({"path": a.image, "role": "reference"})
    model = a.model or ("veo_3_1_lite" if a.kind == "video" else "nano-pro")
    return {
        "kind": a.kind, "project": a.project, "image": a.image, "refs": refs,
        "prompt": a.prompt, "out": a.out, "aspect": a.aspect,
        "sec": a.sec, "model": model, "timeout": a.timeout, "dry": a.dry,
    }


async def run(a) -> dict:
    t = UiAutomationTransport()
    await t.setup(profile_subdir(default_home(), a.profile or default_profile()))
    try:
        return await _run_job(t._page, {}, _job_from_args(a))  # noqa: SLF001
    finally:
        await t.teardown()


async def serve(profile: str | None) -> None:
    """상주 워커: stdin JSON 줄마다 브라우저를 재시작하지 않고 순차 실행."""
    t = UiAutomationTransport()
    await t.setup(profile_subdir(default_home(), profile or default_profile()))
    state: dict = {}
    try:
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                job = json.loads(line)
                res = await _run_job(t._page, state, job)  # noqa: SLF001
            except Exception as e:  # noqa: BLE001
                res = {"ok": False, "stage": "start", "error": f"{type(e).__name__}: {str(e)[:400]}"}
            print("FLUMA_AGENT_I2V " + json.dumps(res, ensure_ascii=False), flush=True)
    finally:
        await t.teardown()


def main() -> None:
    if os.name != "nt" and not os.environ.get("_FLUMA_IN_XVFB"):
        xvfb = shutil.which("xvfb-run")
        if xvfb:
            os.environ.pop("WAYLAND_DISPLAY", None)
            os.environ["XDG_SESSION_TYPE"] = "x11"
            os.environ["GDK_BACKEND"] = "x11"
            os.environ["QT_QPA_PLATFORM"] = "xcb"
            os.environ.setdefault("GFLOW_CLI_BROWSER_WINDOW_POSITION", "-30000,-30000")
            os.environ["_FLUMA_IN_XVFB"] = "1"
            os.execvp(xvfb, [xvfb, "-a", "-s", "-screen 0 1920x1080x24", sys.executable, *sys.argv])
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", action="store_true", help="stdin JSONL 상주 워커 모드(세션 재사용)")
    ap.add_argument("--kind", choices=["video", "image"], default="video")
    ap.add_argument("--project"); ap.add_argument("--image")
    ap.add_argument("--ref", action="append", default=[], help="이미지 참조(경로::역할, 반복 가능)")
    ap.add_argument("--prompt"); ap.add_argument("--out")
    ap.add_argument("--aspect", default="9:16")
    ap.add_argument("--sec", type=int, default=4); ap.add_argument("--model", default=None)
    ap.add_argument("--profile", default=None, help="기본: gflow config.toml 의 default_profile"); ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--dry", action="store_true", help="붙이기까지만 하고 제출하지 않는다($0)")
    a = ap.parse_args()
    if a.server:
        asyncio.run(serve(a.profile))
        return
    if a.kind == "video":
        if not (a.project and a.image and a.prompt and a.out):
            ap.error("video 모드는 --project, --image, --prompt, --out 가 필요합니다(--server 제외)")
    elif not (a.prompt and a.out):
        ap.error("image 모드는 --prompt, --out 가 필요합니다(--server 제외)")
    try:
        r = asyncio.run(run(a))
    except Exception as e:  # noqa: BLE001
        r = {"ok": False, "stage": stage["at"], "error": f"{type(e).__name__}: {str(e)[:400]}"}
    print("FLUMA_AGENT_I2V " + json.dumps(r, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
