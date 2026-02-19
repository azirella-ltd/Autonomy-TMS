import numpy as np
import pandas as pd
from datetime import datetime
import gc
import warnings
import os
from datetime import datetime
import itertools


from sklearn.preprocessing import StandardScaler
from sklearn.cluster import AgglomerativeClustering, KMeans, Birch, MeanShift, OPTICS, SpectralClustering
from sklearn.mixture import GaussianMixture
from sklearn.metrics import silhouette_score, davies_bouldin_score
from sklearn.preprocessing import LabelEncoder
from multiprocessing import Pool
from functools import partial
from statsmodels.tsa.seasonal import STL
from sklearn.linear_model import LassoCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_selection import mutual_info_regression
from sklearn.decomposition import PCA
from sklearn.model_selection import train_test_split
from sklearn.cluster import AffinityPropagation
from sklearn.metrics.pairwise import euclidean_distances
from scipy.spatial.distance import cdist

import hdbscan

from sklearn.cluster import estimate_bandwidth
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score, davies_bouldin_score
from sklearn.preprocessing import LabelEncoder

from matplotlib import pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import seaborn as sns

from tsfresh import extract_features
from tsfresh.utilities.dataframe_functions import impute
from tsfresh.feature_extraction import EfficientFCParameters
from tsfresh import select_features

from helper import (
    mysql_cluster_connection,
    mysql_data_connection,
    load_configuration,
    machine_info,
    data_info,
    duration_calculation,
    load_dataset,
    time_bucketing,
    data_preparation,
    create_features
)


# Suppress all warnings
warnings.filterwarnings("ignore")

key_column = "unique_id"
action = 'clustering'

def clear_memory():
    gc.collect()

cluster_conn, cluster_cursor, cluster_engine = mysql_cluster_connection()
data_conn, data_cursor, data_engine = mysql_data_connection()
os_name, machine_name = machine_info()
config_df = load_configuration(action, cluster_cursor, machine_name)

run_id = config_df['run_id'][0]
dataset = config_df['dataset'][0]
demand_item = config_df['demand_item'][0]    
demand_point = config_df['demand_point'][0]
target_column = config_df['target_column'][0]
date_column = config_df['date_column'][0]
time_bucket = config_df['time_bucket'][0]
number_of_periods_to_forecast = config_df['number_of_periods_to_forecast'][0]
number_of_items_analyzed = config_df['number_of_items_analyzed'][0]
ignore_numeric_columns = config_df['ignore_numeric_columns'][0]
feature_correlation_threshold = config_df['feature_correlation_threshold'][0]
cv_sq_threshold = config_df['cv_sq_threshold'][0]
adi_threshold = config_df['adi_threshold'][0]
minimum_observations_threshold = config_df['minimum_observations_threshold'][0]
min_clusters = config_df['min_clusters'][0]
max_clusters = config_df['max_clusters'][0]
min_cluster_size = config_df['min_cluster_size'][0]
if min_cluster_size < 5:
    min_cluster_size = 5
min_cluster_size_uom = config_df['min_cluster_size_uom'][0]
characteristics_creation_method = config_df['characteristics_creation_method'][0]
cluster_selection_method = config_df['cluster_selection_method'][0]
feature_correlation_threshold = config_df['feature_correlation_threshold'][0]
feature_importance_method = config_df['feature_importance_method'][0]
feature_importance_threshold = config_df['feature_importance_threshold'][0]
pca_variance_threshold = config_df['pca_variance_threshold'][0]
pca_importance_threshold = config_df['pca_importance_threshold'][0]

config_df.to_sql('run_details', con=cluster_engine, if_exists='append', index=False, method='multi', chunksize=10000)
clear_memory()

data_folder, njobs, chunk_size = data_info(os_name,dataset)
 
started = datetime.now()
initial_time = started
step_count = 0

started, step_count = duration_calculation("Initialization", run_id, machine_name, action,step_count, started, cluster_engine)


df, numeric_columns, categorical_columns, static_categorical_columns, dynamic_categorical_columns, \
    unknown_covariates, unknown_covariates_expected_values, known_covariates, known_covariariates_expected_values = \
        load_dataset(config_df, key_column, data_folder)

#Encode the categorical columns
mapping_dict = {}
label_encoder = LabelEncoder()
for col in categorical_columns:
    label_encoder.fit(df[col])
    df[col + '_encoded'] = label_encoder.transform(df[col])
    
    mapping_dict[col] = pd.DataFrame({
        'unique_id': df['unique_id'],
        'original_category': df[col],
        'encoded_value': df[col + '_encoded']
    }).drop_duplicates()
# Modify the original DataFrame
for col in categorical_columns:
    df[col] = df[col + '_encoded']
    df = df.drop(columns=[col + '_encoded'])

started, step_count = duration_calculation("Load Data", run_id, machine_name, action, step_count, started, cluster_engine)

df = time_bucketing(df, key_column, date_column, target_column, time_bucket, \
                   numeric_columns, categorical_columns, static_categorical_columns, dynamic_categorical_columns)
started, step_count = duration_calculation("Time Bucketing", run_id, machine_name, action, step_count, started, cluster_engine)

df, period, trend, seasonal, min_cluster_size, max_date, minimum_observations_threshold = \
    data_preparation(df, key_column, date_column, target_column, numeric_columns, categorical_columns, \
                     time_bucket, number_of_items_analyzed, number_of_periods_to_forecast, \
                     min_cluster_size, min_cluster_size_uom)

df = df[df[date_column] <= max_date]

if dataset == "Honeywell":
    file_name = "industrial_dataset.csv"
else:
    file_name = 'cpg_dataset.csv'

file_path = data_folder + file_name
df.to_csv(file_path)

original_df = df.copy()

started, step_count = duration_calculation("Data Preparation", run_id, machine_name, action, step_count, started, cluster_engine)

cluster_analysis_columns = [
                            key_column, 
                            date_column, 
                            target_column
                            ] #+ numeric_columns
print("cluster_analysis_columns:\n",cluster_analysis_columns)
print("df.columns:\n",df.columns)
df = df[cluster_analysis_columns]
print("cluster_analyis_columns: ", cluster_analysis_columns)
print(df.head(10))

df.reset_index(inplace=True)
df.drop(columns=['index'], inplace=True)



##################################################################
# Define characteristics to be extracted

general_fc_parameters = {'mean': None, 'median': None, 'length': None, 'standard_deviation': None, 'root_mean_square': None, 'quantile': [{'q': 0.1},{'q': 0.5},{'q': 0.9}]}

stationarity_fc_parameters = {'augmented_dickey_fuller': [{'attr': 'teststat'}, {'attr': 'pvalue'}, {'attr': 'usedlag'}]}

sporadic_fc_parameters = {'agg_autocorrelation': [{'f_agg': 'mean', 'maxlag': 40}, {'f_agg': 'median', 'maxlag': 40}, 
                                                  {'f_agg': 'var', 'maxlag': 40}], 'percentage_of_reoccurring_values_to_all_values': None,'count_above': [{'t': 0}],
                        'count_below_mean': None,
                        'longest_strike_below_mean': None,
                        'variance': None,
                        'standard_deviation': None,
                        'has_duplicate_max': None,
                        'abs_energy': None,
                        'skewness': None,
                        'kurtosis': None,
                        'large_standard_deviation': [{'r': 0.75}, {'r': 0.95}],
                        'percentage_of_reoccurring_datapoints_to_all_datapoints': None,
                        'range_count': [{'min': 0, 'max': 1}]}

seasonality_fc_parameters = {
                        'spkt_welch_density': [
                            {'coeff': 2}, 
                            {'coeff': 5}, 
                            {'coeff': 8}],
                        'fft_coefficient': [
                            {'coeff': 0, 'attr': 'real'}, 
                            {'coeff': 1, 'attr': 'real'}, 
                            {'coeff': 2, 'attr': 'real'}],
                        'fft_aggregated': [
                            {'aggtype':'centroid'}, 
                            {'aggtype': 'variance'}, 
                            {'aggtype': 'skew'}, 
                            {'aggtype': 'kurtosis'}],
                        'number_peaks': [
                            {'n': 1}, 
                            {'n': 3}, 
                            {'n': 5}],
                        'energy_ratio_by_chunks': [
                            {'num_segments': 10, 'segment_focus': 0}, 
                            {'num_segments': 10, 'segment_focus': 1}],
                        'time_reversal_asymmetry_statistic': [
                            {'lag': 1}, 
                            {'lag': 2}, 
                            {'lag': 3}]}

