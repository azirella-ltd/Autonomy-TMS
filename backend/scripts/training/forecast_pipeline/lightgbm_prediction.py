# Optimize imports by removing unused ones and grouping them
import numpy as np
import pandas as pd
import gc
import warnings
from datetime import datetime
import platform
import psutil
import os

from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split

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

# Suppress all warnings
warnings.filterwarnings("ignore")

# Initialize global variables
key_column = "unique_id"
suffix = "|"
action = "prediction"
seasonal_type = "additive"
trend_type = "additive"
    
started = datetime.now()
initial_time = started
step_count = 0

# Initialize database connections and configuration
cluster_conn, cluster_cursor, cluster_engine = mysql_cluster_connection()
data_conn, data_cursor, data_engine = mysql_data_connection()
os_name, machine_name = machine_info()

# Load configurations
config_df = load_configuration("clustering", cluster_cursor, machine_name)
dataset = config_df['dataset'][0]
feature_prediction_method = config_df['feature_prediction_method'][0]
predict_target_feature = config_df['predict_target_feature'][0]

config_df = load_configuration(action, cluster_cursor, machine_name)
config_row = config_df.iloc[0]
forecast_metric = str(config_row['forecast_metric'])

# Get data info
data_folder, njobs, chunk_size = data_info(os_name, dataset)

# SQL query optimization
SQL = """
    SELECT r1.run_id 
    FROM run_details r1 
    WHERE r1.run_id LIKE '%|clustering|%' 
      AND dataset = %s 
      AND NOT EXISTS (
        SELECT 1 
        FROM run_details r2 
        WHERE r2.run_id LIKE CONCAT('%%|', %s, '|', %s, '|%%')
          AND SUBSTRING_INDEX(r1.run_id, '|', 1) = SUBSTRING_INDEX(r2.run_id, '|', 1)
      )
"""

run_id_df = pd.read_sql(SQL, cluster_engine, params=(dataset, action, forecast_metric))
run_id_list = run_id_df['run_id'].tolist()

