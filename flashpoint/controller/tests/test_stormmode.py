"""Controller unit tests: transitions, hysteresis, guardrails, watch
lifecycle — plus the full Kitten replay as the end-to-end check.

Run:  python controller/tests/test_stormmode.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from controller.actions import DryRunSink  # noqa: E402
from controller.stormmode import Config, Controller, Inputs, Tier  # noqa: E402

H = 3600.0
RESULTS = []


def check(name, cond, detail=""):
    print(f"{'OK ' if cond else 'FAIL'} {name} {detail}")
    RESULTS.append(cond)


def mk(t0=0.0, **cfg):
    sink = DryRunSink(quiet=True)
    return Controller(Config(**cfg), sink, node_latlon=(43.94, -110.64),
                      t0=t0), sink


def test_happy_path():
    ctl, sink = mk()
    t = 0.0
    ctl.step(Inputs(t=t, outlook_elevated=True))
    check("IDLE->OUTLOOK on outlook", ctl.tier == Tier.OUTLOOK)
    t += 600
    ctl.step(Inputs(t=t, outlook_elevated=True, nearest_cell_km=80))
    check("OUTLOOK->APPROACH on cell", ctl.tier == Tier.APPROACH)
    check("continuous armed", ctl.continuous_since is not None)
    t += 1800
    ctl.step(Inputs(t=t, outlook_elevated=True, local_flash=True,
                    strikes=[{"lat": 43.95, "lon": -110.58,
                              "time_epoch": t, "risk": 87}]))
    check("APPROACH->STORM on local flash", ctl.tier == Tier.STORM)
    # 35 quiet minutes -> aftermath with a watch
    t += 35 * 60
    ctl.step(Inputs(t=t, outlook_elevated=True))
    check("STORM->AFTERMATH after quiet", ctl.tier == Tier.AFTERMATH)
    check("watch started with sectors",
          any("holdover watch" in m or "WATCH" in m for _, m in sink.calls))
    check("continuous reverted", ctl.continuous_since is None)
    # 73 h later -> back to OUTLOOK (outlook still on)
    t += 73 * H
    ctl.step(Inputs(t=t, outlook_elevated=True))
    check("AFTERMATH expires to OUTLOOK", ctl.tier == Tier.OUTLOOK)


def test_no_strikes_no_watch():
    ctl, sink = mk()
    ctl.step(Inputs(t=0, outlook_elevated=True, regional_strikes=5))
    ctl.step(Inputs(t=300, outlook_elevated=True, local_thunder=True))
    ctl.step(Inputs(t=300 + 35 * 60, outlook_elevated=True))
    check("no localized strikes -> no AFTERMATH",
          ctl.tier == Tier.OUTLOOK and
          not any("watch" in m.lower() for _, m in sink.calls))


def test_approach_timeout_reverts():
    ctl, sink = mk()
    ctl.step(Inputs(t=0, outlook_elevated=True, nearest_cell_km=90))
    check("armed", ctl.tier == Tier.APPROACH)
    ctl.step(Inputs(t=5 * H, outlook_elevated=True))
    check("approach timeout -> OUTLOOK + revert",
          ctl.tier == Tier.OUTLOOK and ctl.continuous_since is None)
    check("guardrail audited",
          any(a.kind == "guardrail" for a in ctl.audit))


def test_daily_budget():
    ctl, _ = mk(max_continuous_hours_day=1.0, approach_timeout_hours=100.0)
    ctl.step(Inputs(t=0, nearest_cell_km=50))          # arm (skip outlook)
    ctl.step(Inputs(t=2 * H, local_flash=True))        # storm
    ctl.step(Inputs(t=2 * H + 35 * 60))                # quiet -> used 2.6h > 1h
    ctl.strike_log.clear()
    ctl.step(Inputs(t=3 * H, nearest_cell_km=50))      # try to re-arm same day
    check("budget blocks re-arm",
          ctl.continuous_since is None and
          any("budget" in a.detail for a in ctl.audit))


def test_storm_reentry_from_aftermath():
    ctl, _ = mk()
    ctl.step(Inputs(t=0, nearest_cell_km=50))
    ctl.step(Inputs(t=600, local_flash=True,
                    strikes=[{"lat": 43.9, "lon": -110.6,
                              "time_epoch": 600, "risk": 50}]))
    ctl.step(Inputs(t=600 + 35 * 60))
    check("in aftermath", ctl.tier == Tier.AFTERMATH)
    ctl.step(Inputs(t=600 + 40 * 60, local_thunder=True))
    check("aftermath -> storm on renewed activity", ctl.tier == Tier.STORM)


def test_kitten_replay():
    from controller.replay import run
    summary, ctl = run(quiet=True)
    check("replay reaches all tiers",
          set(summary["tiers_reached"]) >= {"APPROACH", "STORM", "AFTERMATH"},
          str(summary["tiers_reached"]))
    check("positive trigger lead time",
          (summary["trigger_lead_time_min"] or 0) > 30,
          f"lead={summary['trigger_lead_time_min']} min")
    check("watch armed", summary["strikes_watched"] >= 1)
    check("ends clean", summary["final_tier"] in ("IDLE", "OUTLOOK"))
    print(f"     replay summary: {summary}")


if __name__ == "__main__":
    test_happy_path()
    test_no_strikes_no_watch()
    test_approach_timeout_reverts()
    test_daily_budget()
    test_storm_reentry_from_aftermath()
    test_kitten_replay()
    assert all(RESULTS), f"{RESULTS.count(False)} controller check(s) failed"
    print(f"\nALL {len(RESULTS)} CONTROLLER CHECKS PASS")
