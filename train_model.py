"""
train_model.py  ─  SolarNet Pro | Fixed Model Trainer
======================================================
Run this ONCE before starting the Flask app.

Trains: Random Forest + XGBoost on Solar_Prediction.csv
Saves:  all models + scaler to /models/  (same format as before)

BUG FIXES applied vs original:
  FIX 1 — Added cyclic time features: CosHour/SinHour (corr=-0.88 with Radiation),
           CosMonth/SinMonth, CosDOY/SinDOY — these were completely missing and
           are the strongest predictors in the dataset.
  FIX 2 — Added CosZenith and TempDryHeat interaction feature.
  FIX 3 — Saved pressure_meta.pkl so app.py can correct the sea-level pressure
           mismatch at inference time (training data is at ~1200m ASL = 28.15 inHg;
           city inference sends ~29.7 inHg = 12.9 standard deviations out of range).
  FIX 4 — XGBoost tuned: 600 estimators, lr=0.04 (was 300, lr=0.08).
  FIX 5 — Cross-validation added and printed (does not change saved format).
  NOTE  — metrics.pkl and feature_importance.pkl saved in EXACT same format
           as the original so the frontend UI continues to work unchanged.

Usage:
    python train_model.py
"""

import pandas as pd
import numpy as np
import joblib
import os
import pvlib
from pvlib.location import Location
from sklearn.model_selection import train_test_split, KFold, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

# ── Dataset config ─────────────────────────────────────────────
CSV_PATH = "Solar_Prediction.csv"

# The Kaggle SolarEnergy dataset originates from a station near
# Mauna Loa, Hawaii (~19.5 N, 155.6 W, ~1200m ASL).
REF_LAT = 19.5
REF_LON = -155.6
REF_TZ  = "Pacific/Honolulu"

if not os.path.exists(CSV_PATH):
    print("=" * 62)
    print("ERROR: Solar_Prediction.csv not found!")
    print("Place it in the same folder as this script.")
    print("=" * 62)
    exit(1)

# ── 1. Load ────────────────────────────────────────────────────
print("\n*  SolarNet Pro — Model Training (Fixed)")
print("=" * 62)
print("\nStep 1/9  Loading dataset...")
df = pd.read_csv(CSV_PATH)
df.columns = df.columns.str.strip()
print(f"  Shape: {df.shape}")
print(f"  Columns: {list(df.columns)}")

# ── 2. Parse datetime ──────────────────────────────────────────
print("\nStep 2/9  Parsing datetime columns...")
if "Data" in df.columns:
    df.rename(columns={"Data": "Date"}, inplace=True)

df["Time"]     = df["Time"].fillna("00:00:00")
df["Datetime"] = pd.to_datetime(
    df["Date"].astype(str) + " " + df["Time"].astype(str), errors="coerce"
)
df["Year"]      = df["Datetime"].dt.year
df["Month"]     = df["Datetime"].dt.month
df["Day"]       = df["Datetime"].dt.day
df["Hour"]      = df["Datetime"].dt.hour
df["DayOfYear"] = df["Datetime"].dt.dayofyear
print(f"  Date range: {df['Datetime'].min()} -> {df['Datetime'].max()}")

# ── 3. Solar geometry features (pvlib) ────────────────────────
print("\nStep 3/9  Computing pvlib solar geometry features...")
times_index = pd.DatetimeIndex(df["Datetime"])
if times_index.tz is None:
    times_index = times_index.tz_localize(REF_TZ)

location = Location(latitude=REF_LAT, longitude=REF_LON, tz=REF_TZ)
solpos   = location.get_solarposition(times_index)

df["SolarZenith"]    = solpos["apparent_zenith"].values
df["SolarAzimuth"]   = solpos["azimuth"].values
df["SolarElevation"] = solpos["apparent_elevation"].values
df["SolarAirMassRel"] = pvlib.atmosphere.get_relative_airmass(
    df["SolarZenith"].values
)
df["SolarAirMassRel"] = df["SolarAirMassRel"].replace([np.inf, -np.inf], np.nan)
df["ExtraRadiation"]  = pvlib.irradiance.get_extra_radiation(times_index).values
print("  Solar geometry features added.")

