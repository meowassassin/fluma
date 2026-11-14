#!/usr/bin/env python3
"""Craft 원자적 디자인 프리미티브 (Design Primitives for Craft) —
템플릿에 갇히지 않고, 사용자가 원하는 어떤 디자인이든 자유롭게 조합할 수 있는 고품질 시각 원자들.
HTML 슬롭/raw SVG 스크립팅 대신, 검증된 디자인 토큰(비례, 여백, 타이포그래피, 컬러 하모니)을 적용하여
Craft 도구(FigCraft, VectorCraft, EffectCraft)의 프로젝트 파일(.figcraft, .vectorcraft, .ecproj)을 생성한다.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
FONTS_DIR = ROOT / "engine" / "assets" / "fonts"

# 검증된 컬러 토큰
COLORS = {
    "success": {"bg": (16, 185, 129), "hex": "#10B981", "fg": (255, 255, 255)},   # Emerald
    "error": {"bg": (239, 68, 68), "hex": "#EF4444", "fg": (255, 255, 255)},       # Crimson
    "info": {"bg": (59, 130, 246), "hex": "#3B82F6", "fg": (255, 255, 255)},        # Blue
    "dark": {"bg": (24, 23, 22), "hex": "#181716", "fg": (255, 255, 255)},          # Slate Black
    "surface": {"bg": (255, 255, 255), "hex": "#FFFFFF", "fg": (24, 23, 22)},
    "cream_bg": {"bg": (244, 238, 226), "hex": "#F4EEE2", "fg": (30, 26, 23)},
}


def get_font(name: str = "bold", size: int = 32) -> ImageFont.FreeTypeFont:
    font_files = {
        "black": FONTS_DIR / "Pretendard-Black.otf",
        "bold": FONTS_DIR / "Pretendard-Bold.otf",
        "regular": FONTS_DIR / "Pretendard-Regular.otf",
        "mono": FONTS_DIR / "JetBrainsMono-ExtraBold.otf",
        "serif": FONTS_DIR / "GowunBatang-Bold.ttf",
    }
    target = font_files.get(name, font_files["bold"])
    if target.exists():
        return ImageFont.truetype(str(target), size)
    return ImageFont.load_default()


def make_phone_mockup(screen_src: Path | str, out_path: Path, work_dir: Path, oid: str = "phone") -> dict:
    """FigCraft를 호출하여 실제 스크린샷이 담긴 초정밀 스마트폰 벡터 목업(투명 PNG + .figcraft) 생성"""
    from craft.adapters.figcraft import ui_mock
    return ui_mock(
        {"id": oid, "type": "ui_mock", "device": "phone", "src": str(screen_src)},
        out_path,
        work_dir
    )


def make_pill_badge(text: str, status: str = "success", out_path: Path | None = None,
                    scale: int = 2, icon: str | None = None) -> Path:
    """모던 캡슐 상태 배지 (예: ✓ 25% 찢김 · 정상 인식) — 고해상도 안티에일리어싱 + 드롭 섀도우"""
    f = get_font("bold", 28 * scale)
    bbox = f.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    icon_w = 40 * scale
    pad_x = 24 * scale
    pad_y = 16 * scale
    w = tw + icon_w + pad_x * 2 + 10 * scale
    h = max(th + pad_y * 2, 64 * scale)

    # 섀도우를 위한 여유 캔버스
    sh_blur = 16 * scale
    canv_w = w + sh_blur * 2
    canv_h = h + sh_blur * 2

    # 투명 캔버스
    im = Image.new("RGBA", (canv_w, canv_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    # 부드러운 드롭 섀도우
    sh_box = [sh_blur, sh_blur + 4 * scale, sh_blur + w, sh_blur + h + 4 * scale]
    draw.rounded_rectangle(sh_box, radius=h // 2, fill=(0, 0, 0, 35))

    col = COLORS.get(status, COLORS["info"])
    box = [sh_blur, sh_blur, sh_blur + w, sh_blur + h]
    draw.rounded_rectangle(box, radius=h // 2, fill=(*col["bg"], 255))

    # 벡터 아이콘
    ic_cx = sh_blur + pad_x + icon_w // 2
    ic_cy = sh_blur + h // 2
    ic_r = 14 * scale

    if status == "success" or icon == "check":
        # Checkmark
        pts = [
            (ic_cx - ic_r * 0.6, ic_cy),
            (ic_cx - ic_r * 0.1, ic_cy + ic_r * 0.5),
            (ic_cx + ic_r * 0.7, ic_cy - ic_r * 0.5)
        ]
        draw.line(pts, fill=col["fg"], width=4 * scale, joint="curve")
    elif status == "error" or icon == "cross":
        # Cross (X)
        d = ic_r * 0.55
        draw.line([(ic_cx - d, ic_cy - d), (ic_cx + d, ic_cy + d)], fill=col["fg"], width=4 * scale)
        draw.line([(ic_cx + d, ic_cy - d), (ic_cx - d, ic_cy + d)], fill=col["fg"], width=4 * scale)

    # 텍스트
    tx = sh_blur + pad_x + icon_w + 6 * scale
    ty = sh_blur + (h - th) // 2 - bbox[1]
    draw.text((tx, ty), text, font=f, fill=col["fg"])

    if out_path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        im.save(out_path)
    return out_path


def make_card_container(width: int = 460, height: int = 1040, title: str = "", tag: str = "",
                        status_color: str = "#10B981", out_path: Path | None = None,
                        scale: int = 2) -> Path:
    """세련된 실험용 카드 컨테이너 — 카드 헤더, 케이스 태그, 구분 점선, 라운드 모서리"""
    w = width * scale
    h = height * scale
    pad = 20 * scale

    canv_w = w + 40 * scale
    canv_h = h + 40 * scale

    im = Image.new("RGBA", (canv_w, canv_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    x0, y0 = 20 * scale, 20 * scale
    r = 32 * scale

    # 카드 드롭 섀도우
    draw.rounded_rectangle([x0, y0 + 8 * scale, x0 + w, y0 + h + 8 * scale], radius=r, fill=(0, 0, 0, 20))
    # 카드 본체
    draw.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=r, fill=(255, 255, 255, 255), outline=(232, 227, 215, 255), width=2 * scale)

    # 헤더
    if tag or title:
        f_tag = get_font("bold", 18 * scale)
        f_title = get_font("black", 32 * scale)

        ty = y0 + 24 * scale
        if tag:
            draw.text((x0 + w // 2, ty), tag, font=f_tag, fill=(138, 131, 121), anchor="mm")
            ty += 28 * scale
        if title:
            draw.text((x0 + w // 2, ty), title, font=f_title, fill=status_color, anchor="mm")
            ty += 28 * scale

        # 구분선
        draw.line([(x0 + 20 * scale, ty), (x0 + w - 20 * scale, ty)], fill=(239, 236, 227), width=2 * scale)

    if out_path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        im.save(out_path)
    return out_path


def make_scan_hud(width: int = 400, height: int = 400, color: str = "#10B981", out_path: Path | None = None, scale: int = 2) -> Path:
    """카메라 스캔 HUD 브래킷과 스캔 빔"""
    w, h = width * scale, height * scale
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    # 4개 모서리 브래킷
    pad = 20 * scale
    b_len = 40 * scale
    b_w = 4 * scale

    # 좌상
    draw.line([(pad, pad), (pad + b_len, pad)], fill=color, width=b_w)
    draw.line([(pad, pad), (pad, pad + b_len)], fill=color, width=b_w)
    # 우상
    draw.line([(w - pad, pad), (w - pad - b_len, pad)], fill=color, width=b_w)
    draw.line([(w - pad, pad), (w - pad, pad + b_len)], fill=color, width=b_w)
    # 좌하
    draw.line([(pad, h - pad), (pad + b_len, h - pad)], fill=color, width=b_w)
    draw.line([(pad, h - pad), (pad, h - pad - b_len)], fill=color, width=b_w)
    # 우하
    draw.line([(w - pad, h - pad), (w - pad - b_len, h - pad)], fill=color, width=b_w)
    draw.line([(w - pad, h - pad), (w - pad, h - pad - b_len)], fill=color, width=b_w)

    if out_path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        im.save(out_path)
    return out_path
