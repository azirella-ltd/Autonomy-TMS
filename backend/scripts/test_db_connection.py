#!/usr/bin/env python3
"""Test database connectivity using the standard resolver."""

from sqlalchemy import create_engine, text
from app.core.db_urls import resolve_sync_database_url

DATABASE_URL = resolve_sync_database_url()

print(f"Connecting to database with URL: {DATABASE_URL}")

try:
    # Create an engine to connect to the database
    engine = create_engine(DATABASE_URL)
    
    # Test the connection
    with engine.connect() as connection:
        print("Successfully connected to the database!")
        # Try to execute a simple query using text()
        result = connection.execute(text("SELECT 1"))
        print("Test query result:", result.fetchone())
        
        # List all tables
        result = connection.execute(text("SHOW TABLES"))
        print("\nTables in the database:")
        for row in result:
            print(f"- {row[0]}")
            
except Exception as e:
    print(f"Error connecting to the database: {e}")
    raise
