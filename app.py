import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, g
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import inspect, Column, Integer, create_engine, text, desc
from sqlalchemy.orm import Session, joinedload
from datetime import datetime
import asyncio
import edge_tts
import uuid
import jinja2

# Load environment variables
load_dotenv()

# Initialize app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'devfallbacksecret')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
UPLOAD_FOLDER = os.path.join('static', 'covers')
AUDIO_FOLDER = os.path.join('static', 'audios')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(AUDIO_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Initialize DB
db = SQLAlchemy(app)

# Jinja2 template loader
template_loader = jinja2.FileSystemLoader(searchpath=os.path.join(os.path.dirname(__file__), 'templates'))
app.jinja_loader = template_loader

# Models
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
    author = db.Column(db.String(150))

    # ✅ Relationship to chapters with cascade
    chapters = db.relationship(
        'Chapter',
        backref='story',
        cascade='all, delete-orphan',
        passive_deletes=True
    )

    # ✅ Relationship to comments with cascade (MUST HAVE THIS)
    comments = db.relationship(
        'Comment',
        backref='story',
        cascade='all, delete-orphan',
        passive_deletes=True
    )

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

class Comment(db.Model):
    __tablename__ = 'comments'

    id = db.Column(db.Integer, primary_key=True)

    # Add ondelete='CASCADE' to allow story deletion
    story_id = db.Column(
        db.Integer,
        db.ForeignKey('stories.id', ondelete='CASCADE'),
        nullable=False
    )

    part = db.Column(db.Integer, nullable=False)
    username = db.Column(db.String(150))
    comment = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    chapter_id = db.Column(db.Integer)

class Chapter(db.Model):
    __tablename__ = 'chapters'

    id = db.Column(db.Integer, primary_key=True)
    story_id = db.Column(
        db.Integer,
        db.ForeignKey('stories.id', ondelete='CASCADE'),
        nullable=False
    )
    author_name = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    audio_file = db.Column(db.String(255))
    views = db.Column(db.Integer, default=0)

    # ❌ Remove this line (no relationship in Chapter):
    # story = db.relationship(...)

class Like(db.Model):
    __tablename__ = 'likes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    story_id = db.Column(db.Integer, nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'story_id', name='unique_like'),)

class History(db.Model):
    __tablename__ = 'history'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    story_id = db.Column(db.Integer, nullable=False)
    viewed_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'story_id', name='unique_history'),)

@app.before_request
def load_current_user():
    g.user = session.get('username')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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

# Route: index redirect
# Route: index redirect
@app.route('/')
def index():
    return redirect(url_for('login'))

