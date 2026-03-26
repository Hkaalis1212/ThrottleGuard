"""Example training script for XGBoost model.

This script assumes you have a CSV of historical data with target column `days_until_cleaning`.
Adjust feature selection and preprocessing as needed.
"""

import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error

# load dataset
# df = pd.read_csv("historical_data.csv")
# features = [col for col in df.columns if col != 'days_until_cleaning']

# X = df[features]
# y = df['days_until_cleaning']

# X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# model = xgb.XGBRegressor(objective='reg:squarederror')
# model.fit(X_train, y_train)

# preds = model.predict(X_test)
# mse = mean_squared_error(y_test, preds)
# print(f"Test MSE: {mse}")

# save model
# model.save_model('model.xgb')

print("This script is a template; uncomment and adjust lines to train your model.")