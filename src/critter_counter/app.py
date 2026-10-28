"""The field-unit app: capture, compare, save, by day and by night.

Every ``interval`` seconds the app takes a frame from the camera, runs it
through a :class:`~critter_counter.detector.ChangeDetector`, and when
something changed saves the full frame and a close-up (at most once per
``cooldown``). A live view for aiming and focusing is served at
``http://<pi>:8000/`` unless turned off.

Day and night: by day the camera runs on auto exposure. At night it uses a
fixed long exposure and high gain (``night_exposure_us``, ``night_gain``,
``night_awb``), set through ``CameraDeviceManager.set_exposure()``. In
``auto`` mode a :class:`~critter_counter.daynight.DayNightMonitor` decides
when to switch from the camera's ``Lux`` estimate, read every
``light_check_interval`` seconds. Each switch resets the background (the
whole image changes) and uses the detection threshold for the new mode.
"""

import time

from rpi_app_framework import RPIApp
from rpi_app_framework.camera import CameraDeviceManager
from rpi_app_framework.mjpeg_server import MJPEGStreamingManager

from .daynight import DAY, NIGHT, DayNightMonitor
from .detector import ChangeDetector
from .settings import Settings
from .storage import save_detection

STATUS_LOG_INTERVAL = 3600.0  # seconds between light-level lines in the log


class CritterCounterApp(RPIApp):
    """Watch the field day and night and save images of anything that crosses it.

    Attributes:
        settings (Settings): The app's configuration.
        cam (CameraDeviceManager): The camera (after :meth:`setup`).
        stream (MJPEGStreamingManager or None): Live view, if enabled.
        detector (ChangeDetector): Background model and change test.
        monitor (DayNightMonitor or None): Day/night decisions in ``auto``
            mode; None when the mode is fixed.
        mode (str or None): ``"day"`` or ``"night"`` once set up.
        detections_saved (int): Detections saved since start.
        mode_switches (int): Day/night switches since start (the first
            mode set in :meth:`setup` is not counted).
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
        self.monitor = None
        self.mode = None
        self.detections_saved = 0
        self.mode_switches = 0
        self._last_save = None
        self._last_light_check = None
        self._last_status_log = None
        self._warned_no_lux = False

    def setup(self):
        """Open the camera and live view, create the detector, pick day or night."""
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
        if s.mode == "auto":
            self.monitor = DayNightMonitor(
                night_below_lux=s.night_below_lux,
                day_above_lux=s.day_above_lux,
                confirm=s.light_confirm,
                overexposed_level=s.overexposed_level,
            )
            self._check_light()  # the first reading picks the starting mode
        else:
            self._apply_mode(s.mode, reason="fixed by --mode")
        self.log(
            "watching every {}s in {} mode ({}), detections in {}/".format(
                s.interval, self.mode, s.mode, s.detections_dir
            )
        )

    def loop(self):
        """Check the light when due, then capture, compare and save one frame.

        Returns:
            None: The app runs until stopped.
        """
        if self.monitor is not None and (
            time.monotonic() - self._last_light_check
            >= self.settings.light_check_interval
        ):
            self._check_light()
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
            tag=self.mode,
        )
        self._last_save = now
        self.detections_saved += 1
        self.log(
            "detection {} ({}) at {}: {} px changed, peak {:.0f} -> {}".format(
                self.detections_saved,
                self.mode,
                detection.box,
                detection.changed_pixels,
                detection.peak_difference,
                crop,
            )
        )
        return None

    def teardown(self):
        """Log a summary; the framework then closes the stream and camera."""
        self.log(
            "saved {} detections, {} day/night switches".format(
                self.detections_saved, self.mode_switches
            )
        )

    # ------------------------------------------------------------------
    # Day and night
    # ------------------------------------------------------------------

    def _check_light(self):
        """Read the light level and switch day/night if the monitor says so."""
        metadata = self.cam.get_metadata()
        lux = metadata.get("Lux")
        if lux is None and not self._warned_no_lux:
            self._warned_no_lux = True
            self.log(
                "camera reports no Lux; staying in day mode except on "
                "over-exposure (use --mode night to force night)"
            )
        brightness = self.detector.brightness
        first = self.monitor.mode is None
        new_mode = self.monitor.update(lux=lux, brightness=brightness)
        self._log_light(lux, brightness, metadata)
        if new_mode is not None:
            reason = "lux {}".format(_fmt(lux))
            if new_mode == DAY and not (
                lux is not None and lux > self.settings.day_above_lux
            ):
                reason = "night frames over-exposed (brightness {})".format(
                    _fmt(brightness)
                )
            self._apply_mode(new_mode, reason=reason, count=not first)
        self._last_light_check = time.monotonic()

    def _apply_mode(self, mode, reason, count=False):
        """Set the camera, detector threshold and background for a mode.

        Waits until the camera's frames carry the new settings (up to about
        half a minute for a 4 s night exposure); if they don't in time, the
        framework logs it and the app carries on.

        Args:
            mode: ``"day"`` or ``"night"``.
            reason: Why, for the log.
            count: True to count this as a switch in :attr:`mode_switches`.
        """
        s = self.settings
        self.log("{} mode: {}".format(mode, reason))
        if mode == NIGHT:
            settled = self.cam.set_exposure(
                s.night_exposure_us, gain=s.night_gain, awb_gains=s.night_awb
            )
            self.detector.pixel_threshold = s.night_pixel_threshold
        else:
            settled = self.cam.set_auto_exposure()
            self.detector.pixel_threshold = s.pixel_threshold
        if not settled:
            self.log("camera had not settled; continuing anyway")
        self.detector.reset()
        self._last_save = None
        self.mode = mode
        if count:
            self.mode_switches += 1

    def _log_light(self, lux, brightness, metadata):
        """Log the light level while a switch is being voted on, else hourly.

        Args:
            lux: The ``Lux`` reading, or None.
            brightness: Mean frame brightness 0-255, or None.
            metadata: The frame metadata the reading came from.
        """
        now = time.monotonic()
        voting = self.monitor.votes > 0
        due = (
            self._last_status_log is None
            or now - self._last_status_log >= STATUS_LOG_INTERVAL
        )
        if not (voting or due):
            return
        self._last_status_log = now
        self.log(
            "light: lux {}, brightness {}, exposure {} us, gain {}{}".format(
                _fmt(lux),
                _fmt(brightness),
                metadata.get("ExposureTime"),
                _fmt(metadata.get("AnalogueGain")),
                (
                    " ({} vote {}/{})".format(
                        DAY if self.monitor.mode == NIGHT else NIGHT,
                        self.monitor.votes,
                        self.monitor.confirm,
                    )
                    if voting
                    else ""
                ),
            )
        )


def _fmt(value):
    """Format a number for the log with one decimal, or ``?`` if None."""
    return "?" if value is None else "{:.1f}".format(value)
