# -*- coding: utf-8 -*-
"""Template definitions: parsing and validation of the YAML template files.

A template is either a single ``*.yaml`` file or a folder holding a
``template.yaml`` plus its assets (background, overlay, icon...). Relative
paths inside a template are resolved against the template's own folder.
"""

import os
import os.path as osp
import logging

import yaml
from PIL import ImageColor

from . import icons
from .icons import DEFAULT_ICONS

LOGGER = logging.getLogger("pibooth-media-templates")

TYPES = ('single', 'collage', 'animation', 'video', 'wigglegram')
MULTI_FRAME_TYPES = ('animation', 'video', 'wigglegram')
PRESETS = ('single', 'strip', 'strip_h', 'grid')
FITS = ('cover', 'contain')
MAX_CAPTURES = 4  # pibooth builds its default factory first, which accepts 1 to 4 images
DEFAULT_CANVAS = (1200, 1800)
DEFAULT_CAPTURES = {'single': 1, 'collage': 4, 'animation': 4, 'video': 4, 'wigglegram': 3}
TEMPLATE_FILE = 'template.yaml'


class TemplateError(ValueError):
    """Raised when a template file is invalid."""


def _color(value, what):
    try:
        return ImageColor.getrgb(str(value))
    except ValueError:
        raise TemplateError("{}: '{}' is not a valid colour".format(what, value))


