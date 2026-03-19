"""
Kayang Lakarin? v6
Mobile-first outdoor commute finder for Metro Manila.
"""
import streamlit as st
import folium
from streamlit_folium import st_folium
import math, json, time
import requests
import polyline as pl
from supabase import create_client
import datetime

@st.cache_resource
def get_supabase():
    return create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])

st.set_page_config(page_title="Kayang Lakarin?", page_icon="🏃", layout="centered",
                   initial_sidebar_state="collapsed")

if "click_lat" not in st.session_state:
    st.session_state.click_lat = None
    st.session_state.click_lng = None

# ── Engine ────────────────────────────────────────────────────────────
OSRM_BASE = "https://router.project-osrm.org/route/v1"
TM = {"grab": 1.6, "jeepney": 2.2, "walk": 1.0}

@st.cache_data(ttl=3600, show_spinner=False)
def osrm_route(lat1, lng1, lat2, lng2, profile="driving"):
    url = f"{OSRM_BASE}/{profile}/{lng1},{lat1};{lng2},{lat2}"
    try:
        r = requests.get(url, params={"overview": "full", "geometries": "polyline", "steps": "false"}, timeout=8)
        r.raise_for_status()
        d = r.json()
        if d.get("code") != "Ok" or not d.get("routes"): return None
        rt = d["routes"][0]
        return {"distance_km": rt["distance"]/1000, "duration_min": rt["duration"]/60, "geometry": pl.decode(rt["geometry"])}
    except Exception: return None

@st.cache_data(ttl=3600, show_spinner=False)
def batch_osrm(ulat, ulng, keys):
    out = {}
    for name, dlat, dlng in keys:
        dr = osrm_route(ulat, ulng, dlat, dlng, "driving")
        wk = osrm_route(ulat, ulng, dlat, dlng, "foot") if (dr and dr["distance_km"] < 5) or not dr else None
        out[name] = {"driving": dr, "walking": wk}
        time.sleep(0.12)
    return out

def commute_osrm(dr, wk):
    if not dr: return None
    dd, dt = dr["distance_km"], dr["duration_min"]
    jw = 8 if dd < 3 else (12 if dd < 8 else 18)
    jt = round(dt * TM["jeepney"] + jw)
    jf = 13 if dd <= 4 else round(13 + (dd-4)*1.80)
    gp = 5 if dd < 5 else 8
    gt = round(dt * TM["grab"] + gp)
    gb = round(45 + dd*14)
    gr = (round(gb*0.85), round(gb*1.35))
    wi = None
    if wk:
        wt = round(wk["duration_min"])
        if wt <= 90: wi = {"time_min": wt, "cost": 0, "distance_km": wk["distance_km"]}
    return {"walk": wi, "jeepney": {"time_min": jt, "cost": jf},
            "grab": {"time_min": gt, "cost_range": gr}, "road_distance_km": dd,
            "driving_geometry": dr["geometry"], "walking_geometry": wk["geometry"] if wk else None}

def hav(a1, n1, a2, n2):
    R = 6371; dl, dn = math.radians(a2-a1), math.radians(n2-n1)
    a = math.sin(dl/2)**2 + math.cos(math.radians(a1))*math.cos(math.radians(a2))*math.sin(dn/2)**2
    return R*2*math.asin(math.sqrt(a))

def commute_fallback(km):
    rd = km * 1.35
    base = {"road_distance_km": rd, "driving_geometry": None, "walking_geometry": None}
    if rd < 1: return {**base, "walk": {"time_min": round(rd/4.5*60), "cost": 0, "distance_km": rd},
        "jeepney": {"time_min": round(rd/10*60+8), "cost": 13}, "grab": {"time_min": round(rd/15*60+5), "cost_range": (60, 90)}}
    elif rd < 5: return {**base, "walk": {"time_min": round(rd/4.5*60), "cost": 0, "distance_km": rd},
        "jeepney": {"time_min": round(rd/10*60+10), "cost": 13}, "grab": {"time_min": round(rd/15*60+8), "cost_range": (70, 150)}}
    elif rd < 15: return {**base, "walk": None,
        "jeepney": {"time_min": round(rd/8*60+15), "cost": 26}, "grab": {"time_min": round(rd/12*60+10), "cost_range": (120, 280)}}
    else: return {**base, "walk": None,
        "jeepney": {"time_min": round(rd/7*60+20), "cost": 40}, "grab": {"time_min": round(rd/10*60+15), "cost_range": (200, 500)}}

