from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.security import get_password_hash
from app.core.db_urls import resolve_sync_database_url

# Create engine and session
engine = create_engine(resolve_sync_database_url())
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

def reset_admin_password():
    try:
        # Get system administrator user
        admin = db.execute(text("SELECT * FROM users WHERE username = 'systemadmin'"))
        admin = admin.first()
        if not admin:
            print("System administrator user not found")
            return

        # New password
        new_password = "Autonomy@2025"
        hashed_password = get_password_hash(new_password)

        # Update password
        db.execute(
            text("UPDATE users SET hashed_password = :password WHERE username = 'systemadmin'"),
            {"password": hashed_password}
        )
        db.commit()
        print("System administrator password has been reset successfully")
        
    except Exception as e:
        print(f"Error resetting password: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    reset_admin_password()
