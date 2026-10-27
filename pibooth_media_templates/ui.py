# -*- coding: utf-8 -*-
"""The row of template tiles shown over the wait screen.

The tiles are frosted-glass rounded squares floating over the scene, with a
white outline pictogram and a name, in the style of photobooth-app.
"""

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from . import icons

GLASS_TINT = (28, 64, 110)          # frosted blue
GLASS_TINT_SELECTED = (70, 120, 185)
GLASS_ALPHA = 0.62
WHITE = (255, 255, 255, 255)


def compute_layout(count, selected, width, height):
    """Where the tiles go in a bar of ``width`` x ``height`` pixels.

    Tiles are centred. When there are more templates than fit, a window of
    tiles that always contains the selected one is shown.

    :return: (index of first visible template, [(x, y, w, h) per visible tile])
    """
    if count <= 0:
        return 0, []
    gap = max(6, height // 12)
    tile_h = height - gap  # what is left is the margin under the tiles
    tile_w = int(tile_h * 0.95)
    visible = min(count, max(1, (width + gap) // (tile_w + gap)))
    first = min(max(0, selected - visible // 2), count - visible)
    left = (width - (tile_w * visible + gap * (visible - 1))) // 2
    rects = [(left + i * (tile_w + gap), 0, tile_w, tile_h) for i in range(visible)]
    return first, rects


def hit_test(count, selected, width, height, pos):
    """Index of the template under ``pos`` (relative to the bar), or None."""
    first, rects = compute_layout(count, selected, width, height)
    for offset, (x, y, w, h) in enumerate(rects):
        if x <= pos[0] < x + w and y <= pos[1] < y + h:
            return first + offset
    return None


# --------------------------------------------------------------------------
# Icons: white outline pictograms, drawn 4x larger then reduced for smooth edges
# --------------------------------------------------------------------------

def _glyph(kind, size):
    scale = 4
    big = size * scale
    image = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    line = max(2, int(7 * big / 100))

    def u(*values):
        return [v * big / 100.0 for v in values]

    def box(x0, y0, x1, y1, radius=8, **kw):
        draw.rounded_rectangle(u(x0, y0, x1, y1), radius=radius * big / 100.0, **kw)

    if kind == 'single':  # camera
        box(8, 30, 92, 86, 10, outline=WHITE, width=line)
        box(34, 16, 66, 31, 4, outline=WHITE, width=line)
        draw.ellipse(u(33, 41, 67, 75), outline=WHITE, width=line)
    elif kind == 'collage':
        box(10, 10, 42, 90, 6, outline=WHITE, width=line)
        box(54, 10, 90, 44, 6, outline=WHITE, width=line)
        box(54, 56, 90, 90, 6, outline=WHITE, width=line)
    elif kind == 'animation':  # GIF
        box(10, 14, 90, 86, 10, outline=WHITE, width=line)
        try:
            font = ImageFont.load_default(size=int(big * 0.34))
            draw.text(u(50, 51), "GIF", fill=WHITE, font=font, anchor='mm')
        except (TypeError, ValueError):  # Pillow < 10.1 has no sized default font
            box(28, 30, 72, 70, 4, outline=WHITE, width=line)
    elif kind == 'video':  # clapperboard
        box(12, 40, 88, 88, 6, outline=WHITE, width=line)
        box(12, 16, 88, 36, 4, outline=WHITE, width=line)
        for x in (26, 46, 66):
            draw.polygon(u(x, 16, x + 12, 16, x + 3, 36, x - 9, 36), fill=WHITE)
    else:  # wigglegram
        draw.rectangle(u(10, 18, 17, 82), fill=WHITE)
        draw.rectangle(u(25, 18, 32, 82), fill=WHITE)
        box(42, 18, 92, 82, 8, outline=WHITE, width=line)
        draw.polygon(u(50, 74, 63, 52, 71, 63, 77, 55, 85, 74), fill=WHITE)
        draw.ellipse(u(76, 28, 86, 38), fill=WHITE)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def render_icon(template, size, style=icons.DEFAULT_STYLE):
    """Square RGBA icon for a template: its own image file, otherwise its
    Material icon (``icon: photo_camera``), otherwise a drawn pictogram."""
    if template.icon:
        try:
            return ImageOps.fit(Image.open(template.icon).convert('RGBA'), (size, size),
                                Image.Resampling.LANCZOS)
        except OSError:
            pass
    if template.icon_name:
        try:
            return icons.render_material_icon(template.icon_name, size, style=style)
        except (KeyError, OSError):
            pass  # Font missing or unreadable: fall back to the drawn pictogram
    return _glyph(template.type, size)


# --------------------------------------------------------------------------
# pygame bar
# --------------------------------------------------------------------------

def _tobytes(pygame, surface):
    try:
        return pygame.image.tobytes(surface, 'RGB')
    except AttributeError:  # pygame < 2.1.3
        return pygame.image.tostring(surface, 'RGB')


class TemplateBar(object):

    """Draws the template tiles over the bottom (or top) of the pibooth window.

    pibooth does not repaint the wait screen every frame, so translucent tiles
    drawn repeatedly would stack up and turn opaque. The bar therefore keeps a
    snapshot of the clean screen under the tiles and only redraws them when the
    selection changes or pibooth repaints the screen underneath.
    """

    def __init__(self, templates, position='bottom', height_ratio=0.2, show_labels=True,
                 icon_style=icons.DEFAULT_STYLE):
        self.templates = templates
        self.position = position
        self.height_ratio = height_ratio
        self.show_labels = show_labels
        self.icon_style = icon_style if icon_style in icons.STYLES else icons.DEFAULT_STYLE
        self._icons = {}
        self._font = None
        self._font_key = None
        self.invalidate()

    def invalidate(self):
        """Forget the snapshot, e.g. when the screen has been repainted."""
        self._backdrop = None
        self._composed = None
        self._drawn = None

    def bar_height(self, window_height):
        return max(64, int(window_height * self.height_ratio))

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

    # -- drawing -------------------------------------------------------------

    def _icon_surface(self, pygame, index, size):
        key = (index, size)
        if key not in self._icons:
            icon = render_icon(self.templates[index], size, self.icon_style)
            self._icons[key] = pygame.image.frombuffer(icon.tobytes(), icon.size, 'RGBA').convert_alpha()
        return self._icons[key]

    def _label_font(self, pygame, w, h):
        """One font size for every label: the largest at which the longest name still fits."""
        key = (w, h)
        if self._font_key != key:
            fonts = None
            try:
                from pibooth import fonts
            except ImportError:
                pass
            best = None
            for template in self.templates:
                try:
                    font = fonts.get_pygame_font(template.name, fonts.CURRENT, w - 12, int(h * 0.27))
                except Exception:  # No pibooth (command line) or an unreadable font file
                    font = pygame.font.Font(None, int(h * 0.27))
                    font.set_bold(True)
                if best is None or font.get_height() < best.get_height():
                    best = font
            self._font, self._font_key = best, key
        return self._font

    def _glass_tile(self, pygame, backdrop, rect, index, selected):
        """One frosted tile: the blurred scene behind it, tinted, with rounded corners."""
        x, y, w, h = rect
        radius = max(6, h // 6)
        scale = 3
        crop = backdrop.crop((x, y, x + w, y + h)).filter(ImageFilter.GaussianBlur(max(4, h // 12)))
        custom = self.templates[index].color
        if custom:  # the selected tile is the same colour, lightened
            tint = tuple(int(c + (255 - c) * 0.3) for c in custom) if selected else custom
        else:
            tint = GLASS_TINT_SELECTED if selected else GLASS_TINT
        tile = Image.blend(crop, Image.new('RGB', crop.size, tint), GLASS_ALPHA).convert('RGBA')

        # Soft light from the top edge
        shine = Image.linear_gradient('L').resize((w, h)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        light = Image.new('RGBA', (w, h), (255, 255, 255, 0))
        light.putalpha(shine.point(lambda v: int(v * 0.16)))
        tile.alpha_composite(light)

        mask = Image.new('L', (w * scale, h * scale), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w * scale - 1, h * scale - 1),
                                               radius=radius * scale, fill=255)
        tile.putalpha(mask.resize((w, h), Image.Resampling.LANCZOS))
        if selected:
            ring = Image.new('RGBA', (w * scale, h * scale), (0, 0, 0, 0))
            ImageDraw.Draw(ring).rounded_rectangle((0, 0, w * scale - 1, h * scale - 1), radius=radius * scale,
                                                   outline=(255, 255, 255, 235), width=3 * scale)
            tile.alpha_composite(ring.resize((w, h), Image.Resampling.LANCZOS))

        surface = pygame.image.frombuffer(tile.tobytes(), tile.size, 'RGBA').convert_alpha()
        label_h = int(h * 0.27) if self.show_labels else 0
        icon_size = max(8, min(w - int(w * 0.3), h - label_h - int(h * 0.12)))
        icon = self._icon_surface(pygame, index, icon_size)
        surface.blit(icon, icon.get_rect(midtop=(w // 2, int(h * 0.1))))
        if self.show_labels:
            font = self._label_font(pygame, w, h)
            name = self.templates[index].name
            label = font.render(name, True, (255, 255, 255))
            shadow = font.render(name, True, (0, 0, 0))
            if label.get_width() > w - 8:  # Squeeze long names instead of overflowing
                size = (w - 8, label.get_height())
                label = pygame.transform.smoothscale(label, size)
                shadow = pygame.transform.smoothscale(shadow, size)
            centre = (w // 2, h - max(4, int(h * 0.15)))
            shadow.set_alpha(110)
            surface.blit(shadow, shadow.get_rect(center=(centre[0] + 1, centre[1] + 1)))
            surface.blit(label, label.get_rect(center=centre))
        return surface

    def _compose(self, pygame, backdrop, selected):
        pil = Image.frombytes('RGB', backdrop.get_size(), _tobytes(pygame, backdrop))
        result = backdrop.copy()
        first, rects = compute_layout(len(self.templates), selected, *backdrop.get_size())
        for offset, rect in enumerate(rects):
            index = first + offset
            result.blit(self._glass_tile(pygame, pil, rect, index, index == selected), rect[:2])
        return result

    def draw(self, pygame, win, selected):
        """Draw the tiles over whatever is on the window, only when needed."""
        if not self.templates:
            return
        screen = win.surface
        area = pygame.Rect(self.rect(screen.get_size()))
        current = _tobytes(pygame, screen.subsurface(area))
        if self._composed is not None and current == self._composed and selected == self._drawn:
            return  # Nothing changed since the tiles were drawn
        if self._backdrop is None or current != self._composed or self._backdrop.get_size() != area.size:
            self._backdrop = screen.subsurface(area).copy()  # pibooth repainted: take a new clean snapshot
        screen.blit(self._compose(pygame, self._backdrop, selected), area.topleft)
        self._composed = _tobytes(pygame, screen.subsurface(area))
        self._drawn = selected
