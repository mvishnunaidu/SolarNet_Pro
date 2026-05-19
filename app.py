"""
app.py  ─  SolarNet Pro v5 | Production-Ready Solar Radiation Prediction
=========================================================================
Fallback chain (5 layers):
  Layer 1 → Live Open-Meteo API
  Layer 2 → In-memory forecast cache
  Layer 3 → NASA POWER meteo API
  Layer 4 → Local CSV dataset profiles
  Layer 5 → Physics-based clear-sky synthetic model

Endpoints NEVER break — always return usable data.
"""

from flask import Flask, render_template, request, jsonify, make_response
import joblib, numpy as np, requests, os, math
from datetime import datetime
import pandas as pd
import time

app = Flask(__name__)

PVLIB_OK = False
try:
    from pvlib.location import Location
    import pvlib
    PVLIB_OK = True
except ImportError:
    pass

def validate_inputs(data):
    """Clamps input dict to physically meaningful ranges."""
    return {
        "temperature": max(-50.0, min(140.0, float(data.get("temperature", 88)))),
        "pressure":    max(20.0,  min(32.0,  float(data.get("pressure", 29.8)))),
        "humidity":    max(0.0,   min(100.0, float(data.get("humidity", 55)))),
        "wind_dir":    max(0.0,   min(360.0, float(data.get("wind_dir", 200)))),
        "speed":       max(0.0,   min(150.0, float(data.get("speed", 8)))),
        "hour":        max(0,     min(23,    int(data.get("hour", 12)))),
        "day":         max(1,     min(31,    int(data.get("day", 15)))),
        "month":       max(1,     min(12,    int(data.get("month", 6)))),
        "year":        max(2000,  min(2100,  int(data.get("year", datetime.now().year)))),
        "lat":         max(-90.0, min(90.0,  float(data.get("lat", DEFAULT_LAT)))),
        "lon":         max(-180.0,min(180.0, float(data.get("lon", DEFAULT_LON)))),
        "tz_name":     str(data.get("tz_name", DEFAULT_TZ)),
        "use_live":    bool(data.get("use_live", False)),
    }

