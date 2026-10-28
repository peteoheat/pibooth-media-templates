# -*- coding: utf-8 -*-
"""Turn captures into the final still picture of a template."""

import threading
import logging
from functools import lru_cache
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .model import resolve

LOGGER = logging.getLogger("pibooth-media-templates")

LANCZOS = Image.Resampling.LANCZOS
BICUBIC = Image.Resampling.BICUBIC


# --------------------------------------------------------------------------
# Background replacement (delegates to pibooth-modnet when installed)
# --------------------------------------------------------------------------

class BackgroundReplacer(object):

    """Replace the camera background behind the guests with an image.

    The portrait matting is provided by the ``pibooth-modnet`` package, which
    is imported lazily so the plugin still works without it (backgrounds are
    then left untouched and a warning is logged).
    """

    def __init__(self, model_path='~/.config/pibooth/models/modnet.onnx', ref_size=512, threads=3, refine=True):
        self.model_path = model_path
        self.ref_size = ref_size
        self.threads = threads
        self.refine = refine
        self.ready = threading.Event()
        self._modnet = None
        self._processor = None
        self._themes = {}
        self._lock = threading.Lock()

    @property
    def available(self):
        return self._processor is not None

    def load(self):
        """Load the model (slow, run it in a thread). Always sets ``ready``."""
        try:
            import pibooth_modnet as modnet
            path = modnet.ensure_model(self.model_path)
            engine = modnet.MattingEngine(path, self.ref_size, self.threads, self.refine)
            engine.warmup()
            self._modnet = modnet
            self._processor = modnet.CaptureProcessor(engine)
            LOGGER.info("Media templates: background model ready")
        except ImportError:
            LOGGER.error("Media templates: backgrounds need pibooth-modnet (pip install pibooth-modnet), "
                         "captures will keep their own background")
        except Exception as ex:
            LOGGER.error("Media templates: background model could not be loaded: %s", ex)
        finally:
            self.ready.set()

    def replace(self, image, background, timeout=60.0):
        """Return ``image`` with its background replaced by the ``background`` file."""
        self.ready.wait(timeout)
        if not self.available:
            return image
        with self._lock:
            theme = self._themes.get(background)
            if theme is None:
                theme = self._themes[background] = self._modnet.Theme(background, background=background)
        return self._processor.process(image, theme)


# --------------------------------------------------------------------------
# Image helpers
# --------------------------------------------------------------------------

@lru_cache(maxsize=16)
def _load_rgba(path, size):
    image = Image.open(path)
    image = ImageOps.exif_transpose(image).convert('RGBA')
    return image if image.size == size else image.resize(size, LANCZOS)


@lru_cache(maxsize=8)
def _load_cover(path, size):
    image = ImageOps.exif_transpose(Image.open(path)).convert('RGB')
    return ImageOps.fit(image, size, LANCZOS)


def fit_image(image, width, height, mode='cover'):
    """Scale ``image`` into a width x height box. ``cover`` fills the box and
    crops the excess, ``contain`` keeps the whole image."""
    if mode == 'cover':
        return ImageOps.fit(image, (width, height), LANCZOS)
    scale = min(width / image.width, height / image.height)
    return image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), LANCZOS)


def apply_overlay(image, path):
    """Alpha-composite the overlay file, stretched to the image size."""
    overlay = _load_rgba(path, image.size)
    result = image.convert('RGBA')
    result.alpha_composite(overlay)
    return result.convert('RGB')


# --------------------------------------------------------------------------
# Text
# --------------------------------------------------------------------------

def _font_file(font_name):
    """Path of a font given by name or path (pibooth's resolver), or None."""
    if not font_name:
        return None
    try:
        from pibooth import fonts
        return fonts.get_filename(font_name)
    except Exception as ex:  # No pibooth (command line) or an unknown font
        LOGGER.warning("Media templates: font '%s' not usable (%s), using the default font", font_name, ex)
        return None


