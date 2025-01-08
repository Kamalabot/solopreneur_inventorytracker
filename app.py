from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    jsonify,
)
import sqlite3
from datetime import datetime
import csv
import io
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import json
from crawl4ai import AsyncWebCrawler
import asyncio
from asgiref.wsgi import WsgiToAsgi
from quart import Quart
from googleapiclient.discovery import build
from urllib.parse import urlparse, parse_qs
from database import init_db
from yt_dlp import YoutubeDL
from contextlib import contextmanager

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'  # make sure this is secure

# Define database functions first
def get_db():
    conn = sqlite3.connect('inventory.db', timeout=15)
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def get_db_connection():
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

# Then define init_db
def init_db():
    try:
        with get_db_connection() as conn:
            # Create users table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )
            ''')

            # Create videos table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT,
                    transcript TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
    except Exception as e:
        print(f"Database initialization error: {str(e)}")
        raise e

# Initialize database
init_db()

# Add custom Jinja2 filter for JSON parsing
@app.template_filter("from_json")
def from_json(value):
    return json.loads(value)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.")
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


@app.route("/")
def landing():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/dashboard")
@login_required
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
        
    try:
        with get_db_connection() as conn:
            videos = conn.execute(
                "SELECT * FROM videos WHERE user_id = ?", 
                (session["user_id"],)
            ).fetchall()
            return render_template("dashboard.html", videos=videos)
    except Exception as e:
        flash(f"Error loading dashboard: {str(e)}")
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        try:
            with get_db_connection() as conn:
                user = conn.execute(
                    "SELECT * FROM users WHERE username = ?", (username,)
                ).fetchone()

                if user and check_password_hash(user["password"], password):
                    session["user_id"] = user["id"]
                    session["username"] = user["username"]
                    flash("Welcome back!")
                    return redirect(url_for("dashboard"))

                flash("Invalid username or password")
        except Exception as e:
            flash(f"Login error: {str(e)}")
            
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        email = request.form["email"]

        try:
            with get_db_connection() as conn:
                # Check if username exists
                if conn.execute("SELECT id FROM users WHERE username = ?", 
                              (username,)).fetchone():
                    flash("Username already exists")
                    return redirect(url_for("register"))

                # Check if email exists
                if conn.execute("SELECT id FROM users WHERE email = ?", 
                              (email,)).fetchone():
                    flash("Email already registered")
                    return redirect(url_for("register"))

                # Hash the password before storing
                hashed_password = generate_password_hash(password)
                
                # Insert new user
                conn.execute(
                    "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                    (username, email, hashed_password)
                )

            flash("Registration successful! Please log in.")
            return redirect(url_for("login"))
            
        except sqlite3.IntegrityError:
            flash("Registration failed - user already exists")
            return redirect(url_for("register"))
        except Exception as e:
            flash(f"Registration failed - {str(e)}")
            return redirect(url_for("register"))

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("landing"))


@app.route("/add", methods=("GET", "POST"))
@login_required
def add_item():
    if request.method == "POST":
        name = request.form["name"]
        quantity = request.form["quantity"]
        category = request.form["category"]
        sector = request.form["sector"]
        application = request.form["application"]

        if not name or not quantity:
            flash("Name and quantity are required!")
        else:
            conn = get_db_connection()
            conn.execute(
                """INSERT INTO inventory 
                          (name, quantity, category, sector, application, user_id) 
                          VALUES (?, ?, ?, ?, ?, ?)""",
                (name, quantity, category, sector, application, session["user_id"]),
            )
            conn.commit()
            conn.close()
            flash("Item successfully added!")
            return redirect(url_for("dashboard"))

    return render_template("add_item.html")


@app.route("/upload_csv", methods=("GET", "POST"))
@login_required
def upload_csv():
    if request.method == "POST":
        if "file" not in request.files:
            flash("No file selected")
            return redirect(url_for("upload_csv"))

        file = request.files["file"]
        if file.filename == "":
            flash("No file selected")
            return redirect(url_for("upload_csv"))

        if file and file.filename.endswith(".csv"):
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_data = csv.reader(stream)

            conn = get_db_connection()
            success_count = 0
            error_count = 0

            for row in csv_data:
                try:
                    name, quantity, category, sector, application, *_ = row
                    conn.execute(
                        """
                        INSERT INTO inventory (name, quantity, category, sector, application, user_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """,
                        (
                            name.strip(),
                            int(quantity),
                            category.strip(),
                            sector.strip(),
                            application.strip(),
                            session["user_id"],
                        ),
                    )
                    success_count += 1
                except Exception as e:
                    error_count += 1
                    continue

            conn.commit()
            conn.close()

            flash(
                f"Successfully imported {success_count} items. {error_count} items failed."
            )
            return redirect(url_for("dashboard"))
        else:
            flash("Please upload a CSV file")
            return redirect(url_for("upload_csv"))

    return render_template("upload_csv.html")


@app.route("/update_quantity/<int:item_id>", methods=["PUT"])
@login_required
def update_quantity(item_id):
    try:
        quantity = int(request.form.get("value", 0))
        if quantity < 0:
            return "Quantity cannot be negative", 400

        conn = get_db_connection()
        # Verify the item belongs to the current user
        item = conn.execute(
            "SELECT * FROM inventory WHERE id = ? AND user_id = ?",
            (item_id, session["user_id"]),
        ).fetchone()

        if not item:
            conn.close()
            return "Item not found", 404

        conn.execute(
            "UPDATE inventory SET quantity = ? WHERE id = ? AND user_id = ?",
            (quantity, item_id, session["user_id"]),
        )
        conn.commit()
        conn.close()

        return render_template(
            "partials/inventory_row.html",
            item={
                "id": item_id,
                "quantity": quantity,
                "name": item["name"],
                "category": item["category"],
                "sector": item["sector"],
                "application": item["application"],
                "date_added": item["date_added"],
            },
        )
    except ValueError:
        return "Invalid quantity value", 400
    except Exception as e:
        return str(e), 500


@app.route("/delete_item/<int:item_id>", methods=["DELETE"])
@login_required
def delete_item(item_id):
    try:
        conn = get_db_connection()
        # Verify the item belongs to the current user
        result = conn.execute(
            "DELETE FROM inventory WHERE id = ? AND user_id = ?",
            (item_id, session["user_id"]),
        )
        conn.commit()
        conn.close()

        if result.rowcount == 0:
            return "Item not found", 404

        return "", 204
    except Exception as e:
        return str(e), 500


@app.route("/crawl", methods=["GET", "POST"])
@login_required
def crawl_website():
    if request.method == "POST":
        url = request.form["url"]
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def perform_crawl():
                async with AsyncWebCrawler(
                    verbose=True,
                    timeout=30,
                    wait_for_selector=".article-content",
                    wait_time=2,
                    browser_type="chromium",
                    headless=True,
                    javascript_enabled=True,
                    ignore_https_errors=True,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    html2text={
                        "escape_dot": False,
                        "body_width": 0,
                        "protect_links": True,
                        "unicode_snob": True,
                    },
                ) as crawler:
                    result = await crawler.arun(
                        url=url,
                        word_count_threshold=10,  # Minimum words per block
                        exclude_external_links=True,  # Remove external links
                        exclude_external_images=True,  # Remove external images
                        excluded_tags=["form", "nav"],  # Remove specific HTML tags
                        include_links_on_markdown=True,  # Include links in markdown
                    )

                    # Debug print of all available formats
                    print("\n=== Crawl Results ===")
                    print(f"URL: {result.url}")
                    print(f"Status Code: {result.status_code}")

                    print("\n=== Raw HTML (first 200 chars) ===")
                    print(result.html[:200] if result.html else "No HTML content")

                    print("\n=== Cleaned HTML (first 200 chars) ===")
                    print(
                        result.cleaned_html[:200]
                        if hasattr(result, "cleaned_html")
                        else "No cleaned HTML"
                    )

                    print("\n=== Standard Markdown (first 200 chars) ===")
                    print(
                        result.markdown[:200]
                        if result.markdown
                        else "No markdown content"
                    )

                    print(
                        "\n=== Fit Markdown (most relevant content, first 200 chars) ==="
                    )
                    print(
                        result.fit_markdown[:200]
                        if hasattr(result, "fit_markdown")
                        else "No fit markdown"
                    )

                    print("\nFirst 5 links:")
                    print(list(result.links)[:5] if result.links else "No links found")

                    print("\nHeaders:")
                    print(
                        dict(result.headers)
                        if hasattr(result, "headers")
                        else "No headers"
                    )
                    print("===================\n")

                    return result

            result = loop.run_until_complete(perform_crawl())
            loop.close()

            # Store all available formats
            crawl_data = {
                "url": url,
                "html": result.html,  # Original HTML
                "cleaned_html": (
                    result.cleaned_html if hasattr(result, "cleaned_html") else None
                ),  # Sanitized HTML
                "markdown": result.markdown,  # Standard markdown
                "fit_markdown": (
                    result.fit_markdown if hasattr(result, "fit_markdown") else None
                ),  # Most relevant content
                "links": list(result.links) if result.links else [],
                "status_code": (
                    result.status_code if hasattr(result, "status_code") else None
                ),
                "headers": dict(result.headers) if hasattr(result, "headers") else {},
                "timestamp": datetime.now().isoformat(),
            }

            conn = get_db_connection()
            conn.execute(
                """
                INSERT INTO crawled_data (user_id, url, crawl_data, status)
                VALUES (?, ?, ?, ?)
            """,
                (session["user_id"], url, json.dumps(crawl_data), "completed"),
            )
            conn.commit()
            conn.close()

            flash("Website crawled successfully!")
            return redirect(url_for("crawl_history"))
        except Exception as e:
            print(f"\nError during crawl: {str(e)}\n")
            flash(f"Error crawling website: {str(e)}")
            return redirect(url_for("crawl_website"))

    return render_template("crawl.html")


@app.route("/crawl_history")
def crawl_history():
    if "user_id" not in session:
        return redirect(url_for("login"))
        
    try:
        with get_db_connection() as conn:
            # Fetch crawl history for the user
            history = conn.execute(
                "SELECT * FROM videos WHERE user_id = ? ORDER BY created_at DESC", 
                (session["user_id"],)
            ).fetchall()
            
            return render_template(
                "crawl_history.html", 
                history=history
            )
    except Exception as e:
        flash(f"Error loading crawl history: {str(e)}")
        return redirect(url_for("dashboard"))


@app.route("/crawl-details/<int:crawl_id>")
@login_required
def crawl_details(crawl_id):
    conn = get_db_connection()
    crawl = conn.execute(
        """
        SELECT * FROM crawled_data 
        WHERE id = ? AND user_id = ?
    """,
        (crawl_id, session["user_id"]),
    ).fetchone()
    conn.close()

    if crawl is None:
        flash("Crawl not found")
        return redirect(url_for("crawl_history"))

    return render_template("crawl_details.html", crawl=crawl)


def extract_youtube_data(url):
    try:
        # First get the channel URL from the video
        with YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            channel_url = info.get('channel_url') or info.get('uploader_url')
            
            if not channel_url:
                # If no channel URL found, just return the single video
                return [{
                    'video_id': info.get('id'),
                    'title': info.get('title'),
                    'url': info.get('webpage_url') or f'https://youtube.com/watch?v={info.get("id")}',
                    'thumbnail_url': info.get('thumbnail'),
                    'channel_name': info.get('uploader')
                }]

        # Now fetch all videos from the channel
        ydl_opts = {
            'quiet': True,
            'extract_flat': True,
            'force_generic_extractor': False,
            'ignoreerrors': True,
            'extract_flat_playlist': True,
            'playlistend': 50  # Limit to latest 50 videos
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            print(f"Fetching videos from channel: {channel_url}")
            channel_info = ydl.extract_info(channel_url, download=False)
            
            if not channel_info:
                print("No channel information found")
                return None

            videos = []
            if 'entries' in channel_info:
                for entry in channel_info['entries']:
                    if entry and all(key in entry for key in ['id', 'title']):
                        # Get best thumbnail
                        thumbnail_url = entry.get('thumbnail')
                        if isinstance(entry.get('thumbnails'), list):
                            thumbnails = sorted(
                                entry['thumbnails'], 
                                key=lambda x: x.get('height', 0) * x.get('width', 0),
                                reverse=True
                            )
                            if thumbnails:
                                thumbnail_url = thumbnails[0].get('url')

                        video = {
                            'video_id': entry.get('id'),
                            'title': entry.get('title'),
                            'url': entry.get('webpage_url') or f'https://youtube.com/watch?v={entry.get("id")}',
                            'thumbnail_url': thumbnail_url,
                            'channel_name': entry.get('uploader') or channel_info.get('uploader')
                        }
                        
                        # Only add if all required fields are present
                        if all(video.values()):
                            videos.append(video)
                
                print(f"Found {len(videos)} videos in channel")
                return videos
            else:
                print("No entries found in channel info")
                return None

    except Exception as e:
        print(f"Error in extract_youtube_data: {str(e)}")
        return None


@app.route('/add_youtube', methods=['POST'])
@login_required
def add_youtube():
    url = request.form.get('youtube_url')
    if not url:
        flash('Please provide a YouTube URL')
        return redirect(url_for('dashboard'))
    
    try:
        print(f"Processing URL: {url}")
        videos = extract_youtube_data(url)
        
        if videos:
            conn = get_db_connection()
            added_count = 0
            skipped_count = 0
            
            for video in videos:
                # Check if video already exists
                existing = conn.execute(
                    'SELECT id FROM youtube_data WHERE video_id = ? AND user_id = ?',
                    (video['video_id'], session['user_id'])
                ).fetchone()
                
                if not existing:
                    try:
                        conn.execute('''
                            INSERT INTO youtube_data 
                            (user_id, video_id, title, url, thumbnail_url, channel_name)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (
                            session['user_id'],
                            video['video_id'],
                            video['title'],
                            video['url'],
                            video['thumbnail_url'],
                            video['channel_name']
                        ))
                        added_count += 1
                    except Exception as e:
                        print(f"Error inserting video {video['video_id']}: {str(e)}")
                        continue
                else:
                    skipped_count += 1
            
            conn.commit()
            conn.close()
            
            if added_count > 0:
                flash(f'Successfully added {added_count} new videos! ({skipped_count} already existed)')
            else:
                flash(f'No new videos were added. {skipped_count} videos already existed in your collection.')
        else:
            flash('No videos found or invalid URL')
    except Exception as e:
        print(f"Error in add_youtube: {str(e)}")
        flash(f'Error processing YouTube URL: {str(e)}')
    
    return redirect(url_for('dashboard'))


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        try:
            video_url = request.form.get("video_url")
            if not video_url:
                flash("Please provide a video URL")
                return redirect(url_for("upload"))

            # Your existing video processing logic here...
            
            with get_db_connection() as conn:
                conn.execute(
                    "INSERT INTO videos (url, user_id, title, transcript) VALUES (?, ?, ?, ?)",
                    (video_url, session["user_id"], title, transcript)
                )
                
            flash("Video uploaded successfully!")
            return redirect(url_for("dashboard"))
            
        except Exception as e:
            flash(f"Upload error: {str(e)}")
            return redirect(url_for("upload"))
            
    return render_template("upload.html")


