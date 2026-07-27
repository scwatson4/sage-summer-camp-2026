"""Socket Mode listener — reviewer decisions flow back to the node.

Why Socket Mode: the node sits behind the Sage VPN/NAT and cannot receive
inbound webhooks. Socket Mode opens an OUTBOUND WebSocket to Slack, so
button clicks and comments arrive with no public endpoint and no firewall
changes. Runs anywhere the node runs.

What a click does (and does NOT do):
- appends to data/review-decisions.jsonl — the audit trail AND the labeled
  dataset (confirmed smoke / false positive are exactly the labels the
  neural classifier thread needs)
- updates the Slack message so the channel shows who decided what
- optionally writes a watch-directive file the controller/agent can read
  (keep-watching extends the sector's revisit; confirm raises priority)
It never dispatches anyone or actuates anything on its own — human review
means a human stays in the loop, which is the whole posture.

Run:  python -m risk listen        (ctrl-c to stop)
"""
from __future__ import annotations

import datetime
import json
import pathlib

from risk.slack_bot import env

ROOT = pathlib.Path(__file__).resolve().parents[1]
DECISIONS = ROOT / "data" / "review-decisions.jsonl"
DIRECTIVES = ROOT / "data" / "watch-directives.jsonl"

LABELS = {
    "confirm_smoke": ("confirmed_smoke", "🔥 confirmed smoke"),
    "reject_false": ("false_positive", "❌ marked false positive"),
    "keep_watching": ("keep_watching", "🔁 keep watching"),
    "add_comment": ("comment_requested", "💬 comment"),
}


def _record(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(obj) + "\n")


def handle_action(action_id, strike_id, user, text=""):
    """Pure decision logic — unit-testable without Slack."""
    label, human = LABELS.get(action_id, ("unknown", action_id))
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    decision = {"time": now, "strike_id": strike_id, "action": action_id,
                "label": label, "reviewer": user, "comment": text}
    _record(DECISIONS, decision)
    # directives the controller/agent may consult; advisory, never automatic
    if label in ("confirmed_smoke", "keep_watching"):
        _record(DIRECTIVES, {"time": now, "strike_id": strike_id,
                             "directive": ("prioritize_sector"
                                           if label == "confirmed_smoke"
                                           else "extend_watch"),
                             "reviewer": user})
    return decision, human


def start(quiet=False):
    from slack_sdk import WebClient
    from slack_sdk.socket_mode import SocketModeClient
    from slack_sdk.socket_mode.request import SocketModeRequest
    from slack_sdk.socket_mode.response import SocketModeResponse

    app_token, bot_token = env("SLACK_APP_TOKEN"), env("SLACK_BOT_TOKEN")
    if not app_token or not bot_token:
        raise SystemExit("need SLACK_APP_TOKEN and SLACK_BOT_TOKEN "
                         "(env or flashpoint/.env)")
    web = WebClient(token=bot_token)
    client = SocketModeClient(app_token=app_token, web_client=web)

    def on_request(cli: SocketModeClient, req: SocketModeRequest):
        cli.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
        if req.type != "interactive":
            return
        payload = req.payload
        for action in payload.get("actions", []):
            aid = action.get("action_id")
            strike_id = action.get("value", "?")
            user = (payload.get("user", {}).get("username")
                    or payload.get("user", {}).get("id", "?"))
            decision, human = handle_action(aid, strike_id, user)
            if not quiet:
                print(f"[review] {user} -> {human} on strike {strike_id}")
            ch = payload.get("channel", {}).get("id")
            ts = payload.get("message", {}).get("ts")
            if ch and ts:
                web.chat_postMessage(
                    channel=ch, thread_ts=ts,
                    text=f"*{human}* by <@{payload.get('user',{}).get('id','?')}> "
                         f"— logged for strike `{strike_id}`. "
                         + ("This decision is now a labeled training example."
                            if decision["label"] in ("confirmed_smoke",
                                                     "false_positive")
                            else "Watch schedule updated."))

    client.socket_mode_request_listeners.append(on_request)
    if not quiet:
        print("Socket Mode connected — waiting for reviewer decisions "
              f"(logging to {DECISIONS.relative_to(ROOT)}). Ctrl-C to stop.")
    client.connect()
    import threading
    threading.Event().wait()
