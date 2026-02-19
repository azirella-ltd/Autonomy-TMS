import pymysql
import time
import os

def test_connection():
    max_attempts = 30
    attempt = 1
    
    while attempt <= max_attempts:
        try:
            print(f"Attempt {attempt}/{max_attempts}: Connecting to database...")
            connection = pymysql.connect(
                host='db',
                user='autonomy_user',
                password='autonomy_password',
                database='autonomy',
                ssl=None  # Explicitly disable SSL
            )
            print("✅ Successfully connected to the database!")
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                print(f"Test query result: {result}")
            connection.close()
            return True
            
        except pymysql.MySQLError as e:
            print(f"❌ Connection failed: {e}")
            if attempt < max_attempts:
                print(f"Retrying in 2 seconds... (Attempt {attempt}/{max_attempts})")
                time.sleep(2)
            attempt += 1
    
    print("❌ All connection attempts failed")
    return False

if __name__ == "__main__":
    test_connection()
