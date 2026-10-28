# Critter Counter

Watch a harvested field with a Raspberry Pi camera and save images of animals
(mainly deer) that cross it. The field unit is a Pi Zero 2 W on solar power: it
takes a still every few seconds, compares a downscaled copy with a background
model, and saves the full frame plus a close-up whenever something changes.
A classifier on a bigger machine at the house will later sort real animals from
false alarms.

Built on [rpi-app-framework](https://github.com/jsinger0420/RPI-APP-FRAMEWORK)
0.2.0 from GitHub `main` (`RPIApp`, `CameraDeviceManager` with exposure control,
`MJPEGStreamingManager`). Design notes:
[docs/DESIGN.md](docs/DESIGN.md).

## Status

Day and night capture, tested on a PC with a simulated camera; not yet on the Pi:

- [x] Capture every `--interval` seconds, change detection on a downscaled
      grayscale copy (numpy only), noise filtering, whole-scene-change reset
- [x] Save `detections/YYYY-MM-DD/HHMMSS_day_full.jpg` and `_day_crop.jpg`
      (`_night_` after dark)
- [x] Live view at `http://<pi>:8000/` for aiming and focusing
- [x] Night mode: fixed long exposure and high gain, automatic day/night
      switching from the camera's light reading
- [ ] Tune the lux thresholds and night exposure on site
- [ ] Scheduled sleep, sending candidates to the house

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
| `--mode` | auto | `auto` switches day/night; `day` or `night` stays put |
| `--night-exposure-us` | 4000000 | Night exposure (µs); IMX219 max ~11.7 s |
| `--night-gain` | 8.0 | Night analogue gain (IMX219 1.0–~10.7) |
| `--night-awb` | 1,1 | Night white balance `RED,BLUE`, or `auto` |
| `--night-pixel-threshold` | 35 | Detection threshold at night (noisier frames) |
| `--night-below-lux` | 10 | Go to night when lux stays below this |
| `--day-above-lux` | 40 | Back to day when lux stays above this |
| `--light-confirm` | 3 | Readings in a row needed to switch |
| `--light-check-interval` | 60 | Seconds between light readings |
| `--overexposed-level` | 200 | At night, frame brightness (0–255) that means dawn |

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

## Day and night

By day the camera runs on auto exposure. At night it switches to a fixed
exposure (`--night-exposure-us`, `--night-gain`, `--night-awb`) through
`CameraDeviceManager.set_exposure()`.

- **When to switch.** In `--mode auto` the app reads the camera's `Lux`
  estimate every `--light-check-interval` seconds. It goes to night after
  `--light-confirm` readings in a row below `--night-below-lux`, and back to
  day after as many above `--day-above-lux`. The gap between the two stops
  flapping at dusk. At night a frame brighter than `--overexposed-level` also
  counts as a vote for day, in case `Lux` is unreliable under the fixed
  exposure. The first reading at startup decides at once.
- **What a switch does.** The camera changes settings and the call waits until
  frames show them (about 30 s for a 4 s exposure). The background is then
  relearned, and the detection threshold changes to `--night-pixel-threshold`
  or `--pixel-threshold`.
- **At night** each frame takes as long as the exposure, so captures run every
  ~4 s whatever `--interval` says, and the live view drops to ~0.25 fps.

**Tuning on site.** The log shows a light line every hour and on every
reading that votes for a switch, e.g.
`light: lux 6.0, brightness 149.5, exposure 10000 us, gain 1.0 (night vote 2/3)`.
Watch one dusk and one dawn and set the two lux thresholds from what you see.
To try night settings in the dark without waiting for a switch, run
`critter-counter --mode night`. Compare against
`rpicam-still --immediate --shutter 4000000 --gain 8 --awbgains 1,1 -o night_test.jpg`.
