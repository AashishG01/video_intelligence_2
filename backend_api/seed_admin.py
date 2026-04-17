import psycopg2
from auth import get_password_hash

print("--- C.O.R.E. Surveillance: Initializing Superadmin ---")
username = input("Enter Superadmin Username: ")
password = input("Enter Superadmin Password: ")

hashed_pw = get_password_hash(password)

try:
    conn = psycopg2.connect(dbname="surveillance", user="admin", password="password", host="localhost", port="5432")
    conn.autocommit = True
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO users (username, hashed_password, role) VALUES (%s, %s, %s)",
        (username, hashed_pw, 'admin')
    )
    
    cursor.close()
    conn.close()
    print(f"\n✅ SUCCESS: Superadmin '{username}' created.")
    print("The vault is now locked. You can delete this script if you wish.")
except psycopg2.IntegrityError:
    print("\n❌ FAILED: User already exists. Drop the table if you want to start over.")
except Exception as e:
    print(f"\n❌ FAILED: {e}")