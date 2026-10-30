# -*- coding: utf-8 -*-
"""pibooth-media-templates: photobooth-app style templates for pibooth.

Each template is a small YAML file (plus its images) describing one thing a
guest can pick on the wait screen: a single photo, a collage, an animation, a
video or a wigglegram, each with its own background, overlay and texts. The
enabled templates appear as an icon bar on the wait screen.

Install with ``pip install pibooth-media-templates``; pibooth discovers it
automatically. Background replacement uses ``pibooth-modnet`` when installed.
See README.md for the template format.
"""

import sys
import os.path as osp
import shutil
import itertools
import threading
import time
from datetime import datetime

from PIL import Image

try:
    import pygame
    import pibooth
    from pibooth.utils import LOGGER, get_event_pos
except ImportError:  # Allow the command line tools to run without pibooth
    pibooth = None
    pygame = None
    import logging
    LOGGER = logging.getLogger("pibooth-media-templates")

from .model import load_templates, MULTI_FRAME_TYPES, TemplateError  # noqa: F401
from .render import BackgroundReplacer, MediaTemplateFactory, default_context, parse_paper
from .media import generate_media, media_frames, frame_delay, media_stem
from .ui import TemplateBar
from .examples import write_examples

__version__ = "0.1.7"

SECTION = 'MEDIA_TEMPLATES'


def _plugin_hookimpl(*args, **kwargs):
    """Return pibooth.hookimpl, or a no-op decorator outside pibooth."""
    if pibooth is not None:
        return pibooth.hookimpl(*args, **kwargs)
    if args and callable(args[0]):
        return args[0]
    return lambda func: func


class Controller(object):

    """State shared by the pibooth hooks."""

    def __init__(self):
        self.templates = []
        self.index = 0
        self.default_index = 0
        self.keep_selection = True
        self.session = None       # Template of the sequence in progress
        self.last_factory = None  # Factory of the sequence in progress
        self.bar = None
        self.replacer = None
        self.app = None
        self.threads = []
        self.player = None        # Player of the last animated picture
        self.forgotten = False
        self.finish_plays = False
        self.paper = None         # Paper the pictures are fitted to, or None
        self.tapped = None       # index of the tile touched, until the wait state validates

    @property
    def active(self):
        return bool(self.templates)

    @property
    def current(self):
        return self.templates[self.index] if self.templates else None

    def select(self, index, app):
        self.index = index % len(self.templates)
        self.apply(app)
        LOGGER.info("Media templates: '%s' selected", self.current.name)

    def step(self, direction, app):
        if len(self.templates) > 1:
            self.select(self.index + direction, app)

    def apply(self, app):
        """Tell pibooth how many captures the selected template needs. A single
        choice also makes pibooth skip its own layout choice screen."""
        count = self.current.captures
        app.capture_choices = (count,)
        app.capture_nbr = count

    def draw(self, win):
        if self.bar is not None and pygame is not None:
            self.bar.draw(pygame, win, self.index)

    def reset_sequence(self):
        self.session = None
        self.last_factory = None

    def context(self):
        when = datetime.now()
        capture_date = getattr(self.app, 'capture_date', None)
        if capture_date:
            try:
                when = datetime.strptime(capture_date, "%Y-%m-%d-%H-%M-%S")
            except ValueError:
                pass
        return default_context(self.session, when, getattr(self.app, 'count', None))


class Player(object):

    """Plays the frames of an animation, wigglegram or video template on pibooth's
    print and finish screens, which would otherwise show the still picture only."""

    def __init__(self, still, frames, delay):
        self.still = still            # the app.previous_picture this belongs to
        self.frames = frames
        self.cycle = itertools.cycle(frames)
        self.delay = max(0.05, delay)
        self.next_at = 0.0

    def due(self):
        """True (once per frame delay) when the next frame should be shown."""
        now = time.time()
        if now < self.next_at:
            return False
        self.next_at = now + self.delay
        return True

    def restart(self):
        self.cycle = itertools.cycle(self.frames)
        self.next_at = time.time() + self.delay  # the first frame is already shown

    @staticmethod
    def fit(frames, size, share=0.9):
        """Scale frames down to the window so pibooth does not resize them on every frame."""
        box = (size[0] * share, size[1] * share)
        fitted = []
        for frame in frames:
            scale = min(1.0, box[0] / frame.width, box[1] / frame.height)
            if scale < 1.0:
                frame = frame.resize((max(2, int(frame.width * scale)), max(2, int(frame.height * scale))),
                                     Image.Resampling.LANCZOS)
            fitted.append(frame)
        return fitted


