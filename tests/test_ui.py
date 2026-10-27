import pygame
import pytest

from pibooth_media_templates.model import load_templates, TYPES
from pibooth_media_templates.ui import TemplateBar, compute_layout, hit_test, render_icon


@pytest.fixture
def templates(examples):
    found, _ = load_templates(str(examples))
    return found


def test_all_tiles_fit_when_there_is_room():
    first, rects = compute_layout(5, 2, 1280, 120)
    assert first == 0 and len(rects) == 5
    assert all(0 <= x and x + w <= 1280 for x, _, w, _ in rects)


def test_window_follows_the_selection_when_crowded():
    first, rects = compute_layout(20, 15, 800, 120)
    assert len(rects) < 20
    assert first <= 15 < first + len(rects)
    first, _ = compute_layout(20, 0, 800, 120)
    assert first == 0
    first, rects = compute_layout(20, 19, 800, 120)
    assert first + len(rects) == 20


def test_hit_test_returns_template_index():
    first, rects = compute_layout(20, 15, 800, 120)
    x, y, w, h = rects[2]
    assert hit_test(20, 15, 800, 120, (x + w // 2, y + h // 2)) == first + 2
    assert hit_test(20, 15, 800, 120, (x + w // 2, 1000)) is None


def test_every_type_has_an_icon(templates):
    for kind in TYPES:
        tpl = next(t for t in templates if t.type == kind)
        icon = render_icon(tpl, 96)
        assert icon.size == (96, 96) and icon.mode == 'RGBA'


def test_bar_draws_and_locates(templates):
    pygame.init()
    screen = pygame.display.set_mode((1024, 600))
    bar = TemplateBar(templates, 'bottom', 0.18)
    x, y, w, h = bar.rect((1024, 600))
    assert (x, y + h, w) == (0, 600, 1024)

    class Win:
        surface = screen
    bar.draw(pygame, Win, 3)

    first, rects = compute_layout(len(templates), 3, w, h)
    rx, ry, rw, rh = rects[1]
    assert bar.locate((1024, 600), 3, (rx + rw // 2, y + ry + rh // 2)) == first + 1
    assert bar.locate((1024, 600), 3, (500, 10)) is None  # above the bar

    top = TemplateBar(templates, 'top', 0.18)
    assert top.rect((1024, 600))[1] == 0