# Route: signup
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        raw_password = request.form['password']

        hashed_password = generate_password_hash(raw_password)
        existing_user = User.query.filter_by(username=username).first()

        if existing_user:
            flash('⚠️ Username already exists. Please choose another one.', 'error')
            return redirect(url_for('signup'))

        new_user = User(username=username, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        session['username'] = username
        flash('Account created successfully. Welcome!')
        return redirect(url_for('home'))

    return render_template('signup.html')

# Route: login
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

    return render_template("login.html")

# Route: logout
@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('user_id', None)
    session.pop('is_admin', None)
    flash('You have been logged out.')
    return redirect(url_for('login'))

# Route: home
@app.route('/home')
def home():
    if 'username' not in session:
        return redirect(url_for('login'))

    stories = Story.query.order_by(Story.id.desc()).all()
    return render_template('home.html', stories=stories)

@app.route('/create-tables')
def create_tables():
    db.create_all()
    return "✅ Tables created successfully!"

@app.route('/chapter_audio/<int:chapter_id>')
def chapter_audio(chapter_id):
    audio_path = os.path.join(AUDIO_FOLDER, f'chapter_{chapter_id}.mp3')
    if os.path.exists(audio_path):
        return send_file(audio_path, mimetype='audio/mpeg')
    return "Audio not available", 404


# Route: add story
@app.route('/add_story', methods=['GET', 'POST'])
def add_story():
    if 'username' not in session:
        return redirect(url_for('login'))

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
            cover_path = os.path.join(UPLOAD_FOLDER, cover_filename)
            cover.save(cover_path)

        new_story = Story(
            title=title,
            description=description,
            status=status,
            cover_image=cover_filename,
            author=session.get('username')
        )
        db.session.add(new_story)
        db.session.commit()

        first_chapter = Chapter(
            story_id=new_story.id,
            title=chapter_title,
            content=chapter_content,
            author_name=session.get('username')
        )
        db.session.add(first_chapter)
        db.session.commit()

        return redirect(url_for('upload_chapter', story_id=new_story.id))

    return render_template('add_story.html')


@app.route('/submit', methods=['POST'])
def submit_story():
    if 'username' not in session:
        return redirect(url_for('login'))

    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    chapter_title = request.form.get('chapter_title', '').strip()
    chapter_content = request.form.get('chapter_content', '').strip()

    file = request.files.get('cover_image')
    cover_image_filename = ''

    upload_folder = os.path.join(app.root_path, 'static', 'covers')
    os.makedirs(upload_folder, exist_ok=True)

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Rename if file exists to avoid overwriting
        if os.path.exists(os.path.join(upload_folder, filename)):
            ext = filename.rsplit('.', 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{ext}"
        file.save(os.path.join(upload_folder, filename))
        cover_image_filename = filename
    elif file:
        return "Invalid file type. Allowed: png, jpg, jpeg, gif, webp", 400

    
    

    try:
        story = Story(
            title=title,
            description=description,
            cover_image=cover_image_filename,
            author=session['username']
        )
        db.session.add(story)
        db.session.flush()

        chapter = Chapter(
            story_id=story.id,
            title=chapter_title,
            content=chapter_content,
            author_name=session['username']
        )
        db.session.add(chapter)
        db.session.flush()

        audio_path = os.path.join(AUDIO_FOLDER, f'chapter_{chapter.id}.mp3')

        async def generate_audio():
            communicate = edge_tts.Communicate(chapter_content, voice="en-US-GuyNeural")
            await communicate.save(audio_path)

        asyncio.run(generate_audio())

        chapter.audio_file = f'chapter_{chapter.id}.mp3'
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        print("Error:", e)
        return "Internal Server Error", 500

    return redirect(url_for('home'))

# Route: read a story
@app.route('/read/<int:story_id>', methods=['GET', 'POST'])
def read_story(story_id):
    story = Story.query.get_or_404(story_id)
    chapter = Chapter.query.filter_by(story_id=story_id).first()

    if not chapter:
        return "No chapter found for this story", 404

    if request.method == 'POST':
        comment_text = request.form.get('comment')
        username = session.get('username', 'Anonymous')
        timestamp = datetime.now()

        new_comment = Comment(
            chapter_id=chapter.id,
            story_id=story_id,
            username=username,
            comment=comment_text,
            timestamp=timestamp,
            part=1
        )
        db.session.add(new_comment)
        db.session.commit()

        return redirect(url_for('read_story', story_id=story_id))

    comments = Comment.query.filter_by(chapter_id=chapter.id).all()

    return render_template(
        'read_story.html',
        story=story,
        chapter=chapter,
        comments=comments
    )


# Route: read specific chapter
@app.route('/chapter/<int:chapter_id>')
def read_chapter(chapter_id):
    chapter = Chapter.query.get_or_404(chapter_id)
    story = Story.query.get_or_404(chapter.story_id)
    next_chapter = (
        Chapter.query
        .filter(Chapter.story_id == chapter.story_id, Chapter.id > chapter_id)
        .order_by(Chapter.id.asc())
        .first()
    )
    next_chapter_id = next_chapter.id if next_chapter else None
    comments = Comment.query.filter_by(chapter_id=chapter_id).all()

    return render_template(
        'read_chapter.html',
        chapter=chapter,
        story=story,
        comments=comments,
        next_chapter_id=next_chapter_id
    )

# Route: upload chapter
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
            content=chapter_content,
            author_name=session.get('username')
        )
        db.session.add(new_chapter)
        db.session.commit()

        return redirect(url_for('view_story', story_id=story_id))

    return render_template('upload_chapter.html')

# Route: comment on chapter
@app.route('/comment/<int:chapter_id>', methods=['POST'])
def comment(chapter_id):
    text = request.form['comment']
    username = session.get('username', 'Anonymous')
    timestamp = datetime.now()

    new_comment = Comment(
        chapter_id=chapter_id,
        username=username,
        comment=text,
        timestamp=timestamp,
        story_id=Chapter.query.get_or_404(chapter_id).story_id,
        part=1  # You can update this logic for multiple parts
    )

    db.session.add(new_comment)
    db.session.commit()

    return redirect(url_for('read_chapter', chapter_id=chapter_id))

# Route: edit comment
@app.route('/comment/edit/<int:comment_id>', methods=['GET', 'POST'])
def edit_comment(comment_id):
    username = session.get('username')
    comment = Comment.query.get_or_404(comment_id)

    if comment.username != username:
        return redirect(url_for('read_chapter', chapter_id=comment.chapter_id))

    if request.method == 'POST':
        new_text = request.form['comment'].strip()
        if new_text:
            comment.comment = new_text
            db.session.commit()
        return redirect(url_for('read_chapter', chapter_id=comment.chapter_id))

    return render_template('edit_comment.html', comment=comment)

# Route: delete comment
@app.route('/comment/delete/<int:comment_id>')
def delete_comment(comment_id):
    username = session.get('username')
    comment = Comment.query.get_or_404(comment_id)

    if comment.username == username:
        db.session.delete(comment)
        db.session.commit()

    return redirect(url_for('read_chapter', chapter_id=comment.chapter_id))

# Route: story detail
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

    # ✅ 3. Check like status and count
    liked = False
    total_likes = 0
    if 'user_id' in session:
        user_id = session['user_id']
        liked = db.session.execute(
            text("SELECT 1 FROM likes WHERE user_id = :uid AND story_id = :sid"),
            {"uid": user_id, "sid": story_id}
        ).fetchone() is not None

    total_likes = db.session.execute(
        text("SELECT COUNT(*) FROM likes WHERE story_id = :sid"),
        {"sid": story_id}
    ).scalar()

    # ✅ 4. Fetch chapters
    chapters = Chapter.query.filter_by(story_id=story_id).all()

    return render_template(
        'story_detail.html',
        story=story,
        chapters=chapters,
        username=session.get('username'),
        liked=liked,
        total_likes=total_likes
    )

# Route: add chapter
@app.route('/story/<int:story_id>/add_chapter', methods=['GET', 'POST'])
def add_chapter(story_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    # Get the story so we can pass its title to the template
    story = Story.query.get_or_404(story_id)

    if request.method == 'POST':
        chapter_title = request.form['chapter_title']
        chapter_content = request.form['chapter_content']

        new_chapter = Chapter(
            story_id=story_id,
            title=chapter_title,
            content=chapter_content,
            author_name=session.get('username')
        )
        db.session.add(new_chapter)
        db.session.commit()

        return redirect(url_for('story_detail', story_id=story_id))

    return render_template('add_chapter.html', story_id=story_id, story_title=story.title)


@app.route('/edit_story/<int:story_id>', methods=['GET', 'POST'])
def edit_story(story_id):
    story = Story.query.get_or_404(story_id)

    if request.method == 'POST':
        story.title = request.form['title']
        story.description = request.form['description']
        story.status = request.form['status']

        file = request.files.get('cover_image')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            ext = filename.rsplit('.', 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{ext}"

            upload_folder = os.path.join(app.root_path, 'static', 'covers')
            os.makedirs(upload_folder, exist_ok=True)

            file.save(os.path.join(upload_folder, filename))

            # Update cover image filename in story
            story.cover_image = filename

        db.session.commit()
        return redirect(url_for('story_detail', story_id=story.id))

    return render_template('edit_story.html', story=story)

@app.route('/story/<int:story_id>/comment', methods=['POST'])
def add_comment(story_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    comment_text = request.form.get('comment')  # 👈 should match name="comment"

    if not comment_text:
        print("❌ Comment is missing or empty!")
        return "Missing comment field", 400

    new_comment = Comment(
        story_id=story_id,
        user_id=session['user_id'],
        comment=comment_text,  # 👈 not content=comment_text
        timestamp=datetime.now()
    )
    db.session.add(new_comment)
    db.session.commit()

    return redirect(url_for('read_story', story_id=story_id))



# Route: delete story
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
        return redirect(url_for('admin_panel') if is_admin else url_for('home'))

    db.session.delete(story)
    db.session.commit()
    flash('Story deleted successfully.')

    return redirect(url_for('admin_panel') if is_admin else url_for('home'))

# Route: view story (for upload_chapter redirect)
@app.route('/view_story/<int:story_id>')
def view_story(story_id):
    story = Story.query.get_or_404(story_id)
    chapters = Chapter.query.filter_by(story_id=story_id).all()
    return render_template('story_detail.html', story=story, chapters=chapters)

# Route: admin panel
@app.route('/admin')
def admin_panel():
    if 'username' not in session or not session.get('is_admin'):
        flash('Admin access only.', 'error')
        return redirect(url_for('home'))

    users = User.query.with_entities(User.id, User.username, User.email, User.is_admin).all()
    stories = Story.query.with_entities(Story.id, Story.title, Story.status, Story.reads, Story.votes).all()

    return render_template('admin.html', users=users, stories=stories)

# Route: make admin
@app.route('/make_admin/<int:user_id>', methods=['POST'])
def make_admin(user_id):
    if not session.get('is_admin'):
        return redirect(url_for('home'))

    user = User.query.get_or_404(user_id)
    user.is_admin = True
    db.session.commit()

    return redirect(url_for('admin_panel'))

# Route: delete user
@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if not session.get('is_admin'):
        return redirect(url_for('home'))

    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()

    return redirect(url_for('admin_panel'))

# Route: like a story
# Route: like a story
@app.route('/like/<int:story_id>', methods=['POST'])
def like_story(story_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    existing_like = db.session.execute(
        text("SELECT 1 FROM likes WHERE user_id = :uid AND story_id = :sid"),
        {"uid": user_id, "sid": story_id}
    ).fetchone()

    if not existing_like:
        db.session.execute(
            text("INSERT INTO likes (user_id, story_id) VALUES (:uid, :sid)"),
            {"uid": user_id, "sid": story_id}
        )
        db.session.execute(
            text("UPDATE stories SET votes = votes + 1 WHERE id = :sid"),
            {"sid": story_id}
        )
        db.session.commit()

    return redirect(url_for('story_detail', story_id=story_id))

# Route: user history
@app.route('/history')
def view_history():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    db_session = Session(db.engine)

    history = (
        db_session.query(History)
        .join(Story, History.story_id == Story.id)
        .filter(History.user_id == user_id)
        .order_by(desc(History.viewed_at))
        .with_entities(Story.id, Story.title, Story.cover_image)
        .all()
    )

    db_session.close()
    return render_template('history.html', history=history)

# Route: remove from history
@app.route('/history/remove/<int:story_id>', methods=['POST'])
def remove_from_history(story_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    db_session = Session(db.engine)

    entry = db_session.query(History).filter_by(user_id=user_id, story_id=story_id).first()
    if entry:
        db_session.delete(entry)
        db_session.commit()

    db_session.close()
    return redirect(url_for('view_history'))

# Route: search stories
@app.route('/search')
def search():
    query = request.args.get('q', '').strip().lower()
    db_session = Session(db.engine)

    # Search normally and also match hashtags like #bts
    results = db_session.execute(
        text("""
            SELECT * FROM stories 
            WHERE LOWER(title) LIKE :q 
               OR LOWER(description) LIKE :q 
               OR LOWER(description) LIKE :hashtag
        """),
        {
            "q": f"%{query}%",
            "hashtag": f"%#{query}%"  # Match #bts, #sunghoon etc.
        }
    ).fetchall()

    db_session.close()
    return render_template('search_results.html', query=query, results=results)

# Route: set theme
@app.route('/set_theme', methods=['POST'])
def set_theme():
    selected_theme = request.form.get('theme')
    session['theme'] = selected_theme
    return redirect(request.referrer or url_for('home'))

@app.route('/account')
def account():
    if 'username' not in session:
        return redirect(url_for('login'))
    user = User.query.filter_by(username=session['username']).first()
    return render_template('account.html', user=user)



if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        users = User.query.with_entities(User.username).all()
        print("📋 Existing users:")
        for username, in users:
            print(username)

    app.run(debug=True)
