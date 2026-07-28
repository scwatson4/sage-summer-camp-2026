"""The storm-mode state machine — deterministic, auditable, guard-railed.

Tiers (plan F3):
  IDLE      baseline snapshot sampling
  OUTLOOK   elevated convective/fire-weather outlook -> pre-armed
  APPROACH  storm evidence approaching (cells within radius, regional
            strikes, local pressure fall + wind shift) -> ARM: continuous
            ring-buffer capture requested
  STORM     first LOCAL flash or thunder -> full storm mode
  AFTERMATH strike log non-empty and storm exited -> 72 h holdover watch
            (PTZ smoke patrol on strike sectors), then revert

Design rules:
- The transition engine is a pure function of (state, inputs, config, now):
  no I/O, no clocks, no network — everything testable and replayable.
- Every transition and every action is emitted as an audit record with the
  evidence that caused it. The audit log IS a deliverable (plan section 10).
- Guardrails: daily continuous-capture budget, hard cap on storm hours,
  auto-revert timeouts at every tier, hysteresis so flapping inputs can't
  thrash samplers. A guardrail firing is itself an audited event.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Tier(IntEnum):
    IDLE = 0
    OUTLOOK = 1
    APPROACH = 2
    STORM = 3
    AFTERMATH = 4


@dataclass
class Config:
    # approach triggers
    approach_cell_km: float = 100.0     # storm cell within this arms the node
    approach_strikes: int = 3           # regional strikes (<=100 km, ~5 min)
    pressure_drop_hpa_3h: float = 2.0   # local pressure fall trigger...
    gust_ms: float = 10.0               # ...when paired with gusty wind
    # storm entry/exit
    storm_quiet_min: float = 30.0       # hysteresis: quiet this long to exit
    # aftermath
    aftermath_hours: float = 72.0
    watch_revisit_min: float = 20.0
    # guardrails
    max_storm_hours: float = 6.0        # hard cap per storm event
    max_continuous_hours_day: float = 10.0  # daily continuous-capture budget
    approach_timeout_hours: float = 4.0     # armed but nothing came -> revert
    outlook_timeout_hours: float = 24.0     # outlook expires daily


@dataclass
class Inputs:
    """One evaluation step's evidence. All optional-with-defaults so a feed
    outage degrades to 'no evidence' instead of crashing the loop."""
    t: float                                  # epoch seconds
    outlook_elevated: bool = False            # NWS/SPC convective or fire wx
    nearest_cell_km: float | None = None      # Xweather stormcells
    regional_strikes: int = 0                 # Xweather/Blitzortung <=100 km
    pressure_drop_hpa_3h: float = 0.0         # node's own barometer
    gust_ms: float = 0.0                      # node's own anemometer
    local_flash: bool = False                 # detectors.flash event now
    local_thunder: bool = False               # detectors.thunder pass now
    strikes: list = field(default_factory=list)  # localized strikes for the
    # aftermath watch: [{lat, lon, time_epoch, risk}]


@dataclass
class Audit:
    t: float
    kind: str          # transition | action | guardrail
    detail: str
    evidence: dict


class Controller:
    def __init__(self, cfg: Config, sink, node_latlon=None, t0: float = 0.0):
        """sink: actions.ActionSink — receives arm/revert/watch/notify calls.
        node_latlon: (lat, lon) for turning strikes into watch sectors."""
        self.cfg = cfg
        self.sink = sink
        self.node_latlon = node_latlon
        self.tier = Tier.IDLE
        self.tier_since = t0
        self.last_activity = t0
        self.continuous_since: float | None = None
        self.continuous_used_s = 0.0
        self.budget_day: int | None = None
        self.strike_log: list = []
        self.audit: list[Audit] = []

    # ------------------------------------------------------------- helpers
    def _log(self, t, kind, detail, **evidence):
        rec = Audit(t, kind, detail, evidence)
        self.audit.append(rec)
        self.sink.audit(rec)

    def _goto(self, t, tier: Tier, why: str, **evidence):
        self._log(t, "transition", f"{self.tier.name} -> {tier.name}: {why}",
                  **evidence)
        self.tier = tier
        self.tier_since = t

    def _arm_continuous(self, t, why):
        if self.continuous_since is None:
            day = int(t // 86400)
            if self.budget_day != day:
                self.budget_day, self.continuous_used_s = day, 0.0
            if self.continuous_used_s >= self.cfg.max_continuous_hours_day * 3600:
                self._log(t, "guardrail",
                          "daily continuous-capture budget exhausted; NOT arming",
                          used_h=round(self.continuous_used_s / 3600, 2))
                return False
            self.continuous_since = t
            self.sink.arm_continuous(t, why)
            self._log(t, "action", "arm continuous capture", why=why)
        return True

    def _revert_continuous(self, t, why):
        if self.continuous_since is not None:
            self.continuous_used_s += t - self.continuous_since
            self.continuous_since = None
            self.sink.revert_baseline(t, why)
            self._log(t, "action", "revert to baseline sampling", why=why,
                      used_h=round(self.continuous_used_s / 3600, 2))

    # ---------------------------------------------------------------- step
    def step(self, x: Inputs):
        """Evaluate one input snapshot. Call at any cadence (1-5 min live;
        replay uses fixture cadence)."""
        c, t = self.cfg, x.t
        approach_evidence = (
            (x.nearest_cell_km is not None and x.nearest_cell_km <= c.approach_cell_km)
            or x.regional_strikes >= c.approach_strikes
            or (x.pressure_drop_hpa_3h >= c.pressure_drop_hpa_3h
                and x.gust_ms >= c.gust_ms))
        local_evidence = x.local_flash or x.local_thunder
        if local_evidence or approach_evidence:
            self.last_activity = t
        for s in x.strikes:
            if s not in self.strike_log:
                self.strike_log.append(s)

        if self.tier == Tier.IDLE:
            if approach_evidence:  # storm evidence outranks the forecast
                self._goto(t, Tier.APPROACH, "storm evidence from idle",
                           cell_km=x.nearest_cell_km,
                           strikes=x.regional_strikes)
                self._arm_continuous(t, "approach evidence")
            elif x.outlook_elevated:
                self._goto(t, Tier.OUTLOOK, "elevated outlook")

        elif self.tier == Tier.OUTLOOK:
            if approach_evidence:
                self._goto(t, Tier.APPROACH, "approach evidence",
                           cell_km=x.nearest_cell_km,
                           strikes=x.regional_strikes,
                           dp=x.pressure_drop_hpa_3h, gust=x.gust_ms)
                self._arm_continuous(t, "approach evidence")
            elif not x.outlook_elevated and \
                    t - self.tier_since > c.outlook_timeout_hours * 3600:
                self._goto(t, Tier.IDLE, "outlook expired")

        elif self.tier == Tier.APPROACH:
            if local_evidence:
                self._goto(t, Tier.STORM, "first local flash/thunder",
                           flash=x.local_flash, thunder=x.local_thunder)
                self.sink.notify(t, "storm-mode entered",
                                 {"tier": "STORM", "node": self.node_latlon})
            elif t - self.last_activity > c.approach_timeout_hours * 3600:
                self._log(t, "guardrail", "approach timed out with no storm")
                self._revert_continuous(t, "approach timeout")
                self._goto(t, Tier.OUTLOOK if x.outlook_elevated else Tier.IDLE,
                           "approach timeout auto-revert")

        elif self.tier == Tier.STORM:
            stormed_h = (t - self.tier_since) / 3600
            quiet_min = (t - self.last_activity) / 60
            if stormed_h >= c.max_storm_hours:
                self._log(t, "guardrail",
                          f"max storm hours ({c.max_storm_hours}) reached")
            if quiet_min >= c.storm_quiet_min or stormed_h >= c.max_storm_hours:
                self._revert_continuous(t, "storm exited")
                if self.strike_log:
                    self._goto(t, Tier.AFTERMATH,
                               f"storm quiet {quiet_min:.0f} min; "
                               f"{len(self.strike_log)} strike(s) logged")
                    self._start_watch(t)
                else:
                    self._goto(t, Tier.OUTLOOK if x.outlook_elevated else Tier.IDLE,
                               "storm quiet, no localized strikes")

        elif self.tier == Tier.AFTERMATH:
            if local_evidence:  # storm came back
                self._goto(t, Tier.STORM, "renewed local activity")
                self._arm_continuous(t, "storm re-entry")
            else:
                newest = max((s["time_epoch"] for s in self.strike_log),
                             default=self.tier_since)
                if t - newest > c.aftermath_hours * 3600:
                    self.sink.stop_watch(t, "holdover window expired")
                    self._log(t, "action", "stop holdover watch",
                              hours=c.aftermath_hours)
                    self.strike_log.clear()
                    self._goto(t, Tier.OUTLOOK if x.outlook_elevated else Tier.IDLE,
                               "aftermath complete")
        return self.tier

    def _start_watch(self, t):
        sectors = []
        if self.node_latlon:
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                                   / "agent" / "skills"))
            from strike_sectors import sectors_for_node
            sectors = sectors_for_node(self.node_latlon[0], self.node_latlon[1],
                                       self.strike_log, now_epoch=t)
        self.sink.start_watch(t, sectors,
                              revisit_min=self.cfg.watch_revisit_min,
                              hours=self.cfg.aftermath_hours)
        self._log(t, "action",
                  f"start holdover watch: {len(sectors)} sector(s), "
                  f"{self.cfg.aftermath_hours:.0f} h",
                  sectors=sectors[:5])
