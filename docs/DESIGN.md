# Critter Counter — Design Decisions

Summary of the planning conversation (October 2026). Kept in step with the
"design-decisions" doc in the Claude project.

## Goal

Watch a large outdoor field (harvested farmland) and detect animals, mainly deer,
at distances up to about 1/4 mile (~400 m), day and night. Save images of detections.

## Detection approach

- **Image comparison, not PIR motion sensors.** PIR sensors only reach 10–30 ft.
  Detect change by comparing frames against a background model (e.g. OpenCV
  background subtraction or frame differencing on downscaled images).
- **Stills, not video.** Deer cross slowly, so one frame every few seconds is enough.
  This allows long exposures at night and keeps power low.
- **On a detection, save** the full-resolution frame plus a cropped close-up of the
  changed region.
- **Later (two-tier design):** the field unit does only cheap change detection; a Pi 5
  or PC at the house receives candidate images and runs an animal classifier to
  reject false alarms (grass, branches, bugs).

## Camera

- **Rejected: consumer WiFi/solar security cameras.** Most are app/cloud-only, and
  battery models sleep between events, so they can't give a continuous stream.
- **Rejected for now: PoE security cameras.** 5–14 W continuously, too much for solar.
- **Prototype camera: Arducam 8MP IMX219 NoIR** (already owned), on the Pi's camera
  ribbon cable.
  - NoIR helps at night; pinkish daytime color doesn't matter.
  - Stock lens (~62°) puts only ~10 px on a deer at 400 m (~5 px binned at night).
    Plan: a 12–16 mm M12 telephoto lens (f/1.6–2.0, no IR-cut) for ~40–55 px per deer.
- **Possible upgrade: Raspberry Pi HQ Camera (IMX477)** with a C/CS-mount telephoto
  lens, if IMX219 night images are too noisy.

## Night imaging

- No infrared illuminators (can't reach the field; they light up bugs/rain). Disable
  any IR LEDs.
- Moonlight/starlight: harvested fields are pale, so deer show as dark shapes.
- Long exposures (seconds) and higher gain at night; auto exposure by day. The app
  needs a day/night capture mode.
- Night test command:
  `rpicam-still --immediate --shutter 4000000 --gain 8 --awbgains 1,1 -o night_test.jpg`

## Power

- **No mains power: battery + solar.**
- Solar panel → MPPT charge controller → 12 V LiFePO4 (low-temperature charge
  protection) → efficient 12 V→5 V buck → Pi + camera.
- **Field board: Pi Zero 2 W** (~1–1.5 W). Budget 40–50 Wh/day → ~50 W panel,
  12 V 20 Ah LiFePO4 (3–4 days reserve). A Pi 5 needs roughly 3× that.
- Consider scheduled sleep/wake (e.g. Witty Pi) to run only during hours of interest.
- Keep processing light on the Zero: downscaled comparisons, no on-device classifier,
  watch memory (512 MB).

## Enclosure (user-built)

- Outdoor utility box with a clear cover; lens close to the cover with a black foam
  ring; black out the rest of the cover's inside.
- Turn off or cover the Pi's status LEDs (they reflect into long exposures).
- Test sharpness with cover on vs. off; if soft, seal a glass window over a hole.
- Shade/hood the box, add desiccant and a small vent.

## Data link to the house — open item

Depends on distance and line of sight: WiFi with outdoor antenna, point-to-point
WiFi bridge (+3–6 W), or cellular modem (~2 W + data plan).

## Implementation notes (code)

- `detector.py`: block-average downscale to grayscale (numpy only, no OpenCV),
  running-average background, changed pixels must have ≥ 2 changed neighbors,
  > 25 % of the scene changing at once resets the background (clouds, exposure).
- `storage.py`: saves the analyzed frame (not a new capture) and a padded close-up.
- Default resolution 1640x1232: full field of view, 2x2 binned. Full 3280x2464 in
  the framework's always-on video mode needs too much memory on a Zero 2 W; full-res
  stills would need a mode switch in the framework.
- Day/night (`daynight.py`, `app.py`): auto exposure by day; at night
  `set_exposure(4 s, gain 8, awb 1/1)` from the framework's exposure API.
  Switching uses the camera's `Lux` estimate with hysteresis (night below 10,
  day above 40, 3 readings in a row, one reading a minute); at night an
  over-exposed frame (mean > 200) also votes for day. Thresholds are starting
  guesses to tune on site. Each switch waits for the new settings, relearns
  the background and uses a higher detection threshold at night (35 vs 25).
- Saved images are tagged `_day_` or `_night_` for the later classifier.
