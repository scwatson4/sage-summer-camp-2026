# FlashPoint dashboard

Visual analysis workbench for the FlashPoint project: compare node imagery,
line up image + audio + weather on one clock, turn flash→thunder delays into
range rings, and localize strikes on a map next to the wildfires they may have
started.

## Run it

```bash
cd flashpoint
pip install -r requirements.txt
streamlit run dashboard/app.py
```

No credentials? Pick **Demo storm** in the sidebar — a synthetic 5-strike
storm over the real Argonne node geometry (physically consistent thunder
delays) exercises every feature offline.

For the real case studies (Kitten Fire, Signal Flat, Selma bust):

- upload **listings** and met telemetry are public — timelines work as-is;
- the actual JPG/FLAC files are protected: set `SAGE_USER` / `SAGE_TOKEN`
  (portal access token) in the environment or `flashpoint/.env`, or paste them
  into the sidebar (session-only). Files are cached under `flashpoint/data/`
  (gitignored), so nothing downloads twice. `scripts/fetch_case_media.py`
  pre-downloads whole case windows; the dashboard picks those up in
  **Offline mode**.

## Views

| Tab | What it does |
|---|---|
| 🗺 Map | Case nodes + whole fleet, WFIGS natural-cause fires (sized by acreage), strike-board rings/estimates |
| 🖼 Image compare | A/B panels across nodes and times, blend mode for change detection, filmstrip, luminance timeline with ⚡ flash-candidate markers |
| ⚡ Strike sync | Camera / audio / met tracks on one UTC axis; clip inspector (waveform + spectrogram + playback, leading-edge onset pick); flash-to-bang range engine with honest σ; multi-ring strike localization with uncertainty ellipse + GDOP |
| 📓 Case notes | The story, the fires, archive census, and the method's caveats |

## Files

- `app.py` — Streamlit UI
- `fp/sage.py` — manifest/case assets, public queries, authenticated media cache
- `fp/analysis.py` — luminance series, thunder-band features, onset picking, flash-to-bang
- `fp/geo.py` — projection, range rings, multilateration, uncertainty ellipse
- `fp/demo.py` — synthetic storm replay (the plan's "no-storm insurance")
- `fp/palette.py` — chart palette (validated light+dark; camera=blue, audio=orange, met=aqua)
- `bake_assets.py` — regenerates `assets/nodes.json` + `assets/cases.json` from the live manifest + WFIGS