def _dim(value, total, what):
    """Floats between 0 and 1 are a fraction of ``total``, anything else is pixels."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TemplateError("{}: '{}' is not a number".format(what, value))
    if isinstance(value, float) and 0.0 <= value <= 1.0:
        return int(round(value * total))
    return int(round(value))


def _pair(value, what):
    try:
        width, height = value
        return int(width), int(height)
    except (TypeError, ValueError):
        raise TemplateError("{}: expected [width, height]".format(what))


class Slot(object):

    """A rectangle of the canvas that receives one capture."""

    def __init__(self, capture, x, y, width, height, rotation=0, fit='cover', background=None):
        self.capture = capture  # 0 based index of the capture
        self.x, self.y, self.width, self.height = x, y, width, height
        self.rotation = rotation
        self.fit = fit
        self.background = background  # None: template default, False: keep camera background

    def __repr__(self):
        return "Slot(capture={}, {}x{}+{}+{})".format(self.capture, self.width, self.height, self.x, self.y)


class TextItem(object):

    def __init__(self, text, x, y, width, height, color, font, align, rotation):
        self.text = text
        self.x, self.y, self.width, self.height = x, y, width, height
        self.color = color
        self.font = font
        self.align = align
        self.rotation = rotation


def preset_slots(preset, count, size, margin, gap, footer):
    """Compute the slots of a built-in layout as (x, y, w, h) pixel tuples."""
    width, height = size
    footer_px = int(round(footer * height)) if isinstance(footer, float) and footer <= 1 else int(footer)
    inner_w = width - 2 * margin
    inner_h = height - 2 * margin - footer_px
    if inner_w <= 0 or inner_h <= 0:
        raise TemplateError("layout margin/footer leave no room on a {}x{} canvas".format(width, height))

    if preset == 'single':
        return [(margin, margin, inner_w, inner_h)]
    if preset == 'strip':  # stacked vertically
        cell = (inner_h - gap * (count - 1)) // count
        return [(margin, margin + i * (cell + gap), inner_w, cell) for i in range(count)]
    if preset == 'strip_h':  # side by side
        cell = (inner_w - gap * (count - 1)) // count
        return [(margin + i * (cell + gap), margin, cell, inner_h) for i in range(count)]
    # grid: two columns
    cols = 1 if count == 1 else 2
    rows = (count + cols - 1) // cols
    cell_w = (inner_w - gap * (cols - 1)) // cols
    cell_h = (inner_h - gap * (rows - 1)) // rows
    return [(margin + (i % cols) * (cell_w + gap), margin + (i // cols) * (cell_h + gap), cell_w, cell_h)
            for i in range(count)]


class Template(object):

    """A validated template."""

    def __init__(self, data, folder, source):
        self.source = source
        self.folder = folder
        self.errors = []

        stem = osp.basename(folder) if osp.basename(source) == TEMPLATE_FILE else osp.splitext(osp.basename(source))[0]
        self.name = str(data.get('name') or stem.replace('_', ' ').replace('-', ' ').strip().title())
        self.enabled = bool(data.get('enabled', True))

        self.type = str(data.get('type', 'single')).lower()
        if self.type not in TYPES:
            raise TemplateError("type must be one of {}, not '{}'".format(', '.join(TYPES), self.type))

        self.icon, self.icon_name = self._icon(data.get('icon'))
        self.color = _color(data['color'], 'color') if data.get('color') else None  # tile tint
        self.overlay = self._path(data.get('overlay'))
        self.background = self._background(data.get('background'))

        layout = data.get('layout') or {}
        if not isinstance(layout, dict):
            raise TemplateError("layout must be a mapping")
        slots_data = data.get('slots')
        preset = layout.get('preset')
        if preset is not None and preset not in PRESETS:
            raise TemplateError("layout preset must be one of {}".format(', '.join(PRESETS)))

        self.native = not slots_data and preset is None  # No canvas, the capture is the picture
        if self.type == 'collage' and self.native:
            raise TemplateError("a collage needs 'slots' or a 'layout' preset")

        # Number of captures
        if 'captures' in data:
            captures = data['captures']
        elif slots_data:
            captures = len({s.get('capture', i + 1) for i, s in enumerate(slots_data)})
        else:
            captures = DEFAULT_CAPTURES[self.type]
        if isinstance(captures, bool) or not isinstance(captures, int) or not 1 <= captures <= MAX_CAPTURES:
            raise TemplateError("captures must be a whole number from 1 to {}".format(MAX_CAPTURES))
        if self.type == 'single':
            captures = 1
        elif self.type in MULTI_FRAME_TYPES and captures < 2:
            raise TemplateError("a {} needs at least 2 captures".format(self.type))
        self.captures = captures

        # Canvas
        size = data.get('size')
        self.size = _pair(size, 'size') if size else (None if self.native else DEFAULT_CANVAS)
        canvas = data.get('canvas') or {}
        if not isinstance(canvas, dict):
            raise TemplateError("canvas must be a mapping")
        self.canvas_color = _color(canvas.get('color', '#ffffff'), 'canvas color')
        self.canvas_image = self._path(canvas.get('image'))

        # Slots
        self.slots = []
        if not self.native:
            if slots_data:
                self.slots = [self._slot(i, s) for i, s in enumerate(slots_data)]
            else:
                rects = preset_slots(preset, captures, self.size, int(layout.get('margin', 60)),
                                     int(layout.get('gap', 30)), layout.get('footer', 0))
                self.slots = [Slot(i, *rect) for i, rect in enumerate(rects)]
            for slot in self.slots:
                if slot.capture >= self.captures:
                    raise TemplateError("slot uses capture {} but the template only takes {}".format(
                        slot.capture + 1, self.captures))
                if slot.width <= 0 or slot.height <= 0:
                    raise TemplateError("slot {} has no size".format(slot.capture + 1))

        self.texts = [self._text(i, t) for i, t in enumerate(data.get('texts') or [])]

        media = data.get(self.type) or {}
        if not isinstance(media, dict):
            raise TemplateError("'{}' options must be a mapping".format(self.type))
        self.media = media
        self.media_overlay = self._path(media.get('overlay'))

    # -- helpers -------------------------------------------------------------

    def _path(self, value):
        if not value:
            return None
        value = osp.expanduser(str(value))
        path = value if osp.isabs(value) else osp.join(self.folder, value)
        if not osp.isfile(path):
            raise TemplateError("file not found: {}".format(path))
        return path

    def _icon(self, value):
        """An icon is a Material icon name (``photo_camera``) or an image file.

        :return: (image file or None, material icon name or None)
        """
        if not value:
            return None, DEFAULT_ICONS[self.type]
        value = str(value).strip()
        if '.' in value or '/' in value or '\\' in value:
            return self._path(value), None
        if not icons.is_icon_name(value):
            hint = icons.suggest(value)
            raise TemplateError("unknown icon '{}'{} (pick a name from https://fonts.google.com/icons, "
                                "or use an image file)".format(value, ", did you mean {}?".format(
                                    ' / '.join(hint)) if hint else ''))
        return None, value

    def _background(self, value):
        return False if value is False else self._path(value)

    def _slot(self, index, data):
        if not isinstance(data, dict):
            raise TemplateError("slot {} must be a mapping".format(index + 1))
        width, height = self.size
        capture = data.get('capture', index + 1)
        if isinstance(capture, bool) or not isinstance(capture, int) or capture < 1:
            raise TemplateError("slot {}: capture must be 1 or more".format(index + 1))
        fit = str(data.get('fit', 'cover')).lower()
        if fit not in FITS:
            raise TemplateError("slot {}: fit must be cover or contain".format(index + 1))
        what = "slot {}".format(index + 1)
        return Slot(capture - 1,
                    _dim(data.get('x', 0), width, what), _dim(data.get('y', 0), height, what),
                    _dim(data.get('w', 1.0), width, what), _dim(data.get('h', 1.0), height, what),
                    float(data.get('rotation', 0)), fit, self._background(data.get('background')))

    def _text(self, index, data):
        if not isinstance(data, dict) or 'text' not in data:
            raise TemplateError("text {} needs a 'text' entry".format(index + 1))
        if self.native and not self.size:
            raise TemplateError("texts need a 'size' (or slots/layout) so they can be positioned")
        width, height = self.size
        what = "text {}".format(index + 1)
        align = str(data.get('align', 'center')).lower()
        if align not in ('left', 'center', 'right'):
            raise TemplateError("{}: align must be left, center or right".format(what))
        return TextItem(str(data['text']),
                        _dim(data.get('x', 0.0), width, what), _dim(data.get('y', 0.9), height, what),
                        _dim(data.get('w', 1.0), width, what), _dim(data.get('h', 0.08), height, what),
                        _color(data.get('color', '#000000'), what), data.get('font'), align,
                        float(data.get('rotation', 0)))

    # -- queries -------------------------------------------------------------

    def background_for(self, capture):
        """Background image path that replaces the camera background of a
        capture, or None to leave it as it was."""
        for slot in self.slots:
            if slot.capture == capture and slot.background is not None:
                return slot.background or None
        return self.background or None

    @property
    def needs_matting(self):
        return any(self.background_for(i) for i in range(self.captures))

    def __repr__(self):
        return "Template({!r}, {}, {} capture(s))".format(self.name, self.type, self.captures)


def load_template(path):
    """Load a template from a ``.yaml`` file or a folder holding ``template.yaml``."""
    source = osp.join(path, TEMPLATE_FILE) if osp.isdir(path) else path
    try:
        with open(source, 'r', encoding='utf-8') as fp:
            data = yaml.safe_load(fp) or {}
    except yaml.YAMLError as ex:
        raise TemplateError("{}: invalid YAML: {}".format(source, ex))
    if not isinstance(data, dict):
        raise TemplateError("{}: a template must be a mapping".format(source))
    try:
        return Template(data, osp.dirname(osp.abspath(source)), source)
    except TemplateError as ex:
        raise TemplateError("{}: {}".format(source, ex))


def load_templates(folder, disabled=()):
    """Load every template found in ``folder`` (sorted by name).

    Invalid templates are logged and skipped, so one typo never stops the booth.
    ``disabled`` is a collection of template names (case insensitive) to hide.

    :return: (list of enabled templates, list of error messages)
    """
    templates, errors = [], []
    disabled = {str(name).strip().lower() for name in disabled if str(name).strip()}
    if not osp.isdir(folder):
        return templates, ["templates folder '{}' does not exist".format(folder)]

    for entry in sorted(os.listdir(folder)):
        path = osp.join(folder, entry)
        if osp.isdir(path) and osp.isfile(osp.join(path, TEMPLATE_FILE)):
            pass
        elif osp.isfile(path) and entry.lower().endswith(('.yaml', '.yml')):
            pass
        else:
            continue
        try:
            template = load_template(path)
        except (TemplateError, OSError) as ex:
            LOGGER.error("Template skipped: %s", ex)
            errors.append(str(ex))
            continue
        if template.enabled and template.name.lower() not in disabled and entry.lower() not in disabled:
            templates.append(template)
    return templates, errors
