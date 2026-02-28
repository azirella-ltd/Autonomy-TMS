import bcrypt
import pymysql
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_db_connection():
    return pymysql.connect(
        host=os.getenv('MYSQL_SERVER', 'db'),
        user=os.getenv('MYSQL_USER', 'autonomy_user'),
        password=os.getenv('MYSQL_PASSWORD', 'Autonomy@2026'),
        database=os.getenv('MYSQL_DB', 'autonomy'),
        cursorclass=pymysql.cursors.DictCursor
    )

def update_admin_password():
    # Generate a bcrypt hash for the password
    password = "Autonomy@2026"
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
