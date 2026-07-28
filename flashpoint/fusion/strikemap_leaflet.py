"""Leaflet strike-map renderer — real basemap, dark-themed to match the rest
of FlashPoint (ui/index.html, the SVG map, the dashboard's CARTO Positron).

Self-contained EXCEPT map tiles: Leaflet's JS/CSS are vendored and inlined
(fusion/vendor/), markers are CSS divIcons (no external marker images), so
the page renders anywhere — but the basemap TILES load from CARTO/Esri and
need network at view time. Without network the tiles are simply blank and
the strikes/nodes/ellipses still render on the map pane (graceful degrade);
for a guaranteed-offline map use strikemap.render() (the SVG version).

Layers: CARTO Dark Matter (default), CARTO Voyager, Esri World Imagery
(satellite) — switchable. Real uncertainty ellipses (geo.ellipse_polygon),
quality-colored strikes, node markers, truth ✕, rich popups, legend, scale.
"""
import datetime
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "dashboard"))
from fp import geo  # noqa: E402

VENDOR = pathlib.Path(__file__).resolve().parent / "vendor"

# palette shared with the SVG map / ui / dashboard
C = {"node": "#7FDBFF", "fix": "#F5B722", "ambiguous": "#E0592A",
     "range-only": "#AFC0D8", "truth": "#F5F7FA", "ellipse": "#F5B722",
     "bg": "#151C2C", "panel": "#222E47", "txt": "#F5F7FA", "mut": "#AFC0D8"}

PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sage FlashPoint — Strike Map</title>
<style>__LEAFLET_CSS__</style>
<style>
html,body{margin:0;height:100%;background:__BG__;color:__TXT__;
  font:14px/1.4 'Segoe UI',system-ui,sans-serif}
#map{position:absolute;inset:0}
.hdr{position:absolute;top:0;left:0;right:0;z-index:1000;padding:8px 14px;
  background:rgba(34,46,71,.92);font-size:15px}
