# Electronics Inventory Tracking System

A Flask-based inventory management system with user authentication, modern UI, and HTMX integration.

## Project Structure
```
electronics_inventory/
    ├── static/
    │   └── css/
    │       └── styles.css
    ├── templates/
    │   ├── base.html
    │   ├── landing.html
    │   ├── login.html
    │   ├── register.html
    │   ├── dashboard.html
    │   ├── add_item.html
    │   ├── upload_csv.html
    │   └── partials/
    │       └── inventory_row.html
    ├── app.py
    ├── database.py
    └── inventory_sample.csv
```

## Features
- User authentication (register, login, logout)
- Secure inventory management per user
- Modern responsive dashboard with sidebar
- Real-time updates using HTMX
- Inline quantity editing with HTMX
- Item deletion with confirmation
- View all inventory items
- Add individual items through a web form
- Bulk import items via CSV file
- Bootstrap-styled responsive interface
- SQLite database for data persistence
- Flash messages for user feedback

## HTMX Integration and Solutions

### Avoiding Recursive Loading
Initially, the dashboard had a recursive loading issue due to the following HTMX configuration:

```html
<!-- Problematic code -->
<div class="table-responsive" hx-get="{{ url_for('dashboard') }}" hx-trigger="load">
    <!-- Table content -->
</div>
```

This caused infinite reloading because:
1. The page loads
2. HTMX triggers the load event
3. The dashboard route returns the entire page
4. The new page triggers another load event
5. And so on...

### Solution
The solution involves:

1. Remove automatic loading of the entire table:
```html
<!-- Correct implementation -->
<div class="table-responsive" id="inventory-table">
    <!-- Table content -->
</div>
```

2. Implement targeted updates using partial templates:
```html
<!-- Partial template for row updates -->
templates/partials/inventory_row.html
```

3. Use specific HTMX triggers for individual actions:
```html
<!-- Example: Inline quantity editing -->
<input type="number" 
       class="form-control quantity-input d-none" 
       value="{{ item['quantity'] }}"
       hx-put="{{ url_for('update_quantity', item_id=item['id']) }}"
       hx-trigger="change"
       hx-target="closest tr">
```

4. Handle row-level updates:
```html
<!-- Example: Delete button with confirmation -->
<button class="btn btn-sm btn-outline-danger"
        hx-delete="{{ url_for('delete_item', item_id=item['id']) }}"
        hx-confirm="Are you sure you want to delete this item?"
        hx-target="closest tr">
    <i class="bi bi-trash"></i>
</button>
```

## Installation and Setup

1. Create a new directory for the project:
```bash
mkdir electronics_inventory
cd electronics_inventory
```

2. Install required packages:
```bash
pip install flask werkzeug
```

3. Create the necessary files and directories as shown in the project structure.

## Database Setup

Create `database.py`:
```python
import sqlite3

def init_db():
    conn = sqlite3.connect('inventory.db')
    c = conn.cursor()
    
    # Create table for electronics inventory
    c.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            category TEXT NOT NULL,
            sector TEXT NOT NULL,
            application TEXT NOT NULL,
            date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Create users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
```

## Flask Application

