# plugin-stormmode — M4 edge plugin

The D2-3 tiered storm-mode controller (IDLE → OUTLOOK → APPROACH → STORM →
AFTERMATH, guardrails + full audit trail) packaged for Sage nodes. Fleet
actions stay **DRY-RUN** (camp scheduling permissions unresolved) — every
arm/revert/watch/notify intent is published to Beehive as
`storm.mode.action` and appended to the JSONL audit instead of touching the
samplers.

Default mode (`--mode replay`, what a bare container run does) replays the
REAL Kitten Fire ignition storm from the committed dual-satellite GLM
fixture: fully offline, zero credentials, zero sensors. Expected headline:
**145 min trigger lead** before the first local flash, one holdover watch
armed, ends clean in IDLE.

## Build & run on H03E (from your laptop, per the runbook)

```bash
ssh waggle-dev-node-H03E
tmux new -s m4                      # or: tmux attach -t m4
git clone -b main https://github.com/scwatson4/sage-summer-camp-2026 && \
  cd sage-summer-camp-2026/flashpoint/plugin-stormmode
./sync_vendor.sh                    # vendor controller/ + siblings into the context
sudo pluginctl build .              # needs the local registry running —
                                    # see classroom-notes.md if port 5000 refuses
sudo pluginctl run --name stormmode localhost:5000/local/plugin-stormmode
                                    # no args = offline Kitten replay (smoke test)
sudo pluginctl run --name stormmode localhost:5000/local/plugin-stormmode \
  -- --mode live --vsn W096 --lat 41.8657 --lon -87.6465 --interval 300
```

Local no-infra test first (also works on the laptop):
```bash
PYWAGGLE_LOG_DIR=test-run python3 main.py            # offline replay demo
cat test-run/data.ndjson                             # published values land here
```

Live-mode feeds and credentials:

- NWS alerts: free, no key.
- Node met: public `sage_data_client` query, no key.
- Xweather cells/strikes: set `XWEATHER_CLIENT_ID` / `XWEATHER_CLIENT_SECRET`
  env vars (pass with `pluginctl run ... --env` or export in the session;
  never commit them). Polled ONLY while the NWS outlook is elevated, to stay
  inside the 15k/month budget. **Without creds live mode keeps running
  degraded** (no cell/strike evidence) — `feeds.xweather_inputs` catches the
  `SystemExit` the creds check raises, so an elevated outlook without a key
  can no longer crash the loop.

ECR submission (after pushing to GitHub — ECR pins the branch head):
run ./sync_vendor.sh, commit the vendored copy, push, then POST sage.yaml
per classroom-notes.md "ECR submission (API route)".

Cloud check after a node run:
```bash
curl -s -H 'Content-Type: application/json' \
  https://data.sagecontinuum.org/api/v1/query \
  -d '{"start":"-10m","filter":{"task":"stormmode","vsn":"H03E"}}'
```

## Published measurements

| name | value | meta |
| --- | --- | --- |
| `storm.mode.tier` | tier int (0–4), one per transition | tier name, mode, replay_t |
| `storm.mode.poll` | tier int, live heartbeat every `--heartbeat-every` polls (default 12) | tier name |
| `storm.mode.action` | 1 per action/notify/audit intent | kind + short detail |
| `storm.mode.replay.trigger_lead_min` | minutes armed before first local flash | |
| `storm.mode.replay.strikes_watched` | holdover watches armed | |
| `storm.mode.replay.guardrails_fired` | audited guardrail events | |
| `storm.mode.replay.audit_records` | audit trail length | |

## H03E gotchas (inherited from plugin-thunder, validated 2026-07-27)

- `pluginctl build` names the image after the DIRECTORY, not sage.yaml:
  the local image is `localhost:5000/local/plugin-stormmode`
  (not `.../flashpoint-stormmode`).
- Run via `localhost:5000/...`, not `10.31.81.1:5000/...`.
- No mic/camera needed here at all — the dev-blade "no PulseAudio" gotcha
  does not apply; the bare no-args run is the working smoke test.
