import streamlit as st
import folium
from streamlit_folium import st_folium
import math
from drone_drop.game import compute_trajectory, new_round, VECTOR_SCALE, MAP_SIZE, BASE_RADII, BASE_POINTS
from drone_drop.ui import sidebar_controls, sidebar_environment, round_result_bar

# Modern CSS for card-style layout and improved typography
st.markdown('''
    <style>
    body {
        background: #f4f6fa;
    }
    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 1.5rem;
    }
    .card {
        background: #fff;
        border-radius: 18px;
        box-shadow: 0 4px 24px rgba(0,0,0,0.08);
        padding: 2rem 2.5rem 2rem 2.5rem;
        margin-bottom: 2rem;
    }
    .sidebar .sidebar-content {
        background: #f8fafc;
        border-radius: 16px;
        padding: 1.5rem 1rem 1.5rem 1rem;
        margin: 1rem 0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    .big-title {
        font-size: 2.5rem;
        font-weight: 900;
        color: #2d3a4a;
        letter-spacing: -1px;
        margin-bottom: 0.5rem;
        text-align: center;
    }
    .section-title {
        font-size: 1.3rem;
        font-weight: 700;
        color: #3b4a5a;
        margin-top: 1.5rem;
        margin-bottom: 0.5rem;
    }
    .score-banner {
        background: linear-gradient(90deg, #4f8cff 0%, #38e8ff 100%);
        color: #fff;
        font-size: 1.4rem;
        font-weight: 700;
        border-radius: 12px;
        padding: 0.7rem 1.5rem;
        margin-bottom: 1.2rem;
        text-align: center;
        box-shadow: 0 2px 8px rgba(0,0,0,0.07);
    }
    .help-box {
        background: #e9eef6;
        border-radius: 10px;
        padding: 1rem 1.5rem;
        margin-bottom: 1.2rem;
        font-size: 1.05rem;
        color: #2d3a4a;
    }
    .vector-box {
        background: #f8fafc;
        border-radius: 12px;
        padding: 1.2rem 1rem 1.2rem 1rem;
        margin-bottom: 1.2rem;
        text-align: center;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    .vector-arrow {
        font-size: 3.5rem;
        font-weight: bold;
        display: block;
        margin: 0.5rem auto 0 auto;
    }
    .vector-arrow.wind { color: #1f77b4; }
    .vector-arrow.drone { color: #d62728; }
    .score-highlight { color: #e74c3c; font-weight: bold; }
    .env-label { color: #888; font-size: 0.95rem; }
    </style>
''', unsafe_allow_html=True)

st.set_page_config(page_title="Drone Drop Game", page_icon="🚁", layout="wide")

# Ensure required session state keys are initialized
if "initialized" not in st.session_state:
    st.session_state["initialized"] = True
    st.session_state["score"] = 0
    st.session_state["scored"] = False
    st.session_state["round_points"] = 0
    st.session_state["error_dist"] = 0.0
    new_round(st.session_state)

# Collapsible help section
with st.expander("❓ How to Play", expanded=False):
    st.markdown(
        """
        - **Goal:** Guess where the drone's payload will land, given wind, speed, and altitude.
        - **How:** Click on the map to make your guess. The closer you are to the actual impact, the more points you score!
        - **Controls:** Use the sidebar to start a new round or change difficulty.
        - **Scoring:** Points are awarded based on how close your guess is to the bullseye rings.
        """
    )

# Score/status banner
score = st.session_state.get("score", 0)
if st.session_state.get("scored", False):
    error_display = f"Error: <span style='color:#e74c3c;font-weight:bold'>{st.session_state['error_dist']:.1f} m</span> | Points: <span style='color:#e67e22;font-weight:bold'>{st.session_state['round_points']}</span>"
else:
    error_display = "Make your guess!"
st.markdown(f'''<div style="background: linear-gradient(90deg, #4f8cff 0%, #38e8ff 100%); color: #fff; font-size: 1.3rem; font-weight: 700; border-radius: 12px; padding: 0.7rem 1.5rem; margin-bottom: 1.2rem; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.07);">Score: <span style='color:#fff;font-weight:bold'>{score}</span> &nbsp;|&nbsp; {error_display}</div>''', unsafe_allow_html=True)

# Title
st.markdown('<h1 style="text-align:center; color:#2d3a4a; font-size:2.2rem; font-weight:900; margin-bottom:0.5rem;">🚁 Drone Drop Game</h1>', unsafe_allow_html=True)

# Sidebar controls and environment
sidebar_controls(st.session_state, new_round)
sidebar_environment(st.session_state)

difficulty = st.session_state["difficulty"]
if difficulty == "Easy":
    size_factor   = 15.0
    points_factor = 0.1
elif difficulty == "Medium":
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

# MAIN AREA: Two columns—Map (wide) and Vector boxes (right)
col_map, col_vecs = st.columns((3, 1), gap="large")

