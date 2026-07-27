#!/usr/bin/env python3
"""FlashPoint dashboard — lightning localization & wildfire ignition watch.

Run from the flashpoint/ directory:
    streamlit run dashboard/app.py

Views:
  🗺 Map          — fleet + case nodes, nearby natural-cause fires, strike results
  🖼 Image compare — A/B + filmstrip comparison across nodes and times, with a
                     luminance timeline and flash-candidate markers
  ⚡ Strike sync   — synchronized image-luminance / audio-energy / met timelines,
                     clip inspector (waveform, spectrogram, playback), the
                     flash-to-bang range engine and multi-node strike localization
  📓 Case notes    — the story, the fires, and the archive census for each case

Data: listings and met telemetry are public; media files need portal
credentials (SAGE_USER / SAGE_TOKEN) — or use the synthetic demo storm, which
needs nothing. All times UTC.
"""
import datetime
import pathlib
import sys

import altair as alt
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from fp import analysis, demo, geo, palette as pal, sage  # noqa: E402

alt.data_transformers.disable_max_rows()

st.set_page_config(page_title="FlashPoint — Lightning & Wildfire Watch",
                   page_icon="⚡", layout="wide")

MAX_IMG_DEFAULT = 150
MAX_AUDIO_DEFAULT = 60


# ---------------------------------------------------------------- cached IO

@st.cache_data(ttl=900, show_spinner=False)
def q_uploads(vsn, task_regex, start_iso, end_iso):
    return sage.list_uploads(vsn, task_regex, start_iso, end_iso)


@st.cache_data(ttl=900, show_spinner=False)
def q_met(vsn, name_regex, start_iso, end_iso):
    return sage.met_series(vsn, name_regex, start_iso, end_iso)


@st.cache_data(show_spinner=False)
def luminance_of(path, mtime):
    return analysis.mean_luminance(path)


@st.cache_data(show_spinner=False)
def clip_summary(path, mtime):
    y, sr = analysis.load_audio(path)
    feats = analysis.clip_features(y, sr)
    feats["onset_s"] = analysis.onset_time(y, sr)
    return feats


@st.cache_data(show_spinner=False)
def load_nodes():
    return sage.load_nodes()


@st.cache_data(show_spinner=False)
def load_cases():
    return sage.load_cases()


@st.cache_resource(show_spinner="Generating synthetic demo storm (first run only)…")
def demo_manifest():
    return demo.generate(sage.load_nodes())


# ---------------------------------------------------------------- helpers

def utc(ts):
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def fmt_t(ts):
    return utc(ts).strftime("%m-%d %H:%M:%S")


def configured(chart):
    """Apply chart chrome (must be the last, top-level call — configure_* is
    illegal on subcharts)."""
    return (chart.configure_axis(gridColor=pal.GRID, domainColor=pal.GRID,
                                 labelColor=pal.INK_2, titleColor=pal.INK_2)
            .configure_view(stroke=None)
            .configure_legend(labelColor=pal.INK_2, titleColor=pal.INK_2))


def styled(chart, height=180):
    return configured(chart.properties(height=height))


def for_chart(df, col="timestamp"):
    """Copy with the time column as tz-naive UTC wall-clock. Vega-Lite renders
    naive datetimes verbatim (no browser-timezone shift), so this keeps every
    axis honest to the app's 'all times UTC' promise regardless of viewer TZ."""
    d = df.copy()
    if col in d.columns:
        s = pd.to_datetime(d[col], utc=True)
        d[col] = s.dt.tz_convert("UTC").dt.tz_localize(None)
    return d


def creds():
    user = st.session_state.get("sage_user", "")
    token = st.session_state.get("sage_token", "")
    return user, token


def fetch_media_rows(rows, label, cap):
    """Download (or reuse cached) media for listing rows -> adds 'path'.

    Returns (df_with_paths, auth_error_message_or_None). Demo/local rows that
    already carry a path pass straight through.
    """
    if "path" in rows.columns and rows["path"].notna().all():
        return rows, None
    user, token = creds()
    out, err = [], None
    todo = rows
    if len(todo) > cap:
        step = len(todo) / cap
        todo = todo.iloc[[int(i * step) for i in range(cap)]]
    prog = st.progress(0.0, text=f"Fetching {len(todo)} {label} files…")
    consecutive = 0
    for k, (_, r) in enumerate(todo.iterrows()):
        try:
            p = sage.fetch_media(r["url"], user, token)
            out.append({**r.to_dict(), "path": str(p)})
            consecutive = 0
        except sage.SageAuthError as e:
            err = str(e)
            break
        except Exception as e:  # single bad file shouldn't kill the batch…
            consecutive += 1
            st.toast(f"skip {r.get('filename', '?')}: {e}", icon="⚠️")
            if consecutive >= 3:  # …but a dead network/storage host should
                err = (f"3 downloads in a row failed (last: {e}). Storage looks "
                       "unreachable from here — check network/credentials, use "
                       "files pre-downloaded with scripts/fetch_case_media.py "
                       "(Offline mode), or the Demo storm case.")
                break
        prog.progress((k + 1) / len(todo))
    prog.empty()
    df = pd.DataFrame(out)
    return df, err


def need_creds_warning(err):
    st.warning(
        f"**Couldn't download media.** {err}\n\n"
        "Media files are protected — enter portal credentials in the sidebar "
        "(they stay in this session only), or pre-download with "
        "`scripts/fetch_case_media.py` and flip on **Offline mode**, or switch "
        "to the **Demo storm** case which needs nothing.", icon="🔒")