for cluster_run_id in run_id_list:
    # Load your dataset
    print(cluster_run_id)
    SQL = f"SELECT * FROM run_details where run_id = '{cluster_run_id}'"
    config_df = pd.read_sql(SQL, cluster_engine)    
    config_row = config_df.iloc[0]
    #print(config_row)

    dataset = str(config_row['dataset'])
    demand_item = str(config_row['demand_item'])
    demand_point = str(config_row['demand_point'])
    target_column = str(config_row['target_column'])
    date_column = str(config_row['date_column'])
    time_bucket = str(config_row['time_bucket'])
    number_of_periods_to_forecast = int(config_row['number_of_periods_to_forecast'])
    number_of_items_analyzed = int(config_row['number_of_items_analyzed'])
    min_cluster_size = str(config_row['min_cluster_size'])
    min_cluster_size_uom = str(config_row['min_cluster_size_uom'])

    metric_df = load_configuration(action, cluster_cursor, machine_name)
    metric_row = metric_df.iloc[0]
    forecast_metric = str(metric_row['forecast_metric'])
    run_id = [datetime.now().strftime("%Y%m%d_%H%M"), 
        action,
        forecast_metric, 
        dataset, 
        demand_item, 
        demand_point, 
        target_column, 
        time_bucket]
    run_id = "|".join(run_id)
    run_id = run_id[:80] if len(run_id) > 80 else run_id
    config_df['run_id'] = run_id

    config_df['feature_prediction_method'] = feature_prediction_method

    print(config_df.head(1))
    config_df.to_sql('run_details', con=cluster_engine, if_exists='append', index=False, chunksize=50000)

    started, step_count = duration_calculation("Initialization", run_id, machine_name, action, step_count, started, cluster_engine)


    df, numeric_columns, categorical_columns, static_categorical_columns, dynamic_categorical_columns, \
        unknown_covariates, unknown_covariates_expected_values, known_covariates, known_covariates_expected_values = \
            load_dataset(config_df, key_column, data_folder)

    
    # Define max_date for train/test split
    if 'D' in time_bucket:
        max_date = pd.to_datetime(df[date_column].max()) - pd.DateOffset(days=number_of_periods_to_forecast)
    elif "W" in time_bucket:
        max_date = pd.to_datetime(df[date_column].max()) - pd.DateOffset(weeks=number_of_periods_to_forecast)
    elif "M" in time_bucket:
        max_date = pd.to_datetime(df[date_column].max()) - pd.DateOffset(months=number_of_periods_to_forecast)

    # Create predicted_test_df and set the expected values for the categorical columns
    train_df = df[df[date_column] <= max_date].copy() 
    test_df = df[df[date_column] > max_date].copy() 

    # Predict the known covariates for all of the test period
    icol = 0
    known_covariates_df = pd.DataFrame()
    unknown_covariates_df = pd.DataFrame()
    for known_covariate in known_covariates:
        if known_covariates_expected_values[icol] == 'last':
            known_covariates_df[known_covariate] = train_df[known_covariate].iloc[-1]

        else:
            known_covariates_df[known_covariate] = known_covariates_expected_values[icol]

        icol += 1

    # Predict the unknown covariates with known expected values for all of the test period
    icol = 0
    for unknown_covariate in unknown_covariates:
        if unknown_covariates_expected_values[icol] != 'predict':
            unknown_covariates_df[unknown_covariate] = unknown_covariates_expected_values[icol]

        icol += 1

    predicted_df = pd.concat([known_covariates_df, unknown_covariates_df], ignore_index=True)
    predicted_df = pd.concat([train_df, predicted_df], ignore_index=True)
   
    #Encode the categorical columns
    mapping_dict = {}
    label_encoder = LabelEncoder()
    for col in categorical_columns:
        label_encoder.fit(df[col])
        df[col + '_encoded'] = label_encoder.transform(df[col])
        predicted_df[col + '_encoded'] = label_encoder.transform(predicted_df[col])
        
        mapping_dict[col] = pd.DataFrame({
            'unique_id': df['unique_id'],
            'original_category': df[col],
            'encoded_value': df[col + '_encoded']
        }).drop_duplicates()

    # Modify the original DataFrame
    for col in categorical_columns:
        df[col] = df[col + '_encoded']
        df = df.drop(columns=[col + '_encoded'])

    # Modify the original DataFrame
    for col in categorical_columns:
        predicted_df[col] = predicted_df[col + '_encoded']
        predicted_df = predicted_df.drop(columns=[col + '_encoded'])

    started, step_count = duration_calculation("Load Data", run_id, machine_name, action, step_count, started, cluster_engine)

    df = time_bucketing(df, key_column, date_column, target_column, time_bucket, \
                    numeric_columns, categorical_columns, static_categorical_columns, dynamic_categorical_columns)
    started, step_count = duration_calculation("Time Bucketing", run_id, machine_name, action, step_count, started, cluster_engine)

    df, period, trend, seasonal_periods, min_cluster_size, max_date, minimum_observations_threshold = \
        data_preparation(df, key_column, date_column, target_column, numeric_columns, categorical_columns, \
                        time_bucket, number_of_items_analyzed, number_of_periods_to_forecast, \
                        min_cluster_size, min_cluster_size_uom)


    df['cluster'] = -1
    sorted_columns = [key_column, 'cluster'] + categorical_columns + [date_column, target_column] + numeric_columns
    df = df[sorted_columns]
    df = df.sort_values(by=[key_column,date_column])
    
    predicted_df['cluster'] = -1
    predicted_df = predicted_df[sorted_columns]
    predicted_df = predicted_df.sort_values(by=[key_column,date_column])
    #print(df)

    table_name = "clusters"
    SQL = f"SELECT * FROM {table_name} WHERE run_id = '{cluster_run_id}'"
    clusters_df = pd.read_sql(SQL, cluster_engine, chunksize=chunk_size)
    clusters_df = pd.concat(clusters_df, ignore_index=True)
    clusters_df.drop(columns=['run_id', 'demand_item', 'demand_point'], inplace=True)
    #print(clusters_df)
    #print(df)
    df = pd.merge(df, clusters_df[[key_column, 'cluster']], on=key_column, how='left', suffixes=('', '_new'))
    df['cluster'] = df['cluster_new']
    #print(df)
    df.drop(columns=['cluster_new'], inplace=True)
    #print(df)
    df = df.dropna(subset=['cluster'])

    predicted_df = pd.merge(predicted_df, clusters_df[[key_column, 'cluster']], on=key_column, how='left', suffixes=('', '_new'))
    predicted_df['cluster'] = predicted_df['cluster_new']
    #print(df)
    predicted_df.drop(columns=['cluster_new'], inplace=True)
    #print(df)
    predicted_df = predicted_df.dropna(subset=['cluster'])

    feature_columns = (
        [target_column]
        + dynamic_categorical_columns
        + numeric_columns
    )

    started, step_count = duration_calculation("Data Preparation", run_id, machine_name, action, step_count, started, cluster_engine)  


    ###################################################################
    #
    # This code has been modified to be able to handle known and unknown covariates
    # The known covariates will be handled as per this code
    # For example, OTIF should be set to 1, inventory quality to "good", etc
    #
    # The unknown covariates will have to be handles with an expected values function that returns a TS for the test period
    # If there are features generated for the unknown covariates these need tobe either forecast or reevaluated for the test period
    #
    # Other unknown covariates such as CPI will have to be absorbed from elsewhere
    #
    # First attempt has been implemented below
    #
    ####################################################################


    df, dynamic_features = create_features(df, time_bucket, key_column, target_column, date_column, numeric_columns, static_categorical_columns, dynamic_categorical_columns)

    started, step_count = duration_calculation("Feature Creation", run_id, machine_name, action, step_count, started, cluster_engine)

    predicted_test_df = predicted_df[predicted_df[date_column] > max_date].copy() 
    df = pd.concat([train_df, predicted_test_df], ignore_index=True)

    # Predict unknown covariate in the test period
    icol = 0
    features_to_reevalulate = []
    features_to_predict = []
    for unknown_covariate in unknown_covariates:
        if unknown_covariates_expected_values[icol] == "predict":
            features_to_predict = features_to_predict + [unknown_covariate]
            # Predict features and update df with predictions
            if unknown_covariate in dynamic_features:
                covariate_suffix = unknown_covariate + suffix
                features_to_reevalulate = [features_to_predict] + [col for col in df.columns if covariate_suffix in col]
            
            #df = predict_features_in_parallel(
            #    df, features_to_predict, date_column, key_column, max_date, feature_prediction_method,
            #    seasonal_type=seasonal_type, seasonal_periods=seasonal_periods, trend_type=trend_type, optuna_metric=forecast_metric
            #)
    

 

    # Predict target features for all of the test period
    # This is the alternative to incremental prediction with feature reevaluation after each step
    #if predict_target_feature == "True":
    #    target_suffix = target_column + suffix
    #    features_to_predict = [col for col in df.columns if target_suffix in col]

    #    # Predict features and update df with predictions
    #    df = predict_features_in_parallel(
    #        df, features_to_predict, date_column, key_column, max_date, feature_prediction_method,
    #        seasonal_type=seasonal_type, seasonal_periods=seasonal_periods, trend_type=trend_type, optuna_metric=forecast_metric
    #    )

    #started, step_count = duration_calculation("Feature Prediction", run_id, machine_name, action, step_count, started, cluster_engine)

    if 'index' in df.columns:
        df.drop(columns=['index'], inplace=True)

    print("df columns after feature creation:\n", df.columns)
    print(df.head(10))

    exclude_columns = [key_column, date_column, target_column]
    exogenous_columns = [col for col in df.columns if col not in exclude_columns]
    df[exogenous_columns] = df[exogenous_columns].fillna(0)

    full_df = df.copy()
    print("full_df columns: ", full_df.columns)
    columns_with_target = [key_column, date_column] + [col for col in df.columns if target_column in col]
    print(full_df[columns_with_target].tail(10))
    print(full_df.tail(10))

    # Ensure date is in datetime format and sorted
    df[date_column] = pd.to_datetime(df[date_column])
    df = df.sort_values(by=['cluster', key_column, date_column])

    prediction_dates = df[df[date_column] > max_date][date_column].unique()

    model = 'lightGBM'
    for feature_type in ['N Clusters']:
        for method in ['FNB', 'SHAP', 'ALL']:
            # Initialize lists for results
            df = full_df.copy()
            predictions_list = []
            metrics_list = []

            if method == 'FNB':
                table_name = "feature_importance_by_cluster"

            elif method == 'SHAP':
                table_name = "SHAP_contribution_by_cluster"

            cluster_ids = df['cluster'].unique()

            for cluster in cluster_ids:
                cluster_df = df[df['cluster'] == cluster].copy()
                print(f"Processing cluster: {cluster}")
            
                if method == 'FNB' or method == 'SHAP':
                    SQL = f"SELECT * FROM {table_name} WHERE run_id = '{cluster_run_id}' AND cluster ='{cluster}'"
                    features_df = pd.read_sql(SQL, cluster_engine, chunksize=chunk_size)
                    features_df = pd.concat(features_df, ignore_index=True)
                    features_df.drop(columns=['run_id'], inplace=True)
                    feature_columns = features_df['feature'].tolist()
                    all_columns = [key_column, 'cluster', date_column, target_column] + feature_columns
                    cluster_df = cluster_df[all_columns]
                else:
                    exclude_columns = [key_column, 'cluster', date_column, target_column] 
                    feature_columns = [col for col in df.columns if col not in exclude_columns]

                features_to_reevaluate = [col for col in cluster_df.columns if suffix in col]
                print("feature_columns:\n", feature_columns)
                print("features_to_predict:\n", features_to_predict)
                print("features_to_reevaluate:\n", features_to_reevaluate)

                all_predictions = pd.DataFrame()

                for prediction_date in prediction_dates:
                    train_df = cluster_df[cluster_df[date_column] < prediction_date]
                    test_df = cluster_df[cluster_df[date_column] >= prediction_date]

                    if prediction_date > min(prediction_dates):
                        train_df.set_index([key_column, date_column], inplace=True)
                        current_predictions.set_index([key_column, date_column], inplace=True)
                        train_df[target_column].update(current_predictions['prediction'])
                        train_df.reset_index(inplace=True)

                        train_df = reevaluate_features(full_df, train_df, features_to_reevaluate, key_column, date_column, suffix, time_bucket)

                    # Check if train_df or test_df is empty
                    if train_df.empty or test_df.empty:
                        print(f"Skipping cluster {cluster} due to insufficient data.")
                        continue

                    # Features and target
                    X_train = train_df[feature_columns]
                    #y_train = train_df[target_column]
                    y_train = train_df[features_to_predict]
                    X_test = test_df[feature_columns]
                    #y_test = test_df[target_column]
                    y_test = test_df[features_to_predict]

                    # Check for NaNs
                    if X_train.isnull().any().any():
                        print("Warning: Missing values found in X_train.")

                    # Normalize features if X_train is valid
                    if X_train.shape[0] > 0:  # Check if not empty
                        feature_scaler = StandardScaler()
                        X_train_scaled = feature_scaler.fit_transform(X_train)
                        X_test_scaled = feature_scaler.transform(X_test)
                    else:
                        print("Error: X_train is empty.")
                        continue

                    # Get the best parameters from optuna
                    best_params = optuna_study(X_train_scaled, y_train, X_test_scaled, y_test, forecast_metric)

                    # Train the final model with the best parameters
                    lgb_train = lgb.Dataset(X_train_scaled, label=y_train)
                    print(X_test_scaled)
                    lgb_eval = lgb.Dataset(X_test_scaled, label=y_test, reference=lgb_train)
                    print(lgb_eval)

                    if forecast_metric == 'WAPE':
                        gbm = lgb.train(
                            best_params,
                            lgb_train,
                            num_boost_round=1000,
                            valid_sets=[lgb_eval],
                            feval=wape_lightgbm,
                            callbacks=[early_stopping(stopping_rounds=10)]
                        )
                    elif forecast_metric == 'MMAN':
                        gbm = lgb.train(
                            best_params,
                            lgb_train,
                            num_boost_round=1000,
                            valid_sets=[lgb_eval],
                            feval=mman_lightgbm,
                            callbacks=[early_stopping(stopping_rounds=10)]
                        )
                    else:
                        gbm = lgb.train(
                            best_params,
                            lgb_train,
                            num_boost_round=1000,
                            valid_sets=[lgb_eval],
                            callbacks=[early_stopping(stopping_rounds=10)]
                        )

                    first_step_df = test_df[test_df[date_column] == prediction_date].copy()
                    X_test = first_step_df[feature_columns]
                    X_test_scaled = feature_scaler.transform(X_test)
                    y_pred = gbm.predict(X_test_scaled, num_iteration=gbm.best_iteration)
                    #y_pred = y_pred.round(0).clip(min=0)

                    current_predictions = test_df[test_df[date_column] == prediction_date][[key_column, date_column]].copy()
                    current_predictions.reset_index(inplace=True)
                    current_predictions.drop(columns=['index'], inplace=True)
                    current_predictions['prediction'] = y_pred #.round(0).clip(min=0)
                    if all_predictions.empty:
                        all_predictions = current_predictions.copy()
                    else:
                        all_predictions = pd.concat([all_predictions, current_predictions], ignore_index=True)

                                            
                # Collect predictions
                all_predictions['prediction'] = all_predictions['prediction'].round(0).clip(lower=0)
                test_df = cluster_df[cluster_df[date_column] > max_date]
                forecast = test_df[[key_column, 'cluster', date_column, target_column]].copy()
                forecast.columns = [key_column, 'cluster', date_column, 'actual']
                forecast = forecast.merge(
                    all_predictions[[key_column, date_column, 'prediction']],
                    on=[key_column, date_column],
                    how='left'
                )
                forecast['model'] = model
                forecast['feature_type'] = feature_type
                forecast['method'] = method
                print("forecast: ", forecast.columns)
                print(forecast[date_column].unique())
                print(forecast)
                predictions_list.append(forecast)

            # Save predictions
            final_predictions = pd.concat(predictions_list, ignore_index=True)
            final_predictions['run_id'] = run_id
            final_predictions = final_predictions[['run_id', 'model', 'feature_type', 'method', 'cluster', key_column, date_column, 'actual', 'prediction']]
            final_predictions.columns = ['run_id', 'model', 'feature_type', 'method', 'cluster', 'unique_id', 'date_column', 'actual', 'prediction']
            print("final_predictions: ", final_predictions.columns)
            print(final_predictions['date_column'].unique())
            print(final_predictions)
            final_predictions.to_sql('predictions', con=cluster_engine, if_exists='append', index=False, chunksize=chunk_size)
            #result = to_databricks(data_to_insert=final_predictions, table_name='predictions', mode='append') 
            started, step_count = duration_calculation(f"{model} with {feature_type} using {method} features",\
                                                            run_id, machine_name, action, step_count, started, cluster_engine)


    for feature_type in ['1 Cluster']:
        for method in ['FNB', 'SHAP', 'ALL']:
            # Initialize lists for results
            df = full_df.copy()
            predictions_list = []
            metrics_list = []

            if method == 'FNB':
                table_name = "feature_importance_overall"

            elif method == 'SHAP':
                table_name = "SHAP_contribution_overall"

            cluster_df = df
            if method == 'FNB' or method == 'SHAP':
                SQL = f"SELECT * FROM {table_name} WHERE run_id = '{cluster_run_id}'"
                features_df = pd.read_sql(SQL, cluster_engine, chunksize=chunk_size)
                features_df = pd.concat(features_df, ignore_index=True)
                features_df.drop(columns=['run_id'], inplace=True)
                feature_columns = features_df['feature'].tolist()
                all_columns = [key_column, 'cluster', date_column, target_column] + feature_columns
                cluster_df = cluster_df[all_columns]
            else:
                exclude_columns = [key_column, 'cluster', date_column, target_column] 
                feature_columns = [col for col in df.columns if col not in exclude_columns]
                
            all_predictions = pd.DataFrame()

            for prediction_date in prediction_dates:
                train_df = cluster_df[cluster_df[date_column] < prediction_date]
                test_df = cluster_df[cluster_df[date_column] >= prediction_date]

                if prediction_date > min(prediction_dates):
                    train_df.set_index([key_column, date_column], inplace=True)
                    current_predictions.set_index([key_column, date_column], inplace=True)
                    train_df[target_column].update(current_predictions['prediction'])
                    train_df.reset_index(inplace=True)

                    train_df = reevaluate_features(full_df, train_df, features_to_reevaluate, key_column, date_column, suffix, time_bucket)

                # Check if train_df or test_df is empty
                if train_df.empty or test_df.empty:
                    print(f"Skipping cluster {cluster} due to insufficient data.")
                    continue

                # Features and target
                X_train = train_df[feature_columns]
                y_train = train_df[target_column]
                X_test = test_df[feature_columns]
                y_test = test_df[target_column]

                # Check for NaNs
                if X_train.isnull().any().any():
                    print("Warning: Missing values found in X_train.")

                # Normalize features if X_train is valid
                if X_train.shape[0] > 0:  # Check if not empty
                    feature_scaler = StandardScaler()
                    X_train_scaled = feature_scaler.fit_transform(X_train)
                    X_test_scaled = feature_scaler.transform(X_test)
                else:
                    print("Error: X_train is empty.")
                    continue

                # Get the best parameters from optuna
                best_params = optuna_study(X_train_scaled, y_train, X_test_scaled, y_test, forecast_metric)
                #print("best_params:\n", best_params)
                #best_params['objective'] = 'regression'
                #best_params['metric'] = 'wape' #'poisson'
                #best_params['boosting_type'] = 'gbdt'
                #best_params['verbose'] = 1

                # Train the final model with the best parameters
                lgb_train = lgb.Dataset(X_train_scaled, label=y_train)
                lgb_eval = lgb.Dataset(X_test_scaled, label=y_test, reference=lgb_train)

                if forecast_metric == 'WAPE':
                    gbm = lgb.train(
                        best_params,
                        lgb_train,
                        num_boost_round=1000,
                        valid_sets=[lgb_eval],
                        feval=wape_lightgbm,
                        callbacks=[early_stopping(stopping_rounds=10)]
                    )
                elif forecast_metric == 'MMAN':
                    gbm = lgb.train(
                        best_params,
                        lgb_train,
                        num_boost_round=1000,
                        valid_sets=[lgb_eval],
                        feval=mman_lightgbm,
                        callbacks=[early_stopping(stopping_rounds=10)]
                    )
                else:
                    gbm = lgb.train(
                        best_params,
                        lgb_train,
                        num_boost_round=1000,
                        valid_sets=[lgb_eval],
                        callbacks=[early_stopping(stopping_rounds=10)]
                    )
                gbm = lgb.train(
                    best_params,
                    lgb_train,
                    num_boost_round=1000,
                    valid_sets=[lgb_eval],
                    callbacks=[early_stopping(stopping_rounds=10)]
                )

                first_step_df = test_df[test_df[date_column] == prediction_date].copy()
                X_test = first_step_df[feature_columns]
                X_test_scaled = feature_scaler.transform(X_test)
                y_pred = gbm.predict(X_test_scaled, num_iteration=gbm.best_iteration)
                #y_pred = y_pred.round(0).clip(min=0)

                current_predictions = test_df[test_df[date_column] == prediction_date][[key_column, date_column]].copy()
                current_predictions.reset_index(inplace=True)
                current_predictions.drop(columns=['index'], inplace=True)
                current_predictions['prediction'] = y_pred #.round(0).clip(min=0)
                if all_predictions.empty:
                    all_predictions = current_predictions.copy()
                else:
                    all_predictions = pd.concat([all_predictions, current_predictions], ignore_index=True)


            # Collect predictions
            all_predictions['prediction'] = all_predictions['prediction'].round(0).clip(lower=0)
            test_df = cluster_df[cluster_df[date_column] > max_date]
            forecast = test_df[[key_column, 'cluster', date_column, target_column]].copy()
            forecast.columns = [key_column, 'cluster', date_column, 'actual']
            forecast = forecast.merge(
                all_predictions[[key_column, date_column, 'prediction']],
                on=[key_column, date_column],
                how='left'
            )
            forecast['model'] = model
            forecast['feature_type'] = feature_type
            forecast['method'] = method
            #predictions_list.append(forecast)

            # Save predictions
            final_predictions = forecast
            final_predictions['run_id'] = run_id
            final_predictions = final_predictions[['run_id', 'model', 'feature_type', 'method', 'cluster', key_column, date_column, 'actual', 'prediction']]
            final_predictions.columns = ['run_id', 'model', 'feature_type', 'method', 'cluster', 'unique_id', 'date_column', 'actual', 'prediction']
            final_predictions.to_sql('predictions', con=cluster_engine, if_exists='append', index=False, chunksize=chunk_size)
            #result = to_databricks(data_to_insert=final_predictions, table_name='predictions', mode='append') 

            started, step_count = duration_calculation(f"{model} forecast with {feature_type} using {method} features", \
                                                        run_id, machine_name, action, step_count, started, cluster_engine)

    # Holt-Winter's forecast

    forecast = full_df[[key_column, 'cluster', date_column, target_column]].copy()
    forecast.columns = [key_column, 'cluster', date_column, 'actual']
    forecast['prediction'] = forecast['actual']
    forecast = predict_target(forecast, 'prediction', date_column, key_column, max_date, seasonal_type, seasonal_periods, trend_type)
    forecast = forecast[forecast[date_column] > max_date]
    print(forecast)
    forecast['model'] = 'Holt-Winters'
    forecast['feature_type'] = 'None'
    forecast['method'] = 'None'

    # Save forecast        
    forecast['run_id'] = run_id
    forecast = forecast[['run_id', 'model', 'feature_type', 'method', 'cluster', key_column, date_column, 'actual', 'prediction']]
    forecast.columns = ['run_id', 'model', 'feature_type', 'method', 'cluster', 'unique_id', 'date_column', 'actual', 'prediction']
    forecast.to_sql('predictions', con=cluster_engine, if_exists='append', index=False)
    #result = to_databricks(data_to_insert=final_predictions, table_name='predictions', mode='append') 

    started, step_count = duration_calculation("Holt-Winter's forecast by item", run_id, machine_name, action, step_count, started, cluster_engine)

    
started = initial_time
started, step_count = duration_calculation("Overall Prediction", run_id, machine_name, action, step_count, started, cluster_engine)