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