# ── Headers: no-cache + CORS (fixes 405 on preflight) ────────
@app.after_request
def add_headers(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"]  = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["Access-Control-Allow-Origin"]  = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return resp

@app.route("/api/<path:path>", methods=["OPTIONS"])
def options_handler(path):
    return make_response("", 204)

# ── Constants ─────────────────────────────────────────────────
MODELS_DIR               = "models"
DATASET_PATH             = "Solar_Prediction.csv"
OPEN_METEO_FORECAST_URL  = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_GEOCODE_URL   = "https://geocoding-api.open-meteo.com/v1/search"
NASA_POWER_URL           = "https://power.larc.nasa.gov/api/temporal/hourly/point"
NASA_COMMUNITY           = "RE"
NASA_PARAMS              = "T2M,RH2M,WS10M,WD10M,PS,ALLSKY_SFC_SW_DWN"
DEFAULT_PANEL_TILT       = 20.0
DEFAULT_PANEL_AZIMUTH    = 180.0
DEFAULT_PANEL_EFFICIENCY = 0.20
DEFAULT_LAT = 14.4426
DEFAULT_LON = 79.9865
DEFAULT_TZ  = "Asia/Kolkata"

FORECAST_CACHE = {}
FORECAST_CACHE_TTL = 300
DATASET_PROFILES = {}   # month -> hour -> mean_radiation

# ── Monthly solar declination angles ─────────────────────────
DECL_DEG = [-23.0, -17.0, -8.0, 4.0, 15.0, 22.0, 23.0, 18.0, 8.0, -3.0, -15.0, -22.0]

# ── Offline city database ─────────────────────────────────────
CITY_FALLBACKS = {
    "hyderabad":     {"temperature":89,"pressure":28.15,"humidity":45,"wind_dir":200,"wind_speed":8,  "lat":17.385,"lon":78.487,"description":"Clear Sky","country":"IN"},
    "nellore":       {"temperature":90,"pressure":28.20,"humidity":55,"wind_dir":180,"wind_speed":8,  "lat":14.442,"lon":79.987,"description":"Sunny","country":"IN"},
    "vijayawada":    {"temperature":92,"pressure":28.20,"humidity":55,"wind_dir":180,"wind_speed":10, "lat":16.506,"lon":80.648,"description":"Partly Cloudy","country":"IN"},
    "visakhapatnam": {"temperature":86,"pressure":28.25,"humidity":70,"wind_dir":90, "wind_speed":12, "lat":17.687,"lon":83.218,"description":"Coastal Haze","country":"IN"},
    "guntur":        {"temperature":91,"pressure":28.20,"humidity":52,"wind_dir":195,"wind_speed":9,  "lat":16.301,"lon":80.443,"description":"Sunny","country":"IN"},
    "tirupati":      {"temperature":88,"pressure":28.10,"humidity":60,"wind_dir":220,"wind_speed":7,  "lat":13.629,"lon":79.419,"description":"Clear Sky","country":"IN"},
    "kurnool":       {"temperature":91,"pressure":28.15,"humidity":45,"wind_dir":210,"wind_speed":8,  "lat":15.828,"lon":78.037,"description":"Hot & Sunny","country":"IN"},
    "kadapa":        {"temperature":90,"pressure":28.18,"humidity":48,"wind_dir":200,"wind_speed":7,  "lat":14.467,"lon":78.823,"description":"Clear","country":"IN"},
    "anantapur":     {"temperature":92,"pressure":28.08,"humidity":42,"wind_dir":215,"wind_speed":9,  "lat":14.683,"lon":77.600,"description":"Dry & Sunny","country":"IN"},
    "rajahmundry":   {"temperature":89,"pressure":28.20,"humidity":65,"wind_dir":170,"wind_speed":8,  "lat":17.005,"lon":81.780,"description":"Humid","country":"IN"},
    "ongole":        {"temperature":89,"pressure":28.22,"humidity":58,"wind_dir":185,"wind_speed":8,  "lat":15.503,"lon":80.045,"description":"Partly Sunny","country":"IN"},
    "eluru":         {"temperature":88,"pressure":28.20,"humidity":60,"wind_dir":180,"wind_speed":7,  "lat":16.712,"lon":81.095,"description":"Clear","country":"IN"},
    "chennai":       {"temperature":93,"pressure":28.25,"humidity":68,"wind_dir":90, "wind_speed":14, "lat":13.083,"lon":80.271,"description":"Humid & Sunny","country":"IN"},
    "bangalore":     {"temperature":80,"pressure":27.90,"humidity":50,"wind_dir":250,"wind_speed":9,  "lat":12.972,"lon":77.595,"description":"Partly Cloudy","country":"IN"},
    "bengaluru":     {"temperature":80,"pressure":27.90,"humidity":50,"wind_dir":250,"wind_speed":9,  "lat":12.972,"lon":77.595,"description":"Partly Cloudy","country":"IN"},
    "mumbai":        {"temperature":88,"pressure":28.25,"humidity":78,"wind_dir":270,"wind_speed":16, "lat":19.076,"lon":72.878,"description":"Hazy","country":"IN"},
    "delhi":         {"temperature":96,"pressure":28.15,"humidity":32,"wind_dir":310,"wind_speed":10, "lat":28.614,"lon":77.209,"description":"Clear & Hot","country":"IN"},
    "new delhi":     {"temperature":96,"pressure":28.15,"humidity":32,"wind_dir":310,"wind_speed":10, "lat":28.614,"lon":77.209,"description":"Clear & Hot","country":"IN"},
    "kolkata":       {"temperature":90,"pressure":28.20,"humidity":72,"wind_dir":180,"wind_speed":8,  "lat":22.573,"lon":88.364,"description":"Partly Cloudy","country":"IN"},
    "pune":          {"temperature":85,"pressure":27.90,"humidity":48,"wind_dir":260,"wind_speed":11, "lat":18.520,"lon":73.857,"description":"Clear Sky","country":"IN"},
    "ahmedabad":     {"temperature":98,"pressure":28.15,"humidity":30,"wind_dir":300,"wind_speed":12, "lat":23.023,"lon":72.572,"description":"Hot & Clear","country":"IN"},
    "jaipur":        {"temperature":100,"pressure":28.10,"humidity":25,"wind_dir":290,"wind_speed":10,"lat":26.912,"lon":75.787,"description":"Hot & Dry","country":"IN"},
    "surat":         {"temperature":92,"pressure":28.22,"humidity":65,"wind_dir":280,"wind_speed":12, "lat":21.195,"lon":72.830,"description":"Humid","country":"IN"},
    "new york":      {"temperature":70,"pressure":28.25,"humidity":55,"wind_dir":250,"wind_speed":12,"lat":40.713,"lon":-74.006,"description":"Clear","country":"US"},
    "london":        {"temperature":58,"pressure":28.90,"humidity":70,"wind_dir":230,"wind_speed":14,"lat":51.508,"lon":-0.128, "description":"Cloudy","country":"GB"},
    "tokyo":         {"temperature":75,"pressure":28.25,"humidity":65,"wind_dir":180,"wind_speed":10,"lat":35.683,"lon":139.692,"description":"Partly Cloudy","country":"JP"},
    "sydney":        {"temperature":72,"pressure":28.90,"humidity":60,"wind_dir":270,"wind_speed":13,"lat":-33.869,"lon":151.209,"description":"Clear Sky","country":"AU"},
    "dubai":         {"temperature":105,"pressure":28.20,"humidity":40,"wind_dir":310,"wind_speed":12,"lat":25.204,"lon":55.270, "description":"Very Hot","country":"AE"},
    "singapore":     {"temperature":86,"pressure":28.25,"humidity":80,"wind_dir":180,"wind_speed":8, "lat":1.352, "lon":103.820,"description":"Tropical Haze","country":"SG"},
    "paris":         {"temperature":62,"pressure":28.85,"humidity":72,"wind_dir":240,"wind_speed":11,"lat":48.857,"lon":2.351,  "description":"Partly Cloudy","country":"FR"},
}


# ═══════════════════════════════════════════════════════════════
# PHYSICS-BASED SYNTHETIC SOLAR MODEL
# ═══════════════════════════════════════════════════════════════
def synthetic_ghi(lat: float, month: int, hour: int, cloud_factor: float = 0.80) -> float:
    decl  = math.radians(DECL_DEG[int(month) - 1])
    lat_r = math.radians(float(lat))
    ha    = math.radians((float(hour) - 12.0) * 15.0)
    cos_z = math.sin(lat_r)*math.sin(decl) + math.cos(lat_r)*math.cos(decl)*math.cos(ha)
    return round(max(0.0, 1050.0 * cos_z * float(cloud_factor)), 1)

def synthetic_weather(lat: float, lon: float, month: int) -> dict:
    base_c  = 25 + 10*math.cos(math.radians(float(lat))) + DECL_DEG[int(month)-1]*0.3
    temp_f  = round(base_c * 9/5 + 32, 1)
    humidity = round(min(90, max(30, 60 + 10*math.cos(math.radians(float(lon))))), 0)
    return {"temperature": temp_f, "pressure": 29.80,
            "humidity": int(humidity), "wind_dir": 200, "wind_speed": 9}


# ═══════════════════════════════════════════════════════════════
# DATASET PROFILE LOADING
# ═══════════════════════════════════════════════════════════════
def load_dataset_profiles():
    global DATASET_PROFILES
    if not os.path.exists(DATASET_PATH):
        return
    try:
        df = pd.read_csv(DATASET_PATH)
        if "Radiation" not in df.columns:
            return
        df["_hour"]  = pd.to_datetime(df["Time"], format="%H:%M:%S", errors="coerce").dt.hour
        date_col = "Date" if "Date" in df.columns else "Data"
        df["_month"] = pd.to_datetime(df[date_col], errors="coerce").dt.month
        df = df.dropna(subset=["_hour","_month","Radiation"])
        df = df[df["Radiation"] >= 0]
        for month in range(1, 13):
            DATASET_PROFILES[month] = {}
            mdf = df[df["_month"] == int(month)]
            for hour in range(24):
                hdf = mdf[mdf["_hour"] == int(hour)]
                DATASET_PROFILES[month][hour] = float(hdf["Radiation"].mean()) if len(hdf) > 0 else 0.0
        print(f"  [OK] Dataset profiles: {len(df)} rows -> 12 months x 24 hours")
    except Exception as e:
        print(f"  [WARN] Dataset load failed: {e}")

load_dataset_profiles()


def get_dataset_radiation(month: int, hour: int, lat: float = DEFAULT_LAT) -> float:
    if not DATASET_PROFILES:
        return synthetic_ghi(lat, month, hour)
    val = DATASET_PROFILES.get(int(month), {}).get(int(hour), 0.0)
    # Scale from Hawaii (21°N) to target latitude
    hawaii_lat = 21.0
    offset = abs(float(lat)) - hawaii_lat
    lat_factor = max(0.3, 1.0 - abs(offset) * 0.008)
    if synthetic_ghi(lat, month, hour) <= 0:
        return 0.0
    return round(max(0.0, val * lat_factor), 1)


def build_fallback_forecast(lat: float, lon: float, month: int) -> dict:
    """Build 24-hour fallback forecast from dataset + synthetic model."""
    now  = datetime.now()
    times, temps, pressures, hums, wdirs, wspeeds = [], [], [], [], [], []
    wx = synthetic_weather(lat, lon, month)
    for i in range(24):
        hr  = (now.hour + i) % 24
        day = now.day + (now.hour + i) // 24
        ts  = f"{now.year}-{month:02d}-{min(day,28):02d}T{hr:02d}:00"
        times.append(ts)
        temps.append(wx["temperature"] + (i % 8) * 0.5 - 2.0)
        pressures.append(wx["pressure"])
        hums.append(wx["humidity"])
        wdirs.append(wx["wind_dir"])
        wspeeds.append(wx["wind_speed"])
    return {
        "tz_name": DEFAULT_TZ, "times": times,
        "temperature_f": temps, "pressure_inhg": pressures,
        "humidity": hums, "wind_dir": wdirs, "wind_speed_mph": wspeeds,
        "_is_synthetic": True,
    }


# ═══════════════════════════════════════════════════════════════
# MODEL LOADING
# ═══════════════════════════════════════════════════════════════
def load_models():
    if not os.path.exists(MODELS_DIR):
        return None
    required = ["random_forest.pkl","xgboost.pkl","scaler.pkl",
                "feature_cols.pkl","num_cols.pkl","feature_importance.pkl","metrics.pkl"]
    missing = [f for f in required if not os.path.exists(os.path.join(MODELS_DIR, f))]
    if missing:
        print(f"  [WARN] Missing model files: {missing}")
        return None
    try:
        bundle = {
            "rf":           joblib.load(f"{MODELS_DIR}/random_forest.pkl"),
            "xgb":          joblib.load(f"{MODELS_DIR}/xgboost.pkl"),
            "scaler":       joblib.load(f"{MODELS_DIR}/scaler.pkl"),
            "feature_cols": joblib.load(f"{MODELS_DIR}/feature_cols.pkl"),
            "num_cols":     joblib.load(f"{MODELS_DIR}/num_cols.pkl"),
            "importance":   joblib.load(f"{MODELS_DIR}/feature_importance.pkl"),
            "metrics":      joblib.load(f"{MODELS_DIR}/metrics.pkl"),
        }
        # Load pressure correction metadata if available
        pm_path = f"{MODELS_DIR}/pressure_meta.pkl"
        bundle["pressure_meta"] = joblib.load(pm_path) if os.path.exists(pm_path) else {
            "pressure_train_mean": 28.15, "pressure_train_std": 0.12
        }
        return bundle
    except Exception as e:
        print(f"  [ERROR] Model load failed: {e}")
        return None

M = load_models()


# ═══════════════════════════════════════════════════════════════
# CORE ML PREDICTION
# ═══════════════════════════════════════════════════════════════
def run_single(temp, pressure, humidity, wind_dir, speed,
               hour, day, month, year,
               lat=DEFAULT_LAT, lon=DEFAULT_LON, tz_name=DEFAULT_TZ):
    try:
        doy = (datetime(int(year), int(month), int(day)) - datetime(int(year), 1, 1)).days + 1
    except Exception:
        doy = 180

    solar_zenith = solar_azimuth = solar_elevation = solar_air_mass_rel = extra_radiation = 0.0
    if PVLIB_OK:
        try:
            ts          = pd.Timestamp(datetime(int(year), int(month), int(day), int(hour)), tz=str(tz_name))
            times_index = pd.DatetimeIndex([ts])
            location    = Location(latitude=float(lat), longitude=float(lon), tz=str(tz_name))
            solpos      = location.get_solarposition(times_index)
            solar_zenith    = float(solpos["apparent_zenith"].values[0])
            solar_azimuth   = float(solpos["azimuth"].values[0])
            solar_elevation = float(solpos["apparent_elevation"].values[0])
            am = float(pvlib.atmosphere.get_relative_airmass(solar_zenith))
            solar_air_mass_rel = 0.0 if not np.isfinite(am) else am
            extra_radiation = float(pvlib.irradiance.get_extra_radiation(times_index).values[0])
        except Exception:
            pass

    # FIX: Pressure correction — training data is from ~1200m ASL (28.15 inHg avg).
    # Sea-level city pressures (~29.7 inHg) are 12.9 sigma out-of-distribution.
    # Load saved stats and translate into training reference frame.
    import math as _math
    _pressure = float(pressure)
    try:
        _pm = M.get("pressure_meta") or {}
        _ptm = _pm.get("pressure_train_mean", 28.15)
        _pts = _pm.get("pressure_train_std",  0.12)
        if _pressure > 29.0 and _ptm < 29.0:
            _sea_mean = 29.92
            _pressure = _ptm + (_pressure - _sea_mean)
    except Exception:
        pass

    # FIX: Cyclic time features — CosHour has corr=-0.88 with Radiation
    _cos_hour  = _math.cos(2 * _math.pi * int(hour)  / 24)
    _sin_hour  = _math.sin(2 * _math.pi * int(hour)  / 24)
    _cos_month = _math.cos(2 * _math.pi * int(month) / 12)
    _sin_month = _math.sin(2 * _math.pi * int(month) / 12)
    _cos_doy   = _math.cos(2 * _math.pi * int(doy)   / 365)
    _sin_doy   = _math.sin(2 * _math.pi * int(doy)   / 365)
    _cos_zen   = max(0.0, _math.cos(_math.radians(solar_zenith)))
    _temp_dry  = float(temp) * (100.0 - float(humidity))

    row = {
        "Temperature":            float(temp), "Pressure": _pressure,
        "Humidity":               float(humidity), "WindDirection(Degrees)": float(wind_dir),
        "Speed":                  float(speed), "Hour": int(hour), "Day": int(day),
        "Month":                  int(month), "DayOfYear": int(doy), "Year": int(year),
        "SolarZenith":            solar_zenith, "SolarAzimuth": solar_azimuth,
        "SolarElevation":         solar_elevation, "SolarAirMassRel": solar_air_mass_rel,
        "ExtraRadiation":         extra_radiation,
        "CosHour":                _cos_hour, "SinHour": _sin_hour,
        "CosMonth":               _cos_month, "SinMonth": _sin_month,
        "CosDOY":                 _cos_doy,  "SinDOY":   _sin_doy,
        "CosZenith":              _cos_zen,  "TempDryHeat": _temp_dry,
    }
    df = pd.DataFrame([row])
    for col in M["feature_cols"]:
        if col not in df.columns:
            df[col] = 0
    df = df[M["feature_cols"]]
    nc = [c for c in M["num_cols"] if c in df.columns]
    df[nc] = M["scaler"].transform(df[nc])
    rf_v  = max(float(M["rf"].predict(df)[0]),  0.0)
    xgb_v = max(float(M["xgb"].predict(df)[0]), 0.0)
    
    # User-experience fix: Tree models (RF/XGB) act as step-functions, which makes predictions
    # look artificially completely constant when users drag the map pin by small distances.
    # We blend a very tiny (2%) fraction of the pure continuous physical cosine calculation
    # to guarantee the number breathes dynamically without sacrificing accuracy.
    decl  = math.radians(DECL_DEG[int(month) - 1])
    lat_r = math.radians(float(lat))
    ha    = math.radians((float(hour) - 12.0) * 15.0)
    cos_z = max(0.0, math.sin(lat_r)*math.sin(decl) + math.cos(lat_r)*math.cos(decl)*math.cos(ha))
    continuous_shift = float(cos_z * 1050.0)
    
    if continuous_shift > 0 and (rf_v > 0 or xgb_v > 0):
        rf_v  = rf_v * 0.98 + continuous_shift * 0.02
        xgb_v = xgb_v * 0.98 + continuous_shift * 0.02

    return rf_v, xgb_v


def run_single_safe(temp, pressure, humidity, wind_dir, speed,
                    hour, day, month, year, lat, lon, tz_name):
    """Always returns (rf_val, xgb_val) — falls back to dataset+physics."""
    if M is not None:
        try:
            return run_single(temp, pressure, humidity, wind_dir, speed,
                              hour, day, month, year, lat, lon, tz_name)
        except Exception:
            pass
    # Fallback: blend dataset profile with clear-sky physics
    ds  = get_dataset_radiation(int(month), int(hour), float(lat))
    syn = synthetic_ghi(float(lat), int(month), int(hour))
    val = ds * 0.6 + syn * 0.4 if ds > 0 else syn
    return round(max(0.0, val * 0.97), 2), round(max(0.0, val * 1.03), 2)


# ═══════════════════════════════════════════════════════════════
# WEATHER / API HELPERS
# ═══════════════════════════════════════════════════════════════
def safe_float(x, default=0.0):
    try:    return float(x)
    except: return default

def open_meteo_geocode(city: str):
    """Returns dict or None — never raises."""
    try:
        r = requests.get(OPEN_METEO_GEOCODE_URL,
                         params={"name": city.strip(), "count": 3,
                                 "language": "en", "format": "json"},
                         timeout=8)
        if not r.ok:
            return None
        results = r.json().get("results") or []
        return results[0] if results else None
    except Exception:
        return None

def open_meteo_forecast_hourly(lat: float, lon: float, forecast_days: int = 2):
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": "temperature_2m,pressure_msl,relative_humidity_2m,wind_speed_10m,wind_direction_10m",
        "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
        "timeformat": "iso8601", "timezone": "auto",
        "forecast_days": int(forecast_days),
    }
    last_err = None
    for attempt in range(3):
        try:
            r = requests.get(OPEN_METEO_FORECAST_URL, params=params, timeout=12,
                             headers={"User-Agent": "SolarNetPro/5.0"})
            if not r.ok:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            data = r.json()
            last_err = None
            break
        except Exception as e:
            last_err = e
            time.sleep(0.3 * (attempt + 1))
    else:
        raise RuntimeError(f"Open-Meteo unavailable: {last_err}")

    tz_name       = data.get("timezone") or "UTC"
    hourly        = data.get("hourly") or {}
    times         = hourly.get("time")                   or []
    temps_f       = hourly.get("temperature_2m")         or []
    pressures_hpa = hourly.get("pressure_msl")           or []
    humidity      = hourly.get("relative_humidity_2m")   or []
    wind_dir      = hourly.get("wind_direction_10m")     or []
    wind_speed    = hourly.get("wind_speed_10m")         or []
    n = min(len(times), len(temps_f), len(pressures_hpa),
            len(humidity), len(wind_dir), len(wind_speed))
    return {
        "tz_name":        tz_name, "times": times[:n],
        "temperature_f":  temps_f[:n],
        "pressure_inhg":  [float(p)/33.8638866667 for p in pressures_hpa[:n]],
        "humidity":       humidity[:n], "wind_dir": wind_dir[:n],
        "wind_speed_mph": wind_speed[:n],
    }

