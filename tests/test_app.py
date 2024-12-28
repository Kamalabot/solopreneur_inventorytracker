import unittest
from app import app

class FlaskAppTests(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

        # Create a test user for login and registration tests
        self.test_username = 'testuser'
        self.test_password = 'testpass'
        self.test_email = 'testuser@example.com'

        # Register the test user
        self.app.post('/register', data={
            'username': self.test_username,
            'password': self.test_password,
            'email': self.test_email
        })

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

    def test_login(self):
        response = self.app.post('/login', data={
            'username': self.test_username,
            'password': self.test_password
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Welcome back!', response.data)
        self.assertIn(b'Dashboard', response.data)

    def test_register(self):
        response = self.app.post('/register', data={
            'username': 'newuser1',
            'password': 'newpass2',
            'email': 'newuser12@example.com'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Registration successful!', response.data)
        self.assertIn(b'Please log in.', response.data)

    def test_add_item(self):
        self.app.post('/login', data={
            'username': self.test_username,
            'password': self.test_password
        })
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