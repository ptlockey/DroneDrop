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
from branca.element import MacroElement, Template

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
# UI HELPERS
# ──────────────────────────────────────────────────────────────────────────────


def metric_card(label, value, *, accent="#1f77b4", subtext=""):
    """Render a compact metric card for the sidebar."""
    return f"""
    <div style="background:rgba(31, 119, 180, 0.08); border-left:4px solid {accent};
                padding:8px 10px; border-radius:6px; margin-bottom:6px;">
        <div style="font-size:12px; text-transform:uppercase; letter-spacing:0.5px;
                    color:#4b5563;">{label}</div>
        <div style="font-size:18px; font-weight:700; color:#111827;">{value}</div>
        <div style="font-size:12px; color:#6b7280;">{subtext}</div>
    </div>
    """


def vector_card(title, heading, speed, *, color, icon):
    """Render a styled vector card with a rotated arrow icon."""
    arrow = (
        f"<div style='width:54px; height:54px; margin:0 auto; display:flex; align-items:center;"
        f" justify-content:center; border-radius:50%; background:rgba(17,24,39,0.05);"
        f" color:{color}; transform:rotate({heading}deg); font-size:28px; transition:transform 0.3s;'>"
        "↑"
        "</div>"
    )
    return f"""
    <div style="border:1px solid rgba(17, 24, 39, 0.1); border-radius:10px; padding:12px;
                background:linear-gradient(135deg, rgba(17,24,39,0.02), rgba(17,24,39,0.06));
                margin-bottom:16px;">
        <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;">
            <div style="font-weight:700; color:#111827;">{title}</div>
            <div style="color:{color}; font-size:16px;">{icon}</div>
        </div>
        <div style="display:flex; gap:12px; align-items:center;">
            {arrow}
            <div>
                <div style="font-size:14px; color:#4b5563;">Heading</div>
                <div style="font-weight:600; color:#111827;">{heading:.0f}°</div>
                <div style="font-size:14px; color:#4b5563; margin-top:6px;">Speed</div>
                <div style="font-weight:600; color:#111827;">{speed:.0f} m/s</div>
            </div>
        </div>
    </div>
    """


def velocity_calibration_card(*, east_vel, north_vel, fall_time, drift_east, drift_north, drift_total, drift_bearing):
    """Display a compact card summarizing velocity-derived landing cues."""

    def format_component(value, positive_label, negative_label, unit="m/s"):
        direction = positive_label if value >= 0 else negative_label
        return f"{abs(value):.1f} {unit} {direction}"

    def format_drift_component(value, positive_label, negative_label):
        direction = positive_label if value >= 0 else negative_label
        return f"{abs(value):.0f} m {direction}"

    drift_direction = f"{drift_bearing:.0f}°"
    return f"""
    <div style="border:1px solid rgba(17,24,39,0.1); border-radius:10px; padding:12px; margin-bottom:16px;
                background:linear-gradient(135deg, rgba(59,130,246,0.08), rgba(59,130,246,0.18));">
        <div style="font-weight:700; color:#0f172a; margin-bottom:8px;">Velocity Calibration</div>
        <div style="font-size:13px; color:#1e3a8a; text-transform:uppercase; letter-spacing:0.4px;">Horizontal Components</div>
        <div style="font-size:14px; color:#111827; font-weight:600;">{format_component(east_vel, 'E', 'W')}</div>
        <div style="font-size:14px; color:#111827; font-weight:600; margin-bottom:6px;">{format_component(north_vel, 'N', 'S')}</div>
        <div style="font-size:13px; color:#1e3a8a; text-transform:uppercase; letter-spacing:0.4px;">Fall Time</div>
        <div style="font-size:14px; color:#111827; font-weight:600;">{fall_time:.1f} s</div>
        <div style="font-size:13px; color:#1e3a8a; text-transform:uppercase; letter-spacing:0.4px; margin-top:6px;">Estimated Drift</div>
        <div style="font-size:14px; color:#111827; font-weight:600;">{drift_total:.0f} m ({drift_direction})</div>
        <div style="font-size:13px; color:#1f2937;">{format_drift_component(drift_east, 'E', 'W')} · {format_drift_component(drift_north, 'N', 'S')}</div>
    </div>
    """


