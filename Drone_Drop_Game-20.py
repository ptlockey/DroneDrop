# drone_drop_game.py

import streamlit as st
import folium
from streamlit_folium import st_folium
import random
import math
import numpy as np
import geopandas as gpd
from shapely.geometry import shape, Point
import fiona
import csv
from datetime import datetime

# ──────────────────────────────────────────────────────────────────────────────
# SETTINGS
# ──────────────────────────────────────────────────────────────────────────────
VECTOR_SCALE = 4    # pixels per m/s for arrow length
MAP_SIZE     = 700  # map will be 700×700 px square (fits a 1080px screen)

# Base (Hard) bullseye radii (in meters) and base point awards:
BASE_RADII  = [3, 10, 30]
BASE_POINTS = [2500, 1000, 100]
# ──────────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
# LOAD “naturalearth_cities” & “naturalearth_lowres” FOR LAND‐ONLY / CITY SAMPLING
# ──────────────────────────────────────────────────────────────────────────────
_cities_gdf    = None
_use_land_check = False
_land_features = []

try:
    # 1) built‐in “naturalearth_cities” for random city picks
    cities_path = gpd.datasets.get_path("naturalearth_cities")
    _cities_gdf = gpd.read_file(cities_path)

    # 2) built‐in “naturalearth_lowres” for land‐only fallback
    land_shp = gpd.datasets.get_path("naturalearth_lowres")
    with fiona.open(land_shp) as src:
        _land_features = list(src)
    _use_land_check = True

except Exception:
    _cities_gdf = None
    try:
        land_shp = gpd.datasets.get_path("naturalearth_lowres")
        with fiona.open(land_shp) as src:
            _land_features = list(src)
        _use_land_check = True
    except Exception:
        _land_features = []
        _use_land_check = False


def get_random_land_point():
    """
    Return (lat, lon) that falls over land (using lowres shapefile) if possible;
    otherwise returns a random lat/lon anywhere.
    """
    if not _use_land_check or not _land_features:
        return random.uniform(-90.0, 90.0), random.uniform(-180.0, 180.0)

    while True:
        lat = random.uniform(-90.0, 90.0)
        lon = random.uniform(-180.0, 180.0)
        pt = Point(lon, lat)
        for feat in _land_features:
            geom = shape(feat["geometry"])
            if geom.contains(pt):
                return lat, lon


def get_random_city_point():
    """
    Return (lat, lon) of a random city from “naturalearth_cities” if available;
    otherwise fallback to get_random_land_point().
    """
    if _cities_gdf is not None and not _cities_gdf.empty:
        row = _cities_gdf.sample(n=1).iloc[0]
        return float(row.geometry.y), float(row.geometry.x)
    else:
        return get_random_land_point()


# ──────────────────────────────────────────────────────────────────────────────
# TRAJECTORY COMPUTATION (drag, density, wind shear; CdA ≤ 0.1)
# ──────────────────────────────────────────────────────────────────────────────
def displacement_to_latlon(lat0, lon0, dx, dy, *, dist=None, bearing=None):
    """Convert local ENU displacement (meters) into lat/lon using great-circle math."""
    R_earth = 6_371_000.0

    if dist is None:
        dist = math.hypot(dx, dy)
    if dist == 0.0:
        return lat0, lon0

    lat0_rad = math.radians(lat0)
    lon0_rad = math.radians(lon0)
    if bearing is None:
        bearing = math.atan2(dx, dy)
    angular_distance = dist / R_earth

    sin_lat1 = (
        math.sin(lat0_rad) * math.cos(angular_distance)
        + math.cos(lat0_rad) * math.sin(angular_distance) * math.cos(bearing)
    )
    sin_lat1 = max(-1.0, min(1.0, sin_lat1))
    lat1_rad = math.asin(sin_lat1)

    lon1_rad = lon0_rad + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(lat0_rad),
        math.cos(angular_distance) - math.sin(lat0_rad) * math.sin(lat1_rad),
    )

    lon1_rad = (lon1_rad + math.pi) % (2 * math.pi) - math.pi

    return math.degrees(lat1_rad), math.degrees(lon1_rad)


