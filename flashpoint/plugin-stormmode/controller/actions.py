"""Action sinks — what the controller's decisions actually do.

DryRunSink is the DEFAULT and prints/logs intents without touching the
fleet: camp scheduling permissions on W-nodes are unresolved (CLAUDE.md
gotchas), so nothing here fires a real job until explicitly swapped in.

SageJobSink documents the real calls for when permissions exist:
  - arm:    submit_plugin_job(continuous audio/frame sampler), suspend the
            snapshot samplers
  - revert: suspend continuous job, resume snapshot samplers
  (Sage job API / sage-mcp `submit_plugin_job` / `suspend_job`; on-node
  pluginctl equivalents in classroom-notes.md.)

AgentSchedulerSink turns the aftermath watch into sage-agent scheduler
jobs: `python -m ptz_node schedule add` running the holdover_smoke_watch
skill every revisit_min, bounded by the watch window (see agent/README.md).
"""
from __future__ import annotations

import json
import pathlib
import sys
import time


class ActionSink:
    """Interface. Implementations must be non-throwing (log, don't crash)."""

    def arm_continuous(self, t, why): ...
    def revert_baseline(self, t, why): ...
    def start_watch(self, t, sectors, revisit_min, hours): ...
    def stop_watch(self, t, why): ...
    def notify(self, t, title, payload): ...
    def audit(self, record): ...


def _ts(t):
    return time.strftime("%m-%d %H:%M", time.gmtime(t))


class DryRunSink(ActionSink):
    """Prints every intent; optionally appends JSONL audit to a file."""

    def __init__(self, audit_path=None, quiet=False):
        self.audit_path = pathlib.Path(audit_path) if audit_path else None
        self.quiet = quiet
        self.calls = []

    def _say(self, t, msg):
        self.calls.append((t, msg))
        if not self.quiet:
            print(f"[{_ts(t)}Z] {msg}", file=sys.stderr)

    def arm_continuous(self, t, why):
        self._say(t, f"DRY-RUN arm continuous capture ({why}) — would "
                     "submit_plugin_job(continuous sampler) + suspend snapshots")

    def revert_baseline(self, t, why):
        self._say(t, f"DRY-RUN revert to baseline ({why}) — would suspend "
                     "continuous job + resume snapshot samplers")

    def start_watch(self, t, sectors, revisit_min, hours):
        self._say(t, f"DRY-RUN start holdover watch: {len(sectors)} sectors, "
                     f"every {revisit_min:.0f} min for {hours:.0f} h — would "
                     "`ptz_node schedule add` holdover_smoke_watch")

    def stop_watch(self, t, why):
        self._say(t, f"DRY-RUN stop holdover watch ({why})")

    def notify(self, t, title, payload):
        self._say(t, f"DRY-RUN notify: {title}")

    def audit(self, record):
        if self.audit_path:
            with self.audit_path.open("a") as f:
                f.write(json.dumps({"t": record.t, "kind": record.kind,
                                    "detail": record.detail,
                                    "evidence": record.evidence}) + "\n")


class AgentSchedulerSink(DryRunSink):
    """Emits ready-to-run sage-agent scheduler commands for the watch (still
    dry for fleet job control — that part stays gated on permissions)."""

    def start_watch(self, t, sectors, revisit_min, hours):
        args = json.dumps({"sectors": sectors})
        cmd = (f"python -m ptz_node schedule add --kind skill "
               f"--name holdover_smoke_watch --args '{args}' "
               f"--every {int(revisit_min)}m --until +{int(hours)}h")
        self._say(t, f"WATCH CMD: {cmd}")
