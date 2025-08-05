import os
from werkzeug.security import generate_password_hash
from your_flask_app import app, db  # Import your Flask app and db instance
from models import User  # Your User model with SQLAlchemy

def create_admin_user():
    with app.app_context():
        username = os.getenv("ADMIN_USERNAME")
        password = os.getenv("ADMIN_PASSWORD")
        is_admin = True

        if not username or not password:
            raise ValueError("❌ ADMIN_USERNAME and ADMIN_PASSWORD must be set as environment variables.")

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            print(f"❌ Username '{username}' already exists. Choose a different one.")
            return

        hashed_password = generate_password_hash(password)

        new_admin = User(
            username=username,
            password=hashed_password,
            is_admin=is_admin
        )

        db.session.add(new_admin)
        db.session.commit()
        print("✅ Admin user created successfully.")

if __name__ == '__main__':
    create_admin_user()
