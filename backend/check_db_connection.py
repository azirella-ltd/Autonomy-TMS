import pymysql
from pymysql.constants import CLIENT
from sqlalchemy.engine import make_url
from app.core.db_urls import resolve_sync_database_url

try:
    url = make_url(resolve_sync_database_url())
    if not url.host:
        raise RuntimeError("MySQL database required for this connectivity check")
    db_host = url.host
    db_port = url.port or 3306
    db_user = url.username or "autonomy_user"
    db_password = url.password or "autonomy_password"
    db_name = url.database or "autonomy"

    print(f"Attempting to connect to MySQL at {db_user}@{db_host}:{db_port}/{db_name}")
    
    # Try to connect to the database
    connection = pymysql.connect(
        host=db_host,
        port=db_port,
        user=db_user,
        password=db_password,
        database=db_name,
        client_flag=CLIENT.MULTI_STATEMENTS,
        connect_timeout=5
    )
    
    print("Successfully connected to MySQL!")
    
    # Try a simple query
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        print(f"Query result: {result[0]}")
    
    connection.close()
    print("Connection closed.")
    
except Exception as e:
    print(f"Error: {str(e)}")
