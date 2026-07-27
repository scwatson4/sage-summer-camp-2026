# Storm-mode controller (D2–3, plan F3)

Tiered state machine: **IDLE → OUTLOOK → APPROACH (arm continuous) → STORM →
AFTERMATH (72 h holdover watch) → revert.** Deterministic core, pluggable
action sinks, full audit trail, guardrails (daily continuous-capture budget,
storm-hour cap, arm timeouts, exit hysteresis).

```bash
python -m controller replay                 # re-run the REAL Kitten ignition
                                            # storm through the controller
python -m controller live --vsn W06C --lat 43.9402 --lon -110.6441
                                            # poll real feeds, DRY-RUN actions
python controller/tests/test_stormmode.py   # 19 checks
```

**Replay headline (real GLM data, committed fixture):** the controller arms
continuous capture **145 minutes before the first local flash** of the storm
that preceded the Kitten Fire, rides out the storm, then schedules the
holdover smoke watch with strike sectors. Snapshot sampling would have been
listening ~0.2% of that time.

- `stormmode.py` — pure transition engine (no I/O; replayable)
- `feeds.py` — NWS alerts (free), Xweather cells/strikes (budget-aware: only
  polled when the outlook is elevated), node met trends, detector hooks
- `actions.py` — `DryRunSink` (default: fleet job control is gated on camp
  scheduling permissions), `AgentSchedulerSink` (emits the `ptz_node schedule
  add` command for the Tier-3 watch)
- `replay.py` — fixture built from `detectors/data/kitten_glm.json`

Wiring the real thing on a node: swap `DryRunSink` for a sink that calls the
Sage job API (`submit_plugin_job`/`suspend_job`) once organizers confirm
scheduling permissions — every call site is already marked in `actions.py`.
