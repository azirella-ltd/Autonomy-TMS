from sqlalchemy import create_engine, text
from app.core.db_urls import resolve_sync_database_url

def apply_migration():
    engine = create_engine(resolve_sync_database_url())
    
    # SQL statements to execute
    migration_sql = """
    -- Add round_time_limit column to scenarios table
    ALTER TABLE scenarios 
    ADD COLUMN IF NOT EXISTS round_time_limit INT NOT NULL DEFAULT 60;
    
    -- Add current_round_ends_at column to scenarios table
    ALTER TABLE scenarios 
    ADD COLUMN IF NOT EXISTS current_round_ends_at DATETIME NULL;
    
    -- Add is_processed column to scenario_periods table
    ALTER TABLE scenario_periods 
    ADD COLUMN IF NOT EXISTS is_processed BOOLEAN NOT NULL DEFAULT FALSE;
    
    -- Add is_completed and completed_at columns if they don't exist
    ALTER TABLE scenario_periods 
    ADD COLUMN IF NOT EXISTS is_completed BOOLEAN NOT NULL DEFAULT FALSE;
    
    ALTER TABLE scenario_periods 
    ADD COLUMN IF NOT EXISTS completed_at DATETIME NULL;
    """
    
    # Execute the migration
    with engine.connect() as connection:
        with connection.begin():
            # Split the SQL into individual statements and execute them
            for statement in migration_sql.split(';'):
                if statement.strip():
                    connection.execute(text(statement + ';'))
    
    print("Database migration completed successfully!")

if __name__ == "__main__":
    apply_migration()