def compute_trajectory(lat0, lon0):
    """
    Compute realistic drop trajectory. Returns:
      (lat1, lon1, xs, ys, zs, ts_list, vhs_list, vzs_list, dist, bearing_deg)

    Reads from session_state keys:
      surface_temp_c, surface_pressure_mb, wind_dir, wind_speed,
      drone_heading, drone_speed, initial_height, dt, mass, CdA, h_ref, alpha
    """
    surface_temp_c     = st.session_state["surface_temp_c"]
    surface_pressure_mb = st.session_state["surface_pressure_mb"]
    wind_dir           = st.session_state["wind_dir"]       # “from” heading
    wind_speed         = st.session_state["wind_speed"]
    init_dir           = st.session_state["drone_heading"]
    v0                 = st.session_state["drone_speed"]
    initial_height     = st.session_state["initial_height"]
    dt                 = st.session_state["dt"]
    mass               = st.session_state["mass"]
    CdA                = st.session_state["CdA"]
    h_ref              = st.session_state["h_ref"]
    alpha              = st.session_state["alpha"]

    g = 9.80665
    R = 287.05
    L = 0.0065

    temp_k = surface_temp_c + 273.15
    pres0   = surface_pressure_mb * 100.0  # mb → Pa

    # Convert “wind FROM” → “wind TO” direction
    wind_to = (wind_dir + 180.0) % 360.0
    wind_unit = np.array([
        math.sin(math.radians(wind_to)),
        math.cos(math.radians(wind_to))
    ])

    # Drone’s initial horizontal velocity [east, north]
    theta0 = math.radians(init_dir)
    v_h = np.array([v0 * math.sin(theta0), v0 * math.cos(theta0)])
    v_z = 0.0

    pos = np.zeros(2)  # [east, north] in meters
    z = initial_height
    t = 0.0

    xs, ys, zs, ts_list, vhs_list, vzs_list = [], [], [], [], [], []

    while z >= 0:
        dloc = dt / 10.0 if z < 10.0 else dt

        temp = temp_k - L * z
        pres = pres0 * (1 - (L * z) / temp_k) ** (g / (R * L))
        rho = pres / (R * temp)
        u_term = math.sqrt(2.0 * mass * g / (rho * CdA))
        uz = wind_speed * (max(z, h_ref) / h_ref) ** alpha

        wind_vec = uz * wind_unit  # [east, north]
        rel = np.array([wind_vec[0] - v_h[0], wind_vec[1] - v_h[1], -v_z])
        rm = np.linalg.norm(rel)
        k_drag = rho * CdA / (2.0 * mass)
        a = k_drag * rm * rel
        a_h, a_z = a[:2], -g + a[2]

        # Horizontal update + cap
        v_h += a_h * dloc
        speed_h = np.linalg.norm(v_h)
        if speed_h > uz and uz > 0:
            v_h = (v_h / speed_h) * uz

        # Vertical update + cap
        v_z += a_z * dloc
        if abs(v_z) > u_term and u_term > 0:
            v_z = math.copysign(u_term, v_z)

        pos += v_h * dloc
        z += v_z * dloc
        t += dloc

        xs.append(pos[0])
        ys.append(pos[1])
        zs.append(z)
        ts_list.append(t)
        vhs_list.append(math.hypot(v_h[0], v_h[1]))
        vzs_list.append(abs(v_z))

    dx_final, dy_final = xs[-1], ys[-1]
    dist = math.hypot(dx_final, dy_final)
    bearing_rad = math.atan2(dx_final, dy_final)
    bearing_deg = (math.degrees(bearing_rad) + 360.0) % 360.0

    lat1, lon1 = displacement_to_latlon(
        lat0,
        lon0,
        dx_final,
        dy_final,
        dist=dist,
        bearing=bearing_rad,
    )

    return lat1, lon1, xs, ys, zs, ts_list, vhs_list, vzs_list, dist, bearing_deg


