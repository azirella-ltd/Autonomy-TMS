import numpy as np
import pandas as pd

import platform
import psutil 
import os
from datetime import datetime
import itertools
#import ace_tools as tools

import mysql.connector

from sqlalchemy import create_engine
from databricks import sql
import urllib

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

from scipy.spatial.distance import cdist

import hdbscan
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score, davies_bouldin_score
from sktime.transformations.panel.tsfresh import TSFreshFeatureExtractor
from sklearn.preprocessing import LabelEncoder

from matplotlib import pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import seaborn as sns

from collections import defaultdict

from scipy import stats
from statsmodels.tsa.seasonal import MSTL
from statsmodels.tsa.seasonal import STL
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.tsa.stattools import acf, pacf

#from pmdarima.preprocessing import STLTransformer
#from darts import TimeSeries
#from darts.utils.statistics import extract_trend_and_seasonality
#from darts.utils.utils import ModelMode

from tsfresh import extract_features
from tsfresh.utilities.dataframe_functions import impute
from tsfresh.feature_extraction import EfficientFCParameters
from tsfresh import select_features

import warnings

started = datetime.now()
initial_time = started
step_count = 0

cluster_conn = mysql.connector.connect(
    host='aiserver.local',         
    user='root',     
    password='19890617',  
    database='Clustering'   
)
cluster_cursor = cluster_conn.cursor(dictionary=True)
cluster_engine = create_engine('mysql+mysqlconnector://root:19890617@aiserver.local/Clustering')

data_conn = mysql.connector.connect(
    host='aiserver.local',         
    user='root',      
    password='19890617',  
    database='HistoricalData'   
)
data_cursor = data_conn.cursor(dictionary=True)
data_engine = create_engine('mysql+mysqlconnector://root:19890617@aiserver.local/HistoricalData')

# Databricks connection details
databricks_server_hostname = "dbc-1240ceb0-fb8c.cloud.databricks.com"
http_path = "sql/protocolv1/o/1817514056689607/1018-091119-r6bcyh4a"
access_token = "dapiff0565c897d05ba3ea3bd8303668a7e2"

# Establish a connection to Databricks
#conn_db = sql.connect(
#    server_hostname=databricks_server_hostname,
#    http_path=http_path,
#    access_token=access_token,
#    timeout=30
#)
def from_databricks(conn_db,base_query, chunk_size=5000):
    offset = 0
    chunks = []

    while True:
        query = f"{base_query} LIMIT {chunk_size} OFFSET {offset}"
        chunk_df = pd.read_sql_query(query, conn_db)

        if chunk_df.empty:
            break

        chunks.append(chunk_df)
        offset += chunk_size

    return  pd.concat(chunks, ignore_index=True)


def to_databricks(conn_db, table_name, data_to_insert, chunk_size=5000):
    # Mapping Pandas dtypes to SQL data types
    dtype_mapping = {
        "int64": "INT",
        "float64": "FLOAT",
        "object": "STRING",
        "bool": "BOOLEAN",
        "datetime64[ns]": "TIMESTAMP"
    }
    column_definitions = []
    for column_name, dtype in data_to_insert.dtypes.items():
        sql_type = dtype_mapping.get(str(dtype), "STRING")  # Default to STRING if type is not mapped
        column_definitions.append(f"{column_name} {sql_type}")

    create_table_query = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(column_definitions)})"

    with conn_db.cursor() as cursor:
        cursor.execute(create_table_query)

    try:
        for i in range(0, len(data_to_insert), chunk_size):
            chunk = data_to_insert.iloc[i:i + chunk_size]
            values = ", ".join(
                f"({', '.join(repr(val) for val in row)})" for row in chunk.to_numpy()
            )
            insert_query = f"INSERT INTO {table_name} ({', '.join(df.columns)}) VALUES {values}"
   
            with conn_db.cursor() as cursor:
                cursor.execute(insert_query)

        conn_db.commit()
        result = "Success"

    except Exception as e:
        conn_db.rollback()
        result = f"Error: {e}"

    return result
#============================================================================

initial_time = datetime.now()

# Suppress all warnings
warnings.filterwarnings("ignore")

key_column = "unique_id"


# Get the OS name
os_name = platform.system()
machine_name = platform.node().lower()

def commitmany(connection, query, data, chunk_size):
    for i in range(0, len(data), chunk_size):
        chunk = data[i:i + chunk_size]
        data_cursor.executemany(query, chunk)
        connection.commit()

            
def clean_currency(value):
    # Remove dollar signs and commas
    value = str(value)
    value = value.replace('$', '')
    value = value.replace(',', '')
    # Handle negative numbers represented by parentheses
    if '(' in value and ')' in value:
        value = '-' + value.replace('(', '').replace(')', '')

    try:
        value = float(value)
    except (ValueError, TypeError):
        value = float(0.0)

    return value

def duration_calculation(description):
    start_time = started.strftime("%Y/%m/%d %H:%M")
    
    ended = datetime.now()
    end_time = ended.strftime("%Y/%m/%d %H:%M")

    time_difference = ended - started

    # Get the difference in hours and minutes
    minutes, seconds = divmod(time_difference.seconds, 60)
    duration = f"{minutes:02}:{seconds:02}"
    print(description, end_time, duration)

    data = {
        'run_id': run_id,
        'machine': machine_name,
        'step': step_count,
        'description': description,
        'start': start_time,
        'end': end_time,
        'duration': duration
    }
    df = pd.DataFrame([data])
    df.to_sql('performance', con=cluster_engine, if_exists='append', index=False, chunksize=5000)
    
    return ended, int(step_count + 1)



# Load your dataset
##config_file = 'config.csv'
#config_df = pd.read_csv(config_file)
#config_df = config_df[config_df['machine'] == machine_name]

#cluster_cursor.execute("SELECT * FROM configuration")   
#config_rows = cluster_cursor.fetchall()
#config_df = pd.DataFrame(config_rows)
#print(config_df.head(5))
#result = to_databricks(conn_db=databricks_engine, table_name="configuration", data_to_insert= config_df)

#config_row = config_df.iloc[0]
cluster_cursor.execute("SELECT * FROM configuration where machine = %s", (machine_name,))   
config_row = cluster_cursor.fetchone()
#print(config_row)

dataset = str(config_row['dataset'])
demand_item = str(config_row['demand_item'])
demand_point = str(config_row['demand_point'])
target_column = str(config_row['target_column'])
date_column = str(config_row['date_column'])
time_bucket = str(config_row['time_bucket'])
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

config_df = pd.DataFrame([config_row])
run_id = [datetime.now().strftime("%Y%m%d_%H%M"), dataset, demand_item, demand_point, target_column, time_bucket]
run_id = " | ".join(run_id)
run_id = run_id[:80] if len(run_id) > 80 else run_id
config_df['run_id'] = run_id
#print(config_df.head(1))
config_df.to_sql('run_details', con=cluster_engine, if_exists='append', index=False, chunksize=50000)

if os_name == 'Linux':
    data_folder = '/home/trevor/Insync/trevor.miles@noodle.ai/OneDrive Biz/Product Design/Demand Data/' + dataset + '/'
    njobs = psutil.cpu_count() - 2

