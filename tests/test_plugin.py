"""Exercises the plugin through pibooth's real hook specs and config parser."""

import os.path as osp
from types import SimpleNamespace

import pytest

pytest.importorskip('pibooth')
import pygame  # noqa: E402
from PIL import Image  # noqa: E402

import pibooth  # noqa: E402
from pibooth.config.parser import PiConfigParser, DEFAULT  # noqa: E402
from pibooth.plugins import create_plugin_manager  # noqa: E402
from pibooth.plugins.picture_plugin import PicturePlugin  # noqa: E402
from pibooth.pictures.factory import PilPictureFactory  # noqa: E402

import pibooth_media_templates as plugin  # noqa: E402
from pibooth_media_templates.ui import compute_layout  # noqa: E402
from conftest import make_photo  # noqa: E402


@pytest.fixture
def booth(tmp_path):
    pm = create_plugin_manager()
    # Keep only pibooth's picture plugin: its hookwrapper pushes margin, background,
    # overlay and texts on whatever factory is returned, exactly as in a real booth
    picture = PicturePlugin(pm)
    pm.register(picture, name='pibooth-core:picture')
    pm.register(plugin)  # pluggy validates every hook name and argument against pibooth's specs

    cfg = PiConfigParser(str(tmp_path / 'pibooth.cfg'), pm)
    DEFAULT.pop('MEDIA_TEMPLATES', None)  # pibooth keeps option defaults in a module global
    pm.hook.pibooth_configure(cfg=cfg)  # same order as pibooth's main()
    cfg.save(default=True)
    cfg.set('MEDIA_TEMPLATES', 'templates_path', str(tmp_path / 'templates'))
    cfg.set('GENERAL', 'directory', str(tmp_path / 'pictures'))
    (tmp_path / 'pictures').mkdir()

    pygame.init()
    win = SimpleNamespace(surface=pygame.display.set_mode((1000, 600)), update=lambda: None)
    app = SimpleNamespace(capture_choices=(4, 1), capture_nbr=None, capture_date='2026-10-27-14-03-11',
                          picture_filename='2026-10-27-14-03-11_pibooth.jpg', previous_picture=None,
                          previous_animated=None, previous_picture_file=None, count=SimpleNamespace(taken=0))
    plugin.CTRL.__init__()
    pm.hook.pibooth_reset(cfg=cfg, hard=False)  # writes the examples
    pm.hook.pibooth_startup(cfg=cfg, app=app)
    yield SimpleNamespace(pm=pm, cfg=cfg, win=win, app=app, hook=pm.hook, tmp=tmp_path, picture=picture)
    pm.hook.pibooth_cleanup(app=app)
    plugin.CTRL.__init__()


def tap_on(booth, name):
    names = [t.name for t in plugin.CTRL.templates]
    index = names.index(name)
    size = booth.win.surface.get_size()
    x, y, w, h = plugin.CTRL.bar.rect(size)
    first, rects = compute_layout(len(names), plugin.CTRL.index, w, h)
    assert first <= index < first + len(rects), "template not visible in the bar"
    rx, ry, rw, rh = rects[index - first]
    return pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(x + rx + rw // 2, y + ry + rh // 2))


def start(booth):
    booth.hook.state_wait_enter(cfg=booth.cfg, app=booth.app, win=booth.win)


def test_registers_against_pibooth_hookspecs_and_loads_examples(booth):
    assert len(plugin.CTRL.templates) == 10
    assert osp.isdir(booth.cfg.getpath('MEDIA_TEMPLATES', 'templates_path'))


def test_wait_screen_forces_a_single_choice_matching_the_template(booth):
    start(booth)
    template = plugin.CTRL.current
    assert booth.app.capture_choices == (template.captures,)
    assert booth.app.capture_nbr == template.captures


def test_tapping_an_icon_selects_it_and_starts_the_sequence(booth):
    start(booth)
    event = tap_on(booth, 'Night Sky')
    state = booth.hook.state_wait_validate(cfg=booth.cfg, app=booth.app, win=booth.win, events=[event])
    assert state in ('chosen', 'preview')
    assert plugin.CTRL.current.name == 'Night Sky'
    assert booth.app.capture_nbr == 1
    booth.hook.state_wait_exit(cfg=booth.cfg, app=booth.app, win=booth.win)
    assert plugin.CTRL.session.name == 'Night Sky'


def test_a_tap_outside_the_bar_is_left_to_pibooth(booth):
    start(booth)
    event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(100, 100))
    state = booth.hook.state_wait_validate(cfg=booth.cfg, app=booth.app, win=booth.win, events=[event])
    assert state is None


def test_arrow_keys_cycle_the_selection(booth):
    start(booth)
    first = plugin.CTRL.index
    booth.hook.state_wait_do(cfg=booth.cfg, app=booth.app, win=booth.win,
                             events=[pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT)])
    assert plugin.CTRL.index == first + 1
    booth.hook.state_wait_do(cfg=booth.cfg, app=booth.app, win=booth.win,
                             events=[pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LEFT)] * 2)
    assert plugin.CTRL.index == len(plugin.CTRL.templates) - 1  # wrapped


