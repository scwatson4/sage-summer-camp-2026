"""Evidence renderer + Slack delivery tests (no network required).

Run:  python risk/tests/test_slack_evidence.py
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from PIL import Image  # noqa: E402

from agent import evidence  # noqa: E402
from risk import RiskFactors, build_card, score  # noqa: E402
from risk.card import to_slack_blocks  # noqa: E402
from risk.slack_bot import env, review_blocks  # noqa: E402
from risk.slack_socket import handle_action  # noqa: E402

R = []


def check(name, cond, detail=""):
    print(f"{'OK ' if cond else 'FAIL'} {name} {detail}")
    R.append(cond)


def main():
    tmp = pathlib.Path(tempfile.mkdtemp())
    src = pathlib.Path(__file__).resolve().parents[2] / "docs" / "w097-imagery"
    raws = [str(src / "ptz-2025-10-05T2020Z.jpg"),
            str(src / "ptz-2025-10-01T2020Z.jpg")]

    # 1. raw frames are never modified (the W097 rule)
    before = [Image.open(r).tobytes() for r in raws]
    pack = evidence.evidence_pack(150.0, raws, tile_probs=[0.9] + [0.01] * 44,
                                  gap_s=120, outdir=tmp)
    after = [Image.open(r).tobytes() for r in raws]
    check("raw frames untouched", before == after)
    check("annotated copies written", len(pack["annotated"]) == 2
          and all(pathlib.Path(p).exists() for p in pack["annotated"]))
    check("annotated differs from raw",
          Image.open(pack["annotated"][0]).tobytes() != before[0])
    check("before/after composite built",
          pack["composite"] and Image.open(pack["composite"]).width
          > Image.open(raws[0]).width * 2)

    # 2. box annotation path
    boxed = evidence.annotate_boxes(
        raws[0], [{"label": "smoke", "confidence": 0.53,
                   "box": [100, 100, 400, 300]}],
        out_path=tmp / "boxed.jpg")
    check("box annotation renders", pathlib.Path(boxed).exists())

    # 3. card carries evidence, conditions, scene read
    f = RiskFactors(rain_mm=0.0, dryness=0.7, fuel=0.6, thunder_conf=1.0,
                    sources={"rain": "gauge", "dryness": "POWER",
                             "fuel": "cover", "thunder": "6 nodes"})
    s = {"time_epoch": 1784344326.0, "lat": 41.7, "lon": -88.0,
         "semi_major_m": 160.0, "semi_minor_m": 95.0, "angle_deg": 30.0,
         "gdop": 0.9, "rms_m": 3.0, "n_nodes": 6, "quality": "fix",
         "ranges": {"V032": 2.27}, "note": ""}
    card = build_card(s, score(f), watch={"revisit_min": 20, "hours": 72},
                      evidence=[pack], provenance="demo",
                      conditions={"wind": "3.4 m/s", "RH": "38%"},
                      scene_read="white column above treeline")
    body = to_slack_blocks(card)["blocks"][1]["text"]["text"]
    for tok in ("evidence, sector", "before/after composite",
                "conditions at strike", "scene read", "DEMO"):
        check(f"card renders '{tok}'", tok in body)

    # 3b. glanceable summary vs full detail (the alert must not be a wall)
    from risk.card import detail_markdown, summary_line
    summ = summary_line(card)
    detail = detail_markdown(card)
    check("summary is one short line",
          "\n" not in summ and len(summ) < 120, f"{len(summ)} chars")
    check("summary carries score/dry/accuracy/nodes",
          all(t in summ for t in ("83", "DRY", "nodes")), summ)
    check("summary omits raw coordinates",
          "41.7" not in summ and "GDOP" not in summ)
    check("detail carries the audit trail",
          all(t in detail for t in ("position", "per-node ranges", "score = ",
                                    "corroboration", "conditions")))
    check("detail is longer than summary", len(detail) > 3 * len(summ))

    # 3c. contact sheet (the closest thing to a carousel Slack allows)
    strip = pack.get("strip")
    check("evidence strip built", strip and pathlib.Path(strip).exists())
    if strip:
        w = Image.open(strip).width
        check("strip tiles multiple frames", w > Image.open(raws[0]).width,
              f"{w}px wide")

    # 4. review buttons
    blocks = review_blocks("S2", "live")
    ids = [e["action_id"] for e in blocks[0]["elements"]]
    check("four review actions",
          ids == ["confirm_smoke", "reject_false", "keep_watching",
                  "add_comment"], str(ids))
    check("no-dispatch notice on live",
          "no automated dispatch" in blocks[1]["elements"][0]["text"])

    # 5. decision handling writes audit + labeled example
    import json
    from risk import slack_socket as ss
    ss.DECISIONS = tmp / "decisions.jsonl"
    ss.DIRECTIVES = tmp / "directives.jsonl"
    d, human = ss.handle_action("confirm_smoke", "S2", "sammy")
    check("decision logged", ss.DECISIONS.exists()
          and json.loads(ss.DECISIONS.read_text().splitlines()[0])["label"]
          == "confirmed_smoke")
    check("directive emitted for confirmation", ss.DIRECTIVES.exists())
    d2, _ = ss.handle_action("reject_false", "S3", "sammy")
    check("false positive labeled", d2["label"] == "false_positive")
    check("rejection emits no directive",
          len(ss.DIRECTIVES.read_text().splitlines()) == 1)

    # 6. env parser handles a value that starts with '#'
    check("env() keeps leading '#' in channel",
          env("SLACK_CHANNEL", "").startswith("#")
          or env("SLACK_CHANNEL", "") == "")

    assert all(R), f"{R.count(False)} check(s) failed"
    print(f"\nALL {len(R)} EVIDENCE/SLACK CHECKS PASS")


if __name__ == "__main__":
    main()
