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
    assert [f[-13:] for f in files] == ["_day_crop.jpg", "_day_full.jpg"]
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


def night_controls(cam):
    """Return the controls a camera received for its last manual exposure."""
    return [c for c in cam.control_calls if c.get("AeEnable") is False][-1]


def test_starts_in_day_when_bright(tmp_path, fake_camera):
    """In daylight the camera stays on auto exposure."""
    app = make_app(tmp_path)
    app.setup()
    cam = fake_camera.instances[-1]
    assert app.mode == "day"
    assert all(c["AeEnable"] for c in cam.control_calls)
    assert app.cam.exposure["mode"] == "auto"
    assert app.detector.pixel_threshold == 25.0
    app.stop()


def test_starts_in_night_when_dark(tmp_path, fake_camera):
    """Started after dark, the first reading goes straight to night settings."""
    fake_camera.lux = 2.0
    app = make_app(tmp_path)
    app.setup()
    cam = fake_camera.instances[-1]
    assert app.mode == "night"
    assert app.mode_switches == 0
    assert night_controls(cam) == {
        "AeEnable": False,
        "ExposureTime": 4_000_000,
        "AnalogueGain": 8.0,
        "FrameDurationLimits": (4_000_000, 4_000_000),
        "AwbEnable": False,
        "ColourGains": (1.0, 1.0),
    }
    assert app.detector.pixel_threshold == 35.0
    app.stop()


def test_dusk_switches_to_night_after_confirmed_readings(tmp_path, fake_camera):
    """Dark readings in a row switch to night; the background is relearned."""
    app = make_app(tmp_path, light_check_interval=0, light_confirm=3)
    app.setup()
    cam = fake_camera.instances[-1]
    cam.frames = [field_frame(seed=0)]
    app.loop()
    assert app.detector.ready
    fake_camera.lux = 3.0
    app.loop()
    app.loop()
    assert app.mode == "day"
    app.loop()
    assert app.mode == "night"
    assert app.mode_switches == 1
    assert night_controls(cam)["ExposureTime"] == 4_000_000
    app.stop()


def test_dawn_switches_back_to_day(tmp_path, fake_camera):
    """Bright readings at night restore auto exposure and the day threshold."""
    fake_camera.lux = 2.0
    app = make_app(tmp_path, light_check_interval=0, light_confirm=1)
    app.setup()
    cam = fake_camera.instances[-1]
    fake_camera.lux = 200.0
    app.loop()
    assert app.mode == "day"
    assert cam.control_calls[-1] == {
        "AeEnable": True,
        "AwbEnable": True,
        "FrameDurationLimits": (33_333, 33_333),
    }
    assert app.detector.pixel_threshold == 25.0
    assert app.mode_switches == 1
    app.stop()


def test_overexposed_night_frames_switch_to_day(tmp_path, fake_camera):
    """Without Lux, an over-exposed night frame (dawn) still ends the night."""
    fake_camera.lux = 2.0
    app = make_app(tmp_path, light_check_interval=0, light_confirm=1)
    app.setup()
    cam = fake_camera.instances[-1]
    fake_camera.lux = None
    cam.frames = [field_frame(brightness=235)]
    app.loop()  # captures the bright frame; no brightness known before it
    assert app.mode == "night"
    app.loop()  # this check sees brightness 235
    assert app.mode == "day"
    app.stop()


def test_fixed_mode_never_switches(tmp_path, fake_camera):
    """--mode night stays at night in daylight and reads no light level."""
    app = make_app(tmp_path, mode="night", light_check_interval=0)
    app.setup()
    assert app.mode == "night" and app.monitor is None
    for _ in range(3):
        app.loop()
    assert app.mode == "night"
    assert len(fake_camera.instances[-1].control_calls) == 1
    app.stop()


def test_night_detections_are_tagged(tmp_path, fake_camera):
    """Images saved at night carry 'night' in their names."""
    fake_camera.lux = 2.0
    app = make_app(tmp_path)
    app.setup()
    fake_camera.instances[-1].frames = [
        field_frame(seed=0),
        field_frame(seed=1, deer=(100, 80, 140, 104)),
    ]
    app.loop()
    app.loop()
    app.stop()
    assert [f[-15:] for f in saved_files(tmp_path)] == [
        "_night_crop.jpg",
        "_night_full.jpg",
    ]


def test_no_lux_stays_day_and_warns_once(tmp_path, fake_camera):
    """A camera without Lux stays in day mode and says so once."""
    fake_camera.lux = None
    app = make_app(tmp_path, light_check_interval=0, light_confirm=1)
    lines = []
    app.log = lines.append
    app.setup()
    fake_camera.instances[-1].frames = [field_frame(brightness=20)]
    for _ in range(3):
        app.loop()
    assert app.mode == "day"
    assert sum("no Lux" in line for line in lines) == 1
    app.stop()


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


def test_settings_night_options():
    """Night options parse, including auto white balance."""
    s = Settings.from_args(
        [
            "--mode",
            "night",
            "--night-exposure-us",
            "2000000",
            "--night-gain",
            "6",
            "--night-awb",
            "1.5,1.2",
        ]
    )
    assert (s.mode, s.night_exposure_us, s.night_gain) == ("night", 2_000_000, 6.0)
    assert s.night_awb == (1.5, 1.2)
    assert Settings.from_args(["--night-awb", "auto"]).night_awb is None
    with pytest.raises(SystemExit):
        Settings.from_args(["--night-awb", "1"])
    with pytest.raises(SystemExit):
        Settings.from_args(["--mode", "dusk"])


def test_settings_validation():
    """Bad values in code are rejected too."""
    with pytest.raises(ValueError):
        Settings(mode="dusk")
    with pytest.raises(ValueError):
        Settings(night_exposure_us=0)
    with pytest.raises(ValueError):
        Settings(interval=0)
