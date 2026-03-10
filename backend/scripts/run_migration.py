import mysql.connector
from sqlalchemy.engine import make_url
from app.core.db_urls import resolve_sync_database_url

def run_migration():
    url = make_url(resolve_sync_database_url())
    db_config = {
        'host': url.host or 'localhost',
        'user': url.username or 'autonomy_user',
        'password': url.password or '',
        'database': url.database or 'autonomy',
        'port': int(url.port or 3306),
    }
    
    # Read the SQL file
    with open('scripts/apply_migration.sql', 'r') as file:
        sql_script = file.read()
    
    # Execute the SQL script
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()
        
        # Split the SQL script into individual statements and execute them
        for statement in sql_script.split(';'):
            if statement.strip():
                cursor.execute(statement + ';')
        
        connection.commit()
        print("Database migration completed successfully!")
        
    except mysql.connector.Error as err:
        print(f"Error: {err}")
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()

if __name__ == "__main__":
    run_migration()
