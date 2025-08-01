import sqlite3

username = "Khushi_Singh_four"
password = "MKA142930"
is_admin = 1

with sqlite3.connect("stories.db") as conn:
    cur = conn.cursor()

    # Check if the username already exists
    cur.execute("SELECT * FROM users WHERE username=?", (username,))
    existing_user = cur.fetchone()

    if existing_user:
        print(f"❌ Username '{username}' already exists. Choose a different one.")
    else:
        # Insert only if username is not taken
        cur.execute('''
            INSERT INTO users (username, password, is_admin)
            VALUES (?, ?, ?)
        ''', (username, password, is_admin))
        conn.commit()
        print("✅ Admin user created successfully.")