def luminance_frame(media_df):
    rows = []
    for _, r in media_df.iterrows():
        p = pathlib.Path(r["path"])
        if not p.exists():
            continue
        try:
            rows.append({"timestamp": r["timestamp"], "vsn": r.get("vsn", ""),
                         "path": str(p),
                         "luma": luminance_of(str(p), p.stat().st_mtime)})
        except Exception:
            continue
    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True) \
        if rows else pd.DataFrame(columns=["timestamp", "vsn", "path", "luma"])


def audio_frame(media_df):
    rows = []
    for _, r in media_df.iterrows():
        p = pathlib.Path(r["path"])
        if not p.exists():
            continue
        try:
            f = clip_summary(str(p), p.stat().st_mtime)
        except Exception:
            continue
        rows.append({"timestamp": r["timestamp"], "vsn": r.get("vsn", ""),
                     "path": str(p), **f})
    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True) \
        if rows else pd.DataFrame()


def mark_flashes(ldf):
    """Flag flash-candidate frames per node (cameras differ in exposure and
    simultaneous cross-node flashes would defeat a pooled median baseline)."""
    ldf = ldf.copy()
    ldf["flash"] = False
    group_key = ldf["vsn"] if "vsn" in ldf.columns else pd.Series(0, index=ldf.index)
    for _, g in ldf.groupby(group_key):
        idx = analysis.flash_candidates(g.timestamp, g.luma)
        ldf.loc[g.index[idx], "flash"] = True
    return ldf


def window_slider(case, key):
    t0 = utc(case["start"]).to_pydatetime().replace(tzinfo=None)
    t1 = utc(case["end"]).to_pydatetime().replace(tzinfo=None)
    lo, hi = st.slider("Time window (UTC)", min_value=t0, max_value=t1,
                       value=(t0, t1), step=datetime.timedelta(minutes=15),
                       format="MM-DD HH:mm", key=key)
    return utc(lo), utc(hi)


def case_nodes(case, nodes_df):
    vsns = case.get("nodes") or [case["vsn"]]
    return nodes_df[nodes_df.vsn.isin(vsns)].reset_index(drop=True)


def case_media_listing(case, tasks, lo, hi):
    """Unified media listing for a case: demo manifest, local files, or live API."""
    if case["id"] == "demo-storm":
        df = demo.media_index(demo_manifest())
        df = df[df.task.isin(tasks)]
        return df[(df.timestamp >= lo) & (df.timestamp <= hi)].reset_index(drop=True)
    frames = []
    if st.session_state.get("offline"):
        idx = sage.local_media_index()
        if len(idx):
            idx = idx[(idx.vsn.isin(case.get("nodes") or [case["vsn"]])) | (idx.vsn == "")]
            idx = idx[idx.task.str.contains("|".join(tasks), regex=True, na=False)]
            frames.append(idx.rename(columns={}))
    else:
        for vsn in case.get("nodes") or [case["vsn"]]:
            try:
                df = q_uploads(vsn, "|".join(tasks), lo.isoformat(), hi.isoformat())
                df["vsn"] = vsn
                frames.append(df)
            except Exception as e:
                st.warning(f"Sage query failed for {vsn}: {e}. "
                           "Check network, or enable Offline mode.", icon="🌐")
    if not frames:
        return pd.DataFrame(columns=["timestamp", "vsn", "task", "url", "filename"])
    out = pd.concat(frames, ignore_index=True)
    return out[(out.timestamp >= lo) & (out.timestamp <= hi)] \
        .sort_values("timestamp").reset_index(drop=True)


def get_case_temp(case, when):
    if case["id"] == "demo-storm":
        return demo_manifest()["temp_c"]
    if st.session_state.get("offline"):
        return None
    return sage.temperature_at(case["vsn"], when)


# ---------------------------------------------------------------- map layers

def node_layer(df, dim=False):
    d = df.copy()
    d["tooltip"] = d.apply(
        lambda r: f"{r.vsn} — {'🎤' if r.mic else ''}{'📷' if r.cam else ''} {r.address[:60]}",
        axis=1)
    return pdk.Layer(
        "ScatterplotLayer", d, get_position=["lon", "lat"],
        get_fill_color=pal.MAP_NODE_DIM if dim else pal.MAP_NODE,
        get_radius=180 if dim else 350, radius_min_pixels=3 if dim else 6,
        radius_max_pixels=30, pickable=True, stroked=False)


def fire_layer(fires):
    if not fires:
        return None
    d = pd.DataFrame(fires)
    d["radius"] = 250 + 120 * np.sqrt(d["size_ac"].clip(lower=0.05))
    d["tooltip"] = d.apply(
        lambda r: (f"🔥 {r['name']} — {r['size_ac']:.1f} ac, natural cause; "
                   f"discovered {r['discovered'][:16]}Z; {r['dist_km']} km from node"),
        axis=1)
    return pdk.Layer("ScatterplotLayer", d, get_position=["lon", "lat"],
                     get_fill_color=pal.MAP_FIRE, get_radius="radius",
                     radius_min_pixels=5, radius_max_pixels=40, pickable=True)


