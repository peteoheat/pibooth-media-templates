# -*- coding: utf-8 -*-
"""The row of template icons shown on the wait screen."""

import os.path as osp

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

BAR_COLOR = (25, 25, 25)
TILE_COLOR = (60, 60, 60)
SELECTED_COLOR = (255, 255, 255)
TYPE_COLORS = {
    'single': (66, 133, 244),
    'collage': (52, 168, 83),
    'animation': (251, 140, 0),
    'video': (219, 68, 85),
    'wigglegram': (142, 84, 233),
}
MIN_TILE = 0.65  # a tile is never narrower than this fraction of the bar height


def compute_layout(count, selected, width, height):
    """Where the tiles go in a bar of ``width`` x ``height`` pixels.

    When there are more templates than fit, a window of tiles that always
    contains the selected one is shown.

    :return: (index of first visible template, [(x, y, w, h) per visible tile])
    """
    if count <= 0:
        return 0, []
    fit = max(1, int(width // (height * MIN_TILE)))
    visible = min(count, fit)
    first = min(max(0, selected - visible // 2), count - visible)
    tile_w = min(int(height * 1.35), width // visible)  # Wide enough for a label
    left = (width - tile_w * visible) // 2
    pad = max(2, height // 12)
    rects = [(left + i * tile_w + pad // 2, pad, tile_w - pad, height - 2 * pad) for i in range(visible)]
    return first, rects


def hit_test(count, selected, width, height, pos):
    """Index of the template under ``pos`` (relative to the bar), or None."""
    first, rects = compute_layout(count, selected, width, height)
    for offset, (x, y, w, h) in enumerate(rects):
        if x <= pos[0] < x + w and y <= pos[1] < y + h:
            return first + offset
    return None


# --------------------------------------------------------------------------
# Icons
# --------------------------------------------------------------------------

def _glyph(draw, kind, box, color):
    """A simple pictogram of the template type, centred in ``box``."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    line = max(2, w // 14)

    def rect(a, b, c, d, **kw):
        draw.rounded_rectangle((x0 + a * w, y0 + b * h, x0 + c * w, y0 + d * h), radius=line, **kw)

    if kind == 'single':
        rect(0.2, 0.1, 0.8, 0.9, outline=color, width=line)
        draw.ellipse((x0 + 0.38 * w, y0 + 0.28 * h, x0 + 0.62 * w, y0 + 0.46 * h), fill=color)
        draw.pieslice((x0 + 0.3 * w, y0 + 0.5 * h, x0 + 0.7 * w, y0 + 0.95 * h), 180, 360, fill=color)
    elif kind == 'collage':
        for col in (0.1, 0.53):
            for row in (0.1, 0.53):
                rect(col, row, col + 0.37, row + 0.37, fill=color)
    elif kind == 'animation':
        for i, shift in enumerate((0.0, 0.14, 0.28)):
            rect(0.1 + shift, 0.2 - shift / 2, 0.52 + shift, 0.62 - shift / 2 + 0.28,
                 outline=color, width=line, fill=None if i < 2 else color)
    elif kind == 'video':
        rect(0.08, 0.25, 0.65, 0.75, fill=color)
        draw.polygon([(x0 + 0.7 * w, y0 + 0.5 * h), (x0 + 0.95 * w, y0 + 0.3 * h),
                      (x0 + 0.95 * w, y0 + 0.7 * h)], fill=color)
    else:  # wigglegram: two offset frames with arrows
        rect(0.05, 0.25, 0.55, 0.75, outline=color, width=line)
        rect(0.45, 0.25, 0.95, 0.75, fill=color)


def render_icon(template, size):
    """Square PIL icon for a template: its own ``icon`` file, otherwise a
    pictogram over a darkened thumbnail of its background (if any)."""
    if template.icon:
        try:
            return ImageOps.fit(Image.open(template.icon).convert('RGBA'), (size, size),
                                Image.Resampling.LANCZOS)
        except OSError:
            pass

    color = TYPE_COLORS.get(template.type, TILE_COLOR)
    icon = Image.new('RGBA', (size, size), color + (255,))
    if template.background and osp.isfile(template.background):
        try:
            thumb = ImageOps.fit(Image.open(template.background).convert('RGB'), (size, size),
                                 Image.Resampling.BILINEAR)
            icon = ImageEnhance.Brightness(thumb).enhance(0.55).convert('RGBA')
        except OSError:
            pass
    draw = ImageDraw.Draw(icon)
    margin = size // 5
    _glyph(draw, template.type, (margin, margin, size - margin, size - margin), (255, 255, 255, 235))

    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 6, fill=255)
    icon.putalpha(mask)
    return icon


# --------------------------------------------------------------------------
# pygame bar
# --------------------------------------------------------------------------

class TemplateBar(object):

    """Draws the template tiles at the bottom (or top) of the pibooth window."""

    def __init__(self, templates, position='bottom', height_ratio=0.18, show_labels=True):
        self.templates = templates
        self.position = position
        self.height_ratio = height_ratio
        self.show_labels = show_labels
        self._cache = {}
        self._icons = {}

    def bar_height(self, window_height):
        return max(48, int(window_height * self.height_ratio))

    def rect(self, window_size):
        """(x, y, w, h) of the bar inside a window."""
        width, height = window_size
        bar_h = self.bar_height(height)
        return (0, height - bar_h if self.position != 'top' else 0, width, bar_h)

    def locate(self, window_size, selected, pos):
        """Template index under a window position, or None."""
        x, y, w, h = self.rect(window_size)
        if not (x <= pos[0] < x + w and y <= pos[1] < y + h):
            return None
        return hit_test(len(self.templates), selected, w, h, (pos[0] - x, pos[1] - y))

    def _icon_surface(self, pygame, index, size):
        key = (index, size)
        if key not in self._icons:
            icon = render_icon(self.templates[index], size)
            self._icons[key] = pygame.image.frombuffer(icon.tobytes(), icon.size, 'RGBA').convert_alpha()
        return self._icons[key]

    def surface(self, pygame, window_size, selected):
        """The bar, drawn once per (size, selection) and cached."""
        key = (window_size, selected)
        if key in self._cache:
            return self._cache[key]
        self._cache = {key: None}  # Keep only the current one
        _, _, width, height = self.rect(window_size)
        bar = pygame.Surface((width, height))
        bar.fill(BAR_COLOR)

        first, rects = compute_layout(len(self.templates), selected, width, height)
        label_h = int(height * 0.22) if self.show_labels else 0
        font = pygame.font.Font(None, max(14, label_h)) if self.show_labels else None
        for offset, (x, y, w, h) in enumerate(rects):
            index = first + offset
            is_selected = index == selected
            tile = pygame.Rect(x, y, w, h)
            pygame.draw.rect(bar, SELECTED_COLOR if is_selected else TILE_COLOR, tile,
                             width=0 if is_selected else 2, border_radius=h // 8)
            icon_size = max(8, min(w, h - label_h) - 2 * max(4, h // 14))
            icon = self._icon_surface(pygame, index, icon_size)
            bar.blit(icon, icon.get_rect(midtop=(tile.centerx, tile.top + max(4, h // 14))))
            if font:
                name = self.templates[index].name
                label = font.render(name, True, (20, 20, 20) if is_selected else (235, 235, 235))
                if label.get_width() > w - 6:  # Squeeze long names instead of overflowing
                    label = pygame.transform.smoothscale(label, (w - 6, label.get_height()))
                bar.blit(label, label.get_rect(midbottom=(tile.centerx, tile.bottom - 3)))

        self._cache[key] = bar
        return bar

    def draw(self, pygame, win, selected):
        size = win.surface.get_size()
        x, y, _, _ = self.rect(size)
        win.surface.blit(self.surface(pygame, size, selected), (x, y))