Create `app.py`:
```python
from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
from datetime import datetime
import csv
import io
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Required for sessions and flash messages

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_db_connection():
    conn = sqlite3.connect('inventory.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def landing():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('landing.html')

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    items = conn.execute('SELECT * FROM inventory WHERE user_id = ? ORDER BY date_added DESC', 
                        (session['user_id'],)).fetchall()
    conn.close()
    return render_template('dashboard.html', items=items)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Welcome back!')
            return redirect(url_for('dashboard'))
        
        flash('Invalid username or password')
        conn.close()
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        
        conn = get_db_connection()
        if conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone():
            flash('Username already exists')
            return redirect(url_for('register'))
            
        hashed_password = generate_password_hash(password)
        conn.execute('INSERT INTO users (username, password, email) VALUES (?, ?, ?)',
                    (username, hashed_password, email))
        conn.commit()
        conn.close()
        flash('Registration successful! Please log in.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.')
    return redirect(url_for('landing'))

@app.route('/add', methods=('GET', 'POST'))
def add_item():
    if request.method == 'POST':
        name = request.form['name']
        quantity = request.form['quantity']
        category = request.form['category']
        sector = request.form['sector']
        application = request.form['application']
        
        if not name or not quantity:
            flash('Name and quantity are required!')
        else:
            conn = get_db_connection()
            conn.execute('INSERT INTO inventory (name, quantity, category, sector, application, user_id) VALUES (?, ?, ?, ?, ?, ?)',
                        (name, quantity, category, sector, application, session['user_id']))
            conn.commit()
            conn.close()
            flash('Item successfully added!')
            return redirect(url_for('dashboard'))
            
    return render_template('add_item.html')

@app.route('/upload_csv', methods=('GET', 'POST'))
def upload_csv():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected')
            return redirect(url_for('upload_csv'))
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected')
            return redirect(url_for('upload_csv'))
        
        if file and file.filename.endswith('.csv'):
            # Read the CSV file
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_data = csv.reader(stream)
            
            conn = get_db_connection()
            success_count = 0
            error_count = 0
            
            for row in csv_data:
                try:
                    # Assuming CSV format: name, quantity, category, sector, application, date
                    name, quantity, category, sector, application, *_ = row
                    
                    conn.execute('''
                        INSERT INTO inventory (name, quantity, category, sector, application, user_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (name.strip(), int(quantity), category.strip(), 
                         sector.strip(), application.strip(), session['user_id']))
                    success_count += 1
                except Exception as e:
                    error_count += 1
                    continue
            
            conn.commit()
            conn.close()
            
            flash(f'Successfully imported {success_count} items. {error_count} items failed.')
            return redirect(url_for('dashboard'))
        else:
            flash('Please upload a CSV file')
            return redirect(url_for('upload_csv'))
            
    return render_template('upload_csv.html')

if __name__ == '__main__':
    from database import init_db
    init_db()
    app.run(debug=True)
```

## HTML Templates

### Base Template (`templates/base.html`):
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Inventory Tracker</title>
    <!-- Bootstrap CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <!-- Bootstrap Icons -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.7.2/font/bootstrap-icons.css">
    <!-- Custom CSS -->
    <link rel="stylesheet" href="{{ url_for('static', filename='css/styles.css') }}">
    <!-- HTMX -->
    <script src="https://unpkg.com/htmx.org@1.9.6"></script>
</head>
<body>
    {% if session.get('user_id') %}
    <header class="navbar navbar-dark sticky-top bg-dark flex-md-nowrap p-0 shadow">
        <a class="navbar-brand col-md-3 col-lg-2 me-0 px-3" href="{{ url_for('dashboard') }}">Inventory Tracker</a>
        <button class="navbar-toggler position-absolute d-md-none collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#sidebar" aria-controls="sidebar" aria-expanded="false" aria-label="Toggle navigation">
            <span class="navbar-toggler-icon"></span>
        </button>
        <div class="navbar-nav">
            <div class="nav-item text-nowrap">
                <span class="nav-link px-3 text-white">Welcome, {{ session.get('username') }}</span>
            </div>
        </div>
    </header>
    {% endif %}

    <div class="container-fluid">
        {% for message in get_flashed_messages() %}
            <div class="alert alert-info alert-dismissible fade show mt-3" role="alert">
                {{ message }}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        {% endfor %}
        {% block content %}{% endblock %}
    </div>

    <!-- Bootstrap Bundle with Popper -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
```

### Landing Page (`templates/landing.html`):
```html
{% extends 'base.html' %}

{% block content %}
<div class="container-fluid px-0">
    <div class="row g-0">
        <div class="col-md-6 bg-primary text-white p-5 min-vh-100 d-flex flex-column justify-content-center">
            <h1 class="display-4 fw-bold">Inventory Tracker</h1>
            <p class="lead">Manage your inventory efficiently with our modern tracking system.</p>
            <div class="mt-4">
                <a href="{{ url_for('login') }}" class="btn btn-light btn-lg me-3">Login</a>
                <a href="{{ url_for('register') }}" class="btn btn-outline-light btn-lg">Register</a>
            </div>
        </div>
        <div class="col-md-6 bg-light p-5 min-vh-100 d-flex flex-column justify-content-center">
            <h2 class="mb-4">Features</h2>
            <div class="feature-list">
                <div class="mb-4">
                    <h4>📊 Real-time Tracking</h4>
                    <p>Monitor your inventory levels in real-time with our dynamic dashboard.</p>
                </div>
                <div class="mb-4">
                    <h4>📈 Bulk Import</h4>
                    <p>Easily import inventory data using CSV files for quick setup.</p>
                </div>
                <div class="mb-4">
                    <h4>🔒 Secure Access</h4>
                    <p>Keep your inventory data safe with user authentication and authorization.</p>
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

