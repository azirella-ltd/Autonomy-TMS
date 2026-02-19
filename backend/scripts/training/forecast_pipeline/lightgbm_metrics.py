import numpy as np
import pandas as pd
from datetime import datetime
import gc
import warnings
import platform
import psutil
import os

from helper import (
    mysql_cluster_connection,
    mysql_data_connection,
    load_configuration,
    machine_info,
    data_info,
    duration_calculation,
    bias_metric,
    wape_metric,
    mma_metric,
    mman_metric
)

# Memory management function
def clear_memory():
    gc.collect()

# Suppress all warnings
warnings.filterwarnings("ignore")

# Initialize global variables
key_column = "unique_id"
baseline = "Holt-Winters"

# Initialize database connections and configuration
cluster_conn, cluster_cursor, cluster_engine = mysql_cluster_connection()
data_conn, data_cursor, data_engine = mysql_data_connection()
os_name, machine_name = machine_info()

# Load configurations
config_df = load_configuration("clustering", cluster_cursor, machine_name)
dataset = config_df['dataset'][0]

# Get data info
data_folder, njobs, chunk_size = data_info(os_name, dataset)

config_row = config_df.iloc[0]
dataset = str(config_row['dataset'])

# SQL query optimization
SQL = """
    SELECT r1.run_id 
    FROM run_details r1 
    WHERE r1.run_id LIKE '%|prediction|%' 
      AND dataset = %s 
      AND NOT EXISTS (
        SELECT 1 
        FROM run_details r2 
        WHERE r2.run_id LIKE '%|metrics|%'
          AND SUBSTRING_INDEX(r1.run_id, '|', 1) = SUBSTRING_INDEX(r2.run_id, '|', 1)
      )
"""

run_id_df = pd.read_sql(SQL, cluster_engine, params=(dataset,))
run_id_list = run_id_df['run_id'].tolist()

