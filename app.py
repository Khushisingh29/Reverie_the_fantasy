import os
from dotenv import load_dotenv
load_dotenv()  # ✅ Load .env first

from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import jinja2
from datetime import datetime

# ✅ Initialize Flask app after loading .env
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'devfallbacksecret')

# ✅ Load database URL
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ✅ Debug print
print("🔍 DATABASE_URL =", app.config['SQLALCHEMY_DATABASE_URI'])

if not app.config['SQLALCHEMY_DATABASE_URI']:
    raise RuntimeError("❌ DATABASE_URL not loaded properly. Check your .env file.")

# ✅ Initialize SQLAlchemy
db = SQLAlchemy(app)

# Optional Jinja loader setup
template_loader = jinja2.FileSystemLoader(searchpath=os.path.join(os.path.dirname(__file__), 'templates'))
app.jinja_loader = template_loader


class Story(db.Model):
    __tablename__ = 'stories'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    cover_image = db.Column(db.String(255))
    description = db.Column(db.Text)
    reads = db.Column(db.Integer, default=0)
    votes = db.Column(db.Integer, default=0)
    parts = db.Column(db.Integer, default=1)
    status = db.Column(db.String(50), default='Ongoing')

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    story_id = db.Column(db.Integer, db.ForeignKey('stories.id'), nullable=False)
    part = db.Column(db.Integer, nullable=False)
    username = db.Column(db.String(150))
    comment = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)



from flask import g

# Automatically set the current user before each request
@app.before_request
def load_current_user():
    g.user = session.get('username')


# ✅ Add 'is_admin' column if not exists using SQLAlchemy's engine
from sqlalchemy import inspect, Column, Integer

def add_is_admin_column():
    inspector = inspect(db.engine)
    columns = [col["name"] for col in inspector.get_columns("users")]

    if "is_admin" not in columns:
        with db.engine.connect() as conn:
            conn.execute('ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0')
            print("✅ 'is_admin' column added.")
    else:
        print("ℹ️ 'is_admin' column already exists.")

with app.app_context():
    add_is_admin_column()


@app.route('/insert_dummy')
def insert_dummy():
    dummy_story = Story(
        title='My First Story',
        cover_image='/static/cover1.jpg',
        description="This is a description of the first story. It's about dreams and fate.",
        reads=150,
        votes=20,
        parts=5,
        status='Ongoing'
    )
    db.session.add(dummy_story)
    db.session.commit()
    return "✅ Dummy story inserted!"


@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('home'))
    return redirect(url_for('login'))


@app.route('/home')
def home():
    if 'username' not in session:
        return redirect(url_for('login'))

    print("Session username:", session.get('username'))

    # 🔁 SQLAlchemy: Fetch stories from DB
    stories = Story.query.order_by(Story.id.desc()).all()

    return render_template('home.html', stories=stories)