@app.route("/video/<int:video_id>")
def video_detail(video_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
        
    try:
        with get_db_connection() as conn:
            video = conn.execute(
                "SELECT * FROM videos WHERE id = ? AND user_id = ?",
                (video_id, session["user_id"])
            ).fetchone()
            
            if video is None:
                flash("Video not found")
                return redirect(url_for("dashboard"))
                
            return render_template("video_detail.html", video=video)
    except Exception as e:
        flash(f"Error loading video: {str(e)}")
        return redirect(url_for("dashboard"))


@app.route("/delete/<int:video_id>", methods=["POST"])
def delete_video(video_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
        
    try:
        with get_db_connection() as conn:
            conn.execute(
                "DELETE FROM videos WHERE id = ? AND user_id = ?",
                (video_id, session["user_id"])
            )
            
        flash("Video deleted successfully")
    except Exception as e:
        flash(f"Error deleting video: {str(e)}")
        
    return redirect(url_for("dashboard"))


@app.route("/search", methods=["GET", "POST"])
def search():
    if "user_id" not in session:
        return redirect(url_for("login"))
        
    if request.method == "POST":
        query = request.form.get("query", "")
        try:
            with get_db_connection() as conn:
                videos = conn.execute(
                    """SELECT * FROM videos 
                       WHERE user_id = ? AND 
                       (title LIKE ? OR transcript LIKE ?)""",
                    (session["user_id"], f"%{query}%", f"%{query}%")
                ).fetchall()
                
            return render_template("search_results.html", videos=videos, query=query)
        except Exception as e:
            flash(f"Search error: {str(e)}")
            return redirect(url_for("dashboard"))
            
    return render_template("search.html")


@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))
        
    try:
        with get_db_connection() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (session["user_id"],)
            ).fetchone()
            
            if user is None:
                session.clear()
                return redirect(url_for("login"))
                
            return render_template("profile.html", user=user)
    except Exception as e:
        flash(f"Error loading profile: {str(e)}")
        return redirect(url_for("dashboard"))