trend_fc_parameters = {
                        'linear_trend': [
                            {'attr': 'slope'}, 
                            {'attr': 'intercept'}, 
                            {'attr': 'rvalue'}],
                        'linear_trend_timewise': [
                            {'attr': 'slope'}, 
                            {'attr': 'rvalue'}],
                        'ratio_beyond_r_sigma': [
                            {'r': 1}, 
                            {'r': 2}, 
                            {'r': 3}],
                        'ar_coefficient': [
                            {'coeff': 0, 'k': 10}, 
                            {'coeff': 1, 'k': 10}],
                        'absolute_sum_of_changes': None,
                        'first_location_of_maximum': None,
                        'first_location_of_minimum': None,
                        'c3': [
                            {'lag': 1}, 
                            {'lag': 2}, 
                            {'lag': 3}]}

smoothness_fc_parameters = {
                        'cid_ce': [
                            {'normalize': True}, 
                            {'normalize': False}]}

if "D" in time_bucket:
    freq = 7
    selected_lags = [1, 7, 30, 128, 365]
    max_lags = 365
    seasonality_fc_parameters = seasonality_fc_parameters | {
                                                            'autocorrelation': [
                                                                {'lag':   1}, 
                                                                {'lag':   2}, 
                                                                {'lag':   3}, 
                                                                {'lag':   4}, 
                                                                {'lag':   5}, 
                                                                {'lag':   6}, 
                                                                {'lag':   7}, 
                                                                {'lag':  30}, 
                                                                {'lag':  91}, 
                                                                {'lag': 182}, 
                                                                {'lag': 365}],
                                                            'partial_autocorrelation': [
                                                                {'lag':   1}, 
                                                                {'lag':   2}, 
                                                                {'lag':   3}, 
                                                                {'lag':   4}, 
                                                                {'lag':   5}, 
                                                                {'lag':   6}, 
                                                                {'lag':   7}, 
                                                                {'lag':  30}, 
                                                                {'lag':  91}, 
                                                                {'lag': 182}, 
                                                                {'lag': 365}],
                                                            'c3': [
                                                                {'lag':   1}, 
                                                                {'lag':   2}, 
                                                                {'lag':   3}, 
                                                                {'lag':   4}, 
                                                                {'lag':   5}, 
                                                                {'lag':   6}, 
                                                                {'lag':   7}, 
                                                                {'lag':  30}, 
                                                                {'lag':  91}, 
                                                                {'lag': 182}, 
                                                                {'lag': 365}]}
    smoothness_fc_parameters = smoothness_fc_parameters | {
                                                            'symmetry_looking': [
                                                            {'r': 0.1}, 
                                                            {'r': 0.2}]}
    trend_fc_parameters = trend_fc_parameters | {'agg_linear_trend': [
                                                        {'attr': 'slope', 'chunk_len':90, 'f_agg':'mean'}, 
                                                        #{'attr': 'slope', 'chunk_len':90, 'f_agg':'median'}, 
                                                        {'attr': 'slope', 'chunk_len':90, 'f_agg':'max'}, 
                                                        {'attr': 'slope', 'chunk_len':90, 'f_agg':'min'}]}
    
elif "W" in time_bucket:
    freq = 52
    selected_lags= [1, 4, 13, 52]
    max_lags = 52
    seasonality_fc_parameters = seasonality_fc_parameters | {
                                                            'autocorrelation': [
                                                                {'lag':  1}, 
                                                                {'lag':  2}, 
                                                                {'lag':  3}, 
                                                                {'lag':  4}, 
                                                                {'lag': 13}, 
                                                                {'lag': 26}, 
                                                                {'lag': 39}, 
                                                                {'lag': 52}],
                                                            'partial_autocorrelation': [
                                                                {'lag':  1}, 
                                                                {'lag':  2}, 
                                                                {'lag':  3}, 
                                                                {'lag':  4}, 
                                                                {'lag': 13}, 
                                                                {'lag': 26}, 
                                                                {'lag': 39}, 
                                                                {'lag': 52}],
                                                            'c3': [
                                                                {'lag':  1}, 
                                                                {'lag':  2}, 
                                                                {'lag':  3}, 
                                                                {'lag':  4}, 
                                                                {'lag': 13}, 
                                                                {'lag': 52}]}
    smoothness_fc_parameters = smoothness_fc_parameters | {
                                                            'symmetry_looking': [
                                                                {'r': 0.3}, 
                                                                {'r': 0.5}]}
    trend_fc_parameters = trend_fc_parameters | {'agg_linear_trend': [
                                                        {'attr': 'slope', 'chunk_len':13, 'f_agg':'mean'}, 
                                                        #{'attr': 'slope', 'chunk_len':13, 'f_agg':'median'}, 
                                                        {'attr': 'slope', 'chunk_len':13, 'f_agg':'max'}, 
                                                        {'attr': 'slope', 'chunk_len':13, 'f_agg':'min'}]}

elif "M" in time_bucket:
    freq = 12
    selected_lags = [1, 3, 12]
    max_lags = 12
    seasonality_fc_parameters = seasonality_fc_parameters | {
                                                            'autocorrelation': [
                                                                {'lag':  1}, 
                                                                {'lag':  2}, 
                                                                {'lag':  3}, 
                                                                {'lag':  6}, 
                                                                {'lag':  9}, 
                                                                {'lag': 12}],
                                                            'partial_autocorrelation': [
                                                                {'lag':  1}, 
                                                                {'lag':  2}, 
                                                                {'lag':  3}, 
                                                                {'lag':  6}, 
                                                                {'lag':  9}, 
                                                                {'lag': 12}],
                                                            'c3': [
                                                                {'lag':  1}, 
                                                                {'lag':  2}, 
                                                                {'lag':  3}, 
                                                                {'lag': 12}]}
    smoothness_fc_parameters = smoothness_fc_parameters | {
                                                            'symmetry_looking': [{'r': 0.5}, {'r': 0.7}]}
    trend_fc_parameters = trend_fc_parameters | {'agg_linear_trend': [
                                                                    {'attr': 'slope', 'chunk_len':3, 'f_agg':'mean'}, 
                                                                    #{'attr': 'slope', 'chunk_len':3, 'f_agg':'median'}, 
                                                                    {'attr': 'slope', 'chunk_len':3, 'f_agg':'max'}, 
                                                                    {'attr': 'slope', 'chunk_len':3, 'f_agg':'min'}]}

##################################################################
# Extract features using the specified configuration
print('Extracting features using the specified configuration:', characteristics_creation_method)
if characteristics_creation_method == 'tsfresh' or characteristics_creation_method == 'both':
    custom_fc_parameters = general_fc_parameters | stationarity_fc_parameters | sporadic_fc_parameters | seasonality_fc_parameters | trend_fc_parameters | smoothness_fc_parameters
    use_numeric_columns = False
    if len(numeric_columns) > 1 and use_numeric_columns: 
        all_numeric_columns = [target_column] + numeric_columns
        print("all_numeric_columns:", all_numeric_columns)
        print(df[all_numeric_columns].head(10))
        df_melted = df.melt(id_vars=[key_column, date_column], value_vars=all_numeric_columns, var_name='kind', value_name='value')
        print("df_melted.head(10):", df_melted.head(10))
        print(df_melted.shape)
        # Extract features for all numeric columns
        features = extract_features(df_melted, column_id=key_column, column_sort=date_column, column_kind='kind', column_value='value', n_jobs=njobs)

        #features.to_csv(data_folder + "features.csv")
        #scaler = StandardScaler()
        #scaled_features = scaler.fit_transform(features)
        #scaled_features_df = pd.DataFrame(scaled_features, columns=features.columns, index=features.index)
        #scaled_features_df.to_csv(data_folder + "scaled_features.csv")

    else:
        print(df.head(10))
        features = extract_features(df, column_id=key_column, column_sort=date_column, column_value=target_column, default_fc_parameters= custom_fc_parameters, n_jobs=njobs)

    impute(features)

    features = pd.DataFrame(features)
    features.reset_index(inplace=True)
    features.rename(columns={'index': key_column}, inplace=True)


    started, step_count = duration_calculation("Characteristic Extraction - tsfresh", run_id, machine_name, action, step_count, started, cluster_engine)


