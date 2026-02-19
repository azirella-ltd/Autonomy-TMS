from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

def check_database():
    try:
        # Create engine and connect
        engine = create_engine(settings.SQLALCHEMY_DATABASE_URI)
        print(f"Connecting to database at: {settings.SQLALCHEMY_DATABASE_URI}")
        
        # Create a session
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        # Get table information
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        print("\nTables in the database:")
        for table in tables:
            print(f"- {table}")
            
        # Check if migrations table exists
        if 'alembic_version' in tables:
            print("\nAlembic version table found.")
            
        db.close()
        print("\nDatabase check completed successfully!")
        
    except Exception as e:
        print(f"Error checking database: {str(e)}")

if __name__ == "__main__":
    check_database()