# ──────────────────────────────────────────────────────────────────────────────
# MAP HELPERS
# ──────────────────────────────────────────────────────────────────────────────


class SimpleScaleControl(MacroElement):
    """Custom Leaflet scale control with consistent metric styling."""

    def __init__(self, position="bottomleft", max_width=120):
        super().__init__()
        self._name = "SimpleScaleControl"
        self.position = position
        self.max_width = max_width
        self._template = Template(
            """
            {% macro script(this, kwargs) %}
            var simpleScale = L.control.scale({
                position: '{{this.position}}',
                maxWidth: {{this.max_width}},
                metric: true,
                imperial: false
            }).addTo({{this._parent.get_name()}});
            if (simpleScale && simpleScale._container) {
                simpleScale._container.classList.add('simple-scale');
            }
            {% endmacro %}

            {% macro style(this, kwargs) %}
            .simple-scale {
                padding:4px 8px;
                background:rgba(15,23,42,0.82);
                color:#f9fafb;
                border-radius:6px;
                font-size:12px;
                font-weight:600;
                box-shadow:0 2px 6px rgba(15,23,42,0.35);
            }
            .simple-scale .leaflet-control-scale-line {
                background:transparent;
                border:none;
                border-top:3px solid #f9fafb;
                color:#f9fafb;
                text-align:center;
            }
            {% endmacro %}
            """
        )


def add_simple_scale(map_obj, *, position="bottomleft", max_width=120):
    """Attach the custom metric scale bar to the supplied map."""
    SimpleScaleControl(position=position, max_width=max_width).add_to(map_obj)

def wedge_coordinates(lat, lon, bearing_deg, spread_deg, distance_m):
    """Return lat/lon coordinates describing a wedge originating at (lat, lon)."""
    if distance_m <= 0:
        return []
    half = spread_deg / 2.0
    bearings = np.linspace(bearing_deg - half, bearing_deg + half, num=6)
    points = []
    for b in bearings:
        b_rad = math.radians((b + 360.0) % 360.0)
        dx = distance_m * math.sin(b_rad)
        dy = distance_m * math.cos(b_rad)
        points.append(displacement_to_latlon(lat, lon, dx, dy, dist=distance_m, bearing=b_rad))
    return [(lat, lon)] + points + [(lat, lon)]


# ──────────────────────────────────────────────────────────────────────────────
# LOAD “naturalearth_cities” & “naturalearth_lowres” FOR LAND‐ONLY / CITY SAMPLING
# ──────────────────────────────────────────────────────────────────────────────
_cities_gdf     = None
_use_land_check = False
_land_features  = []
_land_geometries = []

try:
    # 1) built‐in “naturalearth_cities” for random city picks
    cities_path = gpd.datasets.get_path("naturalearth_cities")
    _cities_gdf = gpd.read_file(cities_path)

    # 2) built‐in “naturalearth_lowres” for land‐only fallback
    land_shp = gpd.datasets.get_path("naturalearth_lowres")
    with fiona.open(land_shp) as src:
        _land_features = list(src)
    _land_geometries = [shape(feat["geometry"]) for feat in _land_features]
    _use_land_check = True

except Exception:
    _cities_gdf = None
    try:
        land_shp = gpd.datasets.get_path("naturalearth_lowres")
        with fiona.open(land_shp) as src:
            _land_features = list(src)
        _land_geometries = [shape(feat["geometry"]) for feat in _land_features]
        _use_land_check = True
    except Exception:
        _land_features = []
        _land_geometries = []
        _use_land_check = False


def is_land(lat, lon):
    """Return True if the given coordinate lies over land or checks are unavailable."""
    if not _use_land_check or not _land_geometries:
        return True

    pt = Point(lon, lat)
    for geom in _land_geometries:
        if geom.contains(pt) or geom.touches(pt):
            return True
    return False


