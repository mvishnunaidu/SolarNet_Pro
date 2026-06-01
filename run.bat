@echo off
title SolarNet Pro - Solar Radiation Prediction

echo ========================================================
echo   SolarNet Pro   Final Year Project   NBKRIST CSE
echo ========================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install from https://python.org
    pause
    exit /b 1
)

:: Install dependencies
echo Step 1/3  Installing dependencies...
pip install -r requirements.txt -q --only-binary=:all:
if errorlevel 1 (
    echo WARNING: Some packages may not have installed correctly.
)

:: Train models if not present
if not exist "models\random_forest.pkl" (
    echo.
    echo Step 2/3  Training models (first-time setup, may take a few minutes)...
    python train_model.py
    if errorlevel 1 (
        echo ERROR: Model training failed. Check Solar_Prediction.csv exists.
        pause
        exit /b 1
    )
) else (
    echo Step 2/3  Models already trained. Skipping.
)

:: Launch app
echo.
echo Step 3/3  Starting Flask server...
echo.
echo   Open browser at:  http://localhost:5000
echo.
start "" "http://localhost:5000"
python app.py

pause
