import sqlite3
from flask import g
from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
from dotenv import load_dotenv
load_dotenv()
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'devfallbacksecret')

conn = sqlite3.connect('stories.db', check_same_thread=False)  # Replace with your DB name
conn.row_factory = sqlite3.Row  # ✅ ADD THIS LINE HERE
cur = conn.cursor()


UPLOAD_FOLDER = 'static/covers'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initial setup: create tables if they don't exist
def init_db():
    with sqlite3.connect('stories.db') as conn:
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS stories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                cover_image TEXT,
                description TEXT,
                reads INTEGER DEFAULT 0,
                votes INTEGER DEFAULT 0,
                parts INTEGER DEFAULT 1,
                status TEXT DEFAULT 'Ongoing'
            )
        ''')

        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                
                password TEXT NOT NULL
                
            )
        ''')
        

        # ✅ Add this comment table here:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                story_id INTEGER,
                part INTEGER,
                username TEXT,
                comment TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (story_id) REFERENCES stories(id)
            )
        ''')
        conn.commit()



init_db()


@app.before_request
def load_current_user():
    g.user = session.get('user')


import sqlite3

with sqlite3.connect('stories.db') as conn:
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
        print("✅ 'is_admin' column added.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("ℹ️ 'is_admin' column already exists.")
        else:
            raise


@app.route('/insert_dummy')
def insert_dummy():
    with sqlite3.connect('stories.db') as conn:
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO stories (title, cover_image, description, reads, votes, parts, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            'My First Story',
            '/static/cover1.jpg',
            'This is a description of the first story. It\'s about dreams and fate.',
            150,
            20,
            5,
            'Ongoing'
        ))
        conn.commit()
    return "Dummy story inserted!"

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

    with sqlite3.connect('stories.db') as conn:
        conn.row_factory = sqlite3.Row  # ✅ Important!
        cur = conn.cursor()
        cur.execute("SELECT * FROM stories ORDER BY id DESC")
        stories = cur.fetchall()

    return render_template('home.html', stories=stories)



@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        with sqlite3.connect('stories.db') as conn:
            cur = conn.cursor()
            try:
                cur.execute("INSERT INTO users (username, password, email) VALUES (?, ?, ?)",
                            (username, password, email))
                conn.commit()
                flash('Account created successfully. Please log in.')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('⚠️ Username already exists. Please choose another one.', 'error')
                return redirect(url_for('signup'))

    return render_template('signup.html')


from werkzeug.utils import secure_filename
import os

@app.route('/add_story', methods=['GET', 'POST'])
def add_story():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        status = request.form['status']
        chapter_title = request.form['chapter_title']
        chapter_content = request.form['chapter_content']

        cover = request.files.get('cover_image')  # ✅ match form
        cover_filename = None

        if cover and cover.filename != '':
            cover_filename = secure_filename(cover.filename)
            cover.save(os.path.join(app.config['UPLOAD_FOLDER'], cover_filename))

        with sqlite3.connect('stories.db') as conn:
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO stories (title, description, status, cover_image, author)
                VALUES (?, ?, ?, ?, ?)
            """, (title, description, status, cover_filename, session['username']))
            story_id = cur.lastrowid

            cur.execute("""
                INSERT INTO chapters (story_id, title, content)
                VALUES (?, ?, ?)
            """, (story_id, chapter_title, chapter_content))

            conn.commit()

        return redirect(url_for('upload_chapter.html', story_id=story_id))

    return render_template('add_story.html')

from gtts import gTTS

import sqlite3

conn = sqlite3.connect('stories.db')
cur = conn.cursor()

# Add the column only if it doesn't exist
try:
    cur.execute("ALTER TABLE chapters ADD COLUMN audio_file TEXT")
    print("✅ Column 'audio_file' added successfully.")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("ℹ️ Column 'audio_file' already exists.")
    else:
        raise
conn.commit()
conn.close()
       


from werkzeug.utils import secure_filename
import os
import sqlite3
from flask import request, session, redirect, url_for

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
UPLOAD_FOLDER = os.path.join('static', 'covers')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

import os
import asyncio
import edge_tts
import sqlite3

@app.route('/submit', methods=['POST'])
def submit_story():
    if 'username' not in session:
        return redirect(url_for('login'))

    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()

    file = request.files.get('cover_image')
    cover_image_filename = ''

    if file and file.filename != '':
        if allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)

            # Avoid filename conflict
            if os.path.exists(filepath):
                import uuid
                ext = filename.rsplit('.', 1)[1].lower()
                filename = f"{uuid.uuid4().hex}.{ext}"
                filepath = os.path.join(UPLOAD_FOLDER, filename)

            file.save(filepath)
            cover_image_filename = filename
        else:
            return "Invalid file type. Allowed: png, jpg, jpeg, gif, webp", 400

    chapter_title = request.form.get('chapter_title', '').strip()
    chapter_content = request.form.get('chapter_content', '').strip()

    with sqlite3.connect('stories.db') as conn:
        cur = conn.cursor()

        # Insert into stories
        cur.execute('''
            INSERT INTO stories (title, description, cover_image, author)
            VALUES (?, ?, ?, ?)
        ''', (title, description, cover_image_filename, session['username']))
        story_id = cur.lastrowid

        # Insert first chapter
        cur.execute('''
            INSERT INTO chapters (story_id, title, content)
            VALUES (?, ?, ?)
        ''', (story_id, chapter_title, chapter_content))
        chapter_id = cur.lastrowid

        # ✅ Generate audio using edge-tts
        try:
            audio_folder = os.path.join('static', 'audios')
            os.makedirs(audio_folder, exist_ok=True)
            audio_path = os.path.join(audio_folder, f'chapter_{chapter_id}.mp3')

            async def generate_audio():
                communicate = edge_tts.Communicate(chapter_content, voice="en-US-GuyNeural")
                await communicate.save(audio_path)

            asyncio.run(generate_audio())

        except Exception as e:
            print("Error generating audio:", e)

        # ✅ Commit changes after all database + audio logic
        conn.commit()

    return redirect(url_for('home'))



@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('You have been logged out.')
    return redirect(url_for('login'))

@app.route('/account')
def account():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']

    with sqlite3.connect('stories.db') as conn:
        conn.row_factory = sqlite3.Row  # ✅ to access results like a dictionary
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cur.fetchone()

    return render_template('account.html', user=user)

@app.route('/read/<int:story_id>', methods=['GET', 'POST'])
def read_story(story_id):
    with sqlite3.connect('stories.db') as conn:
        conn.row_factory = sqlite3.Row 
        cur = conn.cursor()

        # Get story info
        cur.execute("SELECT * FROM stories WHERE id=?", (story_id,))
        story = cur.fetchone()

        # Get the specific chapter/part
        cur.execute("SELECT * FROM story_parts WHERE story_id=?" , (story_id))
        chapter = cur.fetchone()

        # Get comments
        cur.execute("SELECT * FROM comments WHERE story_id=? ", (story_id))
        comments = cur.fetchall()

    return render_template(
        'read_story.html',
        story=story,
        
        chapter=chapter,  # ✅ now it's passed to the template
        comments=comments
    )


@app.route('/edit/<int:story_id>', methods=['GET', 'POST'])
def edit_story(story_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    with sqlite3.connect('stories.db') as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM stories WHERE id=?", (story_id,))
        story = cur.fetchone()

        if story['author'] != session['username']:
            flash("You can't edit someone else's story!")
            return redirect(url_for('home'))

        # Continue with editing logic...

@app.route('/story/<int:story_id>/part/<int:part>/comment', methods=['POST'])
def add_comment(story_id, part):
    username = request.form['username']
    comment = request.form['comment']

    with sqlite3.connect('stories.db') as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO comments (story_id, part, username, comment) VALUES (?, ?, ?, ?)",
            (story_id, part, username, comment)
        )
        conn.commit()

    return redirect(url_for('read_story', story_id=story_id, part=part))

@app.route('/delete_story/<int:story_id>', methods=['POST'])
def delete_story(story_id):
    if 'user_id' not in session and not session.get('is_admin'):
        flash('You need to log in to delete a story.')
        return redirect(url_for('login'))

    user_id = session.get('user_id')
    is_admin = session.get('is_admin', False)

    with sqlite3.connect('stories.db') as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        if is_admin:
            # Admin can delete any story
            cur.execute("SELECT * FROM stories WHERE id = ?", (story_id,))
        else:
            # Author can only delete their own story
            cur.execute("SELECT * FROM stories WHERE id = ? AND author = ?", (story_id, user_id))

        story = cur.fetchone()

        if story is None:
            flash('Story not found or you do not have permission to delete it.')
            return redirect(url_for('admin_panel') if is_admin else url_for('my_stories'))

        # Delete the story
        cur.execute("DELETE FROM stories WHERE id = ?", (story_id,))
        conn.commit()
        flash('Story deleted successfully.')

    return redirect(url_for('admin_panel') if is_admin else url_for('my_stories'))


def get_db_connection():
    conn = sqlite3.connect('stories.db')
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/story/<int:story_id>')
def story_detail(story_id):
    conn = sqlite3.connect('stories.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ✅ increment read count
    cur.execute('UPDATE stories SET reads = reads + 1 WHERE id = ?', (story_id,))
    conn.commit()

    # ✅ Save reading history only if user is logged in
    if 'user_id' in session:
        user_id = session['user_id']
        cur.execute('''
            INSERT OR IGNORE INTO history (user_id, story_id)
            VALUES (?, ?)
        ''', (user_id, story_id))
        conn.commit()

    # Fetch story and chapters
    cur.execute('SELECT * FROM stories WHERE id = ?', (story_id,))
    story = cur.fetchone()

    cur.execute('SELECT * FROM chapters WHERE story_id = ?', (story_id,))
    chapters = cur.fetchall()

    conn.close()

    return render_template(
        'story_detail.html',
        story=story,
        chapters=chapters,
        username=session.get('username')
    )


# Read chapter
@app.route('/chapter/<int:chapter_id>')
def read_chapter(chapter_id):
    conn = sqlite3.connect('stories.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Current chapter
    cur.execute('SELECT * FROM chapters WHERE id = ?', (chapter_id,))
    chapter = cur.fetchone()

    # Story details
    cur.execute('SELECT * FROM stories WHERE id = ?', (chapter['story_id'],))
    story = cur.fetchone()

    # Next chapter in same story
    cur.execute('''
        SELECT id FROM chapters 
        WHERE story_id = ? AND id > ? 
        ORDER BY id ASC LIMIT 1
    ''', (chapter['story_id'], chapter_id))
    next_chapter_row = cur.fetchone()
    next_chapter_id = next_chapter_row['id'] if next_chapter_row else None

    # Comments
    cur.execute('SELECT * FROM comments WHERE chapter_id = ?', (chapter_id,))
    comments = cur.fetchall()

    conn.close()

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
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # add this line

    conn = sqlite3.connect('stories.db')
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO comments (chapter_id, username, comment, timestamp)
        VALUES (?, ?, ?, ?)
    """, (chapter_id, username, text, timestamp))  # add timestamp here

    conn.commit()
    conn.close()

    return redirect(url_for('read_chapter', chapter_id=chapter_id))


from datetime import datetime

@app.template_filter('datetimeformat')
def datetimeformat(value):
    if not value:
        return "Unknown time"
    try:
        dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        return dt.strftime('%B %d, %I:%M %p')
    except Exception:
        return str(value)  # fallback if parsing fails

@app.route('/comment/delete/<int:comment_id>')
def delete_comment(comment_id):
    username = session.get('username')

    conn = sqlite3.connect('stories.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))
    comment = cur.fetchone()

    if comment and comment['username'] == username:
        cur.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
        conn.commit()

    conn.close()
    return redirect(url_for('read_chapter', chapter_id=comment['chapter_id']))


@app.route('/comment/edit/<int:comment_id>', methods=['GET', 'POST'])
def edit_comment(comment_id):
    username = session.get('username')

    conn = sqlite3.connect('stories.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))
    comment = cur.fetchone()

    if request.method == 'POST':
        new_text = request.form['comment']
        if comment and comment['username'] == username:
            cur.execute("UPDATE comments SET comment = ? WHERE id = ?", (new_text, comment_id))
            conn.commit()
        conn.close()
        return redirect(url_for('read_chapter', chapter_id=comment['chapter_id']))

    conn.close()
    return render_template('edit_comment.html', comment=comment)



import sqlite3

with sqlite3.connect("your_database.db", timeout=10) as conn:
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id INTEGER,
            title TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (story_id) REFERENCES stories(id)
        )
    ''')
    print("✅ 'chapters' table created successfully.")

    cursor.execute('''
        INSERT INTO chapters (story_id, title, content)
        VALUES (?, ?, ?)
    ''', (1, 'Chapter 1: The Beginning', 'This is the content of the first chapter.'))

    conn.commit()

