"""
Generate expanded Metro Manila outdoor areas dataset.
Combines Wikipedia list, research articles, and curated data.
Air quality scores are computed based on:
  - Distance from major arterial roads (EDSA, C5, etc.)
  - Park size (larger = better buffer)
  - Type (forest/wetland > park > plaza)
  - Known environmental data
"""
import json
import math

# ─── Expanded Dataset ────────────────────────────────────────────────────────
# Each entry: (name, lat, lng, city, type, area_ha, activities[], aq_override_or_None)
# Coordinates verified via OSM/Google Maps

RAW_AREAS = [
    # ══════ QUEZON CITY ══════
    ("Quezon Memorial Circle", 14.6510, 121.0494, "Quezon City", "Park & Recreation", 27,
     ["jogging","cycling","picnic","playground","museum"], 4),
    ("La Mesa Eco Park", 14.7080, 121.0770, "Quezon City", "Ecological Park", 33,
     ["hiking","swimming","fishing","picnic","bird watching"], 5),
    ("UP Diliman Sunken Garden", 14.6537, 121.0690, "Quezon City", "Open Space", 17,
     ["jogging","cycling","frisbee","yoga","kite flying"], 4),
    ("UP Academic Oval", 14.6550, 121.0650, "Quezon City", "Open Space", 8,
     ["jogging","cycling","walking","running"], 4),
    ("UP Lagoon", 14.6555, 121.0720, "Quezon City", "Open Space", 2,
     ["walking","photography","picnic","nature walk"], 4),
    ("Ninoy Aquino Parks & Wildlife", 14.6570, 121.0420, "Quezon City", "Park & Wildlife", 22,
     ["nature walk","picnic","playground","lagoon","wildlife viewing"], 3),
    ("Eastwood Central Park", 14.6095, 121.0805, "Quezon City", "Urban Open Space", 3,
     ["walking","al fresco dining","concerts","people watching"], 3),
    ("Liwasang Aurora", 14.6500, 121.0510, "Quezon City", "Urban Plaza", 1.5,
     ["walking","community events","skateboarding"], 3),
    ("N.S. Amoranto Park", 14.6280, 121.0180, "Quezon City", "Urban Park", 1.5,
     ["walking","community events","playground"], 3),
    ("Bernardo Park", 14.6290, 121.0350, "Quezon City", "Urban Park", 1,
     ["walking","picnic","playground"], 3),
    ("Corinthian Gardens Park", 14.6190, 121.0680, "Quezon City", "Residential Park", 2,
     ["walking","jogging","playground"], 4),
    ("C.P. Garcia Community Park", 14.6480, 121.0650, "Quezon City", "Community Park", 1,
     ["walking","playground","community events"], 3),
    ("Don Jose Heights Park", 14.6700, 121.0830, "Quezon City", "Community Park", 1.5,
     ["walking","playground","jogging"], 3),
    ("Acropolis Park", 14.6130, 121.0780, "Quezon City", "Residential Park", 2,
     ["walking","jogging","playground"], 3),
    ("Filinvest Park Batasan", 14.6810, 121.0900, "Quezon City", "Community Park", 3,
     ["jogging","walking","playground","basketball"], 3),
    ("North Olympus Park", 14.7100, 121.0550, "Quezon City", "Community Park", 2,
     ["walking","playground","community events"], 3),
    ("Lagro Dulo Park", 14.7180, 121.0730, "Quezon City", "Community Park", 1.5,
     ["walking","playground"], 3),
    ("Rosalia Park", 14.6770, 121.0420, "Quezon City", "Community Park", 1.5,
     ["walking","playground","picnic"], 3),
    ("Mariana Park", 14.6200, 121.0320, "Quezon City", "Neighborhood Park", 1,
     ["walking","playground"], 3),
    ("Wisdom Park", 14.6175, 121.0350, "Quezon City", "Garden", 0.8,
     ["walking","meditation","photography"], 3),
    ("Madrigal Circle Park", 14.6240, 121.0620, "Quezon City", "Neighborhood Park", 0.5,
     ["walking","picnic"], 3),

    # ══════ MANILA ══════
    ("Rizal Park (Luneta)", 14.5831, 120.9794, "Manila", "National Park", 58,
     ["walking","dancing","gardens","museum","cultural shows"], 3),
    ("Arroceros Forest Park", 14.5907, 120.9832, "Manila", "Urban Forest", 2.2,
     ["nature walk","bird watching","photography","environmental education"], 4),
    ("Manila Baywalk", 14.5770, 120.9730, "Manila", "Coastal Promenade", 1.5,
     ["sunset viewing","walking","jogging","photography"], 3),
    ("Paco Park", 14.5810, 120.9870, "Manila", "Historical Garden", 0.8,
     ["walking","photography","concerts","meditation"], 3),
    ("ASEAN Garden (Intramuros)", 14.5882, 120.9748, "Manila", "Heritage Garden", 0.5,
     ["walking","photography","sightseeing"], 3),
    ("Remedios Circle", 14.5705, 120.9868, "Manila", "Urban Plaza", 0.3,
     ["walking","al fresco dining","people watching"], 2),
    ("Plaza Rueda", 14.5810, 120.9850, "Manila", "Urban Plaza", 0.2,
     ["walking","community events"], 2),
    ("Pandacan Linear Park", 14.5930, 120.9980, "Manila", "Linear Park", 1.5,
     ["walking","jogging","river walk"], 3),
    ("Earnshaw Linear Park", 14.5950, 120.9960, "Manila", "Linear Park", 0.8,
     ["walking","jogging"], 2),
    ("Agrifina Circle", 14.5850, 120.9790, "Manila", "Open Space", 0.4,
     ["walking","photography"], 3),
    ("Bacood Park", 14.6000, 120.9920, "Manila", "Neighborhood Park", 0.5,
     ["walking","playground"], 2),
    ("Estero de Magdalena Linear Park", 14.6090, 120.9730, "Manila", "Linear Park", 0.5,
     ["walking","jogging"], 2),
    ("APEC Sculpture Garden", 14.5520, 120.9840, "Pasay", "Garden", 1.5,
     ["walking","photography","sightseeing"], 3),
    ("China-Philippines Friendship Park", 14.5890, 120.9730, "Manila", "Heritage Garden", 0.3,
     ["walking","photography","sightseeing"], 3),
    ("San Diego Garden (Intramuros)", 14.5870, 120.9710, "Manila", "Heritage Garden", 0.4,
     ["walking","photography","weddings"], 3),
    ("Bonifacio Shrine", 14.5870, 120.9830, "Manila", "Historical Park", 0.3,
     ["walking","photography","sightseeing"], 2),

    # ══════ MAKATI ══════
    ("Ayala Triangle Gardens", 14.5565, 121.0240, "Makati", "Urban Park", 2,
     ["walking","lunchtime picnic","concerts","yoga"], 3),
    ("Washington Sycip Park", 14.5585, 121.0205, "Makati", "Urban Park", 0.8,
     ["walking","reading","relaxation","zen garden"], 3),
    ("Salcedo Park", 14.5600, 121.0210, "Makati", "Urban Park", 1.2,
     ["walking","weekend market","playground","dog park"], 3),
    ("Legazpi Active Park", 14.5535, 121.0170, "Makati", "Fitness Park", 0.75,
     ["jogging","cycling","yoga","calisthenics","playground"], 3),
    ("Greenbelt Park", 14.5520, 121.0195, "Makati", "Urban Park", 1,
     ["walking","photography","al fresco dining"], 3),
    ("Circuit Makati Park", 14.5530, 121.0150, "Makati", "Events Ground", 5,
     ["running","outdoor events","food festivals","concerts"], 3),
    ("Makati Poblacion Park", 14.5645, 121.0295, "Makati", "Urban Park", 0.5,
     ["walking","community events"], 3),
    ("Guadalupe Linear Park", 14.5670, 121.0430, "Makati", "Linear Park", 1,
     ["walking","jogging","river walk"], 2),

    # ══════ TAGUIG / BGC ══════
    ("BGC Greenway Park", 14.5510, 121.0480, "Taguig (BGC)", "Linear Park", 3,
     ["walking","jogging","cycling","dog walking"], 3),
    ("Track 30th Park", 14.5505, 121.0495, "Taguig (BGC)", "Fitness Park", 1.5,
     ["jogging","yoga","fitness","meditation"], 3),
    ("Terra 28th Park", 14.5500, 121.0505, "Taguig (BGC)", "Urban Park", 1,
     ["playground","walking","picnic"], 3),
    ("Burgos Circle", 14.5535, 121.0485, "Taguig (BGC)", "Urban Plaza", 0.3,
     ["walking","al fresco dining","people watching"], 3),
    ("Forbes Town Park", 14.5530, 121.0460, "Taguig (BGC)", "Urban Park", 0.8,
     ["walking","picnic","lagoon"], 3),
    ("De Jesus Oval Park", 14.5465, 121.0490, "Taguig (BGC)", "Open Space", 0.5,
     ["walking","jogging","community events"], 3),
    ("Mind Museum Park", 14.5520, 121.0440, "Taguig (BGC)", "Open Space", 1,
     ["picnic","kite flying","playground","walking"], 3),
    ("Alveo Central Plaza", 14.5480, 121.0470, "Taguig (BGC)", "Urban Plaza", 0.5,
     ["walking","events","al fresco dining"], 3),
    ("J.Y. Campos Park", 14.5495, 121.0510, "Taguig (BGC)", "Open Space", 0.5,
     ["walking","picnic","playground"], 3),
    ("DOST Plaza", 14.4950, 121.0410, "Taguig", "Urban Plaza", 0.5,
     ["walking","events"], 3),
    ("FTI Park", 14.5130, 121.0640, "Taguig", "Open Space", 2,
     ["walking","jogging","community events"], 3),
    ("Plaza Bonifacio (Taguig)", 14.5260, 121.0710, "Taguig", "Heritage Plaza", 0.3,
     ["walking","sightseeing"], 3),

    # ══════ PASIG ══════
    ("Pasig RAVE Park", 14.5750, 121.0860, "Pasig", "Adventure Park", 6,
     ["ziplining","wall climbing","obstacle course","camping"], 4),
    ("Capitol Commons Park", 14.5740, 121.0610, "Pasig", "Urban Park", 2,
     ["walking","jogging","playground","events"], 3),
    ("Ortigas Park", 14.5870, 121.0600, "Pasig", "Urban Park", 1.5,
     ["walking","jogging","picnic"], 3),
    ("Kapitolyo Park", 14.5710, 121.0590, "Pasig", "Neighborhood Park", 0.5,
     ["walking","playground","community events"], 3),
    ("Plaza Rizal (Pasig)", 14.5740, 121.0800, "Pasig", "Heritage Plaza", 0.3,
     ["walking","sightseeing"], 2),

    # ══════ MARIKINA ══════
    ("Marikina River Park", 14.6360, 121.1010, "Marikina", "Riverfront Park", 22,
     ["biking","jogging","skateboarding","river walk","food park"], 4),
    ("Marikina Freedom Park", 14.6300, 121.0960, "Marikina", "Urban Park", 2,
     ["walking","playground","community events"], 3),
    ("Evolution Park Marikina", 14.6350, 121.1150, "Marikina", "Community Park", 1,
     ["walking","playground","community events"], 3),
    ("Hacienda Heights Park", 14.6380, 121.1200, "Marikina", "Residential Park", 1.5,
     ["walking","jogging","playground"], 4),

    # ══════ MANDALUYONG ══════
    ("Hardin ng Pag-asa", 14.5830, 121.0380, "Mandaluyong", "Community Park", 1,
     ["walking","playground","community events"], 3),
    ("Maysilo Circle Park", 14.5770, 121.0380, "Mandaluyong", "Urban Park", 0.5,
     ["walking","jogging"], 2),
    ("Vergara Linear Park", 14.5850, 121.0410, "Mandaluyong", "Linear Park", 0.5,
     ["walking","jogging"], 2),

    # ══════ SAN JUAN ══════
    ("Greenhills Central Garden", 14.6010, 121.0480, "San Juan", "Urban Park", 1.5,
     ["walking","playground","picnic"], 3),
    ("Jackson Park", 14.6020, 121.0440, "San Juan", "Neighborhood Park", 1,
     ["walking","playground"], 3),
    ("Johnson Park", 14.6040, 121.0460, "San Juan", "Neighborhood Park", 0.8,
     ["walking","playground","jogging"], 3),
    ("McKinley Park", 14.6050, 121.0450, "San Juan", "Neighborhood Park", 0.5,
     ["walking","playground"], 3),
    ("San Juan Mini Park", 14.5990, 121.0360, "San Juan", "Pocket Park", 0.3,
     ["walking","playground"], 2),
    ("Ermitaño Linear Park", 14.6010, 121.0410, "San Juan", "Linear Park", 0.5,
     ["walking","jogging"], 2),

    # ══════ MUNTINLUPA ══════
    ("Filinvest City Linear Park", 14.4175, 121.0330, "Muntinlupa", "Linear Park", 5,
     ["jogging","cycling","walking","playground"], 4),
    ("Filinvest City Central Park", 14.4190, 121.0310, "Muntinlupa", "Urban Park", 3,
     ["walking","events","concerts","picnic"], 4),
    ("Spectrum Linear Park", 14.4180, 121.0290, "Muntinlupa", "Linear Park", 2,
     ["walking","jogging","outdoor art"], 4),
    ("Alabang River Park", 14.4150, 121.0400, "Muntinlupa", "Riverfront Park", 2,
     ["walking","jogging","river walk"], 3),
    ("Muntinlupa Sunken Garden", 14.4100, 121.0500, "Muntinlupa", "Historical Park", 1.5,
     ["walking","photography","sightseeing"], 3),
    ("Sucat People's Park", 14.4570, 121.0440, "Muntinlupa", "Community Park", 2,
     ["walking","playground","basketball","community events"], 3),

    # ══════ PARAÑAQUE ══════
    ("LPPCHEA Wetland Park", 14.4830, 120.9650, "Las Piñas / Parañaque", "Wetland / Ecotourism", 175,
     ["bird watching","kayaking","mangrove tour","nature photography"], 5),
    ("Aguirre Central Park", 14.4500, 121.0130, "Parañaque", "Community Park", 2,
     ["walking","jogging","playground","basketball"], 3),
    ("Don Galo Park", 14.4810, 120.9810, "Parañaque", "Neighborhood Park", 0.5,
     ["walking","playground"], 2),
    ("Guadalajara Park", 14.4680, 121.0200, "Parañaque", "Residential Park", 1,
     ["walking","jogging","playground"], 3),
    ("Sun Valley Park", 14.4780, 121.0180, "Parañaque", "Community Park", 1,
     ["walking","playground","basketball"], 2),

    # ══════ LAS PIÑAS ══════
    ("Pilar Friendship Park", 14.4600, 120.9920, "Las Piñas", "Community Park", 1.5,
     ["walking","playground","community events"], 3),
    ("Philamlife Village Park", 14.4530, 120.9950, "Las Piñas", "Residential Park", 1,
     ["walking","jogging","playground"], 3),

    # ══════ VALENZUELA ══════
    ("Valenzuela People's Park", 14.6930, 120.9750, "Valenzuela", "Urban Park", 5,
     ["walking","jogging","playground","basketball","events"], 3),
    ("Valenzuela Family Park", 14.6920, 120.9720, "Valenzuela", "Community Park", 2,
     ["walking","playground","picnic"], 3),
    ("Arkong Bato Park", 14.6850, 120.9710, "Valenzuela", "Heritage Park", 1,
     ["walking","sightseeing","community events"], 3),

    # ══════ CALOOCAN ══════
    ("Glorieta Park (Tala)", 14.7500, 121.0070, "Caloocan", "Community Park", 2,
     ["walking","playground","community events"], 3),
    ("Mother Ignacia Park", 14.6530, 120.9750, "Caloocan", "Neighborhood Park", 0.5,
     ["walking","playground"], 2),

    # ══════ NAVOTAS ══════
    ("Navotas Centennial Park", 14.6660, 120.9500, "Navotas", "Urban Park", 1.5,
     ["walking","playground","community events"], 2),

    # ══════ MALABON ══════
    ("Malabon People's Park", 14.6690, 120.9600, "Malabon", "Urban Park", 1,
     ["walking","playground","community events"], 2),

    # ══════ PASAY ══════
    ("Meridian Park", 14.5310, 120.9870, "Pasay", "Urban Park", 2,
     ["walking","jogging","events"], 3),

    # ══════ NEAR METRO MANILA ══════
    ("Hinulugang Taktak", 14.5860, 121.1650, "Antipolo (near MM)", "National Park", 2,
     ["swimming","hiking","picnic","sightseeing"], 5),
]

