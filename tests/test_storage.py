"""Tests for ``critter_counter.storage``."""

import os
import time

import numpy as np
import pytest
from PIL import Image

from critter_counter.detector import Detection
from critter_counter.storage import crop_box, save_detection, save_jpeg


def test_crop_box_pads_and_respects_min_size():
    """A small box grows to min_size, centered on the box."""
    assert crop_box((100, 100, 110, 110), (1000, 800), pad=0.5, min_size=40) == (
        85,
        85,
        125,
        125,
    )


def test_crop_box_pads_large_box():
    """A box larger than min_size grows by pad on each side."""
    assert crop_box((200, 200, 300, 260), (1000, 800), pad=0.5, min_size=10) == (
        150,
        170,
        350,
        290,
    )


def test_crop_box_stays_inside_frame():
    """A box at the edge is shifted, and never larger than the frame."""
    assert crop_box((0, 0, 10, 10), (100, 50), pad=0, min_size=40) == (0, 0, 40, 40)
    assert crop_box((90, 40, 100, 50), (100, 50), pad=0, min_size=40) == (
        60,
        10,
        100,
        50,
    )
    assert crop_box((0, 0, 10, 10), (30, 20), pad=0, min_size=100) == (0, 0, 30, 20)


def test_crop_box_rejects_negative():
    """Negative pad or min_size is an error."""
    with pytest.raises(ValueError):
        crop_box((0, 0, 1, 1), (10, 10), pad=-1)


def test_save_jpeg_converts_bgr_to_rgb(tmp_path):
    """A BGR red pixel is saved as red."""
    frame = np.zeros((16, 16, 3), np.uint8)
    frame[...] = (0, 0, 255)
    path = save_jpeg(frame, str(tmp_path / "red.jpg"))
    r, g, b = Image.open(path).convert("RGB").getpixel((8, 8))
    assert r > 200 and g < 50 and b < 50


def test_save_detection_writes_day_folder(tmp_path):
    """Full frame and crop go in a dated folder; same-second names don't clash."""
    frame = np.zeros((240, 320, 3), np.uint8)
    det = Detection(
        box=(100, 80, 140, 104),
        changed_pixels=60,
        changed_fraction=0.01,
        peak_difference=90.0,
    )
    when = time.strptime("2026-10-27 18:30:05", "%Y-%m-%d %H:%M:%S")
    full, crop = save_detection(frame, det, str(tmp_path), when=when, min_size=64)
    assert full == os.path.join(str(tmp_path), "2026-10-27", "183005_full.jpg")
    assert Image.open(full).size == (320, 240)
    assert Image.open(crop).size == (80, 64)  # 40 px wide + 50% each side
    full2, _ = save_detection(frame, det, str(tmp_path), when=when)
    assert full2.endswith("183005_2_full.jpg")