CTRL = Controller()


# --------------------------------------------------------------------------
# pibooth hooks
# --------------------------------------------------------------------------

@_plugin_hookimpl
def pibooth_configure(cfg):
    cfg.add_option(SECTION, 'enabled', True,
                   "Offer media templates (single, collage, animation, video, wigglegram) on the wait screen",
                   "Enable media templates", ['True', 'False'])
    cfg.add_option(SECTION, 'templates_path', '~/.config/pibooth/media_templates',
                   "Folder of templates: one YAML file or one sub-folder with a template.yaml per template. "
                   "Examples are created there on first start")
    cfg.add_option(SECTION, 'disabled', '',
                   "Names of templates to hide, separated by commas (or set 'enabled: false' in the template)")
    cfg.add_option(SECTION, 'default', '',
                   "Name of the template selected at start (first one if empty)")
    cfg.add_option(SECTION, 'keep_selection', True,
                   "Keep the guest's choice for the next guest (False goes back to the default template)",
                   "Keep selection", ['True', 'False'])
    cfg.add_option(SECTION, 'bar_position', 'bottom',
                   "Where the template icons are shown", "Icon bar position", ['bottom', 'top'])
    cfg.add_option(SECTION, 'bar_height', 0.2,
                   "Height of the icon bar as a fraction of the window height")
    cfg.add_option(SECTION, 'show_labels', True,
                   "Show the template name under each icon", "Show names", ['True', 'False'])
    cfg.add_option(SECTION, 'icon_style', 'outlined',
                   "Style of the Material icons on the tiles", "Icon style", ['outlined', 'filled'])
    cfg.add_option(SECTION, 'print_size', '',
                   "Paper the pictures are made for: postcard (Canon SELPHY 100x148 mm), l, card, 4x6, 5x7, "
                   "or WIDTHxHEIGHT in mm (e.g. 100x148); empty keeps the template's own shape")
    cfg.add_option(SECTION, 'print_dpi', 300,
                   "Resolution of the picture made for print_size (the Canon SELPHY CP1300 prints at 300)")
    cfg.add_option(SECTION, 'print_fit', 'auto',
                   "How a picture of another shape fills the paper: auto (crop a little, or pad a strip), "
                   "cover (always crop) or contain (always pad)", "Paper fit", ['auto', 'cover', 'contain'])
    cfg.add_option(SECTION, 'model_path', '~/.config/pibooth/models/modnet.onnx',
                   "MODNet model used to replace backgrounds (shared with pibooth-modnet)")
    cfg.add_option(SECTION, 'inference_size', 512,
                   "Short side in pixels the background model runs at (multiple of 32)")
    cfg.add_option(SECTION, 'threads', 3,
                   "CPU threads for the background model")
    cfg.add_option(SECTION, 'refine_edges', True,
                   "Snap the background cut-out to full resolution edges (needs OpenCV)")


@_plugin_hookimpl
def pibooth_reset(cfg, hard):
    folder = cfg.getpath(SECTION, 'templates_path')
    if folder and not osp.isdir(folder):
        LOGGER.info("Media templates: creating example templates in '%s'", folder)
        write_examples(folder)