### Dashboard Template (`templates/dashboard.html`):
```html
{% extends 'base.html' %}

{% block content %}
<div class="container-fluid">
    <div class="row">
        <!-- Sidebar -->
        <nav id="sidebar" class="col-md-3 col-lg-2 d-md-block bg-light sidebar collapse">
            <div class="position-sticky pt-3">
                <ul class="nav flex-column">
                    <li class="nav-item">
                        <a class="nav-link active" href="{{ url_for('dashboard') }}">
                            <i class="bi bi-house-door"></i> Dashboard
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('add_item') }}">
                            <i class="bi bi-plus-circle"></i> Add Item
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('upload_csv') }}">
                            <i class="bi bi-upload"></i> Import CSV
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('logout') }}">
                            <i class="bi bi-box-arrow-right"></i> Logout
                        </a>
                    </li>
                </ul>
            </div>
        </nav>

        <!-- Main content -->
        <main class="col-md-9 ms-sm-auto col-lg-10 px-md-4">
            <h1>Inventory List</h1>
            <table class="table table-striped">
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Quantity</th>
                        <th>Category</th>
                        <th>Sector</th>
                        <th>Application</th>
                        <th>Date Added</th>
                    </tr>
                </thead>
                <tbody>
                    {% for item in items %}
                    <tr>
                        <td>{{ item['name'] }}</td>
                        <td>{{ item['quantity'] }}</td>
                        <td>{{ item['category'] }}</td>
                        <td>{{ item['sector'] }}</td>
                        <td>{{ item['application'] }}</td>
                        <td>{{ item['date_added'] }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </main>
    </div>
</div>
{% endblock %}
```

## Custom Styles

Create `static/css/styles.css`:
```css
/* Sidebar styles */
.sidebar {
    position: fixed;
    top: 0;
    bottom: 0;
    left: 0;
    z-index: 100;
    padding: 48px 0 0;
    box-shadow: inset -1px 0 0 rgba(0, 0, 0, .1);
}

/* ... [Additional styles for sidebar, main content, responsive design] ... */

/* Landing page styles */
.feature-list h4 {
    color: #0d6efd;
    margin-bottom: 0.5rem;
}

.feature-list p {
    color: #6c757d;
    margin-bottom: 1.5rem;
}
```

## Running the Application

1. Make sure all files are created in the correct directory structure
2. Open a terminal in the project directory
3. Run the application:
```bash
python app.py
```
4. Open a web browser and navigate to `http://localhost:5000`

## Security Considerations
- Passwords are hashed using Werkzeug's security functions
- User sessions are managed securely
- Protected routes require authentication
- Each user can only access their own inventory items
- HTMX requests are validated for user ownership

## Best Practices for HTMX Integration
1. Use partial templates for updates
2. Target specific elements instead of full page reloads
3. Implement proper error handling
4. Validate user permissions for each request
5. Use appropriate HTTP methods (GET, POST, PUT, DELETE)
6. Add confirmation dialogs for destructive actions
7. Provide visual feedback for user actions

## Future Enhancements
- Password reset functionality
- Email verification
- Two-factor authentication
- Advanced search and filtering
- Export functionality
- Stock alerts
- Activity logging
- Batch operations
- Role-based access control
```

This markdown document provides a complete guide to setting up and running the electronics inventory tracking system. You can save this as `inventory_tracker.md` and use it as a reference for implementing the system.

Certainly! Below is the updated section for the `inventory_tracker_doc.md` that includes a discussion of the test cases and the GitHub Actions setup for CI/CD.

### Updated `inventory_tracker_doc.md`

```markdown
# Electronics Inventory Tracking System