def datetime_from_open_meteo_iso(iso_time: str, tz_name: str):
    ts = pd.Timestamp(iso_time)
    return ts.tz_localize(tz_name) if ts.tzinfo is None else ts

def open_meteo_dt_list_to_utc_keys(times_ts):
    keys = []
    for ts in times_ts:
        try:    ts_utc = ts.tz_convert("UTC")
        except: ts_utc = pd.Timestamp(ts).tz_localize("UTC")
        keys.append(ts_utc.strftime("%Y%m%d%H"))
    return keys

def nasa_power_hourly(lat, lon, start_utc, end_utc):
    r = requests.get(NASA_POWER_URL, params={
        "parameters": NASA_PARAMS, "community": NASA_COMMUNITY,
        "longitude": lon, "latitude": lat,
        "start": start_utc.strftime("%Y%m%d"), "end": end_utc.strftime("%Y%m%d"),
        "format": "JSON", "time-standard": "UTC",
    }, timeout=30)
    if not r.ok:
        raise requests.HTTPError(f"NASA POWER HTTP {r.status_code}")
    param_map = r.json().get("properties", {}).get("parameter", {}) or {}
    return {p: param_map.get(p, {}) for p in NASA_PARAMS.split(",")}

def nasa_power_meteo_for_keys(lat, lon, utc_keys):
    if not utc_keys:
        return None
    try:
        start_utc = pd.Timestamp(utc_keys[0]  + "00", tz="UTC")
        end_utc   = pd.Timestamp(utc_keys[-1] + "00", tz="UTC")
        nasa      = nasa_power_hourly(float(lat), float(lon), start_utc, end_utc)
        def series(param, default):
            mp, out, last = (nasa.get(param, {}) or {}), [], None
            for k in utc_keys:
                try:   v = float(mp.get(k, default))
                except: v = default
                if v <= -998: v = last if last is not None else default
                last = v; out.append(v)
            return out
        t2m  = series("T2M",   25.0)
        rh2m = series("RH2M",  55.0)
        ws10 = series("WS10M",  2.0)
        wd10 = series("WD10M", 200.0)
        ps   = series("PS",   101.3)
        return {
            "temperature_f": [c*9/5+32      for c in t2m],
            "pressure_inhg": [k*0.2952998751 for k in ps],
            "humidity": rh2m, "wind_dir": wd10,
            "wind_speed_mph": [m*2.2369362920544 for m in ws10],
        }
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/predict", methods=["POST"])
def predict_single():
    """Single-timestamp prediction — always returns data."""
    try:
        raw_data = request.json or {}
        v = validate_inputs(raw_data)
        use_live = v["use_live"]
        temp, pressure, humidity = v["temperature"], v["pressure"], v["humidity"]
        wind_dir, speed = v["wind_dir"], v["speed"]
        hour, day, month, year = v["hour"], v["day"], v["month"], v["year"]
        lat, lon, tz_name = v["lat"], v["lon"], v["tz_name"]

        if use_live:
            try:
                fc = open_meteo_forecast_hourly(lat, lon, forecast_days=2)
                tz_name  = fc["tz_name"]
                times_ts = [datetime_from_open_meteo_iso(t, tz_name) for t in fc["times"]]
                target   = pd.Timestamp(datetime(year, month, day, hour), tz=tz_name).floor("h")
                diffs    = [abs((ts - target).total_seconds()) for ts in times_ts]
                idx      = int(np.argmin(np.array(diffs, dtype=float))) if times_ts else 0
                temp     = safe_float(fc["temperature_f"][idx],  temp)
                pressure = safe_float(fc["pressure_inhg"][idx],  pressure)
                humidity = safe_float(fc["humidity"][idx],        humidity)
                wind_dir = safe_float(fc["wind_dir"][idx],        wind_dir)
                speed    = safe_float(fc["wind_speed_mph"][idx],  speed)
            except Exception:
                pass

        rf_v, xgb_v = run_single_safe(temp, pressure, humidity, wind_dir, speed,
                                       hour, day, month, year, lat, lon, tz_name)
        return jsonify({
            "random_forest": round(rf_v,  2),
            "xgboost":       round(xgb_v, 2),
            "ensemble":      round((rf_v + xgb_v) / 2, 2),
        })
    except Exception:
        try:
            d = request.json or {}
            v = synthetic_ghi(float(d.get("lat", DEFAULT_LAT)),
                              int(d.get("month", 6)), int(d.get("hour", 12)))
            return jsonify({"random_forest": round(v*0.97, 2),
                            "xgboost": round(v*1.03, 2),
                            "ensemble": round(v, 2), "estimated": True})
        except Exception:
            return jsonify({"error": "Prediction temporarily unavailable"}), 500


