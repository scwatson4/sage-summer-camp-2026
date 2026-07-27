"""FlashPoint storm-mode controller (plan F3 / roadmap D2-3).

Tiered, guard-railed state machine that decides when nodes listen hard:
IDLE -> OUTLOOK -> APPROACH -> STORM -> AFTERMATH(72 h holdover) -> IDLE.
Deterministic core (stormmode.py), pluggable action sinks (actions.py),
live feeds (feeds.py), and a replay harness (replay.py) that re-runs the
real Kitten Fire ignition storm through the controller.
"""
from .stormmode import Config, Controller, Inputs, Tier  # noqa: F401
