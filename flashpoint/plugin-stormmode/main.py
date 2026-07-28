#!/usr/bin/env python3
"""FlashPoint storm-mode plugin (M4) — the D2-3 tiered controller
(IDLE -> OUTLOOK -> APPROACH -> STORM -> AFTERMATH) packaged for Sage nodes.

Modes:
  --mode replay (DEFAULT, fully offline): re-run the REAL Kitten Fire
    ignition storm (committed dual-satellite GLM fixture) through the
    controller and publish the outcome metrics. Zero creds, zero network,
    zero sensors — this is the container smoke test.
  --mode live: poll real feeds every --interval s (NWS alerts free/no-key;
    Xweather only while the outlook is elevated, to respect the API budget;
    the node's own met stream via public sage_data_client) and drive the
    controller. ALL fleet actions stay DRY-RUN (camp scheduling permissions
    unresolved) — every intent is published + audited, nothing is scheduled.

Published measurements:
  storm.mode.tier                    tier int per transition (meta: tier)
  storm.mode.poll                    live heartbeat, tier int, every
                                     --heartbeat-every polls (default 12)
  storm.mode.action                  1 per action/notify/audit intent
                                     (meta: kind + short detail)
  storm.mode.replay.trigger_lead_min minutes armed BEFORE first local flash
  storm.mode.replay.strikes_watched  holdover watches armed
  storm.mode.replay.guardrails_fired audited guardrail events
  storm.mode.replay.audit_records    total audit trail length

Xweather creds (optional): XWEATHER_CLIENT_ID / XWEATHER_CLIENT_SECRET env
vars. Without them live mode degrades to (no cells, 0 strikes) and keeps
running — feeds.xweather_inputs catches the SystemExit.

Local test:  PYWAGGLE_LOG_DIR=test-run python3 main.py
Node test:   sudo pluginctl run --name stormmode localhost:5000/local/plugin-stormmode
"""
import argparse
import sys
import time

from waggle.plugin import Plugin

from controller.actions import AgentSchedulerSink
from controller.stormmode import Config, Controller, Inputs, Tier


def _iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


class PublishingSink(AgentSchedulerSink):
    """AgentSchedulerSink that mirrors every intent to Beehive as
    storm.mode.action (value 1). The audit trail IS a deliverable (plan
    section 10) — this makes it queryable from the cloud, not just a file."""

    def __init__(self, plugin, audit_path=None, quiet=False):
        super().__init__(audit_path=audit_path, quiet=quiet)
        self.plugin = plugin

    def _publish(self, kind, detail):
        self.plugin.publish("storm.mode.action", 1,
                            meta={"kind": str(kind),
                                  "detail": str(detail)[:140]})

    def notify(self, t, title, payload):  # not routed through audit()
        super().notify(t, title, payload)
        self._publish("notify", title)

    def audit(self, record):  # transitions, actions, guardrails
        super().audit(record)
        self._publish(record.kind, record.detail)


def run_replay(plugin):
    """Offline demo: Kitten ignition storm through the controller. Publishes
    one storm.mode.tier per transition (parsed from the audit trail —
    replay.run() is used unmodified) plus the summary metrics."""
    from controller.replay import run
    summary, ctl = run()
    for rec in ctl.audit:
        if rec.kind != "transition":
            continue
        # detail format is stable: "OLD -> NEW: why"
        dst = rec.detail.split("->", 1)[1].split(":", 1)[0].strip()
        plugin.publish("storm.mode.tier", int(Tier[dst]),
                       meta={"tier": dst, "mode": "replay",
                             "replay_t": _iso(rec.t)})
    lead = summary.get("trigger_lead_time_min")
    plugin.publish("storm.mode.replay.trigger_lead_min",
                   float(lead) if lead is not None else -1.0)
    plugin.publish("storm.mode.replay.strikes_watched",
                   int(summary["strikes_watched"]))
    plugin.publish("storm.mode.replay.guardrails_fired",
                   int(summary["guardrails_fired"]))
    plugin.publish("storm.mode.replay.audit_records",
                   int(summary["audit_records"]))
    return summary


def run_live(plugin, args):
    """Mirror of `python -m controller live` with Beehive publishing bolted
    on. Feed outages (and missing Xweather creds) degrade to no-evidence
    inputs — the loop must never die during a storm."""
    from controller import feeds

    sink = PublishingSink(plugin, audit_path=args.audit_path)
    ctl = Controller(Config(), sink, node_latlon=(args.lat, args.lon),
                     t0=time.time())
    prev = ctl.tier
    polls = 0
    print(f"live dry-run for {args.vsn} — ctrl-c to stop", file=sys.stderr)
    while True:
        now = time.time()
        elevated, why = feeds.nws_outlook_elevated(args.lat, args.lon)
        cell_km, strikes = (feeds.xweather_inputs(args.lat, args.lon)
                            if elevated else (None, 0))  # respect API budget
        dp, gust = feeds.sage_met_inputs(args.vsn)
        tier = ctl.step(Inputs(t=now, outlook_elevated=elevated,
                               nearest_cell_km=cell_km,
                               regional_strikes=strikes,
                               pressure_drop_hpa_3h=dp, gust_ms=gust))
        if tier != prev:
            plugin.publish("storm.mode.tier", int(tier),
                           meta={"tier": tier.name, "mode": "live"})
            prev = tier
        polls += 1
        if (polls - 1) % args.heartbeat_every == 0:  # poll 1, then every N
            plugin.publish("storm.mode.poll", int(tier),
                           meta={"tier": tier.name})
        print(f"[{time.strftime('%H:%M')}] tier={tier.name} outlook={elevated} "
              f"cell={cell_km} strikes={strikes} dp={dp:.1f} gust={gust:.1f}",
              file=sys.stderr)
        time.sleep(args.interval)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("replay", "live"), default="replay",
                    help="replay = offline Kitten-storm demo (default)")
    ap.add_argument("--vsn", help="live: node VSN for the met feed")
    ap.add_argument("--lat", type=float, help="live: node latitude")
    ap.add_argument("--lon", type=float, help="live: node longitude")
    ap.add_argument("--interval", type=int, default=300,
                    help="live: seconds between feed polls")
    ap.add_argument("--heartbeat-every", type=int, default=12,
                    help="live: publish storm.mode.poll every N polls")
    ap.add_argument("--audit-path", default="storm-audit.jsonl",
                    help="live: JSONL audit trail path")
    args = ap.parse_args()
    if args.mode == "live" and not (args.vsn and args.lat is not None
                                    and args.lon is not None):
        ap.error("--mode live requires --vsn, --lat, --lon")
    if args.interval < 1 or args.heartbeat_every < 1:
        ap.error("--interval and --heartbeat-every must be >= 1")

    with Plugin() as plugin:
        if args.mode == "replay":
            summary = run_replay(plugin)
            sys.exit(0 if summary["final_tier"] in ("IDLE", "OUTLOOK") else 1)
        run_live(plugin, args)


if __name__ == "__main__":
    main()