elif os_name == 'Darwin':
    data_folder = 'C:\\Users\\miles\\OneDrive - Noodle Analytics\\Product Design\\Demand Data\\' + dataset + '\\'
    njobs = psutil.cpu_count() - 2  

elif os_name == 'Windows':
    data_folder = 'C:\\Users\\miles\\OneDrive - Noodle Analytics\\Product Design\\Demand Data\\' + dataset + '\\'
    njobs = 1
 
started, step_count = duration_calculation("Initialization")

#chunk_size = 100000
#chunks = []
categorical_driver_df = pd.DataFrame()
numeric_driver_df = pd.DataFrame()
numeric_columns = []
categorical_columns = []

if dataset == 'Honeywell':
    file_path = data_folder + 'weekly_shipment_data.csv'
    df = pd.read_csv(file_path)
    df = df.drop(["load timestamp"], axis=1)
    df.columns = ['product_id', 'site_id', 'quantity', 'ship_date']
    #print(df.head(10))
    #print(df.shape)
    #print(df.columns)

    file_path = data_folder + 'std_unit_cost_df.csv'
    prod_hierarchy_df = pd.read_csv(file_path)
    prod_hierarchy_df.columns = [
        "product_id",
        "site_id",
        "std_cost",
        "std_cost_edit",
        "std_cost_new",
        "prod_hier_01",
        "prod_hier_02",
        "prod_hier_03",
        "prod_hier_04",
        "prod_hier_05",
        "prod_hier_06",
        "abc_xyz"
    ]
    #prod_hierarchy_df['prod_hier_01'] = prod_hierarchy_df['prod_hier_01'].str.split(" - ").str[0]
    #prod_hierarchy_df['prod_hier_02'] = prod_hierarchy_df['prod_hier_02'].str.split(" - ").str[0]
    #prod_hierarchy_df['prod_hier_03'] = prod_hierarchy_df['prod_hier_03'].str.split(" - ").str[0]
    #prod_hierarchy_df['prod_hier_04'] = prod_hierarchy_df['prod_hier_04'].str.split(" - ").str[0]
    #prod_hierarchy_df['prod_hier_05'] = prod_hierarchy_df['prod_hier_05'].str.split(" - ").str[0]
    #prod_hierarchy_df['prod_hier_06'] = prod_hierarchy_df['prod_hier_06'].str.split(" - ").str[0]

    prod_hierarchy_df = prod_hierarchy_df.set_index(['product_id', 'site_id'])

    df = df.merge(prod_hierarchy_df, 
              left_on=['product_id', 'site_id'], 
              right_index=True,
              how='left')


    #print(df.head(10))

    df["ship_date"] = pd.to_datetime(df["ship_date"], infer_datetime_format=True)
    df["site_id"] = df["site_id"].astype(str)
    df["product_id"] = df["product_id"].astype(str)
    df["std_cost"] = df["std_cost"].apply(clean_currency)
    df["std_cost_edit"] = df["std_cost_edit"].apply(clean_currency)
    df["std_cost_new"] = df["std_cost_new"].apply(clean_currency)
    df["quantity"] = df["quantity"].apply(clean_currency)

    #df["dollar"] = df["quantity"] * df["std_cost_new"]

    df.drop(["std_cost", "std_cost_edit", "std_cost_new"], axis=1, inplace=True)
    #print(df.columns)
    
    df[key_column] = df[demand_item] + "|" + df[demand_point]
    df.drop([demand_item, demand_point], axis=1, inplace=True)

    #print(df.head(10))

    if ignore_numeric_columns:
        numeric_columns = []
    elif target_column == 'dollar':
        numeric_columns = ['quantity']
    elif target_column == 'quantity':
        numeric_columns = ['dollar']

    if demand_item == 'product_id':
        item_columns = ['prod_hier_01', 'prod_hier_02', 'prod_hier_03', 'prod_hier_04', 'prod_hier_05', 'prod_hier_06', 'abc_xyz']

    elif demand_item == 'prod_hier_01':
        item_columns = ['product_id', 'prod_hier_02', 'prod_hier_03', 'prod_hier_04', 'prod_hier_05', 'prod_hier_06', 'abc_xyz']

    elif demand_item == 'prod_hier_02':
        item_columns = ['product_id', 'prod_hier_01', 'prod_hier_03', 'prod_hier_04', 'prod_hier_05', 'prod_hier_06', 'abc_xyz']

    elif demand_item == 'prod_hier_03':
        item_columns = ['product_id', 'prod_hier_01', 'prod_hier_02', 'prod_hier_04', 'prod_hier_05', 'prod_hier_06', 'abc_xyz']

    elif demand_item == 'prod_hier_04':
        item_columns = ['product_id', 'prod_hier_01', 'prod_hier_02', 'prod_hier_03', 'prod_hier_05', 'prod_hier_06', 'abc_xyz']

    elif demand_item == 'prod_hier_05':
        item_columns = ['product_id', 'prod_hier_01', 'prod_hier_02', 'prod_hier_03', 'prod_hier_04', 'prod_hier_06', 'abc_xyz']

    elif demand_item == 'prod_hier_06':
        item_columns = ['product_id', 'prod_hier_01', 'prod_hier_02', 'prod_hier_03', 'prod_hier_04', 'prod_hier_05', 'abc_xyz']

    elif demand_item == 'abc_xyz':
        item_columns = ['product_id', 'prod_hier_01', 'prod_hier_02', 'prod_hier_03', 'prod_hier_04', 'prod_hier_05', 'prod_hier_06']

    customer_columns = []
    categorical_columns = item_columns + customer_columns + [
        ]


