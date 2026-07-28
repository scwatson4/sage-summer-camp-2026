#!/usr/bin/env python3
"""Phase 3b — synthesis: catalog/REPORT.md.

(a) top-20 storm + recording + fire coincidences, ranked as candidate
    retrospective studies (the Kitten Fire is the benchmark row)
(b) per-node storm-day recording coverage — the snapshot-cadence duty-cycle
    argument, quantified fleet-wide
(c) dry-lightning candidates — storm days with <=2.5 mm at the node gauge
    followed by a WFIGS fire within 72 h and 35 km
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common as C

DRY_MM = 2.5
FIRE_WINDOW_H = 72
FIRE_RADIUS_KM = 35.0
AUDIO_CLIP_S = 10.0          # audio-sampler clip length assumption, stated openly


def _n(x, default="—"):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return default
    return x


def norm(s, invert=False, log=False):
    v = pd.to_numeric(s, errors="coerce").astype("float64")
    if log:
        v = np.log1p(v.clip(lower=0))
    lo, hi = np.nanmin(v), np.nanmax(v)
    if not np.isfinite(lo) or hi <= lo:
        return pd.Series(np.zeros(len(v)), index=s.index)
    z = (v - lo) / (hi - lo)
    z = z.fillna(0.0)
    return 1.0 - z if invert else z


def build_scores(ev: pd.DataFrame) -> pd.DataFrame:
    """Transparent composite: every component is a printed column."""
    e = ev[ev.n_flash_fire_30km > 0].copy()
    if not len(e):
        return e
    e["c_fire_prox"] = norm(e.nearest_flash_to_fire_km, invert=True)
    e["c_node_prox"] = norm(e.dist_node_km, invert=True)
    e["c_storm"] = norm(e.n_flash_fire_30km, log=True)
    e["c_audio"] = norm(e.get("audio_clips_in_window", pd.Series(0, index=e.index)), log=True)
    e["c_imagery"] = norm(
        e.get("image_uploads_in_window", pd.Series(0, index=e.index)).fillna(0)
        + e.get("ptz_frames_in_window", pd.Series(0, index=e.index)).fillna(0), log=True)
    e["c_holdover"] = np.where(e.holdover_gap_h.between(0, 120), 1.0, 0.3)
    e["study_score"] = (0.26 * e.c_fire_prox + 0.16 * e.c_node_prox
                        + 0.16 * e.c_storm + 0.22 * e.c_audio
                        + 0.12 * e.c_imagery + 0.08 * e.c_holdover)
    return e.sort_values("study_score", ascending=False)


def dry_candidates(storm: pd.DataFrame, rain: pd.DataFrame, fires: pd.DataFrame,
                   nodes: pd.DataFrame):
    """Storm days that were dry at the gauge and were followed by a fire."""
    if not len(storm):
        return pd.DataFrame()
    acc = {v: g.set_index("hour")[["lo", "hi"]].sort_index()
           for v, g in rain.groupby("vsn")} if len(rain) else {}

    nl = nodes.set_index("vsn")
    rows = []
    for r in storm.itertuples():
        a = acc.get(r.vsn)
        day0 = pd.Timestamp(r.date)
        day_mm = _rain(a, day0, day0 + pd.Timedelta(days=1))
        w0 = pd.Timestamp(r.first_flash) - pd.Timedelta(hours=3)
        w1 = pd.Timestamp(r.last_flash) + pd.Timedelta(hours=9)
        win_mm = _rain(a, w0, w1)
        best = win_mm if np.isfinite(win_mm) else day_mm
        if not np.isfinite(best) or best > DRY_MM:
            continue
        # a fire within 72 h after the storm and 35 km of the node
        t_end = pd.Timestamp(r.last_flash)
        cand = fires[(fires.discovery >= t_end)
                     & (fires.discovery <= t_end + pd.Timedelta(hours=FIRE_WINDOW_H))]
        if not len(cand):
            continue
        d = C.haversine_km(float(nl.loc[r.vsn, "lat"]), float(nl.loc[r.vsn, "lon"]),
                           cand.lat.to_numpy(), cand.lon.to_numpy())
        m = d <= FIRE_RADIUS_KM
        if not m.any():
            continue
        i = int(np.argmin(np.where(m, d, np.inf)))
        f = cand.iloc[i]
        rows.append(dict(
            vsn=r.vsn, date=day0, n_flashes=r.n_flashes, nearest_km=r.nearest_km,
            storm_hours=r.storm_hours, rain_day_mm=day_mm, rain_storm_mm=win_mm,
            audio_clips=getattr(r, "audio_clips", 0),
            image_frames=getattr(r, "image_frames", 0),
            ptz_frames=getattr(r, "ptz_frames", 0),
            was_recording=getattr(r, "was_recording", False),
            fire_name=f["name"], fire_id=f.fire_id, fire_discovery=f.discovery,
            fire_size_acres=f.size_acres, fire_dist_node_km=float(d[i]),
            lag_h=(f.discovery - t_end).total_seconds() / 3600.0))
    out = pd.DataFrame(rows)
    return out.sort_values(["n_flashes"], ascending=False) if len(out) else out


def _rain(acc, t0, t1):
    if acc is None or not len(acc):
        return float("nan")
    w = acc[(acc.index >= t0) & (acc.index < t1)]
    if not len(w):
        return float("nan")
    return float(max(0.0, w.hi.max() - w.lo.min()))


def md_table(df: pd.DataFrame, cols, headers=None, fmts=None):
    headers = headers or cols
    fmts = fmts or {}
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in df.itertuples():
        cells = []
        for c in cols:
            v = getattr(r, c, None)
            f = fmts.get(c)
            if v is None or (isinstance(v, float) and not np.isfinite(v)):
                cells.append("—")
            elif f:
                try:
                    cells.append(f(v))
                except Exception:
                    cells.append(str(v))
            else:
                cells.append(str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    C.log("Phase 3b — synthesis report")
    ev = pd.read_parquet(C.CATALOG / "fire_events.parquet")
    storm = pd.read_parquet(C.CATALOG / "storm_recording_days.parquet")
    fires = pd.read_parquet(C.CATALOG / "fires_natural.parquet")
    inv = pd.read_parquet(C.CATALOG / "node_inventory.parquet")
    p2 = pd.read_parquet(C.CATALOG / "phase2_nodes.parquet")
    cov = pd.read_parquet(C.CATALOG / "node_coverage.parquet")
    rain = (pd.read_parquet(C.CATALOG / "node_rain_hourly.parquet")
            if (C.CATALOG / "node_rain_hourly.parquet").exists() else pd.DataFrame())
    plan = pd.read_parquet(C.CATALOG / "scan_plan.parquet")
    ranked = build_scores(ev)
    top = ranked.head(args.top)
    dry = dry_candidates(storm[storm.storm_day] if 'storm_day' in storm else storm,
                         rain, fires, inv)

    sd = storm[storm.storm_day] if "storm_day" in storm else storm
    per = (sd.groupby("vsn")
             .agg(storm_days=("storm_day", "size"), recorded=("was_recording", "sum"),
                  audio=("had_audio", "sum"), imagery=("had_imagery", "sum"),
                  flashes=("n_flashes", "sum"), clips=("audio_clips", "sum"),
                  storm_h=("storm_hours", "sum"))
             .reset_index())
    per["pct_recorded"] = 100 * per.recorded / per.storm_days
    per["pct_audio"] = 100 * per.audio / per.storm_days
    per["pct_imagery"] = 100 * per.imagery / per.storm_days
    # Coverage data is day-granular, so clips cannot be attributed to storm
    # hours. Dividing a day's clips by that day's storm duration would inflate
    # the rate by 24/storm_hours. Use the day rate; the samplers run at fixed
    # cadence regardless of weather, so prorating it over the storm is the
    # defensible estimate of what the archive holds from the storm itself.
    per["clips_per_day"] = per.clips / per.storm_days.replace(0, np.nan)
    per["duty_pct"] = 100 * per.clips_per_day * AUDIO_CLIP_S / 86400.0
    per["exp_clips_per_storm"] = per.clips_per_day * (
        per.storm_h / per.storm_days.replace(0, np.nan)) / 24.0
    per = per.merge(p2[["vsn", "n_natural_fires", "nearest_fire_km", "address"]],
                    on="vsn", how="left").sort_values("storm_days", ascending=False)

    kitten = ranked[ranked.fire_name.str.contains("Kitten", case=False, na=False)]
    krank = (int(ranked.index.get_indexer([kitten.index[0]])[0]) + 1) if len(kitten) else None
    # rank by position in the sorted frame
    if len(kitten):
        krank = int(np.nonzero(ranked.fire_id.to_numpy() == kitten.fire_id.iloc[0])[0][0]) + 1

    gran = len(plan) * 4320
    actual_gran = short_days = 0
    ckpt = pathlib.Path(str(C.CKPT / "glm.jsonl"))
    if ckpt.exists():
        import json as _json
        for _l in ckpt.read_text().splitlines():
            if not _l.strip():
                continue
            _d = _json.loads(_l)
            actual_gran += _d.get("granules", 0)
            if _d.get("granules", 0) < 4320:
                short_days += 1
    L = []
    A = L.append
    A("# FlashPoint storm–archive–fire catalog\n")
    A(f"*Generated {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC from public sources only "
      f"(GOES GLM on AWS anonymous, WFIGS, Sage query API). No Sage token was used.*\n")

    A("## What this is\n")
    A("Every co-occurrence of lightning, node recording, and nearby wildfire across the Sage "
      "fleet's fire-country nodes, from first deployment to now. It generalises the M1 Kitten "
      "Fire retrospective from one case to the whole fleet.\n")

    A("## Method and scale\n")
    n_gps = int((inv.lat.notna() & inv.lon.notna()).sum())
    A(f"- **Nodes.** {len(inv)} deployed W/V nodes carry a microphone or camera; {n_gps} of them "
      f"have a GPS fix in the manifest and can be fire-matched. The remaining "
      f"{len(inv) - n_gps} publish data but have no coordinates, so they are inventoried and "
      f"excluded from every distance-based result here.")
    A(f"- **Fires.** {len(fires)} natural-cause WFIGS incidents since 2021 within 35 km of such a node.")
    A(f"- **Lightning.** GOES GLM L2 LCFA flash centroids, quality-flag 0, from the "
      f"best-viewing operational satellite per date and longitude "
      f"(G16 →2025-04-07, G17 →2023-01-10, G18 2022-09-19→, G19 2025-01-15→; boundaries "
      f"verified against the S3 buckets).")
    A(f"- **Scan.** {len(plan):,} satellite-days planned ≈ {gran:,} granules; "
      f"**{actual_gran:,} granules actually existed and were read** "
      f"({100*actual_gran/max(gran,1):.1f}%). Granules were staged through tmpfs and deleted "
      f"per hour, so nothing raw was retained.")
    A(f"- **Archive completeness.** {short_days} of {len(plan):,} satellite-days returned fewer "
      f"than the nominal 4,320 granules. These are real GLM outages, not fetch failures: "
      f"re-listing S3 for a sample of short days returned exactly the reduced count. Storm-day "
      f"counts are therefore a lower bound on those dates.\n")

    A("### The cost lever is dates, not nodes\n")
    A("GLM granules are full-disk, so one download serves every target at once and the scan cost "
      "is `|unique (satellite, date)| × 4320`. Measured on this catalog, trimming the Phase-2 "
      "census from 17 nodes to 12 or to 10 changed the granule count **not at all** "
      "(7,369,920 in every case): the same May–September dates are still required. What did "
      "reduce it was dropping the GOES-**East** track — the eastern mic nodes "
      "(Great Lakes, Dakotas, central Texas) are the only reason a second satellite's dates are "
      "needed — which took Phase 2 from 7.37M to 3.10M granules, under the 4M ceiling. "
      "Planning Phase 1 and Phase 2 as one union saved a further 2.14M granules (~1.5 h) versus "
      "scanning them separately.\n")

    A("### The manifest is not the archive\n")
    aud_by_node = (cov[cov.bucket == "audio"].groupby("vsn").n_uploads.sum()
                   if "bucket" in cov.columns else pd.Series(dtype=float))
    inv2 = inv.copy()
    inv2["records_audio"] = inv2.vsn.map(aud_by_node).fillna(0) > 0
    claim = int(inv2.mic.sum())
    real = int(inv2.records_audio.sum())
    ghost = sorted(inv2[inv2.mic & ~inv2.records_audio].vsn)
    hidden = sorted(inv2[~inv2.mic & inv2.records_audio].vsn)
    A(f"Selecting \"microphone-equipped\" nodes from the manifest would have been wrong in both "
      f"directions. **{claim} nodes advertise a Microphone capability, but only {real} have ever "
      f"published a single audio clip.** {len(ghost)} advertise a microphone and record nothing; "
      f"{len(hidden)} publish audio with no microphone listed at all "
      f"({', '.join(hidden)}).\n")
    A(f"This matters for the census, not just for tidiness. **V040 (Bear Mt., OR) and V041 "
      f"(Harness Mt., OR) rank #2 and #3 in the fleet by natural-fire proximity — 55 and 53 "
      f"fires within 35 km — and both genuinely record audio, but neither lists a microphone.** "
      f"They are included here on the strength of the archive. Conversely V015 and V023 list "
      f"microphones and have never recorded a second of audio, which is why their audio columns "
      f"below are zero. **W021 (Fort Collins, CO) also records audio with no microphone listed, "
      f"contradicting the project's standing note that Colorado has zero microphones** — it has "
      f"{int(aud_by_node.get('W021', 0)):,} audio uploads and 19 natural-cause fires within "
      f"35 km. It is *not* in the census below because at 105.1°W it falls on the GOES-East side "
      f"of the 106.2°W viewing crossover, and adding it would pull in a whole second satellite "
      f"track: 500 more satellite-days, ~2.16M granules, ~51 min. That is the single highest-value "
      f"extension to this catalog and it is a deliberate, costed omission.\n")

    A("### Validation against M1\n")
    A("The scanner was checked against the independently derived Kitten Fire result before any "
      "bulk run: the nearest GLM flash to the fire point during the 2025-07-02 22–00 UT ignition "
      "storm comes out at **3.13 km** (M1 documented 3.1 km). The rain module reproduces M1's "
      "dry/wet split for the same node — 0.16 mm across the dry nocturnal storm of 1 July "
      "(M1: 0.0 mm) and 2.01 mm across the 2 July evening storm (M1: 2.2 mm).\n")

    # ---------------- (a) -------------------------------------------------
    A(f"## (a) Top {len(top)} storm + recording + fire coincidences\n")
    A("Ranked as candidate retrospective studies. `study_score` is a transparent weighted blend "
      "of flash-to-fire proximity (0.26), archived audio (0.22), fire-to-node distance (0.16), "
      "storm size (0.16), archived imagery (0.12) and an attributable holdover gap (0.08); every "
      "component is shown so the ranking can be argued with.\n")
    if krank:
        k = kitten.iloc[0]
        A(f"**Benchmark check — the Kitten Fire ranks #{krank}** of "
          f"{len(ranked)} scored (fire, node) pairs: nearest flash "
          f"{k.nearest_flash_to_fire_km:.2f} km, {int(k.n_flash_fire_30km)} flashes ≤30 km, "
          f"{int(k.get('audio_clips_in_window', 0))} audio clips and "
          f"{int(k.get('ptz_frames_in_window', 0))} PTZ frames archived in the window.\n")
    else:
        A("*(Kitten Fire row not present — check the fire inventory.)*\n")
    A(md_table(top, ["fire_name", "discovery", "state", "vsn", "dist_node_km",
                     "nearest_flash_to_fire_km", "n_flash_fire_30km", "holdover_gap_h",
                     "audio_clips_in_window", "image_uploads_in_window",
                     "ptz_frames_in_window", "size_acres", "study_score"],
               ["fire", "discovered (UTC)", "st", "node", "node km", "flash→fire km",
                "flashes ≤30km", "holdover h", "audio", "images", "ptz", "acres", "score"],
               {"discovery": lambda v: f"{pd.Timestamp(v):%Y-%m-%d %H:%M}",
                "dist_node_km": lambda v: f"{v:.1f}",
                "nearest_flash_to_fire_km": lambda v: f"{v:.2f}",
                "holdover_gap_h": lambda v: f"{v:.1f}",
                "size_acres": lambda v: f"{v:,.1f}",
                "study_score": lambda v: f"{v:.3f}"}))
    A("")

    # ---------------- (b) -------------------------------------------------
    A("## (b) Per-node storm-day recording coverage — the duty-cycle argument\n")
    lit = ev[ev.n_flash_fire_30km > 0]
    A(f"Across the census nodes there are **{len(sd):,} storm days** "
      f"(≥10 GLM flashes within 30 km of the node, May–September, after that node's deployment). "
      f"The archive captured *something* on "
      f"{100*sd.was_recording.mean():.1f}% of them and audio on "
      f"{100*sd.had_audio.mean():.1f}%.\n")
    A(md_table(per, ["vsn", "address", "storm_days", "flashes", "pct_recorded", "pct_audio",
                     "pct_imagery", "clips", "clips_per_day", "duty_pct", "exp_clips_per_storm",
                     "n_natural_fires", "nearest_fire_km"],
               ["node", "site", "storm days", "flashes", "% any media", "% audio",
                "% imagery", "clips", "clips/day", "audio duty %", "exp clips/storm", "nat. fires",
                "nearest fire km"],
               {"pct_recorded": lambda v: f"{v:.0f}", "pct_audio": lambda v: f"{v:.0f}",
                "pct_imagery": lambda v: f"{v:.0f}",
                "clips_per_day": lambda v: f"{v:.0f}",
                "exp_clips_per_storm": lambda v: f"{v:.0f}",
                "duty_pct": lambda v: f"{v:.1f}",
                "nearest_fire_km": lambda v: f"{v:.1f}",
                "flashes": lambda v: f"{int(v):,}", "clips": lambda v: f"{int(v):,}",
                "address": lambda v: " ".join(str(v).split())[:26]}))
    A("")
    # --- the seasonal-scheduling finding -----------------------------------
    aud = cov[cov.bucket == "audio"] if "bucket" in cov.columns else cov.iloc[0:0]
    rows = []
    for v in per.vsn:
        a = aud[aud.vsn == v]
        s = sd[sd.vsn == v]
        if not len(s):
            continue
        adays = set(pd.to_datetime(a.day).dt.date) if len(a) else set()
        sdays = set(pd.to_datetime(s.date).dt.date)
        amonths = {d.month for d in adays}
        rows.append(dict(
            vsn=v,
            audio_first=(min(adays).isoformat() if adays else None),
            audio_last=(max(adays).isoformat() if adays else None),
            audio_days=len(adays),
            in_season_audio_days=sum(1 for d in adays if 5 <= d.month <= 9),
            storm_days=len(sdays),
            storm_days_with_audio=len(adays & sdays),
            audio_months=",".join(str(m) for m in sorted(amonths)) if amonths else "—"))
    seas = pd.DataFrame(rows)
    A("### Two of the most fire-exposed microphones ran outside storm season\n")
    A("Before duty cycle enters the argument there is a scheduling problem. Most nodes run "
      "`audio-sampler` year-round, but it follows no storm-season logic, and where it was "
      "scheduled narrowly it landed in the wrong half of the year:\n")
    A(md_table(seas, ["vsn", "audio_first", "audio_last", "audio_days",
                      "in_season_audio_days", "audio_months", "storm_days",
                      "storm_days_with_audio"],
               ["node", "audio from", "audio to", "audio days", "of which May–Sep",
                "months active", "storm days", "storm days WITH audio"]))
    A("")
    worst = seas[(seas.audio_days > 0) & (seas.storm_days_with_audio == 0)]
    if len(worst):
        A(f"**{', '.join(worst.vsn)} recorded audio on {int(worst.audio_days.sum()):,} days and "
          f"caught not one of their {int(worst.storm_days.sum())} storm days.** V040 (Bear Mt.) "
          f"and V041 (Harness Mt.) are the fleet's #2 and #3 nodes by natural-fire proximity, and "
          f"their microphones ran from late September through February — autumn and winter, while "
          f"every storm day they experienced fell in May–September. The most fire-exposed "
          f"audio-capable nodes in the fleet listened in exactly the wrong months. No amount of "
          f"detector work recovers a signal that was never sampled; this is a scheduling fix, and "
          f"it is free.\n")

    A(f"**The duty-cycle problem, quantified.** `audio duty %` is the fraction of storm wall-clock "
      f"actually inside an archived clip, at the measured upload cadence and a "
      f"{AUDIO_CLIP_S:.0f}-second clip length (the one assumption here — clip length is not "
      f"readable without file access). A node can sit under a storm all night and retain only a "
      f"few percent of it. M1 supplies the independent check: of the 219 GLM flashes within "
      f"25 km of the Kitten fire point during the ignition storm, satellite-anchored "
      f"re-listening recovered **22 flash→bang arrivals** in the archived clips — about 10%, "
      f"the same order as the cadence predicts. Snapshot sampling is why single-modality "
      f"retrospective detection fails, and it is the quantitative case for storm mode: the "
      f"missing signal is not faint, it is *not recorded*.\n")

    # ---------------- (c) -------------------------------------------------
    A("## (c) Dry-lightning candidates\n")
    A(f"Storm days with ≤{DRY_MM} mm at the node's own gauge, followed within "
      f"{FIRE_WINDOW_H} h by a natural-cause WFIGS fire within {FIRE_RADIUS_KM:g} km of the "
      f"node. `rain_storm_mm` is measured across the storm window (first flash −3 h to last "
      f"flash +9 h), which separates a dry nocturnal storm from a wet day far better than a "
      f"UTC-day total.\n")
    if len(dry):
        A(f"**{len(dry)} candidates** across {dry.vsn.nunique()} nodes.\n")
        A(md_table(dry.head(25),
                   ["vsn", "date", "n_flashes", "nearest_km", "rain_storm_mm", "rain_day_mm",
                    "audio_clips", "ptz_frames", "fire_name", "fire_dist_node_km", "lag_h",
                    "fire_size_acres"],
                   ["node", "storm day", "flashes", "nearest km", "storm rain mm",
                    "day rain mm", "audio", "ptz", "fire", "fire km", "lag h", "acres"],
                   {"date": lambda v: f"{pd.Timestamp(v):%Y-%m-%d}",
                    "nearest_km": lambda v: f"{v:.1f}",
                    "rain_storm_mm": lambda v: f"{v:.2f}",
                    "rain_day_mm": lambda v: f"{v:.2f}",
                    "fire_dist_node_km": lambda v: f"{v:.1f}",
                    "lag_h": lambda v: f"{v:.1f}",
                    "fire_size_acres": lambda v: f"{v:,.1f}"}))
    else:
        A("No candidates met all three conditions with the rain data available.\n")
    A("")

    # ---------------- files ------------------------------------------------
    A("## Catalog files\n")
    for f, desc in [
        ("node_inventory.parquet", "deployed W/V mic/cam nodes: capabilities, GPS, first data"),
        ("node_coverage.parquet", "uploads per (node, task, day) — the archive record"),
        ("node_coverage_monthly.parquet", "the same rolled up per month"),
        ("fires_all.parquet", "every WFIGS incident within 35 km of a node since 2021"),
        ("fires_natural.parquet", "the natural-cause subset that anchors Phase 1"),
        ("fire_node_pairs.parquet", "(fire, node) pairs within 35 km with distances"),
        ("fire_events.parquet", "Phase 1: one row per (fire, node) with GLM + archive summary"),
        ("fire_flashes.parquet", "Phase 1: flash-level detail inside the fire windows"),
        ("storm_recording_days.parquet", "Phase 2: node-days with lightning ≤30 km + archive"),
        ("node_storm_coverage.parquet", "Phase 2: per-node storm-day capture rates"),
        ("node_rain_hourly.parquet", "hourly cumulative rain traces for the census nodes"),
        ("scan_plan.parquet / scan_targets.parquet", "exact scan units and targets (reproducible)"),
    ]:
        if (C.CATALOG / f.split(" /")[0]).exists() or "/" in f:
            A(f"- `{f}` — {desc}")
    A("")

    A("## Caveats\n")
    A("- GLM detects total lightning optically from geostationary orbit with 8–14 km pixels and "
      "reduced efficiency by day and toward the limb; it under-detects cloud-to-ground strokes, "
      "which are the fire-starting ones. Distances here are flash-centroid to point, not stroke "
      "locations. NLDN/STRIKEnet remains the arbiter for metre-scale claims.")
    A("- WFIGS discovery time is when a fire was *reported*, not when it ignited; the holdover "
      "gap is therefore an upper bound on the true smouldering interval.")
    A(f"- {int((fires.coord_source=='geometry').sum())} of {len(fires)} fire points fall back to "
      "the incident geometry because the reported initial point was missing or implausibly far "
      "from it (>25 km); those rows are flagged in `coord_source`.")
    A("- Rain comes from the node's own gauge, which is a point measurement — a dry gauge does "
      "not prove the strike point was dry.")
    A("- Nodes without GPS in the manifest cannot be fire-matched and are excluded from Phase 1.")
    A("- Phase 0 could not retrieve 76 (node, task, month) units, **all of them `mobotix-scan*` "
      "tasks** — those queries return responses large enough to break the connection, and "
      "`sage_data_client` calls `urlopen` with no timeout, so they hang rather than fail. The "
      "affected census node is W084 (thermal `mobotix-scan`, 2023-05 → 2024-11); its "
      "audio-sampler, imagesampler and ptz-yolo coverage is complete, so the audio columns above "
      "are unaffected and only W084's thermal-scan frame counts are understated.")
    A("- Storm days are counted from GLM alone. A node may have been under a storm that GLM "
      "missed (daytime, weak optical signal, limb geometry), so the capture percentages in (b) "
      "are, if anything, optimistic about how much the archive holds.")

    (C.CATALOG / "REPORT.md").write_text("\n".join(L) + "\n")
    C.log(f"wrote catalog/REPORT.md ({len('\n'.join(L))} chars)")
    if len(ranked):
        ranked.to_parquet(C.CATALOG / "study_candidates.parquet", index=False)
    if len(dry):
        dry.to_parquet(C.CATALOG / "dry_lightning_candidates.parquet", index=False)
    C.log("PHASE 3 DONE — safe to shelve")


if __name__ == "__main__":
    main()