class DemandPatternClassifier:
    # define thresholds for trend and seasonality binning
    cv_sq_threshold = 0.49
    adi_threshold = 1.32

    # number of minimum observations to run STL
    minimum_observations_threshold = 12

    def __init__(self,date_column: str,target_column: str,key_column: str,period: int = 12,trend: int = 13,seasonal: int = 13,):
        self.key_column = key_column
        self.date_column = date_column
        self.target_column = target_column

    def classify(self, data: pd.DataFrame) -> pd.DataFrame:
        """Method to classify series into different demand types.Possible combinations are:
        {smooth, erratic, intermittent, lumpy, not_classified} x
        {seasonal, non-seasonal} x
        {trend, non-trend}

        Args:
            - data (pd.DataFrame): Historical data
        Returns:
            - pd.DataFrame: Historical data with a `demand_pattern_label` column added
        """
        data = self._join_key(data)
        data_orig = data.copy()

        # filter out keys where num_observations <= self.minimum_observations_threshold
        data_filtered = data.loc[data_orig.groupby(self.key_column)[self.date_column].transform("count") >= self.minimum_observations_threshold, :]
        stl_decomposed_data = self._stl_decompose(data_filtered)
        classified_data = self._assign_labels(data_orig, stl_decomposed_data)
        classified_data = self._split_key(classified_data)
        return classified_data
    
    def _stl_decompose(self, data: pd.DataFrame) -> pd.DataFrame:
        temp = data[[self.key_column, self.date_column, self.target_column]].copy()
        temp = temp.set_index(self.date_column)

        # Get the series to decompose
        series_to_decompose = [self._get_series_to_decompose(temp, key) for key in data[self.key_column].unique()]

        # Decompose the series
        decomposed_series = [self._stl_decompose_single_series(key, series, period, trend, seasonal) for key, series in series_to_decompose]

        return pd.concat(decomposed_series, ignore_index=True)

    def _org_stl_decompose(self, data: pd.DataFrame) -> pd.DataFrame:
        temp = data[[self.key_column, self.date_column, self.target_column]].copy()
        temp = temp.set_index(self.date_column)
        with Pool() as pool:
            series_to_decompose = pool.map( \
                partial( \
                    self._get_series_to_decompose, \
                    temp, \
                ), \
                [key for key in data[self.key_column].unique()], \
                chunksize=64, \
            )
            pool.close()
            pool.join()
        num_cores = 1 if len(series_to_decompose) <= os.cpu_count() else os.cpu_count()
        if num_cores == 1:
            decomposed_series = [self._stl_decompose_single_series(key, series, period, trend, seasonal) for key, series in series_to_decompose]
        else:
            pool = Pool(processes=num_cores)
            try:
                decomposed_series = pool.starmap(self._stl_decompose_single_series, series_to_decompose, chunksize=25)
            finally:
                pool.close()

        return pd.concat(decomposed_series, ignore_index=True)

    def _get_series_to_decompose( \
        self, \
        temp, \
        key \
    ):
        return key, temp[temp[self.key_column].isin([key])][self.target_column]

    def _stl_decompose_single_series( \
        self, \
        key: str, \
        series: pd.Series, \
        period: int = 12, \
        trend: int = 13, \
        seasonal: int = 13 \
    ) -> pd.DataFrame:
        # fit the model
        trend = self._make_odd(trend)
        stl = STL(series, period=period, seasonal=seasonal, trend=trend)
        result = stl.fit()

        # Construct TS Decomposition DataFrame
        seasonal_adjusted = series - result.seasonal
        result_df = pd.DataFrame( \
            { \
                self.key_column: key, \
                self.target_column: series, \
                "seasonal": result.seasonal, \
                "seasadj": seasonal_adjusted, \
                "trend": result.trend, \
                "remainder": seasonal_adjusted - result.trend \
            } \
        ).reset_index().rename(columns={"index": self.date_column})

        return result_df

    def _assign_labels(self, data: pd.DataFrame, stl: pd.DataFrame) -> pd.DataFrame:
        # add trend & seasonality to STL remainder
        stl["remainder_plus_trend"] = stl["remainder"] + stl["trend"]
        stl["remainder_plus_seasonal"] = stl["remainder"] + stl["seasonal"]

        # create new columns based on aggregation
        stl_agg = stl.groupby(self.key_column).agg( \
            n_demand_buckets=(self.target_column, "size"), \
            n_non_zero_buckets=(self.target_column, self._count_non_zero), \
            mean_cv=(self.target_column, self._calculate_mean_non_zero), \
            sd_cv=(self.target_column, self._calculate_std_non_zero), \
            total_orders=(self.target_column, "sum"), \
            var_remainder=("remainder", self._calculate_var), \
            var_remainder_plus_trend=("remainder_plus_trend", self._calculate_var), \
            var_remainder_plus_seasonal=("remainder_plus_seasonal", self._calculate_var), \
        ).reset_index()

        # find parameters necessary to bin into seasonl and trend components
        stl_agg["seasonal_strength"] = np.clip(1 - stl_agg["var_remainder"] / stl_agg["var_remainder_plus_seasonal"], 0, 1)
        stl_agg["trend_strength"] = np.clip(1 - stl_agg["var_remainder"] / stl_agg["var_remainder_plus_trend"], 0, 1)
        stl_agg["adi"] = stl_agg["n_demand_buckets"] / np.where( \
            stl_agg["n_non_zero_buckets"] == 0, np.nan, stl_agg["n_non_zero_buckets"] \
        )
        stl_agg["cv"] = stl_agg["sd_cv"] / np.where(stl_agg["mean_cv"] == 0, np.nan, stl_agg["mean_cv"])
        stl_agg["cv_sq"] = stl_agg["cv"] ** 2
        stl_agg["seasonal_bin"] = np.where(stl_agg["seasonal_strength"] > 0.5, "high_seas", "low_seas")
        stl_agg["trend_bin"] = np.where(stl_agg["trend_strength"] > 0.5, "high_local_trend", "low_local_trend")

        # create conditions on which demand-class will be assigned
        conditions = { \
            "smooth": (stl_agg["adi"] < self.adi_threshold) & (stl_agg["cv_sq"] < self.cv_sq_threshold), \
            "erratic": (stl_agg["adi"] < self.adi_threshold) & (stl_agg["cv_sq"] >= self.cv_sq_threshold), \
            "intermittent": (stl_agg["adi"] >= self.adi_threshold) & (stl_agg["cv_sq"] < self.cv_sq_threshold), \
            "lumpy": (stl_agg["adi"] >= self.adi_threshold) & (stl_agg["cv_sq"] >= self.cv_sq_threshold), \
            "single demand bucket": (stl_agg["n_demand_buckets"] == 1) \
        }

        stl_agg["demand_class"] = np.select(list(conditions.values()), list(conditions.keys()), default="Not Assigned")
        stl_agg["demand_pattern_label"] = stl_agg[["demand_class", "seasonal_bin", "trend_bin"]].apply("-".join, axis=1)

        data_out = data.merge(stl_agg[[self.key_column, "seasonal_strength","trend_strength","adi","cv_sq","demand_pattern_label"]], on=self.key_column, how="left")
        data_out = data_out.fillna(0) #("not_classified")
        return data_out

    def _join_key(self, data: pd.DataFrame) -> pd.DataFrame:
        if isinstance(self.key_column, list):
            data["internal_key"] = data[self.key_column].apply("0x1C".join, axis=1)
            self.original_key = copy.deepcopy(self.key_column)
            self.key_column = "internal_key"
        else:
            self.original_key = self.key_column
        return data

    def _split_key(self, data: pd.DataFrame) -> pd.DataFrame:
        if isinstance(self.original_key, list):
            data[self.original_key] = data[self.key_column].str.split("0x1C", expand=True)
        return data

    def _make_odd(self, n):
        return n + 1 if n % 2 == 0 else n

    def _count_non_zero(self, x):
        return np.sum(x > 0)

    def _calculate_mean_non_zero(self, x):
        return np.mean(x[x > 0])

    def _calculate_std_non_zero(self, x):
        return np.std(x[x > 0])

    def _calculate_var(self, x):
        return np.var(x)


