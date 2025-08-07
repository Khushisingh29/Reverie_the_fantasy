from app import app, db, User
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
import os

load_dotenv()

admin_username = os.getenv("ADMIN_USERNAME")
admin_email = os.getenv("ADMIN_EMAIL")
admin_password = os.getenv("ADMIN_PASSWORD")

with app.app_context():  # ✅ this ensures the context is active

    # Print existing usernames
    print("📋 Existing usernames:")
    users = User.query.with_entities(User.username).all()
    for username, in users:
        print(username)

    if not admin_username or not admin_email or not admin_password:
        print("❌ Missing admin credentials in .env")
    else:
        existing_admin = User.query.filter_by(username=admin_username).first()
        if existing_admin:
            print("⚠️ Admin user already exists.")
        else:
            hashed_password = generate_password_hash(admin_password)
            new_admin = User(
                username=admin_username,
                email=admin_email,
                password=hashed_password,
                is_admin=True
            )
            db.session.add(new_admin)
            db.session.commit()
            print("✅ Admin user created securely.")
