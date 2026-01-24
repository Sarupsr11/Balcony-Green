#!/bin/bash

# Setup script for Balcony Green

echo "🌱 Setting up Balcony Green Environment..."

# 1. Switch to correct branch
echo "Checking branch..."
git checkout model-making

# 2. Create virtual environment (optional but recommended)
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# 3. Activate venv
source venv/bin/activate

# 4. Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
# Install explicitly as pyproject.toml might be missing some
pip install streamlit pydantic click fastapi requests pandas numpy scikit-learn matplotlib scipy torch torchvision timm pillow

echo "✅ Setup Complete!"
echo "To run the app:"
echo "  source venv/bin/activate"
echo "  streamlit run src/balconygreen/app.py"
