import sqlite3

# Connect to your database
conn = sqlite3.connect('stories.db')  # or your actual DB name
cursor = conn.cursor()

# Add 'is_admin' column to the users table (only if not already added)
try:
    cursor.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
    print("Column 'is_admin' added.")
except:
    print("Column 'is_admin' already exists or error occurred.")

conn.commit()
conn.close()
