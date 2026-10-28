"""Shared test fixtures: a fake ``picamera2`` so tests run without a camera.

The real ``CameraDeviceManager`` from rpi-app-framework is used; only the
``picamera2`` library underneath it is replaced.
"""

import sys
import types

import numpy as np
import pytest


class FakePicamera2:
    """Stand-in for ``picamera2.Picamera2`` that returns queued frames.

    Attributes:
        frames (list): Frames for ``capture_array``, used in order; the last
            one repeats. Set by tests through the ``fake_camera`` fixture.
        config: Last configuration passed to ``configure``.
        options (dict): Encoder options.
        closed (bool): True after ``close``.
        controls (dict): All controls set so far (later calls override).
        control_calls (list): Each dict passed to ``set_controls``.
        lux (float or None): Class attribute: the ``Lux`` every camera
            reports in its metadata (None leaves the key out). Tests change
            it through the ``fake_camera`` fixture to simulate dusk and dawn.
        camera_controls (dict): IMX219-like control ranges.
    """

    instances = []
    lux = 300.0
    camera_controls = {
        "ExposureTime": (75, 11_766_829, 20_000),
        "AnalogueGain": (1.0, 10.666667, 1.0),
        "FrameDurationLimits": (47_183, 11_767_556, 33_333),
    }
    NORMAL_FRAME_US = 33_333

    def __init__(self, camera_num=0):
        """Open the fake camera."""
        self.camera_num = camera_num
        self.frames = []
        self.config = None
        self.options = {}
        self.closed = False
        self.controls = {}
        self.control_calls = []
        FakePicamera2.instances.append(self)

    def create_video_configuration(self, main=None):
        """Return a config dict running at 30 fps."""
        frame = self.NORMAL_FRAME_US
        return {"main": main, "controls": {"FrameDurationLimits": (frame, frame)}}

    def set_controls(self, controls):
        """Record and apply controls (they take effect at once here)."""
        self.control_calls.append(dict(controls))
        self.controls.update(controls)

    def capture_metadata(self):
        """Return metadata reflecting the current controls and ``lux``."""
        if self.controls.get("AeEnable", True):
            exposure, gain = 10_000, 1.0
            frame = self.NORMAL_FRAME_US
        else:
            exposure = self.controls["ExposureTime"]
            gain = self.controls["AnalogueGain"]
            frame = max(exposure, self.NORMAL_FRAME_US)
        md = {"ExposureTime": exposure, "AnalogueGain": gain, "FrameDuration": frame}
        if FakePicamera2.lux is not None:
            md["Lux"] = FakePicamera2.lux
        return md

    def configure(self, config):
        """Store the config."""
        self.config = config

    def start(self):
        """Start the camera."""

    def stop(self):
        """Stop the camera."""

    def close(self):
        """Release the camera."""
        self.closed = True

    def capture_array(self, name="main"):
        """Return the next queued frame, or a black one of the configured size."""
        if len(self.frames) > 1:
            return self.frames.pop(0)
        if self.frames:
            return self.frames[0]
        width, height = self.config["main"]["size"]
        return np.zeros((height, width, 3), dtype=np.uint8)

    def capture_file(self, target, format=None):
        """Write a tiny fake JPEG to a path or file object."""
        data = b"\xff\xd8JPEG\xff\xd9"
        if hasattr(target, "write"):
            target.write(data)
        else:
            with open(target, "wb") as f:
                f.write(data)


@pytest.fixture
def fake_camera(monkeypatch):
    """Install a fake ``picamera2`` module.

    Returns:
        type: :class:`FakePicamera2`; ``FakePicamera2.instances[-1]`` is the
        camera the app opened, and setting ``.lux`` changes the light level
        (300 lux, daylight, by default).
    """
    module = types.ModuleType("picamera2")
    module.Picamera2 = FakePicamera2
    monkeypatch.setitem(sys.modules, "picamera2", module)
    FakePicamera2.instances = []
    FakePicamera2.lux = 300.0
    return FakePicamera2


def field_frame(width=320, height=240, deer=None, brightness=150, seed=0):
    """Make a test frame: a pale noisy field, optionally with a dark "deer".

    Args:
        width: Frame width in pixels.
        height: Frame height in pixels.
        deer: ``(x0, y0, x1, y1)`` of a dark rectangle, or None.
        brightness: Field brightness 0-255.
        seed: Random seed for the sensor noise.

    Returns:
        numpy.ndarray: ``height x width x 3`` ``uint8`` BGR frame.
    """
    rng = np.random.default_rng(seed)
    frame = rng.normal(brightness, 4, (height, width, 3)).clip(0, 255)
    if deer is not None:
        x0, y0, x1, y1 = deer
        frame[y0:y1, x0:x1] = 60
    return frame.astype(np.uint8)
