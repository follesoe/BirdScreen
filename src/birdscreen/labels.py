"""Render our own title + species labels onto a generated scene (Pillow).

Used with the "no-labels" prompt mode: Gemini paints only the birds and scenery
(it renders text poorly, especially the flash models), and we composite reliable,
correctly-spelled captions ourselves into translucent header/footer bands.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from birdscreen.poster import Bird

_FONT_DIR = Path("/System/Library/Fonts/Supplemental")
_SERIF = _FONT_DIR / "Georgia.ttf"
_SERIF_BOLD = _FONT_DIR / "Georgia Bold.ttf"
_SERIF_ITALIC = _FONT_DIR / "Georgia Italic.ttf"

_INK = (58, 50, 40)
_MAX_PER_ROW = 5  # species labels per legend row
_MIN_TITLE_SIZE = 16  # don't shrink the title font below this

type _Font = ImageFont.FreeTypeFont | ImageFont.ImageFont


def _font(path: Path, size: int) -> _Font:
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def _sample_parchment(img: Image.Image) -> tuple[int, int, int]:
    rgb = img.convert("RGB")
    w, h = rgb.size
    pts = [(2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3)]
    r = g = b = 0
    for x, y in pts:
        pr, pg, pb = cast("tuple[int, int, int]", rgb.getpixel((x, y)))
        r, g, b = r + pr, g + pg, b + pb
    n = len(pts)
    return (r // n, g // n, b // n)


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: _Font) -> float:
    return draw.textbbox((0, 0), text, font=font)[2]


def compose_poster(
    scene_path: str | Path,
    dst: str | Path,
    title: str,
    birds: list[Bird],
    *,
    size: tuple[int, int] = (3840, 2160),
) -> Path:
    """Mat the scene on parchment and add ``title`` (top) + species legend (bottom).

    The scene is placed in the middle with solid parchment margins, so the title
    and labels sit in dedicated space and never overlap the illustration.
    """
    width, height = size
    scene = Image.open(scene_path).convert("RGB")
    parchment = _sample_parchment(scene)

    # Slim parchment margins for the text; the artwork fills the rest.
    top_h, bot_h, side = int(height * 0.06), int(height * 0.095), int(width * 0.012)
    area_w, area_h = width - 2 * side, height - top_h - bot_h

    # Cover-fit: fill the artwork area, cropping into the (intentionally generous)
    # margins the no-labels prompt asks for — so no letterboxing, more drawing.
    scale = max(area_w / scene.width, area_h / scene.height)
    nw, nh = round(scene.width * scale), round(scene.height * scale)
    scene = scene.resize((nw, nh), Image.Resampling.LANCZOS)
    cx, cy = (nw - area_w) // 2, (nh - area_h) // 2
    scene = scene.crop((cx, cy, cx + area_w, cy + area_h))

    canvas = Image.new("RGB", (width, height), parchment)
    canvas.paste(scene, (side, top_h))
    draw = ImageDraw.Draw(canvas)

    # Title centered in the top margin.
    tsize = int(top_h * 0.62)
    tfont = _font(_SERIF_BOLD, tsize)
    while _text_width(draw, title, tfont) > width * 0.8 and tsize > _MIN_TITLE_SIZE:
        tsize -= 3
        tfont = _font(_SERIF_BOLD, tsize)
    tw = _text_width(draw, title, tfont)
    draw.text(((width - tw) / 2, (top_h - tsize) / 2), title, font=tfont, fill=_INK)

    # Species legend in the bottom margin: common + italic Latin, in rows.
    n = len(birds)
    per_row = _MAX_PER_ROW if n > _MAX_PER_ROW else n
    rows = [birds[i : i + per_row] for i in range(0, n, per_row)]
    common_sz, sci_sz = 30, 23
    cfont, ifont = _font(_SERIF, common_sz), _font(_SERIF_ITALIC, sci_sz)
    row_h = bot_h / len(rows)
    for ri, row in enumerate(rows):
        col_w = width / len(row)
        y = height - bot_h + ri * row_h + row_h * 0.14
        for ci, bird in enumerate(row):
            center_x = ci * col_w + col_w / 2
            common = bird.common or bird.scientific
            cw = _text_width(draw, common, cfont)
            draw.text((center_x - cw / 2, y), common, font=cfont, fill=_INK)
            if bird.common:
                sw = _text_width(draw, bird.scientific, ifont)
                draw.text(
                    (center_x - sw / 2, y + common_sz * 1.12),
                    bird.scientific,
                    font=ifont,
                    fill=_INK,
                )

    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dst, "JPEG", quality=92)
    return dst
