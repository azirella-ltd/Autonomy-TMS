from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, text
from sqlalchemy.orm import sessionmaker
from app.core.db_urls import resolve_sync_database_url

def update_database():
    engine = create_engine(resolve_sync_database_url())
    
    # Create a session
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Add missing columns to users table
        alter_queries = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login DATETIME DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_password_change DATETIME DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_attempts INT DEFAULT 0",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until DATETIME DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_secret VARCHAR(255) DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_enabled BOOLEAN DEFAULT FALSE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS user_type ENUM('SYSTEM_ADMIN','GROUP_ADMIN','PLAYER') NOT NULL DEFAULT 'PLAYER'"
        ]
        
        for query in alter_queries:
            try:
                session.execute(text(query))
                session.commit()
                print(f"Successfully executed: {query}")
            except Exception as e:
                session.rollback()
                print(f"Error executing {query}: {e}")
        
        try:
            session.execute(text(
                "UPDATE users SET user_type = CASE WHEN is_superuser = 1 THEN 'SYSTEM_ADMIN' ELSE 'PLAYER' END "
                "WHERE user_type IS NULL OR user_type = '' OR user_type NOT IN ('SYSTEM_ADMIN','GROUP_ADMIN','PLAYER')"
            ))
            session.commit()
            print("Backfilled user_type column on existing records")
        except Exception as e:
            session.rollback()
            print(f"Error backfilling user_type column: {e}")

        print("Database schema update completed successfully!")
        
    except Exception as e:
        session.rollback()
        print(f"Error updating database schema: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    update_database()
