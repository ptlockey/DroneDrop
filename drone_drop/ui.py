"""
UI components for the Drone Drop Game using Streamlit.
"""

import streamlit as st

def sidebar_controls(session_state, new_round_func):
    """Render the sidebar controls (Next Drop, Exit & Save)."""
    st.sidebar.header("🏷️ Controls")
    if st.sidebar.button("Next Drop"):
        new_round_func(session_state)
    if st.sidebar.button("Exit & Save"):
        import csv
        from datetime import datetime
        try:
            with open("high_scores.csv", "a", newline="") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([datetime.now().isoformat(), session_state["score"]])
            st.sidebar.success("✅ Score saved")
        except Exception as e:
            st.sidebar.error(f"Error saving score: {e}")
    st.sidebar.markdown("---")

def sidebar_environment(session_state):
    """Render the sidebar environment and score info."""
    if "difficulty" not in session_state:
        session_state["difficulty"] = "Hard"
    st.sidebar.markdown("<div style='margin-bottom:4px; font-weight:bold;'>🎚️ Difficulty</div>", unsafe_allow_html=True)
    session_state["difficulty"] = st.sidebar.radio(
        "", ["Easy", "Medium", "Hard"],
        index=["Easy", "Medium", "Hard"].index(session_state["difficulty"])
    )
    st.sidebar.markdown("---")
    st.sidebar.header("🏷️ Environment & Score")
    colA, colB = st.sidebar.columns(2)
    with colA:
        st.write(f"**Score:** {session_state['score']}")
        st.write(f"T₀: {session_state['surface_temp_c']:.0f} °C")
        st.write(f"P₀: {session_state['surface_pressure_mb']:.0f} mb")
        st.write(f"Wind from: {session_state['wind_dir']:.0f}°")
    with colB:
        st.write(" ")
        st.write(f"Wind spd: {session_state['wind_speed']:.0f} m/s")
        st.write(f"Dr Hdg: {session_state['drone_heading']:.0f}°")
        st.write(f"Dr Spd: {session_state['drone_speed']:.0f} m/s")
        st.write(f"Alt: {session_state['initial_height']:.0f} m")
        st.write(f"CdA: {session_state['CdA']:.2f} m²")
        st.write(f"Mass: {session_state['mass']:.1f} kg")

def vector_boxes(session_state, VECTOR_SCALE):
    """Render the wind and drone vector boxes in the right column."""
    import math
    st.markdown(
        '<div style="border:1px solid #333; padding:8px; border-radius:8px; margin-bottom:12px;">'
        '<div style="font-size:16px; font-weight:bold; margin-bottom:6px;">'
        'Wind Vector</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    wind_dir = session_state["wind_dir"]
    wind_to  = (wind_dir + 180.0) % 360.0
    wind_spd = session_state["wind_speed"]
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
    st.markdown(
        '<div style="border:1px solid #333; padding:8px; border-radius:8px; margin-bottom:12px;">'
        '<div style="font-size:16px; font-weight:bold; margin-bottom:6px;">'
        'Drone Vector</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    drone_h   = session_state["drone_heading"]
    drone_to  = drone_h
    drone_spd = session_state["drone_speed"]
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

def round_result_bar(session_state):
    """Render the full-width bottom bar with the round result."""
    if session_state["scored"]:
        error_display = f"Round result: Error {session_state['error_dist']:.1f} m"
    else:
        error_display = "Round result: Error — (making guess…)"
    st.markdown(
        f'<div style="border-top:2px solid #333; padding:8px; margin-top:12px; '
        'font-size:16px; font-weight:bold; text-align:center;">'
        f'{error_display}'
        '</div>',
        unsafe_allow_html=True,
    )

# Functions for sidebar, map, and main interface will go here. 