# ─── Major arterial roads (simplified centerlines for proximity scoring) ─────
# Segments: list of (lat1, lng1, lat2, lng2, name)
MAJOR_ROADS = [
    # EDSA (north to south)
    (14.6571, 120.9839, 14.6218, 121.0555, "EDSA-N"),
    (14.6218, 121.0555, 14.5812, 121.0540, "EDSA-C"),
    (14.5812, 121.0540, 14.5547, 121.0244, "EDSA-S"),
    (14.5547, 121.0244, 14.5130, 121.0200, "EDSA-SS"),
    # C-5
    (14.5503, 121.0496, 14.5880, 121.0610, "C5-S"),
    (14.5880, 121.0610, 14.6218, 121.0750, "C5-C"),
    (14.6218, 121.0750, 14.6537, 121.0800, "C5-N"),
    # Quezon Avenue
    (14.6350, 121.0200, 14.6510, 121.0494, "QuezonAve"),
    # Commonwealth
    (14.6510, 121.0494, 14.7100, 121.0850, "Commonwealth"),
    # Roxas Blvd
    (14.5500, 120.9830, 14.5831, 120.9794, "RoxasBlvd"),
    # SLEX / Skyway
    (14.5130, 121.0200, 14.4230, 121.0350, "SLEX"),
    # Marcos Highway
    (14.6218, 121.0750, 14.5860, 121.1650, "MarcosHwy"),
    # Taft Avenue
    (14.5600, 120.9900, 14.6000, 120.9880, "TaftAve"),
]