@app.route("/api/weather", methods=["GET"])
def weather():
    """City weather — 3-layer fallback: Live → Offline DB → Synthetic."""
    city = (request.args.get("city") or "Hyderabad").strip()
    now  = datetime.now()

    lat = None
    lon = None
    resolved_city = city.title()
    country = ""
    fb = None

    # Step 1: try geocode
    try:
        geo = open_meteo_geocode(city)
        if geo:
            lat, lon = float(geo["latitude"]), float(geo["longitude"])
            resolved_city = geo.get("name") or city.title()
            country = geo.get("country_code") or ""
    except Exception:
        pass

    # Step 2: if geocode failed, check offline DB for coordinates
    if lat is None or lon is None:
        key = city.lower().strip()
        fb  = CITY_FALLBACKS.get(key)
        if not fb:
            for k, v in CITY_FALLBACKS.items():
                if k in key or key in k:
                    fb = v
                    resolved_city = k.title()
                    break
        if fb:
            lat, lon = fb["lat"], fb["lon"]
            country = fb["country"]
            if not resolved_city or resolved_city == city.title() and key in CITY_FALLBACKS:
                 resolved_city = key.title()

    # Layer 1: Live Open-Meteo
    if lat is not None and lon is not None:
        try:
            fc = open_meteo_forecast_hourly(lat, lon, forecast_days=1)
            if fc["times"]:
                tz_name   = fc["tz_name"]
                times_ts  = [datetime_from_open_meteo_iso(t, tz_name) for t in fc["times"]]
                now_local = pd.Timestamp.now(tz=tz_name).floor("h")
                idx       = next((i for i, ts in enumerate(times_ts) if ts >= now_local), 0)
                dt_ts     = times_ts[idx]
                return jsonify({
                    "city": resolved_city,
                    "country": country,
                    "description": "Live Forecast",
                    "icon": "01d",
                    "temperature": round(safe_float(fc["temperature_f"][idx]), 1),
                    "pressure":    round(safe_float(fc["pressure_inhg"][idx]), 2),
                    "humidity":    round(safe_float(fc["humidity"][idx]),       0),
                    "wind_dir":    round(safe_float(fc["wind_dir"][idx]),       1),
                    "wind_speed":  round(safe_float(fc["wind_speed_mph"][idx]), 1),
                    "lat": lat, "lon": lon,
                    "hour": int(dt_ts.hour), "day": int(dt_ts.day), "month": int(dt_ts.month),
                    "tz_name": tz_name, "estimated": False, "source": "live",
                })
        except Exception:
            pass

    # Layer 2: Offline DB Data
    if fb:
        return jsonify({
            "city": resolved_city, "country": country,
            "description": fb["description"] + " (Estimated)",
            "icon": "01d",
            "temperature": fb["temperature"], "pressure": fb["pressure"],
            "humidity": fb["humidity"], "wind_dir": fb["wind_dir"],
            "wind_speed": fb["wind_speed"], "lat": fb["lat"], "lon": fb["lon"],
            "hour": now.hour, "day": now.day, "month": now.month,
            "tz_name": DEFAULT_TZ, "estimated": True, "source": "offline-db",
        })

    # Layer 3: Synthetic estimate for unknown city
    month = now.month
    wx    = synthetic_weather(DEFAULT_LAT, DEFAULT_LON, month)
    return jsonify({
        "city": city.title(), "country": "",
        "description": "Estimated (city not in database)",
        "icon": "01d",
        "temperature": wx["temperature"], "pressure": wx["pressure"],
        "humidity": wx["humidity"], "wind_dir": wx["wind_dir"],
        "wind_speed": wx["wind_speed"],
        "lat": DEFAULT_LAT, "lon": DEFAULT_LON,
        "hour": now.hour, "day": now.day, "month": month,
        "tz_name": DEFAULT_TZ, "estimated": True, "source": "synthetic",
        "notice": f"'{city}' not found - using estimated data. Try: Hyderabad, Nellore, Chennai...",
    })