# ── Data ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def load_areas():
    sb = get_supabase()
    resp = sb.table("outdoor_areas").select("*").execute()
    areas = resp.data
    for a in areas:
        fee = a.get("entrance_fee", "free")
        if fee != "free":
            try:
                a["entrance_fee"] = int(fee)
            except (ValueError, TypeError):
                a["entrance_fee"] = fee
        if isinstance(a.get("activities"), str):
            a["activities"] = json.loads(a["activities"])
    return areas

AREAS = load_areas()

def aq_lbl(s):
    if s >= 4: return ("Good air", "#2d6a4f")
    if s >= 3: return ("Moderate air", "#b8860b")
    return ("Poor air", "#c0392b")

def fee_str(fee):
    if isinstance(fee, (int, float)) and fee > 0: return f"P{int(fee)}"
    if isinstance(fee, str) and fee != "free":
        try:
            v = int(fee)
            if v > 0: return f"P{v}"
        except (ValueError, TypeError):
            pass
    return ""

REFS = {
    "Quezon City (Cubao)": (14.6218, 121.0555),
    "Quezon City (Commonwealth)": (14.6760, 121.0870),
    "Quezon City (Fairview)": (14.7220, 121.0710),
    "Manila (Quiapo)": (14.5992, 120.9842),
    "Manila (Tondo)": (14.6100, 120.9680),
    "Makati (Ayala)": (14.5547, 121.0244),
    "Pasig (Ortigas)": (14.5880, 121.0610),
    "Pasig (Kapitolyo)": (14.5730, 121.0590),
    "Taguig (BGC)": (14.5503, 121.0496),
    "Marikina": (14.6320, 121.1150),
    "Mandaluyong (Shaw)": (14.5812, 121.0540),
    "San Juan": (14.6010, 121.0480),
    "Parañaque (BF Homes)": (14.4550, 121.0120),
    "Muntinlupa (Alabang)": (14.4230, 121.0350),
    "Valenzuela": (14.6930, 120.9750),
    "Caloocan": (14.6571, 120.9839),
    "Las Piñas": (14.4500, 121.0000),
    "Custom...": None,
}