@app.route('/add_chapter/<int:story_id>', methods=['GET', 'POST'])
def add_chapter(story_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']

        with sqlite3.connect('stories.db') as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO chapters (story_id, title, content)
                VALUES (?, ?, ?)
            """, (story_id, title, content))
            conn.commit()

        return redirect(url_for('story_detail', story_id=story_id))

    with sqlite3.connect('stories.db') as conn:
        cur = conn.cursor()
        cur.execute("SELECT title FROM stories WHERE id=?", (story_id,))
        story_title = cur.fetchone()[0]

    return render_template("add_chapter.html", story_id=story_id, story_title=story_title)

    


@app.route('/admin')
def admin_panel():
    if not session.get('is_admin'):
        return redirect(url_for('home'))

    with sqlite3.connect('stories.db') as conn:
        cursor = conn.cursor()
        # Include email in the SELECT query
        cursor.execute("SELECT id, username, email, is_admin FROM users")
        users = cursor.fetchall()

        cursor.execute("SELECT id, title, status, reads, votes FROM stories")
        stories = cursor.fetchall()

    return render_template('admin.html', users=users, stories=stories)

import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
import sqlite3

load_dotenv()  # ✅ this loads .env values

admin_username = os.getenv("ADMIN_USERNAME")
admin_email = os.getenv("ADMIN_EMAIL")
admin_password = os.getenv("ADMIN_PASSWORD")

if not admin_username or not admin_email or not admin_password:
    print("❌ Missing admin credentials in .env")
else:
    hashed_password = generate_password_hash(admin_password)

    with sqlite3.connect("stories.db") as conn:
        cur = conn.cursor()
        try:
            cur.execute('''
                INSERT INTO users (username, email, password, is_admin)
                VALUES (?, ?, ?, ?)
            ''', (admin_username, admin_email, hashed_password, 1))
            conn.commit()
            print("✅ Admin user created securely.")
        except sqlite3.IntegrityError as e:
            print("❌ Error:", e)



import sqlite3

with sqlite3.connect("stories.db") as conn:
    cur = conn.cursor()
    cur.execute("SELECT username FROM users")
    rows = cur.fetchall()
    print("Existing usernames:")
    for row in rows:
        print(row[0])

import sqlite3

with sqlite3.connect("stories.db") as conn:
    cur = conn.cursor()
    
    
    cur.execute('''
        DELETE FROM users
        WHERE is_admin = 1 AND username != 'Khushi_Singh_four'
    ''')

    conn.commit()
   


import sqlite3

with sqlite3.connect("stories.db") as conn:
    cur = conn.cursor()
    cur.execute("SELECT id, username, password, is_admin FROM users")
    users = cur.fetchall()

    print("📋 Current Users:")
    for user in users:
        print(user)

@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if not session.get('is_admin'):
        return redirect(url_for('home'))
    
    with sqlite3.connect("stories.db") as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    
    return redirect(url_for('admin_panel'))


@app.route('/make_admin/<int:user_id>', methods=['POST'])
def make_admin(user_id):
    if not session.get('is_admin'):
        return redirect(url_for('home'))

    with sqlite3.connect("stories.db") as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))
        conn.commit()

    return redirect(url_for('admin_panel'))

@app.route('/story/<int:story_id>/upload_chapter', methods=['GET', 'POST'])
def upload_chapter(story_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        chapter_title = request.form['chapter_title']
        chapter_content = request.form['chapter_content']

        with sqlite3.connect('stories.db') as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO chapters (story_id, title, content)
                VALUES (?, ?, ?)
            """, (story_id, chapter_title, chapter_content))
            conn.commit()

        return redirect(url_for('view_story', story_id=story_id))

    return render_template('upload_chapter.html')


