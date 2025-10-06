# DroneDrop

DroneDrop is a Streamlit-based game that simulates drone package drops with realistic physics, live mapping via Folium, and optional score tracking. The app samples random drop locations, computes trajectories accounting for wind and drag, and visualizes results on an interactive map.

## Environment setup

1. **Install Python 3.9+** if it is not already available on your system.
2. **Clone the repository** and change into the project directory:
   ```bash
   git clone https://github.com/your-org/DroneDrop.git
   cd DroneDrop
   ```
3. **(Optional) Create and activate a virtual environment** to isolate dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
   ```
4. **Install the required packages** listed in `requirements.txt`:
   ```bash
   pip install -r requirements.txt
   ```

### Built-up drop zones

The game now uses a curated catalogue of inland cities and towns to guarantee that every mission takes place over a built-up area. No external datasets need to be downloaded—locations are bundled directly with the app, and each one carries a safety radius that keeps the full flight path away from oceans and large lakes.

## How to run

Launch the Streamlit app from the project root:

```bash
streamlit run Drone_Drop_Game-20.py
```

Streamlit will open a browser window (or provide a local URL) where you can play the game.

## Persistence and saved assets

High scores are stored in `high_scores.csv`. The file is created in the project root the first time a score is saved, so ensure the application has write access to this directory if you want to keep score history.