# ══════════════════════════════════════════════════════════════════════
# CSS — mobile first, single column
# ══════════════════════════════════════════════════════════════════════
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap');
@font-face {
    font-family: 'Datatype'; font-display: swap; font-weight: 100 900; font-stretch: 50% 150%;
    src: url('https://raw.githubusercontent.com/franktisellano/datatype/main/fonts/variable/Datatype%5Bwdth%2Cwght%5D.woff2') format('woff2');
}
html, .stApp { font-family: 'Outfit', sans-serif; background: #f5f2ed; }
.block-container { max-width: 720px; padding: 1rem 1rem 2rem; }

/* Sidebar */
section[data-testid="stSidebar"] { background: #1c1c1c !important; }
section[data-testid="stSidebar"] * { color: #ccc !important; }
section[data-testid="stSidebar"] .stMarkdown h3 {
    color: #fff !important; font-size: 0.65rem; font-weight: 700;
    letter-spacing: 1.5px; text-transform: uppercase;
    border-bottom: 1px solid #333; padding-bottom: 5px; margin-top: 1rem;
}
section[data-testid="stSidebar"] .stSelectbox > div > div,
section[data-testid="stSidebar"] .stMultiSelect > div > div {
    background: #2a2a2a !important; border: 1px solid #3a3a3a !important; border-radius: 6px !important;
}
section[data-testid="stSidebar"] hr { border-color: #333 !important; }

/* Header */
.hd { margin-bottom: 1rem; }
.hd-t { font-family: 'Datatype','Outfit',sans-serif; font-weight: 800; font-size: 2rem;
    color: #1a1a1a; line-height: 1; letter-spacing: -0.5px;
    font-variation-settings: 'wdth' 100, 'wght' 800; }
.hd-s { font-size: 0.85rem; color: #666; line-height: 1.55; margin-top: 6px; }
.hd-s strong { color: #2d6a4f; }

/* Stats */
.st-row { display: flex; gap: 2px; margin: 0.8rem 0; border-radius: 8px; overflow: hidden; }
.st-c { flex: 1; background: white; padding: 10px 6px; text-align: center; }
.st-c:first-child { border-radius: 8px 0 0 8px; } .st-c:last-child { border-radius: 0 8px 8px 0; }
.st-n { font-family: 'Datatype',monospace; font-weight: 700; font-size: 1.3rem; color: #1a1a1a;
    font-variation-settings: 'wdth' 90, 'wght' 700; line-height: 1; }
.st-l { font-size: 0.55rem; color: #999; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; margin-top: 2px; }

/* Label */
.lb { font-size: 0.6rem; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; color: #999; margin: 1rem 0 6px; }

/* Map */
.mf { border-radius: 10px; overflow: hidden; border: 1px solid #ddd; }
.mf iframe { border-radius: 10px; }
iframe[title="streamlit_folium.st_folium"] { height: 420px; }

/* Cards */
.cl { max-height: 70vh; overflow-y: auto; }
.cl::-webkit-scrollbar { width: 3px; } .cl::-webkit-scrollbar-thumb { background: #ccc; border-radius: 2px; }

.cd {
    background: white; border-radius: 8px; margin-bottom: 6px; border: 1px solid #e8e8e8;
    display: grid; grid-template-columns: 48px 1fr; overflow: hidden;
}
.cd-n { display: flex; align-items: center; justify-content: center; background: #fafaf8;
    border-right: 1px solid #eee; padding: 8px 2px;
    font-family: 'Datatype',monospace; font-weight: 700; font-size: 1.1rem; color: #2d6a4f;
    font-variation-settings: 'wdth' 85, 'wght' 700; }
.cd-b { padding: 7px 12px; }
.cd-t { font-weight: 700; font-size: 0.82rem; color: #1a1a1a; line-height: 1.25; }
.cd-m { font-size: 0.68rem; color: #666; line-height: 1.4; }
.cd-m b { color: #666; font-weight: 500; }
.cd-d { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 3px; vertical-align: middle; }
.cd-sep { margin: 0 2px; color: #bbb; }
.cd-cur { color: #999; }
.cd-fee { display: inline-block; font-size: 0.56rem; font-weight: 600; padding: 0 4px; border-radius: 3px; background: #fff3e0; color: #e65100; margin-left: 4px; vertical-align: middle; }
.cd-tags { display: flex; flex-wrap: wrap; gap: 2px; margin-top: 3px; }
.cd-tag { font-size: 0.52rem; font-weight: 600; padding: 1px 5px; border-radius: 3px; background: #f0efec; color: #888; }

/* Info buttons */
/* Expanders */
.stExpander { border: 1px solid #e0e0e0 !important; border-radius: 8px !important; background: white !important; }
.stExpander, .stExpander * { color: #333 !important; }
.stExpander summary span { color: #1a1a1a !important; font-weight: 600 !important; }
.stExpander a { color: #2d6a4f !important; text-decoration: underline !important; }

/* Force light mode on main content only (not sidebar) */
.stApp header { background: transparent !important; }
.main .stMarkdown, .main .stMarkdown p, .main .stMarkdown li, .main .stMarkdown span { color: #333 !important; }
.main .stSelectbox label, .main .stSlider label { color: #333 !important; }
.main [data-testid="stForm"] { background: white !important; border: 1px solid #e0e0e0 !important; border-radius: 8px !important; }
.main [data-testid="stForm"], .main [data-testid="stForm"] * { color: #333 !important; }
.main [data-testid="stForm"] a { color: #2d6a4f !important; }
.main [data-testid="stAlert"] { color: #333 !important; }
.main .stSelectbox > div > div { background: white !important; border: 1px solid #ddd !important; }

/* Footer */
.ft { text-align: center; padding: 1.5rem 0 0.5rem; font-size: 0.65rem; color: #bbb; line-height: 1.6; }

/* Desktop widen */
@media (min-width: 768px) {
    .block-container { max-width: 960px; }
    .hd-t { font-size: 2.6rem; }
    .map-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
}
</style>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════
# HEADER — renders IMMEDIATELY, visible while OSRM loads
# ══════════════════════════════════════════════════════════════════════
st.markdown(f"""<div class="hd">
    <div class="hd-t">Kayang Lakarin?</div>
    <div class="hd-s">Find the nearest place to run, walk, or exercise outdoors in Metro Manila.
    <strong>{len(AREAS)} parks and green spaces</strong> ranked by distance from you, with real road routes,
    commute costs, and air quality scores. Choose your starting point below.</div>
</div>""", unsafe_allow_html=True)

# ── Location selector — in main body, visible on mobile ──────────────
loc_keys = list(REFS.keys())
has_click = st.session_state.click_lat is not None
if has_click:
    clk_lbl = f"📌 Map pin ({st.session_state.click_lat:.4f}, {st.session_state.click_lng:.4f})"
    disp = [clk_lbl] + loc_keys
    didx = 0
else:
    disp = loc_keys
    didx = 0
    clk_lbl = None

st.markdown('<div class="lb">Where are you?</div>', unsafe_allow_html=True)
sel = st.selectbox("Starting from", disp, index=didx, label_visibility="collapsed")

if has_click and sel == clk_lbl:
    user_lat, user_lng = st.session_state.click_lat, st.session_state.click_lng
    if st.button("Clear pin", type="secondary"):
        st.session_state.click_lat = st.session_state.click_lng = None
        st.rerun()
elif sel == "Custom...":
    c1, c2 = st.columns(2)
    with c1: user_lat = st.number_input("Lat", value=14.5995, format="%.4f", step=0.001)
    with c2: user_lng = st.number_input("Lng", value=120.9842, format="%.4f", step=0.001)
else:
    user_lat, user_lng = REFS[sel]

# ── Info buttons ──────────────────────────────────────────────────────
with st.expander("How the numbers work"):
    st.markdown(f"""
Routes come from [OSRM](https://project-osrm.org/) (open source, uses OpenStreetMap road data).
OSRM returns free-flow travel times, so we apply Metro Manila traffic multipliers:
**x2.2 for jeepney** (frequent stops, loading/unloading, route indirection) and
**x1.6 for Grab** (traffic congestion, plus pickup wait time).

These are daytime averages. Rush hour (7-9am, 5-8pm) can add 30-50% more.
Late night or early morning will be faster than shown.

**Fares:** Jeepney base fare is P13 for the first 4 km, plus P1.80 per km after that (LTFRB 2024 rates).
Grab estimates use P45 base + P14/km, with a x0.85-1.35 surge range.

**Air quality** is scored 1-5 based on three factors: distance from major arterial roads
(EDSA, C-5, Commonwealth, etc.), park size in hectares, and vegetation type.
Forests and wetlands score higher than plazas. Select sites have manual overrides
from DENR monitoring data. These are estimates, not real-time readings.

When OSRM is unavailable, distances use a x1.35 straight-line-to-road multiplier
(typical for Metro Manila's road network).
    """)

with st.expander("Data sources"):
    st.markdown(f"""
**{len(AREAS)} outdoor areas** across all 16 Metro Manila cities plus Antipolo.

Sources: OpenStreetMap leisure/park features, Wikipedia's List of Parks in Metro Manila,
DENR protected area inventories, LGU park directories, and editorial coverage
from Rappler, GMA News, and Coconuts Manila. Coordinates verified against
Google Maps satellite imagery.

Air quality overrides for La Mesa Watershed, LPPCHEA Wetland, and Arroceros Forest
are based on published DENR monitoring data.

Live air quality readings:
[IQAir Manila](https://www.iqair.com/philippines/metro-manila/manila) ·
[DENR EMB](https://emb.gov.ph/)
    """)

# ══════════════════════════════════════════════════════════════════════
# SIDEBAR — advanced filters (collapsed on mobile)
# ══════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("""<div style="text-align:center;padding:1rem 0 0.5rem;">
        <div style="font-family:'Datatype','Outfit',sans-serif;font-weight:800;font-size:1.1rem;color:#fff;
                    font-variation-settings:'wdth' 100,'wght' 800;">Filters</div>
    </div>""", unsafe_allow_html=True)

    st.markdown("### Air Quality")
    min_aq = st.slider("Min", 1, 5, 3, label_visibility="collapsed",
                       help="5 = Forest or wetland, minimal traffic. 1 = Roadside, heavy exhaust exposure.")
    aq_d = {1: "Any", 2: "Fair or better", 3: "Moderate or better", 4: "Good or better", 5: "Excellent only"}
    st.caption(f"{aq_d[min_aq]} ({min_aq}/5)")

    st.markdown("### Activities")
    all_acts = sorted(set(a for p in AREAS for a in p["activities"]))
    sel_acts = st.multiselect("Activities", all_acts, default=[], label_visibility="collapsed")

    st.markdown("### City")
    all_cities = sorted(set(a["city"] for a in AREAS))
    sel_cities = st.multiselect("City", all_cities, default=["Quezon City"], label_visibility="collapsed")

    st.markdown("### Min Size")
    min_area = st.select_slider("Size", options=[0, 0.5, 1, 2, 5, 10, 20], value=0,
        format_func=lambda x: "Any" if x == 0 else f"{x}+ ha", label_visibility="collapsed")

    st.markdown("### Max Commute")
    max_time = st.slider("Min", 10, 120, 60, step=5, label_visibility="collapsed")
    st.caption(f"Up to {max_time} min by jeepney")

    st.markdown("### Routing")
    use_osrm = st.toggle("Road routes (OSRM)", value=True, help="Calculates actual road distances. Turn off for faster results using straight-line estimates.")
    show_walk = st.toggle("Walking routes on map", value=False)

    st.markdown("---")
    st.caption(f"{len(AREAS)} areas · OSM + DENR · OSRM routing · v6")

# ══════════════════════════════════════════════════════════════════════
# FILTER + ROUTE — header is already visible above
# ══════════════════════════════════════════════════════════════════════
pre = []
for a in AREAS:
    if a["air_quality"] < min_aq: continue
    if sel_acts and not any(x in a["activities"] for x in sel_acts): continue
    if sel_cities and a["city"] not in sel_cities: continue
    if a.get("area_ha", 0) < min_area: continue
    pre.append({**a, "straight_km": hav(user_lat, user_lng, a["lat"], a["lng"])})

osrm_ok = False
rd = {}
if use_osrm and pre:
    rd = batch_osrm(user_lat, user_lng, tuple((a["name"], a["lat"], a["lng"]) for a in pre))
    osrm_ok = any(v["driving"] is not None for v in rd.values())

results = []
for a in pre:
    nm = a["name"]
    if osrm_ok and nm in rd and rd[nm]["driving"]:
        c = commute_osrm(rd[nm]["driving"], rd[nm]["walking"])
    else:
        c = commute_fallback(a["straight_km"])
    if not c: continue
    jt = c["jeepney"]["time_min"]
    if jt > max_time: continue
    results.append({**a, "distance_km": c["road_distance_km"], "commute": c, "jeep_time": jt,
                    "has_route": c["driving_geometry"] is not None})
results.sort(key=lambda x: x["distance_km"])

# ══════════════════════════════════════════════════════════════════════
# STATS
# ══════════════════════════════════════════════════════════════════════
if results:
    near = results[0]
    avg = sum(r["jeep_time"] for r in results) / len(results)
    gaq = sum(1 for r in results if r["air_quality"] >= 4)
    near_col = "#2d6a4f" if near['jeep_time'] < 20 else ("#b8860b" if near['jeep_time'] < 40 else "#c0392b")
    st.markdown(f"""<div class="st-row">
        <div class="st-c"><div class="st-n">{len(results)}</div><div class="st-l">Spaces found</div></div>
        <div class="st-c" style="border-left:2px solid {near_col}"><div class="st-n" style="color:{near_col};font-size:1.5rem">{near['jeep_time']}</div><div class="st-l">Min nearest</div></div>
        <div class="st-c"><div class="st-n">{avg:.0f}</div><div class="st-l">Min avg</div></div>
        <div class="st-c"><div class="st-n">{gaq}</div><div class="st-l">Good air</div></div>
    </div>""", unsafe_allow_html=True)
else:
    st.markdown('<div style="text-align:center;padding:2rem 1rem;color:#999;font-size:0.85rem;">No spaces match your filters. Try widening your search in the sidebar.</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════
# MAP + RESULTS
# ══════════════════════════════════════════════════════════════════════
st.markdown('<div class="lb">Map <span style="font-weight:400;letter-spacing:0;text-transform:none;color:#aaa;font-size:0.6rem;">Tap anywhere to set your starting point</span></div>', unsafe_allow_html=True)

m = folium.Map(location=[user_lat, user_lng], zoom_start=12, tiles="CartoDB positron", control_scale=True)

# User pin
is_cp = st.session_state.click_lat is not None and user_lat == st.session_state.click_lat
if is_cp:
    uh = '<div style="position:relative;width:30px;height:30px;"><div style="position:absolute;inset:0;background:rgba(192,57,43,0.2);border-radius:50%;animation:p 1.5s ease-out infinite;"></div><div style="position:absolute;top:3px;left:3px;width:24px;height:24px;background:#c0392b;border:2px solid #fff;border-radius:50%;box-shadow:0 1px 4px rgba(0,0,0,0.3);"></div></div><style>@keyframes p{0%{transform:scale(1);opacity:.6}to{transform:scale(2);opacity:0}}</style>'
    folium.Marker([user_lat, user_lng], tooltip="Your pin", icon=folium.DivIcon(html=uh, icon_size=(30,30), icon_anchor=(15,15))).add_to(m)
else:
    folium.Marker([user_lat, user_lng], tooltip="You",
        icon=folium.DivIcon(html='<div style="width:24px;height:24px;background:#c0392b;border:2px solid #fff;border-radius:50%;box-shadow:0 1px 4px rgba(0,0,0,0.3);"></div>',
        icon_size=(24,24), icon_anchor=(12,12))).add_to(m)

for a in results:
    _, col = aq_lbl(a["air_quality"])
    c = a["commute"]
    fee = fee_str(a.get("entrance_fee"))
    fee_line = f"<br>{fee} entrance" if fee else ""
    folium.Marker([a["lat"], a["lng"]],
        tooltip=f'{a["name"]} — {a["jeep_time"]}m',
        popup=folium.Popup(f'<div style="font-family:Outfit,sans-serif;font-size:11px;min-width:160px;"><b>{a["name"]}</b><br>{a["city"]} · {a["distance_km"]:.1f} km<br>Jeepney {a["jeep_time"]} min, P{c["jeepney"]["cost"]}<br>Grab {c["grab"]["time_min"]} min, P{c["grab"]["cost_range"][0]}-{c["grab"]["cost_range"][1]}{fee_line}</div>', max_width=200),
        icon=folium.DivIcon(html=f'<div style="width:18px;height:18px;background:{col};border:2px solid #fff;border-radius:50%;box-shadow:0 1px 3px rgba(0,0,0,0.2);"></div>',
        icon_size=(18,18), icon_anchor=(9,9))).add_to(m)
    if c["driving_geometry"]:
        folium.PolyLine(c["driving_geometry"], color=col, weight=2.5, opacity=0.55).add_to(m)
        if show_walk and c.get("walking_geometry"):
            folium.PolyLine(c["walking_geometry"], color="#555", weight=1.5, opacity=0.35, dash_array="4 5").add_to(m)
    else:
        folium.PolyLine([[user_lat, user_lng], [a["lat"], a["lng"]]], color=col, weight=1, opacity=0.25, dash_array="5 5").add_to(m)

if not results:
    m.fit_bounds([[14.35, 120.90], [14.78, 121.17]])

st.markdown('<div class="mf">', unsafe_allow_html=True)
map_out = st_folium(m, width=None, height=420, returned_objects=["last_clicked"])
st.markdown('</div>', unsafe_allow_html=True)

if map_out and map_out.get("last_clicked"):
    nl, ng = round(map_out["last_clicked"]["lat"], 5), round(map_out["last_clicked"]["lng"], 5)
    if st.session_state.click_lat != nl or st.session_state.click_lng != ng:
        st.session_state.click_lat, st.session_state.click_lng = nl, ng
        st.rerun()

# ── Results list ──────────────────────────────────────────────────────
if results:
    src = "via road routes" if osrm_ok else "estimated distances"
    st.markdown(f'<div class="lb">{len(results)} results, {src}</div>', unsafe_allow_html=True)

    S = '<span class="cd-sep">&middot;</span>'
    AQ_TINT = {"#2d6a4f": "rgba(45,106,79,0.07)", "#b8860b": "rgba(184,134,11,0.07)", "#c0392b": "rgba(192,57,43,0.07)"}
    html = '<div class="cl">'
    for a in results:
        aq_txt, aq_col = aq_lbl(a["air_quality"])
        c = a["commute"]
        gl, gh = c["grab"]["cost_range"]
        wk = f'{S}{c["walk"]["time_min"]} min walk' if c.get("walk") else ""
        dk = f'{a["distance_km"]:.1f} km' if a["has_route"] else f'~{a["distance_km"]:.1f} km'
        fee = fee_str(a.get("entrance_fee"))
        fee_html = f'<span class="cd-fee">{fee}</span>' if fee else ""
        tg = "".join(f'<span class="cd-tag">{t}</span>' for t in a["activities"][:3])
        if len(a["activities"]) > 3: tg += f'<span class="cd-tag">+{len(a["activities"])-3}</span>'
        tint = AQ_TINT.get(aq_col, "#fafaf8")

        html += f'''<div class="cd">
            <div class="cd-n" style="background:{tint}">{a["jeep_time"]}<br><span style="font-size:0.42rem;font-weight:400;color:#aaa;letter-spacing:1px;">MIN</span></div>
            <div class="cd-b">
                <div class="cd-t">{a["name"]}{fee_html}</div>
                <div class="cd-m">{a["city"]}{S}{a["type"]}{S}{dk}{wk}</div>
                <div class="cd-m"><b>Jeepney</b> {a["jeep_time"]} min, <span class="cd-cur">P</span>{c["jeepney"]["cost"]}{S}<b>Grab</b> {c["grab"]["time_min"]} min, <span class="cd-cur">P</span>{gl}-{gh}</div>
                <div class="cd-m"><span class="cd-d" style="background:{aq_col}"></span>{aq_txt} - {a["aq_note"]}</div>
                <div class="cd-tags">{tg}</div>
            </div>
        </div>'''
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════
# SUBMIT
# ══════════════════════════════════════════════════════════════════════
with st.expander("Contribute a space"):
    st.markdown("Know an outdoor area we haven't listed? Help us grow the dataset. All submissions are reviewed before they go live.")
    with st.form("sub", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            sn = st.text_input("Name *", placeholder="e.g. Valenzuela People's Park")
            sc = st.selectbox("City *", [""] + sorted(set(a["city"] for a in AREAS)) + ["Other"])
        with c2:
            sty = st.selectbox("Type *", ["", "Urban Park", "Ecological Park", "Linear Park", "Community Park",
                "Riverfront Park", "Urban Forest", "Wetland / Ecotourism", "National Park",
                "Heritage Garden", "Fitness Park", "Adventure Park", "Coastal Promenade",
                "Open Space", "Urban Plaza", "Neighborhood Park", "Other"])
            sha = st.number_input("Area (ha)", 0.0, 500.0, 0.0, step=0.5)
            sfee = st.selectbox("Entrance fee", ["Free", "P5", "P10", "P20", "P30", "P50", "P100", "Other amount"])
        sfee_other = 0
        if sfee == "Other amount":
            sfee_other = st.number_input("Fee amount (PHP)", 0, 1000, 0, step=5)
        sco = ""
        if sc == "Other": sco = st.text_input("Specify city")
        lc1, lc2 = st.columns(2)
        with lc1: sla = st.number_input("Lat *", 14.0, 15.0, 14.55, format="%.5f", step=0.0001)
        with lc2: slo = st.number_input("Lng *", 120.5, 121.5, 121.0, format="%.5f", step=0.0001)
        st.markdown("**Activities**")
        acts = ["walking","jogging","cycling","hiking","swimming","bird watching","photography",
                "picnic","playground","yoga","skateboarding","nature walk","fishing","camping",
                "kayaking","events","dog walking","outdoor dining","sightseeing","other"]
        acols = st.columns(4)
        sa = [a for i, a in enumerate(acts) if acols[i%4].checkbox(a, key=f"a_{a}")]
        saq = st.select_slider("Air quality", [1,2,3,4,5], 3,
            format_func=lambda x: {1:"Poor",2:"Fair",3:"OK",4:"Good",5:"Excellent"}[x])
        sqr = st.text_area("Why this score?", placeholder="e.g. far from EDSA, old trees", max_chars=300)
        sev = st.text_input("Source link", placeholder="https://...")
        sno = st.text_area("Notes", max_chars=500)
        sem = st.text_input("Email (optional)")
        if st.form_submit_button("Submit", use_container_width=True):
            err = []
            if not sn or len(sn.strip()) < 3: err.append("Please enter the area name (at least 3 characters).")
            if not sc: err.append("Please select a city.")
            if sc == "Other" and not sco.strip(): err.append("Please specify which city.")
            if not sty: err.append("Please select the area type.")
            if sla == 14.55 and slo == 121.0: err.append("Please set the actual coordinates (the defaults are placeholders).")
            if not (14.3 <= sla <= 14.8): err.append("That latitude is outside Metro Manila (should be between 14.3 and 14.8).")
            if not (120.9 <= slo <= 121.3): err.append("That longitude is outside Metro Manila (should be between 120.9 and 121.3).")
            if not sa: err.append("Please select at least one activity.")
            if not sqr or len(sqr.strip()) < 10: err.append("Please explain your air quality score (at least 10 characters).")
            for ex in AREAS:
                if ex["name"].lower().strip() == sn.lower().strip():
                    err.append(f"'{sn}' is already in our database."); break
                if abs(ex["lat"]-sla) < 0.002 and abs(ex["lng"]-slo) < 0.002:
                    err.append(f"These coordinates are very close to '{ex['name']}'. Is this the same place?"); break
            if err:
                for e in err: st.error(e)
            else:
                fc = sco.strip() if sc == "Other" else sc
                fee_val = "free" if sfee == "Free" else (sfee_other if sfee == "Other amount" else int(sfee.replace("P", "")))
                sub = {
                    "name": sn.strip(),
                    "lat": sla,
                    "lng": slo,
                    "city": fc,
                    "type": sty,
                    "area_ha": sha,
                    "entrance_fee": fee_val,
                    "activities": sa,
                    "air_quality_user": saq,
                    "aq_reason": sqr.strip(),
                    "evidence_url": sev.strip(),
                    "notes": sno.strip(),
                    "email": sem.strip(),
                    "status": "pending_review"
                }
                try:
                    supabase = get_supabase()
                    supabase.table("submissions").insert(sub).execute()
                    st.success(f"Thank you! **{sn.strip()}** in {fc} has been submitted and is now in our review queue.")
                except Exception as e:
                    st.error(f"Failed to save submission. Please try again later. ({e})")

st.markdown(f"""<div class="ft">
    <strong>Kayang Lakarin?</strong><br>
    {len(AREAS)} outdoor areas across Metro Manila<br>
    Open data from OpenStreetMap. Routes by OSRM. Type set in Datatype and Outfit.
</div>""", unsafe_allow_html=True)