def _sized_default(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1 only has one fixed size
        return ImageFont.load_default()


def _sized_font(font_name, size):
    filename = _font_file(font_name)
    if filename:
        try:
            return ImageFont.truetype(filename, size)
        except OSError:
            pass
    return _sized_default(size)


def _fitted_font(text, font_name, width, height):
    """The largest font in which ``text`` fits a width x height box."""
    filename = _font_file(font_name)
    if filename:
        try:
            from pibooth import fonts
            return fonts.get_pil_font(text, filename, width, height)
        except Exception as ex:
            LOGGER.warning("Media templates: could not fit font '%s': %s", font_name, ex)
    low, high, best = 6, max(7, int(height * 2)), None
    while low < high:  # Same bisection as pibooth, on PIL's built-in font
        size = (low + high) // 2
        font = _sized_default(size)
        left, top, right, bottom = font.getbbox(text)
        if right - left > width or bottom - top > height:
            high = size
        else:
            best, low = font, size + 1
    return best or _sized_default(6)


def _outline_color(color):
    """Dark outline for light text, light outline for dark text."""
    r, g, b = tuple(color)[:3]
    return (0, 0, 0, 215) if 0.299 * r + 0.587 * g + 0.114 * b > 128 else (255, 255, 255, 215)


def _draw_in_box(image, text, font, color, align, rect, rotation=0, outline=0):
    """Draw ``text`` in ``rect`` (x, y, w, h): aligned horizontally, centred vertically.
    ``outline`` is the width in pixels of a contrasting outline that keeps the text readable on any colour."""
    x, y, width, height = rect
    layer = Image.new('RGBA', (max(1, width), max(1, height)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font, stroke_width=outline)
    text_w, text_h = right - left, bottom - top
    tx = {'left': 0, 'center': (width - text_w) // 2, 'right': width - text_w}[align]
    draw.text((tx - left, (height - text_h) // 2 - top), text, fill=tuple(color)[:3] + (255,), font=font,
              stroke_width=outline, stroke_fill=_outline_color(color) if outline else None)
    if rotation:
        layer = layer.rotate(-rotation, expand=True, resample=BICUBIC)
    image.paste(layer, (x - (layer.width - width) // 2, y - (layer.height - height) // 2), layer)


class _Date(datetime):
    """``{date}`` prints as the locale date, like photobooth-app; ``{date:%d %B %Y}`` still works."""

    def __str__(self):
        return self.strftime('%x')


class _Time(datetime):
    def __str__(self):
        return self.strftime('%X')


def default_context(template, when=None, count=None):
    """Values available in texts: ``{date}``, ``{time}``, ``{name}`` and pibooth's ``{count}``."""
    when = when or datetime.now()
    fields = tuple(when.timetuple()[:6]) + (when.microsecond,)
    return {'date': _Date(*fields), 'time': _Time(*fields), 'name': template.name, 'count': count}


def draw_texts(image, template, context):
    """The template's own ``texts`` (photobooth-app style), placed against the size of ``image``."""
    width, height = image.size
    for item in template.texts:
        try:
            text = item.text.format(**context)
        except (KeyError, IndexError, ValueError, AttributeError):
            text = item.text
        if not text.strip():
            continue
        x, y = resolve(item.x, width), resolve(item.y, height)
        box_w = resolve(item.width, width) if item.width is not None else max(1, width - x)
        box_h = resolve(item.height, height)
        if item.font_size:
            font = _sized_font(item.font, item.font_size)
            box_h = max(box_h, int(item.font_size * 1.6))
        else:
            font = _fitted_font(text, item.font, box_w, box_h)
        if box_w > 0 and box_h > 0:
            _draw_in_box(image, text, font, item.color, item.align, (x, y, box_w, box_h), item.rotation)


# --------------------------------------------------------------------------
# Footer: pibooth's [PICTURE] footer_text1 / footer_text2
# --------------------------------------------------------------------------

def footer_height(template, size):
    """Height of the footer band, as in pibooth: a sixth of a portrait picture, an eighth of a landscape one."""
    given = template.footer['height']
    if given is not None:
        return max(1, resolve(given, size[1], 'footer height'))
    return size[1] // 6 if size[0] < size[1] else size[1] // 8


def footer_mode(template):
    """'band' (room is made for the text), 'overlay' (drawn on the picture) or 'off'.

    ``auto`` makes room on layouts built from a preset, where the canvas is ours to
    arrange, and draws over the picture otherwise."""
    mode = template.footer['mode']
    if mode == 'auto':
        return 'band' if template.has_preset else 'overlay'
    return mode


def _footer_rects(count, width, height, band, margin):
    """Where each footer text goes, as in pibooth: stacked in a portrait picture, side by side in a landscape one."""
    interline = 20
    x, y = margin, height - band
    total_w, total_h = width - 2 * margin, band - margin
    if count < 1 or total_w <= 0 or total_h <= 0:
        return []
    rects = []
    if width < height:
        line_h = (total_h - interline * (count - 1)) // (count + 1)
        for i in range(count):
            if i == 0:
                rects.append((x, y, total_w, 2 * line_h))
            else:
                y += interline + (2 * line_h if i == 1 else line_h)
                rects.append((x, y, total_w, line_h))
    else:
        text_w = (total_w - interline * (count - 1)) // count
        text_h = total_h // 2
        for i in range(count):
            if i:
                x += interline + text_w
            rects.append((x, y, text_w, 2 * text_h) if i == 0 else (x, y + (total_h - text_h) // 2, text_w, text_h))
    return rects


def draw_footer(image, template, footer_texts, band):
    """Draw pibooth's footer texts in the bottom ``band`` pixels of ``image``."""
    given = template.footer['margin']
    margin = resolve(given, image.width, 'footer margin') if given is not None else max(10, int(image.width * 0.03))
    rects = _footer_rects(len(footer_texts), image.width, image.height, band, margin)
    for (text, font_name, color, align), rect in zip(footer_texts, rects):
        if text.strip():  # An empty text keeps its place, as in pibooth
            outline = max(1, rect[3] // 40)  # fitted inside the box, outline included
            font = _fitted_font(text, font_name, max(1, rect[2] - 2 * outline), max(1, rect[3] - 2 * outline))
            _draw_in_box(image, text, font, color, align, rect, outline=outline)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def process_captures(template, images, replacer=None):
    """Replace the camera background of each capture where the template asks."""
    processed = []
    for index, image in enumerate(images):
        image = image.convert('RGB')
        background = template.background_for(index)
        if background and replacer is not None:
            image = replacer.replace(image, background)
        processed.append(image)
    return processed


def compose(template, processed, context=None, footer_texts=()):
    """Lay the (already processed) captures out on the template canvas.

    :param footer_texts: pibooth's footer texts as (text, font, colour, align)
    """
    context = context or default_context(template)
    footer = [t for t in footer_texts if t[0] is not None]
    mode = footer_mode(template) if any(t[0].strip() for t in footer) else 'off'
    band = 0

    if template.native:
        image = processed[0]
        if template.size:
            image = fit_image(image, template.size[0], template.size[1], 'cover')
        else:
            image = image.copy()
        if template.overlay:
            image = apply_overlay(image, template.overlay)
        if mode != 'off':
            band = footer_height(template, image.size)
        if mode == 'band':  # Extend the picture downwards: a frame overlay stays on the photo
            extended = Image.new('RGB', (image.width, image.height + band), template.canvas_color)
            extended.paste(image, (0, 0))
            image = extended
    else:
        if template.canvas_image:
            image = _load_cover(template.canvas_image, template.size).copy()
        else:
            image = Image.new('RGB', template.size, template.canvas_color)
        if mode != 'off':
            band = footer_height(template, image.size)
        for slot in template.slots_for(band if mode == 'band' else 0):
            if slot.capture >= len(processed):
                continue
            tile = fit_image(processed[slot.capture], slot.width, slot.height, slot.fit)
            if slot.rotation:
                tile = tile.convert('RGBA').rotate(-slot.rotation, expand=True, resample=BICUBIC)
                mask = tile
            else:
                mask = None
            image.paste(tile, (slot.x + (slot.width - tile.width) // 2,
                               slot.y + (slot.height - tile.height) // 2), mask)
        if template.overlay:
            image = apply_overlay(image, template.overlay)

    if mode != 'off':
        draw_footer(image, template, footer, band)
    if template.texts:
        draw_texts(image, template, context)
    return image


def render(template, images, replacer=None, context=None, footer_texts=()):
    """Build the final picture.

    :return: (final picture, processed captures)
    """
    processed = process_captures(template, images, replacer)
    return compose(template, processed, context, footer_texts), processed


class MediaTemplateFactory(object):

    """Picture factory handed to pibooth for the selected template.

    pibooth's own factories are fixed to its layouts, so this one implements
    just what pibooth calls: ``build`` and ``save``, ``add_text`` for the
    [PICTURE] footer texts, and no-op setters for the settings a template
    replaces (margin, background, overlay, cropping).
    """

    def __init__(self, template, images, replacer=None, context=None):
        self.template = template
        self._images = tuple(images)
        self.replacer = replacer
        self.context = context
        self.processed = None
        self._final = None
        self._margin = 0
        self._texts = []  # pibooth's footer texts, pushed by add_text()

    def build(self, rebuild=False):
        if self._final is None or rebuild:
            self._final, self.processed = render(self.template, self._images, self.replacer, self.context,
                                                 self._texts)
        return self._final

    def save(self, path):
        image = self.build()
        image.save(path, quality=95)
        return image

    def add_text(self, text, font_name, color, align='center'):
        """pibooth's footer_text1/2 (already formatted with {date} and {count}) with the font,
        colour and alignment of [PICTURE] text_fonts, text_colors and text_alignments."""
        self._texts.append((text, font_name, color, align))
        self._final = None

    # Other settings pibooth pushes on every factory: the template owns all of them
    def set_margin(self, *args, **kwargs): pass
    def set_background(self, *args, **kwargs): pass
    def set_overlay(self, *args, **kwargs): pass
    def set_cropping(self, *args, **kwargs): pass
    def set_outlines(self, *args, **kwargs): pass