# ──────────────────────────────────────────────────────────────────────────────
# NEW ROUND: pick random city (or land), randomize environment + drone params
# ──────────────────────────────────────────────────────────────────────────────
def new_round():
    lat, lon = get_random_city_point()
    st.session_state["start_lat"] = lat
    st.session_state["start_lon"] = lon

    st.session_state["surface_temp_c"]     = random.uniform(-20.0, 40.0)
    st.session_state["surface_pressure_mb"] = random.uniform(950.0, 1050.0)
    st.session_state["wind_speed"]         = random.uniform(0.0, 40.0)
    st.session_state["wind_dir"]           = random.uniform(0.0, 359.0)
    st.session_state["drone_speed"]        = random.uniform(0.0, 30.0)
    st.session_state["drone_heading"]      = random.uniform(0.0, 359.0)
    st.session_state["initial_height"]     = random.uniform(0.0, 1000.0)
    st.session_state["mass"]               = 1.0
    st.session_state["CdA"]                = random.uniform(0.01, 0.1)
    st.session_state["h_ref"]              = 10.0
    st.session_state["alpha"]              = 0.2
    st.session_state["dt"]                 = 0.01

    # reset previous-round state
    st.session_state["guess"]         = None
    st.session_state["impact"]        = None
    st.session_state["trajectory_xy"] = None
    st.session_state["round_distance"] = None
    st.session_state["bearing"]       = None
    st.session_state["error_dist"]    = None
    st.session_state["round_points"]  = None
    st.session_state["scored"]        = False


# Initialize once
if "initialized" not in st.session_state:
    st.session_state["initialized"] = True
    st.session_state["score"]       = 0
    new_round()


# ──────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG & TITLE
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Drone Drop Game", layout="wide")