with sqlite3.connect("stories.db") as conn:
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS story_parts")
    conn.commit()
    print("✅ 'story_parts' table removed.")

with sqlite3.connect('stories.db') as conn:
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE comments ADD COLUMN chapter_id INTEGER")
        print("✅ 'chapter_id' added to comments.")
    except sqlite3.OperationalError as e:
        if 'duplicate column name' in str(e):
            print("ℹ️ 'chapter_id' already exists.")
        else:
            raise


import sqlite3

conn = sqlite3.connect('stories.db')
cur = conn.cursor()

# Add views column only if it doesn't exist
try:
    cur.execute("ALTER TABLE chapters ADD COLUMN views INTEGER DEFAULT 0")
    conn.commit()
    print("✅ 'views' column added.")
except sqlite3.OperationalError as e:
    print("⚠️", e)

conn.close()


@app.route('/search')
def search():
    query = request.args.get('q', '').strip()

    conn = sqlite3.connect('stories.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM stories WHERE title LIKE ? OR description LIKE ?", (f'%{query}%', f'%{query}%'))
    results = cur.fetchall()

    conn.close()

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

    conn = sqlite3.connect('stories.db')
    cur = conn.cursor()

    # Check if user already liked the story
    cur.execute("SELECT 1 FROM likes WHERE user_id = ? AND story_id = ?", (user_id, story_id))
    already_liked = cur.fetchone()

    if not already_liked:
        # Record like and update count
        cur.execute("INSERT INTO likes (user_id, story_id) VALUES (?, ?)", (user_id, story_id))
        cur.execute("UPDATE stories SET likes = likes + 1 WHERE id = ?", (story_id,))
        conn.commit()

    conn.close()
    return redirect(url_for('home'))

conn = sqlite3.connect('stories.db')
cur = conn.cursor()

cur.execute('''

CREATE TABLE IF NOT EXISTS likes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    story_id INTEGER,
    UNIQUE(user_id, story_id)
)
''')
conn.commit()
conn.close()


conn = sqlite3.connect('stories.db')
cur = conn.cursor()

cur.execute('''

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    story_id INTEGER NOT NULL,
    viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, story_id)
)
''')
conn.commit()
conn.close()

@app.route('/history')
def view_history():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    with sqlite3.connect('stories.db') as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute('''
            SELECT s.id, s.title, s.cover_image
            FROM history h
            JOIN stories s ON h.story_id = s.id
            WHERE h.user_id = ?
            ORDER BY h.viewed_at DESC
        ''', (user_id,))
        history = cur.fetchall()
    
    return render_template('history.html', history=history)

@app.route('/history/remove/<int:story_id>', methods=['POST'])
def remove_from_history(story_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    with sqlite3.connect('stories.db') as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM history WHERE user_id = ? AND story_id = ?", (user_id, story_id))
        conn.commit()

    return redirect(url_for('view_history'))


@app.route('/chapter_audio/<int:chapter_id>')
def chapter_audio(chapter_id):
    audio_path = f'static/audios/chapter_{chapter_id}.mp3'
    if os.path.exists(audio_path):
        return redirect('/' + audio_path)
    return "Audio not available", 404


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
