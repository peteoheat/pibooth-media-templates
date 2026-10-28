# -*- coding: utf-8 -*-
"""Animation, wigglegram and video outputs built from the processed captures.

pibooth captures stills, so every output here is assembled from them. The
final still picture that pibooth shows and prints comes from ``render.py``;
the files written here sit next to it, sharing its name:
``2026-10-27-14-03-11_pibooth.jpg`` -> ``2026-10-27-14-03-11_pibooth.gif``.
"""

import os.path as osp
import shutil
import subprocess
import logging

from PIL import Image

from .render import apply_overlay

try:
    import cv2
    import numpy as np
except ImportError:  # Wigglegram alignment and the fallback video writer need OpenCV
    cv2 = None
    np = None

LOGGER = logging.getLogger("pibooth-media-templates")

DEFAULT_SIZE = {'animation': 800, 'wigglegram': 800, 'video': 1280}


def _scaled(image, long_side):
    scale = long_side / float(max(image.size))
    if scale >= 1:
        return image
    return image.resize((max(2, int(image.width * scale)), max(2, int(image.height * scale))),
                        Image.Resampling.LANCZOS)


def build_frames(template, processed):
    """One frame per capture, scaled to the output size with the overlay applied."""
    options = template.media
    long_side = int(options.get('size', DEFAULT_SIZE[template.type]))
    overlay = template.media_overlay or (template.overlay if template.native else None)
    frames = []
    for image in processed:
        frame = _scaled(image, long_side)
        if overlay:
            frame = apply_overlay(frame, overlay)
        frames.append(frame)
    return frames


# --------------------------------------------------------------------------
# Wigglegram
# --------------------------------------------------------------------------

