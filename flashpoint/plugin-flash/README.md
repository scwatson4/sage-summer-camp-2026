# plugin-flash — M2 edge plugin

The D1-2 flash detector packaged for Sage nodes: the fixed sky camera as a
photometer. Lightning lights the whole sky, so a flash is a scene-wide
luminance spike — a ~±0.5 s time anchor at ANY frame cadence (what sparse
cadence costs is catch probability, and events say so via `sparse_cadence`).
Standalone candidates only (M1 contract); event metadata published, frames
stay on-node unless a candidate fires. Coarse fisheye azimuth
(`azimuth_sector`/`azimuth_deg`) rides along for M3 flash↔thunder pairing.

Published: `lightning.flash.candidate` (jump), `lightning.flash.luma`
(spike-frame luminance), `lightning.flash.frames_checked` (per batch).

## Build & run on H03E (from your laptop, per the runbook)

```bash
ssh waggle-dev-node-H03E
tmux new -s m2                      # or: tmux attach -t m2
git clone -b main https://github.com/scwatson4/sage-summer-camp-2026 && \
  cd sage-summer-camp-2026/flashpoint/plugin-flash
./sync_detectors.sh                 # vendor detectors/ into the context
sudo pluginctl build .              # needs the local registry running —
                                    # see classroom-notes.md if port 5000 refuses
sudo pluginctl run --name flash localhost:5000/local/plugin-flash \
  -- --fps 1 --seconds 60 --interval 300
```

Local no-infra test first (also works on the laptop):
```bash
PYWAGGLE_LOG_DIR=test-run python3 main.py --input demo-frames
cat test-run/data.ndjson            # published values land here
```
Expected: exactly 2 `lightning.flash.candidate` events (jump ≈ 90,
azimuth_sector 1, ~67.5°) plus their `.luma` (~120) and
`frames_checked` = 40.

ECR submission (after pushing to GitHub — ECR pins the branch head):
run ./sync_detectors.sh, commit the vendored copy, then POST sage.yaml per
classroom-notes.md "ECR submission (API route)".

Cloud check after a node run:
```bash
curl -s -H 'Content-Type: application/json' \
  https://data.sagecontinuum.org/api/v1/query \
  -d '{"start":"-10m","filter":{"task":"flash","vsn":"H03E"}}'
```

## Demo frames are SYNTHETIC

`demo-frames/` (regenerable via `python3 make_demo_frames.py`) is 40 tiny
64×64 grayscale JPEGs: night-sky base luma ~30, exactly two flash frames
(~120) at epochs 13 s and 29 s with a hot wedge in fisheye sector 1. They
smoke-test the pipeline end-to-end with zero credentials/network/camera —
they are NOT real lightning and prove nothing about detection skill (the
detector's validation lives in the upstream `flashpoint/detectors/tests/`
and the M1 archive work; tests are stripped from the vendored copy here).

## H03E gotchas

- `pluginctl build` names the image after the DIRECTORY, not sage.yaml:
  the local image is `localhost:5000/local/plugin-flash`
  (not `.../flashpoint-flash`).
- Run via `localhost:5000/...`, not `10.31.81.1:5000/...` — the latter is
  the registry's build-side address and pulls fail from pods.
- The dev-blade pods have no camera: default (camera) mode fails to open
  `cv2` device 0, logs it, runs the bundled demo batch once, and exits —
  by design, so a bare no-args container run is the smoke test. On nodes
  with a real camera, pass the right device (e.g. `--camera <data-config
  id or RTSP URL>`); device 0 is only the cv2 default.
- Daytime batches will flag `daytime=True` (bright baseline ⇒ weak flash
  contrast); downstream fusion should treat those with suspicion — the
  plugin publishes them anyway and lets M5 decide.
