"""CLI:  python -m controller replay | live --vsn W06C --lat .. --lon ..

`replay` needs nothing (fixture built from committed GLM data).
`live` polls real feeds at --interval seconds and drives a DRY-RUN sink —
safe to leave running anywhere; it changes nothing on the fleet.
"""
import argparse
import sys
import time


def main():
    ap = argparse.ArgumentParser(prog="controller")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("replay", help="re-run the Kitten ignition storm")
    live = sub.add_parser("live", help="poll live feeds, dry-run actions")
    live.add_argument("--vsn", required=True)
    live.add_argument("--lat", type=float, required=True)
    live.add_argument("--lon", type=float, required=True)
    live.add_argument("--interval", type=int, default=300)
    args = ap.parse_args()

    if args.cmd == "replay":
        from controller.replay import run
        summary, _ = run()
        sys.exit(0 if summary["final_tier"] in ("IDLE", "OUTLOOK") else 1)

    from controller import feeds
    from controller.actions import AgentSchedulerSink
    from controller.stormmode import Config, Controller, Inputs

    sink = AgentSchedulerSink(audit_path=f"storm-audit-{args.vsn}.jsonl")
    ctl = Controller(Config(), sink, node_latlon=(args.lat, args.lon),
                     t0=time.time())
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
        print(f"[{time.strftime('%H:%M')}] tier={tier.name} outlook={elevated} "
              f"cell={cell_km} strikes={strikes} dp={dp:.1f} gust={gust:.1f}",
              file=sys.stderr)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
