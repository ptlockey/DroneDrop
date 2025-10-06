# drone_drop_game.py

import streamlit as st
import folium
from folium.plugins import PolyLineTextPath
from streamlit_folium import st_folium
import random
import math
import numpy as np
import csv
from datetime import datetime
from branca.element import MacroElement, Template

# ──────────────────────────────────────────────────────────────────────────────
# SETTINGS
# ──────────────────────────────────────────────────────────────────────────────
MAP_SIZE            = 700  # map will be 700×700 px square (fits a 1080px screen)
MAP_VECTOR_SCALE_M  = 4.0  # metres of arrow length per m/s on the map
MIN_ARROW_LENGTH_M  = 6.0  # ensure very slow speeds remain visible
RANGE_RING_RADII_M  = [r for r in range(10, 101, 10)]

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


def add_range_rings(map_obj, *, origin_lat, origin_lon, radii_m=RANGE_RING_RADII_M):
    """Draw concentric range rings around the launch position."""

    for radius in radii_m:
        weight = 2 if radius % 50 == 0 else 1
        folium.Circle(
            location=[origin_lat, origin_lon],
            radius=radius,
            color="#1f2937",
            weight=weight,
            opacity=0.55,
            fill=False,
            dash_array="6,6" if radius % 50 else None,
            tooltip=f"{radius} m range",
        ).add_to(map_obj)


def add_vector_arrow(
    map_obj,
    *,
    origin_lat,
    origin_lon,
    heading_deg,
    speed_mps,
    color,
    label,
    offset_east_m=0.0,
    offset_north_m=0.0,
):
    """Draw a scaled velocity arrow anchored near the launch point."""

    if speed_mps <= 0:
        return

    origin_lat, origin_lon = displacement_to_latlon(
        origin_lat,
        origin_lon,
        offset_east_m,
        offset_north_m,
    )

    length_m = max(speed_mps * MAP_VECTOR_SCALE_M, MIN_ARROW_LENGTH_M)
    heading_rad = math.radians(heading_deg)
    dx = length_m * math.sin(heading_rad)
    dy = length_m * math.cos(heading_rad)

    end_lat, end_lon = displacement_to_latlon(
        origin_lat,
        origin_lon,
        dx,
        dy,
        dist=length_m,
        bearing=heading_rad,
    )

    line = folium.PolyLine(
        [[origin_lat, origin_lon], [end_lat, end_lon]],
        color=color,
        weight=4,
        opacity=0.85,
        tooltip=f"{label}: {speed_mps:.1f} m/s",
    ).add_to(map_obj)

    PolyLineTextPath(
        line,
        "➤",
        repeat=False,
        offset=12,
        attributes={
            "fill": color,
            "font-weight": "bold",
            "font-size": "16px",
        },
    ).add_to(map_obj)

    folium.Marker(
        [end_lat, end_lon],
        icon=folium.DivIcon(
            html=(
                f"<div style=\"background:rgba(255,255,255,0.85); padding:2px 6px; border-radius:4px; "
                f"border:1px solid rgba(15,23,42,0.2); color:{color}; font-size:12px; font-weight:600;\">"
                f"{label}</div>"
            ),
            icon_size=(0, 0),
            icon_anchor=(0, -8),
        ),
    ).add_to(map_obj)

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
# BUILT-UP LOCATION CATALOG & HELPERS
# ──────────────────────────────────────────────────────────────────────────────

