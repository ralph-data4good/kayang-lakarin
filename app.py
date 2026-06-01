"""
Kayang Lakarin? v6
Mobile-first outdoor commute finder for Metro Manila.
"""
import streamlit as st
import folium
from streamlit_folium import st_folium
import math, json, time, os
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
_LOCAL_AREAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outdoor_areas_data.json")

def _normalize(areas):
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

@st.cache_data(ttl=300, show_spinner=False)
def load_areas():
    try:
        sb = get_supabase()
        resp = sb.table("outdoor_areas").select("*").execute()
        if resp.data:
            return _normalize(resp.data)
        raise ValueError("Supabase returned no rows")
    except Exception:
        with open(_LOCAL_AREAS, encoding="utf-8") as f:
            return _normalize(json.load(f))

AREAS = load_areas()

def aq_lbl(s):
    if s >= 4: return ("Good air", "#2d6a4f")
    if s >= 3: return ("Moderate air", "#b8860b")
    return ("Poor air", "#c0392b")

_MON = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
def reviewed_str(d):
    if not d: return ""
    try:
        parts = str(d).split("-")
        return f"{_MON[int(parts[1])]} {parts[0]}"
    except (IndexError, ValueError):
        return str(d)

def fee_str(fee):
    if isinstance(fee, (int, float)) and fee > 0: return f"P{int(fee)}"
    if isinstance(fee, str) and fee != "free":
        try:
            v = int(fee)
            if v > 0: return f"P{v}"
        except (ValueError, TypeError):
            pass
    return ""

# ── Icons (inline SVG) ───────────────────────────────────────────────
IC_SPACES = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="5"/><circle cx="16" cy="10" r="4"/><line x1="8" y1="13" x2="8" y2="21"/><line x1="16" y1="14" x2="16" y2="21"/><line x1="4" y1="21" x2="20" y2="21"/></svg>'
IC_NEAREST = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="14" cy="12" r="9"/><polyline points="14,7 14,12 18,14"/><circle cx="5" cy="5" r="1.5"/><path d="M5 8 L5 14 L3 18"/><path d="M5 11 L7 13"/><path d="M5 14 L7 18"/></svg>'
IC_AVG = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="4" cy="20" r="2"/><circle cx="20" cy="4" r="2"/><path d="M4 18 C4 10, 12 14, 12 8 C12 6, 16 4, 20 6"/></svg>'
IC_AIR = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M17 8 C8 10, 6 16, 4 21"/><path d="M17 8 C17 8, 18 3, 13 3 C8 3, 6 8, 10 10"/><line x1="2" y1="15" x2="8" y2="15"/><line x1="3" y1="18" x2="7" y2="18"/></svg>'
IC_JEEPNEY = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 16 L2 10 C2 8, 4 7, 6 7 L18 7 C20 7, 22 8, 22 10 L22 16"/><line x1="2" y1="16" x2="22" y2="16"/><line x1="2" y1="12" x2="22" y2="12"/><circle cx="6" cy="19" r="1.5"/><circle cx="18" cy="19" r="1.5"/><line x1="7.5" y1="19" x2="16.5" y2="19"/><rect x="9" y="4" width="6" height="3" rx="1"/></svg>'
IC_CAR = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 15 L3 15 C2 15, 1 14, 1 13 L1 11 L4 8 L8 6 L16 6 L20 8 L23 11 L23 13 C23 14, 22 15, 21 15 L19 15"/><line x1="7" y1="15" x2="17" y2="15"/><circle cx="6" cy="16.5" r="2"/><circle cx="18" cy="16.5" r="2"/></svg>'
IC_WALK = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="4" r="2"/><path d="M10 9 L14 9 L16 15 L13 15 L14 22"/><path d="M10 9 L8 15 L11 15 L10 22"/></svg>'
IC_JEEPNEY_POP = IC_JEEPNEY.replace('width="12" height="12"', 'width="14" height="14" style="vertical-align:middle;margin-right:2px"')
IC_CAR_POP = IC_CAR.replace('width="12" height="12"', 'width="14" height="14" style="vertical-align:middle;margin-right:2px"')