def get_random_land_point():
    """
    Return (lat, lon) that falls over land (using lowres shapefile) if possible;
    otherwise returns a random lat/lon anywhere.
    """
    if not _use_land_check or not _land_geometries:
        return random.uniform(-90.0, 90.0), random.uniform(-180.0, 180.0)

    while True:
        lat = random.uniform(-90.0, 90.0)
        lon = random.uniform(-180.0, 180.0)
        pt = Point(lon, lat)
        for geom in _land_geometries:
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
    # reset previous-round state
    st.session_state["guess"]          = None
    st.session_state["impact"]         = None
    st.session_state["trajectory_xy"]  = None
    st.session_state["trajectory_samples"] = None
    st.session_state["round_distance"] = None
    st.session_state["bearing"]        = None
    st.session_state["error_dist"]     = None
    st.session_state["round_points"]   = None
    st.session_state["scored"]         = False
    st.session_state["round_bonus"]    = 0
    st.session_state["round_feedback"] = ""
    st.session_state["fall_time"]      = None
    st.session_state["drift_vector"]   = (0.0, 0.0)

    while True:
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
        ) = compute_trajectory(lat, lon)

        if is_land(lat1, lon1):
            st.session_state["impact"] = (lat1, lon1)
            st.session_state["trajectory_xy"] = list(zip(xs, ys))
            st.session_state["trajectory_samples"] = {
                "times": ts_list,
                "vhs": vhs_list,
                "vzs": vzs_list,
            }
            st.session_state["round_distance"] = impact_dist
            st.session_state["bearing"] = bearing_deg
            fall_time = ts_list[-1] if ts_list else 0.0
            drift_east = xs[-1] if xs else 0.0
            drift_north = ys[-1] if ys else 0.0
            st.session_state["fall_time"] = fall_time
            st.session_state["drift_vector"] = (drift_east, drift_north)
            break


# Initialize once
if "initialized" not in st.session_state:
    st.session_state["initialized"] = True
    st.session_state["score"]       = 0
    st.session_state["rounds_played"] = 0
    st.session_state["total_error"]   = 0.0
    st.session_state["hits"]          = 0
    st.session_state["streak"]        = 0
    st.session_state["best_error"]    = None
    st.session_state["round_history"] = []
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