elif dataset == 'USFoods':
    file_path = data_folder + 'UPC_ID.csv'
    df = pd.read_csv(file_path)

    df = df.dropna(subset=['Item Order Date'])

    # Rename columns for clarity (if necessary)
    #Item Order Date,Delivery Date,Inv Date,Inv .,Order .,Load .,PO .,Customer .,Customer Name,City,ST,Zip,Country,Channel,Segment,Tier,Buying Group,DC,Load Location Name,DSM,CSR/CDR,Corp ID,Supplier Name,PL ID,Product Line,Item Category Description,Item Storage Description,Dot .,MFG .,Item Desc,UPC.,Customer Item Number,Item Shelf Life,Stock Status,Hub Location Number,Hub Stock Status,Ordered,Received,Dollars,LBS,UPC_ID

    columns_to_keep = [
        'Item Order Date',
        'Delivery Date',
        #'Inv Date',
        #'Inv .,
        #'Order .',
        #'Load .,
        #'PO .',
        'Customer .',
        #'Customer Name',
        #'City',
        'ST',
        'Zip',
        #'Country',
        'Channel',
        'Segment',
        'Tier',
        'Buying Group',
        'DC',
        #'Load Location Name',
        #'DSM',
        #'CSR/CDR',
        #'Corp ID',
        #'Supplier Name',
        'PL ID',
        #'Product Line',
        'Item Category Description',
        #'Item Storage Description',
        'Dot .',
        #'MFG .',
        #'Item Desc',
        'UPC.',
        #'Customer Item Number',
        'Item Shelf Life',
        'Stock Status',
        'Hub Location Number',
        'Hub Stock Status',
        'Ordered',
        'Received',
        'Dollars',
        'LBS',
        'UPC_ID' 
        ]
    df = df[columns_to_keep]


    df.columns = ['item_order_date', 'delivery_date', 'customer', 'state', 'zip', 'channel', 'segment','tier','buying_group','dc','prod_line','item_category','dot_number','upc_no','shelf_life','stock_status','hub_location','hub_stock_status','ordered','received','dollar','lbs', 'upc']
    df["item_order_date"] = pd.to_datetime(df["item_order_date"])
    df["delivery_date"] = pd.to_datetime(df["delivery_date"])
    df["customer"] = df["customer"].astype(str)
    df["state"] = df["state"].astype(str)
    df["zip"] = df["zip"].astype(str)
    df["channel"] = df["channel"].astype(str)
    df["segment"] = df["segment"].astype(str)
    df["tier"] = df["tier"].astype(str)
    df["buying_group"] = df["buying_group"].astype(str)
    df["dc"] = df["dc"].astype(str)
    df["prod_line"] = df["prod_line"].astype(str)
    df["item_category"] = df["item_category"].astype(str)
    df["upc_no"] = df["upc_no"].astype(str)
    df["shelf_life"] = df["shelf_life"].fillna(-1).astype(int)
    df["stock_status"] = df["stock_status"].astype(str)
    df["hub_location"] = df["hub_location"].astype(str)
    df["hub_stock_status"] = df["hub_stock_status"].astype(str)
    df["dollar"] = df["dollar"].apply(clean_currency)
    df["lbs"] = df["lbs"].apply(clean_currency)
    df['ordered'] = df['ordered'].apply(clean_currency)
    df['received'] = df['received'].apply(clean_currency)
    df["OTIF"] = np.where(df["ordered"] > 0, df["received"] / df["ordered"], 0)
    df["OTIF"].fillna(0, inplace=True)

    #df['dc'], df_dc = map_categories(df, 'dc')
    #df['item_category'], df_item_category = map_categories(df, 'item_category')
    #df['stock_status'], df_stock_status = map_categories(df, 'stock_status')    
    #df['hub_stock_status'], df_hub_stock_status = map_categories(df, 'hub_stock_status')
  
    df[key_column] = df[demand_item] + "|" + df[demand_point]
    df.drop([demand_item, demand_point], axis=1, inplace=True)
    
    df = df[df[target_column] >= 0]
    
    if ignore_numeric_columns:
        numeric_columns = []
    elif target_column == 'dollar':
        numeric_columns = ['ordered', 'received','lbs', 'OTIF']
    elif target_column == 'lbs':
        numeric_columns = ['ordered', 'received','dollar', 'OTIF']
    elif target_column == 'ordered':
        numeric_columns = ['received', 'dollar', 'lbs', 'OTIF']
    elif target_column == 'received':
        numeric_columns = ['ordered', 'dollar', 'lbs', 'OTIF']

    if demand_item == 'corp_id':
        item_columns = ['prod_line', 'item_category']

    elif demand_item == 'dot_number':    
        item_columns = ['prod_line', 'item_category']

    elif demand_item == 'upc':    
        item_columns = ['prod_line', 'item_category']

    elif demand_item == 'prod_line':    
        item_columns = ['item_category']

    elif demand_item == 'item_category':    
        item_columns = ['prod_line']

    if demand_point == 'customer':   
        customer_columns = ['state', 'zip', 'channel', 'segment', 'tier', 'buying_group', 'dc']
 
    elif demand_point == 'state':   
        customer_columns = ['customer', 'zip', 'channel','segment', 'tier', 'buying_group', 'dc']
 
    elif demand_point == 'zip':   
        customer_columns = ['customer', 'state', 'channel','segment', 'tier', 'buying_group', 'dc']
   
    elif demand_point == 'channel':   
        customer_columns = ['customer', 'state', 'zip', 'segment', 'tier', 'buying_group', 'dc']

    elif demand_point == 'segment':   
        customer_columns = ['customer', 'state', 'zip', 'channel', 'tier', 'buying_group', 'dc']
   
    elif demand_point == 'tier':   
        customer_columns = ['customer', 'state', 'zip', 'channel', 'segment', 'buying_group', 'dc']
   
    elif demand_point == 'buying_group':   
        customer_columns = ['customer', 'state', 'zip', 'channel', 'segment', 'tier', 'dc']
  
    elif demand_point == 'dc':   
        customer_columns = ['customer', 'state', 'zip', 'channel', 'segment', 'tier', 'buying_group']
   

    categorical_columns = item_columns + customer_columns + [
        'shelf_life',
        'stock_status',
        'hub_location',
        'hub_stock_status',
        ]


mapping_dict = {}
for col in categorical_columns:
    le = LabelEncoder()
    df[col + '_encoded'] = le.fit_transform(df[col])
    
    mapping_dict[col] = pd.DataFrame({
        'unique_id': df['unique_id'],
        'original_category': df[col],
        'encoded_value': df[col + '_encoded']
    }).drop_duplicates()

# Modify the original DataFrame
for col in categorical_columns:
    df[col] = df[col + '_encoded']
    df = df.drop(columns=[col + '_encoded'])

df['cluster'] = -1
sorted_columns = [key_column, 'cluster'] + categorical_columns + [date_column, target_column] + numeric_columns
df = df[sorted_columns]




started, step_count = duration_calculation("Data Load")

# number of minimum observations to run STL
if time_bucket == "D":
    minimum_observations_threshold = 30
    period = 365
    trend=367
    seasonal=367
elif time_bucket == "W":
    minimum_observations_threshold = 13
    period = 52
    trend=53
    seasonal=53
elif time_bucket == "ME":
    minimum_observations_threshold = 12
    period = 12
    trend=13
    seasonal=13

if number_of_items_analyzed > 0:
    total_quantity = df.groupby(key_column)[target_column].sum()
    top_items = total_quantity.nlargest(number_of_items_analyzed).index
    df = df[df[key_column].isin(top_items)]

time_bound = "M" if time_bucket == "ME" else "W"

def prune_to_whole_periods(group):
    start_of_first_full_period = group[date_column].dt.to_period(time_bound).min().start_time
    end_of_last_full_period = group[date_column].dt.to_period(time_bound).max().end_time
    return group[(group[date_column] >= start_of_first_full_period) & (group[date_column] <= end_of_last_full_period)]

#df = df.groupby(key_column, group_keys=False).apply(prune_to_whole_periods)
df = df.groupby(key_column).filter(lambda x: x[date_column].nunique() >= minimum_observations_threshold)

original_df = df.copy()

cluster_analysis_columns = [
    key_column, 
    date_column, 
    target_column
    ] + numeric_columns
df = df[cluster_analysis_columns]


#last_dates = df.groupby(key_column)[date_column].max()
#print(last_dates)
#distribution_table = df[date_column].value_counts(normalize=True).reset_index()
#distribution_table.columns = ['Category', 'Proportion']
#print(distribution_table.head(20))
#earliest_last_date = last_dates.min()
#df = df[df[date_column] <= earliest_last_date]