@_plugin_hookimpl(trylast=True)
def pibooth_startup(cfg, app):
    CTRL.app = app
    CTRL.templates = []
    if not cfg.getboolean(SECTION, 'enabled'):
        return

    folder = cfg.getpath(SECTION, 'templates_path')
    if not osp.isdir(folder):
        write_examples(folder)
    disabled = cfg.get(SECTION, 'disabled').split(',')
    templates, errors = load_templates(folder, disabled)
    if not templates:
        LOGGER.warning("Media templates: no usable template in '%s', pibooth keeps its own layouts", folder)
        return
    CTRL.templates = templates
    try:
        CTRL.paper = parse_paper(cfg.get(SECTION, 'print_size'), cfg.getint(SECTION, 'print_dpi'),
                                 cfg.get(SECTION, 'print_fit'))
    except ValueError as ex:
        CTRL.paper = None
        LOGGER.error("Media templates: %s, pictures keep their own shape", ex)

    default = cfg.get(SECTION, 'default').strip().lower()
    CTRL.default_index = next((i for i, t in enumerate(templates) if t.name.lower() == default), 0)
    CTRL.index = CTRL.default_index
    CTRL.keep_selection = cfg.getboolean(SECTION, 'keep_selection')
    CTRL.bar = TemplateBar(templates, cfg.get(SECTION, 'bar_position').strip().lower(),
                           min(0.5, max(0.1, cfg.getfloat(SECTION, 'bar_height'))),
                           cfg.getboolean(SECTION, 'show_labels'),
                           cfg.get(SECTION, 'icon_style').strip().lower())
    LOGGER.info("Media templates: %d template(s): %s", len(templates), ", ".join(t.name for t in templates))

    CTRL.replacer = BackgroundReplacer(cfg.getpath(SECTION, 'model_path'), cfg.getint(SECTION, 'inference_size'),
                                       cfg.getint(SECTION, 'threads'), cfg.getboolean(SECTION, 'refine_edges'))
    if any(t.needs_matting for t in templates):
        threading.Thread(target=CTRL.replacer.load, daemon=True, name='media-templates-model').start()
    else:
        CTRL.replacer.ready.set()

    # pibooth-modnet would also replace backgrounds with its own themes
    modnet = sys.modules.get('pibooth_modnet')
    if modnet is not None and getattr(modnet, 'CTRL', None) is not None and modnet.CTRL.enabled:
        modnet.CTRL.enabled = False
        LOGGER.info("Media templates: pibooth-modnet themes disabled, templates handle backgrounds")


@_plugin_hookimpl(trylast=True)
def state_wait_enter(app, win):
    CTRL.reset_sequence()
    CTRL.tapped = None
    if not CTRL.active:
        return
    if not CTRL.keep_selection:
        CTRL.index = CTRL.default_index
    CTRL.apply(app)
    player = CTRL.player
    if player is not None:
        if app.previous_picture is not player.still:
            CTRL.player = None  # pibooth dropped the picture (delay elapsed, or forgotten)
        else:
            app.previous_animated = player.cycle  # also replaces pibooth's un-templated 'animate' frames
    CTRL.bar.invalidate()  # pibooth has just repainted the wait screen
    CTRL.draw(win)


def _is_tap(event):
    return (event.type == pygame.MOUSEBUTTONUP and event.button in (1, 2, 3)) or event.type == pygame.FINGERUP


def _take_taps(win, events):
    """Remove the taps that hit a tile from ``events`` (pibooth would read a tap on the right half of the
    screen as 'print the previous picture') and remember the first tile touched."""
    size = win.surface.get_size()
    for event in list(events):
        if _is_tap(event):
            index = CTRL.bar.locate(size, CTRL.index, get_event_pos(size, event))
            if index is not None:
                events.remove(event)
                if CTRL.tapped is None:
                    CTRL.tapped = index


@_plugin_hookimpl(hookwrapper=True)
def state_wait_do(app, win, events):
    # A wrapper: runs before pibooth's own handlers so they never see the taps on tiles,
    # and after them so the bar is drawn over what pibooth has just repainted
    if CTRL.active:
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_LEFT:
                CTRL.step(-1, app)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_RIGHT:
                CTRL.step(1, app)
        _take_taps(win, events)
    yield
    if CTRL.active:
        CTRL.draw(win)