def pick(booth, name):
    start(booth)
    plugin.CTRL.index = [t.name for t in plugin.CTRL.templates].index(name)  # scroll the bar to it
    booth.hook.state_wait_validate(cfg=booth.cfg, app=booth.app, win=booth.win, events=[tap_on(booth, name)])
    booth.hook.state_wait_exit(cfg=booth.cfg, app=booth.app, win=booth.win)


def build(booth, count):
    images = tuple(make_photo(shade=i * 10) for i in range(count))
    default = PilPictureFactory(1800, 1200, *images)
    return booth.hook.pibooth_setup_picture_factory(cfg=booth.cfg, opt_index=0, factory=default)


def test_picture_factory_is_the_templates_and_beats_other_plugins(booth):
    pick(booth, 'Four Up')
    factory = build(booth, 4)
    assert isinstance(factory, plugin.MediaTemplateFactory)
    assert factory.build().size == (1800, 1200)


def test_pibooths_per_capture_animation_frames_use_the_default_factory(booth):
    pick(booth, 'Four Up')
    # one image for a four capture template: pibooth's own factory is kept
    assert not isinstance(build(booth, 1), plugin.MediaTemplateFactory)


def test_animation_template_writes_its_gif_next_to_the_picture(booth):
    pick(booth, 'Bounce')
    factory = build(booth, 4)
    factory.build()
    booth.hook.state_processing_exit(cfg=booth.cfg, app=booth.app, win=booth.win)
    for thread in plugin.CTRL.threads:
        thread.join(30)
    gif = booth.tmp / 'pictures' / '2026-10-27-14-03-11_pibooth.gif'
    assert gif.exists()
    with Image.open(gif) as image:
        assert image.n_frames == 6


def test_still_template_writes_no_extra_file(booth):
    pick(booth, 'Four Up')
    build(booth, 4).build()
    booth.hook.state_processing_exit(cfg=booth.cfg, app=booth.app, win=booth.win)
    assert plugin.CTRL.threads == []
    assert [p.name for p in (booth.tmp / 'pictures').iterdir()] == []


def test_selection_is_kept_or_reset_between_guests(booth):
    pick(booth, 'Night Sky')
    start(booth)
    assert plugin.CTRL.current.name == 'Night Sky'
    plugin.CTRL.keep_selection = False
    start(booth)
    assert plugin.CTRL.index == plugin.CTRL.default_index


def test_failsafe_clears_the_sequence(booth):
    pick(booth, 'Four Up')
    booth.hook.state_failsafe_enter(cfg=booth.cfg, app=booth.app, win=booth.win)
    assert plugin.CTRL.session is None
    assert not isinstance(build(booth, 4), plugin.MediaTemplateFactory)


def test_plugin_is_inert_with_no_templates(booth):
    plugin.CTRL.templates = []
    start(booth)
    assert booth.app.capture_choices == (4, 1)  # untouched
    assert not isinstance(build(booth, 4), plugin.MediaTemplateFactory)
    event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(500, 590))
    assert booth.hook.state_wait_validate(cfg=booth.cfg, app=booth.app, win=booth.win, events=[event]) is None


def red_pixels(image, box):
    return sum(1 for r, g, b in image.crop(box).getdata() if r > 200 and g < 60 and b < 60)


