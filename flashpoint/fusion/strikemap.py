"""Self-contained strike-map HTML generator (no network, no basemap
dependency — same offline-demo philosophy as ui/index.html, and the same
dark palette so the two read as one family)."""
import json
import math
import pathlib

TEMPLATE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Sage FlashPoint — Live Strike Map</title><style>
body{background:#151C2C;color:#F5F7FA;font:14px/1.5 'Segoe UI',system-ui,sans-serif;margin:0}
header{padding:10px 18px;background:#222E47}header b{color:#F5B722}
#wrap{display:flex}#map{flex:2}aside{flex:1;max-width:380px;padding:12px;overflow-y:auto;max-height:92vh}
.card{background:#222E47;border-radius:10px;padding:10px 12px;margin-bottom:10px;font-size:13px}
.card h3{font-size:12px;color:#AFC0D8;letter-spacing:1px;text-transform:uppercase;margin:0 0 6px}
.fix{color:#F5B722}.ambiguous{color:#E0592A}.range-only{color:#AFC0D8}
svg text{font:11px 'Segoe UI',sans-serif}
</style></head><body>
<header><b>&#9889; Sage FlashPoint</b> — fused strike map <span style="color:#AFC0D8">__SUBTITLE__</span></header>
<div id="wrap"><div id="map">__SVG__</div><aside>__CARDS__</aside></div>
</body></html>"""


def _project(payload):
    pts = [(n["lat"], n["lon"]) for n in payload["nodes"]]
    pts += [(s["lat"], s["lon"]) for s in payload["strikes"] if s["lat"]]
    pts += [(t["lat"], t["lon"]) for t in payload.get("truth", [])]
    lat0 = sum(p[0] for p in pts) / len(pts)
    lon0 = sum(p[1] for p in pts) / len(pts)
    kx = 111.32 * math.cos(math.radians(lat0))

    def xy(lat, lon):
        return ((lon - lon0) * kx, (lat - lat0) * 110.54)

    xys = [xy(*p) for p in pts]
    span = max(max(abs(x) for x, _ in xys), max(abs(y) for _, y in xys), 1.0)
    scale = 320.0 / span  # px per km into a 700x700 view

    def px(lat, lon):
        x, y = xy(lat, lon)
        return 350 + x * scale, 350 - y * scale

    return px, scale


def render(payload, out_path):
    px, scale = _project(payload)
    parts = [f'<svg viewBox="0 0 700 700" width="100%" height="92vh">']
    # greedy label placement: nodes in a tight cluster otherwise stack their
    # labels on top of each other (Argonne spacing < label width at this zoom).
    # Every node DOT is an obstacle too — a label clear of other labels can
    # still sit on a neighbouring marker.
    node_xy = [px(n["lat"], n["lon"]) for n in payload["nodes"]]
    placed = [(x - 9, y - 9, x + 9, y + 9) for x, y in node_xy]

    def label_spot(x, y, text):
        w, h = 7 * len(text) + 6, 14
        for dx, dy in ((11, 4), (-w - 11, 4), (-w / 2 + 2, -14),
                       (-w / 2 + 2, 24), (11, -14), (-w - 11, -14),
                       (11, 24), (-w - 11, 24), (26, 4), (-w - 26, 4)):
            lx, ly = x + dx, y + dy
            box = (lx - 2, ly - h, lx + w, ly + 4)
            if all(box[2] < p[0] or box[0] > p[2] or box[3] < p[1]
                   or box[1] > p[3] for p in placed):
                placed.append(box)
                return lx, ly
        placed.append((x + 11, y - 10, x + 11 + w, y + 8))
        return x + 11, y + 4  # fall back to default rather than dropping it

    for n, (x, y) in zip(payload["nodes"], node_xy):
        lx, ly = label_spot(x, y, n["vsn"])
        parts.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="6" fill="#7FDBFF"/>'
                     f'<text x="{lx:.0f}" y="{ly:.0f}" fill="#AFC0D8">{n["vsn"]}</text>')
    for t in payload.get("truth", []):
        x, y = px(t["lat"], t["lon"])
        parts.append(f'<text x="{x - 5:.0f}" y="{y + 5:.0f}" fill="#F5F7FA" '
                     f'font-size="14">&#10005;</text>')
    cards = []
    for s in payload["strikes"]:
        if s["lat"] is None:
            cards.append(f'<div class="card"><h3 class="range-only">range-only</h3>'
                         f'{s["note"]} — {json.dumps(s["ranges"])}</div>')
            continue
        x, y = px(s["lat"], s["lon"])
        if s["semi_major_m"]:
            rx = s["semi_major_m"] / 1000 * scale
            ry = max(s["semi_minor_m"] / 1000 * scale, 2)
            parts.append(
                f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="{rx:.1f}" ry="{ry:.1f}" '
                f'transform="rotate({-s["angle_deg"]:.0f} {x:.0f} {y:.0f})" '
                f'fill="rgba(245,183,34,0.15)" stroke="#F5B722" stroke-width="1"/>')
        col = {"fix": "#F5B722", "ambiguous": "#E0592A"}.get(s["quality"], "#AFC0D8")
        parts.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="5" fill="{col}"/>')
        import datetime
        ts = datetime.datetime.fromtimestamp(s["time_epoch"],
                                             datetime.timezone.utc)
        cards.append(
            f'<div class="card"><h3 class="{s["quality"]}">{s["quality"]}'
            f' &middot; {ts:%H:%M:%S}Z</h3>'
            f'{s["lat"]:.5f}, {s["lon"]:.5f}<br>'
            f'ellipse {s["semi_major_m"]:.0f}&times;{s["semi_minor_m"]:.0f} m '
            f'&middot; GDOP {s["gdop"]:.1f} &middot; {s["n_nodes"]} nodes<br>'
            f'<span style="color:#AFC0D8">ranges: '
            + ", ".join(f"{v} {r:.2f} km" for v, r in s["ranges"].items())
            + (f'<br>{s["note"]}' if s["note"] else "") + "</span></div>")
    parts.append("</svg>")
    sub = payload.get("generated_from", "")
    html = (TEMPLATE.replace("__SVG__", "".join(parts))
            .replace("__CARDS__", "".join(cards))
            .replace("__SUBTITLE__", sub))
    pathlib.Path(out_path).write_text(html)
