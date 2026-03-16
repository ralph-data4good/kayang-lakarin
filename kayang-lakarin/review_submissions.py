#!/usr/bin/env python3
"""
Review community submissions for Lakad MNL.
Run: python review_submissions.py

Shows each pending submission, lets you approve/reject,
and merges approved entries into the main dataset.
"""

import json
import os
import sys
import math

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SUBMISSIONS_PATH = os.path.join(SCRIPT_DIR, "submissions.json")
DATA_PATH = os.path.join(SCRIPT_DIR, "outdoor_areas_data.json")

# ── Major roads for AQ scoring (same as generate_data.py) ───────────────────
MAJOR_ROADS = [
    (14.6571, 120.9839, 14.6218, 121.0555, "EDSA-N"),
    (14.6218, 121.0555, 14.5812, 121.0540, "EDSA-C"),
    (14.5812, 121.0540, 14.5547, 121.0244, "EDSA-S"),
    (14.5547, 121.0244, 14.5130, 121.0200, "EDSA-SS"),
    (14.5503, 121.0496, 14.5880, 121.0610, "C5-S"),
    (14.5880, 121.0610, 14.6218, 121.0750, "C5-C"),
    (14.6218, 121.0750, 14.6537, 121.0800, "C5-N"),
    (14.6350, 121.0200, 14.6510, 121.0494, "QuezonAve"),
    (14.6510, 121.0494, 14.7100, 121.0850, "Commonwealth"),
    (14.5500, 120.9830, 14.5831, 120.9794, "RoxasBlvd"),
    (14.5130, 121.0200, 14.4230, 121.0350, "SLEX"),
    (14.6218, 121.0750, 14.5860, 121.1650, "MarcosHwy"),
    (14.5600, 120.9900, 14.6000, 120.9880, "TaftAve"),
]

def haversine(lat1, lng1, lat2, lng2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlng/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def point_to_segment_dist_km(px, py, ax, ay, bx, by):
    dx, dy = bx-ax, by-ay
    if dx == 0 and dy == 0:
        return haversine(px, py, ax, ay)
    t = max(0, min(1, ((px-ax)*dx + (py-ay)*dy) / (dx*dx + dy*dy)))
    proj_x, proj_y = ax + t*dx, ay + t*dy
    return haversine(px, py, proj_x, proj_y)

def compute_aq(lat, lng, area_ha, park_type):
    min_road_dist = min(
        point_to_segment_dist_km(lat, lng, *road[:4])
        for road in MAJOR_ROADS
    )
    if min_road_dist > 2.0: base = 4.5
    elif min_road_dist > 1.0: base = 3.5
    elif min_road_dist > 0.5: base = 2.8
    elif min_road_dist > 0.2: base = 2.2
    else: base = 1.8

    if area_ha >= 20: base += 0.6
    elif area_ha >= 5: base += 0.3
    elif area_ha >= 2: base += 0.15

    t = park_type.lower()
    if any(w in t for w in ["forest", "ecological", "wetland", "nature"]): base += 0.8
    elif any(w in t for w in ["riverfront", "adventure"]): base += 0.3
    elif any(w in t for w in ["linear", "plaza", "pocket"]): base -= 0.2

    return max(1, min(5, round(base)))

def generate_aq_note(lat, lng, aq_score, area_ha, park_type):
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
    road = road_names.get(nearest_road, nearest_road)

    if aq_score >= 5:
        return f"Excellent air quality — far from major traffic, rich natural vegetation"
    elif aq_score >= 4:
        return f"Good tree cover and distance from {road} ({min_road_dist:.1f} km) — relatively clean air"
    elif aq_score >= 3:
        return f"Urban setting with moderate traffic exposure — {road} is {min_road_dist:.1f} km away"
    elif aq_score >= 2:
        return f"Close to {road} ({min_road_dist:.1f} km) — limited vegetation buffer"
    else:
        return f"High-traffic area near {road} — minimal green buffer"


def main():
    if not os.path.exists(SUBMISSIONS_PATH):
        print("No submissions file found. Nothing to review.")
        return

    with open(SUBMISSIONS_PATH) as f:
        submissions = json.load(f)

    pending = [s for s in submissions if s.get("status") == "pending_review"]
    if not pending:
        print("🎉 No pending submissions. All caught up!")
        return

    with open(DATA_PATH) as f:
        dataset = json.load(f)

    approved_count = 0
    rejected_count = 0

    for i, sub in enumerate(pending):
        print(f"\n{'='*60}")
        print(f"📋 Submission {i+1}/{len(pending)}")
        print(f"{'='*60}")
        print(f"  Name:        {sub['name']}")
        print(f"  City:        {sub['city']}")
        print(f"  Type:        {sub['type']}")
        print(f"  Coordinates: {sub['lat']}, {sub['lng']}")
        print(f"  Area:        {sub.get('area_ha', '?')} ha")
        print(f"  Activities:  {', '.join(sub.get('activities', []))}")
        print(f"  User AQ:     {sub.get('air_quality_user', '?')}/5")
        print(f"  AQ reason:   {sub.get('aq_reason', 'N/A')}")
        print(f"  Evidence:    {sub.get('evidence_url', 'None')}")
        print(f"  Notes:       {sub.get('notes', 'None')}")
        print(f"  Submitted:   {sub.get('submitted_at', '?')}")

        # Compute algorithmic AQ
        algo_aq = compute_aq(sub["lat"], sub["lng"], sub.get("area_ha", 1), sub["type"])
        print(f"\n  🌬️ Algorithmic AQ: {algo_aq}/5 (user said {sub.get('air_quality_user', '?')}/5)")
        print(f"  📍 Google Maps: https://maps.google.com/?q={sub['lat']},{sub['lng']}")

        while True:
            choice = input(f"\n  [A]pprove / [R]eject / [S]kip / [Q]uit? ").strip().lower()
            if choice in ('a', 'r', 's', 'q'):
                break
            print("  Please enter A, R, S, or Q")

        if choice == 'q':
            print("\nExiting. Progress saved.")
            break
        elif choice == 'a':
            aq_note = generate_aq_note(sub["lat"], sub["lng"], algo_aq, sub.get("area_ha", 1), sub["type"])
            new_entry = {
                "name": sub["name"],
                "lat": sub["lat"],
                "lng": sub["lng"],
                "city": sub["city"],
                "type": sub["type"],
                "air_quality": algo_aq,
                "aq_note": aq_note,
                "area_ha": sub.get("area_ha", 1),
                "activities": sub.get("activities", ["walking"]),
            }
            dataset.append(new_entry)
            sub["status"] = "approved"
            approved_count += 1
            print(f"  ✅ Approved! AQ set to {algo_aq}/5")
        elif choice == 'r':
            sub["status"] = "rejected"
            rejected_count += 1
            print(f"  ❌ Rejected.")
        else:
            print(f"  ⏭️ Skipped.")

    # Save updates
    with open(DATA_PATH, "w") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)
    with open(SUBMISSIONS_PATH, "w") as f:
        json.dump(submissions, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"✅ Done! Approved: {approved_count}, Rejected: {rejected_count}")
    print(f"   Dataset now has {len(dataset)} areas")
    if approved_count > 0:
        print(f"   Don't forget to commit & push:")
        print(f"   git add . && git commit -m 'Add {approved_count} community submissions' && git push")


if __name__ == "__main__":
    main()