# ── Space-type glyphs (minimal, keyword-mapped, with a park default) ──
_TYPE_PATHS = {
    "water":   '<path d="M3 10 C6 7 9 13 12 10 C15 7 18 13 21 10"/><path d="M3 16 C6 13 9 19 12 16 C15 13 18 19 21 16"/>',
    "garden":  '<path d="M12 21 L12 11"/><path d="M12 13 C9 13 7 11 7 8 C10 8 12 10 12 13Z"/><path d="M12 11 C12 8 14 6 17 6 C17 9 15 11 12 11Z"/>',
    "forest":  '<path d="M12 3 L6.5 11 L9.5 11 L5.5 17 L18.5 17 L14.5 11 L17.5 11Z"/><line x1="12" y1="17" x2="12" y2="21"/>',
    "fitness": '<line x1="6" y1="12" x2="18" y2="12"/><line x1="5" y1="9" x2="5" y2="15"/><line x1="19" y1="9" x2="19" y2="15"/><line x1="8.5" y1="10" x2="8.5" y2="14"/><line x1="15.5" y1="10" x2="15.5" y2="14"/>',
    "plaza":   '<rect x="4" y="4" width="16" height="16" rx="2"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="12" y1="4" x2="12" y2="20"/>',
    "park":    '<circle cx="12" cy="8.5" r="5.5"/><line x1="12" y1="14" x2="12" y2="21"/>',
}
def type_key(t):
    tl = (t or "").lower()
    if "wetland" in tl or "coast" in tl or "river" in tl: return "water"
    if "garden" in tl: return "garden"
    if "forest" in tl or "tree" in tl or "wildlife" in tl or "ecolog" in tl: return "forest"
    if "fitness" in tl or "adventure" in tl: return "fitness"
    if "plaza" in tl or "open" in tl or "events" in tl: return "plaza"
    return "park"
def type_svg(t, color, size, sw=1.9):
    paths = _TYPE_PATHS[type_key(t)]
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round">{paths}</svg>')

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

