#!/usr/bin/env python3
"""agent-only Flow 화면에서 i2v(시작 프레임 → 영상) — gflow-cli 0.98 이 거절하는 경로(#1220)를 직접 몬다.

gflow 의 부품을 그대로 쓴다: 브라우저 · 프로필(UiAutomationTransport), 편집 화면(ensure_editor_for),
에이전트 설정(apply_defaults: 9:16 · 1개 · 모델), 제출 · 크레딧 확인 창 승인(요청보다 많이 청구하면 거부) · 완료 감지(generate),
다운로드(download_video). 새로 하는 일은 제출 전에 '+ → 미디어 업로드 → 프롬프트에 추가'로 시작 이미지를 붙이는 것뿐.

  tools/gflow/.venv/bin/python engine/gen/flow_agent_i2v.py --project <uuid> --image s01.png --prompt "..." --out take.mp4 \
      [--sec 4] [--model veo_3_1_lite] [--profile poi-happywha]
크레딧을 쓴다(--dry 는 붙이기까지만, $0). 결과 JSON 한 줄(ok · stage · path · media_id · first_frame_diff)을 마지막에 찍는다.
stage: attach(제출 전 실패 — 청구 없음) · generate(제출 뒤 실패 — 청구됐을 수 있음) · done.
gflow 의 gflow-cli venv 파이썬으로 돌린다(gflow_cli 를 불러 쓴다). engine/gen/video.py 의 Flow 경로가 agent-only 계정에서 부른다.
측정(2026-11-14): Veo 3.1 Lite 의 첫 프레임 i2v 는 8초만 된다 — 다른 길이는 에이전트가 되묻고(선택 질문) 그 뒤 확인 창을 gflow 가 거부한다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from gflow_cli.api.transports import agent_only_composer as agent
from gflow_cli.api.transports.migrated_composer import (
    ASPECT_LIGATURE,
    MIGRATED_PROJECT_URL,
    VIDEO_MODEL_MENU_MATCHERS,
    MigratedComposer,
)
from gflow_cli.api.transports.ui_automation import UiAutomationTransport
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


import re  # noqa: E402

_COUNT_RE = re.compile(r"(\d+)\s*(?:개|편|videos?\b|clips?\b|generations?\b|видео)", re.I)
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


async def attach(page, image: Path, timeout_s: float = 90, shots: Path | None = None) -> str:
    """시작 이미지를 채팅 칸에 붙인다. 업로드 이름(고유)을 돌려준다."""
    async def snap(tag: str) -> None:
        if shots:
            await page.screenshot(path=str(shots / f"{tag}.png"))
    chips = page.locator(f"{BOX} flow-image-ingredient-chip")
    while await chips.count():                          # 지난 시도에서 남은 칩은 지운다(다른 그림이 같이 가지 않게)
        n = await chips.count()
        await page.locator(f"{BOX} flow-ingredient-bar ~ button:has(mat-icon:text-is('close')), {BOX} button:has(mat-icon:text-is('close'))").first.click()
        await page.wait_for_timeout(600)
        if await chips.count() >= n:
            raise RuntimeError("채팅 칸에 남은 첨부를 지우지 못함")
    await page.locator(ADD).first.click()
    await page.wait_for_timeout(1000)
    async with page.expect_file_chooser(timeout=15_000) as fc:
        await page.locator("button:has(mat-icon:text-is('upload'))").last.click()
    await (await fc.value).set_files(str(image))
    await snap("1-uploading")
    # 측정(2026-11-14): 채팅 칸 '+'에서 올리면 업로드가 끝날 때 칸에 자동으로 붙고 메뉴가 닫힌다.
    # 붙지 않고 목록에 남는 경우만 골라서 '프롬프트에 추가'를 누른다.
    # 목록 항목은 role 이 menuitem 이 아니다(측정) — 겹쳐 뜬 창 안에서 이름 글자로 찾는다
    item = page.locator(f".cdk-overlay-pane :is([role=menuitem], [role=option], button, li, div[tabindex]):has-text('{image.name}')").last
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        if (await chips_ready(page)) == [True]:
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
    while time.monotonic() < end:                        # 이미 자동으로 붙었으면(측정: 버튼은 꺼진 채) 끝, 아니면 버튼이 켜지면 누른다
        if (await chips_ready(page)) == [True]:
            await page.keyboard.press("Escape")
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
    end = time.monotonic() + 60                          # 칩에 그림이 실릴 때까지
    while time.monotonic() < end:
        if (await chips_ready(page)) == [True]:
            return image.name
        await page.wait_for_timeout(1000)
    raise TimeoutError("채팅 칸에 이미지 칩이 붙지 않음")


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


async def run(a) -> dict:
    out = Path(a.out).resolve(); out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp())
    up = tmp / f"fluma_{time.strftime('%H%M%S')}_{Path(a.image).name}"     # 같은 이름 에셋과 헷갈리지 않게
    shutil.copy(a.image, up)
    t = UiAutomationTransport()
    await t.setup(profile_subdir(default_home(), a.profile or default_profile()))
    page = t._page  # noqa: SLF001
    try:
        await page.goto(MIGRATED_PROJECT_URL.format(project_id=a.project), wait_until="domcontentloaded", timeout=60_000)
        kind = await MigratedComposer().ensure_editor_for(page, a.project, needs_classic=False)
        if kind != "agent_only":
            return {"ok": False, "error": f"이 계정은 {kind} 화면 — gflow 의 일반 i2v 를 쓴다"}
        composer = agent.AgentOnlyComposer()
        model = VideoModel(a.model)
        snap = await composer.apply_defaults(page, section="video", aspect_ligature=ASPECT_LIGATURE[Aspect.PORTRAIT], count=1,
                                             model=VIDEO_MODEL_MENU_MATCHERS[model], confirm=agent._confirm_setting())  # noqa: SLF001
        shots = out.parent / "steps"; shots.mkdir(exist_ok=True)
        stage["at"] = "attach"
        try:
            try:
                name = await attach(page, up, shots=shots)
            except Exception:
                await page.screenshot(path=str(shots / "fail.png"))
                raise
            if a.dry:                                   # $0 — 붙이기까지만, 제출하지 않는다
                await page.screenshot(path=str(shots / "dry-attached.png"))
                return {"ok": True, "dry": True, "uploaded": name, "steps": str(shots)}
            stage["at"] = "generate"
            (media,) = await composer.generate(page, directive(a.prompt, a.sec, "9:16"), kind="video", count=1, budget_s=a.timeout)
        finally:
            await agent._restore_quietly(composer, page, snap)  # noqa: SLF001

        stage["at"] = "download"
        async def save(_uuid: str, data: bytes) -> Path:
            out.write_bytes(data)
            return out
        await agent.download_video(page, media.src, media.uuid, save)
        stage["at"] = "done"

        diff_val = None
        try:
            diff_val = first_frame_diff(out, Path(a.image))
        except Exception:
            pass

        return {"ok": True, "stage": "done", "path": str(out), "media_id": media.uuid, "project_id": a.project, "uploaded": name,
                "first_frame_diff": diff_val}
    finally:
        await t.teardown()
        shutil.rmtree(tmp, ignore_errors=True)


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
    ap.add_argument("--project", required=True); ap.add_argument("--image", required=True)
    ap.add_argument("--prompt", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--sec", type=int, default=4); ap.add_argument("--model", default="veo_3_1_lite")
    ap.add_argument("--profile", default=None, help="기본: gflow config.toml 의 default_profile"); ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--dry", action="store_true", help="붙이기까지만 하고 제출하지 않는다($0)")
    a = ap.parse_args()
    try:
        r = asyncio.run(run(a))
    except Exception as e:  # noqa: BLE001
        r = {"ok": False, "stage": stage["at"], "error": f"{type(e).__name__}: {str(e)[:400]}"}
    print("FLUMA_AGENT_I2V " + json.dumps(r, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