st.markdown(
    """
    <style>
    .main .block-container{
        padding-top: 1.5rem;
        padding-bottom: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────────────────────────────────────
# LEFT SIDEBAR: CONTROLS, METRICS, ENVIRONMENT
# ──────────────────────────────────────────────────────────────────────────────
st.sidebar.markdown("## 🎮 Mission Control")
control_col1, control_col2 = st.sidebar.columns(2)
with control_col1:
    if control_col1.button("Next Drop", key="next_drop"):
        new_round()
with control_col2:
    if control_col2.button("Exit & Save", key="exit_save"):
        try:
            with open("high_scores.csv", "a", newline="") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([datetime.now().isoformat(), st.session_state["score"]])
            control_col2.success("✅ Score saved")
        except Exception as e:
            control_col2.error(f"Error saving score: {e}")

st.sidebar.markdown("---")

if "difficulty" not in st.session_state:
    st.session_state["difficulty"] = "Hard"
st.sidebar.markdown("### 🎚️ Difficulty")
st.session_state["difficulty"] = st.sidebar.radio(
    "Select challenge", ["Easy", "Medium", "Hard"],
    index=["Easy", "Medium", "Hard"].index(st.session_state["difficulty"])
)

st.sidebar.markdown("---")

rounds_played = st.session_state["rounds_played"]
total_error = st.session_state["total_error"]
hits = st.session_state["hits"]
avg_error = total_error / rounds_played if rounds_played else 0.0
hit_rate = hits / rounds_played if rounds_played else 0.0

st.sidebar.markdown("### 📊 Flight Report")
st.sidebar.markdown(
    metric_card("Score", f"{st.session_state['score']:,}", accent="#2563eb", subtext="Total mission points"),
    unsafe_allow_html=True,
)
st.sidebar.markdown(
    metric_card(
        "Rounds", f"{rounds_played}", accent="#10b981",
        subtext="Flights completed"
    ),
    unsafe_allow_html=True,
)
avg_text = f"{avg_error:.1f} m" if rounds_played else "—"
st.sidebar.markdown(
    metric_card("Avg. Error", avg_text, accent="#f59e0b", subtext="Across all drops"),
    unsafe_allow_html=True,
)
st.sidebar.markdown(
    metric_card(
        "Hit Rate",
        f"{hit_rate * 100:0.0f}%" if rounds_played else "—",
        accent="#8b5cf6",
        subtext="Within scoring rings"
    ),
    unsafe_allow_html=True,
)

accuracy_target = min(hit_rate, 1.0)
st.sidebar.progress(accuracy_target)
st.sidebar.caption("Build consecutive hits to trigger streak bonuses.")

st.sidebar.markdown("---")
st.sidebar.markdown("### 🌦️ Conditions")
env_col1, env_col2 = st.sidebar.columns(2)
with env_col1:
    st.markdown(
        metric_card(
            "Surface Temp",
            f"{st.session_state['surface_temp_c']:.0f} °C",
            accent="#ef4444",
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        metric_card(
            "Pressure",
            f"{st.session_state['surface_pressure_mb']:.0f} mb",
            accent="#0ea5e9",
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        metric_card(
            "Wind From",
            f"{st.session_state['wind_dir']:.0f}°",
            accent="#22c55e",
        ),
        unsafe_allow_html=True,
    )
with env_col2:
    st.markdown(
        metric_card(
            "Wind Speed",
            f"{st.session_state['wind_speed']:.0f} m/s",
            accent="#14b8a6",
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        metric_card(
            "Drone Hdg",
            f"{st.session_state['drone_heading']:.0f}°",
            accent="#f97316",
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        metric_card(
            "Drone Spd",
            f"{st.session_state['drone_speed']:.0f} m/s",
            accent="#38bdf8",
        ),
        unsafe_allow_html=True,
    )
st.sidebar.markdown(
    metric_card(
        "Drop Altitude",
        f"{st.session_state['initial_height']:.0f} m",
        accent="#a855f7",
    ),
    unsafe_allow_html=True,
)
st.sidebar.markdown(
    metric_card(
        "CdA",
        f"{st.session_state['CdA']:.2f} m²",
        accent="#f472b6",
    ),
    unsafe_allow_html=True,
)
st.sidebar.markdown(
    metric_card(
        "Mass",
        f"{st.session_state['mass']:.1f} kg",
        accent="#9ca3af",
    ),
    unsafe_allow_html=True,
)


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
            control_scale=False,
        )
        add_simple_scale(base_map)
        folium.Marker(
            [start_lat, start_lon],
            tooltip="Drone Start",
            icon=folium.Icon(icon="plane", prefix="fa", color="blue"),
        ).add_to(base_map)

        wind_dir_from = st.session_state["wind_dir"]
        wind_speed = st.session_state["wind_speed"]
        wind_to = (wind_dir_from + 180.0) % 360.0
        cone_distance = max(150.0, wind_speed * 80.0)
        cone_points = wedge_coordinates(start_lat, start_lon, wind_to, 35.0, cone_distance)
        if cone_points:
            folium.Polygon(
                cone_points,
                color="#2563eb",
                weight=1,
                fill=True,
                fill_opacity=0.15,
                tooltip="Projected wind cone",
            ).add_to(base_map)
            axis_lat, axis_lon = displacement_to_latlon(
                start_lat,
                start_lon,
                cone_distance * math.sin(math.radians(wind_to)),
                cone_distance * math.cos(math.radians(wind_to)),
                dist=cone_distance,
                bearing=math.radians(wind_to),
            )
            folium.PolyLine(
                [[start_lat, start_lon], [axis_lat, axis_lon]],
                color="#1d4ed8",
                weight=3,
                tooltip="Wind drift axis",
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

            st.session_state["rounds_played"] += 1
            st.session_state["total_error"] += error_dist
            if error_dist <= R2:
                st.session_state["hits"] += 1

            if error_dist <= R2:
                st.session_state["streak"] += 1
            else:
                st.session_state["streak"] = 0

            bonus = 0
            feedback_parts = []

            if error_dist <= R1:
                bullseye_bonus = 150
                bonus += bullseye_bonus
                feedback_parts.append(f"Bullseye bonus +{bullseye_bonus}")

            streak = st.session_state["streak"]
            if streak >= 3:
                streak_bonus = 100 * (streak - 2)
                bonus += streak_bonus
                feedback_parts.append(f"Hot streak ×{streak} +{streak_bonus}")

            prev_best = st.session_state["best_error"]
            if prev_best is None or error_dist < prev_best:
                st.session_state["best_error"] = error_dist
                personal_best_bonus = 100
                bonus += personal_best_bonus
                feedback_parts.append(f"New personal best +{personal_best_bonus}")

            if error_dist > 0 and error_dist <= R3:
                accuracy_bonus = int(max(0.0, (R3 - error_dist) / R3) * 120)
                if accuracy_bonus:
                    bonus += accuracy_bonus
                    feedback_parts.append(f"Accuracy bonus +{accuracy_bonus}")

            st.session_state["score"] += pts + bonus
            st.session_state["round_points"] = pts
            st.session_state["round_bonus"] = bonus
            st.session_state["round_feedback"] = ", ".join(feedback_parts) if feedback_parts else "Keep refining your approach."
            st.session_state["round_history"].append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "error": error_dist,
                    "points": pts,
                    "bonus": bonus,
                }
            )
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
            control_scale=False,
        )
        add_simple_scale(overlay_map)
        folium.Marker(
            [start_lat, start_lon],
            tooltip="Drone Start",
            icon=folium.Icon(icon="plane", prefix="fa", color="blue"),
        ).add_to(overlay_map)

        if st.session_state["rounds_played"] > 1 and st.session_state["total_error"] > 0:
            avg_error_radius = st.session_state["total_error"] / st.session_state["rounds_played"]
            folium.Circle(
                location=[start_lat, start_lon],
                radius=avg_error_radius,
                color="#7c3aed",
                weight=1,
                fill=True,
                fill_opacity=0.08,
                tooltip="Average error radius",
            ).add_to(overlay_map)
        if st.session_state["best_error"] is not None:
            folium.Circle(
                location=[start_lat, start_lon],
                radius=st.session_state["best_error"],
                color="#10b981",
                weight=2,
                fill=False,
                dash_array="6,6",
                tooltip="Personal best radius",
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

        folium.PolyLine(
            [[start_lat, start_lon], [guess_lat, guess_lon]],
            color="#fb923c",
            weight=2,
            tooltip="Your bearing",
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
    st.markdown("### 📐 Vector Overview")
    wind_dir = st.session_state["wind_dir"]       # from-heading
    wind_spd = st.session_state["wind_speed"]
    wind_to  = (wind_dir + 180.0) % 360.0         # arrow points “to” this heading

    st.markdown(
        vector_card(
            "Wind Vector",
            wind_to,
            wind_spd,
            color="#2563eb",
            icon="🌬️",
        ),
        unsafe_allow_html=True,
    )

    drone_h   = st.session_state["drone_heading"]
    drone_spd = st.session_state["drone_speed"]
    st.markdown(
        vector_card(
            "Drone Vector",
            drone_h,
            drone_spd,
            color="#dc2626",
            icon="🚁",
        ),
        unsafe_allow_html=True,
    )

    drift_east, drift_north = st.session_state.get("drift_vector", (0.0, 0.0))
    fall_time = st.session_state.get("fall_time") or 0.0
    drift_total = st.session_state.get("round_distance")
    if drift_total is None:
        drift_total = math.hypot(drift_east, drift_north)
    drift_bearing = st.session_state.get("bearing") or 0.0
    east_vel = drone_spd * math.sin(math.radians(drone_h))
    north_vel = drone_spd * math.cos(math.radians(drone_h))

    st.markdown(
        velocity_calibration_card(
            east_vel=east_vel,
            north_vel=north_vel,
            fall_time=fall_time,
            drift_east=drift_east,
            drift_north=drift_north,
            drift_total=drift_total,
            drift_bearing=drift_bearing,
        ),
        unsafe_allow_html=True,
    )

    st.caption("Wind heading indicates the direction the gust pushes the payload toward.")

    streak = st.session_state["streak"]
    round_points = st.session_state.get("round_points") or 0
    round_bonus = st.session_state.get("round_bonus", 0)
    insight_text = st.session_state["round_feedback"] or "Make a prediction to earn rewards."
    st.markdown(
        f"""
        <div style="border:1px solid rgba(17,24,39,0.1); border-radius:10px; padding:12px;
                    background:rgba(17,24,39,0.02);">
            <div style="font-weight:600; color:#111827; margin-bottom:6px;">Round Insight</div>
            <div style="font-size:13px; color:#4b5563;">Base points: <strong>{round_points}</strong></div>
            <div style="font-size:13px; color:#4b5563;">Bonus: <strong>{round_bonus}</strong></div>
            <div style="font-size:13px; color:#4b5563;">Current streak: <strong>{streak}</strong></div>
            <div style="font-size:13px; color:#4b5563; margin-top:6px;">{insight_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# BOTTOM SUMMARY BAR WITH ACCURACY + BONUS CALLOUTS
# ──────────────────────────────────────────────────────────────────────────────
summary_col1, summary_col2 = st.columns((3, 1))

with summary_col1:
    if st.session_state["scored"]:
        error_val = st.session_state["error_dist"]
        round_points = st.session_state.get("round_points", 0)
        round_bonus = st.session_state.get("round_bonus", 0)
        total_round = round_points + round_bonus
        summary_title = f"Error {error_val:.1f} m"
        summary_detail = (
            f"Gained <strong>{total_round}</strong> pts · Base {round_points} / Bonus {round_bonus}"
        )
        footer_text = st.session_state.get("round_feedback", "")
    else:
        summary_title = "Awaiting guess"
        summary_detail = "Click on the map to lock in your prediction."
        footer_text = ""

    st.markdown(
        f"""
        <div style="border-top:2px solid rgba(17,24,39,0.12); padding:16px 18px; margin-top:12px;">
            <div style="font-size:18px; font-weight:700; color:#111827;">{summary_title}</div>
            <div style="font-size:14px; color:#4b5563; margin-top:2px;">{summary_detail}</div>
            <div style="font-size:13px; color:#6b7280; margin-top:6px;">{footer_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with summary_col2:
    rounds_played = st.session_state["rounds_played"]
    if rounds_played:
        avg_error = st.session_state["total_error"] / rounds_played
        hit_rate = st.session_state["hits"] / rounds_played
        st.markdown(
            f"""
            <div style="border:1px solid rgba(17,24,39,0.12); border-radius:10px; padding:12px; margin-top:12px;">
                <div style="font-size:13px; color:#4b5563;">Avg error</div>
                <div style="font-weight:600; color:#111827;">{avg_error:.1f} m</div>
                <div style="font-size:13px; color:#4b5563; margin-top:8px;">Hit rate</div>
                <div style="font-weight:600; color:#111827;">{hit_rate*100:0.0f}%</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div style="border:1px solid rgba(17,24,39,0.12); border-radius:10px; padding:12px; margin-top:12px;">
                <div style="font-size:13px; color:#4b5563;">Avg error</div>
                <div style="font-weight:600; color:#111827;">—</div>
                <div style="font-size:13px; color:#4b5563; margin-top:8px;">Hit rate</div>
                <div style="font-weight:600; color:#111827;">—</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