# Initialize the classifier with column names

if characteristics_creation_method == 'classifier' or characteristics_creation_method == 'both':
    classifier = DemandPatternClassifier( \
        date_column=date_column, \
        target_column=target_column, \
        key_column=key_column, \
        period=period, \
        trend=trend, \
        seasonal=seasonal, \
    )

    # Classify the data
    classified_data = classifier.classify(df)

    # Select the specific columns you're interested in
    df_selected = classified_data[[key_column, 'seasonal_strength', 'trend_strength', 'adi', 'cv_sq', 'demand_pattern_label']]


    # Drop duplicates based on unique_id (assuming that these fields are unique for each unique_id)
    df_classification = df_selected.drop_duplicates(subset=[key_column])
    df_classification['demand_class'] = df_classification['demand_pattern_label'].astype('category').cat.codes
    df_classification.drop(columns=['demand_pattern_label'], axis=1, inplace=True)
    

    started, step_count = duration_calculation("Characteristic Extraction - Classifier", run_id, machine_name, action, step_count, started, cluster_engine)


if characteristics_creation_method == 'classifier':
    summary_stats = df_classification 
    print(summary_stats.head(10))
elif characteristics_creation_method == 'tsfresh':
    summary_stats = features
    print(summary_stats.head(10))
elif characteristics_creation_method == 'both':
    summary_stats = pd.merge(features, df_classification, on=key_column, how='inner')
    print(summary_stats.head(10))

characteristics_df = summary_stats.copy()
#characteristics_df.columns = [col.split('|', 1)[-1] for col in characteristics_df.columns]
characteristics_df['run_id'] = run_id
#characteristics_df[['demand_item', 'demand_point']] = characteristics_df[key_column].str.split("|", expand=True)
#characteristics_df.drop(columns=[key_column], axis=1, inplace=True)
#df_melted = pd.melt(characteristics_df, id_vars=['run_id', 'unique_id'], var_name='characteristic', value_name='value')
#df_melted.to_sql('characteristics', con=cluster_engine, if_exists='append', index=False, chunksize=50000)
#result = to_databricks(data_to_insert=df_melted, table_name='characteristics')

summary_stats.fillna(0, inplace=True)



def ensure_min_cluster_size(features_df, labels, min_cluster_size):
    # Get unique clusters and their counts
    unique_clusters, counts = np.unique(labels, return_counts=True)

    # Identify clusters smaller than the minimum size
    small_clusters = unique_clusters[counts < min_cluster_size]
    
    # If there are no small clusters, return the labels unchanged
    if len(small_clusters) == 0:
        return labels

    # Identify the large clusters that meet the minimum size
    large_clusters = unique_clusters[counts >= min_cluster_size]
    
    # Prepare DataFrame for handling small clusters
    features_df_with_labels = features_df.copy()
    features_df_with_labels['cluster'] = labels
    
    for small_cluster in small_clusters:
        # Points in the small cluster
        small_cluster_points = features_df_with_labels[features_df_with_labels['cluster'] == small_cluster]
        
        # Points in the large clusters
        large_cluster_points = features_df_with_labels[features_df_with_labels['cluster'].isin(large_clusters)]
        
        # Compute distances between small cluster points and large cluster points
        distances = cdist(small_cluster_points.drop(columns=['cluster']).values, \
                          large_cluster_points.drop(columns=['cluster']).values)

        # Find the nearest large cluster for each point
        nearest_indices = np.argmin(distances, axis=1)
        nearest_large_cluster_labels = large_cluster_points['cluster'].values[nearest_indices]
        
        # Reassign small cluster points to nearest large cluster
        for i, index in enumerate(small_cluster_points.index):
            labels[index] = nearest_large_cluster_labels[i]

    return labels

def find_cluster_centroids(features_df, labels):
        cluster_centers_df = features_df.copy()
        cluster_centers_df['cluster'] = labels
        cols = ['cluster'] + [col for col in cluster_centers_df.columns if col != 'cluster']
        cluster_centers_df = cluster_centers_df[cols]
        cluster_centers_df = cluster_centers_df.groupby('cluster').mean()
        cluster_centers_df.reset_index(drop=False,inplace=True) 

        return cluster_centers_df

def calculate_wcss(scaled_features_df, labels, n_clusters):
    """Calculate WCSS-like metric for Clustering methods without inertia"""
    wcss = 0
    for i in range(n_clusters):
        # Get points in the cluster
        cluster_points = scaled_features_df[labels == i]
        if len(cluster_points) > 0:
            # Calculate centroid
            centroid = cluster_points.mean(axis=0)
            # Sum of squared distances of points to the centroid
            wcss += np.sum((cluster_points - centroid) ** 2)
    return wcss


