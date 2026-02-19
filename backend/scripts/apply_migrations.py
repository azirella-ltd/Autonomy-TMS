from alembic.config import Config
from alembic import command
import os
from app.core.db_urls import resolve_sync_database_url

def run_migrations():
    # Get the directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Set the path to the alembic.ini file
    alembic_cfg = os.path.join(script_dir, "..", "alembic.ini")
    
    # Create the config
    config = Config(alembic_cfg)
    
    # Set the script location to the consolidated migrations directory
    config.set_main_option('script_location', os.path.join(script_dir, "..", "migrations"))
    
    # Ensure sqlalchemy.url is explicitly set from environment or fallback helper
    db_url = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI") or resolve_sync_database_url()
    if db_url:
        config.set_main_option("sqlalchemy.url", db_url)
    
    # Run the migration
    command.upgrade(config, 'head')
    print("Database migrations applied successfully!")

if __name__ == "__main__":
    run_migrations()
