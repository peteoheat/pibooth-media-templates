# Changelog

## 0.1.3

* Animation, wigglegram and video templates now play their frames on pibooth's print, finish and wait screens
  instead of showing only the still picture. Frame speed follows the template (`frame_ms` / `frame_s`); the wait
  screen uses pibooth's `animate_delay`, and replaces pibooth's un-templated `animate` frames.

## 0.1.2

* pibooth's `[PICTURE]` footer text works again (`footer_text1/2`, `text_colors`, `text_fonts`, `text_alignments`,
  `{date}`, `{count}`), laid out as in pibooth. Drawn over a single photo, with room made on preset collages; a
  template can change this or opt out with `footer`.
* A template's own `texts` now work on single photos without a `size`, accept `font_size`, and support `{time}`.
* `pibooth-media-templates preview --footer TEXT` previews footer text.
* The Photo Strip example uses a white canvas so the default black footer text is readable.

## 0.1.1

* Template icons are frosted-glass tiles floating over the wait screen, instead of a solid bar.
* `icon:` takes a Google Material icon name (as in photobooth-app) or an image file; bundled outlined and filled
  Material Icons fonts, `icon_style` option, type-based default icons, suggestions for misspelt names.
* `color:` sets the tint of a template's tile.

## 0.1.0

* Initial release: YAML media templates (single, collage, animation, video, wigglegram) chosen from an icon bar on the wait screen, with per-template and per-slot background replacement through pibooth-modnet.
