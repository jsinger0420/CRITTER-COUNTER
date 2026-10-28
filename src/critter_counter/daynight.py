"""Decide when to switch between day and night capture.

The decision uses the camera's own scene-brightness estimate (``Lux`` in the
frame metadata, which libcamera computes from the image, exposure time and
gain, so it stays meaningful under a fixed night exposure). Two thresholds
with a gap between them (hysteresis) and several readings in a row stop the
mode flapping at dusk or when a cloud passes.

At night there is a second way back to day: if the fixed night exposure
over-exposes the frame (dawn), switch even if ``Lux`` is missing or low.

Typical usage:

    monitor = DayNightMonitor(night_below_lux=10, day_above_lux=40)
    new_mode = monitor.update(lux=metadata.get("Lux"), brightness=mean_gray)
    if new_mode:
        ...  # apply DAY or NIGHT settings to the camera
"""

DAY = "day"
NIGHT = "night"


class DayNightMonitor:
    """Day/night state with hysteresis and a confirmation count.

    Attributes:
        night_below_lux (float): Switch to night when ``Lux`` is below this.
        day_above_lux (float): Switch back to day when ``Lux`` is above this.
        confirm (int): Readings in a row needed before switching.
        overexposed_level (float): At night, a mean frame brightness (0-255)
            at or above this also counts as a vote for day.
        mode (str or None): ``"day"`` or ``"night"``; None until the first
            :meth:`update`.
        votes (int): Readings in a row so far that favour switching.
    """

    def __init__(
        self,
        night_below_lux=10.0,
        day_above_lux=40.0,
        confirm=3,
        overexposed_level=200.0,
    ):
        """Create a monitor with no mode yet.

        Args:
            night_below_lux: Lux threshold for night, >= 0.
            day_above_lux: Lux threshold for day; must be above
                ``night_below_lux``.
            confirm: Readings in a row (>= 1) before a switch.
            overexposed_level: Mean brightness 0-255 that means a night
                frame is over-exposed.

        Raises:
            ValueError: If an argument is out of range.
        """
        if night_below_lux < 0:
            raise ValueError("night_below_lux must be >= 0")
        if day_above_lux <= night_below_lux:
            raise ValueError("day_above_lux must be greater than night_below_lux")
        if isinstance(confirm, bool) or not isinstance(confirm, int) or confirm < 1:
            raise ValueError("confirm must be an int >= 1")
        if not 0 < overexposed_level <= 255:
            raise ValueError("overexposed_level must be > 0 and <= 255")
        self.night_below_lux = float(night_below_lux)
        self.day_above_lux = float(day_above_lux)
        self.confirm = confirm
        self.overexposed_level = float(overexposed_level)
        self.mode = None
        self.votes = 0

    def update(self, lux=None, brightness=None):
        """Take one reading and say whether to switch.

        The first reading decides the starting mode at once (no
        confirmation), so an app started after dark goes straight to night.

        Args:
            lux: Scene brightness estimate from the frame metadata, or None
                if the sensor does not report it.
            brightness: Mean brightness (0-255) of a recent frame, or None.
                Only used at night, to detect over-exposure.

        Returns:
            str or None: The new mode (``"day"`` or ``"night"``) when the
            camera should switch, else None.
        """
        if self.mode is None:
            self.mode = NIGHT if lux is not None and lux < self.night_below_lux else DAY
            self.votes = 0
            return self.mode
        if self.mode == DAY:
            wants_switch = lux is not None and lux < self.night_below_lux
        else:
            wants_switch = (lux is not None and lux > self.day_above_lux) or (
                brightness is not None and brightness >= self.overexposed_level
            )
        if not wants_switch:
            self.votes = 0
            return None
        self.votes += 1
        if self.votes < self.confirm:
            return None
        self.mode = NIGHT if self.mode == DAY else DAY
        self.votes = 0
        return self.mode