for prediction_run_id in run_id_list:
    # Load your dataset
    print(prediction_run_id)
    SQL = f"SELECT * FROM run_details where run_id = '{prediction_run_id}';"
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
    ignore_numeric_columns = bool(config_row['ignore_numeric_columns'])
    feature_correlation_threshold = float(config_row['feature_correlation_threshold'])    
    cv_sq_threshold = float(config_row['cv_sq_threshold'])
    adi_threshold = float(config_row['adi_threshold'])
    minimum_observations_threshold = int(config_row['minimum_observations_threshold'])
    min_clusters = int(config_row['min_clusters'])
    max_clusters = int(config_row['max_clusters'])
    min_cluster_size = int(config_row['min_cluster_size'])
    characteristics_creation_method = str(config_row['characteristics_creation_method'])
    cluster_selection_method = str(config_row['cluster_selection_method'])
    feature_importance_method = str(config_row['feature_importance_method'])
    feature_importance_threshold = float(config_row['feature_importance_threshold'])
    pca_variance_threshold = float(config_row['pca_variance_threshold'])
    pca_importance_threshold = float(config_row['pca_importance_threshold'])

    key_column = "unique_id"

    config_df = pd.DataFrame([config_row])
    #print(config_df.head(1))

    table_name = "predictions"
    SQL = f"SELECT * FROM {table_name} WHERE run_id = '{prediction_run_id}'"
    global_forecast = pd.read_sql(SQL, cluster_engine)

    run_id = prediction_run_id.replace('prediction', 'metrics')
    config_df['run_id'] = run_id
    action =  'metrics'
    config_df.to_sql('run_details', con=cluster_engine, if_exists='append', index=False, chunksize=50000)

    if os_name == 'Linux':
        data_folder = '/home/trevor/Insync/trevor.miles@noodle.ai/OneDrive Biz/Product Design/Demand Data/' + dataset + '/'
        njobs = psutil.cpu_count() - 1
        njobs= min(3, njobs)

    elif os_name == 'Darwin':
        data_folder = 'C:\\Users\\miles\\OneDrive - Noodle Analytics\\Product Design\\Demand Data\\' + dataset + '\\'
        njobs = psutil.cpu_count() - 2  

    elif os_name == 'Windows':
        data_folder = 'C:\\Users\\miles\\OneDrive - Noodle Analytics\\Product Design\\Demand Data\\' + dataset + '\\'
        njobs = 1
    
    started, step_count = duration_calculation("Initialization", run_id, machine_name, action, step_count, started, cluster_engine)

    chunk_size = 20000
    #chunks = []
    categorical_driver_df = pd.DataFrame()
    numeric_driver_df = pd.DataFrame()
    numeric_columns = []
    categorical_columns = []

    chunk_size = 20000

    warnings.filterwarnings("ignore")

    for model in ['lightGBM']:
        for feature_type in ['N Clusters', '1 Cluster']:
            for method in ['FNB','SHAP','ALL']:
                # Calculate metrics for each item
                metrics_list = []
                forecast_df = global_forecast[(global_forecast['model'] == model) & 
                                            (global_forecast['feature_type'] == feature_type) &
                                            (global_forecast['method'] == method)]
                for item_name, item_data in forecast_df.groupby([key_column]):
                    y_true = item_data['actual']
                    y_pred = item_data['prediction']
                    cluster_name = item_data['cluster'].iloc[0]
                    metrics_df = pd.DataFrame({
                        "cluster": [cluster_name],
                        "unique_id": [item_name[0]],
                        "model": [model],
                        "feature_type": [feature_type],
                        "method": [method],
                        "WAPE": [float(wape_metric(y_true, y_pred))],
                        "MMA": [float(mma_metric(y_true, y_pred))],
                        "MMAN": [float(mman_metric(y_true, y_pred))],
                        "MAE": [float(mean_absolute_error(y_true, y_pred))],
                        "MSE": [float(mean_squared_error(y_true, y_pred))],
                        "RMSE": [float(np.sqrt(mean_squared_error(y_true, y_pred)))],
                        "Bias": [float(bias_metric(y_true, y_pred))],
                    })
                    metrics_list.append(metrics_df)

                if len(metrics_list) > 1:
                    item_metrics = pd.concat(metrics_list, ignore_index=True)
                else:
                    item_metrics = metrics_df
                item_metrics['run_id'] = run_id
                item_metrics = item_metrics[['run_id', 'model', 'feature_type', 'method', 'cluster', key_column, 'WAPE', 'MMA', 'MMAN', 'MAE', 'MSE', 'RMSE', 'Bias']]
                item_metrics.to_sql('metrics_by_item', con=cluster_engine, if_exists='append', index=False, chunksize=chunk_size)

                # Calculate metrics for each cluster
                clustered_data = forecast_df.groupby('cluster')
                metrics_list = []
                for cluster_name, cluster_data in clustered_data:
                    y_true = cluster_data['actual']
                    y_pred = cluster_data['prediction']
                    metrics_df = pd.DataFrame({
                        "cluster": [cluster_name],
                        "unique_id": 'overall',
                        "model": [model],
                        "feature_type": [feature_type],
                        "method": [method],
                        "WAPE": [float(wape_metric(y_true, y_pred))],
                        "MMA": [float(mma_metric(y_true, y_pred))],
                        "MMAN": [float(mman_metric(y_true, y_pred))],
                        "MAE": [float(mean_absolute_error(y_true, y_pred))],
                        "MSE": [float(mean_squared_error(y_true, y_pred))],
                        "RMSE": [float(np.sqrt(mean_squared_error(y_true, y_pred)))],
                        "Bias": [float(bias_metric(y_true, y_pred))],
                    })
                    metrics_list.append(metrics_df)

                if len(metrics_list) > 1:
                    cluster_metrics = pd.concat(metrics_list, ignore_index=True)
                else:
                    cluster_metrics = metrics_df
                cluster_metrics['run_id'] = run_id
                cluster_metrics = cluster_metrics[['run_id', 'model', 'feature_type', 'method', 'cluster', key_column, 'WAPE', 'MMA', 'MMAN', 'MAE', 'MSE', 'RMSE', 'Bias']]
                cluster_metrics.to_sql('metrics_by_cluster', con=cluster_engine, if_exists='append', index=False, chunksize=chunk_size)

                # Calculate overall metrics 
                y_true = forecast_df['actual']
                y_pred = forecast_df['prediction']
                metrics_df = pd.DataFrame({
                    "cluster": 'overall',
                    "unique_id": 'overall',
                    "model": [model],
                    "feature_type": [feature_type],
                    "method": [method],
                    "WAPE": [float(wape_metric(y_true, y_pred))],
                    "MMA": [float(mma_metric(y_true, y_pred))],
                    "MMAN": [float(mman_metric(y_true, y_pred))],
                    "MAE": [float(mean_absolute_error(y_true, y_pred))],
                    "MSE": [float(mean_squared_error(y_true, y_pred))],
                    "RMSE": [float(np.sqrt(mean_squared_error(y_true, y_pred)))],
                    "Bias": [float(bias_metric(y_true, y_pred))],
                })

                overall_metrics = metrics_df
                overall_metrics['run_id'] = run_id
                overall_metrics = overall_metrics[['run_id', 'model', 'feature_type', 'method', 'cluster', key_column, 'WAPE', 'MMA', 'MMAN','MAE', 'MSE', 'RMSE', 'Bias']]
                overall_metrics.to_sql('metrics_overall', con=cluster_engine, if_exists='append', index=False, chunksize=chunk_size)

                description = f"{model} for {feature_type} using {method} features"
                started, step_count = duration_calculation(description, run_id, machine_name, action, step_count, started, cluster_engine)

    # Baseline forecast

    for model in [baseline]:
        for feature_type in ['None']:
            for method in ['None']:
                metrics_list = []
                forecast_df = global_forecast[(global_forecast['model'] == model) & 
                                            (global_forecast['feature_type'] == feature_type) &
                                            (global_forecast['method'] == method)]
                for item_name, item_data in forecast_df.groupby([key_column]):
                    y_true = item_data['actual']
                    y_pred = item_data['prediction']
                    cluster_name = item_data['cluster'].iloc[0]
                    metrics_df = pd.DataFrame({
                        "cluster": [cluster_name],
                        "unique_id": [item_name[0]],
                        "model": [model],
                        "feature_type": [feature_type],
                        "method": [method],
                        "WAPE": [float(wape_metric(y_true, y_pred))],
                        "MMA": [float(mma_metric(y_true, y_pred))],
                        "MMAN": [float(mman_metric(y_true, y_pred))],
                        "MAE": [float(mean_absolute_error(y_true, y_pred))],
                        "MSE": [float(mean_squared_error(y_true, y_pred))],
                        "RMSE": [float(np.sqrt(mean_squared_error(y_true, y_pred)))],
                        "Bias": [float(bias_metric(y_true, y_pred))],
                    })
                    metrics_list.append(metrics_df)

                # Save item metrics
                item_metrics = pd.concat(metrics_list, ignore_index=True)
                item_metrics['run_id'] = run_id
                item_metrics = item_metrics[['run_id', 'model', 'feature_type', 'method', 'cluster', key_column, 'WAPE', 'MMA', 'MMAN', 'MAE', 'MSE', 'RMSE', 'Bias']]
                item_metrics.to_sql('metrics_by_item', con=cluster_engine, if_exists='append', index=False, chunksize=chunk_size)

                clustered_data = forecast_df.groupby('cluster')
                metrics_list = []
                for cluster_name, cluster_data in clustered_data:
                    y_true = cluster_data['actual']
                    y_pred = cluster_data['prediction']
                    metrics_df = pd.DataFrame({
                        "cluster": [cluster_name],
                        "unique_id": 'overall',
                        "model": [model],
                        "feature_type": [feature_type],
                        "method": [method],
                        "WAPE": [float(wape_metric(y_true, y_pred))],
                        "MMA": [float(mma_metric(y_true, y_pred))],
                        "MMAN": [float(mman_metric(y_true, y_pred))],
                        "MAE": [float(mean_absolute_error(y_true, y_pred))],
                        "MSE": [float(mean_squared_error(y_true, y_pred))],
                        "RMSE": [float(np.sqrt(mean_squared_error(y_true, y_pred)))],
                        "Bias": [float(bias_metric(y_true, y_pred))],
                    })
                    metrics_list.append(metrics_df)

                cluster_metrics = pd.concat(metrics_list, ignore_index=True)
                cluster_metrics['run_id'] = run_id
                cluster_metrics = cluster_metrics[['run_id', 'model', 'feature_type', 'method', 'cluster', key_column, 'WAPE', 'MMA', 'MMAN', 'MAE', 'MSE', 'RMSE', 'Bias']]
                cluster_metrics.to_sql('metrics_by_cluster', con=cluster_engine, if_exists='append', index=False, chunksize=chunk_size)


                y_true = forecast_df['actual']
                y_pred = forecast_df['prediction']
                metrics_df = pd.DataFrame({
                    "cluster": 'overall',
                    "unique_id": 'overall',
                    "model": [model],
                    "feature_type": [feature_type],
                    "method": [method],
                    "WAPE": [float(wape_metric(y_true, y_pred))],
                    "MMA": [float(mma_metric(y_true, y_pred))],
                    "MMAN": [float(mman_metric(y_true, y_pred))],
                    "MAE": [float(mean_absolute_error(y_true, y_pred))],
                    "MSE": [float(mean_squared_error(y_true, y_pred))],
                    "RMSE": [float(np.sqrt(mean_squared_error(y_true, y_pred)))],
                    "Bias": [float(bias_metric(y_true, y_pred))],
                })

                overall_metrics = metrics_df
                overall_metrics['run_id'] = run_id
                overall_metrics = overall_metrics[['run_id', 'model', 'feature_type', 'method', 'cluster', key_column, 'WAPE', 'MMA', 'MMAN', 'MAE', 'MSE', 'RMSE', 'Bias']]
                overall_metrics.to_sql('metrics_overall', con=cluster_engine, if_exists='append', index=False, chunksize=chunk_size)

                description = f"{model} for {feature_type} using {method} features"
                started, step_count = duration_calculation(description, run_id, machine_name, action, step_count, started, cluster_engine)


    if 'Honeywell' in run_id:
        SQL = f"SELECT * FROM honeywell_class"
        class_df = pd.read_sql(SQL, cluster_engine)
        global_forecast = global_forecast.merge(
            class_df[['unique_id', 'class']], 
            on='unique_id', 
            how='left', 
            suffixes=('', '_new')
        )
        global_forecast['class'] = global_forecast['class_new'].combine_first(global_forecast['class'])
        global_forecast = global_forecast.drop(columns=['class_new'])
        class_list = global_forecast['class'].unique().tolist()

    elif 'DotFoods' in run_id:
        SQL = f"SELECT upc_id, tier \
            FROM `DotFoods - Raw` \
            GROUP BY upc_id, tier"
        class_df = pd.read_sql(SQL, data_engine)
        global_forecast['upc_id'] = global_forecast['unique_id'].str.split('|').str[0]
        global_forecast = global_forecast.merge(
            class_df[['upc_id', 'tier']], 
            on='upc_id', 
            how='left'
        )
        global_forecast['class'] = global_forecast['tier'].combine_first(global_forecast['tier'])
        global_forecast = global_forecast.drop(columns=['upc_id', 'tier'])

    for model in ['lightGBM']:
        for feature_type in ['N Clusters', '1 Cluster']:
            for method in ['FNB','SHAP','ALL']:
                # Calculate metrics for each item
                metrics_list = []
                forecast_df = global_forecast[(global_forecast['model'] == model) & 
                                            (global_forecast['feature_type'] == feature_type) &
                                            (global_forecast['method'] == method)]
                # Calculate metrics for each class
                data_by_class = forecast_df.groupby('class')
                metrics_list = []
                for class_name, class_data in data_by_class:
                    y_true = class_data['actual']
                    y_pred = class_data['prediction']
                    metrics_df = pd.DataFrame({
                        "class": [class_name],
                        "unique_id": 'overall',
                        "model": [model],
                        "feature_type": [feature_type],
                        "method": [method],
                        "WAPE": [float(wape_metric(y_true, y_pred))],
                        "MMA": [float(mma_metric(y_true, y_pred))],
                        "MMAN": [float(mman_metric(y_true, y_pred))],
                        "MAE": [float(mean_absolute_error(y_true, y_pred))],
                        "MSE": [float(mean_squared_error(y_true, y_pred))],
                        "RMSE": [float(np.sqrt(mean_squared_error(y_true, y_pred)))],
                        "Bias": [float(bias_metric(y_true, y_pred))],
                    })
                    metrics_list.append(metrics_df)

                if len(metrics_list) > 1:
                    class_metrics = pd.concat(metrics_list, ignore_index=True)
                else:
                    class_metrics = metrics_df
                class_metrics['run_id'] = run_id
                class_metrics = class_metrics[['run_id', 'model', 'feature_type', 'method', 'class', key_column, 'WAPE', 'MMA', 'MMAN', 'MAE', 'MSE', 'RMSE', 'Bias']]
                class_metrics.to_sql('metrics_by_class', con=cluster_engine, if_exists='append', index=False, chunksize=chunk_size)

    # Baseline forecast

    for model in [baseline]:
        for feature_type in ['None']:
            for method in ['None']:
                metrics_list = []
                forecast_df = global_forecast[(global_forecast['model'] == model) & 
                                            (global_forecast['feature_type'] == feature_type) &
                                            (global_forecast['method'] == method)]

                # Calculate metrics for each class
                data_by_class = forecast_df.groupby('class')
                metrics_list = []
                for class_name, class_data in data_by_class:
                    y_true = class_data['actual']
                    y_pred = class_data['prediction']
                    metrics_df = pd.DataFrame({
                        "class": [class_name],
                        "unique_id": 'overall',
                        "model": [model],
                        "feature_type": [feature_type],
                        "method": [method],
                        "WAPE": [float(wape_metric(y_true, y_pred))],
                        "MMA": [float(mma_metric(y_true, y_pred))],
                        "MMAN": [float(mman_metric(y_true, y_pred))],
                        "MAE": [float(mean_absolute_error(y_true, y_pred))],
                        "MSE": [float(mean_squared_error(y_true, y_pred))],
                        "RMSE": [float(np.sqrt(mean_squared_error(y_true, y_pred)))],
                        "Bias": [float(bias_metric(y_true, y_pred))],
                    })
                    metrics_list.append(metrics_df)

                if len(metrics_list) > 1:
                    class_metrics = pd.concat(metrics_list, ignore_index=True)
                else:
                    class_metrics = metrics_df
                class_metrics['run_id'] = run_id
                class_metrics = class_metrics[['run_id', 'model', 'feature_type', 'method', 'class', key_column, 'WAPE', 'MMA', 'MMAN', 'MAE', 'MSE', 'RMSE', 'Bias']]
                class_metrics.to_sql('metrics_by_class', con=cluster_engine, if_exists='append', index=False, chunksize=chunk_size)

                description = f"{model} for {feature_type} using {method} features"
                started, step_count = duration_calculation(description, run_id, machine_name, action, step_count, started, cluster_engine)
