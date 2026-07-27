"""Notification cards: markdown + Slack Block Kit, dry-run by default.

Card contract (plan F4 + the evidence rule):
- map with uncertainty ellipse (link/attachment), strike time, score with
  FULL factor breakdown and per-factor provenance, dry-lightning flag,
  follow-up smoke-check schedule;
- evidence frames ship as RAW + ANNOTATED pairs (never boxes burned into
  the only copy — the W097 lesson);
- disagreements are published, not suppressed: a secondary-look
  non-confirmation becomes a quieter update on the same thread, because
  showing falsifications is where reviewer trust comes from (M1).
- human review, never auto-dispatch.

send_slack() posts only when SLACK_WEBHOOK_URL is set; otherwise it prints
the card and returns the payload (dry-run).
"""
from __future__ import annotations

import datetime
import json
import os
import re
import urllib.request


def build_card(strike: dict, risk: dict, watch: dict | None = None,
               evidence: list[dict] | None = None):
    """strike: fusion Strike.to_dict(); risk: score.score() output;
    watch: {revisit_min, hours}; evidence: [{sector, raw, annotated, note}]."""
    ts = datetime.datetime.fromtimestamp(strike["time_epoch"],
                                         datetime.timezone.utc)
    f = risk["factors"]
    sources = f.sources or {}
    return {
        "title": (f"Ignition risk {risk['total']:.0f}/100 — strike "
                  f"{ts:%Y-%m-%d %H:%M:%S}Z"),
        "dry_lightning": risk["dry_lightning"],
        "strike": {
            "lat": strike["lat"], "lon": strike["lon"],
            "ellipse_m": [strike["semi_major_m"], strike["semi_minor_m"]],
            "gdop": strike["gdop"], "quality": strike["quality"],
            "n_nodes": strike["n_nodes"], "ranges_km": strike["ranges"],
        },
        "score": {
            "total": risk["total"],
            "breakdown": risk["breakdown"],
            "inputs": {
                "rain_mm": [f.rain_mm, sources.get("rain", "unspecified")],
                "dryness": [f.dryness, sources.get("dryness", "unspecified")],
                "fuel": [f.fuel, sources.get("fuel", "unspecified")],
                "thunder_conf": [f.thunder_conf,
                                 sources.get("thunder", "unspecified")],
            },
        },
        "watch": watch or {},
        "evidence": evidence or [],
        "posture": "human review only — no automated dispatch",
    }


def render_markdown(card):
    s, sc = card["strike"], card["score"]
    lines = [
        f"## ⚡ {card['title']}",
        ("**DRY LIGHTNING** (rain below 2.5 mm at the node)"
         if card["dry_lightning"] else "wet strike (rain at node)"),
        f"- location: {s['lat']:.5f}, {s['lon']:.5f} — 1σ ellipse "
        f"{s['ellipse_m'][0]:.0f}×{s['ellipse_m'][1]:.0f} m, GDOP "
        f"{s['gdop']:.1f}, {s['n_nodes']} nodes [{s['quality']}]",
        f"- ranges: " + ", ".join(f"{v} {r:.2f} km"
                                  for v, r in s["ranges_km"].items()),
        f"- **score {sc['total']:.0f}** = "
        + " + ".join(f"{k} {v:.0f}" for k, v in sc["breakdown"].items()),
    ]
    for name, (val, src) in sc["inputs"].items():
        lines.append(f"    - {name}: {val} ({src})")
    if card["watch"]:
        lines.append(f"- smoke watch: every {card['watch'].get('revisit_min')} "
                     f"min for {card['watch'].get('hours')} h")
    for ev in card["evidence"]:
        lines.append(f"- evidence sector {ev.get('sector')}: raw {ev.get('raw')} "
                     f"| annotated {ev.get('annotated')} {ev.get('note', '')}")
    lines.append(f"_{card['posture']}_")
    return "\n".join(lines)


def _mrkdwn(md):
    """Markdown -> Slack mrkdwn. Slack has no '##' headers and renders '**'
    as literal asterisks, so headers become closed *bold* lines and bullets
    become '•' (a naive replace leaves an unclosed '*' on the header)."""
    out = []
    for line in md.splitlines():
        if line.startswith("## "):
            line = "*" + line[3:].strip() + "*"
        else:
            line = re.sub(r"\*\*(.+?)\*\*", r"*\1*", line)
            line = re.sub(r"^(\s*)- ", r"\1• ", line)
        out.append(line)
    return "\n".join(out)


def to_slack_blocks(card):
    s = card["strike"]
    header = card["title"]
    body = _mrkdwn(render_markdown(card))
    # strip the duplicated title line now that it lives in the header block
    body = "\n".join(body.splitlines()[1:]).strip()
    blocks = [
        {"type": "header",
         "text": {"type": "plain_text", "text": header[:150], "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": body[:2900]}},
    ]
    if s.get("lat") is not None:
        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn",
             "text": (f"<https://www.google.com/maps?q={s['lat']:.5f},"
                      f"{s['lon']:.5f}|open location in maps> · "
                      f"quality *{s['quality']}* · {s['n_nodes']} nodes")}]})
    return {"blocks": blocks}


def send_slack(card, webhook_url=None, timeout=20):
    """POST to Slack when a webhook is configured; dry-run print otherwise.
    Returns (sent: bool, payload)."""
    payload = to_slack_blocks(card)
    url = webhook_url or os.environ.get("SLACK_WEBHOOK_URL", "")
    if not url:
        print("[risk-card DRY-RUN]\n" + render_markdown(card))
        return False, payload
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status == 200, payload
