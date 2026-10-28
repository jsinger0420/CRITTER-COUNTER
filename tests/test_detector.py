"""Tests for ``critter_counter.detector``."""

import numpy as np
import pytest

from conftest import field_frame
from critter_counter.detector import ChangeDetector, downscale_gray, neighbor_count


def test_downscale_gray_averages_blocks():
    """Each output pixel is the luma of its block's mean color."""
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    frame[:4, :4] = (0, 0, 255)  # pure red (BGR), top-left block
    small = downscale_gray(frame, 4)
    assert small.shape == (2, 2)
    assert small.dtype == np.float32
    assert small[0, 0] == pytest.approx(255 * 0.299, abs=0.01)
    assert small[1, 1] == 0


def test_downscale_gray_drops_partial_blocks():
    """Rows and columns that don't fill a block are ignored."""
    assert downscale_gray(np.zeros((10, 13, 3), np.uint8), 4).shape == (2, 3)


def test_downscale_gray_rejects_tiny_frame():
    """A frame smaller than one block is an error."""
    with pytest.raises(ValueError):
        downscale_gray(np.zeros((2, 2, 3), np.uint8), 4)


def test_neighbor_count():
    """Counts the 8 surrounding pixels, not the pixel itself."""
    mask = np.zeros((3, 3), bool)
    mask[1, 1] = True
    count = neighbor_count(mask)
    assert count[1, 1] == 0
    assert count[0, 0] == 1
    assert neighbor_count(np.ones((3, 3), bool))[1, 1] == 8


def test_first_frame_learns_background():
    """The first frame never gives a detection."""
    detector = ChangeDetector()
    assert not detector.ready
    assert detector.update(field_frame()) is None
    assert detector.ready


def test_no_detection_on_noise_alone():
    """Sensor noise on an unchanged field is ignored."""
    detector = ChangeDetector()
    detector.update(field_frame(seed=0))
    for seed in range(1, 5):
        assert detector.update(field_frame(seed=seed)) is None


def test_detects_deer_and_reports_full_res_box():
    """A dark animal on a pale field is found where it is."""
    detector = ChangeDetector(scale=4)
    detector.update(field_frame(seed=0))
    detection = detector.update(field_frame(seed=1, deer=(100, 80, 140, 104)))
    assert detection is not None
    x0, y0, x1, y1 = detection.box
    assert (x0, y0, x1, y1) == (100, 80, 140, 104)
    assert detection.changed_pixels == 10 * 6
    assert detection.peak_difference > 50


def test_single_pixel_change_is_filtered():
    """An isolated changed pixel (a bug, a speck of noise) is not a detection."""
    detector = ChangeDetector(scale=4, min_changed_pixels=1)
    detector.update(field_frame(seed=0))
    assert detector.update(field_frame(seed=1, deer=(100, 80, 104, 84))) is None


def test_whole_scene_change_resets_background():
    """A cloud or exposure change is not a detection, and is learned at once."""
    detector = ChangeDetector()
    detector.update(field_frame(brightness=150))
    assert detector.update(field_frame(brightness=90, seed=1)) is None
    assert detector.scene_changed
    assert detector.update(field_frame(brightness=90, seed=2)) is None
    assert not detector.scene_changed


def test_reset_forgets_background():
    """After reset() the next frame is learned, not compared."""
    detector = ChangeDetector()
    detector.update(field_frame())
    detector.reset()
    assert not detector.ready
    assert detector.update(field_frame(deer=(100, 80, 140, 104))) is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"scale": 0},
        {"scale": 2.0},
        {"pixel_threshold": 300},
        {"min_changed_pixels": 0},
        {"max_changed_fraction": 0},
        {"learning_rate": 1.5},
        {"min_neighbors": 9},
    ],
)
def test_invalid_arguments(kwargs):
    """Out-of-range settings are rejected."""
    with pytest.raises(ValueError):
        ChangeDetector(**kwargs)


def test_brightness_reported_and_cleared_by_reset():
    """The detector reports each frame's mean brightness; reset() clears it."""
    detector = ChangeDetector()
    assert detector.brightness is None
    detector.update(field_frame(brightness=150))
    assert detector.brightness == pytest.approx(150, abs=1)
    detector.reset()
    assert detector.brightness is None
