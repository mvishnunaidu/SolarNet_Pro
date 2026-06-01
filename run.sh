#!/bin/bash
echo "========================================================"
echo "  SolarNet Pro — Final Year Project — NBKRIST CSE"
echo "========================================================"
echo ""

# Install dependencies
echo "Step 1/3  Installing dependencies..."
pip install -r requirements.txt -q --only-binary=:all:

# Train models if not present
if [ ! -f "models/random_forest.pkl" ]; then
    echo ""
    echo "Step 2/3  Training models (first-time setup)..."
    python train_model.py
else
    echo "Step 2/3  Models already trained. Skipping."
fi

# Launch
echo ""
echo "Step 3/3  Starting server → http://localhost:5000"
echo ""
python app.py