df[date_column] = pd.to_datetime(df[date_column])
df.set_index(date_column, inplace=True)
df_resampled = df.groupby(key_column).resample(time_bucket).sum()
df_resampled.drop(columns=[key_column], inplace=True, errors='ignore')
df = df_resampled.reset_index()

df_total = df.groupby(key_column)[target_column].sum().reset_index()
df_total = df_total.sort_values(by=target_column, ascending=False)
#print(df_total.head(10))
df.reset_index(inplace=True)
df.drop(columns=['index'], inplace=True)
#print(df.head(10))


started, step_count = duration_calculation("Time Bucketing")

##################################################################
# Define characteristics to be extracted

general_fc_parameters = {
    'mean': None,
    'median': None,
    'length': None,
    'standard_deviation': None,
    'root_mean_square': None,
    'quantile': [
        {'q': 0.1}, 
        {'q': 0.5}, 
        {'q': 0.9}]}

stationarity_fc_parameters = {
    'augmented_dickey_fuller': [
        {'attr': 'teststat'}, 
        {'attr': 'pvalue'}, 
        {'attr': 'usedlag'}]}

sporadic_fc_parameters = {
    'agg_autocorrelation': [
        {'f_agg': 'mean', 'maxlag': 40}, 
        {'f_agg': 'median', 'maxlag': 40}, 
        {'f_agg': 'var', 'maxlag': 40}],
    'percentage_of_reoccurring_values_to_all_values': None,
    'count_above': [{'t': 0}],
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

if time_bucket == 'D':
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
    trend_fc_parameters = trend_fc_parameters | {
        'agg_linear_trend': [
            {'attr': 'slope', 'chunk_len':90, 'f_agg':'mean'}, 
            #{'attr': 'slope', 'chunk_len':90, 'f_agg':'median'}, 
            {'attr': 'slope', 'chunk_len':90, 'f_agg':'max'}, 
            {'attr': 'slope', 'chunk_len':90, 'f_agg':'min'}]}
    
elif time_bucket == 'W':
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
    trend_fc_parameters = trend_fc_parameters | {
        'agg_linear_trend': [
            {'attr': 'slope', 'chunk_len':13, 'f_agg':'mean'}, 
            #{'attr': 'slope', 'chunk_len':13, 'f_agg':'median'}, 
            {'attr': 'slope', 'chunk_len':13, 'f_agg':'max'}, 
            {'attr': 'slope', 'chunk_len':13, 'f_agg':'min'}]}

elif time_bucket == 'ME':
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
    trend_fc_parameters = trend_fc_parameters | {
            'agg_linear_trend': [
                {'attr': 'slope', 'chunk_len':3, 'f_agg':'mean'}, 
                #{'attr': 'slope', 'chunk_len':3, 'f_agg':'median'}, 
                {'attr': 'slope', 'chunk_len':3, 'f_agg':'max'}, 
                {'attr': 'slope', 'chunk_len':3, 'f_agg':'min'}]}

##################################################################
# Extract features using the specified configuration
if characteristics_creation_method == 'tsfresh' or characteristics_creation_method == 'both':
    custom_fc_parameters = general_fc_parameters | stationarity_fc_parameters | sporadic_fc_parameters | seasonality_fc_parameters | trend_fc_parameters | smoothness_fc_parameters
    if len(numeric_columns) > 1: 
        all_numeric_columns = [target_column] + numeric_columns
        df_melted = df.melt(id_vars=[key_column, date_column], value_vars=all_numeric_columns,
                    var_name='kind', value_name='value')

        # Extract features for all numeric columns
        features = extract_features(df_melted, 
                                    column_id=key_column, 
                                    column_sort=date_column, 
                                    column_kind='kind', 
                                    column_value='value',
                                    n_jobs=njobs)

        #features.to_csv(data_folder + "features.csv")
        #scaler = StandardScaler()
        #scaled_features = scaler.fit_transform(features)
        #scaled_features_df = pd.DataFrame(scaled_features, columns=features.columns, index=features.index)
        #scaled_features_df.to_csv(data_folder + "scaled_features.csv")

    else:
        features = extract_features(df, 
                                    column_id=key_column, 
                                    column_sort=date_column, 
                                    column_value=target_column, 
                                    default_fc_parameters= custom_fc_parameters,
                                    n_jobs=njobs)

    impute(features)

    features = pd.DataFrame(features)
    features.reset_index(inplace=True)
    features.rename(columns={'index': key_column}, inplace=True)


    started, step_count = duration_calculation("Characteristic Extraction - tsfresh")


class DemandPatternClassifier:
    # define thresholds for trend and seasonality binning
    cv_sq_threshold = 0.49
    adi_threshold = 1.32

    # number of minimum observations to run STL
    minimum_observations_threshold = 12

    def __init__(
        self,
        date_column: str,
        target_column: str,
        key_column: str,
        period: int = 12,
        trend: int = 13,
        seasonal: int = 13,
):
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
        series_to_decompose = [
        self._get_series_to_decompose(temp, key)
            for key in data[self.key_column].unique()
        ]

        # Decompose the series
        decomposed_series = [
            self._stl_decompose_single_series(key, series, period, trend, seasonal)
            for key, series in series_to_decompose
        ]

        return pd.concat(decomposed_series, ignore_index=True)

    def _org_stl_decompose(self, data: pd.DataFrame) -> pd.DataFrame:
        temp = data[[self.key_column, self.date_column, self.target_column]].copy()
        temp = temp.set_index(self.date_column)
        with Pool() as pool:
            series_to_decompose = pool.map(
                partial(
                    self._get_series_to_decompose,
                    temp,
                ),
                [key for key in data[self.key_column].unique()],
                chunksize=64,
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

    def _get_series_to_decompose(
        self,
        temp,
        key
    ):
        return key, temp[temp[self.key_column].isin([key])][self.target_column]

    def _stl_decompose_single_series(
        self,
        key: str,
        series: pd.Series,
        period: int = 12,
        trend: int = 13,
        seasonal: int = 13
    ) -> pd.DataFrame:
        # fit the model
        trend = self._make_odd(trend)
        stl = STL(series, period=period, seasonal=seasonal, trend=trend)
        result = stl.fit()

        # Construct TS Decomposition DataFrame
        seasonal_adjusted = series - result.seasonal
        result_df = pd.DataFrame(
            {
                self.key_column: key,
                self.target_column: series,
                "seasonal": result.seasonal,
                "seasadj": seasonal_adjusted,
                "trend": result.trend,
                "remainder": seasonal_adjusted - result.trend
            }
        ).reset_index().rename(columns={"index": self.date_column})

        return result_df

    def _assign_labels(self, data: pd.DataFrame, stl: pd.DataFrame) -> pd.DataFrame:
        # add trend & seasonality to STL remainder
        stl["remainder_plus_trend"] = stl["remainder"] + stl["trend"]
        stl["remainder_plus_seasonal"] = stl["remainder"] + stl["seasonal"]

        # create new columns based on aggregation
        stl_agg = stl.groupby(self.key_column).agg(
            n_demand_buckets=(self.target_column, "size"),
            n_non_zero_buckets=(self.target_column, self._count_non_zero),
            mean_cv=(self.target_column, self._calculate_mean_non_zero),
            sd_cv=(self.target_column, self._calculate_std_non_zero),
            total_orders=(self.target_column, "sum"),
            var_remainder=("remainder", self._calculate_var),
            var_remainder_plus_trend=("remainder_plus_trend", self._calculate_var),
            var_remainder_plus_seasonal=("remainder_plus_seasonal", self._calculate_var),
        ).reset_index()

        # find parameters necessary to bin into seasonl and trend components
        stl_agg["seasonal_strength"] = np.clip(1 - stl_agg["var_remainder"] / stl_agg["var_remainder_plus_seasonal"], 0, 1)
        stl_agg["trend_strength"] = np.clip(1 - stl_agg["var_remainder"] / stl_agg["var_remainder_plus_trend"], 0, 1)
        stl_agg["adi"] = stl_agg["n_demand_buckets"] / np.where(
            stl_agg["n_non_zero_buckets"] == 0, np.nan, stl_agg["n_non_zero_buckets"]
        )
        stl_agg["cv"] = stl_agg["sd_cv"] / np.where(stl_agg["mean_cv"] == 0, np.nan, stl_agg["mean_cv"])
        stl_agg["cv_sq"] = stl_agg["cv"] ** 2
        stl_agg["seasonal_bin"] = np.where(stl_agg["seasonal_strength"] > 0.5, "high_seas", "low_seas")
        stl_agg["trend_bin"] = np.where(stl_agg["trend_strength"] > 0.5, "high_local_trend", "low_local_trend")

        # create conditions on which demand-class will be assigned
        conditions = {
            "smooth": (stl_agg["adi"] < self.adi_threshold) & (stl_agg["cv_sq"] < self.cv_sq_threshold),
            "erratic": (stl_agg["adi"] < self.adi_threshold) & (stl_agg["cv_sq"] >= self.cv_sq_threshold),
            "intermittent": (stl_agg["adi"] >= self.adi_threshold) & (stl_agg["cv_sq"] < self.cv_sq_threshold),
            "lumpy": (stl_agg["adi"] >= self.adi_threshold) & (stl_agg["cv_sq"] >= self.cv_sq_threshold),
            "single demand bucket": (stl_agg["n_demand_buckets"] == 1)
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
    classifier = DemandPatternClassifier(
        date_column=date_column,
        target_column=target_column,
        key_column=key_column,
        period=period,
        trend=trend,
        seasonal=seasonal,
    )

    # Classify the data
    classified_data = classifier.classify(df)

    # Select the specific columns you're interested in
    df_selected = classified_data[[key_column, 'seasonal_strength', 'trend_strength', 'adi', 'cv_sq', 'demand_pattern_label']]


    # Drop duplicates based on unique_id (assuming that these fields are unique for each unique_id)
    df_classification = df_selected.drop_duplicates(subset=[key_column])
    df_classification['demand_class'] = df_classification['demand_pattern_label'].astype('category').cat.codes
    df_classification.drop(columns=['demand_pattern_label'], axis=1, inplace=True)
    

    started, step_count = duration_calculation("Characteristic Extraction - Classifier")


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
characteristics_df[['demand_item', 'demand_point']] = characteristics_df[key_column].str.split("|", expand=True)
characteristics_df.drop(columns=[key_column], axis=1, inplace=True)
df_melted = pd.melt(characteristics_df, id_vars=['run_id', 'demand_item', 'demand_point'], var_name='characteristic', value_name='value')
#df_melted.to_sql('characteristics', con=cluster_engine, if_exists='append', index=False, chunksize=50000)

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
        distances = cdist(small_cluster_points.drop(columns=['cluster']).values,
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
def find_optimal_clusters(df, key_column, min_clusters =10, max_clusters = 20, cluster_selection_method = 'KMeans'):
    # Normalize the features
    unique_ids = df[key_column].unique()
    features_df = pd.DataFrame(df.drop(columns=[key_column]))

    scaler = StandardScaler()
    scaled_features_df = scaler.fit_transform(features_df)
    
    if cluster_selection_method == 'KMeans':
        inertia = []
        silhouette_scores = []
        davies_bouldin_scores = []

        if max_clusters > min_clusters:
            K = range(min_clusters, max_clusters)  # Test clusters from 2 to 10 (1 is not meaningful in clustering)
    
            for k in K:
                kmeans = KMeans(n_clusters=k, random_state=42)
                kmeans.fit(scaled_features_df)
                inertia.append(kmeans.inertia_)
                silhouette_scores.append(silhouette_score(scaled_features_df, kmeans.labels_))
                davies_bouldin_scores.append(davies_bouldin_score(scaled_features_df, kmeans.labels_))

            # Displaying the scores
            scores_df = pd.DataFrame({
                'Number of Clusters': K,
                'Inertia': inertia,
                'Silhouette Score': silhouette_scores,
                'Davies-Bouldin Score': davies_bouldin_scores
            })
    
            # Suggesting the optimal number of clusters based on each method
            optimal_k_elbow = K[np.argmin(np.diff(np.diff(inertia)))]
            if optimal_k_elbow < min_clusters:
                optimal_k_elbow = optimal_k_elbow + int(min_clusters)  # A heuristic approach for Elbow
            optimal_k_silhouette = K[np.argmax(silhouette_scores)]
            optimal_k_davies = K[np.argmin(davies_bouldin_scores)]
            num_clusters = max(optimal_k_elbow, optimal_k_silhouette, optimal_k_davies)

        else:
            num_clusters = 16


        # Run KMeans with each optimal k and assign clusters to unique_ids
        kmeans = KMeans(n_clusters=num_clusters, random_state=42)
        labels = kmeans.fit_predict(scaled_features_df)
        labels = ensure_min_cluster_size(features_df, labels, min_cluster_size)

        cluster_centers_df = find_cluster_centroids(features_df, labels)
        cluster_df = pd.DataFrame({key_column: df[key_column], 'cluster': labels})

    elif cluster_selection_method == 'DBSCAN':
        clusterer = hdbscan.HDBSCAN(min_cluster_size,core_dist_n_jobs=njobs)
        labels = clusterer.fit_predict(scaled_features_df)
     
        cluster_centers_df = find_cluster_centroids(features_df, labels)
        cluster_df = pd.DataFrame({key_column: unique_ids, 'cluster': labels})

    elif cluster_selection_method == 'AgglomerativeClustering':
        elbow_scores = []
        silhouette_scores = []
        davies_bouldin_scores = []

        if max_clusters > min_clusters:
            N = range(min_clusters, max_clusters)  # Test clusters from 2 to 10 (1 is not meaningful in clustering)
            for n in N:
                clusterer = AgglomerativeClustering(n_clusters=n, linkage='ward')
                labels = clusterer.fit_predict(scaled_features_df)
                elbow_scores.append(calculate_wcss(scaled_features_df, labels, n))
                silhouette_scores.append(silhouette_score(scaled_features_df, clusterer.labels_))
                davies_bouldin_scores.append(davies_bouldin_score(scaled_features_df, clusterer.labels_))
    
            # Suggesting the optimal number of clusters based on each method
            optimal_n_elbow = N[np.argmin(np.diff(np.diff(elbow_scores)))]
            if optimal_n_elbow < min_clusters:
                optimal_n_elbow = optimal_n_elbow + int(min_clusters)  # A heuristic approach for Elbow
            optimal_n_silhouette = N[np.argmax(silhouette_scores)]
            optimal_n_davies = N[np.argmin(davies_bouldin_scores)]
            num_clusters = max(optimal_n_elbow, optimal_n_silhouette, optimal_n_davies)

        else:
            num_clusters = 16

        clusterer = AgglomerativeClustering(n_clusters=num_clusters, linkage='ward')
        labels = clusterer.fit_predict(scaled_features_df)
        labels = ensure_min_cluster_size(features_df, labels, min_cluster_size)

        cluster_centers_df = find_cluster_centroids(features_df, labels)
        cluster_df = pd.DataFrame({key_column: df[key_column], 'cluster': labels})

    elif cluster_selection_method == 'OPTICS':
        clusterer = OPTICS(min_samples=2)
        labels = clusterer.fit_predict(scaled_features_df)

        cluster_centers = scaler.inverse_transform(clusterer.cluster_centers_)    
        cluster_centers_df = pd.DataFrame(cluster_centers, columns=features_df.columns)

        labels = ensure_min_cluster_size(features_df, cluster_centers_df, labels, min_size=min_cluster_size)
        cluster_df = pd.DataFrame({key_column: unique_ids, 'cluster': labels})    
    
    elif cluster_selection_method == 'Birch':
        clusterer = Birch(threshold=0.01, n_clusters=16)
        labels = clusterer.fit_predict(scaled_features_df)
        
        cluster_centers = scaler.inverse_transform(clusterer.cluster_centers_)    
        cluster_centers_df = pd.DataFrame(cluster_centers, columns=features_df.columns)

        labels = ensure_min_cluster_size(features_df, cluster_centers_df, labels, min_size=min_cluster_size)
        cluster_df = pd.DataFrame({key_column: unique_ids, 'cluster': labels})    

    elif cluster_selection_method == 'GaussianMixture':
        clusterer = GaussianMixture(n_components=16)
        labels = clusterer.fit_predict(scaled_features_df)
        
        cluster_centers = scaler.inverse_transform(cluster_centers = clusterer.means_)    
        cluster_centers_df = pd.DataFrame(cluster_centers, columns=features_df.columns)

        labels = ensure_min_cluster_size(features_df, cluster_centers_df, labels, min_size=min_cluster_size)
        cluster_df = pd.DataFrame({key_column: unique_ids, 'cluster': labels})    

    elif cluster_selection_method == 'MeanShift':
        clusterer = MeanShift(bandwidth=0.5)
        labels = clusterer.fit_predict(scaled_features_df)

        cluster_centers = scaler.inverse_transform(clusterer.cluster_centers_)    
        cluster_centers_df = pd.DataFrame(cluster_centers, columns=features_df.columns)

        labels = ensure_min_cluster_size(features_df, cluster_centers_df, labels, min_size=min_cluster_size)
        cluster_df = pd.DataFrame({key_column: unique_ids, 'cluster': labels})    

    elif cluster_selection_method == 'SpectralClustering':
        clusterer = SpectralClustering(n_clusters=16)
        labels = clusterer.fit_predict(scaled_features_df)
        cluster_centers = clusterer.cluster_centers_
        cluster_centers_ = scaler.inverse_transform(cluster_centers)    
        cluster_centers_df = pd.DataFrame(cluster_centers_)  # cluster centers

        labels = ensure_min_cluster_size(features_df, cluster_centers_df, labels, min_size=min_cluster_size)
        cluster_df = pd.DataFrame({key_column: unique_ids, 'cluster': labels})    

    elif cluster_selection_method == 'AffinityPropagation':
        clusterer = AffinityPropagation(damping=0.5)
        labels = clusterer.fit_predict(scaled_features_df)
        cluster_centers = clusterer.cluster_centers_
        cluster_centers_ = scaler.inverse_transform(cluster_centers)    
        cluster_centers_df = pd.DataFrame(cluster_centers_)  # cluster centers
 
        labels = ensure_min_cluster_size(features_df, cluster_centers_df, labels, min_size=min_cluster_size)
        cluster_df = pd.DataFrame({key_column: unique_ids, 'cluster': labels})    

    return cluster_df, cluster_centers_df

# Run the function to find the optimal number of clusters and get the cluster assignments


mode_df = original_df.groupby(key_column)[target_column].apply(lambda x: x.mode().iloc[0] if not x.mode().empty else None)
mode_df = mode_df.reset_index()  # Reset index to turn key_column back into a column
mode_df.columns = [key_column, target_column + "__mode"]  # Rename columns appropriately
summary_stats = pd.merge(summary_stats, mode_df, on=key_column, how="left")  # Use 'how="left"' if you want all rows from summary_stats

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
    mode_value = target_column + '__mode'
    stationarity = target_column + '__augmented_dickey_fuller__p_value' 
    smoothness = target_column + '__cid_ce__normalize_True'
    seasonality = target_column + '__spkt_welch_density__coeff_5'
    sporadic = target_column + '__range_count__max_1__min_0'
    trend = target_column + '__linear_trend__attr_"slope"'
    important_features = [mode_value, smoothness, stationarity, seasonality, sporadic, trend]
    axis_labels = ['mode', 'smoothness', 'stationarity', 'seasonality', 'sporadic', 'trend']

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
        scatter = ax_main.scatter(features_df.iloc[:, x_index], features_df.iloc[:, y_index],
                                c=labels, cmap='viridis', s=5, alpha=0.7)
        
        colors = scatter.cmap(scatter.norm(unique_labels))  # Map colors from clusters

        # Plot cluster centroids
        for i, label in enumerate(unique_labels):
            ax_main.scatter(
                feature_centers_df.iloc[label - 1, x_index],  # Adjust for zero-based indexing if needed
                feature_centers_df.iloc[label - 1, y_index],
                edgecolor=colors[i], facecolor='none',
                marker='X', s=25, linewidth=2, label=f'Centroid {label}'
            )

        # Top KDE plot for X-axis distributions
        for i, label in enumerate(unique_labels):
            sns.kdeplot(features_df[features_df['cluster'] == label].iloc[:, x_index],
                        ax=ax_top, color=colors[i], fill=True, alpha=0.5)
        ax_top.axis('off')  # Hide axis for cleaner look

        # Right KDE plot for Y-axis distributions
        for i, label in enumerate(unique_labels):
            sns.kdeplot(features_df[features_df['cluster'] == label].iloc[:, y_index],
                        ax=ax_right, color=colors[i], fill=True, alpha=0.5, vertical=True)
        ax_right.axis('off')  # Hide axis for cleaner look

        # Main plot aesthetics
        #ax_main.set_xlabel(features_df.columns[x_index])
        #ax_main.set_ylabel(features_df.columns[y_index])
        ax_main.set_xlabel(important_feature_map[features_df.columns[x_index]])
        ax_main.set_ylabel(important_feature_map[features_df.columns[y_index]])
        ax_main.legend(fontsize=9)
        ax_main.legend()

        # Save the current figure to the PDF
        pdf.savefig()  # Adds the current figure to the PDF
        plt.close()  # Close the figure to free up memory


cluster_results_df.to_csv(data_folder + run_id + "_clusters.csv")
clusters_df = cluster_results_df.copy()
clusters_df['run_id'] = run_id
clusters_df[['demand_item', 'demand_point']] = clusters_df[key_column].str.split("|", expand=True)
clusters_df.drop(columns=[key_column], axis=1, inplace=True)
clusters_df = clusters_df[['run_id', 'demand_item', 'demand_point', 'cluster']]
clusters_df.to_sql('clusters', con=cluster_engine, if_exists='append', index=False, chunksize=5000)

centroids_df['run_id'] = run_id
#centroids_df.columns = [col.split("|")[-1] for col in centroids_df.columns]
centroids_df = centroids_df.reset_index(drop=True)
#print(centroids_df.head(10))

# Melt the DataFrame
df_melted = pd.melt(centroids_df, id_vars=['run_id', 'cluster'], var_name='characteristic', value_name='centroid')
df_melted.to_sql('cluster_centroids', con=cluster_engine, if_exists='append', index=False, chunksize=5000)

# Classify the centroids using the Noodle classification
if characteristics_creation_method in ['classifier','both']:
    centroids_df = centroids_df[['run_id', 'cluster','adi', 'cv_sq', 'trend_strength', 'seasonal_strength']]
    centroids_df['seasonal_bin'] = np.where(centroids_df['seasonal_strength'] > 0.5, "high_seas", "low_seas")
    centroids_df['trend_bin'] = np.where(centroids_df['trend_strength'] > 0.5, "high_local_trend", "low_local_trend")
    conditions = [
        (centroids_df['adi'] < adi_threshold) & (centroids_df['cv_sq'] < cv_sq_threshold),
        (centroids_df['adi'] < adi_threshold) & (centroids_df['cv_sq'] >= cv_sq_threshold),
        (centroids_df['adi'] >= adi_threshold) & (centroids_df['cv_sq'] < cv_sq_threshold),
        (centroids_df['adi'] >= adi_threshold) & (centroids_df['cv_sq'] >= cv_sq_threshold)
    ]
    choices = ["smooth", "erratic", "intermittent", "lumpy"]
    centroids_df['demand_class'] = np.select(conditions, choices, default='unknown')

    centroids_df.to_sql('cluster_centroid_classification', con=cluster_engine, if_exists='append', index=False, chunksize=5000)



started, step_count = duration_calculation("Cluster Extraction")


cluster_counts = cluster_results_df['cluster'].value_counts().sort_values(ascending=False)

counts_df = pd.DataFrame(cluster_results_df.groupby('cluster')[key_column].count().reset_index())
counts_df[key_column] = counts_df[key_column].astype(int)
counts_df.sort_values(by=key_column, ascending=False, inplace=True)

    # Perform PCA to see if the important characterisitcs can be identified for each cluster
    # This could be a key way in which the cluster information is used to determine which models to be used
    # If the characteristics are consistent with either the tsfresh clustering or Noodle CLassifier, 
    # this should pint initially to the best models.or Noodle classifier
do_pca = True
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
            characteristic_importance = pd.DataFrame({
                'characteristic': PCA_df.columns,
                'importance': component
            })
            
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
            characteristic_importance.to_sql('pca_characteristic_importance', con=cluster_engine, if_exists='append', index=False, chunksize=5000)

        # Explained variance for each component
        explained_variance = pd.DataFrame({
            'run_id': run_id,
            'cluster': cluster,
            'principal_component': range(1, len(pca.explained_variance_ratio_) + 1),
            'explained_variance': pca.explained_variance_ratio_ 
        })
        explained_variance.to_sql('pca_explained_variance', con=cluster_engine, if_exists='append', index=False, chunksize=5000)
        #print("explained_variance:\n", explained_variance)

        description = f"Cluster {cluster}: PCA Extraction"
        started, step_count = duration_calculation(description)


# Create lags (features) for time series forecasting
def create_lag_features(df, lags, feature_columns):
    for lag in lags:
        for feature in feature_columns:
            df[f'{feature}|lag_{lag}'] = df.groupby(key_column)[feature].shift(lag)
    df.fillna(0, inplace=True)
    return df

def create_rolling_window_features(df, window, suffix, date_column, feature_columns): 
    df_feature = (
        df.groupby(key_column)[feature_columns + [date_column]]
        .apply(lambda x: x.set_index(date_column).rolling(window=window).mean())
        .reset_index(level=0, drop=True))
    df_feature = df_feature.add_suffix(suffix)
    df = pd.concat([df.reset_index(drop=True), df_feature.reset_index(drop=True)], axis=1)
    return df

def create_cum_features(df, group_columns, suffix, date_column, feature_columns):
    if not group_columns or group_columns == ['']:
        group_columns = [key_column]
    else:
        group_columns = [key_column] + group_columns
    df = df.sort_values(by=group_columns + [date_column])
    df_feature = df.groupby(group_columns)[feature_columns].cumsum()
    df_feature = df_feature.add_suffix(suffix)
    df = pd.concat([df.reset_index(drop=True), df_feature.reset_index(drop=True)], axis=1)
    return df

feature_columns = [target_column] + numeric_columns

df = original_df.copy()

df[date_column] = pd.to_datetime(df[date_column])
df = df.sort_values(by=[key_column, date_column])
cluster_counts = df['cluster'].value_counts().sort_values(ascending=False)
cluster_counts = cluster_counts.reset_index()
cluster_counts.columns = ['cluster', 'count']

# Create features
if time_bucket == 'D':
    df['year'] = df[date_column].dt.year
    df['month'] = df[date_column].dt.month
    df['day_of_week'] = df[date_column].dt.dayofweek
    df['week_of_month'] = df[date_column].dt.isocalendar().week % 4
    df['week_of_year'] = df[date_column].dt.isocalendar().week
    df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)
   
    df = create_rolling_window_features(df,   7, '|rmean_W', date_column, feature_columns)
    df = create_rolling_window_features(df,  30, '|rmean_M', date_column, feature_columns)
    df = create_rolling_window_features(df,  91, '|rmean_Q', date_column, feature_columns)
    df = create_rolling_window_features(df, 365, '|rmean_Y', date_column, feature_columns)

    df = create_cum_features(df, [''], '|csum', date_column, feature_columns) 
    df = create_cum_features(df, ['year'], '|csum_Y', date_column, feature_columns)
    df = create_cum_features(df, ['year','month'], '|csum_M', date_column, feature_columns) 
    df = create_cum_features(df, ['year','week_of_year'], '|csum_W_of_Y', date_column, feature_columns) 
    df = create_cum_features(df, ['year','month','week_of_month'], '|csum_W_of_M', date_column, feature_columns) 
     
    lags = [1, 2, 3, 4, 5, 6, 7, 14, 21, 28, 30, 91, 365 ]  
    df = create_lag_features(df, lags, feature_columns)

elif time_bucket == 'W':
    df['year'] = df[date_column].dt.year
    df['quarter'] = df[date_column].dt.quarter
    df['month'] = df[date_column].dt.month
    df['week_of_month'] = df[date_column].dt.isocalendar().week % 4
    df['month_of_quarter'] = df['month'] % 4
    df['week_of_year'] = df[date_column].dt.isocalendar().week

    df = create_rolling_window_features(df,  4, '|rmean_M', date_column, feature_columns)
    df = create_rolling_window_features(df, 13, '|rmean_Q', date_column, feature_columns)
    df = create_rolling_window_features(df, 52, '|rmean_Y', date_column, feature_columns)

    df = create_cum_features(df, [''], '|csum', date_column, feature_columns) 
    df = create_cum_features(df, ['year'], '|csum_Y', date_column, feature_columns) 
    df = create_cum_features(df, ['year','quarter'], '|csum_Q', date_column, feature_columns) 
    df = create_cum_features(df, ['year','month'], '|csum_M', date_column, feature_columns) 
    df = create_cum_features(df, ['year','week_of_year'], '|csum_W_of_Y', date_column, feature_columns) 
    df = create_cum_features(df, ['year','month','week_of_month'], '|csum_W_of_M', date_column, feature_columns) 
   
    lags = [1, 2, 3, 4, 13, 52]
    df = create_lag_features(df, lags, feature_columns)
   
elif time_bucket == 'ME':
    df['year'] = df[date_column].dt.year
    df['quarter'] = df[date_column].dt.quarter
    df['month'] = df[date_column].dt.month
    df['month_of_Q'] = df['month'] % 4

    df = create_rolling_window_features(df,  3, '|rmean_Q', date_column, feature_columns)
    df = create_rolling_window_features(df, 12, '|rmean_Y', date_column, feature_columns)

    df = create_cum_features(df, [''], '|csum', date_column, feature_columns) 
    df = create_cum_features(df, ['year'], '|csum_Y', date_column, feature_columns) 
    df = create_cum_features(df, ['year','quarter'], '|csum_Q', date_column, feature_columns) 
    df = create_cum_features(df, ['year','quarter', 'month_of_Q'], '|csum_M_of_Q', date_column, feature_columns) 
    df = create_cum_features(df, ['year','month'], '|csum_M_of_Y', date_column, feature_columns) 

    lags = [1, 2, 3, 6, 9, 12]  
    df = create_lag_features(df, lags, feature_columns)


started, step_count = duration_calculation("Target Feature Creation")

cluster_counts = df['cluster'].value_counts().sort_values(ascending=False)
cluster_counts = cluster_counts.reset_index()
cluster_counts.columns = ['cluster', 'count']

feature_importance_df = pd.DataFrame(columns=['feature', 'importance', 'cluster'])
cluster_feature_importance_results =[]

for cluster in cluster_counts['cluster']:
    # Step 1: Identify the ID columns and the target column
    cluster_ids = df[df['cluster'] == cluster][key_column].unique().tolist()
    cluster_df = df[df[key_column].isin(cluster_ids)]

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
    cluster_df = cluster_df.drop(columns=features_to_drop)
    original_features = feature_columns
    feature_columns = [col for col in cluster_df.columns if col not in id_columns + [target_column]]

    n_items = 0
    feature_importance_results = []
    for unique_id, group in cluster_df.groupby(key_column):
        #print(f"Processing unique_id: {unique_id} in cluster: {cluster}")
        n_items +=1
        
        drop_columns = id_columns + [target_column]
        X = group.drop(columns=drop_columns)
        y = group[target_column].values
    
        if len(y) > 1:
            # Dynamically adjust the number of CV splits based on the group size
            cv_splits = min(5, len(y))  # Use the smaller of 5 or the number of samples

            # Standardize the features
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)

            if feature_importance_method == "LassoCV":
                # Fit LassoCV model with adjusted cv
                lasso = LassoCV(cv=cv_splits, random_state=42, max_iter=5000)
                lasso.fit(X_scaled, y)
                importances = np.abs(lasso.coef_)

            elif feature_importance_method == "RandomForest":
                rf = RandomForestRegressor(n_estimators=100, random_state=42)
                rf.fit(X_scaled, y)
                importances  = rf.feature_importances_

            elif feature_importance_method == "MutualInformation":
                mi = mutual_info_regression(X, y, random_state=42)
                importances = np.abs(mi)

            feature_importances_df = pd.DataFrame({
                'cluster': cluster,
                'unique_id': unique_id,
                'feature': X.columns,
                'importance': importances
            })

            feature_importances_df = feature_importances_df.sort_values(by='importance', ascending=False)
            feature_importances_df = feature_importances_df[feature_importances_df['importance'] >= feature_importance_threshold]
            if len(feature_importances_df) == 0:
                feature_importances_df = feature_importances_df.loc[:2]

            feature_importance_results.append(feature_importances_df)

    # After processing all unique_id's for the current cluster, aggregate feature importance within the cluster
    if len(feature_importance_results) > 0:
        feature_importance_df = pd.concat(feature_importance_results, ignore_index=True)
        mean_importance = feature_importance_df.groupby('feature')['importance'].agg(['mean']).reset_index()
        cluster_importance = feature_importance_df.groupby('feature')['importance'].agg(['sum']).reset_index()
        cluster_importance['mean'] = mean_importance['mean']   
        cluster_importance = cluster_importance[cluster_importance['mean'] >= feature_importance_threshold]                                                                            
        #print("cluster_importance:\n", cluster_importance)
        cluster_importance['cluster'] = cluster  # Add the cluster_id for reference
        cluster_feature_importance_results.append(cluster_importance)

        cluster_importance['run_id'] = run_id
        cluster_importance = cluster_importance[['run_id', 'cluster', 'feature', 'sum', 'mean']]    
        cluster_importance.to_sql('feature_importance', con=cluster_engine, if_exists='append', index=False, chunksize=5000)
        #feature_importance_df =  pd.concat([feature_importance_df, sorted_features_df], ignore_index=True)
    else:
        print("No feature importance results found for cluster:", cluster)

    description = f"Cluster {cluster}: Feature Importance"
    started, step_count = duration_calculation(description)

# Combine all cluster-level feature importance results into a single DataFrame
feature_importance_df = pd.concat(cluster_feature_importance_results, ignore_index=True)
feature_importance_df.to_csv(data_folder + run_id + "_feature_importance.csv")

# Rename columns for clarity
mean_importance_df = feature_importance_df.groupby('feature')['mean'].agg(['mean']).reset_index()
feature_importance_df = feature_importance_df.groupby('feature')['sum'].agg(['sum']).reset_index()
feature_importance_df['mean'] = mean_importance_df['mean']
feature_importance_df.columns = ['feature', 'total', 'average']
feature_importance_df['run_id'] = run_id
feature_importance_df = feature_importance_df[['run_id', 'feature', 'total', 'average']]   
feature_importance_df = feature_importance_df.sort_values(by='total', ascending=False) 
feature_importance_df.to_sql('feature_importance_overall', con=cluster_engine, if_exists='append', index=False, chunksize=5000)
feature_importance_df.to_csv(data_folder + run_id + "_overall_feature_importance.csv")


started = initial_time
started, step_count = duration_calculation("Complete Cycle Time")

cluster_cursor.execute("SELECT * FROM run_details where machine = %s", (machine_name,))   
run_details = cluster_cursor.fetchall()
run_details = pd.DataFrame(run_details)
run_details.to_csv(data_folder + "run_details.csv")

cluster_conn.close()
cluster_engine.dispose()
data_conn.close()
data_engine.dispose()

