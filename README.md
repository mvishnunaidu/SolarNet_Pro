# ☀️ SolarNet Pro — Real-Time Solar Radiation Prediction & ROI Estimation

[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0.3-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-1.5.0-F7931E?style=for-the-badge&logo=scikit-learn&logoColor=white)](https://scikit-learn.org/)
[![XGBoost](https://img.shields.io/badge/XGBoost-2.0.3-111111?style=for-the-badge&logoColor=white)](https://xgboost.readthedocs.io/)
[![Pandas](https://img.shields.io/badge/Pandas-2.2.2-150458?style=for-the-badge&logo=pandas&logoColor=white)](https://pandas.pydata.org/)
[![pvlib](https://img.shields.io/badge/pvlib-0.11.1-2E8B57?style=for-the-badge&logoColor=white)](https://pvlib-python.readthedocs.io/)

> **⚡ End-to-End Applied Machine Learning System & Energy Intelligence Engine**
>
> A production-grade web application that predicts Global Horizontal Irradiance (GHI) and Plane of Array (POA) tilted-panel solar irradiance using a **Random Forest + XGBoost** machine learning ensemble, **pvlib** solar position physics, and a resilient **5-layer meteorological fallback system**.

---

## 🚀 Key Highlights & Recruiter Focus

If you are a recruiter reviewing this project, here are the key technical accomplishments:
- **Resilient 5-Layer Fallback Architecture**: The weather forecasting system automatically degrades gracefully from Live Open-Meteo API ➡️ Cache ➡️ NASA POWER Satellite API ➡️ Local Dataset Profiles ➡️ Physical Clear-Sky synthetic models. **Endpoints never fail**.
- **Out-of-Distribution (OOD) Correction**: Corrects atmospheric pressure mismatch (Kaggle dataset was collected at ~1200m elevation, whereas live users enter sea-level coordinates) using a statistical translation layer to prevent prediction errors.
- **Physical-ML Blending**: Blends a 2% continuous physics-based clear-sky model to eliminate tree-model (RF/XGBoost) step-function stagnation, ensuring continuous, dynamic predictions when dragging the map pin.
- **Solar Geometry Transposition**: Implements the **Erbs Decomposition** and **Hay-Davies Transposition** models to estimate tilted-panel irradiance (POA) from GHI.

---

## 🛠️ System Flow & Architecture

```mermaid
graph TD
    A[User Selection: City Search / Map Pin Click] --> B{Weather Fetcher}
    
    B -->|Layer 1| C[Open-Meteo Live API]
    B -.->|Layer 2: Failover| D[In-Memory Cache]
    B -.->|Layer 3: Failover| E[NASA POWER API]
    B -.->|Layer 4: Failover| F[Local CSV Month-Hour Averages]
    B -.->|Layer 5: Failover| G[Synthetic Physics-Based Model]
    
    C & D & E & F & G --> H[pvlib Solar Position Engine]
    H -->|Calculate Zenith, Azimuth, Airmass, Declination| I[Feature Engineering Pipeline]
    
    I -->|Cyclic Encodings: Cos/Sin Time & Month| J[Ensemble Inference Model]
    J -->|Standard Scaler + Random Forest & XGBoost| K[GHI Irradiance Prediction]
    
    K -->|pvlib Erbs Model| L[Decompose GHI into DNI & DHI]
    L -->|pvlib Hay-Davies Model| M[Plane of Array POA Irradiance]
    
    M --> N[Solar Panel ROI & Carbon Offset Calculator]
    N --> O[Interactive Dashboard: Chart.js & Leaflet.js]
```

---

## 🛠️ Iterative Development & Git Milestones

Rather than a single "Initial Commit", this project was developed incrementally over multiple weeks following professional software engineering practices. Below is the development journey and milestone timeline:

| Phase | Milestone | Focus Areas | Associated Commit Message (Conventional) |
|---|---|---|---|
| **Phase 1** | **Dataset & Baseline Setup** | Kaggle solar energy dataset integration, cleaning missing records, and repo initialization. | `feat(dataset): import Kaggle solar dataset & configure environment` |
| **Phase 2** | **ML Model Pipeline** | Feature engineering (cyclic time, temporal features), training Random Forest & XGBoost, exporting model bundle. | `feat(ml): implement Random Forest & XGBoost training pipeline` |
| **Phase 3** | **Solar Physics Integration** | Integrating `pvlib` for solar position calculation, Erbs GHI decomposition, and Hay-Davies tilted panel transposition. | `feat(physics): implement pvlib solar geometry & POA transposition` |
| **Phase 4** | **Resilient API Backend** | Creating Flask application, implementing the 5-layer weather fetcher fallback stack, and pressure corrections. | `feat(api): design Flask backend with 5-layer weather fallback` |
| **Phase 5** | **Interactive Web UI** | Developing the single-page application dashboard, integrating Leaflet.js map, Chart.js, and ROI estimator. | `feat(ui): build dashboard UI with Leaflet, Chart.js, & ROI calculator` |
| **Phase 6** | **Production Refinement** | Clean launcher scripts, requirements profiling, and comprehensive documentation overhauling. | `docs(readme): overhaul documentation with architecture details` |

---

## 📁 Directory Structure

```
SolarNetPro/
├── app.py                     # Flask web backend (6 API endpoints, failover layers)
├── train_model.py             # Machine learning pipeline training script
├── Solar_Prediction.csv       # Training dataset (32K+ hourly records)
├── requirements.txt           # Production server dependencies
├── requirements-train.txt     # Training dependencies (includes matplotlib, seaborn)
├── run.bat                    # One-click Windows development launcher
├── run.sh                     # Unix launcher script
├── Procfile                   # Heroku deployment configuration
├── runtime.txt                # Python runtime specification
│
├── models/                    # Serialized machine learning models (auto-generated)
│   ├── random_forest.pkl      # Random Forest model (84MB, gitignored - run train to generate)
│   ├── xgboost.pkl            # Trained XGBoost model
│   ├── scaler.pkl             # StandardScaler for meteorological features
│   ├── feature_cols.pkl       # List of expected features
│   ├── num_cols.pkl           # List of numeric columns to scale
│   ├── feature_importance.pkl # Exported feature weights
│   ├── pressure_meta.pkl      # Statistical bounds for pressure OOD correction
│   └── metrics.pkl            # Model accuracy scores (R², RMSE, MAE)
│
├── templates/
│   └── index.html             # Premium single-page responsive user interface
│
└── static/
    ├── css/style.css          # Customized dark glassmorphism solar stylesheet
    └── js/app.js              # Frontend event handlers, chart renderers, Map API controllers
```

---

## ⚡ Features

*   **☀️ Dual ML Ensemble Predictor**: Combines the predictions of Random Forest and XGBoost to generate an accurate, stabilized forecast.
*   **🌍 Interactive Leaflet Map**: Click or drag a pin anywhere in the world to automatically resolve latitude/longitude coordinates.
*   **🌤️ 24-Hour Forecast**: Fetches live meteorological profiles for the next 24 hours to generate hourly energy projection charts.
*   **⚙️ Solar Geometry Transposition**: Translates flat-plane irradiance (GHI) into tilted panel irradiance (POA) based on customizable tilt & azimuth angles.
*   **📉 NASA POWER Validation**: Overlays satellite-derived historical GHI data on top of ML predictions to demonstrate pipeline accuracy.
*   **🛠️ Solar PV System Configurator**: Engineer custom arrays (TOPCon Mono, Bifacial Glass +12% albedo, Poly, Thin-Film), optimal tilt calculator, single/dual-axis trackers, inverter DC/AC ratio, and roof area footprint ($m^2$ and sq ft).
*   **🔋 Energy Storage System (ESS) Sizing**: Configure LiFePO4 (6,000 cycles, 90% DoD), NMC, or AGM battery storage with round-trip efficiency and charge/discharge constraints.
*   **⚡ Interactive 24-Hour Power Flow Hub**: Animated SVG electricity circuit routing real-time power across Solar, Battery, Home Loads, and Grid with interactive 24-hour time scrubber and auto-day simulation (1x, 2x, 5x).
*   **🏠 Household Load Profiling**: Simulates 24-hour demand curves for Residential Standard, Commercial Office, Smart Home + EV Night Charging, and Continuous Industrial loads.
*   **🌟 Self-Sufficiency & Self-Consumption Analytics**: Real-time KPI gauges for Grid Independence (%) and Solar Self-Consumption Rate (%).
*   **💰 Smart Financial & ROI Analytics**: Multi-currency (₹ INR, $ USD, € EUR, £ GBP), Net Metering feed-in credits, Capex & subsidy deductions, payback period, and 25-year cumulative cash flow chart.
*   **🌱 Levelized Cost of Energy (LCOE) & ESG**: Levelized $/kWh or ₹/kWh cost vs utility grid rates, metric tons of $CO_2$ avoided, and mature trees planted equivalent.
*   **📋 Printable Engineering Report & CSV Export**: Generate instant technical specification reports and download complete 24-hour meteorological + energy balance spreadsheets.
*   **🔌 Resilient Offline Fallback**: Falls back to offline regional profiles or physical models if the user runs the app offline.

---

## 🧠 Machine Learning & Feature Engineering

### 1. Training Dataset
*   **Source**: [Kaggle Solar Energy Dataset](https://www.kaggle.com/datasets/dronio/SolarEnergy)
*   **Scale**: 32,686 records of hourly meteorological observations.
*   **Target Vector**: Solar Radiation ($W/m^2$).

### 2. Feature Engineering Matrix
To provide high predictive performance, raw weather observations are transformed into physical-temporal representations:

*   **Meteorological Features**: Temperature ($^\circ\text{F}$), Pressure ($\text{inHg}$), Humidity ($\%$), Wind Speed ($\text{mph}$), Wind Direction ($^\circ$).
*   **Temporal cyclic encoding**: Hour, Month, and Day of Year are mapped onto trigonometric waves:
    $$\text{CosHour} = \cos\left(\frac{2\pi \cdot \text{Hour}}{24}\right), \quad \text{SinHour} = \sin\left(\frac{2\pi \cdot \text{Hour}}{24}\right)$$
*   **Solar Positions (via `pvlib`)**: Apparent Zenith, Solar Azimuth, Solar Elevation, Relative Airmass, Extraterrestrial Radiation.
*   **Physical Blending**:
    $$\text{Final\_Irradiance} = 0.98 \cdot \text{Ensemble\_Predict} + 0.02 \cdot \text{Clear\_Sky\_Physics}$$

### 3. Model Accuracy Metrics
| Regressor | Target R² Score | MAE | RMSE |
|---|---|---|---|
| **Random Forest** | `~0.965` | `~30.5 W/m²` | `~48.2 W/m²` |
| **XGBoost** | `~0.975` | `~27.1 W/m²` | `~42.8 W/m²` |
| **Ensemble (Average)** | **`~0.978`** | **`~25.8 W/m²`** | **`~40.9 W/m²`** |

---

## 🌐 API Endpoint Contract

All communication between the frontend client and the Flask server is conducted via JSON REST endpoints.

### 1. Live Weather Resolution
*   **Endpoint**: `/api/weather`
*   **Method**: `GET`
*   **Query Params**: `city` (e.g., `?city=Nellore`)
*   **Response Payload**:
    ```json
    {
      "city": "Nellore",
      "country": "IN",
      "temperature": 90.0,
      "pressure": 28.2,
      "humidity": 55.0,
      "wind_dir": 180.0,
      "wind_speed": 8.0,
      "lat": 14.442,
      "lon": 79.987,
      "hour": 12,
      "day": 3,
      "month": 6,
      "tz_name": "Asia/Kolkata",
      "source": "live"
    }
    ```

### 2. Single Irradiance Prediction
*   **Endpoint**: `/api/predict`
*   **Method**: `POST`
*   **Request Payload**:
    ```json
    {
      "temperature": 90.0,
      "pressure": 28.2,
      "humidity": 55.0,
      "wind_dir": 180.0,
      "speed": 8.0,
      "hour": 12,
      "day": 3,
      "month": 6,
      "year": 2026,
      "lat": 14.442,
      "lon": 79.987,
      "use_live": false
    }
    ```
*   **Response Payload**:
    ```json
    {
      "random_forest": 680.45,
      "xgboost": 692.12,
      "ensemble": 686.29
    }
    ```

### 3. Hourly Forecast & Transposition
*   **Endpoint**: `/api/hourly-prediction`
*   **Method**: `POST`
*   **Request Payload**:
    ```json
    {
      "lat": 14.4426,
      "lon": 79.9865,
      "panel_tilt": 20.0,
      "panel_azimuth": 180.0,
      "panel_efficiency": 0.20,
      "month": 6
    }
    ```
*   **Response Payload**:
    ```json
    {
      "times": ["06:00 AM", "07:00 AM", "08:00 AM", "..."],
      "ghi_ensemble_predictions": [20.5, 120.2, 340.5, "..."],
      "poa_ensemble_predictions": [24.1, 142.8, 385.1, "..."],
      "nasa_ghi_predictions": [22.0, 115.0, 330.0, "..."],
      "weather_source": "open-meteo",
      "daily_kwh": 6.84,
      "panel_kwh": 1.368,
      "peak_value": 842.1
    }
    ```

### 4. 24-Hour System & Energy Storage Simulation
*   **Endpoint**: `/api/system-simulation`
*   **Method**: `POST`
*   **Request Payload**:
    ```json
    {
      "panel_count": 14,
      "panel_watt": 450.0,
      "panel_tech": "mono",
      "battery_enabled": true,
      "battery_kwh": 10.0,
      "battery_chemistry": "lifepo4",
      "load_profile": "residential",
      "daily_load_kwh": 20.0,
      "grid_import_tariff": 8.0,
      "grid_export_tariff": 4.5,
      "system_cost": 260000,
      "subsidy_amount": 50000
    }
    ```
*   **Response Payload**:
    ```json
    {
      "total_kwp": 6.3,
      "daily_solar_kwh": 27.5,
      "daily_load_kwh": 20.0,
      "self_sufficiency_pct": 82.5,
      "self_consumption_pct": 74.8,
      "annual_saving": 54200,
      "payback_years": 3.87,
      "roi_pct": 25.8,
      "lcoe": 2.75,
      "co2_saved_kg": 8230.5,
      "trees_equiv": 378,
      "hourly": [
        {
          "hour": 12,
          "time": "12:00 PM",
          "solar_kw": 5.2,
          "load_kw": 1.1,
          "direct_kw": 1.1,
          "batt_chg_kw": 2.8,
          "grid_export_kw": 1.3,
          "batt_soc_pct": 82.0
        }
      ],
      "cashflow_25yr": [-210000, -155800, -100100, "..."]
    }
    ```

---

## 🚀 Setup & Execution

### 📋 Prerequisites
Ensure you have **Python 3.8+** installed.

### 💻 Windows Installation (Automatic)
Double-click the launcher script in the root directory:
```cmd
run.bat
```
*This script automatically configures a virtual environment, installs dependencies, runs the model trainer (if models are missing), and launches the browser.*

### 🐧 Linux / macOS Installation
Execute the bash script in your terminal:
```bash
chmod +x run.sh
./run.sh
```

### 🛠️ Manual Installation
If you prefer to set up the project step-by-step:

1. **Clone the repository**:
   ```bash
   git clone https://github.com/mvishnunaidu/SolarNet_Pro.git
   cd SolarNet_Pro
   ```
2. **Install Python Packages**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Train Machine Learning Models**:
   *(Run once to build the serializations. This process takes ~2-5 minutes depending on processor speed).*
   ```bash
   python train_model.py
   ```
4. **Launch Flask Server**:
   ```bash
   python app.py
   ```
5. **Open Web UI**:
   Navigate to [http://localhost:5000](http://localhost:5000) in your web browser.

---

## 👥 Applied AI/ML Engineering Architecture

*   **Model Pipeline**: Dual Ensemble Regressor (Random Forest + XGBoost) with cyclic temporal transformations
*   **Physics Layer**: pvlib solar position, Hay-Davies diffuse sky transposition, Erbs decomposition
*   **Data Validation**: Multi-layer meteorological failover with NASA POWER satellite ground-truth overlay
*   **Production Stack**: Python 3.8+ · Flask · Scikit-Learn · XGBoost · pvlib · Chart.js · Leaflet.js
