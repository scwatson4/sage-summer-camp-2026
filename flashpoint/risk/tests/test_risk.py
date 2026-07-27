"""Risk score + card tests: back-test separation, gating, card contract.

Run:  python risk/tests/test_risk.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from risk import RiskFactors, build_card, render_markdown, score  # noqa: E402
from risk.card import send_slack, to_slack_blocks  # noqa: E402

RESULTS = []


def check(name, cond, detail=""):
    print(f"{'OK ' if cond else 'FAIL'} {name} {detail}")
    RESULTS.append(cond)


def main():
    # the m1-results back-test shape: hot dry cases separate cleanly from
    # the wet control; no-strike days emit nothing at all
    kitten_night = score(RiskFactors(rain_mm=0.0, dryness=0.8, fuel=0.85,
                                     thunder_conf=0.7))
    kitten_eve = score(RiskFactors(rain_mm=2.2, dryness=0.8, fuel=0.85,
                                   thunder_conf=0.7))
    selma = score(RiskFactors(rain_mm=0.05, dryness=0.92, fuel=0.75,
                              thunder_conf=0.5))
    wet = score(RiskFactors(rain_mm=15.0, dryness=0.5, fuel=0.6,
                            thunder_conf=0.9))
    none_ = score(RiskFactors(rain_mm=0.0, dryness=0.9, fuel=0.9,
                              thunder_conf=0.0), strike_present=False)

    check("dry night storm runs hot", kitten_night["total"] >= 75,
          f"{kitten_night['total']}")
    check("2.2mm storm still warm", 55 <= kitten_eve["total"] < kitten_night["total"],
          f"{kitten_eve['total']}")
    check("selma bust hot", selma["total"] >= 75, f"{selma['total']}")
    check("wet control cool", wet["total"] <= 50, f"{wet['total']}")
    check("no strike -> no score", none_ is None)
    check("dry flag thresholds", kitten_night["dry_lightning"]
          and kitten_eve["dry_lightning"] and not wet["dry_lightning"])

    # card contract
    strike = {"time_epoch": 1751494800.0, "lat": 43.9337, "lon": -110.6069,
              "semi_major_m": 210.0, "semi_minor_m": 90.0, "angle_deg": 30.0,
              "gdop": 2.1, "rms_m": 40.0, "n_nodes": 3, "quality": "fix",
              "ranges": {"W06C": 5.98}, "note": ""}
    kitten_night["factors"].sources = {"rain": "W06C gauge ±30 min",
                                       "dryness": "NASA POWER GWETTOP 0.20",
                                       "fuel": "sagebrush/conifer (static)",
                                       "thunder": "anchored detector 0.70"}
    card = build_card(strike, kitten_night,
                      watch={"revisit_min": 20, "hours": 72},
                      evidence=[{"sector": 150, "raw": "b150_t0.jpg",
                                 "annotated": "b150_t0_ann.jpg"}])
    md = render_markdown(card)
    for token in ("DRY LIGHTNING", "GDOP", "score", "raw", "annotated",
                  "human review", "smoke watch"):
        check(f"card carries '{token}'", token in md)
    blocks = to_slack_blocks(card)
    check("slack payload valid-ish",
          blocks["blocks"][0]["text"]["type"] == "mrkdwn")
    sent, _ = send_slack(card)   # no webhook in env -> dry-run
    check("dry-run does not send", sent is False)

    assert all(RESULTS), f"{RESULTS.count(False)} risk check(s) failed"
    print(f"\nALL {len(RESULTS)} RISK CHECKS PASS")


if __name__ == "__main__":
    main()
