from your_flask_app import app, db
from models import User

def mark_user_as_admin(username):
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if not user:
            print(f"User '{username}' not found.")
            return
        user.is_admin = True
        db.session.commit()
        print(f"{username} is now marked as admin.")

if __name__ == "__main__":
    mark_user_as_admin('khushi')  # Replace with your username