@app.route('/upload_csv_file', methods=['POST'])
def upload_csv_file():
    if 'file' not in request.files:
        return 'No file uploaded', 400

    file = request.files['file']
    if file.filename == '':
        return 'No file selected', 400

    try:
        with get_db_connection() as conn:
            csv_file = TextIOWrapper(file.stream, encoding='utf-8')
            csv_reader = csv.reader(csv_file)
            next(csv_reader)  # Skip header row
            
            for row in csv_reader:
                conn.execute(
                    "INSERT INTO inventory (item_name, quantity, price) VALUES (?, ?, ?)",
                    (row[0], row[1], row[2])
                )
            
        return 'File uploaded successfully', 200
    except Exception as e:
        flash(f"Error uploading CSV: {str(e)}")
        return f'Error uploading file: {str(e)}', 500


@app.route('/upload_csv_data', methods=['POST'])
def upload_csv_data():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        with get_db_connection() as conn:
            for item in data:
                conn.execute(
                    "INSERT INTO inventory (item_name, quantity, price) VALUES (?, ?, ?)",
                    (item['name'], item['quantity'], item['price'])
                )
            
        return jsonify({'message': 'Data uploaded successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == "__main__":
    from database import init_db
    init_db()  # Initialize database tables
    app.run(debug=True)
