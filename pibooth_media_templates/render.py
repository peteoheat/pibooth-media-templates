# -*- coding: utf-8 -*-
"""Turn captures into the final still picture of a template."""

import threading
import logging
from functools import lru_cache
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageOps

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


def _font(text, font_name, width, height):
    try:
        from pibooth import fonts
        return fonts.get_pil_font(text, font_name, width, height)
    except Exception:  # No pibooth (command line) or an unknown font
        try:
            return ImageFont.load_default(size=max(8, int(height * 0.8)))
        except TypeError:  # Pillow < 10.1
            return ImageFont.load_default()


def draw_texts(image, template, context):
    for item in template.texts:
        try:
            text = item.text.format(**context)
        except (KeyError, IndexError, ValueError):
            text = item.text
        if not text.strip() or item.width <= 0 or item.height <= 0:
            continue
        layer = Image.new('RGBA', (item.width, item.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        font = _font(text, item.font, item.width, item.height)
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        text_w, text_h = right - left, bottom - top
        x = {'left': 0, 'center': (item.width - text_w) // 2, 'right': item.width - text_w}[item.align]
        draw.text((x - left, (item.height - text_h) // 2 - top), text, fill=item.color + (255,), font=font)
        if item.rotation:
            layer = layer.rotate(-item.rotation, expand=True, resample=BICUBIC)
        image.paste(layer, (item.x - (layer.width - item.width) // 2,
                            item.y - (layer.height - item.height) // 2), layer)


def default_context(template, when=None):
    return {'date': when or datetime.now(), 'name': template.name}


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


def compose(template, processed, context=None):
    """Lay the (already processed) captures out on the template canvas."""
    context = context or default_context(template)

    if template.native:
        image = processed[0]
        if template.size:
            image = fit_image(image, template.size[0], template.size[1], 'cover')
        else:
            image = image.copy()
    else:
        if template.canvas_image:
            image = _load_cover(template.canvas_image, template.size).copy()
        else:
            image = Image.new('RGB', template.size, template.canvas_color)
        for slot in template.slots:
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
    if template.texts:
        draw_texts(image, template, context)
    return image


def render(template, images, replacer=None, context=None):
    """Build the final picture.

    :return: (final picture, processed captures)
    """
    processed = process_captures(template, images, replacer)
    return compose(template, processed, context), processed


class MediaTemplateFactory(object):

    """Picture factory handed to pibooth for the selected template.

    pibooth's own factories are fixed to its layouts, so this one implements
    just what pibooth calls: ``build`` and ``save`` (plus no-op setters for the
    settings pibooth applies to every factory, which a template replaces).
    """

    def __init__(self, template, images, replacer=None, context=None):
        self.template = template
        self._images = tuple(images)
        self.replacer = replacer
        self.context = context
        self.processed = None
        self._final = None
        self._margin = 0

    def build(self, rebuild=False):
        if self._final is None or rebuild:
            self._final, self.processed = render(self.template, self._images, self.replacer, self.context)
        return self._final

    def save(self, path):
        image = self.build()
        image.save(path, quality=95)
        return image

    # Settings pibooth pushes on every factory: the template owns all of them
    def set_margin(self, *args, **kwargs): pass
    def set_background(self, *args, **kwargs): pass
    def set_overlay(self, *args, **kwargs): pass
    def add_text(self, *args, **kwargs): pass
    def set_cropping(self, *args, **kwargs): pass
    def set_outlines(self, *args, **kwargs): pass
