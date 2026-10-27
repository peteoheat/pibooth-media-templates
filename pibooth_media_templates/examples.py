# -*- coding: utf-8 -*-
"""Example templates written on first start (and by ``pibooth-media-templates init``).

Everything, including the pictures, is generated here so the package ships no
binary assets. Copy a folder and edit it to make your own template.
"""

import os
import os.path as osp
import random

from PIL import Image, ImageDraw, ImageFilter


def _gradient(size, stops):
    """Vertical gradient through ``stops`` = [(position 0-1, (r, g, b)), ...]."""
    width, height = size
    column = Image.new('RGB', (1, height))
    for y in range(height):
        t = y / max(1, height - 1)
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if p0 <= t <= p1:
                f = (t - p0) / max(1e-6, p1 - p0)
                column.putpixel((0, y), tuple(int(a + (b - a) * f) for a, b in zip(c0, c1)))
                break
    return column.resize(size)


def _sunset(size):
    image = _gradient(size, [(0, (255, 183, 94)), (0.5, (237, 80, 110)), (1, (72, 49, 120))])
    draw = ImageDraw.Draw(image)
    cx, cy, r = size[0] // 2, int(size[1] * 0.58), size[1] // 6
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 226, 150))
    return image.filter(ImageFilter.GaussianBlur(1))


def _night(size):
    image = _gradient(size, [(0, (6, 10, 40)), (1, (46, 30, 96))])
    draw = ImageDraw.Draw(image)
    rng = random.Random(7)
    for _ in range(size[0] * size[1] // 9000):
        x, y, r = rng.randrange(size[0]), rng.randrange(int(size[1] * 0.8)), rng.choice((1, 1, 2, 3))
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 230))
    return image


def _frame(size, color=(255, 255, 255, 255), width=None):
    """Transparent overlay with a border and rounded inner corners."""
    width = width or size[0] // 30
    layer = Image.new('RGBA', size, color)
    hole = Image.new('L', size, 0)
    ImageDraw.Draw(hole).rounded_rectangle((width, width, size[0] - width, size[1] - width),
                                           radius=width, fill=255)
    layer.putalpha(Image.eval(hole, lambda v: 255 - v))
    return layer


YAML = {}

YAML['classic_single'] = """\
name: Classic
type: single
icon: photo_camera             # any name from https://fonts.google.com/icons
# No background entry: the photo is kept exactly as the camera took it
overlay: frame.png
"""

YAML['sunset_single'] = """\
name: Sunset
type: single
icon: wb_twilight
color: "#c0392b"                # optional tile colour
background: background.jpg      # replaces what is behind the guests (needs pibooth-modnet)
"""

YAML['night_single'] = """\
name: Night Sky
type: single
icon: nights_stay
color: "#2c2c6c"
background: background.jpg
overlay: frame.png
"""

YAML['photo_strip'] = """\
name: Photo Strip
type: collage
captures: 3
size: [600, 1800]               # 2 x 6 inch strip at 300 dpi
canvas: {color: "#ffffff"}
layout: {preset: strip, margin: 30, gap: 20}   # room is made for pibooth's footer text automatically
# footer: false                 # uncomment to ignore the [PICTURE] footer_text1/2 in this template
# texts:                        # your own texts, placed anywhere on the picture
#   - {text: "{date:%d %B %Y}", y: 0.02, h: 0.04, color: "#000000"}
"""

YAML['grid_four'] = """\
name: Four Up
type: collage
captures: 4
size: [1800, 1200]              # 6 x 4 inch landscape at 300 dpi
canvas: {color: "#ffffff"}
layout: {preset: grid, margin: 40, gap: 30}
"""

YAML['mixed_backgrounds'] = """\
name: Two Worlds
type: collage
captures: 2
size: [1200, 1800]
canvas: {color: "#ffffff"}
slots:                          # each slot can use its own replacement background
  - {capture: 1, x: 0.05, y: 0.03, w: 0.9, h: 0.46, background: sunset.jpg}
  - {capture: 2, x: 0.05, y: 0.51, w: 0.9, h: 0.46, background: night.jpg}
"""

YAML['bounce'] = """\
name: Bounce
type: animation
captures: 4
animation: {format: gif, frame_ms: 350, boomerang: true, size: 800}
"""

YAML['wiggle'] = """\
name: Wiggle
type: wigglegram
captures: 3
wigglegram: {frame_ms: 140, align: true, size: 800}
"""

YAML['reel'] = """\
name: Reel
type: video
captures: 4
video: {fps: 25, frame_s: 0.9, fade_s: 0.3, size: 1280}
"""


def write_examples(folder, overwrite=False):
    """Create the example templates in ``folder``.

    :return: list of template folders written
    """
    made = []
    assets = {
        'classic_single': {'frame.png': lambda: _frame((1800, 1200))},
        'sunset_single': {'background.jpg': lambda: _sunset((1800, 1200))},
        'night_single': {'background.jpg': lambda: _night((1800, 1200)),
                         'frame.png': lambda: _frame((1800, 1200), (255, 214, 102, 255), 36)},
        'mixed_backgrounds': {'sunset.jpg': lambda: _sunset((1200, 800)), 'night.jpg': lambda: _night((1200, 800))},
    }
    for key, text in YAML.items():
        target = osp.join(folder, key)
        if osp.exists(osp.join(target, 'template.yaml')) and not overwrite:
            continue
        os.makedirs(target, exist_ok=True)
        with open(osp.join(target, 'template.yaml'), 'w', encoding='utf-8') as fp:
            fp.write(text)
        for filename, maker in assets.get(key, {}).items():
            image = maker()
            image.save(osp.join(target, filename), quality=92) if filename.endswith('.jpg') \
                else image.save(osp.join(target, filename))
        made.append(target)
    return made
