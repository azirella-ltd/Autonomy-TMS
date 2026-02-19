import sys
import os
from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
import pytest

# Add the current directory to the Python path
sys.path.append(str(Path(__file__).parent))

# Import settings after setting up the path
from app.core.config import settings

def test_database_connection():
    print(f"Testing database connection to: {settings.SQLALCHEMY_DATABASE_URI}")
    
    try:
        # Create engine
        engine = create_engine(settings.SQLALCHEMY_DATABASE_URI)

        # Test connection
        with engine.connect() as conn:
            print("✅ Successfully connected to the database")

            # Check if we can execute a simple query
            result = conn.execute(text("SELECT 1"))
            print(f"✅ Database query test: {result.scalar() == 1}")

            # Get table information
            inspector = inspect(engine)
            tables = inspector.get_table_names()

            if not tables:
                print("⚠️  No tables found in the database")
            else:
                print("\nTables in the database:")
                for table in tables:
                    print(f"- {table}")

                    # Show columns for each table
                    columns = inspector.get_columns(table)
                    print(f"  Columns: {[col['name'] for col in columns]}")

    except OperationalError as e:
        pytest.skip(f"Database not available: {e}")
    except Exception as e:
        print(f"❌ Error connecting to database: {e}")
        raise

if __name__ == "__main__":
    test_database_connection()