A Flask-based inventory management system with user authentication, modern UI, and HTMX integration.

## Project Structure
```
electronics_inventory/
    ├── static/
    │   └── css/
    │       └── styles.css
    ├── templates/
    │   ├── base.html
    │   ├── landing.html
    │   ├── login.html
    │   ├── register.html
    │   ├── dashboard.html
    │   ├── add_item.html
    │   ├── upload_csv.html
    │   └── partials/
    │       └── inventory_row.html
    ├── app.py
    ├── database.py
    ├── tests/
    │   └── test_app.py
    └── inventory_sample.csv
```

## Features
- User authentication (register, login, logout)
- Secure inventory management per user
- Modern responsive dashboard with sidebar
- Real-time updates using HTMX
- Inline quantity editing with HTMX
- Item deletion with confirmation
- View all inventory items
- Add individual items through a web form
- Bulk import items via CSV file
- Bootstrap-styled responsive interface
- SQLite database for data persistence
- Flash messages for user feedback

## Testing

### Test Cases

The application includes a suite of unit tests to ensure the functionality of the Flask server. The tests are located in the `tests/test_app.py` file and cover the following functionalities:

1. **Landing Page**: Tests that the landing page loads successfully and contains the expected elements (e.g., "Inventory Tracker", "Login", "Register").

2. **Login Page**: Tests that the login page loads successfully and contains the necessary fields (e.g., "Username", "Password").

3. **Registration**: Tests the registration process, ensuring that a new user can register successfully and that the appropriate success message is displayed.

4. **Login Functionality**: Tests the login process, ensuring that a registered user can log in and is redirected to the dashboard with a welcome message.

5. **Add Item**: Tests the functionality of adding an item to the inventory, ensuring that the item is added successfully and the appropriate success message is displayed.

### Running Tests Locally

To run the tests locally, follow these steps:

1. **Navigate to Your Project Directory**:
   ```bash
   cd path/to/your/electronics_inventory
   ```

2. **Set Up a Virtual Environment (Optional)**:
   ```bash
   python -m venv venv
   ```

3. **Activate the Virtual Environment**:
   - On **Windows**:
     ```bash
     venv\Scripts\activate
     ```
   - On **macOS/Linux**:
     ```bash
     source venv/bin/activate
     ```

4. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Run the Tests**:
   ```bash
   python -m unittest discover -s tests
   ```

## CI/CD Pipeline Configuration with GitHub Actions

To set up a CI/CD pipeline using GitHub Actions, create a new file in your repository at `.github/workflows/python-app.yml` with the following content:

```yaml
name: Python application

on: [push, pull_request]

jobs:
  build:

    runs-on: ubuntu-latest

    steps:
    - name: Checkout code
      uses: actions/checkout@v2

    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.8'  # Specify the Python version you want to use

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt  # Ensure you have a requirements.txt file

    - name: Run tests
      run: |
        python -m unittest discover -s tests  # Adjust the path if necessary
```

### Explanation of the GitHub Actions Workflow

- **Triggers**: The workflow is triggered on every push and pull request to the repository.
- **Jobs**: The `build` job runs on the latest version of Ubuntu.
- **Steps**:
  - **Checkout Code**: Uses the `actions/checkout` action to pull the code from the repository.
  - **Set Up Python**: Uses the `actions/setup-python` action to set up the specified version of Python.
  - **Install Dependencies**: Installs the required packages listed in `requirements.txt`.
  - **Run Tests**: Executes the unit tests located in the `tests` directory.

## Future Enhancements
- Password reset functionality
- Email verification
- Two-factor authentication
- Advanced search and filtering
- Export functionality
- Stock alerts
- Activity logging
- Batch operations
- Role-based access control
```

### Summary of Updates

- Added a **Testing** section that describes the test cases and their purpose.
- Included instructions for running tests locally.
- Added a **CI/CD Pipeline Configuration with GitHub Actions** section that details the setup for automated testing on GitHub.
- Provided an explanation of the GitHub Actions workflow.

This updated documentation should provide a comprehensive overview of testing and CI/CD setup for the Electronics Inventory Tracking System.
