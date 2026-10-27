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
    pm.register(PicturePlugin(pm), name='pibooth-core:picture')
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
    yield SimpleNamespace(pm=pm, cfg=cfg, win=win, app=app, hook=pm.hook, tmp=tmp_path)
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
    assert len(plugin.CTRL.templates) == 9
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
