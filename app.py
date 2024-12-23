from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3
from datetime import datetime
import csv
import io
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Required for flashing messages and sessions

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_db_connection():
    # Check if the application is in testing mode
    if app.config['TESTING']:
        db_name = 'test_inventory.db'  # Use the test database
    else:
        db_name = 'inventory.db'  # Use the production database

    conn = sqlite3.connect(db_name)
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
@login_required
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
            conn.execute('''INSERT INTO inventory 
                          (name, quantity, category, sector, application, user_id) 
                          VALUES (?, ?, ?, ?, ?, ?)''',
                       (name, quantity, category, sector, application, session['user_id']))
            conn.commit()
            conn.close()
            flash('Item successfully added!')
            return redirect(url_for('dashboard'))
            
    return render_template('add_item.html')

@app.route('/upload_csv', methods=('GET', 'POST'))
@login_required
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
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_data = csv.reader(stream)
            
            conn = get_db_connection()
            success_count = 0
            error_count = 0
            
            for row in csv_data:
                try:
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

@app.route('/update_quantity/<int:item_id>', methods=['PUT'])
@login_required
def update_quantity(item_id):
    try:
        quantity = int(request.form.get('value', 0))
        if quantity < 0:
            return 'Quantity cannot be negative', 400

        conn = get_db_connection()
        # Verify the item belongs to the current user
        item = conn.execute('SELECT * FROM inventory WHERE id = ? AND user_id = ?', 
                          (item_id, session['user_id'])).fetchone()
        
        if not item:
            conn.close()
            return 'Item not found', 404

        conn.execute('UPDATE inventory SET quantity = ? WHERE id = ? AND user_id = ?',
                    (quantity, item_id, session['user_id']))
        conn.commit()
        conn.close()

        return render_template('partials/inventory_row.html', 
                             item={'id': item_id, 'quantity': quantity, 
                                  'name': item['name'], 'category': item['category'],
                                  'sector': item['sector'], 'application': item['application'],
                                  'date_added': item['date_added']})
    except ValueError:
        return 'Invalid quantity value', 400
    except Exception as e:
        return str(e), 500

@app.route('/delete_item/<int:item_id>', methods=['DELETE'])
@login_required
def delete_item(item_id):
    try:
        conn = get_db_connection()
        # Verify the item belongs to the current user
        result = conn.execute('DELETE FROM inventory WHERE id = ? AND user_id = ?',
                            (item_id, session['user_id']))
        conn.commit()
        conn.close()

        if result.rowcount == 0:
            return 'Item not found', 404

        return '', 204
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    from database import init_db
    init_db()
    app.run(debug=True)