@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        raw_password = request.form['password']

        # Hash the password
        hashed_password = generate_password_hash(raw_password)

        # Check if username or email already exists
        existing_user = User.query.filter_by(username=username).first()

        if existing_user:
            flash('⚠️ Username already exists. Please choose another one.', 'error')
            return redirect(url_for('signup'))

        # Create and add new user
        new_user = User(username=username, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        # Set session
        session['username'] = username
        flash('Account created successfully. Welcome!')
        return redirect(url_for('home'))

    return render_template('signup.html')



from werkzeug.utils import secure_filename
import os

@app.route('/add_story', methods=['GET', 'POST'])
def add_story():
    if request.method == 'POST':
        title = request.form['title'].strip()
        description = request.form['description'].strip()
        status = request.form['status']
        chapter_title = request.form['chapter_title'].strip()
        chapter_content = request.form['chapter_content'].strip()

        cover = request.files.get('cover_image')
        cover_filename = None

        if cover and cover.filename != '':
            cover_filename = secure_filename(cover.filename)
            cover_path = os.path.join(app.config['UPLOAD_FOLDER'], cover_filename)
            cover.save(cover_path)

        # Create and save story
        new_story = Story(
            title=title,
            description=description,
            status=status,
            cover_image=cover_filename,
            author=session.get('username')
        )
        db.session.add(new_story)
        db.session.commit()

        # Create and save first chapter
        first_chapter = Chapter(
            story_id=new_story.id,
            title=chapter_title,
            content=chapter_content
        )
        db.session.add(first_chapter)
        db.session.commit()

        return redirect(url_for('upload_chapter', story_id=new_story.id))

    return render_template('add_story.html')

from sqlalchemy import create_engine, text

# Setup engine (adjust DB path if needed)
engine = create_engine('sqlite:///stories.db')

def add_audio_column_sqlalchemy():
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE chapters ADD COLUMN audio_file TEXT"))
            print("✅ Column 'audio_file' added successfully.")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("ℹ️ Column 'audio_file' already exists.")
            else:
                raise

add_audio_column_sqlalchemy()
       


from werkzeug.utils import secure_filename
from flask import request, session, redirect, url_for
from sqlalchemy.orm import Session
from models import db, Story, Chapter  # You need to define these SQLAlchemy models
import os
import asyncio
import edge_tts
import uuid

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
UPLOAD_FOLDER = os.path.join('static', 'covers')
AUDIO_FOLDER = os.path.join('static', 'audios')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(AUDIO_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/submit', methods=['POST'])
def submit_story():
    if 'username' not in session:
        return redirect(url_for('login'))

    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    chapter_title = request.form.get('chapter_title', '').strip()
    chapter_content = request.form.get('chapter_content', '').strip()

    # Handle cover image upload
    file = request.files.get('cover_image')
    cover_image_filename = ''

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)

        # Avoid file conflict
        if os.path.exists(filepath):
            ext = filename.rsplit('.', 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{ext}"
            filepath = os.path.join(UPLOAD_FOLDER, filename)

        file.save(filepath)
        cover_image_filename = filename
    elif file:
        return "Invalid file type. Allowed: png, jpg, jpeg, gif, webp", 400

    # Insert story and chapter using SQLAlchemy
    try:
        story = Story(
            title=title,
            description=description,
            cover_image=cover_image_filename,
            author=session['username']
        )
        db.session.add(story)
        db.session.flush()  # Get story.id without committing

        chapter = Chapter(
            story_id=story.id,
            title=chapter_title,
            content=chapter_content
        )
        db.session.add(chapter)
        db.session.flush()  # Get chapter.id before commit

        # Generate audio
        audio_path = os.path.join(AUDIO_FOLDER, f'chapter_{chapter.id}.mp3')

        async def generate_audio():
            communicate = edge_tts.Communicate(chapter_content, voice="en-US-GuyNeural")
            await communicate.save(audio_path)

        asyncio.run(generate_audio())

        # Save audio path to chapter
        chapter.audio_file = f'chapter_{chapter.id}.mp3'
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        print("Error:", e)
        return "Internal Server Error", 500

    return redirect(url_for('home'))


from flask import Flask, render_template, request, redirect, session, url_for, flash
from werkzeug.security import check_password_hash
from models import db, User  # 🔁 make sure your models file is set up correctly

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = bool(user.is_admin)
            flash('Login successful!')
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password', 'error')
            return redirect(url_for('login'))

    success = request.args.get('success')
    return render_template("login.html", success=success)
 
    

from flask import session, redirect, url_for, flash, render_template
from models import User  # assuming you've already set up your models properly

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('user_id', None)
    session.pop('is_admin', None)
    flash('You have been logged out.')
    return redirect(url_for('login'))

@app.route('/account')
def account():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    user = User.query.filter_by(username=username).first()

    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('login'))

    return render_template('account.html', user=user)


@app.route('/read/<int:story_id>', methods=['GET', 'POST'])
def read_story(story_id):
    story = Story.query.get_or_404(story_id)

    # ✅ Get first chapter (or modify logic to fetch specific part)
    chapter = Chapter.query.filter_by(story_id=story_id).first()

    comments = Comment.query.filter_by(story_id=story_id).all()

    return render_template(
        'read_story.html',
        story=story,
        chapter=chapter,
        comments=comments
    )

@app.route('/edit/<int:story_id>', methods=['GET', 'POST'])
def edit_story(story_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    story = Story.query.get_or_404(story_id)

    if story.author != session['username']:
        flash("You can't edit someone else's story!")
        return redirect(url_for('home'))

    # 🛠️ Add form processing if request.method == 'POST'
    return render_template('edit_story.html', story=story)



@app.route('/story/<int:story_id>/part/<int:part>/comment', methods=['POST'])
def add_comment(story_id, part):
    username = request.form['username']
    comment_text = request.form['comment']

    new_comment = Comment(
        story_id=story_id,
        part=part,
        username=username,
        comment=comment_text
    )

    db.session.add(new_comment)
    db.session.commit()

    return redirect(url_for('read_story', story_id=story_id, part=part))

@app.route('/delete_story/<int:story_id>', methods=['POST'])
def delete_story(story_id):
    if 'user_id' not in session and not session.get('is_admin'):
        flash('You need to log in to delete a story.')
        return redirect(url_for('login'))

    user_id = session.get('user_id')
    is_admin = session.get('is_admin', False)

    if is_admin:
        story = Story.query.get(story_id)
    else:
        story = Story.query.filter_by(id=story_id, author=user_id).first()

    if story is None:
        flash('Story not found or you do not have permission to delete it.')
        return redirect(url_for('admin_panel') if is_admin else url_for('my_stories'))

    db.session.delete(story)
    db.session.commit()
    flash('Story deleted successfully.')

    return redirect(url_for('admin_panel') if is_admin else url_for('my_stories'))


@app.route('/story/<int:story_id>')
def story_detail(story_id):
    # ✅ 1. Increment read count
    story = Story.query.get_or_404(story_id)
    story.reads = (story.reads or 0) + 1
    db.session.commit()

    # ✅ 2. Save to reading history (if logged in)
    if 'user_id' in session:
        user_id = session['user_id']
        existing_entry = History.query.filter_by(user_id=user_id, story_id=story_id).first()
        if not existing_entry:
            new_entry = History(user_id=user_id, story_id=story_id)
            db.session.add(new_entry)
            db.session.commit()

    # ✅ 3. Fetch chapters
    chapters = Chapter.query.filter_by(story_id=story_id).all()

    return render_template(
        'story_detail.html',
        story=story,
        chapters=chapters,
        username=session.get('username')
    )



@app.route('/chapter/<int:chapter_id>')
def read_chapter(chapter_id):
    # Get current chapter
    chapter = Chapter.query.get_or_404(chapter_id)

    # Get story info
    story = Story.query.get_or_404(chapter.story_id)

    # Get next chapter in same story
    next_chapter = (
        Chapter.query
        .filter(Chapter.story_id == chapter.story_id, Chapter.id > chapter_id)
        .order_by(Chapter.id.asc())
        .first()
    )
    next_chapter_id = next_chapter.id if next_chapter else None

    # Get comments
    comments = Comment.query.filter_by(chapter_id=chapter_id).all()

    return render_template(
        'read_chapter.html',
        chapter=chapter,
        story=story,
        comments=comments,
        next_chapter_id=next_chapter_id
    )

from datetime import datetime

@app.route('/comment/<int:chapter_id>', methods=['POST'])
def comment(chapter_id):
    text = request.form['comment']
    username = session.get('username', 'Anonymous')
    timestamp = datetime.now()

    new_comment = Comment(
        chapter_id=chapter_id,
        username=username,
        comment=text,
        timestamp=timestamp
    )

    db.session.add(new_comment)
    db.session.commit()

    return redirect(url_for('read_chapter', chapter_id=chapter_id))



from datetime import datetime

@app.template_filter('datetimeformat')
def datetimeformat(value):
    if not value:
        return "Unknown time"
    try:
        if isinstance(value, str):
            value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        return value.strftime('%B %d, %I:%M %p')
    except Exception:
        return str(value)

@app.route('/comment/delete/<int:comment_id>')
def delete_comment(comment_id):
    username = session.get('username')

    # Get the comment by ID
    comment = Comment.query.get_or_404(comment_id)

    # Only allow deletion if the comment belongs to the logged-in user
    if comment.username == username:
        db.session.delete(comment)
        db.session.commit()

    return redirect(url_for('read_chapter', chapter_id=comment.chapter_id))



@app.route('/comment/edit/<int:comment_id>', methods=['GET', 'POST'])
def edit_comment(comment_id):
    username = session.get('username')

    # Fetch the comment
    comment = Comment.query.get_or_404(comment_id)

    # Allow only the user who wrote the comment to edit
    if comment.username != username:
        return redirect(url_for('read_chapter', chapter_id=comment.chapter_id))

    if request.method == 'POST':
        new_text = request.form['comment'].strip()
        if new_text:
            comment.comment = new_text
            db.session.commit()
        return redirect(url_for('read_chapter', chapter_id=comment.chapter_id))

    return render_template('edit_comment.html', comment=comment)



from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Chapter(db.Model):
    __tablename__ = 'chapters'

    id = db.Column(db.Integer, primary_key=True)
    story_id = db.Column(db.Integer, db.ForeignKey('stories.id'), nullable=False)
    author_name = db.Column(db.String(100), nullable=False)  # ✅ new field for author's name
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Optional: Relationship to Story (if you have a Story model)
    story = db.relationship('Story', backref='chapters')


from flask import request, session, redirect, url_for, render_template
from models import db, Chapter, Story  # make sure you’ve imported your models

@app.route('/add_chapter/<int:story_id>', methods=['GET', 'POST'])
def add_chapter(story_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        author_name = session['username']  # ✅ Use username from session

        new_chapter = Chapter(
            story_id=story_id,
            title=title,
            content=content,
            author_name=author_name  # ✅ store author's name
        )
        db.session.add(new_chapter)
        db.session.commit()

        return redirect(url_for('story_detail', story_id=story_id))

    # Fetch story title using SQLAlchemy
    story = Story.query.get_or_404(story_id)
    return render_template("add_chapter.html", story_id=story_id, story_title=story.title)

    


from flask import session, redirect, url_for, render_template
from models import db, User, Story  # Assuming your models are defined

@app.route('/admin')
def admin_panel():
    if not session.get('is_admin'):
        return redirect(url_for('home'))

    users = User.query.with_entities(User.id, User.username, User.email, User.is_admin).all()
    stories = Story.query.with_entities(Story.id, Story.title, Story.status, Story.reads, Story.votes).all()

    return render_template('admin.html', users=users, stories=stories)

import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
from models import db, User

load_dotenv()

admin_username = os.getenv("ADMIN_USERNAME")
admin_email = os.getenv("ADMIN_EMAIL")
admin_password = os.getenv("ADMIN_PASSWORD")

if not admin_username or not admin_email or not admin_password:
    print("❌ Missing admin credentials in .env")
else:
    # Check if admin already exists
    existing_admin = User.query.filter_by(username=admin_username).first()
    if existing_admin:
        print("⚠️ Admin user already exists.")
    else:
        hashed_password = generate_password_hash(admin_password)
        new_admin = User(username=admin_username, email=admin_email, password=hashed_password, is_admin=True)
        db.session.add(new_admin)
        db.session.commit()
        print("✅ Admin user created securely.")



from models import db, User

print("📋 Existing usernames:")
users = User.query.with_entities(User.username).all()
for username, in users:
    print(username)
from models import db, User

User.query.filter(User.is_admin == True, User.username != 'Khushi_Singh_four').delete(synchronize_session=False)
db.session.commit()
print("✅ Deleted all admin users except 'Khushi_Singh_four'")

users = User.query.with_entities(User.id, User.username, User.password, User.is_admin).all()

print("📋 Current Users:")
for user in users:
    print(user)


@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if not session.get('is_admin'):
        return redirect(url_for('home'))

    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()

    return redirect(url_for('admin_panel'))
@app.route('/make_admin/<int:user_id>', methods=['POST'])
def make_admin(user_id):
    if not session.get('is_admin'):
        return redirect(url_for('home'))

    user = User.query.get_or_404(user_id)
    user.is_admin = True
    db.session.commit()

    return redirect(url_for('admin_panel'))

@app.route('/story/<int:story_id>/upload_chapter', methods=['GET', 'POST'])
def upload_chapter(story_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        chapter_title = request.form['chapter_title']
        chapter_content = request.form['chapter_content']

        new_chapter = Chapter(
            story_id=story_id,
            title=chapter_title,
            content=chapter_content
        )
        db.session.add(new_chapter)
        db.session.commit()

        return redirect(url_for('view_story', story_id=story_id))

    return render_template('upload_chapter.html')


from sqlalchemy import create_engine, text

# Connect using SQLAlchemy engine
engine = create_engine('sqlite:///stories.db')

# ✅ Drop 'story_parts' table if exists
with engine.connect() as conn:
    conn.execute(text("DROP TABLE IF EXISTS story_parts"))
    print("✅ 'story_parts' table removed.")

# ✅ Add 'chapter_id' to comments table if not exists
with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE comments ADD COLUMN chapter_id INTEGER"))
        print("✅ 'chapter_id' added to comments.")
    except Exception as e:
        if "duplicate column name" in str(e):
            print("ℹ️ 'chapter_id' already exists.")
        else:
            print("❌ Error while adding 'chapter_id':", e)

# ✅ Add 'views' to chapters table if not exists
with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE chapters ADD COLUMN views INTEGER DEFAULT 0"))
        print("✅ 'views' column added.")
    except Exception as e:
        if "duplicate column name" in str(e):
            print("ℹ️ 'views' column already exists.")
        else:
            print("❌ Error while adding 'views':", e)


from models import Story, Like  # Assuming these are defined ORM models

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    db = SessionLocal()

    # ORM-like fuzzy search using raw SQL (ORM .filter() doesn't support LIKE with OR easily)
    results = db.execute(
        text("SELECT * FROM stories WHERE title LIKE :q OR description LIKE :q"),
        {"q": f"%{query}%"}
    ).fetchall()

    db.close()
    return render_template('search_results.html', query=query, results=results)


@app.route('/set_theme', methods=['POST'])
def set_theme():
    selected_theme = request.form.get('theme')
    session['theme'] = selected_theme  # 'dark' or 'light'
    return redirect(request.referrer or url_for('home'))


@app.route('/like/<int:story_id>', methods=['POST'])
def like_story(story_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    db = SessionLocal()

    # Check if like already exists
    like_exists = db.execute(
        text("SELECT 1 FROM likes WHERE user_id = :uid AND story_id = :sid"),
        {"uid": user_id, "sid": story_id}
    ).fetchone()

    if not like_exists:
        # Insert like
        db.execute(
            text("INSERT INTO likes (user_id, story_id) VALUES (:uid, :sid)"),
            {"uid": user_id, "sid": story_id}
        )

        # Update like count
        db.execute(
            text("UPDATE stories SET likes = likes + 1 WHERE id = :sid"),
            {"sid": story_id}
        )

        db.commit()

    db.close()
    return redirect(url_for('home'))


from sqlalchemy import Column, Integer, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from your_app import Base  # from your SQLAlchemy setup

class Like(Base):
    __tablename__ = 'likes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    story_id = Column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint('user_id', 'story_id', name='unique_like'),)


class History(Base):
    __tablename__ = 'history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    story_id = Column(Integer, nullable=False)
    viewed_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint('user_id', 'story_id', name='unique_history'),)

from your_app import Base, engine
from models import Like, History

Base.metadata.create_all(engine)

from sqlalchemy.orm import joinedload
from sqlalchemy import desc
from models import History, Story

@app.route('/history')
def view_history():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    db = SessionLocal()

    history = (
        db.query(History)
        .join(Story, History.story_id == Story.id)
        .filter(History.user_id == user_id)
        .order_by(desc(History.viewed_at))
        .with_entities(Story.id, Story.title, Story.cover_image)
        .all()
    )

    db.close()
    return render_template('history.html', history=history)

@app.route('/story/<int:story_id>')
def view_story(story_id):
    # Show story logic...

    if 'user_id' in session:
        user_id = session['user_id']
        db = SessionLocal()

        # Check if already exists
        existing = db.query(History).filter_by(user_id=user_id, story_id=story_id).first()
        if not existing:
            new_entry = History(user_id=user_id, story_id=story_id)
            db.add(new_entry)
            db.commit()

        db.close()


from models import History

@app.route('/history/remove/<int:story_id>', methods=['POST'])
def remove_from_history(story_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    db = SessionLocal()

    entry = db.query(History).filter_by(user_id=user_id, story_id=story_id).first()
    if entry:
        db.delete(entry)
        db.commit()

    db.close()
    return redirect(url_for('view_history'))

import os
from flask import send_file

@app.route('/chapter_audio/<int:chapter_id>')
def chapter_audio(chapter_id):
    audio_path = os.path.join('static', 'audios', f'chapter_{chapter_id}.mp3')
    if os.path.exists(audio_path):
        return send_file(audio_path, mimetype='audio/mpeg')
    return "Audio not available", 404


if __name__ == '__main__':
    from models import Base, engine

    # Create tables if they don't exist yet
    Base.metadata.create_all(engine)

    # Start the Flask development server
    app.run(debug=True)

