Notes from the 2026 Sage Summer Camp

## Lessons learned building & running `app-tutorial` (2026-07-20 to 2026-07-21)

### SSH from Windows
- Use Windows' built-in OpenSSH (`C:\Windows\System32\OpenSSH\ssh.exe`), not Git Bash's ssh — only the Windows one talks to the Windows ssh-agent service where the node key lives.
- If your key has a passphrase, load it into the agent once (`ssh-add`) and everything (ssh, scp, ProxyCommand jump through beekeeper) works non-interactively afterward.
- A "banner exchange timeout" when connecting through the jump host usually means the *inner* ProxyCommand ssh silently failed auth (e.g., locked key) — not a network problem.

### Building and running plugins on a fresh Thor dev node
- `sudo pluginctl build .` builds the container image *and* pushes it to a local registry at `10.31.81.1:5000` (the node's own lan0 IP). A freshly provisioned node may not have that registry running — nothing listens on port 5000 and the build fails with "connection refused".
- Fix: start the standard registry yourself (dev sudo covers `docker`): `sudo docker run -d --restart=always --name local-registry -p 5000:5000 -v local-registry-data:/var/lib/registry docker.io/library/registry:2`. Use a *named volume* — podman does not auto-create host directories like Docker does, and dev sudo doesn't include `mkdir`.
- Podman then needs the registry marked insecure (plain HTTP). Since `/etc/containers/registries.conf` is root-owned, write a drop-in via a container: `sudo docker run --rm -v /etc/containers:/host docker.io/library/registry:2 sh -c 'mkdir -p /host/registries.conf.d && printf "[[registry]]\nlocation = \"10.31.81.1:5000\"\ninsecure = true\n" > /host/registries.conf.d/local-registry.conf'`
- **Key trick:** `pluginctl build` prints the image as `10.31.81.1:5000/local/<app>`, but running that fails — Kubernetes' containerd refuses plain-HTTP registries it isn't configured for. Run it as **`localhost:5000/local/<app>`** instead: containerd allows HTTP for localhost registries by default, and the registry listens on all interfaces. `sudo pluginctl run --name <app> localhost:5000/local/<app>`

### Cameras
- These Thor nodes have no local `Camera()`/`Camera("left")` device — cameras are RTSP network streams on the Sage VPN (`10.107.x.x`), e.g. `Camera("rtsp://10.107.0.232:10001/profile1/media.smp")`.
- **Never hardcode RTSP URLs containing passwords** — ECR requires the app repo to be public on GitHub, so committed credentials are published to the world. Take the camera URL as a runtime argument instead (our app uses `--input`, defaulting to a bundled example image): `sudo pluginctl run --name app-tutorial localhost:5000/local/app-tutorial -- --input "rtsp://..."`
- `cv2.imread` returns BGR, but pywaggle's `Camera` returns RGB — convert with `cv2.cvtColor(..., cv2.COLOR_BGR2RGB)` when reading files or your R/B channels swap.

### Testing and verifying
- Test locally without any Sage infrastructure by setting `PYWAGGLE_LOG_DIR=test-run` — published values land in `test-run/data.ndjson` and uploads in `test-run/uploads/`.
- After a node run, verify data reached the cloud: `curl -s -H 'Content-Type: application/json' https://data.sagecontinuum.org/api/v1/query -d '{"start": "-10m","filter": {"task": "app-tutorial", "vsn": "H03E"}}'`
- A successful `pluginctl run` exits with the pod Completed and no error output — silence is success.

### ECR submission (API route)
- The portal UI works, but there's also an API: `curl -X POST https://ecr.sagecontinuum.org/api/apps/<namespace>/<name>/<version> -H "Authorization: sage $SAGE_TOKEN" --data-binary @sage.yaml`, then trigger a build with `POST .../api/builds/<namespace>/<name>/<version>`. Namespace = your Sage username.
- ECR pins the repo's branch head commit at submission time — **push to GitHub first**, or it builds your old code. Re-submitting an existing version requires DELETE then POST.
- `sage.yaml` supports `source.directory`, so the app can live in a subfolder of a bigger repo (ours is `app-tutorial/` in this one).

## H03E validation notes (2026-07-27, FlashPoint runbook)

### Python on the blades (Ubuntu 24.04 arm64)
- System pip is PEP-668 locked — `pip install --user --break-system-packages ...`
  installs to ~/.local without touching the apt-managed packages (numpy/pandas/
  scipy come from apt and are fine).
- TensorFlow HAS aarch64 wheels now: `tensorflow==2.21` + `tensorflow_hub`
  install and run cleanly on the Thor (YAMNet embeds ~40 min of FLAC in
  well under a minute on CPU). No Jetson-specific wheel needed for CPU work.
- Fresh blades have no git identity — `git config user.name/user.email`
  (repo-local) before the first commit.

### pluginctl, second round of gotchas
- Dev sudo is NOPASSWD for exactly: kubectl, docker, docker-compose,
  runplugin, pluginctl — nothing else (so `sudo mkdir` etc. will prompt).
- `pluginctl build` names the image after the app DIRECTORY, not the `name:`
  in sage.yaml — flashpoint/plugin-thunder builds as
  `localhost:5000/local/plugin-thunder`.
- Plugin pods have no PulseAudio: pywaggle `Microphone()` dies with a bare
  `AssertionError` from soundcard. If your app defaults to the mic, bundle an
  example clip and pass `-- --input example.flac` (same pattern as the
  bundled-image trick for cameras above).
- The local registry + insecure-registry drop-in from the app-tutorial session
  survive reboots (`--restart=always` did its job) — nothing to redo.

### sage-agent (waggle-sensor/sage-agent) on a Thor blade
- `bootstrap_python311.sh` finds system python3.12 and makes a plain venv —
  micromamba never needed. requirements + requirements-vision install clean
  (pulls CUDA-13 torch wheels, ~3 GB of pip cache).
- The sim PTZ backend has NO image-path setting: it hardcodes
  `vendor/ptz_agent/stitched.png`. To point it at your own panorama, back up
  and overwrite that file (PIL sniffs content, a JPEG under the .png name is
  fine). Delete `scratchpads/sim_ptz_state.json` to reset pan/tilt state.
- Ollama on H03E already serves gemma4:31b / gemma4:e2b / gemma4-64k — doctor's
  agent+vision checks go green with zero extra pulls; YOLO grabs yolo11n.pt
  (~5.4 MB) on first detect.

## H03E agent-ladder notes (2026-07-28)

- NVIDIA NIM (`integrate.api.nvidia.com`) is reachable from the blade; the
  Hermes `NVIDIA_API_KEY` in ~/.hermes/.env works for `openai_compat`
  clients. glm-5.2 there is TEXT-ONLY — OpenAI-style `image_url` parts are
  accepted-and-dropped with no error, and the model may hallucinate a scene
  description. Probe with deliberately corrupt image bytes to prove drop
  behavior (it then admits it has no vision).
- The manifests endpoint returns gps_lat/gps_lon = null for some reporting
  nodes (W09E, like W0A0) — keep a fallback coordinate source.
- W096's imagesampler stopped publishing (≥24 h silent on 2026-07-28) while
  its met/audio tasks run fine — check task-level liveness, not node-level.
- `python3 -m controller live` prints through a pipe only with
  PYTHONUNBUFFERED=1 — the poll lines sit in block-buffer otherwise and a
  `timeout ... | head` capture looks like a hang.
- sage-agent venv needs `pip install sage-data-client` if scripts mix query
  API + ultralytics in one process.
