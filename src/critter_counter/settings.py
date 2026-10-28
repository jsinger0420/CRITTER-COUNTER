"""Settings for the Critter Counter app, with command-line overrides.

Typical usage:

    settings = Settings.from_args(["--interval", "5", "--no-stream"])
"""

import argparse
from dataclasses import dataclass, fields

MODES = ("auto", "day", "night")


@dataclass
class Settings:
    """Everything the app can be tuned with.

    Attributes:
        resolution (tuple): Camera ``(width, height)`` in pixels. 1640x1232 is
            the IMX219's full field of view, 2x2 binned; full resolution
            (3280x2464) is too much memory for a Zero 2 W in the framework's
            continuous video mode.
        interval (float): Seconds between captures.
        detections_dir (str): Folder for detection images.
        scale (int): Detector downscale block size in pixels.
        pixel_threshold (float): Brightness change (0-255) that counts.
        min_changed_pixels (int): Changed downscaled pixels for a detection.
        max_changed_fraction (float): Above this, the whole scene changed.
        learning_rate (float): Background blend factor per frame (0-1).
        min_neighbors (int): Changed neighbors a pixel needs to count (0-8).
        cooldown (float): Minimum seconds between saved detections.
        crop_pad (float): Close-up margin as a fraction of the box size.
        crop_min_size (int): Smallest close-up size in pixels.
        jpeg_quality (int): JPEG quality for saved images, 1-95.
        stream_port (int or None): Port for the live view; None turns it off.
        stream_fps (float): Live view frames per second (0.5-30).
        mode (str): ``"auto"`` switches between day and night from the
            light level; ``"day"`` or ``"night"`` stays in that mode.
        night_exposure_us (int): Night exposure time in microseconds
            (IMX219 maximum about 11.7 s).
        night_gain (float): Night analogue gain (IMX219: 1.0 to about 10.7).
        night_awb (tuple or None): Fixed ``(red, blue)`` white-balance gains
            at night; None keeps auto white balance.
        night_pixel_threshold (float): ``pixel_threshold`` at night, higher
            because long, high-gain exposures are noisier.
        night_below_lux (float): Switch to night when the camera's ``Lux``
            estimate stays below this.
        day_above_lux (float): Switch back to day when it stays above this.
        light_confirm (int): Light readings in a row needed to switch.
        light_check_interval (float): Seconds between light readings in
            auto mode.
        overexposed_level (float): At night, a mean frame brightness (0-255)
            at or above this means dawn: switch to day.
    """

    resolution: tuple = (1640, 1232)
    interval: float = 3.0
    detections_dir: str = "detections"
    scale: int = 4
    pixel_threshold: float = 25.0
    min_changed_pixels: int = 4
    max_changed_fraction: float = 0.25
    learning_rate: float = 0.05
    min_neighbors: int = 2
    cooldown: float = 10.0
    crop_pad: float = 0.5
    crop_min_size: int = 160
    jpeg_quality: int = 90
    stream_port: int = 8000
    stream_fps: float = 2.0
    mode: str = "auto"
    night_exposure_us: int = 4_000_000
    night_gain: float = 8.0
    night_awb: tuple = (1.0, 1.0)
    night_pixel_threshold: float = 35.0
    night_below_lux: float = 10.0
    day_above_lux: float = 40.0
    light_confirm: int = 3
    light_check_interval: float = 60.0
    overexposed_level: float = 200.0

    def __post_init__(self):
        """Check the settings that are not checked where they are used.

        Raises:
            ValueError: If a setting is out of range.
        """
        if self.mode not in MODES:
            raise ValueError("mode must be one of {}".format(", ".join(MODES)))
        if self.interval <= 0:
            raise ValueError("interval must be > 0 seconds")
        if self.light_check_interval < 0:
            raise ValueError("light_check_interval must be >= 0 seconds")
        if self.night_exposure_us <= 0:
            raise ValueError("night_exposure_us must be > 0 microseconds")
        if self.night_gain <= 0:
            raise ValueError("night_gain must be > 0")

    @classmethod
    def from_args(cls, argv=None):
        """Build settings from command-line arguments.

        Every field is an option (``--pixel-threshold 30``); ``--resolution``
        takes ``WIDTHxHEIGHT``, ``--night-awb`` takes ``RED,BLUE`` or
        ``auto``, and ``--no-stream`` turns the live view off.

        Args:
            argv: Argument list without the program name; defaults to
                ``sys.argv[1:]``.

        Returns:
            Settings: Defaults with the given options applied.
        """
        defaults = cls()
        parser = argparse.ArgumentParser(
            prog="critter-counter",
            description="Watch a field and save images of animals that cross it.",
        )
        for f in fields(cls):
            if f.name in ("resolution", "stream_port", "mode", "night_awb"):
                continue
            value = getattr(defaults, f.name)
            parser.add_argument(
                "--" + f.name.replace("_", "-"),
                type=type(value),
                default=value,
                help="default: %(default)s",
            )
        parser.add_argument(
            "--resolution",
            type=_parse_resolution,
            default=defaults.resolution,
            help="camera WIDTHxHEIGHT (default: {}x{})".format(*defaults.resolution),
        )
        parser.add_argument(
            "--mode",
            choices=MODES,
            default=defaults.mode,
            help="auto: switch day/night from the light level (default: %(default)s)",
        )
        parser.add_argument(
            "--night-awb",
            type=_parse_awb,
            default=defaults.night_awb,
            help="night white balance RED,BLUE or 'auto' (default: {:g},{:g})".format(
                *defaults.night_awb
            ),
        )
        parser.add_argument(
            "--stream-port",
            type=int,
            default=defaults.stream_port,
            help="live view port (default: %(default)s)",
        )
        parser.add_argument(
            "--no-stream",
            action="store_true",
            help="turn off the live view (saves CPU and power)",
        )
        args = parser.parse_args(argv)
        values = {f.name: getattr(args, f.name) for f in fields(cls)}
        if args.no_stream:
            values["stream_port"] = None
        return cls(**values)


def _parse_resolution(text):
    """Parse ``WIDTHxHEIGHT`` for argparse.

    Args:
        text: e.g. ``"1640x1232"``.

    Returns:
        tuple: ``(width, height)``.

    Raises:
        argparse.ArgumentTypeError: If the text is not two positive integers.
    """
    try:
        width, height = (int(v) for v in text.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError("use WIDTHxHEIGHT, e.g. 1640x1232") from None
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("width and height must be positive")
    return (width, height)


def _parse_awb(text):
    """Parse ``RED,BLUE`` white-balance gains (or ``auto``) for argparse.

    Args:
        text: e.g. ``"1,1"``, ``"1.5,1.2"`` or ``"auto"``.

    Returns:
        tuple or None: ``(red, blue)``, or None for auto white balance.

    Raises:
        argparse.ArgumentTypeError: If the text is not two positive numbers.
    """
    if text.strip().lower() == "auto":
        return None
    try:
        red, blue = (float(v) for v in text.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError("use RED,BLUE (e.g. 1,1) or auto") from None
    if red <= 0 or blue <= 0:
        raise argparse.ArgumentTypeError("white-balance gains must be positive")
    return (red, blue)
