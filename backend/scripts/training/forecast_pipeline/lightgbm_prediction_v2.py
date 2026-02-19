# Full incremental forecasting code using MultiOutputRegressor with LightGBM

import numpy as np
import pandas as pd
import gc
import warnings
from datetime import datetime
from sklearn.preprocessing import StandardScaler
from sklearn.multioutput import MultiOutputRegressor
import lightgbm as lgb
from lightgbm import early_stopping

from helper import \
    mysql_cluster_connection, \
    mysql_data_connection, \
    load_configuration, \
    machine_info, \
    data_info, \
    duration_calculation, \
    load_dataset, \
    time_bucketing, \
    data_preparation, \
    predict_target, \
    create_features, \
    predict_features_in_parallel, \
    optuna_study, \
    wape_lightgbm, \
    mman_lightgbm, \
    reevaluate_features


# Memory management function
def clear_memory():
    gc.collect()


key_column = "unique_id"
suffix = "|"
action = "prediction"

cluster_conn, cluster_cursor, cluster_engine = mysql_cluster_connection()
data_conn, data_cursor, data_engine = mysql_data_connection()
os_name, machine_name = machine_info()

config_df = load_configuration("clustering", cluster_cursor, machine_name)
dataset = config_df['dataset'][0]

config_df = load_configuration(action, cluster_cursor, machine_name)
config_row = config_df.iloc[0]
forecast_metric = str(config_row['forecast_metric'])

# Load dataset and related config
df, numeric_columns, categorical_columns, static_categorical_columns, dynamic_categorical_columns, \
unknown_covariates, unknown_covariates_expected_values, known_covariates, known_covariates_expected_values = \
    load_dataset(config_df, key_column, data_info(os_name, dataset)[0])

time_bucket = str(config_row['time_bucket'])
date_column = str(config_row['date_column'])
target_column = str(config_row['target_column'])
number_of_periods_to_forecast = int(config_row['number_of_periods_to_forecast'])
number_of_items_analyzed = int(config_row['number_of_items_analyzed'])

# Setup max_date for forecasting
if 'D' in time_bucket:
    max_date = pd.to_datetime(df[date_column].max()) - pd.DateOffset(days=number_of_periods_to_forecast)
elif "W" in time_bucket:
    max_date = pd.to_datetime(df[date_column].max()) - pd.DateOffset(weeks=number_of_periods_to_forecast)
elif "M" in time_bucket:
    max_date = pd.to_datetime(df[date_column].max()) - pd.DateOffset(months=number_of_periods_to_forecast)

# Feature preparation and time bucketing
df = time_bucketing(
    df, key_column, date_column, target_column, time_bucket,
    numeric_columns, categorical_columns, static_categorical_columns, dynamic_categorical_columns
)
df, period, trend, seasonal_periods, min_cluster_size, max_date, _ = data_preparation(
    df, key_column, date_column, target_column, numeric_columns, categorical_columns, time_bucket,
    number_of_items_analyzed, number_of_periods_to_forecast, 5, 'items'
)

# Create initial features
df, dynamic_features = create_features(
    df, time_bucket, key_column, target_column, date_column,
    numeric_columns, static_categorical_columns, dynamic_categorical_columns
)

# Incremental multi-output forecasting
prediction_dates = df[df[date_column] > max_date][date_column].unique()
output_columns = [target_column] + [cov for cov, exp in zip(unknown_covariates, unknown_covariates_expected_values) if exp == 'predict']

for prediction_date in prediction_dates:
    print(f"Multi-output incremental forecasting for {prediction_date}")

    train_df = df[df[date_column] < prediction_date]
    test_df = df[df[date_column] == prediction_date]

    X_train = train_df[dynamic_features]
    y_train = train_df[output_columns]
    X_test = test_df[dynamic_features]

    feature_scaler = StandardScaler()
    X_train_scaled = feature_scaler.fit_transform(X_train)
    X_test_scaled = feature_scaler.transform(X_test)

    base_lgbm = lgb.LGBMRegressor(n_estimators=500)
    multioutput_model = MultiOutputRegressor(base_lgbm)
    multioutput_model.fit(X_train_scaled, y_train)

    y_pred_multi = multioutput_model.predict(X_test_scaled)
    predictions = pd.DataFrame(y_pred_multi, columns=output_columns)
    predictions[key_column] = test_df[key_column].values
    predictions[date_column] = test_df[date_column].values

    for output in output_columns:
        df.loc[df[date_column] == prediction_date, output] = predictions[output].clip(lower=0).values

    df, _ = create_features(
        df, time_bucket, key_column, target_column, date_column,
        numeric_columns, static_categorical_columns, dynamic_categorical_columns
    )

# End of full incremental multi-output forecasting code