# ── 4. NEW: Cyclic + interaction features ─────────────────────
print("\nStep 4/9  Adding cyclic and interaction features (FIX)...")
df["CosHour"]     = np.cos(2 * np.pi * df["Hour"]      / 24)
df["SinHour"]     = np.sin(2 * np.pi * df["Hour"]      / 24)
df["CosMonth"]    = np.cos(2 * np.pi * df["Month"]     / 12)
df["SinMonth"]    = np.sin(2 * np.pi * df["Month"]     / 12)
df["CosDOY"]      = np.cos(2 * np.pi * df["DayOfYear"] / 365)
df["SinDOY"]      = np.sin(2 * np.pi * df["DayOfYear"] / 365)
df["CosZenith"]   = np.cos(np.radians(df["SolarZenith"])).clip(0, 1)
df["TempDryHeat"] = df["Temperature"] * (100.0 - df["Humidity"])
print("  Added: CosHour(corr=-0.88), SinHour, CosMonth, SinMonth,")
print("         CosDOY, SinDOY, CosZenith, TempDryHeat")

# ── 5. Drop unneeded columns ───────────────────────────────────
print("\nStep 5/9  Cleaning columns...")
drop_cols = [c for c in ["UNIXTime","Date","Time","TimeSunRise","TimeSunSet","Datetime"]
             if c in df.columns]
df.drop(columns=drop_cols, inplace=True)
print(f"  Dropped: {drop_cols}")

# ── 6. Handle missing values ───────────────────────────────────
print("\nStep 6/9  Handling missing values...")
before = df.isnull().sum().sum()
df.fillna(df.median(numeric_only=True), inplace=True)
print(f"  Filled {before} missing values with column medians")

# ── 7. Features / Target ───────────────────────────────────────
print("\nStep 7/9  Splitting features & target...")
TARGET       = "Radiation"
X            = df.drop(columns=[TARGET])
y            = df[TARGET]
FEATURE_COLS = list(X.columns)
print(f"  Features ({len(FEATURE_COLS)}): {FEATURE_COLS}")
print(f"  Target: {TARGET}  (range: {y.min():.1f} - {y.max():.1f} W/m2)")

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)
print(f"\n  Train: {len(X_train)}  Test: {len(X_test)}")

# ── 8. Scale numeric features ──────────────────────────────────
print("\nStep 8/9  Scaling numeric features...")
NUM_COLS = [
    "Temperature","Pressure","Humidity","WindDirection(Degrees)","Speed",
    "Hour","Day","DayOfYear","Month","Year",
    "SolarZenith","SolarAzimuth","SolarElevation","SolarAirMassRel","ExtraRadiation",
    "CosHour","SinHour","CosMonth","SinMonth","CosDOY","SinDOY",
    "CosZenith","TempDryHeat",
]
NUM_COLS = [c for c in NUM_COLS if c in X_train.columns]

# FIX 3: Save pressure stats for inference correction in app.py
PRESSURE_TRAIN_MEAN = float(X_train["Pressure"].mean())
PRESSURE_TRAIN_STD  = float(X_train["Pressure"].std())
print(f"  Pressure mean={PRESSURE_TRAIN_MEAN:.4f} inHg  std={PRESSURE_TRAIN_STD:.4f}")
print(f"  Sea-level (29.7 inHg) is {(29.7-PRESSURE_TRAIN_MEAN)/PRESSURE_TRAIN_STD:.1f} sigma out — app.py corrects this")

scaler = StandardScaler()
X_train[NUM_COLS] = scaler.fit_transform(X_train[NUM_COLS])
X_test[NUM_COLS]  = scaler.transform(X_test[NUM_COLS])
print(f"  Scaled {len(NUM_COLS)} columns with StandardScaler")

# ── 9. Train models ────────────────────────────────────────────
print("\nStep 9/9  Training models...")
print("  Training Random Forest...")
rf = RandomForestRegressor(
    n_estimators=200, max_depth=None,
    max_features="sqrt", min_samples_split=4,
    min_samples_leaf=2, random_state=42, n_jobs=-1
)
rf.fit(X_train, y_train)
rf_pred = rf.predict(X_test)
rf_mae  = mean_absolute_error(y_test, rf_pred)
rf_rmse = np.sqrt(mean_squared_error(y_test, rf_pred))
rf_r2   = r2_score(y_test, rf_pred)
print(f"  [OK] RF  -> MAE: {rf_mae:.3f}   RMSE: {rf_rmse:.3f}   R2: {rf_r2:.4f}")

