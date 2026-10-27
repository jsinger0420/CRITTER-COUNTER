"""Change detection against a running-average background.

Frames are reduced to small grayscale images (block averages, which also cut
sensor noise), compared with a background model, and filtered so isolated
noisy pixels are ignored. Only numpy is needed, so this runs comfortably on a
Pi Zero 2 W and in tests on a PC.

Typical usage:

    detector = ChangeDetector(scale=4, pixel_threshold=25)
    detection = detector.update(frame)       # None on the first frame
    if detection:
        print(detection.box)                 # (x0, y0, x1, y1), full-res pixels
"""

from dataclasses import dataclass

import numpy as np

# ITU-R BT.601 luma weights in BGR order (frames from the camera are BGR).
_LUMA_BGR = np.array([0.114, 0.587, 0.299], dtype=np.float32)


@dataclass(frozen=True)
class Detection:
    """A region of the frame that differs from the background.

    Attributes:
        box (tuple): ``(x0, y0, x1, y1)`` in full-resolution pixels; ``x1``
            and ``y1`` are exclusive.
        changed_pixels (int): Changed pixels in the downscaled image, after
            noise filtering.
        changed_fraction (float): ``changed_pixels`` divided by the number of
            downscaled pixels (0-1).
        peak_difference (float): Largest brightness difference from the
            background among the changed pixels (0-255).
    """

    box: tuple
    changed_pixels: int
    changed_fraction: float
    peak_difference: float


def downscale_gray(frame, scale):
    """Convert a frame to a small grayscale image by averaging blocks.

    Args:
        frame: ``height x width x 3`` BGR array (or ``height x width``
            grayscale), any numeric dtype.
        scale: Block size in pixels; the result is ``scale`` times smaller in
            each direction. Rows and columns that do not fill a whole block
            are dropped.

    Returns:
        numpy.ndarray: ``float32`` array of ``height // scale`` by
        ``width // scale`` brightness values (0-255 for 8-bit input).

    Raises:
        ValueError: If the frame is smaller than one block or has an
            unsupported shape.
    """
    if frame.ndim not in (2, 3) or (frame.ndim == 3 and frame.shape[2] < 3):
        raise ValueError("frame must be height x width x 3 (BGR) or height x width")
    h, w = frame.shape[0] // scale, frame.shape[1] // scale
    if h == 0 or w == 0:
        raise ValueError("frame is smaller than one {0}x{0} block".format(scale))
    if frame.ndim == 3:
        blocks = frame[: h * scale, : w * scale, :3].reshape(h, scale, w, scale, 3)
        return blocks.mean(axis=(1, 3), dtype=np.float32) @ _LUMA_BGR
    blocks = frame[: h * scale, : w * scale].reshape(h, scale, w, scale)
    return blocks.mean(axis=(1, 3), dtype=np.float32)


def neighbor_count(mask):
    """Count the set neighbors of every pixel in a boolean mask.

    Args:
        mask: 2-D boolean array.

    Returns:
        numpy.ndarray: ``uint8`` array of the same shape; each value is how
        many of the 8 surrounding pixels are set (0-8).
    """
    h, w = mask.shape
    padded = np.pad(mask.astype(np.uint8), 1)
    count = np.zeros((h, w), dtype=np.uint8)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            if dy == 1 and dx == 1:
                continue
            count += padded[dy : dy + h, dx : dx + w]
    return count


