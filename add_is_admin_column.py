import os
import sqlite3

username = os.getenv("ADMIN_USERNAME")
password = os.getenv("ADMIN_PASSWORD")
is_admin = 1

if not username or not password:
    raise ValueError("❌ ADMIN_USERNAME and ADMIN_PASSWORD must be set as environment variables.")

with sqlite3.connect("stories.db") as conn:
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE username=?", (username,))
    existing_user = cur.fetchone()

    if existing_user:
        print(f"❌ Username '{username}' already exists. Choose a different one.")
    else:
        cur.execute('''
            INSERT INTO users (username, password, is_admin)
            VALUES (?, ?, ?)
        ''', (username, password, is_admin))
        conn.commit()
        print("✅ Admin user created successfully.")