.hdr b{color:#F5B722}.hdr span{color:__MUT__;font-size:12px}
.dot{width:14px;height:14px;border-radius:50%;border:2px solid #151C2C;
  box-shadow:0 0 4px rgba(0,0,0,.6)}
.truth{color:__TXT__;font-size:18px;font-weight:700;text-shadow:0 0 3px #000}
.leaflet-popup-content-wrapper,.leaflet-popup-tip{background:__PANEL__;color:__TXT__}
.leaflet-popup-content{margin:10px 12px;font-size:13px}
.leaflet-popup-content h4{margin:0 0 6px}
.leaflet-bar a{background:__PANEL__;color:__TXT__;border-color:#3a4a6a}
.legend{background:rgba(34,46,71,.92);padding:8px 10px;border-radius:8px;
  font-size:12px;line-height:1.7;color:__TXT__}
.legend i{display:inline-block;width:12px;height:12px;border-radius:50%;
  margin-right:6px;vertical-align:-1px}
.fix-t{color:#F5B722}.ambiguous-t{color:#E0592A}.range-only-t{color:#AFC0D8}
</style></head><body>
<div class="hdr"><b>&#9889; Sage FlashPoint</b> — fused strike map &nbsp;
  <span>__SUBTITLE__</span></div>
<div id="map"></div>
<script>__LEAFLET_JS__</script>
<script>
const DATA = __DATA__;
const C = __COLORS__;
const map = L.map('map', {zoomControl:true, attributionControl:true});

const carto = (name)=>L.tileLayer(
  `https://{s}.basemaps.cartocdn.com/${name}/{z}/{x}/{y}{r}.png`,
  {subdomains:'abcd', maxZoom:20,
   attribution:'&copy; OpenStreetMap &copy; CARTO'});
const dark = carto('dark_all').addTo(map);
const voyager = carto('rastertiles/voyager');
const sat = L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  {maxZoom:19, attribution:'Tiles &copy; Esri'});
L.control.layers({'Dark':dark,'Voyager':voyager,'Satellite':sat}).addTo(map);
L.control.scale({imperial:false}).addTo(map);

const bounds = [];
function dotIcon(color, size){return L.divIcon({className:'',
  html:`<div class="dot" style="background:${color};width:${size}px;height:${size}px"></div>`,
  iconSize:[size,size], iconAnchor:[size/2,size/2]});}

DATA.nodes.forEach(n=>{
  L.marker([n.lat,n.lon],{icon:dotIcon(C.node,12)})
    .bindPopup(`<h4>${n.vsn}</h4>node`).addTo(map);
  L.tooltip({permanent:true,direction:'right',className:'',offset:[8,0]})
    .setContent(n.vsn).setLatLng([n.lat,n.lon]).addTo(map);
  bounds.push([n.lat,n.lon]);
});

(DATA.truth||[]).forEach(t=>{
  L.marker([t.lat,t.lon],{icon:L.divIcon({className:'truth',html:'&#10005;',
    iconSize:[18,18],iconAnchor:[9,9]})})
    .bindPopup(`<h4>truth ${t.id}</h4>${t.lat.toFixed(5)}, ${t.lon.toFixed(5)}`)
    .addTo(map);
  bounds.push([t.lat,t.lon]);
});

DATA.strikes.forEach(s=>{
  if(s.lat==null) return;
  const col = C[s.quality]||C['range-only'];
  if(s.ellipse){ L.polygon(s.ellipse,{color:C.ellipse,weight:1.5,
    fillColor:C.ellipse,fillOpacity:.15}).addTo(map); }
  const t = new Date(s.time_epoch*1000).toISOString().slice(11,19);
  const ranges = Object.entries(s.ranges||{})
    .map(([v,r])=>`${v} ${r.toFixed(2)} km`).join(', ');
  L.marker([s.lat,s.lon],{icon:dotIcon(col,14)}).bindPopup(
    `<h4 class="${s.quality}-t">&#9889; ${s.quality} &middot; ${t}Z</h4>`+
    `${s.lat.toFixed(5)}, ${s.lon.toFixed(5)}<br>`+
    (s.semi_major_m?`ellipse ${s.semi_major_m.toFixed(0)}&times;${s.semi_minor_m.toFixed(0)} m &middot; `:'')+
    `GDOP ${s.gdop?s.gdop.toFixed(1):'—'} &middot; ${s.n_nodes} nodes<br>`+
    `<span style="color:${C.mut}">ranges: ${ranges}</span>`+
    (s.note?`<br><span style="color:${C.mut}">${s.note}</span>`:''))
    .addTo(map);
  bounds.push([s.lat,s.lon]);
});

const legend = L.control({position:'bottomright'});
legend.onAdd = ()=>{const d=L.DomUtil.create('div','legend');
  d.innerHTML =
    `<i style="background:${C.node}"></i>node<br>`+
    `<i style="background:${C.fix}"></i><span class="fix-t">strike (fix)</span><br>`+
    `<i style="background:${C.ambiguous}"></i><span class="ambiguous-t">ambiguous</span><br>`+
    `<i style="background:${C['range-only']}"></i><span class="range-only-t">range-only</span><br>`+
    `&#10005; truth`;
  return d;};
legend.addTo(map);

if(bounds.length) map.fitBounds(bounds,{padding:[60,60]});
else map.setView([41.8,-88.0],9);
</script></body></html>"""


def render(payload, out_path):
    """payload: same dict strikemap.render() consumes (nodes/strikes/truth)."""
    lat0 = sum(n["lat"] for n in payload["nodes"]) / len(payload["nodes"])
    lon0 = sum(n["lon"] for n in payload["nodes"]) / len(payload["nodes"])
    strikes = []
    for s in payload["strikes"]:
        s = dict(s)
        if s["lat"] is not None and s.get("semi_major_m"):
            s["ellipse"] = geo.ellipse_polygon(
                s["lat"], s["lon"], max(s["semi_major_m"], 30),
                max(s["semi_minor_m"], 30), s["angle_deg"])
            # geo returns [[lon,lat],...]; Leaflet wants [lat,lon]
            s["ellipse"] = [[p[1], p[0]] for p in s["ellipse"]]
        else:
            s["ellipse"] = None
        strikes.append(s)
    data = {"nodes": payload["nodes"],
            "strikes": strikes,
            "truth": payload.get("truth", [])}
    html = (PAGE
            .replace("__LEAFLET_CSS__", (VENDOR / "leaflet-1.9.4.css").read_text())
            .replace("__LEAFLET_JS__", (VENDOR / "leaflet-1.9.4.js").read_text())
            .replace("__DATA__", json.dumps(data))
            .replace("__COLORS__", json.dumps(C))
            .replace("__SUBTITLE__", payload.get("generated_from", ""))
            .replace("__BG__", C["bg"]).replace("__TXT__", C["txt"])
            .replace("__MUT__", C["mut"]).replace("__PANEL__", C["panel"]))
    pathlib.Path(out_path).write_text(html)
    return out_path
