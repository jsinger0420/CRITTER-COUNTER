"""Tests for ``critter_counter.app`` and the command line, with a fake camera."""

import os

import pytest

from conftest import field_frame
from critter_counter.app import CritterCounterApp
from critter_counter.settings import Settings


def make_app(tmp_path, **overrides):
    """Create an app that writes into ``tmp_path`` with no file logging."""
    values = dict(
        resolution=(320, 240),
        detections_dir=str(tmp_path / "detections"),
        stream_port=None,
        cooldown=0,
    )
    values.update(overrides)
    return CritterCounterApp(Settings(**values), enable_file_logging=False)


def saved_files(tmp_path):
    """List every file saved under the detections folder."""
    found = []
    for folder, _, files in os.walk(tmp_path / "detections"):
        found += [os.path.join(folder, f) for f in files]
    return sorted(found)


def test_saves_full_frame_and_crop_on_detection(tmp_path, fake_camera):
    """A deer appearing gives one _full and one _crop image."""
    app = make_app(tmp_path)
    app.setup()
    cam = fake_camera.instances[-1]
    assert cam.config["main"]["size"] == (320, 240)
    cam.frames = [field_frame(seed=0), field_frame(seed=1, deer=(100, 80, 140, 104))]
    app.loop()
    app.loop()
    app.stop()
    files = saved_files(tmp_path)
    assert [f[-9:] for f in files] == ["_crop.jpg", "_full.jpg"]
    assert app.detections_saved == 1
    assert cam.closed


def test_nothing_saved_when_field_is_empty(tmp_path, fake_camera):
    """Noise alone saves nothing."""
    app = make_app(tmp_path)
    app.setup()
    fake_camera.instances[-1].frames = [field_frame(seed=s) for s in range(4)]
    for _ in range(4):
        app.loop()
    app.stop()
    assert saved_files(tmp_path) == []


def test_cooldown_limits_saves(tmp_path, fake_camera):
    """Within the cooldown a continuing detection is saved only once."""
    app = make_app(tmp_path, cooldown=3600)
    app.setup()
    fake_camera.instances[-1].frames = [field_frame(seed=0)] + [
        field_frame(seed=s, deer=(100, 80, 140, 104)) for s in range(1, 4)
    ]
    for _ in range(4):
        app.loop()
    app.stop()
    assert app.detections_saved == 1


def test_live_view_starts_and_closes(tmp_path, fake_camera):
    """With a port, the MJPEG stream is created and closed on stop."""
    app = make_app(tmp_path, stream_port=0)
    app.setup()
    assert app.stream is not None and app.stream.is_streaming
    app.stop()
    assert not app.stream.is_streaming


def test_settings_from_args():
    """Command-line options override the defaults."""
    s = Settings.from_args(
        ["--interval", "5", "--resolution", "1280x720", "--pixel-threshold", "30"]
    )
    assert s.interval == 5.0
    assert s.resolution == (1280, 720)
    assert s.pixel_threshold == 30.0
    assert s.stream_port == 8000
    assert Settings.from_args(["--no-stream"]).stream_port is None


def test_settings_rejects_bad_resolution():
    """A malformed resolution exits with a usage error."""
    with pytest.raises(SystemExit):
        Settings.from_args(["--resolution", "big"])