BUILT_UP_LOCATIONS = [
    {"name": "Addis Ababa", "country": "Ethiopia", "lat": 8.9806, "lon": 38.7578, "max_radius_km": 22},
    {"name": "Nairobi", "country": "Kenya", "lat": -1.2864, "lon": 36.8172, "max_radius_km": 18},
    {"name": "Abuja", "country": "Nigeria", "lat": 9.0765, "lon": 7.3986, "max_radius_km": 20},
    {"name": "Johannesburg", "country": "South Africa", "lat": -26.2041, "lon": 28.0473, "max_radius_km": 22},
    {"name": "Lusaka", "country": "Zambia", "lat": -15.3875, "lon": 28.3228, "max_radius_km": 20},
    {"name": "Harare", "country": "Zimbabwe", "lat": -17.8249, "lon": 31.053, "max_radius_km": 18},
    {"name": "Riyadh", "country": "Saudi Arabia", "lat": 24.7136, "lon": 46.6753, "max_radius_km": 25},
    {"name": "Tehran", "country": "Iran", "lat": 35.6892, "lon": 51.389, "max_radius_km": 20},
    {"name": "Ulaanbaatar", "country": "Mongolia", "lat": 47.8864, "lon": 106.9057, "max_radius_km": 22},
    {"name": "Chengdu", "country": "China", "lat": 30.5728, "lon": 104.0668, "max_radius_km": 20},
    {"name": "Xi'an", "country": "China", "lat": 34.3416, "lon": 108.9398, "max_radius_km": 20},
    {"name": "Bengaluru", "country": "India", "lat": 12.9716, "lon": 77.5946, "max_radius_km": 18},
    {"name": "Hyderabad", "country": "India", "lat": 17.385, "lon": 78.4867, "max_radius_km": 18},
    {"name": "Kathmandu", "country": "Nepal", "lat": 27.7172, "lon": 85.324, "max_radius_km": 15},
    {"name": "Ankara", "country": "Turkey", "lat": 39.9334, "lon": 32.8597, "max_radius_km": 20},
    {"name": "Tashkent", "country": "Uzbekistan", "lat": 41.2995, "lon": 69.2401, "max_radius_km": 20},
    {"name": "Almaty", "country": "Kazakhstan", "lat": 43.222, "lon": 76.8512, "max_radius_km": 20},
    {"name": "Isfahan", "country": "Iran", "lat": 32.6546, "lon": 51.668, "max_radius_km": 20},
    {"name": "Ranchi", "country": "India", "lat": 23.3441, "lon": 85.3096, "max_radius_km": 18},
    {"name": "Kunming", "country": "China", "lat": 25.0389, "lon": 102.7183, "max_radius_km": 18},
    {"name": "Madrid", "country": "Spain", "lat": 40.4168, "lon": -3.7038, "max_radius_km": 22},
    {"name": "Paris", "country": "France", "lat": 48.8566, "lon": 2.3522, "max_radius_km": 18},
    {"name": "Berlin", "country": "Germany", "lat": 52.52, "lon": 13.405, "max_radius_km": 20},
    {"name": "Warsaw", "country": "Poland", "lat": 52.2297, "lon": 21.0122, "max_radius_km": 20},
    {"name": "Vienna", "country": "Austria", "lat": 48.2082, "lon": 16.3738, "max_radius_km": 18},
    {"name": "Munich", "country": "Germany", "lat": 48.1351, "lon": 11.582, "max_radius_km": 18},
    {"name": "Prague", "country": "Czechia", "lat": 50.0755, "lon": 14.4378, "max_radius_km": 18},
    {"name": "Budapest", "country": "Hungary", "lat": 47.4979, "lon": 19.0402, "max_radius_km": 18},
    {"name": "Milan", "country": "Italy", "lat": 45.4642, "lon": 9.19, "max_radius_km": 18},
    {"name": "Zaragoza", "country": "Spain", "lat": 41.6488, "lon": -0.8891, "max_radius_km": 18},
    {"name": "Krakow", "country": "Poland", "lat": 50.0647, "lon": 19.945, "max_radius_km": 18},
    {"name": "Denver", "country": "United States", "lat": 39.7392, "lon": -104.9903, "max_radius_km": 20},
    {"name": "Dallas", "country": "United States", "lat": 32.7767, "lon": -96.797, "max_radius_km": 20},
    {"name": "Phoenix", "country": "United States", "lat": 33.4484, "lon": -112.074, "max_radius_km": 20},
    {"name": "Las Vegas", "country": "United States", "lat": 36.1699, "lon": -115.1398, "max_radius_km": 18},
    {"name": "Atlanta", "country": "United States", "lat": 33.749, "lon": -84.388, "max_radius_km": 20},
    {"name": "Calgary", "country": "Canada", "lat": 51.0447, "lon": -114.0719, "max_radius_km": 20},
    {"name": "Edmonton", "country": "Canada", "lat": 53.5461, "lon": -113.4938, "max_radius_km": 20},
    {"name": "Mexico City", "country": "Mexico", "lat": 19.4326, "lon": -99.1332, "max_radius_km": 20},
    {"name": "Guadalajara", "country": "Mexico", "lat": 20.6597, "lon": -103.3496, "max_radius_km": 20},
    {"name": "Monterrey", "country": "Mexico", "lat": 25.6866, "lon": -100.3161, "max_radius_km": 20},
    {"name": "Bogotá", "country": "Colombia", "lat": 4.711, "lon": -74.0721, "max_radius_km": 20},
    {"name": "Quito", "country": "Ecuador", "lat": -0.1807, "lon": -78.4678, "max_radius_km": 18},
    {"name": "La Paz", "country": "Bolivia", "lat": -16.4897, "lon": -68.1193, "max_radius_km": 18},
    {"name": "Cordoba", "country": "Argentina", "lat": -31.4201, "lon": -64.1888, "max_radius_km": 20},
    {"name": "Belo Horizonte", "country": "Brazil", "lat": -19.9167, "lon": -43.9345, "max_radius_km": 20},
    {"name": "Rosario", "country": "Argentina", "lat": -32.9442, "lon": -60.6505, "max_radius_km": 20},
    {"name": "Alice Springs", "country": "Australia", "lat": -23.698, "lon": 133.8807, "max_radius_km": 15},
    {"name": "Toowoomba", "country": "Australia", "lat": -27.5598, "lon": 151.9507, "max_radius_km": 15},
    {"name": "Canberra", "country": "Australia", "lat": -35.2809, "lon": 149.13, "max_radius_km": 15},
]