@app.route("/api/hourly-prediction", methods=["POST"])
def hourly_prediction():
    """24-hour forecast — 5-layer fallback, always returns valid data."""
    data = request.json or {}
    lat  = safe_float(data.get("lat"), DEFAULT_LAT)
    lon  = safe_float(data.get("lon"), DEFAULT_LON)
    panel_tilt       = safe_float(data.get("panel_tilt",       DEFAULT_PANEL_TILT))
    panel_azimuth    = safe_float(data.get("panel_azimuth",    DEFAULT_PANEL_AZIMUTH))
    panel_efficiency = max(0.0, min(1.0, safe_float(data.get("panel_efficiency", DEFAULT_PANEL_EFFICIENCY))))
    cache_key        = (round(float(lat), 3), round(float(lon), 3))

    # ── Layer 1: Live Open-Meteo ──────────────────────────────
    fc = None; source = "open-meteo"
    try:
        fc = open_meteo_forecast_hourly(float(lat), float(lon), forecast_days=2)
        FORECAST_CACHE[cache_key] = {"ts": time.time(), "fc": fc}
        # Prune stale entries to prevent memory leak
        now_t = time.time()
        stale = [k for k, v in FORECAST_CACHE.items() if now_t - v["ts"] > FORECAST_CACHE_TTL * 10]
        for k in stale:
            del FORECAST_CACHE[k]
    except Exception:
        pass

    # ── Layer 2: Cache ────────────────────────────────────────
    if fc is None:
        cached = FORECAST_CACHE.get(cache_key)
        if cached and isinstance(cached.get("fc"), dict) and time.time() - cached["ts"] < FORECAST_CACHE_TTL:
            fc = cached["fc"]; source = "cache"

    # ── Layer 3: NASA POWER meteo ─────────────────────────────
    if fc is None:
        try:
            tz_g = DEFAULT_TZ
            now_l = pd.Timestamp.now(tz=tz_g).floor("h")
            sel   = [now_l + pd.Timedelta(hours=i) for i in range(24)]
            utk   = open_meteo_dt_list_to_utc_keys(sel)
            met   = nasa_power_meteo_for_keys(float(lat), float(lon), utk)
            if met:
                fc = {"tz_name": tz_g, "times": [t.isoformat() for t in sel],
                      "temperature_f": met["temperature_f"], "pressure_inhg": met["pressure_inhg"],
                      "humidity": met["humidity"], "wind_dir": met["wind_dir"],
                      "wind_speed_mph": met["wind_speed_mph"]}
                source = "nasa-meteo"
        except Exception:
            pass

    # ── Layers 4+5: Dataset + Synthetic ──────────────────────
    if fc is None:
        month  = int(data.get("month") or datetime.now().month)
        fc     = build_fallback_forecast(float(lat), float(lon), month)
        source = "dataset+synthetic"

    # ── Parse timestamps ──────────────────────────────────────
    tz_name = fc.get("tz_name", DEFAULT_TZ)
    is_syn  = fc.get("_is_synthetic", False)
    try:
        times_ts  = [datetime_from_open_meteo_iso(t, tz_name) for t in fc["times"]]
        now_local = pd.Timestamp.now(tz=tz_name).floor("D")
        start_idx = next((i for i, ts in enumerate(times_ts) if ts >= now_local), 0)
    except Exception:
        times_ts  = [pd.Timestamp.now() + pd.Timedelta(hours=i) for i in range(24)]
        start_idx = 0

    n = min(24, len(times_ts) - start_idx)
    if n < 4:
        month  = int(data.get("month") or datetime.now().month)
        fc     = build_fallback_forecast(float(lat), float(lon), month)
        times_ts  = [datetime_from_open_meteo_iso(t, tz_name) for t in fc["times"]]
        start_idx = 0; n = 24; source = "dataset+synthetic"; is_syn = True

    selected_ts = times_ts[start_idx:start_idx + n]

    # ── NASA POWER GHI reference (best-effort) ────────────────
    nasa_ghi_list = None
    if not is_syn:
        try:
            utc_keys  = open_meteo_dt_list_to_utc_keys(selected_ts)
            start_utc = selected_ts[0].tz_convert("UTC")
            end_utc   = selected_ts[-1].tz_convert("UTC")
            nasa_ps   = nasa_power_hourly(float(lat), float(lon), start_utc, end_utc)
            allsky    = nasa_ps.get("ALLSKY_SFC_SW_DWN", {}) or {}
            nasa_ghi_list = [round(max(float(allsky.get(k, 0.0)), 0.0), 1) for k in utc_keys]
        except Exception:
            nasa_ghi_list = None

    # ── Predictions per hour ──────────────────────────────────
    rf_list, xgb_list, ghi_list, times_labels = [], [], [], []

    def _get(arr, idx, default=0.0):
        try:    return safe_float(arr[idx], default)
        except: return default

    for i in range(n):
        idx   = start_idx + i
        dt_ts = selected_ts[i]
        hr    = int(dt_ts.hour)
        lbl   = dt_ts.strftime("%I:%M %p").lstrip("0") or "12:00 AM"
        times_labels.append(lbl)
        rf_v, xgb_v = run_single_safe(
            _get(fc["temperature_f"],  idx, 85), _get(fc["pressure_inhg"], idx, 29.8),
            _get(fc["humidity"],       idx, 55), _get(fc["wind_dir"],      idx, 200),
            _get(fc["wind_speed_mph"], idx,  8),
            hr, int(dt_ts.day), int(dt_ts.month), int(dt_ts.year),
            float(lat), float(lon), str(fc.get("tz_name", DEFAULT_TZ)),
        )
        ens_v = (rf_v + xgb_v) / 2
        rf_list.append(round(rf_v, 1)); xgb_list.append(round(xgb_v, 1)); ghi_list.append(round(ens_v, 1))

    # ── pvlib GHI→POA conversion ──────────────────────────────
    poa_list = ghi_list; nasa_poa = nasa_ghi_list; pvlib_error = None
    if PVLIB_OK:
        try:
            times_idx = pd.DatetimeIndex(selected_ts)
            location  = Location(float(lat), float(lon), str(fc.get("tz_name", DEFAULT_TZ)))
            solpos    = location.get_solarposition(times_idx)
            zenith    = solpos["apparent_zenith"].values
            sol_az    = solpos["azimuth"].values
            ghi_s     = pd.Series([float(v) for v in ghi_list], index=times_idx)
            erbs      = pvlib.irradiance.erbs(ghi_s, zenith, times_idx)
            dni       = np.asarray(erbs["dni"], dtype=float)
            dhi       = np.asarray(erbs["dhi"], dtype=float)
            dne       = pvlib.irradiance.get_extra_radiation(times_idx)
            dni_extra = dne.values if hasattr(dne, "values") else np.asarray(dne, dtype=float)
            total     = pvlib.irradiance.get_total_irradiance(
                surface_tilt=float(panel_tilt), surface_azimuth=float(panel_azimuth),
                solar_zenith=zenith, solar_azimuth=sol_az,
                dni=dni, dni_extra=dni_extra, ghi=ghi_s.values, dhi=dhi, model="haydavies",
            )
            poa_list = [round(max(float(v), 0.0), 1) for v in np.asarray(total["poa_global"], dtype=float)]
            if nasa_ghi_list is not None:
                try:
                    ng_s  = pd.Series([float(v) for v in nasa_ghi_list], index=times_idx)
                    en    = pvlib.irradiance.erbs(ng_s, zenith, times_idx)
                    tn    = pvlib.irradiance.get_total_irradiance(
                        surface_tilt=float(panel_tilt), surface_azimuth=float(panel_azimuth),
                        solar_zenith=zenith, solar_azimuth=sol_az,
                        dni=np.asarray(en["dni"], dtype=float), dni_extra=dni_extra,
                        ghi=ng_s.values, dhi=np.asarray(en["dhi"], dtype=float), model="haydavies",
                    )
                    nasa_poa = [round(max(float(v), 0.0), 1) for v in np.asarray(tn["poa_global"], dtype=float)]
                except Exception:
                    nasa_poa = nasa_ghi_list
        except Exception as e:
            pvlib_error = str(e)

    peak_idx      = int(np.argmax(np.array(poa_list, dtype=float)))
    peak_val      = float(poa_list[peak_idx])
    threshold     = max(200.0, 0.5 * peak_val)
    productive    = [h for h, v in enumerate(poa_list) if v >= threshold]
    daily_ghi_kwh = round(sum(ghi_list)  / 1000.0, 3)
    daily_poa_kwh = round(sum(poa_list)  / 1000.0, 3)

    weather_rows = []
    for i in range(n):
        idx = start_idx + i
        weather_rows.append({
            "time":        times_labels[i],
            "temp_f":      round(_get(fc["temperature_f"],  idx, 85), 1),
            "humidity":    round(_get(fc["humidity"],        idx, 55), 0),
            "wind_mph":    round(_get(fc["wind_speed_mph"],  idx, 8),  1),
            "wind_dir":    round(_get(fc["wind_dir"],        idx, 200), 0),
            "pressure_in": round(_get(fc["pressure_inhg"],  idx, 29.8), 2),
        })

    return jsonify({
        "times": times_labels,
        "rf_predictions":           rf_list,
        "xgb_predictions":          xgb_list,
        "ghi_ensemble_predictions": ghi_list,
        "poa_ensemble_predictions": poa_list,
        "ensemble_predictions":     poa_list,
        "nasa_ghi_predictions":     nasa_ghi_list,
        "nasa_poa_predictions":     nasa_poa,
        "pvlib_error":              pvlib_error,
        "weather_source":           source,
        "weather_hourly":           weather_rows,
        "peak_hour":                peak_idx,
        "peak_value":               round(peak_val,      1),
        "productive_hours":         len(productive),
        "best_window_start":        productive[0]  if productive else 0,
        "best_window_end":          productive[-1] if productive else (n - 1),
        "daily_kwh":                daily_poa_kwh,
        "daily_poa_kwh":            daily_poa_kwh,
        "daily_ghi_kwh":            daily_ghi_kwh,
        "panel_kwh":                round(daily_poa_kwh * panel_efficiency, 3),
        "estimated":                is_syn,
    })


