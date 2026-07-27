# plugin-thunder — M2 edge plugin

The D1-2 thunder detector packaged for Sage nodes. Standalone candidates
only (M1 contract); event metadata published, raw audio stays on-node unless
a candidate fires.

## Build & run on H03E (from your laptop, per the runbook)

```bash
ssh waggle-dev-node-H03E
tmux new -s m2                      # or: tmux attach -t m2
git clone -b main https://github.com/scwatson4/sage-summer-camp-2026 && \
  cd sage-summer-camp-2026/flashpoint/plugin-thunder
./sync_detectors.sh                 # vendor detectors/ into the context
sudo pluginctl build .              # needs the local registry running —
                                    # see classroom-notes.md if port 5000 refuses
sudo pluginctl run --name thunder localhost:5000/local/flashpoint-thunder \
  -- --seconds 30 --interval 300
```

Local no-infra test first (also works on the laptop):
```bash
PYWAGGLE_LOG_DIR=test-run python3 main.py --input ../data/kitten_clips/<any>.flac
cat test-run/data.ndjson            # published values land here
```

ECR submission (after pushing to GitHub — ECR pins the branch head):
run ./sync_detectors.sh, commit the vendored copy, then POST sage.yaml per
classroom-notes.md "ECR submission (API route)".

Cloud check after a node run:
```bash
curl -s -H 'Content-Type: application/json' \
  https://data.sagecontinuum.org/api/v1/query \
  -d '{"start":"-10m","filter":{"task":"thunder","vsn":"H03E"}}'
```