def align_frames(frames, focus=(0.5, 0.5)):
    """Shift every frame so the subject stays still, then crop the borders.

    A wigglegram only works when the subject (not the background) is the part
    that stays fixed: the shift of each frame relative to the first one is
    measured around ``focus`` (fractions of the width/height) by phase
    correlation, and the frames are translated to cancel it.
    """
    if cv2 is None or len(frames) < 2:
        if cv2 is None:
            LOGGER.warning("Wigglegram alignment needs OpenCV, frames are not aligned")
        return frames

    width, height = frames[0].size
    scale = 400.0 / max(width, height)
    small = (max(8, int(width * scale)), max(8, int(height * scale)))

    def grey(frame):
        return cv2.resize(cv2.cvtColor(np.asarray(frame.convert('RGB')), cv2.COLOR_RGB2GRAY), small,
                          interpolation=cv2.INTER_AREA).astype(np.float32)

    # Correlate on the central region where the guests are
    cx, cy = int(small[0] * focus[0]), int(small[1] * focus[1])
    half_w, half_h = small[0] // 3, small[1] // 3
    box = (slice(max(0, cy - half_h), cy + half_h), slice(max(0, cx - half_w), cx + half_w))
    reference = grey(frames[0])[box]
    window = cv2.createHanningWindow(reference.shape[::-1], cv2.CV_32F)

    shifts = [(0.0, 0.0)]
    for frame in frames[1:]:
        (dx, dy), _ = cv2.phaseCorrelate(reference, grey(frame)[box], window)
        shifts.append((dx / scale, dy / scale))

    aligned = []
    for frame, (dx, dy) in zip(frames, shifts):
        matrix = np.float32([[1, 0, -dx], [0, 1, -dy]])
        shifted = cv2.warpAffine(np.asarray(frame.convert('RGB')), matrix, (width, height),
                                 flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        aligned.append(Image.fromarray(shifted))

    # Crop what the shifts exposed so the wiggle has clean edges
    pad_x = int(max(abs(dx) for dx, _ in shifts)) + 1
    pad_y = int(max(abs(dy) for _, dy in shifts)) + 1
    if width - 2 * pad_x > 16 and height - 2 * pad_y > 16:
        aligned = [f.crop((pad_x, pad_y, width - pad_x, height - pad_y)) for f in aligned]
    return aligned


def ping_pong(frames):
    """1 2 3 -> 1 2 3 2: loops without a jump."""
    return frames + frames[-2:0:-1] if len(frames) > 2 else frames + frames[::-1][1:-1]


# --------------------------------------------------------------------------
# Writers
# --------------------------------------------------------------------------

def save_animation(frames, path, frame_ms=500, fmt='gif'):
    """Save an endlessly looping animated GIF or WebP."""
    first, rest = frames[0], frames[1:]
    if fmt == 'webp':
        first.save(path, format='WEBP', save_all=True, append_images=rest, duration=frame_ms,
                   loop=0, quality=80, method=4)
    else:
        first.save(path, format='GIF', save_all=True, append_images=rest, duration=frame_ms,
                   loop=0, disposal=2)
    return path


def _find_ffmpeg():
    exe = shutil.which('ffmpeg')
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _video_frames(frames, fps, hold, fade):
    """Yield each frame held for ``hold`` seconds, cross-fading into the next."""
    hold_count = max(1, int(round(hold * fps)))
    fade_count = int(round(fade * fps))
    for index, frame in enumerate(frames):
        for _ in range(hold_count):
            yield frame
        if fade_count and index + 1 < len(frames):
            for step in range(1, fade_count + 1):
                yield Image.blend(frame, frames[index + 1], step / float(fade_count + 1))


def write_video(frames, path, fps=25, hold=1.0, fade=0.3):
    """Write an H.264 MP4 slideshow (ffmpeg), or MPEG-4 through OpenCV if there is no ffmpeg."""
    width, height = frames[0].size
    width, height = width - width % 2, height - height % 2  # H.264 wants even sizes
    frames = [f.convert('RGB').crop((0, 0, width, height)) for f in frames]

    ffmpeg = _find_ffmpeg()
    if ffmpeg:
        command = [ffmpeg, '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                   '-s', '{}x{}'.format(width, height), '-r', str(fps), '-i', '-',
                   '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p',
                   '-movflags', '+faststart', path]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for frame in _video_frames(frames, fps, hold, fade):
                process.stdin.write(frame.tobytes())
            process.stdin.close()
            error = process.stderr.read().decode('utf-8', 'replace')
            if process.wait() != 0:
                raise RuntimeError("ffmpeg failed: {}".format(error.strip()))
        finally:
            if process.poll() is None:
                process.kill()
        return path

    if cv2 is None:
        raise RuntimeError("video needs ffmpeg (sudo apt install ffmpeg) or OpenCV")
    LOGGER.warning("ffmpeg not found, using OpenCV's MPEG-4 writer (bigger files, less compatible)")
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))
    try:
        for frame in _video_frames(frames, fps, hold, fade):
            writer.write(cv2.cvtColor(np.asarray(frame), cv2.COLOR_RGB2BGR))
    finally:
        writer.release()
    return path


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def media_frames(template, processed):
    """The frames of an animation, wigglegram or video template, in playing order.

    :return: list of PIL images, or [] for still-only templates
    """
    if template.type not in DEFAULT_SIZE:
        return []
    options = template.media
    frames = build_frames(template, processed)
    if template.type == 'animation':
        return ping_pong(frames) if options.get('boomerang', False) else frames
    if template.type == 'wigglegram':
        if options.get('align', True):
            frames = align_frames(frames)
        return ping_pong(frames)
    return frames


def frame_delay(template):
    """Seconds each frame of ``media_frames`` stays on screen."""
    options = template.media
    if template.type == 'animation':
        return int(options.get('frame_ms', 500)) / 1000.0
    if template.type == 'wigglegram':
        return int(options.get('frame_ms', 120)) / 1000.0
    return float(options.get('frame_s', 1.0))


def generate_media(template, processed, stem, frames=None):
    """Create the extra file of an animation, wigglegram or video template.

    :param stem: output path without extension
    :param frames: result of ``media_frames`` if already computed
    :return: path of the file written, or None for still-only templates
    """
    if template.type not in DEFAULT_SIZE:
        return None  # single and collage templates only produce the still picture
    options = template.media
    frames = frames or media_frames(template, processed)

    if template.type in ('animation', 'wigglegram'):
        fmt = str(options.get('format', 'gif')).lower()
        return save_animation(frames, '{}.{}'.format(stem, fmt), int(frame_delay(template) * 1000), fmt)

    return write_video(frames, stem + '.mp4', int(options.get('fps', 25)),
                       float(options.get('frame_s', 1.0)), float(options.get('fade_s', 0.3)))


def media_stem(picture_path):
    return osp.splitext(picture_path)[0]