@_plugin_hookimpl(tryfirst=True)
def state_wait_validate(cfg, app, win, events):
    """Touching an icon selects that template and starts the sequence."""
    if not CTRL.active:
        return None
    _take_taps(win, events)
    index, CTRL.tapped = CTRL.tapped, None
    if index is None:
        return None
    CTRL.select(index, app)
    return 'chosen' if cfg.getfloat('WINDOW', 'chosen_delay') > 0 else 'preview'


@_plugin_hookimpl
def state_wait_exit(win):
    if CTRL.active:
        CTRL.session = CTRL.current
        win.update()  # Repaint the wait screen to remove the bar


@_plugin_hookimpl(tryfirst=True)
def pibooth_setup_picture_factory(factory):
    # Firstresult hook: running first means the template's factory is used
    # instead of the layouts of pibooth and of other picture plugins.
    template = CTRL.session
    if not CTRL.active or template is None:
        return None
    images = getattr(factory, '_images', ())
    if len(images) != template.captures:
        return None  # pibooth's per-capture animation frames: leave them to the default factory
    CTRL.last_factory = MediaTemplateFactory(template, images, CTRL.replacer, CTRL.context(), CTRL.paper)
    return CTRL.last_factory


@_plugin_hookimpl
def state_processing_exit(cfg, app, win):
    factory, CTRL.last_factory = CTRL.last_factory, None
    CTRL.player = None
    if factory is None or factory.processed is None or factory.template.type not in MULTI_FRAME_TYPES:
        return
    frames = media_frames(factory.template, factory.processed)
    if len(frames) > 1:
        CTRL.player = Player(app.previous_picture, Player.fit(frames, win.surface.get_size()),
                             frame_delay(factory.template))
        app.previous_animated = CTRL.player.cycle
    folders = cfg.gettuple('GENERAL', 'directory', 'path')
    stems = [media_stem(osp.join(folder, app.picture_filename)) for folder in folders]
    thread = threading.Thread(target=_write_media, args=(factory.template, factory.processed, stems, frames),
                              name='media-templates-output')
    thread.start()  # Not a daemon: a half written file is worse than a slow exit
    CTRL.threads = [t for t in CTRL.threads if t.is_alive()] + [thread]


def _write_media(template, processed, stems, frames=None):
    started = time.time()
    try:
        path = generate_media(template, processed, stems[0], frames)
        for stem in stems[1:]:
            shutil.copy(path, stem + osp.splitext(path)[1])
        LOGGER.info("Media templates: %s '%s' saved in %.1fs", template.type, osp.basename(path),
                    time.time() - started)
    except Exception as ex:
        LOGGER.error("Media templates: could not create the %s: %s", template.type, ex)


@_plugin_hookimpl
def state_print_enter():
    if CTRL.player is not None:
        CTRL.player.restart()


@_plugin_hookimpl
def state_print_do(app, win):
    if CTRL.player is not None and CTRL.player.due():
        win.show_print(next(CTRL.player.cycle))
        win.set_print_number(len(app.printer.get_all_tasks()), not app.printer.is_ready())


@_plugin_hookimpl
def state_print_validate(app, events):
    CTRL.forgotten = bool(app.find_capture_event(events))  # as pibooth: a capture event forgets the picture
    return None


@_plugin_hookimpl(trylast=True)
def state_finish_enter(cfg):
    # pibooth shows the picture on the finish screen only if it is not forgotten
    CTRL.finish_plays = (CTRL.player is not None and not CTRL.forgotten
                         and cfg.getfloat('WINDOW', 'finish_picture_delay') > 0)
    CTRL.forgotten = False
    if CTRL.player is not None:
        CTRL.player.restart()


@_plugin_hookimpl
def state_finish_do(win):
    if CTRL.finish_plays and CTRL.player.due():
        win.show_finished(next(CTRL.player.cycle))


@_plugin_hookimpl
def state_failsafe_enter():
    CTRL.reset_sequence()
    CTRL.player = None


@_plugin_hookimpl
def pibooth_cleanup():
    for thread in CTRL.threads:
        thread.join(timeout=30)