############################################################################
# Function to determine the optimal number of clusters using various methods
def find_optimal_clusters(df, key_column, min_clusters=10, max_clusters=20, cluster_selection_method='KMeans'):
    # Normalize features
    unique_ids = df[key_column].unique()
    features_df = pd.DataFrame(df.drop(columns=[key_column]))

    scaler = StandardScaler()
    scaled_features_df = scaler.fit_transform(features_df)

    if cluster_selection_method == 'KMeans':
        inertia = []
        silhouette_scores = []
        davies_bouldin_scores = []

        if max_clusters > min_clusters:
            K = range(min_clusters, max_clusters)
            for k in K:
                kmeans = KMeans(n_clusters=k, random_state=42)
                kmeans.fit(scaled_features_df)
                inertia.append(kmeans.inertia_)
                silhouette_scores.append(silhouette_score(scaled_features_df, kmeans.labels_))
                davies_bouldin_scores.append(davies_bouldin_score(scaled_features_df, kmeans.labels_))

            optimal_k_elbow = K[np.argmin(np.diff(np.diff(inertia)))]
            if optimal_k_elbow < min_clusters:
                optimal_k_elbow += int(min_clusters)
            optimal_k_silhouette = K[np.argmax(silhouette_scores)]
            optimal_k_davies = K[np.argmin(davies_bouldin_scores)]
            num_clusters = max(optimal_k_elbow, optimal_k_silhouette, optimal_k_davies)
        else:
            num_clusters = 16

        kmeans = KMeans(n_clusters=num_clusters, random_state=42)
        labels = kmeans.fit_predict(scaled_features_df)
        labels = ensure_min_cluster_size(features_df, labels, min_cluster_size)
        cluster_centers_df = find_cluster_centroids(features_df, labels)
        cluster_df = pd.DataFrame({key_column: df[key_column], 'cluster': labels})

    elif cluster_selection_method == 'DBSCAN':
        clusterer = hdbscan.HDBSCAN(min_cluster_size=min_clusters)
        labels = clusterer.fit_predict(scaled_features_df)
        cluster_centers_df = find_cluster_centroids(features_df, labels)
        cluster_df = pd.DataFrame({key_column: unique_ids, 'cluster': labels})

    elif cluster_selection_method == 'AgglomerativeClustering':
        elbow_scores, silhouette_scores, davies_bouldin_scores = [], [], []

        if max_clusters > min_clusters:
            N = range(min_clusters, max_clusters)
            for n in N:
                clusterer = AgglomerativeClustering(n_clusters=n, linkage='ward')
                labels = clusterer.fit_predict(scaled_features_df)
                elbow_scores.append(calculate_wcss(scaled_features_df, labels, n))
                silhouette_scores.append(silhouette_score(scaled_features_df, labels))
                davies_bouldin_scores.append(davies_bouldin_score(scaled_features_df, labels))

            optimal_n_elbow = N[np.argmin(np.diff(np.diff(elbow_scores)))]
            if optimal_n_elbow < min_clusters:
                optimal_n_elbow += int(min_clusters)
            optimal_n_silhouette = N[np.argmax(silhouette_scores)]
            optimal_n_davies = N[np.argmin(davies_bouldin_scores)]
            num_clusters = max(optimal_n_elbow, optimal_n_silhouette, optimal_n_davies)
        else:
            num_clusters = 6

        clusterer = AgglomerativeClustering(n_clusters=num_clusters, linkage='ward')
        labels = clusterer.fit_predict(scaled_features_df)
        labels = ensure_min_cluster_size(features_df, labels, min_cluster_size)
        cluster_centers_df = find_cluster_centroids(features_df, labels)
        cluster_df = pd.DataFrame({key_column: df[key_column], 'cluster': labels})

    elif cluster_selection_method == 'OPTICS':
        clusterer = OPTICS(min_samples=2)
        labels = clusterer.fit_predict(scaled_features_df)
        cluster_centers_df = find_cluster_centroids(features_df, labels)
        labels = ensure_min_cluster_size(features_df, labels, min_cluster_size)
        cluster_df = pd.DataFrame({key_column: unique_ids, 'cluster': labels})

    elif cluster_selection_method == 'Birch':
        clusterer = Birch(threshold=0.5, n_clusters=max_clusters)
        labels = clusterer.fit_predict(scaled_features_df)
        cluster_centers_df = find_cluster_centroids(features_df, labels)
        labels = ensure_min_cluster_size(features_df, labels, min_cluster_size)
        cluster_df = pd.DataFrame({key_column: unique_ids, 'cluster': labels})

    elif cluster_selection_method == 'GaussianMixture':
        bic_scores, aic_scores = [], []
        for n in range(min_clusters, max_clusters):
            gmm = GaussianMixture(n_components=n, random_state=42)
            gmm.fit(scaled_features_df)
            bic_scores.append(gmm.bic(scaled_features_df))
            aic_scores.append(gmm.aic(scaled_features_df))

        optimal_n = max(range(min_clusters, max_clusters)[np.argmin(bic_scores)],
                        range(min_clusters, max_clusters)[np.argmin(aic_scores)])
        clusterer = GaussianMixture(n_components=optimal_n, random_state=42)
        clusterer.fit(scaled_features_df)
        labels = clusterer.predict(scaled_features_df)
        cluster_centers = scaler.inverse_transform(clusterer.means_)
        cluster_centers_df = pd.DataFrame(cluster_centers, columns=features_df.columns)
        labels = ensure_min_cluster_size(features_df, labels, min_cluster_size)
        cluster_df = pd.DataFrame({key_column: unique_ids, 'cluster': labels})

    elif cluster_selection_method == 'MeanShift':
        bandwidth = estimate_bandwidth(scaled_features_df, quantile=0.2, n_samples=500)
        bandwidth = bandwidth if bandwidth > 0 else None
        clusterer = MeanShift(bandwidth=bandwidth, bin_seeding=True)
        labels = clusterer.fit_predict(scaled_features_df)
        cluster_centers = scaler.inverse_transform(clusterer.cluster_centers_)
        cluster_centers_df = pd.DataFrame(cluster_centers, columns=features_df.columns)
        labels = ensure_min_cluster_size(features_df, labels, min_cluster_size)
        cluster_df = pd.DataFrame({key_column: unique_ids, 'cluster': labels})

    elif cluster_selection_method == 'SpectralClustering':
        clusterer = SpectralClustering(n_clusters=max(min_clusters, 8), 
                                       eigen_solver='arpack', 
                                       n_components=8,
                                       random_state=42)
        labels = clusterer.fit_predict(scaled_features_df)
        cluster_centers_df = find_cluster_centroids(features_df, labels)
        labels = ensure_min_cluster_size(features_df, labels, min_cluster_size)
        cluster_df = pd.DataFrame({key_column: unique_ids, 'cluster': labels})

    elif cluster_selection_method == 'AffinityPropagation':
        similarity_matrix = -euclidean_distances(scaled_features_df)
        clusterer = AffinityPropagation(damping=0.9, preference=-20, affinity='precomputed')
        labels = clusterer.fit_predict(similarity_matrix)
        cluster_centers = scaled_features_df[clusterer.cluster_centers_indices_]
        cluster_centers_ = scaler.inverse_transform(cluster_centers)
        cluster_centers_df = pd.DataFrame(cluster_centers_, columns=features_df.columns)
        labels = ensure_min_cluster_size(features_df, labels, min_cluster_size)
        cluster_df = pd.DataFrame({key_column: unique_ids, 'cluster': labels})

    # Ensure cluster_centers_df has cluster column for consistent remapping
    if 'cluster' not in cluster_centers_df.columns:
        # Ensure cluster_centers_df has 'cluster' column for consistent remapping
        num_centroids = cluster_centers_df.shape[0]
        unique_clusters = np.unique(labels)
        if len(unique_clusters) == num_centroids:
            cluster_centers_df['cluster'] = unique_clusters
        else:
            cluster_centers_df['cluster'] = range(num_centroids)

    return cluster_df, cluster_centers_df


# Run the function to find the optimal number of clusters and get the cluster assignments

#mode_df = original_df.groupby(key_column)[target_column].apply(lambda x: x.mode().iloc[0] if not x.mode().empty else None)
#mode_df = mode_df.reset_index()  # Reset index to turn key_column back into a column
#mode_df.columns = [key_column, target_column + "__mode"]  # Rename columns appropriately
#print(mode_df.columns)
#print(df.columns)
#summary_stats = pd.merge(summary_stats, mode_df, on=key_column, how="left")  # Use 'how="left"' if you want all rows from summary_stats

cluster_results_df, centroids_df = find_optimal_clusters(summary_stats, key_column, min_clusters, max_clusters, cluster_selection_method)

cluster_counts = cluster_results_df['cluster'].value_counts().sort_values(ascending=False)
cluster_counts = cluster_counts.reset_index()
cluster_counts.columns = ['old_cluster', 'count']
first_cluster = cluster_counts['old_cluster'].min()
if cluster_counts['old_cluster'].min() > 0:
    first_cluster = 0
cluster_mapping = {old_label: new_label for new_label, old_label in enumerate(cluster_counts['old_cluster'], start=first_cluster)}

cluster_results_df['cluster'] = cluster_results_df['cluster'].map(cluster_mapping)
centroids_df['cluster'] = centroids_df['cluster'].map(cluster_mapping)

cluster_mapping = cluster_results_df.set_index(key_column)['cluster']
original_df['cluster'] = original_df[key_column].map(cluster_mapping)

cluster_counts = original_df['cluster'].value_counts().sort_values(ascending=False)
cluster_counts = cluster_counts.reset_index()
cluster_counts.columns = ['old_cluster', 'count']

labels = cluster_results_df['cluster']
unique_labels = sorted(centroids_df['cluster'])
features_df = summary_stats.copy()
features_df['cluster'] = labels
features_df.sort_values(by=['cluster', key_column], inplace=True)
labels = features_df['cluster']
unique_labels = sorted(labels.unique())

features_df = features_df.drop(columns=[key_column,'cluster'])

feature_centers_df = centroids_df.drop(columns=['cluster'])

# Train a random forest classifier to determnine the static features that cause most separation between clusers
rf = RandomForestClassifier()
rf.fit(features_df, labels)

# Extract feature importances
feature_importances = pd.Series(rf.feature_importances_, index=features_df.columns)
feature_importances = feature_importances.sort_values(ascending=False)

#custom_fc_parameters = general_fc_parameters | sporadic_fc_parameters | seasonality_fc_parameters | trend_fc_parameters | smoothness_fc_parameters

