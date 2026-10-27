"""The field-unit app: capture, compare, save.

Every ``interval`` seconds the app takes a frame from the camera, runs it
through a :class:`~critter_counter.detector.ChangeDetector`, and when
something changed saves the full frame and a close-up (at most once per
``cooldown``). A live view for aiming and focusing is served at
``http://<pi>:8000/`` unless turned off.

Daytime only for now: the camera runs on auto exposure. Night mode needs
exposure and gain control in rpi-app-framework's CameraDeviceManager (see the
README, "Framework changes needed").
"""

import time

from rpi_app_framework import RPIApp
from rpi_app_framework.camera import CameraDeviceManager
from rpi_app_framework.mjpeg_server import MJPEGStreamingManager

from .detector import ChangeDetector
from .settings import Settings
from .storage import save_detection


class CritterCounterApp(RPIApp):
    """Watch the field and save images of anything that crosses it.

    Attributes:
        settings (Settings): The app's configuration.
        cam (CameraDeviceManager): The camera (after :meth:`setup`).
        stream (MJPEGStreamingManager or None): Live view, if enabled.
        detector (ChangeDetector): Background model and change test.
        detections_saved (int): Detections saved since start.
    """

    def __init__(self, settings=None, **kwargs):
        """Create the app; devices are opened in :meth:`setup`.

        Args:
            settings: A :class:`Settings`; defaults to ``Settings()``.
            **kwargs: Passed to ``RPIApp`` (``app_name`` defaults to
                ``"CritterCounter"``, ``loop_interval`` to
                ``settings.interval``).
        """
        self.settings = settings if settings is not None else Settings()
        kwargs.setdefault("app_name", "CritterCounter")
        kwargs.setdefault("loop_interval", self.settings.interval)
        super().__init__(**kwargs)
        self.cam = None
        self.stream = None
        self.detector = None
        self.detections_saved = 0
        self._last_save = None

    def setup(self):
        """Open the camera, start the live view, and create the detector."""
        s = self.settings
        self.cam = CameraDeviceManager("cam", resolution=s.resolution, app=self)
        if s.stream_port is not None:
            self.stream = MJPEGStreamingManager(
                "stream",
                camera=self.cam,
                port=s.stream_port,
                fps=s.stream_fps,
                app=self,
            )
            self.log("live view: http://<this pi>:{}/".format(self.stream.port))
        self.detector = ChangeDetector(
            scale=s.scale,
            pixel_threshold=s.pixel_threshold,
            min_changed_pixels=s.min_changed_pixels,
            max_changed_fraction=s.max_changed_fraction,
            learning_rate=s.learning_rate,
            min_neighbors=s.min_neighbors,
        )
        self.log(
            "watching every {}s, detections in {}/".format(s.interval, s.detections_dir)
        )

    def loop(self):
        """Capture one frame, check it, and save it if something changed.

        Returns:
            None: The app runs until stopped.
        """
        frame = self.cam.capture_frame()
        detection = self.detector.update(frame)
        if self.detector.scene_changed:
            self.log("whole scene changed; background reset")
        if detection is None:
            return None
        now = time.monotonic()
        if (
            self._last_save is not None
            and now - self._last_save < self.settings.cooldown
        ):
            return None
        s = self.settings
        full, crop = save_detection(
            frame,
            detection,
            s.detections_dir,
            pad=s.crop_pad,
            min_size=s.crop_min_size,
            quality=s.jpeg_quality,
        )
        self._last_save = now
        self.detections_saved += 1
        self.log(
            "detection {} at {}: {} px changed, peak {:.0f} -> {}".format(
                self.detections_saved,
                detection.box,
                detection.changed_pixels,
                detection.peak_difference,
                crop,
            )
        )
        return None

    def teardown(self):
        """Log a summary; the framework then closes the stream and camera."""
        self.log("saved {} detections".format(self.detections_saved))