def test_pibooth_footer_texts_from_the_picture_section_are_drawn(booth):
    """[PICTURE] footer_text1/2, text_colors, text_fonts, text_alignments and {date} still work."""
    from datetime import datetime
    booth.cfg.set('PICTURE', 'footer_text1', '"London Science Museum"')
    booth.cfg.set('PICTURE', 'footer_text2', '"STEM Skills Fair {date:%Y}"')
    booth.cfg.set('PICTURE', 'text_colors', '(255, 0, 0)')
    booth.picture.texts_vars['date'] = datetime(2026, 10, 27, 14, 3, 11)
    booth.picture.texts_vars['count'] = SimpleNamespace(taken=7)

    pick(booth, 'Classic')          # a single photo: texts are drawn over it
    factory = build(booth, 1)
    assert isinstance(factory, plugin.MediaTemplateFactory)
    assert [t[0] for t in factory._texts] == ["London Science Museum", "STEM Skills Fair 2026"]
    final = factory.build()
    assert final.size == (1800, 1200) or final.size == factory._images[0].size
    width, height = final.size
    assert red_pixels(final, (0, height - height // 8, width, height)) > 100


def test_footer_makes_room_on_a_preset_collage(booth):
    booth.cfg.set('PICTURE', 'footer_text1', '"London Science Museum"')
    booth.cfg.set('PICTURE', 'text_colors', '(255, 0, 0)')
    pick(booth, 'Four Up')
    final = build(booth, 4).build()
    assert final.size == (1800, 1200)
    band = 1200 // 8
    assert red_pixels(final, (0, 1200 - band, 1800, 1200)) > 100


def test_a_template_can_opt_out_of_the_footer(booth):
    booth.cfg.set('PICTURE', 'footer_text1', '"London Science Museum"')
    booth.cfg.set('PICTURE', 'text_colors', '(255, 0, 0)')
    pick(booth, 'Classic')
    plugin.CTRL.session.footer['mode'] = 'off'
    final = build(booth, 1).build()
    width, height = final.size
    assert red_pixels(final, (0, height - height // 8, width, height)) == 0


# --- animated templates play on pibooth's print, finish and wait screens ----

class FakeWin(object):

    def __init__(self, surface):
        self.surface = surface
        self.shown = []

    def update(self):
        pass

    def show_print(self, image=None):
        self.shown.append(('print', image))

    def show_finished(self, image=None):
        self.shown.append(('finished', image))

    def set_print_number(self, *args):
        pass


def finish_processing(booth, name, count):
    pick(booth, name)
    factory = build(booth, count)
    booth.app.previous_picture = factory.build()
    booth.app.printer = SimpleNamespace(get_all_tasks=lambda: [], is_ready=lambda: True)
    booth.app.find_capture_event = lambda events: False
    booth.hook.state_processing_exit(cfg=booth.cfg, app=booth.app, win=booth.win)
    return FakeWin(booth.win.surface)


@pytest.mark.parametrize('name,count', [('Bounce', 4), ('Wiggle', 3), ('Reel', 4)])
def test_animated_templates_play_instead_of_the_still(booth, name, count):
    win = finish_processing(booth, name, count)
    player = plugin.CTRL.player
    assert player is not None and len(player.frames) >= count
    assert booth.app.previous_animated is player.cycle   # wait screen cycles our frames

    booth.hook.state_print_enter(cfg=booth.cfg, app=booth.app, win=win)
    player.next_at = 0
    booth.hook.state_print_do(cfg=booth.cfg, app=booth.app, win=win, events=[])
    booth.hook.state_print_do(cfg=booth.cfg, app=booth.app, win=win, events=[])  # not due yet
    assert [kind for kind, _ in win.shown] == ['print']
    assert win.shown[0][1] in player.frames

    booth.cfg.set('WINDOW', 'finish_picture_delay', '1')
    booth.hook.state_print_validate(cfg=booth.cfg, app=booth.app, win=win, events=[])
    booth.hook.state_finish_enter(cfg=booth.cfg, app=booth.app, win=win)
    player.next_at = 0
    booth.hook.state_finish_do(cfg=booth.cfg, app=booth.app, win=win, events=[])
    assert win.shown[-1][0] == 'finished'
    for thread in plugin.CTRL.threads:
        thread.join(30)


def test_a_forgotten_picture_does_not_play_on_the_finish_screen(booth):
    win = finish_processing(booth, 'Bounce', 4)
    booth.app.find_capture_event = lambda events: True
    booth.cfg.set('WINDOW', 'finish_picture_delay', '1')
    booth.hook.state_print_validate(cfg=booth.cfg, app=booth.app, win=win, events=[])
    booth.hook.state_finish_enter(cfg=booth.cfg, app=booth.app, win=win)
    plugin.CTRL.player.next_at = 0
    booth.hook.state_finish_do(cfg=booth.cfg, app=booth.app, win=win, events=[])
    assert win.shown == []
    for thread in plugin.CTRL.threads:
        thread.join(30)


def test_still_templates_have_no_player_and_wait_screen_resets_it(booth):
    finish_processing(booth, 'Four Up', 4)
    assert plugin.CTRL.player is None
    finish_processing(booth, 'Bounce', 4)
    booth.app.previous_picture = None            # pibooth dropped the picture
    booth.hook.state_wait_enter(cfg=booth.cfg, app=booth.app, win=booth.win)
    assert plugin.CTRL.player is None
    for thread in plugin.CTRL.threads:
        thread.join(30)


# --- a tap on a tile must never reach pibooth's 'print the previous picture' handler ---

class PrinterSpy(object):

    """Stands in for pibooth's printer plugin: sees the wait events like it does."""

    def __init__(self):
        self.seen = []

    @pibooth.hookimpl
    def state_wait_do(self, events):
        self.seen.extend(events)


def test_tap_on_a_tile_is_hidden_from_pibooths_print_handler(booth):
    spy = PrinterSpy()
    booth.pm.register(spy)
    start(booth)
    # a tile on the right half of the screen, where pibooth would print
    right = [t.name for t in plugin.CTRL.templates][-1]
    plugin.CTRL.index = len(plugin.CTRL.templates) - 1
    tap = tap_on(booth, right)
    assert tap.pos[0] > booth.win.surface.get_width() // 2
    events = [tap]
    booth.hook.state_wait_do(cfg=booth.cfg, app=booth.app, win=booth.win, events=events)
    assert spy.seen == [] and events == []
    state = booth.hook.state_wait_validate(cfg=booth.cfg, app=booth.app, win=booth.win, events=events)
    assert state in ('chosen', 'preview')
    assert plugin.CTRL.current.name == right


def test_taps_off_the_bar_still_reach_pibooth(booth):
    spy = PrinterSpy()
    booth.pm.register(spy)
    start(booth)
    tap = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(900, 100))
    booth.hook.state_wait_do(cfg=booth.cfg, app=booth.app, win=booth.win, events=[tap])
    assert spy.seen == [tap]
