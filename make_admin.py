from your_flask_app import app, db  # Import your Flask app and SQLAlchemy db
from sqlalchemy import inspect, text

def add_is_admin_column():
    with app.app_context():
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('users')]

        if 'is_admin' not in columns:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0"))
                print("✅ Column 'is_admin' added.")
        else:
            print("ℹ️ Column 'is_admin' already exists.")

if __name__ == '__main__':
    add_is_admin_column()

