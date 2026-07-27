"""Bot-token Slack delivery: rich cards, image uploads, review buttons.

Three tiers, auto-selected by what's configured (all read from env or
flashpoint/.env, never committed):
  SLACK_BOT_TOKEN + SLACK_CHANNEL -> full cards with uploaded images and
                                     approve/reject/comment buttons
  SLACK_WEBHOOK_URL only          -> text card, no images/buttons (fallback)
  neither                         -> dry-run print

Images go through files.getUploadURLExternal + files.completeUploadExternal
(files.upload is deprecated); uploading to the channel means Slack hosts
them — no public URL needed, so authenticated Sage storage stays private.

Buttons carry the strike id in `value`; clicks arrive over Socket Mode
(see slack_socket.py) and land in the decision log.
"""
from __future__ import annotations

import json
import os
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def env(key, default=""):
    """Read a config value from the environment, else flashpoint/.env.

    NOTE: '#' only starts a comment when preceded by whitespace — a value may
    legitimately BEGIN with '#' (e.g. SLACK_CHANNEL=#flashpoint-alerts), and
    treating that as a comment silently yields an empty channel.
    """
    v = os.environ.get(key, "")
    if v:
        return v
    f = ROOT / ".env"
    if f.exists():
        m = re.search(rf"^\s*(?:export\s+)?{key}\s*=\s*(.*)$",
                      f.read_text(), re.M)
        if m:
            val = m.group(1).strip()
            if val[:1] in ("'", '"'):          # quoted: take to closing quote
                q = val[0]
                end = val.find(q, 1)
                return val[1:end] if end != -1 else val[1:]
            val = re.split(r"\s+#", val, 1)[0]  # inline comment only
            return val.strip()
    return default


def _client():
    from slack_sdk import WebClient
    tok = env("SLACK_BOT_TOKEN")
    return WebClient(token=tok) if tok else None


def upload_images(paths, channel_id, title_prefix="", thread_ts=None):
    """Upload local files into the channel; returns [{path, permalink, id}].

    Slack hosts the bytes, so authenticated Sage imagery never needs a public
    URL. NOTE: files_upload_v2 requires the channel ID (C0…), not the
    '#name' — passing a name fails at files.completeUploadExternal. Callers
    get the ID from a chat_postMessage response.
    """
    client = _client()
    if not client or not paths:
        return []
    out = []
    for p in paths:
        p = pathlib.Path(p)
        if not p.exists():
            out.append({"path": str(p), "error": "file not found"})
            continue
        try:
            res = client.files_upload_v2(
                channel=channel_id, file=str(p), filename=p.name,
                title=f"{title_prefix}{p.name}".strip(), thread_ts=thread_ts)
            f = res.get("file", {})
            out.append({"path": str(p), "permalink": f.get("permalink"),
                        "id": f.get("id")})
        except Exception as e:  # never let evidence failure kill the alert
            err = getattr(e, "response", None)
            out.append({"path": str(p),
                        "error": (err.get("error") if err else str(e)[:120])})
    return out


def review_blocks(strike_id, provenance="live"):
    """Human-in-the-loop controls. Approval NEVER auto-dispatches anything —
    it records a reviewer decision and (optionally) tells the node to keep
    watching. Each click is also a labeled example for the classifier."""
    return [
        {"type": "actions", "block_id": f"review::{strike_id}", "elements": [
            {"type": "button", "action_id": "confirm_smoke",
             "style": "danger",
             "text": {"type": "plain_text", "text": "🔥 Confirm smoke",
                      "emoji": True}, "value": strike_id},
            {"type": "button", "action_id": "reject_false",
             "text": {"type": "plain_text", "text": "❌ False positive",
                      "emoji": True}, "value": strike_id},
            {"type": "button", "action_id": "keep_watching",
             "text": {"type": "plain_text", "text": "🔁 Keep watching",
                      "emoji": True}, "value": strike_id},
            {"type": "button", "action_id": "add_comment",
             "text": {"type": "plain_text", "text": "💬 Comment",
                      "emoji": True}, "value": strike_id},
        ]},
        {"type": "context", "elements": [
            {"type": "mrkdwn",
             "text": ("_Human review only — no automated dispatch. Your "
                      "decision is logged and becomes a labeled training "
                      "example._" if provenance == "live" else
                      "_DEMO event — decisions are logged but change nothing._")}]},
    ]


def post_card(card, strike_id=None, image_paths=None, thread_ts=None):
    """Post a full card. Returns (ok, response_dict).

    Falls back to the webhook (text-only) when no bot token is configured,
    and to a dry-run print when neither exists — so the same call site works
    in every environment.
    """
    from risk.card import send_slack, to_slack_blocks

    client = _client()
    channel = env("SLACK_CHANNEL")
    if not client or not channel:
        ok, payload = send_slack(card)          # webhook or dry-run
        return ok, {"fallback": "webhook" if ok else "dry-run",
                    "payload": payload}

    strike_id = strike_id or str(int(card["strike"].get("lat", 0) * 1e5))
    blocks = to_slack_blocks(card)["blocks"]
    blocks += review_blocks(strike_id, card.get("provenance", "unknown"))
    # post the card first — its response yields the channel ID that uploads
    # require, and it means the alert lands even if evidence upload fails
    res = client.chat_postMessage(
        channel=channel, blocks=blocks, text=card["title"],
        thread_ts=thread_ts, unfurl_links=False)
    if not res.get("ok"):
        return False, {"error": res.get("error")}
    channel_id, ts = res.get("channel"), res.get("ts")
    uploads = upload_images(image_paths or [], channel_id,
                            title_prefix="FlashPoint evidence ",
                            thread_ts=ts)
    shown = [u for u in uploads if u.get("permalink")]
    if shown:
        client.chat_postMessage(
            channel=channel_id, thread_ts=ts,
            text="*evidence* (raw + annotated; raw frames unmodified): "
                 + " · ".join(f"<{u['permalink']}|{pathlib.Path(u['path']).name}>"
                              for u in shown))
    failed = [u for u in uploads if u.get("error")]
    if failed:
        client.chat_postMessage(
            channel=channel_id, thread_ts=ts,
            text=f":warning: {len(failed)} evidence file(s) failed to upload: "
                 + ", ".join(f"{pathlib.Path(u['path']).name} ({u['error']})"
                             for u in failed))
    return True, {"ts": ts, "channel": channel_id, "uploads": uploads}


def post_followup(strike_id, text, thread_ts=None):
    """Quieter update on the same thread — used for non-confirmations.
    Disagreements get published, not suppressed (the M1 posture)."""
    client = _client()
    channel = env("SLACK_CHANNEL")
    if not client or not channel:
        print(f"[followup dry-run] {strike_id}: {text}")
        return False, {}
    res = client.chat_postMessage(channel=channel, text=text,
                                  thread_ts=thread_ts)
    return bool(res.get("ok")), {"ts": res.get("ts")}