def select_built_up_location():
    """Return a random built-up location descriptor."""

    if not BUILT_UP_LOCATIONS:
        raise RuntimeError("No built-up locations configured.")
    return random.choice(BUILT_UP_LOCATIONS)


def path_within_radius(xs, ys, radius_m, *, tolerance=5.0):
    """Ensure every sampled point stays within the allowed radius."""

    radius_limit = max(radius_m, 0.0) + tolerance
    return all(math.hypot(x, y) <= radius_limit for x, y in zip(xs, ys))


def get_random_city_point():
    """Return (lat, lon, metadata) for a curated built-up area."""

    location = select_built_up_location()
    return float(location["lat"]), float(location["lon"]), location

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

    attempts = 0
    while True:
        attempts += 1
        if attempts > 300:
            st.error("Unable to generate a built-up drop zone. Please try again.")
            st.stop()

        lat, lon, location = get_random_city_point()
        radius_m = float(location["max_radius_km"]) * 1_000.0

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

        if impact_dist > radius_m:
            continue

        if not path_within_radius(xs, ys, radius_m):
            continue

        st.session_state["impact"] = (lat1, lon1)
        st.session_state["trajectory_xy"] = list(zip(xs, ys))
        st.session_state["trajectory_samples"] = {
            "times": ts_list,
            "vhs": vhs_list,
            "vzs": vzs_list,
        }
        st.session_state["round_distance"] = impact_dist
        st.session_state["bearing"] = bearing_deg
        st.session_state["start_location"] = location
        st.session_state["start_location_label"] = location["name"]
        st.session_state["start_location_country"] = location["country"]
        st.session_state["safe_radius_km"] = float(location["max_radius_km"])
        st.session_state["safe_radius_m"] = radius_m
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

