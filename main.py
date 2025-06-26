import streamlit as st
import folium
from streamlit_folium import st_folium
import math
from drone_drop.game import compute_trajectory, new_round, VECTOR_SCALE, MAP_SIZE, BASE_RADII, BASE_POINTS
from drone_drop.ui import sidebar_controls, sidebar_environment, vector_boxes, round_result_bar

st.set_page_config(page_title="Drone Drop Game", layout="wide")

# Initialize once
if "initialized" not in st.session_state:
    st.session_state["initialized"] = True
    st.session_state["score"] = 0
    new_round(st.session_state)

# Title flush at top with minimal margin
st.markdown(
    '<div style="font-size:24px; font-weight:bold; text-align:center; margin-bottom:4px;">'
    '🚁 Drone Drop Game</div>',
    unsafe_allow_html=True,
)

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
col_map, col_vecs = st.columns((3, 1))

# CENTER COLUMN: SQUARE MAP + SINGLE-CLICK LOGIC
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

        # Curved green trajectory
        trajectory_xy = st.session_state["trajectory_xy"]
        lat_lon_points = [
            [
                start_lat + (y / 111111.0),
                start_lon + (
                    x / (111111.0 * math.cos(math.radians(start_lat)))
                ),
            ]
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

# RIGHT COLUMN: WIND & DRONE VECTOR BOXES (tight margins)
with col_vecs:
    vector_boxes(st.session_state, VECTOR_SCALE)

# FULL-WIDTH BOTTOM BAR: "Round result: Error xxx m"
round_result_bar(st.session_state) 