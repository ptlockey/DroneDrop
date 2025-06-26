import streamlit as st
from drone_drop.game import new_round, compute_trajectory
from drone_drop.geo_utils import get_random_city_point

st.set_page_config(page_title="Drone Drop Game", layout="wide")

# Initialize session state if needed
def initialize():
    if "initialized" not in st.session_state:
        st.session_state["initialized"] = True
        st.session_state["score"] = 0
        new_round(st.session_state)

initialize()

# TODO: Add UI rendering and game loop here
st.title("🚁 Drone Drop Game")
st.write("Game UI coming soon...") 