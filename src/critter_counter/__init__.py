"""Critter Counter: detect animals crossing a field with a Raspberry Pi camera.

The field unit (a Pi Zero 2 W) takes a still every few seconds, compares a
downscaled copy with a background model, and saves the full frame plus a
close-up whenever something changes, by day on auto exposure and at night with
a fixed long exposure. Built on rpi-app-framework.
"""

__version__ = "0.2.0"