def rings_layers(board, nodes_df):
    """Range rings + estimate + ellipse layers from the strike board."""
    layers, est = [], None
    rings = []
    for m in board:
        n = nodes_df[nodes_df.vsn == m["vsn"]]
        if not len(n):
            continue
        la, lo = float(n.iloc[0].lat), float(n.iloc[0].lon)
        rings.append({"path": geo.ring_path(la, lo, m["range_m"]),
                      "tooltip": f"{m['vsn']} range {m['range_m']/1000:.2f} ± {m['sigma_m']/1000:.2f} km"})
        for r in (m["range_m"] - m["sigma_m"], m["range_m"] + m["sigma_m"]):
            if r > 100:  # ±1σ envelope rings (thin), share the parent's tooltip
                rings.append({"path": geo.ring_path(la, lo, r), "thin": True,
                              "tooltip": f"{m['vsn']} range ±1σ edge"})
    if rings:
        d = pd.DataFrame(rings)
        d["w"] = [1 if r.get("thin") else 3 for r in rings]
        layers.append(pdk.Layer("PathLayer", d, get_path="path",
                                get_color=pal.MAP_RING, get_width="w",
                                width_units="pixels", pickable=True))
    # localization
    usable = []
    for m in board:
        n = nodes_df[nodes_df.vsn == m["vsn"]]
        if len(n):
            usable.append((float(n.iloc[0].lat), float(n.iloc[0].lon),
                           m["range_m"], m["sigma_m"]))
    if len(usable) >= 2:
        lat0 = np.mean([u[0] for u in usable]); lon0 = np.mean([u[1] for u in usable])
        anchors = [geo.to_xy(u[0], u[1], lat0, lon0) for u in usable]
        est = geo.trilaterate(anchors, [u[2] for u in usable], [u[3] for u in usable])
        if est:
            ela, elo = geo.to_latlon(*est["xy"], lat0, lon0)
            est["lat"], est["lon"] = ela, elo
            finite = np.isfinite([est["semi_major_m"], est["semi_minor_m"]]).all()
            if finite and not est.get("degenerate"):  # a bounded uncertainty ellipse
                ell = geo.ellipse_polygon(ela, elo, max(est["semi_major_m"], 30),
                                          max(est["semi_minor_m"], 30), est["angle_deg"])
                layers.append(pdk.Layer("PolygonLayer", pd.DataFrame([{"poly": ell}]),
                                        get_polygon="poly", get_fill_color=pal.MAP_ELLIPSE,
                                        get_line_color=[11, 11, 11, 160], get_line_width=2,
                                        line_width_units="pixels"))
            gdop_txt = "∞" if not np.isfinite(est["gdop"]) else f"{est['gdop']:.1f}"
            err_txt = ("unbounded" if not finite
                       else f"±{est['semi_major_m']:.0f} m")
            pts = [{"lat": ela, "lon": elo,
                    "tooltip": (f"⚡ strike estimate {err_txt} "
                                f"(GDOP {gdop_txt}, {est['n_nodes']} nodes)")}]
            for ax, ay in est["alternates"] if est["bimodal"] else []:
                ala, alo = geo.to_latlon(ax, ay, lat0, lon0)
                pts.append({"lat": ala, "lon": alo,
                            "tooltip": "⚡ alternate solution (geometry ambiguous)"})
            layers.append(pdk.Layer("ScatterplotLayer", pd.DataFrame(pts),
                                    get_position=["lon", "lat"],
                                    get_fill_color=pal.MAP_STRIKE, get_radius=120,
                                    radius_min_pixels=7, radius_max_pixels=24,
                                    stroked=True, get_line_color=[11, 11, 11, 200],
                                    line_width_min_pixels=1, pickable=True))
    return layers, est


CARTO_POSITRON = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"


def deck(layers, lat, lon, zoom=9.5, height=520):
    st.pydeck_chart(pdk.Deck(
        layers=[l for l in layers if l is not None],
        initial_view_state=pdk.ViewState(latitude=lat, longitude=lon, zoom=zoom),
        map_style=CARTO_POSITRON,  # token-free basemap
        tooltip={"text": "{tooltip}"}), height=height)


def map_legend(*items):
    dots = {"node": ("#2a78d6", "case node"), "dim": ("#898781", "other nodes"),
            "fire": ("#d03b3b", "🔥 natural-cause fire"),
            "ring": ("#eb6834", "thunder range ring ±σ"),
            "strike": ("#fab219", "⚡ strike estimate"),
            "truth": ("#0b0b0b", "✕ demo truth strike")}
    html = "&nbsp;&nbsp;".join(
        f"<span style='color:{dots[i][0]}'>●</span> {dots[i][1]}" for i in items if i in dots)
    st.caption(html, unsafe_allow_html=True)


# ================================================================ sidebar

nodes_df = load_nodes()
cases = load_cases()
case_by_id = {c["id"]: c for c in cases}

with st.sidebar:
    st.title("⚡ FlashPoint")
    st.caption("Lightning localization & wildfire ignition watch — "
               "Sage Summer Camp 2026")

    case_ids = [c["id"] for c in cases] + ["demo-storm"]
    titles = {c["id"]: c["title"] for c in cases}
    titles["demo-storm"] = "Demo storm — synthetic replay (no credentials needed)"
    case_id = st.radio("Case study", case_ids, format_func=lambda i: titles[i])

    if case_id == "demo-storm":
        case = demo.demo_case(demo_manifest())
    else:
        case = case_by_id[case_id]

    st.divider()
    st.session_state["offline"] = st.toggle(
        "Offline mode (local files only)", value=False,
        help="Skip all Sage API calls; use files already under flashpoint/data/ "
             "(e.g. downloaded with scripts/fetch_case_media.py).") \
        if case_id != "demo-storm" else False

    with st.expander("🔑 Sage credentials (for media downloads)"):
        env_u, env_t = sage.env_credentials()
        if env_u and env_t:
            st.success(f"Using credentials from environment (`{env_u}`).")
            st.session_state["sage_user"] = env_u
            st.session_state["sage_token"] = env_t
        else:
            st.session_state["sage_user"] = st.text_input("Portal username",
                                                          value=st.session_state.get("sage_user", ""))
            st.session_state["sage_token"] = st.text_input(
                "Access token", type="password",
                value=st.session_state.get("sage_token", ""),
                help="portal.sagecontinuum.org → My account → Access credentials. "
                     "Kept in this session only — never written to disk.")
        st.caption("Upload *listings* and met data are public — only the "
                   "image/audio files themselves need auth.")

    st.divider()
    st.caption(f"**{case['vsn']}** · {utc(case['start']):%Y-%m-%d} → "
               f"{utc(case['end']):%Y-%m-%d} · all times **UTC**")