print("\n  Training XGBoost...")
xgb = XGBRegressor(
    n_estimators=600, learning_rate=0.04, max_depth=7,
    subsample=0.8, colsample_bytree=0.8,
    min_child_weight=5, gamma=0.05,
    random_state=42, eval_metric="rmse", verbosity=0,
    tree_method="hist",
)
xgb.fit(X_train, y_train)
xgb_pred = xgb.predict(X_test)
xgb_mae  = mean_absolute_error(y_test, xgb_pred)
xgb_rmse = np.sqrt(mean_squared_error(y_test, xgb_pred))
xgb_r2   = r2_score(y_test, xgb_pred)
print(f"  [OK] XGB -> MAE: {xgb_mae:.3f}   RMSE: {xgb_rmse:.3f}   R2: {xgb_r2:.4f}")

ens_pred = (rf_pred + xgb_pred) / 2
ens_r2   = r2_score(y_test, ens_pred)
ens_rmse = np.sqrt(mean_squared_error(y_test, ens_pred))
print(f"  [OK] ENS -> R2: {ens_r2:.4f}   RMSE: {ens_rmse:.3f}")

# 5-fold CV (printed for reference only)
print("\n  5-fold cross-validation on XGBoost...")
kf    = KFold(n_splits=5, shuffle=True, random_state=42)
cv_r2 = cross_val_score(xgb, X_train, y_train, cv=kf, scoring="r2", n_jobs=-1)
print(f"  CV R2: {cv_r2.mean():.4f} +/- {cv_r2.std():.4f}")

# ── Feature importance ─────────────────────────────────────────
rf_importances  = dict(zip(FEATURE_COLS, rf.feature_importances_.tolist()))
xgb_importances = dict(zip(FEATURE_COLS, xgb.feature_importances_.tolist()))
# SAME format as original so the UI works
importances = {"rf": rf_importances, "xgb": xgb_importances}
top5 = sorted(rf_importances.items(), key=lambda x: x[1], reverse=True)[:5]
print(f"\n  Top features (RF): {[f[0] for f in top5]}")

# ── Save everything ────────────────────────────────────────────
print("\nSaving models...")
os.makedirs("models", exist_ok=True)

joblib.dump(rf,           "models/random_forest.pkl")
joblib.dump(xgb,          "models/xgboost.pkl")
joblib.dump(scaler,       "models/scaler.pkl")
joblib.dump(FEATURE_COLS, "models/feature_cols.pkl")
joblib.dump(NUM_COLS,     "models/num_cols.pkl")
joblib.dump(importances,  "models/feature_importance.pkl")

# Pressure correction metadata for app.py (new file, does not affect UI)
joblib.dump({
    "pressure_train_mean": PRESSURE_TRAIN_MEAN,
    "pressure_train_std":  PRESSURE_TRAIN_STD,
}, "models/pressure_meta.pkl")

# EXACT same metrics format as original — UI reads these keys
metrics = {
    "random_forest": {"mae": round(rf_mae,3),  "rmse": round(rf_rmse,3),  "r2": round(rf_r2,4)},
    "xgboost":       {"mae": round(xgb_mae,3), "rmse": round(xgb_rmse,3), "r2": round(xgb_r2,4)},
    "ensemble":      {"rmse": round(ens_rmse,3), "r2": round(ens_r2,4)},
}
joblib.dump(metrics, "models/metrics.pkl")

print("\n" + "=" * 62)
print("  [OK] All models saved to /models/")
print(f"     Random Forest  R2: {rf_r2:.4f}")
print(f"     XGBoost        R2: {xgb_r2:.4f}")
print(f"     Ensemble       R2: {ens_r2:.4f}")
print(f"     CV R2 (5-fold): {cv_r2.mean():.4f} +/- {cv_r2.std():.4f}")
print("\n  Now run:  python app.py")
print("=" * 62 + "\n")
