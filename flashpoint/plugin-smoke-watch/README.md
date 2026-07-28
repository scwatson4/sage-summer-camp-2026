# plugin-smoke-watch — Tier-3 holdover patrol as an edge plugin

The 72 h holdover smoke-watch packaged for Sage nodes: visit lightning-strike
sectors highest-risk-first, dwell for a before/after frame pair, flag sectors
whose horizon band changed, upload RAW evidence for flagged sectors only.

**Honest scope:** patrol orchestration + deterministic change-detection
placeholder head; SmokeyNet horizon-band tiles are the planned upgrade; no
real PTZ driver yet. YOLO-COCO scored 0 relevant detections on sky cams in
the live H03E exercise (see `../agent/README.md`), so the head here is
per-tile mean-luma abs diff over the dwell pair (horizon-band crop, 5x9
SmokeyNet-convention grid). The RTSP gateway records commanded pan/tilt as
metadata only — it cannot aim a physical camera.

Publishes:

| name | value | meta |
|---|---|---|
| `fire.smokewatch.sectors_visited` | count | head |
| `fire.smokewatch.flagged` | count | head |
| `fire.smokewatch.sector.flagged` | detections (tiles) per flagged sector | bearing_deg, pan_deg, range_km |
| `upload` (frame pair, flagged only) | — | frame=before/after + sector meta |

## Offline demo (zero credentials / network / camera)

Bare `python3 main.py` patrols the bundled W097 panorama (downscaled copy in
`sim-assets/`; the full-res original lives in `../agent/sim-panoramas/` —
regenerate with `make_sim_assets.py`). Six 60° sectors, one of which is the
REAL Halemaumau plume with the archive's burned-in boxes scrubbed.

```bash
PYWAGGLE_LOG_DIR=test-run python3 main.py
cat test-run/data.ndjson         # published values land here
# -> sectors_visited=6, flagged=0 (a static pano never changes during a dwell)

PYWAGGLE_LOG_DIR=test-run python3 main.py --sim-inject-plume
# TEST HOOK, sim only: brightens a blob in the AFTER frame at the plume
# sector (pan 150) -> flagged=1, sector.flagged value=5 tiles at
# bearing 150.0, frame pair in test-run/uploads/
```

## Sector input

- default: bundled demo sectors derived from `sim-assets/sectors.json`
- `--sectors-file f.json` — `[{bearing_deg, range_km, age_h, risk}]`
- `--strikes-file f.json --lat 41.88 --lon -87.63` —
  `[{lat, lon, time_epoch[, risk]}]` converted via
  `strike_sectors.sectors_for_node` (72 h age gate, 30 km range gate)

## Build & run on H03E (from your laptop, per the runbook)

```bash
ssh waggle-dev-node-H03E
tmux new -s smokewatch
git clone -b main https://github.com/scwatson4/sage-summer-camp-2026 && \
  cd sage-summer-camp-2026/flashpoint/plugin-smoke-watch
./sync_vendor.sh                    # vendor agent code into the context
sudo pluginctl build .              # needs the local registry running —
                                    # see classroom-notes.md if port 5000 refuses
sudo pluginctl run --name smokewatch \
  localhost:5000/local/plugin-smoke-watch
sudo pluginctl run --name smokewatch \
  localhost:5000/local/plugin-smoke-watch -- --sim-inject-plume
```

Real camera (frames only — the camera stays wherever it points; commanded
pan/tilt land in metadata, and dwell defaults must be raised from the
sim-short values):

```bash
sudo pluginctl run --name smokewatch \
  localhost:5000/local/plugin-smoke-watch -- \
  --rtsp-url rtsp://user:pass@CAM/stream \
  --dwell-s 180 --frame-pair-gap-s 120
```

Camera credentials come from node admins via the URL/env — never committed.
`--tile-thresh 12` is calibrated to nothing (sim JPEGs are noiseless);
expect to raise it on a real sensor before trusting flags.

`vendored/evidence.py` is bundled but not yet imported: it's the W097-rule
evidence renderer (raw untouched, overlays on derived copies) queued for the
flagged-sector card assembler; shipping it keeps the vendor sync one script.

ECR submission (after pushing to GitHub — **ECR pins the branch head, so
push first**): run `./sync_vendor.sh` and `python3 make_sim_assets.py`,
commit the vendored copy + sim assets, then POST sage.yaml per
classroom-notes.md "ECR submission (API route)".

## H03E gotchas (inherited from plugin-thunder, validated 2026-07-27)

- `pluginctl build` names the image after the DIRECTORY, not sage.yaml:
  the local image is `localhost:5000/local/plugin-smoke-watch`
  (not `.../flashpoint-smoke-watch`).
- Run via `localhost:5000/...`, not `10.31.81.1:5000/...`.
- Dev blades have no camera; the no-args sim demo is the container smoke
  test and needs nothing attached.
