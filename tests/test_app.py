import unittest
import sqlite3
import os
from werkzeug.security import generate_password_hash
from app import app

class FlaskAppTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Create a test database
        cls.connection = sqlite3.connect('test_inventory.db')
        cls.cursor = cls.connection.cursor()
        
        # Create tables with user_id column in inventory
        cls.cursor.execute('''
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                category TEXT NOT NULL,
                sector TEXT NOT NULL,
                application TEXT NOT NULL,
                date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        cls.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cls.connection.commit()

        # Create a test user with hashed password
        cls.test_username = 'testuser'
        cls.test_password = 'testpass'
        cls.test_email = 'test@example.com'
        
        # Hash the password before storing
        hashed_password = generate_password_hash(cls.test_password)
        
        try:
            cls.cursor.execute(
                'INSERT INTO users (username, password, email) VALUES (?, ?, ?)',
                (cls.test_username, hashed_password, cls.test_email)
            )
            cls.connection.commit()
        except sqlite3.IntegrityError:
            # User might already exist, that's okay for testing
            pass

    @classmethod
    def tearDownClass(cls):
        # Clean up the database after tests
        cls.connection.close()
        os.remove('test_inventory.db')

    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
        app.config['TESTING'] = True  # Set the app to testing mode

    def test_landing_page(self):
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Inventory Tracker', response.data)
        self.assertIn(b'Login', response.data)
        self.assertIn(b'Register', response.data)

    def test_login_page(self):
        response = self.app.get('/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Login', response.data)
        self.assertIn(b'Username', response.data)
        self.assertIn(b'Password', response.data)

    def test_register_page(self):
        response = self.app.get('/register')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Register', response.data)
        self.assertIn(b'Username', response.data)
        self.assertIn(b'Password', response.data)
        self.assertIn(b'Email', response.data)

    def test_dashboard_redirect(self):
        response = self.app.get('/dashboard', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Please log in first.', response.data)
    

    def test_register(self):
        response = self.app.post('/register', data={
            'username': 'newuser1',
            'password': 'newpass2',
            'email': 'newuser12@example.com'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        print(response.data)
        self.assertIn(b' Registration successful!', response.data)
        self.assertIn(b' Please log in.', response.data)

    def test_login(self):
        response = self.app.post('/login', data={
            'username': self.test_username,
            'password': self.test_password
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Welcome back!', response.data)
        self.assertIn(b'Dashboard', response.data)

    def test_add_item(self):
        # First login with the test user credentials
        login_response = self.app.post('/login', data={
            'username': self.test_username,
            'password': self.test_password
        }, follow_redirects=True)
        self.assertEqual(login_response.status_code, 200)
        self.assertIn(b'Welcome back!', login_response.data)
        
        # Then try to add an item
        response = self.app.post('/add', data={
            'name': 'Test Item',
            'quantity': '10',
            'category': 'Test Category',
            'sector': 'Test Sector',
            'application': 'Test Application'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Item successfully added!', response.data)

    def test_upload_csv(self):
        # This test would require a valid CSV file to be uploaded
        pass  # Implement CSV upload test

    def test_logout(self):
        self.app.post('/login', data={
            'username': self.test_username,
            'password': self.test_password
        })
        response = self.app.get('/logout', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'You have been logged out.', response.data)

if __name__ == '__main__':
    unittest.main() 