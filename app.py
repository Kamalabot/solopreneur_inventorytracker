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
from crawl4ai import AsyncWebCrawler  # Correct import
import asyncio
from asgiref.wsgi import WsgiToAsgi
from quart import Quart

app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # Required for flashing messages and sessions


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


def get_db_connection():
    conn = sqlite3.connect("inventory.db")
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def landing():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/dashboard")
@login_required
def dashboard():
    try:
        conn = get_db_connection()
        items = conn.execute(
            "SELECT * FROM inventory WHERE user_id = ? ORDER BY date_added DESC",
            (session["user_id"],),
        ).fetchall()
        conn.close()

        # Convert items to list of dictionaries for better handling
        items_list = []
        for item in items:
            items_list.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "quantity": item["quantity"],
                    "category": item["category"],
                    "sector": item["sector"],
                    "application": item["application"],
                    "date_added": item["date_added"],
                }
            )

        return render_template("dashboard.html", items=items_list)
    except Exception as e:
        flash(f"Error loading dashboard: {str(e)}")
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            flash("Welcome back!")
            return redirect(url_for("dashboard"))

        flash("Invalid username or password")
        conn.close()
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        email = request.form["email"]

        conn = get_db_connection()
        if conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone():
            flash("Username already exists")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)
        conn.execute(
            "INSERT INTO users (username, password, email) VALUES (?, ?, ?)",
            (username, hashed_password, email),
        )
        conn.commit()
        conn.close()
        flash("Registration successful! Please log in.")
        return redirect(url_for("login"))
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


@app.route("/crawl-history")
@login_required
def crawl_history():
    try:
        conn = get_db_connection()
        crawls = conn.execute(
            """
            SELECT id, url, crawl_date, status, crawl_data
            FROM crawled_data 
            WHERE user_id = ? 
            ORDER BY crawl_date DESC
        """,
            (session["user_id"],),
        ).fetchall()

        # Convert rows to dictionaries
        crawls_list = []
        for crawl in crawls:
            crawls_list.append(
                {
                    "id": crawl["id"],
                    "url": crawl["url"],
                    "crawl_date": crawl["crawl_date"],
                    "status": crawl["status"],
                    "crawl_data": json.loads(crawl["crawl_data"]),
                }
            )

        conn.close()
        return render_template("crawl_history.html", crawls=crawls_list)
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


if __name__ == "__main__":
    from database import init_db

    init_db()
    app.run(debug=False, host="0.0.0.0", port=5000)