class ChangeDetector:
    """Find what changed between each frame and a learned background.

    The first frame becomes the background. Each later frame is compared with
    it and then blended in slowly (``learning_rate``), so gradual changes such
    as moving shadows are absorbed while an animal crossing is not.

    When most of the scene changes at once (clouds, auto exposure, camera
    bumped), that is not an animal: the background is replaced by the new
    frame and :attr:`scene_changed` is set for that update.

    Attributes:
        scale (int): Downscale block size in pixels.
        pixel_threshold (float): Brightness difference (0-255) that counts a
            downscaled pixel as changed.
        min_changed_pixels (int): Changed downscaled pixels needed to report
            a detection.
        max_changed_fraction (float): Above this fraction of changed pixels
            the whole scene is treated as changed (0-1).
        learning_rate (float): How fast the background follows the scene per
            frame (0-1).
        min_neighbors (int): A changed pixel is kept only if at least this
            many of its 8 neighbors also changed (0 keeps every pixel).
        scene_changed (bool): True if the last :meth:`update` reset the
            background because most of the scene changed.
    """

    def __init__(
        self,
        scale=4,
        pixel_threshold=25.0,
        min_changed_pixels=4,
        max_changed_fraction=0.25,
        learning_rate=0.05,
        min_neighbors=2,
    ):
        """Create a detector with no background yet.

        Args:
            scale: Downscale block size in pixels (>= 1).
            pixel_threshold: Brightness difference that marks a pixel as
                changed, 0-255.
            min_changed_pixels: Changed downscaled pixels needed for a
                detection (>= 1).
            max_changed_fraction: Fraction of changed pixels (0-1, exclusive
                of 0) above which the background is reset instead.
            learning_rate: Background blend factor per frame, 0-1 (0 never
                learns, 1 replaces the background every frame).
            min_neighbors: Neighbors (0-8) a changed pixel needs to be kept.

        Raises:
            ValueError: If any argument is out of range.
        """
        if isinstance(scale, bool) or not isinstance(scale, int) or scale < 1:
            raise ValueError("scale must be an int >= 1")
        if not 0 <= pixel_threshold <= 255:
            raise ValueError("pixel_threshold must be from 0 to 255")
        if (
            isinstance(min_changed_pixels, bool)
            or not isinstance(min_changed_pixels, int)
            or min_changed_pixels < 1
        ):
            raise ValueError("min_changed_pixels must be an int >= 1")
        if not 0 < max_changed_fraction <= 1:
            raise ValueError("max_changed_fraction must be > 0 and <= 1")
        if not 0 <= learning_rate <= 1:
            raise ValueError("learning_rate must be from 0 to 1")
        if not 0 <= min_neighbors <= 8:
            raise ValueError("min_neighbors must be from 0 to 8")
        self.scale = scale
        self.pixel_threshold = float(pixel_threshold)
        self.min_changed_pixels = min_changed_pixels
        self.max_changed_fraction = float(max_changed_fraction)
        self.learning_rate = float(learning_rate)
        self.min_neighbors = min_neighbors
        self.scene_changed = False
        self._background = None

    @property
    def ready(self):
        """bool: True once a background has been learned."""
        return self._background is not None

    def reset(self):
        """Forget the background; the next frame becomes the new one."""
        self._background = None
        self.scene_changed = False

    def update(self, frame):
        """Compare a frame with the background, then learn from it.

        Args:
            frame: ``height x width x 3`` BGR array, as returned by
                ``CameraDeviceManager.capture_frame()``.

        Returns:
            Detection or None: The changed region, or None if nothing
            significant changed (always None for the first frame, a frame of
            a new size, or a whole-scene change).

        Raises:
            ValueError: If the frame has an unsupported shape.
        """
        self.scene_changed = False
        small = downscale_gray(frame, self.scale)
        if self._background is None or self._background.shape != small.shape:
            self._background = small
            return None

        diff = np.abs(small - self._background)
        mask = diff > self.pixel_threshold
        if self.min_neighbors:
            mask &= neighbor_count(mask) >= self.min_neighbors
        changed = int(np.count_nonzero(mask))
        fraction = changed / mask.size

        if fraction > self.max_changed_fraction:
            self._background = small
            self.scene_changed = True
            return None
        self._background += self.learning_rate * (small - self._background)

        if changed < self.min_changed_pixels:
            return None
        ys, xs = np.nonzero(mask)
        s = self.scale
        height, width = frame.shape[:2]
        box = (
            int(xs.min()) * s,
            int(ys.min()) * s,
            min((int(xs.max()) + 1) * s, width),
            min((int(ys.max()) + 1) * s, height),
        )
        return Detection(
            box=box,
            changed_pixels=changed,
            changed_fraction=fraction,
            peak_difference=float(diff[mask].max()),
        )