/* Search box */
.main .stTextInput input {
    background: #fff !important; border: 1px solid #ddd !important; border-radius: 999px !important;
    padding: 11px 16px !important; font-size: 0.9rem !important; min-height: 44px;
}
.main .stTextInput input:focus { border-color: #2d6a4f !important; box-shadow: 0 0 0 2px rgba(45,106,79,0.12) !important; }

/* Filter chips (popover triggers) */
.chips + div [data-testid="stPopover"] button,
[data-testid="stPopover"] button {
    background: #fff !important; border: 1px solid #d8d2c4 !important; border-radius: 999px !important;
    color: #2f5d44 !important; font-weight: 600 !important; font-size: 0.72rem !important;
    min-height: 40px !important; padding: 6px 10px !important; box-shadow: none !important;
    white-space: normal !important; line-height: 1.1 !important;
}
[data-testid="stPopover"] button:hover { border-color: #2d6a4f !important; background: #f7faf8 !important; }
[data-testid="stHorizontalBlock"] { gap: 8px !important; }
.main .stSelectbox > div > div { min-height: 44px; display: flex; align-items: center; }

/* Header / app-bar */
.hd { background: #2f5d44; padding: 1.1rem 1.2rem; border-radius: 14px; margin-bottom: 0.85rem;
    box-shadow: 0 2px 12px rgba(47,93,68,0.18); }
.hd-bar { display: flex; align-items: center; gap: 9px; }
.hd-logo { display: flex; align-items: center; justify-content: center; width: 30px; height: 30px;
    background: rgba(188,211,95,0.20); border-radius: 9px; flex-shrink: 0; }
.hd-t { font-family: 'Datatype','Outfit',sans-serif; font-weight: 800; font-size: 1.6rem;
    color: #fff; line-height: 1; letter-spacing: -0.5px;
    font-variation-settings: 'wdth' 100, 'wght' 800; }
.hd-s { font-size: 0.78rem; color: rgba(255,255,255,0.72); line-height: 1.5; margin-top: 8px; }
.hd-s strong { color: #bcd35f; font-weight: 600; }

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
    background: white; border-radius: 12px; margin-bottom: 8px; border: 1px solid #ebe8e1;
    display: grid; grid-template-columns: 42px 1fr auto; gap: 11px; align-items: start;
    padding: 12px 13px; transition: border-color .15s, box-shadow .15s;
}
.cd:hover { border-color: #cdd8d1; box-shadow: 0 2px 10px rgba(27,67,50,0.06); }
.cd-av { width: 42px; height: 42px; border-radius: 12px; display: flex; align-items: center;
    justify-content: center; flex-shrink: 0; }
.cd-b { min-width: 0; }
.cd-t { font-weight: 700; font-size: 0.9rem; color: #1a1a1a; line-height: 1.2; }
.cd-m { font-size: 0.69rem; color: #666; line-height: 1.45; margin-top: 2px; }
.cd-m b { color: #666; font-weight: 500; }
.cd-time { text-align: right; flex-shrink: 0; padding-left: 2px; }
.cd-time-n { font-family: 'Datatype',monospace; font-weight: 700; font-size: 1.4rem; color: #2f5d44;
    line-height: 1; font-variation-settings: 'wdth' 90, 'wght' 700; }
.cd-time-l { font-size: 0.48rem; color: #aaa; text-transform: uppercase; letter-spacing: 1px;
    font-weight: 700; margin-top: 3px; }
.cd-d { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 3px; vertical-align: middle; }
.cd-sep { margin: 0 2px; color: #bbb; }
.cd-cur { color: #999; }
.cd-fee { display: inline-block; font-size: 0.56rem; font-weight: 600; padding: 0 4px; border-radius: 3px; background: #fff3e0; color: #e65100; margin-left: 4px; vertical-align: middle; }
.cd-tags { display: flex; flex-wrap: wrap; gap: 2px; margin-top: 3px; }
.cd-tag { font-size: 0.52rem; font-weight: 600; padding: 1px 5px; border-radius: 3px; background: #f0efec; color: #888; }
.cd-q { font-size: 0.52rem; font-weight: 600; letter-spacing: 0.3px; text-transform: uppercase; margin-left: 4px; vertical-align: middle; }
.cd-q-est { color: #aaa; }
.cd-q-meas { color: #2d6a4f; }
.cd-q-approx { color: #b8860b; }
.note { font-size: 0.62rem; color: #999; line-height: 1.45; margin: -2px 0 8px; }
.note b { color: #777; font-weight: 600; }
.cd-prov { font-size: 0.5rem; color: #bbb; letter-spacing: 0.3px; margin-top: 4px; text-transform: uppercase; font-weight: 600; }
.gap { font-size: 0.72rem; color: #7a4a00; line-height: 1.45; background: #fff8ec; border-left: 3px solid #b8860b; border-radius: 0 6px 6px 0; padding: 8px 12px; margin: 0 0 10px; }
.gap b { color: #5c3800; font-weight: 700; }

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
.main [data-testid="stForm"] input:not([type="checkbox"]),
.main [data-testid="stForm"] textarea { border: 1px solid #ccc !important; }
.st-c svg { display: block; margin: 0 auto 4px; }
.cd-m svg { vertical-align: middle; margin-right: 2px; }
.main [data-testid="stAlert"] { color: #333 !important; }
.main .stSelectbox > div > div { background: white !important; border: 1px solid #ddd !important; }

/* Footer */
.ft { text-align: center; padding: 1.5rem 0 0.5rem; font-size: 0.65rem; color: #bbb; line-height: 1.6; }

/* Desktop widen */
@media (min-width: 768px) {
    .block-container { max-width: 960px; }
    .hd { padding: 1.4rem 1.8rem; }
    .hd-t { font-size: 2.1rem; }
    .hd-logo { width: 36px; height: 36px; }
    .map-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
}
</style>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════
# HEADER — renders IMMEDIATELY, visible while OSRM loads
# ══════════════════════════════════════════════════════════════════════
st.markdown(f"""<div class="hd">
    <div class="hd-bar">
        <span class="hd-logo"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#bcd35f" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M11 20 C11 14, 8 8, 4 6 C4 12, 7 17, 11 20Z"/><path d="M13 20 C13 13, 16 7, 21 5 C21 12, 18 17, 13 20Z"/><line x1="12" y1="20" x2="12" y2="22"/></svg></span>
        <div class="hd-t">Kayang Lakarin?</div>
    </div>
    <div class="hd-s">The nearest place to run, walk, or exercise outdoors in Metro Manila -
    <strong>{len(AREAS)} parks and green spaces</strong> ranked by how far they really are from you,
    with road routes, commute costs, and air quality.</div>
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

# ── Search + filter chips (replaces sidebar) ─────────────────────────
st.markdown('<div class="lb">Find a park</div>', unsafe_allow_html=True)
q = st.text_input("Search parks", placeholder="Search parks by name", label_visibility="collapsed")

all_acts = sorted(set(x for p in AREAS for x in p["activities"]))
all_cities = sorted(set(a["city"] for a in AREAS))
aq_d = {1: "Any air", 2: "Fair or better", 3: "Moderate or better", 4: "Good or better", 5: "Excellent only"}

# Read previous values so chip labels reflect the current selection.
aq_v = st.session_state.get("f_aq", 3)
time_v = st.session_state.get("f_time", 60)
cities_v = st.session_state.get("f_cities", ["Quezon City"])
acts_v = st.session_state.get("f_acts", [])

st.markdown('<div class="chips">', unsafe_allow_html=True)
fc1, fc2, fc3, fc4 = st.columns(4)
with fc1:
    with st.popover(f"Air {aq_v}/5+", use_container_width=True):
        min_aq = st.slider("Minimum air quality", 1, 5, value=3, key="f_aq",
                           help="5 = forest or wetland, minimal traffic. 1 = roadside, heavy exhaust.")
        st.caption(f"{aq_d[min_aq]} ({min_aq}/5)")
with fc2:
    with st.popover(f"Max {time_v}m", use_container_width=True):
        max_time = st.slider("Max commute (min, jeepney)", 10, 120, value=60, step=5, key="f_time")
        st.caption(f"Up to {max_time} min by jeepney")
if not cities_v:
    city_lbl = "Add city +"
elif len(cities_v) == 1:
    city_lbl = f"{cities_v[0]} +"
else:
    city_lbl = f"{cities_v[0]} +{len(cities_v)-1}"
with fc3:
    with st.popover(city_lbl, use_container_width=True):
        sel_cities = st.multiselect("Cities", all_cities, default=["Quezon City"], key="f_cities",
                                    label_visibility="collapsed")
with fc4:
    with st.popover("Filters", use_container_width=True):
        st.markdown("**Activities**")
        sel_acts = st.multiselect("Activities", all_acts, default=[], key="f_acts",
                                  label_visibility="collapsed")
        st.markdown("**Minimum size**")
        min_area = st.select_slider("Size", options=[0, 0.5, 1, 2, 5, 10, 20], value=0,
            format_func=lambda x: "Any" if x == 0 else f"{x}+ ha", key="f_area", label_visibility="collapsed")
        st.markdown("**Routing**")
        use_osrm = st.toggle("Road routes (OSRM)", value=True, key="f_osrm",
            help="Calculates actual road distances. Turn off for faster straight-line estimates.")
        show_walk = st.toggle("Walking routes on map", value=False, key="f_walk")
st.markdown('</div>', unsafe_allow_html=True)

# ── Info buttons ──────────────────────────────────────────────────────
with st.expander("How the numbers work"):
    st.markdown(f"""
**Start here: this is a guide, not gospel.** Think of it as a smart estimate to help you
compare options and pick where to go - not a promise of exact times. The numbers are honest
about what they are: travel times and air quality are *modeled estimates*, and whether a
place actually feels good to reach depends on things no map can see - shade, sidewalks,
safety, weather, and whether you feel welcome there. We would rather tell you that up front.

**Getting there.** Routes come from [OSRM](https://project-osrm.org/), an open-source engine
built on OpenStreetMap. It gives free-flow driving times, so we adjust for real Metro Manila
conditions: **x2.2 for jeepney** (all those stops and detours) and **x1.6 for Grab**
(traffic, plus waiting for your ride). These are daytime averages - rush hour (7-9am, 5-8pm)
can add 30-50%, and a quiet early morning will beat what you see here.

**What it costs.** Jeepney fares follow the LTFRB 2024 rates: P13 for the first 4 km, then
P1.80 for every km after. Grab is estimated at P45 base plus P14/km, with a x0.85-1.35 range
to account for surge.

**Air quality, honestly.** We score each space 1-5 from three things we can measure well:
how far it sits from big roads (EDSA, C-5, Commonwealth), its size in hectares, and how green
it is - forests and wetlands breathe easier than concrete plazas. Most scores are estimates,
tagged `est.`. Three places - La Mesa, Arroceros, and the LPPCHEA Wetland - get a `measured`
tag because their scores lean on published DENR monitoring. None of these are live readings.

**How sure we are of the spot.** Most pins are checked against satellite imagery. Community
gardens and other grassroots spaces are pinned at the barangay or general area and tagged
`approx. location` - their edges are fluid and defined by the people who use them, which is
exactly the point.

**If routing is down,** we fall back to a straight-line estimate scaled by x1.35 (a fair guess
for Metro Manila's road grid), and mark those distances with a `~` so you know.
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

**Provenance and review.** Each entry carries its own source and a `Reviewed` date, shown
at the bottom of every card, so you can see where the information came from and how fresh
it is. The bulk of the dataset was last verified in March 2026; community-submitted spaces
are dated when they were reviewed. A map is not finished when it launches - keeping these
entries correct as parks, entrances, and routes change is ongoing data work, and the dates
are there to keep that honest.

Live air quality readings:
[IQAir Manila](https://www.iqair.com/philippines/metro-manila/manila) ·
[DENR EMB](https://emb.gov.ph/)
    """)

# ══════════════════════════════════════════════════════════════════════
# FILTER + ROUTE — header is already visible above
# ══════════════════════════════════════════════════════════════════════
ql = q.strip().lower() if q else ""
pre = []
for a in AREAS:
    if ql and ql not in a["name"].lower(): continue
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
        <div class="st-c">{IC_SPACES.format(color="#999")}<div class="st-n">{len(results)}</div><div class="st-l">Spaces found</div></div>
        <div class="st-c" style="border-left:2px solid {near_col}">{IC_NEAREST.format(color=near_col)}<div class="st-n" style="color:{near_col};font-size:1.5rem">{near['jeep_time']}</div><div class="st-l">Min nearest</div></div>
        <div class="st-c">{IC_AVG.format(color="#999")}<div class="st-n">{avg:.0f}</div><div class="st-l">Min avg</div></div>
        <div class="st-c">{IC_AIR.format(color="#2d6a4f")}<div class="st-n">{gaq}</div><div class="st-l">Good air</div></div>
    </div>""", unsafe_allow_html=True)
    disc = ("Travel times are <b>modeled daytime estimates</b> - rush hour runs slower. "
            "Air quality is a <b>modeled score</b>, not a live reading.")
    if not osrm_ok:
        disc += " Distances marked ~ are <b>straight-line approximations</b> (road routing unavailable)."
    st.markdown(f'<div class="note">{disc}</div>', unsafe_allow_html=True)

    gap_msg = ""
    if near["jeep_time"] >= 40:
        gap_msg = (f'<b>Access gap.</b> The nearest green space from here is <b>{near["jeep_time"]} min</b> '
                   f'away by jeepney. Green-space access is not evenly distributed across Metro Manila - '
                   f'who has a park within walking distance, and who has to travel for it?')
    elif gaq == 0:
        gap_msg = ('<b>Access gap.</b> No good-air green spaces are within reach from here - the closest '
                   'options sit near heavy traffic. Cleaner outdoor space is not equally available everywhere.')
    if gap_msg:
        st.markdown(f'<div class="gap">{gap_msg}</div>', unsafe_allow_html=True)
else:
    st.markdown('<div style="text-align:center;padding:2rem 1rem;color:#999;font-size:0.85rem;">No spaces match your filters. Try widening the filters above or clearing the search.</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════
# MAP + RESULTS
# ══════════════════════════════════════════════════════════════════════
st.markdown('<div class="lb">Map <span style="font-weight:500;letter-spacing:0;text-transform:none;color:#2d6a4f;font-size:0.6rem;background:rgba(45,106,79,0.08);padding:2px 6px;border-radius:4px;">Tap anywhere to set your starting point</span></div>', unsafe_allow_html=True)

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
    aq_txt, col = aq_lbl(a["air_quality"])
    c = a["commute"]
    fee = fee_str(a.get("entrance_fee"))
    fee_line = f"<br>{fee} entrance" if fee else ""
    aq_meth = "DENR measured" if a.get("aq_method") == "measured" else "estimated"
    aq_line = f'<br><span style="color:{col}">&#9679;</span> {aq_txt} <span style="color:#aaa">({aq_meth})</span>'
    approx_line = '<br><span style="color:#b8860b;font-size:10px;">approx. location</span>' if a.get("coord_confidence") == "approximate" else ""
    folium.Marker([a["lat"], a["lng"]],
        tooltip=f'{a["name"]} — {a["jeep_time"]}m',
        popup=folium.Popup(f'<div style="font-family:Outfit,sans-serif;font-size:11px;min-width:160px;"><b>{a["name"]}</b><br>{a["city"]} · {a["distance_km"]:.1f} km<br>{IC_JEEPNEY_POP.format(color="#666")} {a["jeep_time"]} min, P{c["jeepney"]["cost"]}<br>{IC_CAR_POP.format(color="#666")} {c["grab"]["time_min"]} min, P{c["grab"]["cost_range"][0]}-{c["grab"]["cost_range"][1]}{aq_line}{fee_line}{approx_line}</div>', max_width=200),
        icon=folium.DivIcon(html=f'<div style="width:24px;height:24px;background:{col};border:2px solid #fff;border-radius:50%;box-shadow:0 1px 3px rgba(0,0,0,0.25);display:flex;align-items:center;justify-content:center;">{type_svg(a["type"], "#fff", 13, sw=2)}</div>',
        icon_size=(24,24), icon_anchor=(12,12))).add_to(m)
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
        wk = f'{S}{IC_WALK.format(color="#999")} {c["walk"]["time_min"]} min walk' if c.get("walk") else ""
        dk = f'{a["distance_km"]:.1f} km' if a["has_route"] else f'~{a["distance_km"]:.1f} km'
        fee = fee_str(a.get("entrance_fee"))
        fee_html = f'<span class="cd-fee">{fee}</span>' if fee else ""
        tg = "".join(f'<span class="cd-tag">{t}</span>' for t in a["activities"][:3])
        if len(a["activities"]) > 3: tg += f'<span class="cd-tag">+{len(a["activities"])-3}</span>'
        tint = AQ_TINT.get(aq_col, "#fafaf8")
        aq_q = ('<span class="cd-q cd-q-meas" title="From published DENR monitoring data">measured</span>'
                if a.get("aq_method") == "measured"
                else '<span class="cd-q cd-q-est" title="Modeled estimate, not a live reading">est.</span>')
        approx = f'{S}<span class="cd-q cd-q-approx" title="Mapped to barangay or centroid level">approx. location</span>' if a.get("coord_confidence") == "approximate" else ""
        rev = reviewed_str(a.get("last_reviewed"))
        prov_bits = []
        if rev: prov_bits.append(f"Reviewed {rev}")
        if a.get("source"): prov_bits.append(a["source"])
        prov = f'<div class="cd-prov">{" &middot; ".join(prov_bits)}</div>' if prov_bits else ""

        glyph = type_svg(a["type"], aq_col, 20)
        html += f'''<div class="cd">
            <div class="cd-av" style="background:{tint}">{glyph}</div>
            <div class="cd-b">
                <div class="cd-t">{a["name"]}{fee_html}</div>
                <div class="cd-m">{a["city"]}{S}{a["type"]}{S}{dk}{wk}{approx}</div>
                <div class="cd-m">{IC_JEEPNEY.format(color="#666")} {a["jeep_time"]} min, <span class="cd-cur">P</span>{c["jeepney"]["cost"]}{S}{IC_CAR.format(color="#666")} {c["grab"]["time_min"]} min, <span class="cd-cur">P</span>{gl}-{gh}</div>
                <div class="cd-m"><span class="cd-d" style="background:{aq_col}"></span>{aq_txt} {aq_q} - {a["aq_note"]}</div>
                <div class="cd-tags">{tg}</div>{prov}
            </div>
            <div class="cd-time"><div class="cd-time-n">{a["jeep_time"]}</div><div class="cd-time-l">min</div></div>
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
                "Community Garden", "Riverfront Park", "Urban Forest", "Wetland / Ecotourism", "National Park",
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