cnodes = case_nodes(case, nodes_df)
if "board" not in st.session_state:
    st.session_state.board = {}
board = st.session_state.board.setdefault(case["id"], [])

tab_map, tab_img, tab_sync, tab_notes = st.tabs(
    ["🗺 Map", "🖼 Image compare", "⚡ Strike sync", "📓 Case notes"])


# ================================================================ 🗺 Map

with tab_map:
    left, right = st.columns([3, 1])
    with right:
        st.subheader(case["title"])
        st.markdown(case.get("notes", ""))
        scope = st.radio("Show nodes", ["Case region", "Whole fleet"], index=0)
        if case["id"] == "demo-storm" and st.toggle("Reveal truth strikes", key="truth_map"):
            truth = True
        else:
            truth = False
        if board:
            st.metric("Strike-board measurements", len(board))
    with left:
        layers = []
        if scope == "Whole fleet":
            layers.append(node_layer(nodes_df[~nodes_df.vsn.isin(cnodes.vsn)], dim=True))
        layers.append(node_layer(cnodes))
        layers.append(fire_layer(case.get("fires", [])))
        ring_layers, est = rings_layers(board, cnodes)
        layers += ring_layers
        if truth:
            td = pd.DataFrame(demo_manifest()["strikes"])
            td["tooltip"] = td.apply(lambda r: f"✕ truth {r['id']} @ {r['time'][11:19]}Z", axis=1)
            layers.append(pdk.Layer("TextLayer", td, get_position=["lon", "lat"],
                                    get_text="'✕'", get_size=22,
                                    get_color=[11, 11, 11, 255]))
        clat = float(cnodes.lat.mean()) if len(cnodes) else 41.8
        clon = float(cnodes.lon.mean()) if len(cnodes) else -87.7
        if case.get("fires"):
            flat = np.mean([f["lat"] for f in case["fires"]])
            flon = np.mean([f["lon"] for f in case["fires"]])
            clat, clon = (clat + flat) / 2, (clon + flon) / 2
        zoom = 12 if case["id"] == "demo-storm" else 9.2
        deck(layers, clat, clon, zoom=zoom)
        map_legend("node", *( ["dim"] if scope == "Whole fleet" else []),
                   "fire", *( ["ring", "strike"] if board else []),
                   *( ["truth"] if truth else []))
    if case.get("fires"):
        fdf = pd.DataFrame(case["fires"])
        fdf = fdf[["name", "discovered", "size_ac", "dist_km", "featured"]] \
            .rename(columns={"size_ac": "acres", "dist_km": "km from node"})
        st.dataframe(fdf, use_container_width=True, hide_index=True)


# ================================================================ 🖼 Image compare

