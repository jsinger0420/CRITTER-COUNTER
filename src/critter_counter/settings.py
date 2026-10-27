"""Settings for the Critter Counter app, with command-line overrides.

Typical usage:

    settings = Settings.from_args(["--interval", "5", "--no-stream"])
"""

import argparse
from dataclasses import dataclass, fields


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

    @classmethod
    def from_args(cls, argv=None):
        """Build settings from command-line arguments.

        Every field is an option (``--pixel-threshold 30``); ``--resolution``
        takes ``WIDTHxHEIGHT`` and ``--no-stream`` turns the live view off.

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
            if f.name in ("resolution", "stream_port"):
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
