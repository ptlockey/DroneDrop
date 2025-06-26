import random
import math
import numpy as np
from datetime import datetime
from .geo_utils import get_random_city_point

# ──────────────────────────────────────────────────────────────────────────────
# SETTINGS
# ──────────────────────────────────────────────────────────────────────────────
VECTOR_SCALE = 4    # pixels per m/s for arrow length
MAP_SIZE     = 700  # map will be 700×700 px square (fits a 1080px screen)

# Base (Hard) bullseye radii (in meters) and base point awards:
BASE_RADII  = [3, 10, 30]
BASE_POINTS = [2500, 1000, 100]
# ──────────────────────────────────────────────────────────────────────────────

def compute_trajectory(lat0, lon0, session_state):
    """
    Compute realistic drop trajectory. Returns:
      (lat1, lon1, xs, ys, zs, ts_list, vhs_list, vzs_list, dist, bearing_deg)

    Reads from session_state keys:
      surface_temp_c, surface_pressure_mb, wind_dir, wind_speed,
      drone_heading, drone_speed, initial_height, dt, mass, CdA, h_ref, alpha
    """
    surface_temp_c     = session_state["surface_temp_c"]
    surface_pressure_mb = session_state["surface_pressure_mb"]
    wind_dir           = session_state["wind_dir"]       # "from" heading
    wind_speed         = session_state["wind_speed"]
    init_dir           = session_state["drone_heading"]
    v0                 = session_state["drone_speed"]
    initial_height     = session_state["initial_height"]
    dt                 = session_state["dt"]
    mass               = session_state["mass"]
    CdA                = session_state["CdA"]
    h_ref              = session_state["h_ref"]
    alpha              = session_state["alpha"]

    g = 9.80665
    R = 287.05
    L = 0.0065

    temp_k = surface_temp_c + 273.15
    pres0   = surface_pressure_mb * 100.0  # mb → Pa

    # Convert "wind FROM" → "wind TO" direction
    wind_to = (wind_dir + 180.0) % 360.0
    wind_unit = np.array([
        math.sin(math.radians(wind_to)),
        math.cos(math.radians(wind_to))
    ])

    # Drone's initial horizontal velocity [east, north]
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

    # Convert final (x, y) displacement → lat/lon
    lat1 = lat0 + ys[-1] / 111111.0
    lon1 = lon0 + xs[-1] / (111111.0 * math.cos(math.radians(lat0)))
    dist = math.hypot(xs[-1], ys[-1])

    dx_final, dy_final = xs[-1], ys[-1]
    bearing_rad = math.atan2(dx_final, dy_final)
    bearing_deg = (math.degrees(bearing_rad) + 360.0) % 360.0

    return lat1, lon1, xs, ys, zs, ts_list, vhs_list, vzs_list, dist, bearing_deg

def new_round(session_state):
    lat, lon = get_random_city_point()
    session_state["start_lat"] = lat
    session_state["start_lon"] = lon

    session_state["surface_temp_c"]     = random.uniform(-20.0, 40.0)
    session_state["surface_pressure_mb"] = random.uniform(950.0, 1050.0)
    session_state["wind_speed"]         = random.uniform(0.0, 40.0)
    session_state["wind_dir"]           = random.uniform(0.0, 359.0)
    session_state["drone_speed"]        = random.uniform(0.0, 30.0)
    session_state["drone_heading"]      = random.uniform(0.0, 359.0)
    session_state["initial_height"]     = random.uniform(0.0, 1000.0)
    session_state["mass"]               = 1.0
    session_state["CdA"]                = random.uniform(0.01, 0.1)
    session_state["h_ref"]              = 10.0
    session_state["alpha"]              = 0.2
    session_state["dt"]                 = 0.01

    # reset previous-round state
    session_state["guess"]         = None
    session_state["impact"]        = None
    session_state["trajectory_xy"] = None
    session_state["round_distance"] = None
    session_state["bearing"]       = None
    session_state["error_dist"]    = None
    session_state["round_points"]  = None
    session_state["scored"]        = False 