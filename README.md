# ThrottleGuard Dashboard

This project provides a Streamlit-based web dashboard for ThrottleGuard, a DPF failure prediction system for diesel trucks.

## Features

- Upload CSV files containing truck CAN bus and DPF sensor data
- Run XGBoost model to predict days until DPF cleaning is required
- Risk categorization (CRITICAL/HIGH/MEDIUM/LOW)
- Cleaning schedule sorted by priority
- Charts showing DPF health trends

## Setup

1. Create a Python virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Place your trained XGBoost model in the project directory (e.g., `model.xgb`).
4. Run the app:
   ```bash
   streamlit run app.py
   ```

## Usage

Upload CSV data via the web interface and view predictions and trends.
