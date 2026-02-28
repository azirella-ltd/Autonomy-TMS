from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from passlib.hash import bcrypt
from app.core.db_urls import resolve_sync_database_url

# Create engine and session
engine = create_engine(resolve_sync_database_url())
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

def update_all_passwords():
    try:
        # Generate bcrypt hash for the password
        password_hash = bcrypt.using(rounds=12).hash("Autonomy@2026")
        
        # Update all users' passwords
        result = db.execute(
            text("UPDATE users SET hashed_password = :password"),
            {"password": password_hash}
        )
        db.commit()
        
        print(f"Successfully updated passwords for {result.rowcount} users")
        
    except Exception as e:
        print(f"Error updating passwords: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    update_all_passwords()