# Title flush at top with minimal margin
st.markdown(
    '<div style="font-size:24px; font-weight:bold; text-align:center; margin-bottom:4px;">'
    '🚁 Drone Drop Game</div>',
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────────────────────────────────────
# LEFT SIDEBAR: CONTROLS, DIFFICULTY, ENVIRONMENT & SCORE
# ──────────────────────────────────────────────────────────────────────────────
st.sidebar.header("🏷️ Controls")
if st.sidebar.button("Next Drop"):
    new_round()
if st.sidebar.button("Exit & Save"):
    try:
        with open("high_scores.csv", "a", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([datetime.now().isoformat(), st.session_state["score"]])
        st.sidebar.success("✅ Score saved")
    except Exception as e:
        st.sidebar.error(f"Error saving score: {e}")

st.sidebar.markdown("---")

# Difficulty radio (compact)
if "difficulty" not in st.session_state:
    st.session_state["difficulty"] = "Hard"
st.sidebar.markdown("<div style='margin-bottom:4px; font-weight:bold;'>🎚️ Difficulty</div>", unsafe_allow_html=True)
st.session_state["difficulty"] = st.sidebar.radio(
    "", ["Easy", "Medium", "Hard"],
    index=["Easy", "Medium", "Hard"].index(st.session_state["difficulty"])
)

st.sidebar.markdown("---")

# Environment & Score (compact)
st.sidebar.header("🏷️ Environment & Score")
colA, colB = st.sidebar.columns(2)
with colA:
    st.write(f"**Score:** {st.session_state['score']}")
    st.write(f"T₀: {st.session_state['surface_temp_c']:.0f} °C")
    st.write(f"P₀: {st.session_state['surface_pressure_mb']:.0f} mb")
    st.write(f"Wind from: {st.session_state['wind_dir']:.0f}°")
with colB:
    st.write(" ")
    st.write(f"Wind spd: {st.session_state['wind_speed']:.0f} m/s")
    st.write(f"Dr Hdg: {st.session_state['drone_heading']:.0f}°")
    st.write(f"Dr Spd: {st.session_state['drone_speed']:.0f} m/s")
    st.write(f"Alt: {st.session_state['initial_height']:.0f} m")
    st.write(f"CdA: {st.session_state['CdA']:.2f} m²")
    st.write(f"Mass: {st.session_state['mass']:.1f} kg")


# ──────────────────────────────────────────────────────────────────────────────
# DETERMINE BULLSEYE RADII & POINT AWARDS FOR SELECTED DIFFICULTY
# ──────────────────────────────────────────────────────────────────────────────
difficulty = st.session_state["difficulty"]
if difficulty == "Easy":
    # Easy now 50% larger than the old 10× → 10×1.5 = 15×
    size_factor   = 15.0
    points_factor = 0.1
elif difficulty == "Medium":
    # Medium now 50% larger than old 3× → 3×1.5 = 4.5×
    size_factor   = 4.5
    points_factor = 1.0 / 3.0
else:  # Hard
    size_factor   = 1.0
    points_factor = 1.0

R1 = BASE_RADII[0] * size_factor
R2 = BASE_RADII[1] * size_factor
R3 = BASE_RADII[2] * size_factor

P1 = int(BASE_POINTS[0] * points_factor)
P2 = int(BASE_POINTS[1] * points_factor)
P3 = int(BASE_POINTS[2] * points_factor)


# ──────────────────────────────────────────────────────────────────────────────
# MAIN AREA: Two columns—Map (wide) and Vector boxes (right)
# ──────────────────────────────────────────────────────────────────────────────
col_map, col_vecs = st.columns((3, 1))

# ──────────────────────────────────────────────────────────────────────────────
# CENTER COLUMN: SQUARE MAP + SINGLE-CLICK LOGIC
# ──────────────────────────────────────────────────────────────────────────────
with col_map:
    start_lat = st.session_state["start_lat"]
    start_lon = st.session_state["start_lon"]

    # 1) If no guess yet, draw bare square map and wait for a single click
    if st.session_state["guess"] is None:
        base_map = folium.Map(
            location=[start_lat, start_lon],
            zoom_start=16,
            tiles="OpenStreetMap",
            control_scale=True,
        )
        folium.Marker(
            [start_lat, start_lon],
            tooltip="Drone Start",
            icon=folium.Icon(icon="plane", prefix="fa", color="blue"),
        ).add_to(base_map)

        map_data = st_folium(
            base_map,
            width=MAP_SIZE,
            height=MAP_SIZE,
            returned_objects=["last_clicked"],
        )

        if map_data and map_data["last_clicked"]:
            lat_clicked = map_data["last_clicked"]["lat"]
            lon_clicked = map_data["last_clicked"]["lng"]
            st.session_state["guess"] = (lat_clicked, lon_clicked)

            # Immediately compute trajectory
            (
                lat1,
                lon1,
                xs,
                ys,
                zs,
                ts_list,
                vhs_list,
                vzs_list,
                impact_dist,
                bearing_deg,
            ) = compute_trajectory(start_lat, start_lon)

            st.session_state["impact"] = (lat1, lon1)
            st.session_state["trajectory_xy"] = list(zip(xs, ys))
            st.session_state["round_distance"] = impact_dist
            st.session_state["bearing"] = bearing_deg

            # Compute error (haversine) between guess & impact
            def haversine(coord1, coord2):
                R = 6371000  # Earth radius in meters
                lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
                lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
                dlat = lat2 - lat1
                dlon = lon2 - lon1
                a = (
                    math.sin(dlat / 2) ** 2
                    + math.cos(lat1)
                    * math.cos(lat2)
                    * math.sin(dlon / 2) ** 2
                )
                c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                return R * c

            error_dist = haversine(st.session_state["guess"], st.session_state["impact"])
            st.session_state["error_dist"] = error_dist

            # Award points based on R1, R2, R3
            if error_dist <= R1:
                pts = P1
            elif error_dist <= R2:
                pts = P2
            elif error_dist <= R3:
                pts = P3
            else:
                pts = 0

            st.session_state["score"] += pts
            st.session_state["round_points"] = pts
            st.session_state["scored"] = True
            # Now guess & trajectory_xy exist → draw overlay next

    # 2) If guess exists → draw overlay: trajectory + bullseye + impact
    if (
        st.session_state["guess"] is not None
        and st.session_state["trajectory_xy"] is not None
    ):
        overlay_map = folium.Map(
            location=[start_lat, start_lon],
            zoom_start=16,
            tiles="OpenStreetMap",
            control_scale=True,
        )
        folium.Marker(
            [start_lat, start_lon],
            tooltip="Drone Start",
            icon=folium.Icon(icon="plane", prefix="fa", color="blue"),
        ).add_to(overlay_map)

        # Curved green trajectory
        trajectory_xy = st.session_state["trajectory_xy"]
        lat_lon_points = [
            list(displacement_to_latlon(start_lat, start_lon, x, y))
            for x, y in trajectory_xy
        ]
        folium.PolyLine(
            lat_lon_points,
            color="green",
            weight=3,
            tooltip="Payload Trajectory",
        ).add_to(overlay_map)

        # Draw bullseye circles (use R1, R2, R3)
        guess_lat, guess_lon = st.session_state["guess"]
        folium.Circle(
            location=[guess_lat, guess_lon],
            radius=R1,
            color="red",
            fill=True,
            fill_opacity=0.4,
        ).add_to(overlay_map)
        folium.Circle(
            location=[guess_lat, guess_lon],
            radius=R2,
            color="yellow",
            fill=True,
            fill_opacity=0.3,
        ).add_to(overlay_map)
        folium.Circle(
            location=[guess_lat, guess_lon],
            radius=R3,
            color="blue",
            fill=True,
            fill_opacity=0.2,
        ).add_to(overlay_map)

        # Actual impact marker + dashed line from start→impact
        impact_lat, impact_lon = st.session_state["impact"]
        folium.Marker(
            [impact_lat, impact_lon],
            tooltip="Actual Impact",
            icon=folium.Icon(icon="times", prefix="fa", color="black"),
        ).add_to(overlay_map)
        folium.PolyLine(
            [[start_lat, start_lon], [impact_lat, impact_lon]],
            color="black",
            dash_array="5,5",
        ).add_to(overlay_map)

        st_folium(
            overlay_map,
            width=MAP_SIZE,
            height=MAP_SIZE,
        )


# ──────────────────────────────────────────────────────────────────────────────
# RIGHT COLUMN: WIND & DRONE VECTOR BOXES (tight margins)
# ──────────────────────────────────────────────────────────────────────────────
with col_vecs:
    # Wind Vector Box
    st.markdown(
        '<div style="border:1px solid #333; padding:8px; border-radius:8px; margin-bottom:12px;">'
        '<div style="font-size:16px; font-weight:bold; margin-bottom:6px;">'
        'Wind Vector</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    wind_dir = st.session_state["wind_dir"]       # from-heading
    wind_to  = (wind_dir + 180.0) % 360.0         # arrow points “to” this heading
    wind_spd = st.session_state["wind_speed"]
    wind_len = int(wind_spd * VECTOR_SCALE)
    st.markdown(
        f'<div style="text-align:center; margin-bottom:16px;">'
        f'<div style="font-size:14px;">Heading: {wind_dir:.0f}° (from)</div>'
        f'<div style="font-size:14px;">Speed: {wind_spd:.0f} m/s</div>'
        f'<div style="font-size:{wind_len}px; transform: rotate({wind_to}deg); '
        'display:inline-block; color:#1f77b4; margin-top:6px;">↑</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Drone Vector Box
    st.markdown(
        '<div style="border:1px solid #333; padding:8px; border-radius:8px; margin-bottom:12px;">'
        '<div style="font-size:16px; font-weight:bold; margin-bottom:6px;">'
        'Drone Vector</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    drone_h   = st.session_state["drone_heading"]   # heading
    drone_to  = drone_h                             # arrow points in that direction
    drone_spd = st.session_state["drone_speed"]
    drone_len = int(drone_spd * VECTOR_SCALE)
    st.markdown(
        f'<div style="text-align:center; margin-bottom:16px;">'
        f'<div style="font-size:14px;">Heading: {drone_h:.0f}°</div>'
        f'<div style="font-size:14px;">Speed: {drone_spd:.0f} m/s</div>'
        f'<div style="font-size:{drone_len}px; transform: rotate({drone_to}deg); '
        'display:inline-block; color:#d62728; margin-top:6px;">↑</div>'
        '</div>',
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# FULL-WIDTH BOTTOM BAR: “Round result: Error xxx m”
# ──────────────────────────────────────────────────────────────────────────────
if st.session_state["scored"]:
    error_display = f"Round result: Error {st.session_state['error_dist']:.1f} m"
else:
    error_display = "Round result: Error — (making guess…)"

st.markdown(
    f'<div style="border-top:2px solid #333; padding:8px; margin-top:12px; '
    'font-size:16px; font-weight:bold; text-align:center;">'
    f'{error_display}'
    '</div>',
    unsafe_allow_html=True,
)