#sporadic_columns = [f"{num}_{sporadic}" for num, sporadic in itertools.product(numeric_columns, sporadic_fc_features)]

if characteristics_creation_method == 'tsfresh': 
    #N = 5
    #important_features = feature_importances.index[:N].tolist() 
    #mode_value = target_column + '__mode'
    smoothness = target_column + '__cid_ce__normalize_True'
    stationarity = target_column + '__augmented_dickey_fuller__p_value' 
    seasonality = target_column + '__spkt_welch_density__coeff_5'
    sporadic = target_column + '__range_count__max_1__min_0'
    trend = target_column + '__linear_trend__attr_"slope"'
    important_features = [smoothness, stationarity, seasonality, sporadic, trend]
    axis_labels = ['smoothness', 'stationarity', 'seasonality', 'sporadic', 'trend']

elif characteristics_creation_method == 'classifier':
    important_features = ['adi', 'cv_sq', 'seasonal_strength', 'trend_strength']
    axis_labels = ['adi', 'cv_sq', 'seasonal_strength', 'trend_strength']

else:
    important_features = ['adi', 'cv_sq', 'seasonal_strength', 'trend_strength']
    axis_labels = ['adi', 'cv_sq', 'seasonal_strength', 'trend_strength']

file_name = f"{data_folder}important_features_{run_id}.pdf"
features_df['cluster'] = labels
feature_indices = [i for i, col in enumerate(features_df.columns) if col in important_features]
important_feature_map = {features_df.columns[i]: axis_labels[important_features.index(features_df.columns[i])] for i in feature_indices}

file_name = data_folder + run_id + "_clusters.csv"
file_name = file_name.replace(" | ", "_")
#print("file_name: ", file_name)
#cluster_results_df.to_csv(file_name)
clusters_df = cluster_results_df.copy()
#print("clusters_df:\n", clusters_df[clusters_df[key_column].str.startswith('002-439')])
clusters_df['run_id'] = run_id
clusters_df[['demand_item', 'demand_point']] = clusters_df[key_column].str.split("|", expand=True)
clusters_df = clusters_df[['run_id', 'unique_id', 'demand_item', 'demand_point', 'cluster']]
#print("clusters_df:\n", clusters_df[clusters_df['demand_item']=='002-439'])
clusters_df.to_sql('clusters', con=cluster_engine, if_exists='append', index=False, chunksize=chunk_size)
#result = to_databricks(table_name='clusters', data_to_insert= clusters_df)

centroids_df['run_id'] = run_id
#centroids_df.columns = [col.split("|")[-1] for col in centroids_df.columns]
centroids_df = centroids_df.reset_index(drop=True)
#print(centroids_df.head(10))

# Melt the DataFrame
df_melted = pd.melt(centroids_df, id_vars=['run_id', 'cluster'], var_name='characteristic', value_name='centroid')
df_melted.to_sql('cluster_centroids', con=cluster_engine, if_exists='append', index=False, chunksize=chunk_size)
#result = to_databricks(table_name="cluster_centroids", data_to_insert=df_melted)

# Classify the centroids using the Noodle classification
if characteristics_creation_method in ['classifier','both']:
    centroids_df = centroids_df[['run_id', 'cluster','adi', 'cv_sq', 'trend_strength', 'seasonal_strength']]
    centroids_df['seasonal_bin'] = np.where(centroids_df['seasonal_strength'] > 0.5, "high_seas", "low_seas")
    centroids_df['trend_bin'] = np.where(centroids_df['trend_strength'] > 0.5, "high_local_trend", "low_local_trend")
    conditions = [ \
        (centroids_df['adi'] < adi_threshold) & (centroids_df['cv_sq'] < cv_sq_threshold), \
        (centroids_df['adi'] < adi_threshold) & (centroids_df['cv_sq'] >= cv_sq_threshold), \
        (centroids_df['adi'] >= adi_threshold) & (centroids_df['cv_sq'] < cv_sq_threshold), \
        (centroids_df['adi'] >= adi_threshold) & (centroids_df['cv_sq'] >= cv_sq_threshold) \
    ]
    choices = ["smooth", "erratic", "intermittent", "lumpy"]
    centroids_df['demand_class'] = np.select(conditions, choices, default='unknown')

    centroids_df.to_sql('cluster_centroid_classification', con=cluster_engine, if_exists='append', index=False, chunksize=chunk_size)
    #result = to_databricks(table_name="cluster_centroids_classification", data_to_insert=centroids_df)



started, step_count = duration_calculation("Cluster Extraction", run_id, machine_name, action, step_count, started, cluster_engine)


# COMMAND ----------

# DBTITLE 1,Create Plots
create_plots = True    
# pd.set_option("mode.use_inf_as_na", True) 
if create_plots:
    file_name = f"{data_folder}important_features_{run_id}.pdf"
    features_df['cluster'] = labels
    feature_indices = [i for i, col in enumerate(features_df.columns) if col in important_features]
    important_feature_map = {features_df.columns[i]: axis_labels[important_features.index(features_df.columns[i])] for i in feature_indices}
    with PdfPages(file_name) as pdf:
        # Iterate over all unique pairs of features
        for (x_index, y_index) in itertools.combinations(feature_indices, 2):
            # Set up the figure with main plot and marginal plots
            fig = plt.figure(figsize=(8, 6))
            gs = fig.add_gridspec(4, 4, hspace=0.05, wspace=0.05)  # Control spacing
            ax_main = fig.add_subplot(gs[1:, :-1])
            ax_top = fig.add_subplot(gs[0, :-1], sharex=ax_main)
            ax_right = fig.add_subplot(gs[1:, -1], sharey=ax_main)
        
            # Main scatter plot
            scatter = ax_main.scatter(features_df.iloc[:, x_index], features_df.iloc[:, y_index], \
                                    c=labels, cmap='viridis', s=5, alpha=0.7)
            
            colors = scatter.cmap(scatter.norm(unique_labels))  # Map colors from clusters

            # Plot cluster centroids
            for i, label in enumerate(unique_labels):
                ax_main.scatter(feature_centers_df.iloc[label - 1, x_index], feature_centers_df.iloc[label - 1, y_index], edgecolor=colors[i], facecolor='none', marker='X', s=2, linewidth=2, label=f'Centroid {label}')

            # Top KDE plot for X-axis distributions
            for i, label in enumerate(unique_labels):
                sns.kdeplot(features_df[features_df['cluster'] == label].iloc[:, x_index], ax=ax_top, color=colors[i], fill=True, alpha=0.95)
                for i, label in enumerate(unique_labels):
                    data = features_df[features_df['cluster'] == label].iloc[:, x_index]
                    sns.kdeplot(data, ax=ax_top, color=colors[i], fill=True, alpha=0.95)
            ax_top.axis('off')  # Hide axis for cleaner look

            # Right KDE plot for Y-axis distributions
            for i, label in enumerate(unique_labels):
                sns.kdeplot(features_df[features_df['cluster'] == label].iloc[:, y_index], ax=ax_right, color=colors[i], fill=True, alpha=0.5, vertical=True)
            ax_right.axis('off')  # Hide axis for cleaner look

            # Main plot aesthetics
            #ax_main.set_xlabel(features_df.columns[x_index])
            #ax_main.set_ylabel(features_df.columns[y_index])
            ax_main.set_xlabel(important_feature_map[features_df.columns[x_index]])
            ax_main.set_ylabel(important_feature_map[features_df.columns[y_index]])
            ax_main.legend(fontsize=6)
            ax_main.legend()

            # Save the current figure to the PDF
            pdf.savefig()  # Adds the current figure to the PDF
            plt.close()  # Close the figure to free up memory


# COMMAND ----------

# DBTITLE 1,Principal Component Anaysis

cluster_counts = cluster_results_df['cluster'].value_counts().sort_values(ascending=False)

counts_df = pd.DataFrame(cluster_results_df.groupby('cluster')[key_column].count().reset_index())
counts_df[key_column] = counts_df[key_column].astype(int)
counts_df.sort_values(by=key_column, ascending=False, inplace=True)

    # Perform PCA to see if the important characterisitcs can be identified for each cluster
    # This could be a key way in which the cluster information is used to determine which models to be used
    # If the characteristics are consistent with either the tsfresh clustering or Noodle CLassifier, 
    # this should pint initially to the best models.or Noodle classifier