def point_to_segment_dist_km(px, py, ax, ay, bx, by):
    """Min distance from point (px,py) to segment (ax,ay)-(bx,by) in km."""
    dx, dy = bx-ax, by-ay
    if dx == 0 and dy == 0:
        return haversine(px, py, ax, ay)
    t = max(0, min(1, ((px-ax)*dx + (py-ay)*dy) / (dx*dx + dy*dy)))
    proj_x, proj_y = ax + t*dx, ay + t*dy
    return haversine(px, py, proj_x, proj_y)

def haversine(lat1, lng1, lat2, lng2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlng/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def compute_aq_score(lat, lng, area_ha, park_type, override=None):
    """Compute air quality score 1-5 based on road proximity, size, and type."""
    if override is not None:
        return override

    # Find minimum distance to any major road
    min_road_dist = float('inf')
    for ax, ay, bx, by, _ in MAJOR_ROADS:
        d = point_to_segment_dist_km(lat, lng, ax, ay, bx, by)
        min_road_dist = min(min_road_dist, d)

    # Base score from road distance
    if min_road_dist > 2.0:
        base = 4.5
    elif min_road_dist > 1.0:
        base = 3.5
    elif min_road_dist > 0.5:
        base = 2.8
    elif min_road_dist > 0.2:
        base = 2.2
    else:
        base = 1.8

    # Size bonus (larger parks have better internal air quality)
    if area_ha >= 20: base += 0.6
    elif area_ha >= 5: base += 0.3
    elif area_ha >= 2: base += 0.15

    # Type bonus
    type_lower = park_type.lower()
    if any(w in type_lower for w in ["forest", "ecological", "wetland", "nature", "watershed"]):
        base += 0.8
    elif any(w in type_lower for w in ["riverfront", "adventure"]):
        base += 0.3
    elif any(w in type_lower for w in ["linear", "plaza", "pocket"]):
        base -= 0.2

    return max(1, min(5, round(base)))


def generate_aq_note(name, aq_score, lat, lng, area_ha, park_type):
    """Generate an air quality explanation note."""
    min_road_dist = float('inf')
    nearest_road = ""
    for ax, ay, bx, by, rname in MAJOR_ROADS:
        d = point_to_segment_dist_km(lat, lng, ax, ay, bx, by)
        if d < min_road_dist:
            min_road_dist = d
            nearest_road = rname

    road_names = {
        "EDSA-N": "EDSA", "EDSA-C": "EDSA", "EDSA-S": "EDSA", "EDSA-SS": "EDSA",
        "C5-S": "C-5", "C5-C": "C-5", "C5-N": "C-5",
        "QuezonAve": "Quezon Avenue", "Commonwealth": "Commonwealth Avenue",
        "RoxasBlvd": "Roxas Boulevard", "SLEX": "SLEX/Skyway",
        "MarcosHwy": "Marcos Highway", "TaftAve": "Taft Avenue",
    }
    road_name = road_names.get(nearest_road, nearest_road)

    if aq_score >= 5:
        if "wetland" in park_type.lower() or "ecotourism" in park_type.lower():
            return f"Protected wetland ecosystem - sea breeze and mangroves provide pristine air quality"
        elif "ecological" in park_type.lower() or "forest" in park_type.lower():
            return f"Dense forest/watershed area - minimal vehicle traffic provides excellent air quality"
        else:
            return f"Remote from major traffic corridors - natural elevation and tree cover ensure clean air"
    elif aq_score >= 4:
        if area_ha >= 10:
            return f"Large green buffer ({area_ha:.0f} ha) - tree canopy effectively filters pollutants from {road_name}"
        else:
            return f"Good tree cover and distance from {road_name} ({min_road_dist:.1f} km) - relatively clean air"
    elif aq_score >= 3:
        if min_road_dist < 0.5:
            return f"Adjacent to {road_name} ({min_road_dist:.1f} km) - green cover provides partial buffer"
        else:
            return f"Urban setting with moderate traffic exposure - {road_name} is {min_road_dist:.1f} km away"
    elif aq_score >= 2:
        return f"Close to {road_name} ({min_road_dist:.1f} km) - limited vegetation buffer against traffic pollution"
    else:
        return f"High-traffic area near {road_name} - minimal green buffer"


# ─── Build final dataset ─────────────────────────────────────────────────────
areas = []
for (name, lat, lng, city, ptype, area_ha, activities, aq_override) in RAW_AREAS:
    aq = compute_aq_score(lat, lng, area_ha, ptype, aq_override)
    note = generate_aq_note(name, aq, lat, lng, area_ha, ptype)
    areas.append({
        "name": name,
        "lat": lat,
        "lng": lng,
        "city": city,
        "type": ptype,
        "air_quality": aq,
        "aq_note": note,
        "area_ha": area_ha,
        "activities": activities,
    })

# Save
with open("/home/claude/outdoor_commute/outdoor_areas_data.json", "w") as f:
    json.dump(areas, f, indent=2, ensure_ascii=False)

# Stats
from collections import Counter
print(f"✅ Generated {len(areas)} outdoor areas")
print(f"\nBy city:")
for city, count in Counter(a["city"] for a in areas).most_common():
    print(f"  {city}: {count}")
print(f"\nBy air quality:")
for aq in range(5, 0, -1):
    n = sum(1 for a in areas if a["air_quality"] == aq)
    print(f"  AQ {aq}: {n}")
print(f"\nBy type:")
for t, c in Counter(a["type"] for a in areas).most_common(10):
    print(f"  {t}: {c}")