drop_city = st.session_state.get("start_location_label", "—")
drop_country = st.session_state.get("start_location_country", "")
safe_radius = st.session_state.get("safe_radius_km")
start_lat = st.session_state.get("start_lat")
start_lon = st.session_state.get("start_lon")

st.sidebar.markdown("### 📍 Drop Zone")
st.sidebar.markdown(
    metric_card(
        "Built-Up Area",
        drop_city,
        accent="#1d4ed8",
        subtext=drop_country or "Curated urban location",
    ),
    unsafe_allow_html=True,
)
coord_col1, coord_col2 = st.sidebar.columns(2)
with coord_col1:
    lat_text = f"{start_lat:.4f}°" if start_lat is not None else "—"
    st.markdown(
        metric_card("Latitude", lat_text, accent="#2563eb", subtext="Launch point"),
        unsafe_allow_html=True,
    )
with coord_col2:
    lon_text = f"{start_lon:.4f}°" if start_lon is not None else "—"
    st.markdown(
        metric_card("Longitude", lon_text, accent="#2563eb", subtext="Launch point"),
        unsafe_allow_html=True,
    )
radius_text = f"{safe_radius:.0f} km" if safe_radius else "—"
st.sidebar.markdown(
    metric_card(
        "Urban Radius",
        radius_text,
        accent="#059669",
        subtext="Trajectory kept off water",
    ),
    unsafe_allow_html=True,
)

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

        add_range_rings(base_map, origin_lat=start_lat, origin_lon=start_lon)

        wind_dir_from = st.session_state["wind_dir"]
        wind_speed = st.session_state["wind_speed"]
        wind_to = (wind_dir_from + 180.0) % 360.0

        drone_heading = st.session_state["drone_heading"]
        drone_speed = st.session_state["drone_speed"]

        add_vector_arrow(
            base_map,
            origin_lat=start_lat,
            origin_lon=start_lon,
            heading_deg=drone_heading,
            speed_mps=drone_speed,
            color="#22c55e",
            label="Drone",
            offset_east_m=5.0,
            offset_north_m=5.0,
        )

        add_vector_arrow(
            base_map,
            origin_lat=start_lat,
            origin_lon=start_lon,
            heading_deg=wind_to,
            speed_mps=wind_speed,
            color="#2563eb",
            label="Wind",
            offset_east_m=-5.0,
            offset_north_m=-5.0,
        )

        safe_radius_m = st.session_state.get("safe_radius_m")
        if safe_radius_m:
            folium.Circle(
                location=[start_lat, start_lon],
                radius=safe_radius_m,
                color="#0ea5e9",
                weight=1,
                fill=True,
                fill_opacity=0.08,
                tooltip="Urban coverage boundary",
            ).add_to(base_map)

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

        add_range_rings(overlay_map, origin_lat=start_lat, origin_lon=start_lon)

        wind_dir_from = st.session_state["wind_dir"]
        wind_speed = st.session_state["wind_speed"]
        wind_to = (wind_dir_from + 180.0) % 360.0

        drone_heading = st.session_state["drone_heading"]
        drone_speed = st.session_state["drone_speed"]

        add_vector_arrow(
            overlay_map,
            origin_lat=start_lat,
            origin_lon=start_lon,
            heading_deg=drone_heading,
            speed_mps=drone_speed,
            color="#22c55e",
            label="Drone",
            offset_east_m=5.0,
            offset_north_m=5.0,
        )

        add_vector_arrow(
            overlay_map,
            origin_lat=start_lat,
            origin_lon=start_lon,
            heading_deg=wind_to,
            speed_mps=wind_speed,
            color="#2563eb",
            label="Wind",
            offset_east_m=-5.0,
            offset_north_m=-5.0,
        )

        safe_radius_m = st.session_state.get("safe_radius_m")
        if safe_radius_m:
            folium.Circle(
                location=[start_lat, start_lon],
                radius=safe_radius_m,
                color="#0ea5e9",
                weight=1,
                fill=True,
                fill_opacity=0.06,
                tooltip="Urban coverage boundary",
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