do_pca = False
if do_pca:
    id_columns = [key_column, date_column]
    feature_columns = [col for col in summary_stats.columns if col not in id_columns + [target_column]]
    for cluster in counts_df['cluster']:
        # Step 1: Identify the ID columns and the target column
        cluster_ids = cluster_results_df[cluster_results_df['cluster'] == cluster]
        cluster_ids = cluster_ids[key_column].tolist()
        PCA_df = summary_stats[summary_stats[key_column].isin(cluster_ids)]
        PCA_df = PCA_df[feature_columns]

        scaler = StandardScaler()
        scaled_PCA_df = scaler.fit_transform(PCA_df)
        pca = PCA(n_components=pca_variance_threshold)  # Retain X% of the variance
        df_pca = pca.fit_transform(scaled_PCA_df)

        df_reduced = pd.DataFrame(df_pca)
        #print("reduced\n", df_reduced.head(10))

        loadings = pd.DataFrame(pca.components_, columns=PCA_df.columns)
        #print("loadings:\n", loadings.head())  # Inspect the loadings

        for i, component in enumerate(pca.components_):
            # Create a DataFrame explicitly from the component loadings and sort by absolute values
            characteristic_importance = pd.DataFrame({'characteristic': PCA_df.columns, 'importance': component})
            
            # Convert the importance values to absolute and sort in descending order
            characteristic_importance['importance'] = characteristic_importance['importance'].abs()
            characteristic_importance = characteristic_importance.sort_values(by='importance', ascending=False)
            
            # Add the necessary metadata columns: run_id, cluster, and principal_component
            characteristic_importance['run_id'] = run_id
            characteristic_importance['cluster'] = cluster
            characteristic_importance['principal_component'] = i + 1
            
            # Reorder the columns to match the expected output
            characteristic_importance = characteristic_importance[['run_id', 'cluster', 'principal_component', 'characteristic', 'importance']]
            # Apply the split operation to each element in the 'characteristic' column
            characteristic_importance = characteristic_importance[characteristic_importance['importance'] >= pca_importance_threshold]
            #characteristic_importance['characteristic'] = characteristic_importance['characteristic'].apply(lambda x: x.split('|', 1)[-1])
            # Print to verify the structure (optional)
            #print("characteristic_importance_df:\n", characteristic_importance.head(10))
            
            # Write the DataFrame to the SQL table
            characteristic_importance.to_sql('pca_characteristic_importance', con=cluster_engine, if_exists='append', index=False, chunksize=chunk_size)
            #result = to_databricks(data_to_insert=characteristic_importance, table_name='pca_characteristic_importance')

        # Explained variance for each component
        explained_variance = pd.DataFrame({ \
            'run_id': run_id, \
            'cluster': cluster, \
            'principal_component': range(1, len(pca.explained_variance_ratio_) + 1), \
            'explained_variance': pca.explained_variance_ratio_ \
        })
        explained_variance.to_sql('pca_explained_variance', con=cluster_engine, if_exists='append', index=False, chunksize=chunk_size)
        #result = to_databricks(data_to_insert=explained_variance, table_name='pca_explained_variance')
        #print("explained_variance:\n", explained_variance)

        description = f"Cluster {cluster}: PCA Extraction"
        started, step_count = duration_calculation(description, run_id, machine_name, action, step_count, started, cluster_engine)


df = original_df.copy()

df[date_column] = pd.to_datetime(df[date_column])
df = df.sort_values(by=[key_column, date_column])
cluster_counts = df['cluster'].value_counts().sort_values(ascending=False)
cluster_counts = cluster_counts.reset_index()
cluster_counts.columns = ['cluster', 'count']

df, dynamic_features = create_features(df, time_bucket, key_column, target_column, date_column, numeric_columns, static_categorical_columns, dynamic_categorical_columns)

if 'index' in df.columns:
    df.drop(columns=['index'], inplace=True)

print("df columns after feature creation:\n", df.columns)
print(df.head(10))
full_df = df.copy()

started, step_count = duration_calculation("Target Feature Creation", run_id, machine_name, action, step_count, started, cluster_engine)

import shap

cluster_counts = df['cluster'].value_counts().sort_values(ascending=False)
cluster_counts = cluster_counts.reset_index()
cluster_counts.columns = ['cluster', 'count']

feature_importance_df = pd.DataFrame(columns=['feature', 'importance', 'cluster'])
cluster_feature_importance_results =[]
cluster_SHAP_values_results =[]

