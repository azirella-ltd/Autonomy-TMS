import bcrypt
import pymysql
from sqlalchemy.engine import make_url
from app.core.db_urls import resolve_sync_database_url


def get_db_connection():
    url = make_url(resolve_sync_database_url())
    if not url.host:
        raise RuntimeError("MySQL connection required for fix_admin_password script")
    return pymysql.connect(
        host=url.host,
        port=url.port or 3306,
        user=url.username or "autonomy_user",
        password=url.password or "",
        database=url.database or "autonomy",
        cursorclass=pymysql.cursors.DictCursor,
    )

def update_admin_password():
    # Generate a bcrypt hash for the password
    password = "Autonomy@2025"
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')
    
    print(f"Generated hash: {hashed_password}")
    
    # Update the database
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            sql = "UPDATE users SET hashed_password = %s WHERE username = 'admin'"
            cursor.execute(sql, (hashed_password,))
            connection.commit()
            print("Successfully updated admin password")
            
            # Verify the update
            cursor.execute("SELECT username, LEFT(hashed_password, 60) as hash_start FROM users WHERE username = 'admin'")
            result = cursor.fetchone()
            print(f"Updated record: {result}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if connection:
            connection.close()

if __name__ == "__main__":
    update_admin_password()
