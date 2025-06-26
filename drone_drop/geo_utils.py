import os
import random
import geopandas as gpd
from shapely.geometry import shape, Point
import fiona

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
CITIES_PATH = os.path.join(DATA_DIR, 'ne_110m_populated_places.shp')
LAND_PATH = os.path.join(DATA_DIR, 'ne_110m_land.shp')

_cities_gdf    = None
_use_land_check = False
_land_features = []

try:
    _cities_gdf = gpd.read_file(CITIES_PATH)
    with fiona.open(LAND_PATH) as src:
        _land_features = list(src)
    _use_land_check = True
except Exception as e:
    _cities_gdf = None
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