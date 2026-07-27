"""CLI:  python -m fusion demo | live --events events.jsonl

demo: full detector->fusion chain on the demo storm, writes
      fusion/out/strikes.json + fusion-map.html.
live: tail a JSONL event stream (one flash/thunder event dict per line —
      the M2 plugins' output shape), re-fuse on every batch, rewrite the
      map. Works on any machine that can see the event file; this is the
      live strike map until Beehive subscription lands on-node.
"""
import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


def main():
    ap = argparse.ArgumentParser(prog="fusion")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    live = sub.add_parser("live")
    live.add_argument("--events", required=True)
    live.add_argument("--nodes", required=True,
                      help="JSON file: {vsn: [lat, lon], ...}")
    live.add_argument("--interval", type=float, default=10.0)
    live.add_argument("--temp-c", type=float, default=20.0)
    args = ap.parse_args()

    if args.cmd == "demo":
        from fusion.demo_run import run
        strikes, truth, errs = run()
        fixes = [e for e in errs if e[2] == "fix"]
        sys.exit(0 if len(fixes) >= 3 else 1)

    from fusion.engine import FusionEngine
    from fusion import strikemap, strikemap_leaflet
    nodes = {v: tuple(p) for v, p in
             json.loads(pathlib.Path(args.nodes).read_text()).items()}
    engine = FusionEngine(nodes)
    out = pathlib.Path(__file__).resolve().parent / "out"
    out.mkdir(exist_ok=True)
    seen = 0
    print(f"tailing {args.events} every {args.interval}s — ctrl-c to stop",
          file=sys.stderr)
    while True:
        lines = pathlib.Path(args.events).read_text().splitlines() \
            if pathlib.Path(args.events).exists() else []
        if len(lines) != seen:
            seen = len(lines)
            events = [json.loads(ln) for ln in lines if ln.strip()]
            strikes = engine.process(events, temp_c=args.temp_c)
            payload = {"generated_from": f"live tail ({seen} events)",
                       "nodes": [{"vsn": v, "lat": p[0], "lon": p[1]}
                                 for v, p in nodes.items()],
                       "strikes": [s.to_dict() for s in strikes],
                       "truth": []}
            (out / "strikes.json").write_text(json.dumps(payload, indent=1))
            strikemap.render(payload, out / "fusion-map.html")
            strikemap_leaflet.render(payload, out / "fusion-map-leaflet.html")
            print(f"[{time.strftime('%H:%M:%S')}] {seen} events -> "
                  f"{len(strikes)} strikes", file=sys.stderr)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
