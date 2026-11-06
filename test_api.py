"""
test_api.py ─ Automated Integration and Unit Test Suite for SolarNet Pro
========================================================================
Run with:
    python test_api.py
or:
    pytest test_api.py
"""

import unittest
import json
from app import app, validate_inputs, synthetic_ghi, synthetic_weather

class SolarNetProTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()

    def test_01_index_route(self):
        """Test GET / renders dashboard HTML with status 200."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'SolarNet', response.data)
        self.assertIn(b'chart.js', response.data)

    def test_02_health_endpoint(self):
        """Test GET /api/health returns system status and loaded models."""
        response = self.client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertTrue(data.get('models_loaded'))
        self.assertTrue(data.get('dataset_loaded'))
        self.assertEqual(data.get('fallback_layers'), 5)

    def test_03_cors_headers(self):
        """Test that CORS headers are returned on preflight and GET requests."""
        response = self.client.options('/api/predict')
        self.assertIn(response.status_code, (200, 204))
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), '*')
        self.assertIn('GET, POST, OPTIONS', response.headers.get('Access-Control-Allow-Methods', ''))

    def test_04_input_validation(self):
        """Test that input validation strictly clamps extreme out-of-bound inputs."""
        extreme_payload = {
            'temperature': 999.0,   # Exceeds max 140
            'pressure': 10.0,       # Below min 20
            'humidity': 150.0,      # Exceeds max 100
            'hour': 35,             # Exceeds max 23
            'month': 15,            # Exceeds max 12
            'lat': -100.0,          # Below min -90
        }
        validated = validate_inputs(extreme_payload)
        self.assertEqual(validated['temperature'], 140.0)
        self.assertEqual(validated['pressure'], 20.0)
        self.assertEqual(validated['humidity'], 100.0)
        self.assertEqual(validated['hour'], 23)
        self.assertEqual(validated['month'], 12)
        self.assertEqual(validated['lat'], -90.0)

    def test_05_predict_endpoint(self):
        """Test POST /api/predict returns RF, XGBoost, and ensemble predictions."""
        payload = {
            'temperature': 88, 'pressure': 29.8, 'humidity': 55,
            'wind_dir': 200, 'speed': 8, 'hour': 12, 'day': 15,
            'month': 6, 'year': 2026, 'lat': 14.4426, 'lon': 79.9865,
            'tz_name': 'Asia/Kolkata', 'use_live': False
        }
        response = self.client.post('/api/predict', json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('random_forest', data)
        self.assertIn('xgboost', data)
        self.assertIn('ensemble', data)
        self.assertGreater(data['ensemble'], 0.0)

    def test_06_metrics_endpoint(self):
        """Test GET /api/metrics returns MAE, RMSE, R2 scores and feature importances."""
        response = self.client.get('/api/metrics')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('metrics', data)
        self.assertIn('importance', data)
        self.assertIn('random_forest', data['metrics'])
        self.assertIn('xgboost', data['metrics'])
        self.assertIn('rf', data['importance'])
        self.assertIn('xgb', data['importance'])
        # Verify R² score > 0.90
        self.assertGreater(data['metrics']['xgboost']['r2'], 0.90)

    def test_07_hourly_prediction_endpoint(self):
        """Test POST /api/hourly-prediction returns 24-hr profile and POA calculation."""
        payload = {
            'lat': 14.4426, 'lon': 79.9865,
            'panel_tilt': 20.0, 'panel_azimuth': 180.0, 'panel_efficiency': 0.20,
            'month': 6
        }
        response = self.client.post('/api/hourly-prediction', json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data.get('times', [])), 24)
        self.assertEqual(len(data.get('poa_ensemble_predictions', [])), 24)
        self.assertIn('weather_source', data)
        self.assertIn('daily_kwh', data)

    def test_08_panel_estimate_endpoint(self):
        """Test POST /api/panel-estimate calculates financial ROI and carbon offsets."""
        payload = {
            'panel_count': 10, 'panel_watt': 400, 'efficiency': 0.20,
            'sun_hours': 5.5, 'tariff': 7.0, 'system_cost': 150000
        }
        response = self.client.post('/api/panel-estimate', json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data.get('total_kwp'), 4.0)
        self.assertGreater(data.get('annual_saving'), 0)
        self.assertGreater(data.get('co2_saved_kg'), 0)
        self.assertGreater(data.get('roi_pct'), 0)

    def test_09_offline_city_fallback(self):
        """Test GET /api/weather fallback to offline database for known Indian city."""
        response = self.client.get('/api/weather?city=Hyderabad')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data.get('city'), 'Hyderabad')
        self.assertIn(data.get('source'), ('live', 'offline-db'))

    def test_10_unknown_city_synthetic_fallback(self):
        """Test GET /api/weather fallback to clear-sky physics for unknown city."""
        response = self.client.get('/api/weather?city=NonExistentCity999')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data.get('source'), 'synthetic')
        self.assertTrue(data.get('estimated'))

    def test_11_physics_clear_sky_model(self):
        """Test that synthetic clear-sky model produces 0 GHI at night and positive during midday."""
        # Midday at equator in June
        noon_ghi = synthetic_ghi(lat=0.0, month=6, hour=12)
        self.assertGreater(noon_ghi, 500.0)
        # Midnight
        midnight_ghi = synthetic_ghi(lat=0.0, month=6, hour=0)
        self.assertEqual(midnight_ghi, 0.0)

    def test_12_system_simulation_endpoint(self):
        """Test POST /api/system-simulation returns 24-hr PV, Battery ESS, and Load Flow metrics."""
        payload = {
            'panel_count': 14, 'panel_watt': 450, 'efficiency': 0.21,
            'battery_enabled': True, 'battery_kwh': 10.0, 'load_profile': 'residential',
            'daily_load_kwh': 20.0, 'grid_import_tariff': 8.0, 'grid_export_tariff': 4.5,
            'system_cost': 260000, 'subsidy_amount': 50000
        }
        response = self.client.post('/api/system-simulation', json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data.get('total_kwp'), 6.3)
        self.assertEqual(len(data.get('hourly', [])), 24)
        self.assertIn('self_sufficiency_pct', data)
        self.assertIn('self_consumption_pct', data)
        self.assertIn('cashflow_25yr', data)
        self.assertEqual(len(data['cashflow_25yr']), 26) # Year 0 to 25
        self.assertGreater(data.get('daily_solar_kwh', 0), 0)
        self.assertGreater(data.get('annual_saving', 0), 0)

if __name__ == '__main__':
    unittest.main(verbosity=2)