with col_map:
    st.markdown('<div style="background:#fff; border-radius:16px; box-shadow:0 4px 24px rgba(0,0,0,0.08); padding:1.5rem 1.5rem 1.2rem 1.5rem; margin-bottom:2rem;">', unsafe_allow_html=True)
    st.markdown('<div style="font-size:1.3rem; font-weight:700; color:#3b4a5a; margin-bottom:0.7rem;">🗺️ Drop Zone</div>', unsafe_allow_html=True)
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
            ) = compute_trajectory(start_lat, start_lon, st.session_state)

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
        # Add guess marker (if desired, e.g., orange question mark)
        if st.session_state["guess"] is not None:
            guess_lat, guess_lon = st.session_state["guess"]
            folium.Marker(
                [guess_lat, guess_lon],
                tooltip="Your Guess",
                icon=folium.Icon(icon="question", prefix="fa", color="orange"),
            ).add_to(overlay_map)
        # Actual impact marker (bullseye, purple)
        impact_lat, impact_lon = st.session_state["impact"]
        folium.Marker(
            [impact_lat, impact_lon],
            tooltip="Actual Impact",
            icon=folium.Icon(icon="bullseye", prefix="fa", color="purple"),
        ).add_to(overlay_map)
        # Draw bullseye circles (use R1, R2, R3)
        folium.Circle(
            location=[guess_lat, guess_lon],
            radius=R3,
            color="#3498db",  # blue
            fill=True,
            fill_opacity=0.18,
            weight=2,
        ).add_to(overlay_map)
        folium.Circle(
            location=[guess_lat, guess_lon],
            radius=R2,
            color="#f1c40f",  # yellow
            fill=True,
            fill_opacity=0.28,
            weight=2,
        ).add_to(overlay_map)
        folium.Circle(
            location=[guess_lat, guess_lon],
            radius=R1,
            color="#e74c3c",  # red
            fill=True,
            fill_opacity=0.38,
            weight=3,
        ).add_to(overlay_map)
        # Add range markers (distance labels) north of the guess point
        for radius, color in zip([R1, R2, R3], ["#e74c3c", "#f1c40f", "#3498db"]):
            label = f"{int(round(radius))}m"
            label_lat = guess_lat + (radius / 111111.0)
            folium.Marker(
                location=[label_lat, guess_lon],
                icon=folium.DivIcon(html=f'<div style="color:{color}; font-weight:bold; font-size:14px; text-shadow:1px 1px 2px #fff;">{label}</div>'),
            ).add_to(overlay_map)
        # Actual impact marker + dashed line from start→impact
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
    st.markdown('</div>', unsafe_allow_html=True)

with col_vecs:
    st.markdown('<div style="background:#fff; border-radius:16px; box-shadow:0 2px 8px rgba(0,0,0,0.07); padding:1.2rem 1rem 1.2rem 1rem; margin-bottom:1.2rem; text-align:center;">', unsafe_allow_html=True)
    st.markdown('<div style="font-size:1.2rem; font-weight:700; color:#3b4a5a; margin-bottom:0.7rem;">🧭 Vectors</div>', unsafe_allow_html=True)
    # Wind Vector Box
    wind_dir = st.session_state["wind_dir"]
    wind_to  = (wind_dir + 180.0) % 360.0
    wind_spd = st.session_state["wind_speed"]
    wind_len = int(wind_spd * VECTOR_SCALE)
    st.markdown(f'<div style="color:#888; font-size:0.95rem;">Wind Vector</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:14px;">Heading: <b>{wind_dir:.0f}°</b> (from)</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:14px;">Speed: <b>{wind_spd:.0f} m/s</b></div>', unsafe_allow_html=True)
    st.markdown(f'<span style="font-size:3.5rem; font-weight:bold; color:#1f77b4; display:block; margin:0.5rem auto 0 auto; transform: rotate({wind_to}deg);">↑</span>', unsafe_allow_html=True)
    # Drone Vector Box
    st.markdown(f'<div style="color:#888; font-size:0.95rem; margin-top:2.5rem;">Drone Vector</div>', unsafe_allow_html=True)
    drone_h   = st.session_state["drone_heading"]
    drone_to  = drone_h
    drone_spd = st.session_state["drone_speed"]
    drone_len = int(drone_spd * VECTOR_SCALE)
    st.markdown(f'<div style="font-size:14px;">Heading: <b>{drone_h:.0f}°</b></div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:14px;">Speed: <b>{drone_spd:.0f} m/s</b></div>', unsafe_allow_html=True)
    st.markdown(f'<span style="font-size:3.5rem; font-weight:bold; color:#d62728; display:block; margin:0.5rem auto 0 auto; transform: rotate({drone_to}deg);">↑</span>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# FULL-WIDTH BOTTOM BAR: "Round result: Error xxx m"
round_result_bar(st.session_state) 