for cluster in cluster_counts['cluster']:
    # Step 1: Identify the ID columns and the target column
    cluster_ids = df[df['cluster'] == cluster][key_column].unique().tolist()
    cluster_df = df[df[key_column].isin(cluster_ids)]
    print(cluster_df.head(10))

    # Ensure that 'quantity' (the target variable) is NOT included in feature_columns
    id_columns = [key_column, date_column, 'cluster']

    # Dynamically identify the feature_columns (all columns except ID and target)
    feature_columns = [col for col in cluster_df.columns if col not in id_columns + [target_column]]
    feature_df = df[feature_columns]

    scaler = StandardScaler()
    feature_df_scaled = pd.DataFrame(scaler.fit_transform(feature_df), columns=feature_df.columns)
    correlation_matrix = feature_df_scaled.corr().abs()
    upper_triangle = correlation_matrix.where(np.triu(np.ones(correlation_matrix.shape), k=1).astype(bool))
    variances = feature_df.var()

    features_to_drop = []
    for column in upper_triangle.columns:
        correlated_features = [index for index in upper_triangle.index if upper_triangle.loc[index, column] > feature_correlation_threshold]
        if correlated_features:
            correlated_features.append(column)  # Include the column itself
            feature_with_highest_variance = variances[correlated_features].idxmax()
            features_to_drop += [f for f in correlated_features if f != feature_with_highest_variance]

    features_to_drop = list(set(features_to_drop))
    print("Features to drop due to high correlation:", features_to_drop)
    cluster_df = cluster_df.drop(columns=features_to_drop)
    original_features = feature_columns
    print("Original features:", original_features)
    feature_columns = [col for col in cluster_df.columns if col not in id_columns + [target_column]]
    print("Features after dropping:", feature_columns)

    n_items = 0
    feature_importance_results = []
    SHAP_contribution_results = []
    for unique_id, group in cluster_df.groupby(key_column):
        #print(f"Processing unique_id: {unique_id} in cluster: {cluster}")
        n_items +=1
        #print(group.head(10))
        drop_columns = id_columns + [target_column]
        X = group.drop(columns=drop_columns)
        y = group[target_column].values

        # Standardize the featuresgg
        scaler = StandardScaler()
        #X_scaled = scaler.fit_transform(X)
        #y_scaled = scaler.fit_transform(y)
        #print(unique_id,len(X), len(y)) 
        try: 
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
            if feature_importance_method == "LassoCV":
                if len(y_train) > 1:
                    cv_splits = min(5, len(y_train))  # Use the smaller of 5 or the number of samples

                # Fit LassoCV model with adjusted cv
                lasso = LassoCV(cv=cv_splits, random_state=42, max_iter=chunk_size)
                lasso.fit(X_train, y_train)
                importances = np.abs(lasso.coef_)

                explainer = shap.Explainer(lasso, X_train)
                shap_values = explainer(X_test)

            elif feature_importance_method == "RandomForest":
                rf = RandomForestRegressor(n_estimators=100, random_state=42)
                rf.fit(X_train, y_train)
                importances  = np.abs(rf.feature_importances_)

                explainer = shap.Explainer(rf, X_train)
                shap_values = explainer(X_test,check_additivity=False)

            elif feature_importance_method == "MutualInformation":
                mi = mutual_info_regression(X_train, y_train, random_state=42)
                importances = np.abs(mi)

                explainer = shap.Explainer(mi, X_train)
                shap_values = explainer(X_test)

            feature_importances_df = pd.DataFrame({
                'cluster': cluster,
                'unique_id': unique_id,
                'feature': X.columns,
                'importance': importances
            })
            feature_importances_df['importance'].fillna(0)
            feature_importance_results.append(feature_importances_df)

            shap_feature_contributions = np.abs(shap_values.values.mean(axis=0))
            shap_feature_contributions_df = pd.DataFrame({
                'cluster': cluster,
                'unique_id': unique_id,
                'feature': X_test.columns,
                'contribution': shap_feature_contributions
            })  
            shap_feature_contributions_df['contribution'].fillna(0)
            shap_feature_contributions_df = shap_feature_contributions_df.sort_values(by='contribution', ascending=False)
            SHAP_contribution_results.append(shap_feature_contributions_df)
        except ValueError:
            print(f"Error {ValueError} processing unique_id: {unique_id} in cluster: {cluster}") 

        # Visualize SHAP values
        #print("Feature contributions for the predictions:")
        #shap.summary_plot(shap_values, X_test, show=False)  # Feature importance summary plot
        #shap.plots.bar(shap_values)  # Bar plot of SHAP values

    # After processing all unique_id's for the current cluster, aggregate feature importance within the cluster
    if len(feature_importance_results) > 0:
        feature_importance_df = pd.concat(feature_importance_results, ignore_index=True)
        mean_importance = feature_importance_df.groupby('feature')['importance'].agg(['mean']).reset_index()
        cluster_importance = feature_importance_df.groupby('feature')['importance'].agg(['sum']).reset_index()
        max_importance = max(abs(mean_importance['mean']))
        if max_importance == 0:
            cluster_importance['mean'] = 1.01 * feature_importance_threshold
        else:
            cluster_importance['mean'] = mean_importance['mean'] / max_importance
        
        cluster_importance = cluster_importance[cluster_importance['mean'] >= feature_importance_threshold]                                                                            
        print("cluster_importance:\n", cluster_importance)
        cluster_importance['cluster'] = cluster  # Add the cluster_id for reference
        cluster_feature_importance_results.append(cluster_importance)

        feature_importance_df['run_id'] = run_id
        feature_importance_df = feature_importance_df[['run_id', 'cluster', 'unique_id','feature', 'importance']]
        feature_importance_df.to_sql('feature_importance_by_id', con=cluster_engine, if_exists='append', index=False, chunksize=chunk_size)
        #result = to_databricks(data_to_insert=feature_importance_df, table_name='feature_importance_by_id', mode='append')

        cluster_importance['run_id'] = run_id
        cluster_importance = cluster_importance[['run_id', 'cluster', 'feature', 'sum', 'mean']]    
        cluster_importance.to_sql('feature_importance_by_cluster', con=cluster_engine, if_exists='append', index=False, chunksize=chunk_size)
        #result = to_databricks(data_to_insert=cluster_importance, table_name='feature_importance_by_cluster', mode='append')  
        cluster_importance.drop(columns=['run_id'], inplace=True)

    if len(SHAP_contribution_results) > 0:
        SHAP_values_df = pd.concat(SHAP_contribution_results, ignore_index=True)
        mean_SHAP_values = SHAP_values_df.groupby('feature')['contribution'].agg(['mean']).reset_index()
        max_SHAP = max(abs(mean_SHAP_values['mean']))
        if max_SHAP == 0:
            mean_SHAP_values['mean'] = 1.01 * feature_importance_threshold
        else:
            mean_SHAP_values['mean'] = mean_SHAP_values['mean'] / max_SHAP

        cluster_SHAP_values = SHAP_values_df.groupby('feature')['contribution'].agg(['sum']).reset_index()
        cluster_SHAP_values['mean'] = mean_SHAP_values['mean']
        cluster_SHAP_values = cluster_SHAP_values[cluster_SHAP_values['mean'] >= feature_importance_threshold] 
        cluster_SHAP_values = cluster_SHAP_values.sort_values(by='mean', ascending=False)   
        cluster_SHAP_values['cluster'] = cluster  # Add the cluster_id for reference
        cluster_SHAP_values = cluster_SHAP_values[['cluster', 'feature', 'sum', 'mean']]
        cluster_SHAP_values_results.append(cluster_SHAP_values)

        SHAP_values_df['run_id'] = run_id
        SHAP_values_df = SHAP_values_df[['run_id', 'cluster', 'unique_id','feature', 'contribution']]
        SHAP_values_df = SHAP_values_df.sort_values(by='contribution', ascending=False)
        SHAP_values_df.to_sql('SHAP_contribution_by_id', con=cluster_engine, if_exists='append', index=False, chunksize=chunk_size)
        #result = to_databricks(data_to_insert=SHAP_values_df, table_name='SHAP_contribution_by_id', mode='append')

        cluster_SHAP_values['run_id'] = run_id
        cluster_SHAP_values = cluster_SHAP_values[['run_id', 'cluster', 'feature', 'sum', 'mean']]
        cluster_SHAP_values = cluster_SHAP_values.sort_values(by='mean', ascending=False)  
        cluster_SHAP_values.to_sql('SHAP_contribution_by_cluster', con=cluster_engine, if_exists='append', index=False, chunksize=chunk_size)
        #result = to_databricks(data_to_insert=cluster_SHAP_values, table_name='SHAP_contribution_by_cluster', mode='append')  
        cluster_SHAP_values.drop(columns=['run_id'], inplace=True)
    else:
        print("No feature importance results found for cluster:", cluster)

    description = f"Cluster {cluster}: Feature Importance"
    started, step_count = duration_calculation(description, run_id, machine_name, action, step_count, started, cluster_engine)

# Combine all cluster-level feature importance results into a single DataFrame
feature_importance_df = pd.concat(cluster_feature_importance_results, ignore_index=True)
#feature_importance_df.to_csv(data_folder + run_id + "_feature_importance.csv")

# Rename columns for clarity
mean_importance_df = feature_importance_df.groupby('feature')['mean'].agg(['mean']).reset_index()
feature_importance_df = feature_importance_df.groupby('feature')['sum'].agg(['sum']).reset_index()
feature_importance_df['mean'] = mean_importance_df['mean']
feature_importance_df.columns = ['feature', 'total', 'average']
feature_importance_df['run_id'] = run_id
feature_importance_df = feature_importance_df[['run_id', 'feature', 'total', 'average']]   
feature_importance_df = feature_importance_df.sort_values(by='average', ascending=False) 
feature_importance_df.to_sql('feature_importance_overall', con=cluster_engine, if_exists='append', index=False, chunksize=chunk_size)
#result = to_databricks(data_to_insert=feature_importance_df, table_name='feature_importance_overall', mode='append')  
#feature_importance_df.to_csv(data_folder + run_id + "_overall_feature_importance.csv")


shap_contributions_df = pd.concat(cluster_SHAP_values_results, ignore_index=True)
#shap_contributions_df.to_csv(data_folder + run_id + "SHAP_values.csv")
# Rename columns for clarity
mean_contribution_df = shap_contributions_df.groupby('feature')['mean'].agg(['mean']).reset_index()
shap_contributions_df = shap_contributions_df.groupby('feature')['sum'].agg(['sum']).reset_index()
shap_contributions_df['mean'] = mean_contribution_df['mean']
shap_contributions_df.columns = ['feature', 'total', 'average']
shap_contributions_df['run_id'] = run_id
shap_contributions_df = feature_importance_df[['run_id', 'feature', 'total', 'average']]   
shap_contributions_df = feature_importance_df.sort_values(by='average', ascending=False) 
shap_contributions_df.to_sql('SHAP_contribution_overall', con=cluster_engine, if_exists='append', index=False, chunksize=chunk_size)
#result = to_databricks(data_to_insert=feature_contribution_df, table_name='SHAP_contribution_overall', mode='append')  
#feature_contribution_df.to_csv(data_folder + run_id + "_overall_feature_importance.csv")

started = initial_time
started, step_count = duration_calculation("Overall Feature Importance", run_id, machine_name, action, step_count, started, cluster_engine)