with tab_img:
    st.caption("Compare frames across time (did smoke appear?) and across nodes "
               "(same sky, different vantage). The luminance track below flags "
               "flash-candidate frames ⚡.")
    tasks = case.get("image_tasks") or []
    if not tasks:
        st.info("This case has no camera tasks.")
    else:
        c1, c2, c3 = st.columns([2, 2, 1])
        sel_tasks = c1.multiselect("Camera tasks", tasks, default=tasks[:1])
        lo, hi = window_slider(case, "img_win")
        cap = int(c3.number_input("Max files", 10, 1000, MAX_IMG_DEFAULT, step=10,
                                  help="Evenly subsampled if the listing is larger."))
        listing = case_media_listing(case, sel_tasks, lo, hi) if sel_tasks else pd.DataFrame()
        if not len(listing):
            st.info("No uploads listed in this window.")
        else:
            per_task = listing.groupby("task").size()
            st.caption(" · ".join(f"**{t}**: {n} files" for t, n in per_task.items()))
            media, err = fetch_media_rows(listing, "image", cap)
            if err:
                need_creds_warning(err)
            if len(media):
                ldf = luminance_frame(media)
                if len(ldf) >= 5:
                    ldf = mark_flashes(ldf)
                    n_cand = int(ldf.flash.sum())
                    n_nodes = ldf.vsn.nunique() if "vsn" in ldf else 1
                    base = alt.Chart(for_chart(ldf)).encode(
                        x=alt.X("timestamp:T", title=None,
                                axis=alt.Axis(format="%m-%d %H:%M")))
                    if n_nodes > 1:  # distinguish nodes by hue + legend, not shape alone
                        color = alt.Color("vsn:N", title="node",
                                          scale=alt.Scale(range=[pal.CAMERA, pal.AUDIO, pal.MET,
                                                                 pal.INK_2]))
                        line = base.mark_line(strokeWidth=2).encode(
                            y=alt.Y("luma:Q", title="mean luminance"), color=color, detail="vsn:N")
                        pts = base.mark_point(filled=True, size=36).encode(
                            y="luma:Q", color=color,
                            tooltip=[alt.Tooltip("timestamp:T", format="%m-%d %H:%M:%S", title="UTC"),
                                     alt.Tooltip("luma:Q", format=".0f"), "vsn:N"])
                        legend_note = f"{n_nodes} nodes by color"
                    else:
                        line = base.mark_line(color=pal.CAMERA, strokeWidth=2).encode(
                            y=alt.Y("luma:Q", title="mean luminance"), detail="vsn:N")
                        pts = base.mark_point(color=pal.CAMERA, filled=True, size=36).encode(
                            y="luma:Q",
                            tooltip=[alt.Tooltip("timestamp:T", format="%m-%d %H:%M:%S", title="UTC"),
                                     alt.Tooltip("luma:Q", format=".0f"), "vsn:N"])
                        legend_note = "luminance in blue"
                    flashes = base.transform_filter(alt.datum.flash).mark_rule(
                        color=pal.FLASH, strokeWidth=2).encode(tooltip=alt.value("⚡ flash candidate"))
                    ftext = base.transform_filter(alt.datum.flash).mark_text(
                        text="⚡", dy=-6, size=14).encode(y=alt.value(8))
                    st.altair_chart(styled(line + pts + flashes + ftext, height=160),
                                    use_container_width=True)
                    st.caption(f"— {n_cand} flash-candidate frame(s) "
                               f"(robust-z luminance spikes, per node) · "
                               f"⚡ marks; {legend_note}")

                # A/B compare
                st.divider()
                colA, colB = st.columns(2)
                media = media.sort_values("timestamp").reset_index(drop=True)
                opts = list(media.index)

                def panel(col, name, default_idx):
                    with col:
                        st.markdown(f"**Panel {name}**")
                        vsns = sorted(media.vsn.unique()) if "vsn" in media else []
                        pick_vsn = st.selectbox(f"Node ({name})", vsns,
                                                index=0 if name == "A" else min(len(vsns) - 1, 1),
                                                key=f"vsn{name}") if len(vsns) > 1 else (vsns[0] if vsns else "")
                        sub = media[media.vsn == pick_vsn] if pick_vsn else media
                        sub = sub.reset_index(drop=True)
                        if not len(sub):
                            st.info("no frames"); return None
                        i = st.select_slider(
                            f"Frame ({name})", options=list(sub.index),
                            value=min(default_idx, len(sub) - 1),
                            format_func=lambda k: fmt_t(sub.loc[k, "timestamp"]),
                            key=f"frame{name}")
                        r = sub.loc[i]
                        st.image(str(r["path"]),
                                 caption=f"{r.get('vsn','')} · {r.get('task','')} · "
                                         f"{fmt_t(r['timestamp'])}Z",
                                 use_container_width=True)
                        return r

                ra = panel(colA, "A", 0)
                rb = panel(colB, "B", max(len(media) - 1, 0))
                if ra is not None and rb is not None:
                    if st.toggle("Blend A/B (change detection)"):
                        from PIL import Image
                        alpha = st.slider("Blend", 0.0, 1.0, 0.5, 0.05)
                        ia = Image.open(ra["path"]).convert("RGB")
                        ib = Image.open(rb["path"]).convert("RGB").resize(ia.size)
                        st.image(Image.blend(ia, ib, alpha),
                                 caption=f"A ⇆ B blend @ {alpha:.2f}",
                                 use_container_width=False)

                with st.expander("🎞 Filmstrip (evenly spaced)"):
                    n = min(len(media), 24)
                    step = max(len(media) // n, 1)
                    strip = media.iloc[::step].head(n)
                    cols = st.columns(6)
                    for k, (_, r) in enumerate(strip.iterrows()):
                        with cols[k % 6]:
                            st.image(str(r["path"]), caption=fmt_t(r["timestamp"]),
                                     use_container_width=True)


# ================================================================ ⚡ Strike sync

with tab_sync:
    st.caption("Synchronized image–audio–weather timelines. Pick a thunder clip, "
               "pick the flash that caused it, and turn Δt into a range ring — "
               "three rings localize the strike.")
    audio_task = case.get("audio_task")
    img_tasks = case.get("image_tasks") or []
    if not audio_task:
        st.info("**This case has no audio archive** (audio-sampler wasn't running). "
                "Use the Image compare tab for the smoke/сloud timeline, or the "
                "Demo storm for the full flash-to-bang workflow.")
    else:
        lo, hi = window_slider(case, "sync_win")
        sel_vsn = st.selectbox("Node", list(cnodes.vsn)) if len(cnodes) > 1 else case["vsn"]

        # ---- listings
        a_listing = case_media_listing(case, [audio_task], lo, hi)
        i_listing = case_media_listing(case, img_tasks[:1], lo, hi) if img_tasks else pd.DataFrame()
        if "vsn" in a_listing.columns and len(cnodes) > 1:
            a_listing = a_listing[a_listing.vsn == sel_vsn].reset_index(drop=True)
        if len(i_listing) and "vsn" in i_listing.columns and len(cnodes) > 1:
            i_listing = i_listing[i_listing.vsn == sel_vsn].reset_index(drop=True)

        cap_a = st.slider("Max audio clips to analyze", 10, 400, MAX_AUDIO_DEFAULT, 10,
                          help="Clips are fetched & analyzed lazily; narrow the "
                               "window instead of raising this.")
        a_media, a_err = fetch_media_rows(a_listing, "audio", cap_a) if len(a_listing) else (pd.DataFrame(), None)
        i_media, i_err = fetch_media_rows(i_listing, "image", MAX_IMG_DEFAULT) if len(i_listing) else (pd.DataFrame(), None)
        if a_err or i_err:
            need_creds_warning(a_err or i_err)

        adf = audio_frame(a_media) if len(a_media) else pd.DataFrame()
        ldf = luminance_frame(i_media) if len(i_media) else pd.DataFrame()

        if not len(adf):
            st.info("No audio clips available in this window "
                    f"({len(a_listing)} listed).")
        else:
            # ---- synchronized tracks (shared UTC x-domain, one measure per panel)
            span_days = (hi - lo).total_seconds() / 86400
            xfmt = "%m-%d %H:%M" if span_days > 1 else "%H:%M"
            tfmt = "%m-%d %H:%M:%S" if span_days > 1 else "%H:%M:%S"
            dom = [lo.tz_convert(None).isoformat(), hi.tz_convert(None).isoformat()]
            x = alt.X("timestamp:T", title=None, axis=alt.Axis(format=xfmt),
                      scale=alt.Scale(domain=dom))
            charts = []
            if len(ldf) >= 2:
                ldf = mark_flashes(ldf)
                lum = (alt.Chart(for_chart(ldf), title=alt.Title("camera — mean luminance",
                                                      color=pal.CAMERA, fontSize=12))
                       .mark_line(color=pal.CAMERA, strokeWidth=2, point={"filled": True, "color": pal.CAMERA})
                       .encode(x=x, y=alt.Y("luma:Q", title=None),
                               tooltip=[alt.Tooltip("timestamp:T", format=tfmt, title="UTC"),
                                        alt.Tooltip("luma:Q", format=".0f")]))
                fl = (alt.Chart(for_chart(ldf)).transform_filter(alt.datum.flash)
                      .mark_rule(color=pal.FLASH, strokeWidth=2)
                      .encode(x=x, tooltip=alt.value("⚡ flash candidate")))
                charts.append((lum + fl).properties(height=140))
            aud = (alt.Chart(for_chart(adf), title=alt.Title("audio — low-band (20–150 Hz) peak, dB",
                                                  color=pal.AUDIO, fontSize=12))
                   .mark_point(filled=True, size=70, color=pal.AUDIO)
                   .encode(x=x, y=alt.Y("low_peak_db:Q", title=None),
                           opacity=alt.Opacity("low_ratio:Q",
                                               scale=alt.Scale(range=[0.35, 1.0]),
                                               legend=None),
                           tooltip=[alt.Tooltip("timestamp:T", format=tfmt, title="UTC"),
                                    alt.Tooltip("low_peak_db:Q", format=".1f", title="low-band dB"),
                                    alt.Tooltip("low_ratio:Q", format=".2f", title="low-band ratio"),
                                    alt.Tooltip("duration_s:Q", format=".0f", title="clip s")]))
            charts.append(aud.properties(height=140))

            met_name = st.radio("Weather track", ["rain accumulation", "temperature", "pressure"],
                                horizontal=True, label_visibility="collapsed")
            met_key = {"rain accumulation": "wxt.rain.accumulation",
                       "temperature": "env.temperature",
                       "pressure": "env.pressure"}[met_name]
            if case["id"] == "demo-storm":
                met = demo.met_index(demo_manifest())
                met = met[(met.vsn == sel_vsn) & (met.name == met_key)]
            elif st.session_state.get("offline"):
                met = pd.DataFrame()
            else:
                try:  # met from the SELECTED node, matching the other tracks
                    met = q_met(sel_vsn, met_key, lo.isoformat(), hi.isoformat())
                except Exception:
                    met = pd.DataFrame()
            if len(met):
                m = met.set_index("timestamp").resample("5min")["value"].mean().dropna().reset_index()
                charts.append(
                    alt.Chart(for_chart(m), title=alt.Title(f"met — {met_name} ({sel_vsn})",
                                                            color=pal.MET, fontSize=12))
                    .mark_line(color=pal.MET, strokeWidth=2)
                    .encode(x=x, y=alt.Y("value:Q", title=None),
                            tooltip=[alt.Tooltip("timestamp:T", format=tfmt, title="UTC"),
                                     alt.Tooltip("value:Q", format=".2f")])
                    .properties(height=110))
            st.altair_chart(configured(alt.vconcat(*charts).resolve_scale(x="shared")),
                            use_container_width=True)
            st.caption("tracks share one UTC time axis — "
                       f"<span style='color:{pal.CAMERA}'>■</span> camera · "
                       f"<span style='color:{pal.AUDIO}'>■</span> audio · "
                       f"<span style='color:{pal.MET}'>■</span> met · "
                       f"<span style='color:{pal.FLASH}'>│</span> ⚡ flash candidate",
                       unsafe_allow_html=True)

            # ---- clip inspector
            st.divider()
            st.subheader("Clip inspector & flash-to-bang")
            adf = adf.reset_index(drop=True)
            ranked = adf.sort_values("low_peak_db", ascending=False)
            default_clip = int(ranked.index[0]) if len(ranked) else 0
            ci = st.selectbox(
                "Audio clip (sorted by time; ★ = top-5 low-band energy)",
                list(adf.index), index=default_clip,
                format_func=lambda k: (
                    f"{'★ ' if k in set(ranked.index[:5]) else ''}"
                    f"{fmt_t(adf.loc[k, 'timestamp'])}Z · "
                    f"low {adf.loc[k, 'low_peak_db']:.0f} dB · "
                    f"ratio {adf.loc[k, 'low_ratio']:.2f}"))
            clip = adf.loc[ci]
            y, sr = analysis.load_audio(clip["path"])
            t_env, env_db = analysis.envelope_db(y, sr)
            onset = clip.get("onset_s")

            cwave, cspec = st.columns(2)
            with cwave:
                wdf = pd.DataFrame({"t": t_env, "dB": env_db})
                w = (alt.Chart(wdf).mark_line(color=pal.AUDIO, strokeWidth=1.5)
                     .encode(x=alt.X("t:Q", title="seconds into clip"),
                             y=alt.Y("dB:Q", title="envelope dBFS"),
                             tooltip=[alt.Tooltip("t:Q", format=".2f"),
                                      alt.Tooltip("dB:Q", format=".1f")]))
                if onset is not None and not pd.isna(onset):
                    w += (alt.Chart(pd.DataFrame({"t": [onset]}))
                          .mark_rule(color=pal.INK, strokeWidth=2, strokeDash=[4, 3])
                          .encode(x="t:Q", tooltip=alt.value(f"onset {onset:.2f}s")))
                st.altair_chart(styled(w, height=200), use_container_width=True)
                st.audio(analysis.to_wav_bytes(y, sr), format="audio/wav")
            with cspec:
                import matplotlib
                matplotlib.use("Agg")
                import matplotlib.pyplot as plt
                ts_, fs_, sxx = analysis.spectrogram(y, sr)
                fig, ax = plt.subplots(figsize=(6, 2.6), dpi=110)
                vmax = np.percentile(sxx, 99)
                ax.pcolormesh(ts_, fs_, sxx, cmap="magma", vmin=vmax - 60, vmax=vmax,
                              shading="auto")
                if onset is not None and not pd.isna(onset):
                    ax.axvline(onset, color="#ffffff", lw=1.2, ls="--")
                ax.set_xlabel("seconds into clip", fontsize=8)
                ax.set_ylabel("Hz", fontsize=8)
                ax.tick_params(labelsize=7)
                ax.set_title("spectrogram (thunder band lives < 150 Hz)", fontsize=9,
                             color=pal.INK_2, loc="left")
                fig.tight_layout()
                st.pyplot(fig, use_container_width=True)
                plt.close(fig)

            # ---- flash-to-bang
            st.markdown("**Flash → bang → range**")
            clip_t0 = utc(clip["timestamp"])
            f1, f2, f3, f4 = st.columns([2, 1.4, 1.2, 1.2])
            with f1:
                flash_opts = []
                if len(ldf) and "flash" in ldf.columns:
                    fc = ldf[ldf["flash"]]
                    flash_opts = sorted(utc(t) for t in fc.timestamp)
                # best default: the nearest flash BEFORE the (guessed) bang —
                # thunder never precedes its flash, and 300 s ≈ 100 km already
                bang_guess = clip_t0 + pd.Timedelta(
                    seconds=float(onset) if onset is not None and not pd.isna(onset) else 0.0)
                prev = [t for t in flash_opts
                        if 0 <= (bang_guess - t).total_seconds() <= 300]
                best_flash = max(prev) if prev else None
                mode = st.radio("Flash time from", ["flash-candidate frame", "manual"],
                                index=0 if best_flash is not None else 1,
                                horizontal=True)
                if mode == "flash-candidate frame" and flash_opts:
                    t_flash = st.selectbox(
                        "Flash frame", flash_opts,
                        index=flash_opts.index(best_flash) if best_flash is not None else 0,
                        format_func=lambda t: fmt_t(t) + "Z")
                else:
                    off = st.number_input("Flash = clip start + (s)", value=0.0,
                                          step=0.1, format="%.1f")
                    t_flash = clip_t0 + pd.Timedelta(seconds=off)
            with f2:
                t_on = st.number_input("Thunder onset (s into clip)",
                                       value=float(onset) if onset is not None and not pd.isna(onset) else 0.0,
                                       min_value=0.0, max_value=float(clip["duration_s"]),
                                       step=0.05, format="%.2f")
                t_bang = clip_t0 + pd.Timedelta(seconds=float(t_on))
            with f3:
                sig_on = st.number_input("onset σ (ms)", value=100, min_value=10,
                                         max_value=1000, step=10)
                sig_fl = st.number_input("flash σ (s)", value=0.3, min_value=0.0,
                                         max_value=300.0, step=0.1,
                                         help="How well the flash time is known. "
                                              "Storm-mode triggered frames: ~0.3 s. "
                                              "Snapshot cadence: half the cadence.")
            with f4:
                temp = get_case_temp(case, clip_t0)
                temp_c = st.number_input("Air temp °C (for c)",
                                         value=float(temp) if temp is not None else 20.0,
                                         step=0.5, format="%.1f")

            dt = (t_bang - t_flash).total_seconds()
            c_ms = analysis.speed_of_sound(temp_c)
            if dt <= 0:
                st.error(f"Δt = {dt:.2f} s — thunder must come *after* the flash. "
                         "Pick an earlier flash or later onset.")
            else:
                sigma_t = np.hypot(sig_on / 1000.0, sig_fl)
                rng_m = c_ms * dt
                sig_m = c_ms * sigma_t
                m1, m2, m3 = st.columns(3)
                m1.metric("Δt flash→bang", f"{dt:.2f} s")
                m2.metric(f"speed of sound at {temp_c:.1f} °C", f"{c_ms:.1f} m/s")
                m3.metric("range", f"{rng_m/1000:.2f} ± {sig_m/1000:.2f} km")
                if dt > 90:
                    st.warning(f"Δt = {dt:.0f} s ⇒ {rng_m/1000:.0f} km — beyond "
                               "plausible thunder audibility (~15 km). Almost "
                               "certainly the wrong flash↔clip pairing.", icon="⚠️")
                node_for_clip = clip.get("vsn") or sel_vsn or case["vsn"]
                if st.button(f"➕ Add ring: {node_for_clip} @ {rng_m/1000:.2f} km",
                             type="primary"):
                    board.append({
                        "vsn": node_for_clip,
                        "t_flash": t_flash.isoformat(),
                        "t_bang": t_bang.isoformat(),
                        "dt_s": round(dt, 3),
                        "range_m": round(rng_m, 1),
                        "sigma_m": round(sig_m, 1),
                        "temp_c": temp_c,
                    })
                    st.rerun()

        # ---- strike board + localization
        st.divider()
        st.subheader(f"Strike board — {len(board)} measurement(s)")
        if not board:
            st.caption("Add flash-to-bang rings from 2–3 nodes (or the same node "
                       "for different strikes) and the intersection appears here.")
        else:
            bdf = pd.DataFrame(board)
            bdf_disp = bdf.assign(
                range_km=(bdf.range_m / 1000).round(2),
                sigma_km=(bdf.sigma_m / 1000).round(2),
            )[["vsn", "t_flash", "dt_s", "range_km", "sigma_km", "temp_c"]]
            st.dataframe(bdf_disp, use_container_width=True, hide_index=True)
            cbtn1, cbtn2 = st.columns([1, 4])
            if cbtn1.button("🗑 Clear board"):
                board.clear()
                st.rerun()

            ring_layers, est = rings_layers(board, cnodes if len(cnodes) else nodes_df)
            layers = [node_layer(cnodes)] + ring_layers
            layers.append(fire_layer(case.get("fires", [])))
            truth_on = case["id"] == "demo-storm" and st.toggle("Reveal truth strikes",
                                                                key="truth_sync")
            if truth_on:
                td = pd.DataFrame(demo_manifest()["strikes"])
                td["tooltip"] = td.apply(lambda r: f"✕ truth {r['id']} @ {r['time'][11:19]}Z", axis=1)
                layers.append(pdk.Layer("TextLayer", td, get_position=["lon", "lat"],
                                        get_text="'✕'", get_size=22,
                                        get_color=[11, 11, 11, 255]))
            clat = float(cnodes.lat.mean()); clon = float(cnodes.lon.mean())
            deck(layers, clat, clon, zoom=11.5 if case["id"] == "demo-storm" else 9.5,
                 height=460)
            map_legend("node", "ring", "strike", "fire",
                       *( ["truth"] if truth_on else []))

            if est and (est.get("degenerate") or not np.isfinite(est["semi_major_m"])):
                st.warning(
                    f"**Strike under-constrained** at {est['lat']:.5f}, {est['lon']:.5f} — "
                    "the ring geometry is degenerate (rings from the same node, or "
                    "collinear nodes), so the fix is unbounded along one axis "
                    "(GDOP ∞). Add a ring from a node off that line to pin it down.",
                    icon="⚠️")
            elif est:
                ambig = ""
                if est["bimodal"]:
                    ambig = (", ⚠️ two-ring solution is ambiguous — both shown"
                             if est["n_nodes"] == 2
                             else ", ⚠️ near-collinear geometry — mirror solution shown")
                st.success(
                    f"**Strike estimate:** {est['lat']:.5f}, {est['lon']:.5f} — "
                    f"1σ ellipse {est['semi_major_m']:.0f} × {est['semi_minor_m']:.0f} m, "
                    f"GDOP {est['gdop']:.1f}, rms residual {est['rms_m']:.0f} m "
                    f"({est['n_nodes']} rings{ambig})", icon="⚡")
                for f in case.get("fires", []):
                    d = geo.dist_km(est["lat"], est["lon"], f["lat"], f["lon"])
                    if f.get("featured") or d < 20:
                        st.caption(f"→ {d:5.1f} km from 🔥 **{f['name']}** "
                                   f"({f['size_ac']} ac, discovered {f['discovered'][:16]}Z)")
                if case["id"] == "demo-storm":
                    tr = demo_manifest()["strikes"]
                    dmin = min((geo.dist_km(est["lat"], est["lon"], s["lat"], s["lon"]), s["id"])
                               for s in tr)
                    st.caption(f"→ {dmin[0]*1000:.0f} m from truth strike **{dmin[1]}**")
            elif len(board) == 1:
                st.info("One ring so far — a range without a bearing. Add a ring "
                        "from another node (or use the fisheye azimuth) to pin it down.")


# ================================================================ 📓 Case notes

with tab_notes:
    st.subheader(case["title"])
    st.markdown(case.get("notes", ""))
    ccol1, ccol2 = st.columns(2)
    with ccol1:
        st.markdown("**Node(s) under study**")
        st.dataframe(cnodes[["vsn", "lat", "lon", "mic", "cam", "address"]],
                     use_container_width=True, hide_index=True)
        if case.get("fires"):
            st.markdown("**Natural-cause fires in the window (WFIGS)**")
            st.dataframe(pd.DataFrame(case["fires"])[
                ["name", "discovered", "size_ac", "dist_km"]],
                use_container_width=True, hide_index=True)
    with ccol2:
        st.markdown("**Archive census for this window**")
        if case["id"] == "demo-storm":
            idx = demo.media_index(demo_manifest())
            st.dataframe(idx.groupby(["vsn", "task"]).size().rename("files").reset_index(),
                         use_container_width=True, hide_index=True)
        elif st.session_state.get("offline"):
            idx = sage.local_media_index()
            st.dataframe(idx.groupby(["vsn", "task"]).size().rename("files").reset_index()
                         if len(idx) else pd.DataFrame({"files": []}),
                         use_container_width=True, hide_index=True)
        else:
            if st.button("Query archive census (public listing)"):
                lo, hi = utc(case["start"]), utc(case["end"])
                lst = case_media_listing(case, [".*"], lo, hi)
                if len(lst):
                    st.dataframe(lst.groupby("task").size().rename("files").reset_index(),
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("Nothing listed (or query failed).")
        st.markdown("**Method, honestly stated**")
        st.markdown(
            "- Flash-to-bang range needs **no cross-node clock sync** — light is "
            "the time anchor; each node self-clocks its own Δt.\n"
            "- Thunder onsets are smeared: expect 50–200 ms picking error "
            "(±17–70 m of range) — σ inputs propagate into the ring width.\n"
            "- Snapshot archives (1 clip / ~5.5 min) can *contain* thunder but "
            "can't time flashes; treat retrospective ranges as demonstrations, "
            "not measurements. Storm-mode continuous capture (the demo) is the "
            "design target.\n"
            "- Every estimate carries an uncertainty ellipse + GDOP; two-ring "
            "solutions are shown with **both** intersections.")
    st.divider()
    st.caption("Plan: `docs/echoguard-flashpoint-plan.md` (Part II) · handoff "
               "brief: `CLAUDE.md` · data patterns verified live 2026-07-21/22. "
               "Fires: NIFC WFIGS incident locations, natural cause only. "
               "All timestamps UTC.")
