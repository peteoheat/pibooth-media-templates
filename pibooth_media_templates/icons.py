# -*- coding: utf-8 -*-
"""Material icons by name, as in photobooth-app (``icon: photo_camera``).

The classic Google Material Icons fonts (Apache-2.0, see
``data/LICENSE-material-icons.txt``) are bundled in outlined and filled styles,
so icons work offline. Browse the names at https://fonts.google.com/icons : most
are the same, but a few newer "Material Symbols" additions (for example
``animated_images`` and ``3d``) are not in the classic fonts.
"""

import difflib
import os.path as osp
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

DATA = osp.join(osp.dirname(osp.abspath(__file__)), 'data')
STYLES = {
    'outlined': ('MaterialIconsOutlined-Regular.otf', 'MaterialIconsOutlined-Regular.codepoints'),
    'filled': ('MaterialIcons-Regular.ttf', 'MaterialIcons-Regular.codepoints'),
}
DEFAULT_STYLE = 'outlined'

# photobooth-app's defaults, using the classic names where it uses newer ones
DEFAULT_ICONS = {
    'single': 'photo_camera',
    'collage': 'auto_awesome_mosaic',
    'animation': 'gif',            # photobooth-app: animated_images
    'video': 'movie',
    'wigglegram': '3d_rotation',   # photobooth-app: 3d
}


@lru_cache(maxsize=None)
def codepoints(style=DEFAULT_STYLE):
    """{icon name: code point} for one style."""
    names = {}
    with open(osp.join(DATA, STYLES[style][1]), 'r', encoding='ascii') as fp:
        for line in fp:
            parts = line.split()
            if len(parts) == 2:
                names[parts[0]] = int(parts[1], 16)
    return names


def all_names():
    return set(codepoints('outlined')) | set(codepoints('filled'))


def is_icon_name(name):
    return name in all_names()


def suggest(name, count=3):
    """Closest icon names, for a helpful error message."""
    return difflib.get_close_matches(name, sorted(all_names()), n=count, cutoff=0.6)


@lru_cache(maxsize=16)
def _font(style, pixels):
    return ImageFont.truetype(osp.join(DATA, STYLES[style][0]), pixels)


def render_material_icon(name, size, color=(255, 255, 255, 255), style=DEFAULT_STYLE):
    """Square RGBA image of the icon ``name``, drawn smoothly in ``color``.

    A name missing from the chosen style is drawn in the other style.

    :raises KeyError: for a name that is in neither style
    """
    if name not in codepoints(style):
        style = 'filled' if style == 'outlined' else 'outlined'
    code = codepoints(style)[name]
    scale = 4
    big = size * scale
    layer = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((big / 2, big / 2), chr(code), font=_font(style, big), fill=color, anchor='mm')
    return layer.resize((size, size), Image.Resampling.LANCZOS)
