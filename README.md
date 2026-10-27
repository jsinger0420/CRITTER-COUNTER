# Critter Counter

Watch a harvested field with a Raspberry Pi camera and save images of animals
(mainly deer) that cross it. The field unit is a Pi Zero 2 W on solar power: it
takes a still every few seconds, compares a downscaled copy with a background
model, and saves the full frame plus a close-up whenever something changes.
A classifier on a bigger machine at the house will later sort real animals from
false alarms.

Built on [rpi-app-framework](https://github.com/jsinger0420/RPI-APP-FRAMEWORK)
0.2.0 (`RPIApp`, `CameraDeviceManager`, `MJPEGStreamingManager`). Design notes:
[docs/DESIGN.md](docs/DESIGN.md).

## Status

First version, daytime only:

- [x] Capture every `--interval` seconds, change detection on a downscaled
      grayscale copy (numpy only), noise filtering, whole-scene-change reset
- [x] Save `detections/YYYY-MM-DD/HHMMSS_full.jpg` and `_crop.jpg`
- [x] Live view at `http://<pi>:8000/` for aiming and focusing
- [ ] Night mode (long exposure, high gain): needs a framework change, see below
- [ ] Day/night switching, scheduled sleep, sending candidates to the house

## Run on the Pi (Zero 2 W, Bookworm)

```bash
sudo apt install python3-picamera2 ffmpeg git
python3 -m venv --system-site-packages ~/venv
source ~/venv/bin/activate
git clone <this repo> critter-counter && cd critter-counter
pip install -e .            # pulls rpi-app-framework 0.2.0 from GitHub main
critter-counter             # or: python -m critter_counter
```

Open `http://<pi>:8000/` to aim and focus. Stop with Ctrl-C; the camera and
stream are closed and the log (in `LOGFILES/CritterCounter/`) ends with "stopped".

Useful options (`critter-counter --help` lists all):

| Option | Default | Meaning |
|---|---|---|
| `--interval` | 3.0 | Seconds between captures |
| `--resolution` | 1640x1232 | Camera size (IMX219 full view, binned) |
| `--scale` | 4 | Detector downscale block size |
| `--pixel-threshold` | 25 | Brightness change (0-255) that counts |
| `--min-changed-pixels` | 4 | Changed downscaled pixels for a detection |
| `--cooldown` | 10 | Minimum seconds between saved detections |
| `--no-stream` | | Turn off the live view (saves CPU and power) |

## Develop on Windows

```powershell
cd C:\Users\Jsing\dev\CRITTER-COUNTER
py -m venv .venv
.venv\Scripts\activate
# Use your local framework checkout so framework fixes are picked up at once:
pip install -e ..\RPI-APP-FRAMEWORK
pip install -e ".[dev]"
pytest
ruff check . ; black --check .
```

Tests use the real framework with a fake `picamera2`, so no camera is needed.

## Framework changes needed

`CameraDeviceManager` (0.2.0) has no exposure or gain controls, and its
continuous video configuration caps exposure at the frame period. Night mode
needs multi-second exposures, so rather than reaching into `cam.picam2` from
the app, this is proposed for the framework (a `fix/` branch there):

- `set_exposure(exposure_us=None, gain=None)`: manual exposure time and
  analogue gain (also sets `FrameDurationLimits` so long exposures are allowed);
  `None` returns to auto.
- `set_auto_exposure()` (or `set_exposure()` with no arguments): back to auto
  exposure and auto white balance.
- Optionally `awb_gains=(r, b)` to fix white balance at night.