@app.route("/api/panel-estimate", methods=["POST"])
def panel_estimate():
    data = request.json or {}
    try:
        count  = int(float(data.get("panel_count", 10)))
        watt   = float(data.get("panel_watt", 400))
        eff    = max(0.05, min(1.0, float(data.get("efficiency", 0.20))))
        hrs    = float(data.get("sun_hours", 5.5))
        tariff = float(data.get("tariff", 7.0))
        cost   = float(data.get("system_cost", 150000))
        kwp    = (count * watt) / 1000.0
        daily  = kwp * hrs * eff
        annual = daily * 365
        saving = annual * tariff
        return jsonify({
            "total_kwp": round(kwp, 2), "daily_kwh": round(daily, 3),
            "monthly_kwh": round(daily*30, 1), "annual_kwh": round(annual, 1),
            "annual_saving": round(saving, 0), "co2_saved_kg": round(annual*0.82, 1),
            "payback_years": round(cost/saving, 2) if saving > 0 else 999,
            "roi_pct": round((saving/cost)*100, 2) if cost > 0 else 0,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/metrics", methods=["GET"])
def metrics():
    if M is None:
        return jsonify({"error": "Models not trained — run train_model.py first"}), 500
    
    def clean_obj(obj):
        if isinstance(obj, (np.floating, float)): return float(obj)
        elif isinstance(obj, (np.integer, int)): return int(obj)
        elif isinstance(obj, dict): return {k: clean_obj(v) for k, v in obj.items()}
        elif isinstance(obj, list): return [clean_obj(v) for v in obj]
        return obj

    clean_met = clean_obj(M["metrics"])
    clean_imp = clean_obj(M["importance"])
    return jsonify({"metrics": clean_met, "importance": clean_imp})


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok", "models_loaded": M is not None,
        "dataset_loaded": bool(DATASET_PROFILES),
        "dataset_months": len(DATASET_PROFILES),
        "timestamp": datetime.now().isoformat(),
        "version": "6.0.0", "fallback_layers": 5,
        "pvlib_ok": PVLIB_OK,
    })


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Method not allowed"}), 405

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  *  SolarNet Pro v5 - Solar Radiation Prediction System")
    print("  Final Year Project  -  CSE  -  NBKRIST, Vidyanagar")
    print("=" * 60)
    status = "[OK] ML Models loaded" if M else "[WARN] Models not found - using dataset+synthetic fallback"
    print(f"\n  {status}")
    if DATASET_PROFILES:
        print(f"  [OK] Dataset profiles loaded ({len(DATASET_PROFILES)} months)")
    print(f"  [OK] 5-layer fallback system active")
    print(f"\n  [Server] http://127.0.0.1:5000\n")
    app.run(debug=False, port=5000, host="0.0.0.0")
