"""Save detection images: the full frame and a close-up of the changed region.

Images go into one folder per day, tagged with the capture mode::

    detections/2026-10-27/183005_night_full.jpg
    detections/2026-10-27/183005_night_crop.jpg

Typical usage:

    full, crop = save_detection(frame, detection, "detections", tag="night")
"""

import os
import time

import numpy as np


def crop_box(box, frame_size, pad=0.5, min_size=160):
    """Grow a box for a close-up and keep it inside the frame.

    Args:
        box: ``(x0, y0, x1, y1)`` in pixels, ``x1``/``y1`` exclusive.
        frame_size: ``(width, height)`` of the frame in pixels.
        pad: Extra margin on each side as a fraction of the box size, e.g.
            0.5 makes the box twice as wide and tall.
        min_size: Smallest crop width and height in pixels (limited to the
            frame size), so tiny detections still give a usable picture.

    Returns:
        tuple: ``(x0, y0, x1, y1)`` of the crop, inside the frame.

    Raises:
        ValueError: If ``pad`` or ``min_size`` is negative.
    """
    if pad < 0 or min_size < 0:
        raise ValueError("pad and min_size must be >= 0")
    result = []
    for lo, hi, limit in (
        (box[0], box[2], frame_size[0]),
        (box[1], box[3], frame_size[1]),
    ):
        size = hi - lo
        new_size = min(
            max(int(round(size * (1 + 2 * pad))), int(min_size), size), limit
        )
        start = int(round((lo + hi) / 2 - new_size / 2))
        start = max(0, min(start, limit - new_size))
        result.append((start, start + new_size))
    (x0, x1), (y0, y1) = result
    return (x0, y0, x1, y1)


def save_jpeg(frame, path, quality=90):
    """Write a BGR frame as a JPEG.

    Args:
        frame: ``height x width x 3`` ``uint8`` array in BGR order.
        path: File to write; its folder must exist.
        quality: JPEG quality 1-95.

    Returns:
        str: ``path``.
    """
    from PIL import Image

    rgb = np.ascontiguousarray(frame[..., 2::-1])
    Image.fromarray(rgb).save(path, format="JPEG", quality=quality)
    return path


def save_detection(
    frame, detection, root, when=None, pad=0.5, min_size=160, quality=90, tag=None
):
    """Save the full frame and a close-up of a detection.

    Args:
        frame: The ``height x width x 3`` BGR frame the detection came from.
        detection: A :class:`~critter_counter.detector.Detection`.
        root: Base folder; a ``YYYY-MM-DD`` folder is created inside it.
        when: ``time.struct_time`` used for the names; defaults to now
            (local time).
        pad: Close-up margin, see :func:`crop_box`.
        min_size: Smallest close-up size in pixels, see :func:`crop_box`.
        quality: JPEG quality 1-95.
        tag: Word added to the names, e.g. ``"night"``
            (``183005_night_full.jpg``); None for no tag.

    Returns:
        tuple: ``(full_path, crop_path)``.
    """
    if when is None:
        when = time.localtime()
    folder = os.path.join(root, time.strftime("%Y-%m-%d", when))
    os.makedirs(folder, exist_ok=True)
    stem = os.path.join(folder, time.strftime("%H%M%S", when))
    if tag:
        stem += "_" + tag
    base, n = stem, 2
    while os.path.exists(base + "_full.jpg"):
        base, n = "{}_{}".format(stem, n), n + 1

    height, width = frame.shape[:2]
    x0, y0, x1, y1 = crop_box(detection.box, (width, height), pad, min_size)
    full = save_jpeg(frame, base + "_full.jpg", quality)
    crop = save_jpeg(frame[y0:y1, x0:x1], base + "_crop.jpg", quality)
    return full, crop
