"""CLI:  python -m risk demo [--slack] | python -m risk post FILE [--slack]

demo: score the fused demo strikes (fusion/out/strikes.json — run
      `python -m fusion demo` first if missing) and emit a notification
      card per fix-quality strike. Dry-run prints cards; --slack (or a
      SLACK_WEBHOOK_URL in the environment / flashpoint/.env) posts them.
post: same, for any strikes.json produced by fusion live mode.

Demo factor provenance (deterministic, honest about what's synthetic):
rain from the demo storm's own met stream at strike time; dryness/fuel are
labeled demo assumptions; thunder confidence scales with fusing-node count.
Live deployments replace these with risk.score.rain_at_strike() and
power_dryness() — both already verified against real feeds.
"""
import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from risk.card import build_card, send_slack  # noqa: E402
from risk.score import RiskFactors, score  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _env_webhook():
    import os
    url = os.environ.get("SLACK_WEBHOOK_URL", "")
    envf = ROOT / ".env"
    if not url and envf.exists():
        m = re.search(r"^\s*SLACK_WEBHOOK_URL\s*=\s*['\"]?([^'\"\s#]+)",
                      envf.read_text(), re.M)
        url = m.group(1) if m else ""
    return url


def demo_factors(strike, met_df):
    """Deterministic factors for the demo storm, provenance labeled."""
    import pandas as pd

    t = pd.Timestamp(strike["time_epoch"], unit="s", tz="UTC")
    rain = met_df[(met_df.name == "wxt.rain.accumulation")
                  & (met_df.timestamp <= t)]["value"]
    rain_mm = float(rain.iloc[-1]) if len(rain) else 0.0
    conf = min(1.0, strike["n_nodes"] / 4.0)
    return RiskFactors(
        rain_mm=rain_mm, dryness=0.7, fuel=0.6, thunder_conf=conf,
        sources={"rain": "demo storm met stream at strike time",
                 "dryness": "demo assumption 0.7 (live: NASA POWER GWETTOP)",
                 "fuel": "demo assumption 0.6 (live: land cover / BioCLIP)",
                 "thunder": f"{strike['n_nodes']} nodes fused"})


def emit(strikes_path, use_slack):
    payload = json.loads(pathlib.Path(strikes_path).read_text())
    webhook = _env_webhook() if use_slack else ""
    met_df = None
    if "demo" in payload.get("generated_from", ""):
        sys.path.insert(0, str(ROOT / "dashboard"))
        from fp import demo as fpdemo
        import json as _json
        man = _json.loads((ROOT / "data" / "demo" / "manifest.json").read_text())
        met_df = fpdemo.met_index(man)

    fixes = [s for s in payload["strikes"] if s["quality"] == "fix"]
    print(f"{len(fixes)} fix-quality strike(s) -> cards "
          f"({'POSTING to Slack' if webhook else 'dry-run'})\n")
    sent = 0
    for s in fixes:
        if met_df is not None:
            factors = demo_factors(s, met_df)
        else:  # live path: pull real feeds, degrade to labeled defaults
            from risk.score import rain_at_strike
            vsn = next(iter(s["ranges"]), None)
            mm, src = (rain_at_strike(vsn, s["time_epoch"])
                       if vsn else (None, "no node"))
            factors = RiskFactors(
                rain_mm=mm if mm is not None else 0.0,
                dryness=0.5, fuel=0.5, thunder_conf=min(1.0, s["n_nodes"] / 4),
                sources={"rain": src if mm is not None else f"default ({src})",
                         "dryness": "default 0.5 — wire power_dryness()",
                         "fuel": "default 0.5",
                         "thunder": f"{s['n_nodes']} nodes fused"})
        risk = score(factors, strike_present=True)
        card = build_card(s, risk, watch={"revisit_min": 20, "hours": 72})
        ok, _ = send_slack(card, webhook_url=webhook or None)
        sent += bool(ok)
        print()
    if webhook:
        print(f"posted {sent}/{len(fixes)} cards to Slack")
    else:
        print("dry-run complete — set SLACK_WEBHOOK_URL (env or flashpoint/"
              ".env) or pass --slack with it set, and these post for real")


def main():
    ap = argparse.ArgumentParser(prog="risk")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo")
    d.add_argument("--slack", action="store_true")
    p = sub.add_parser("post")
    p.add_argument("file")
    p.add_argument("--slack", action="store_true")
    args = ap.parse_args()

    if args.cmd == "demo":
        path = ROOT / "fusion" / "out" / "strikes.json"
        if not path.exists():
            sys.exit("run `python -m fusion demo` first (no strikes.json)")
        emit(path, args.slack)
    else:
        emit(args.file, args.slack)


if __name__ == "__main__":
    main()
