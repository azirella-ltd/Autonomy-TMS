#!/usr/bin/env python3
"""Test database connection with direct MySQL connection."""

import pymysql
from pymysql.constants import CLIENT
from sqlalchemy.engine import make_url
from app.core.db_urls import resolve_sync_database_url

def test_connection():
    """Test database connection with provided credentials."""
    try:
        url = make_url(resolve_sync_database_url())
        if url.drivername.startswith("sqlite"):
            raise RuntimeError("MySQL database required for this connectivity script")
        db_config = {
            'host': url.host or "localhost",
            'port': int(url.port or 3306),
            'user': url.username or "autonomy_user",
            'password': url.password or "",
            'database': url.database or "autonomy",
            'client_flag': CLIENT.MULTI_STATEMENTS,
            'connect_timeout': 10,
        }
        
        print("Testing database connection with the following parameters:")
        print(f"Host: {db_config['host']}")
        print(f"Port: {db_config['port']}")
        print(f"User: {db_config['user']}")
        print(f"Database: {db_config['database']}")
        
        # Try to connect to the database
        connection = pymysql.connect(**db_config)
        
        # Test the connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            print(f"\nConnection successful! Result: {result}")
            
            # List all tables in the database
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            print("\nTables in the database:")
            for table in tables:
                print(f"- {table[0]}")
        
        connection.close()
        return True
        
    except Exception as e:
        print(f"\nError connecting to the database: {str(e)}")
        return False

if __name__ == "__main__":
    test_connection()
