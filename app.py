from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from functools import wraps
import sqlite3
import csv
import os
import re
from datetime import datetime, timezone
import pytz

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
LOCAL_TZ = pytz.timezone('Asia/Kolkata')  # IST

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
@app.template_filter('format_datetime')
def format_datetime(value):
    if not value:
        return ''
    dt = datetime.fromisoformat(value)
    return dt.strftime('%b %d, %Y at %I:%M %p')

@app.template_filter('format_datetime_short')
def format_datetime_short(value):
    if not value:
        return ''
    dt = datetime.fromisoformat(value)
    return dt.strftime('%m/%d/%y %I:%M %p')

DATABASE = 'lms.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn



def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS allowed_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_name TEXT NOT NULL,
            test_link TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('SELECT COUNT(*) FROM admin WHERE username = ?', ('admin',))
    if cursor.fetchone()[0] == 0:
        hashed_password = generate_password_hash('admin123')
        cursor.execute('INSERT INTO admin (username, password) VALUES (?, ?)', ('admin', hashed_password))
    
    conn.commit()
    conn.close()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_email' not in session and 'admin_logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            flash('Admin access required', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def get_test_status(start_time, end_time):
    now = datetime.now(timezone.utc)  # Get UTC time
    start = datetime.fromisoformat(start_time).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(end_time).replace(tzinfo=timezone.utc)
    
    if now >= start and now <= end:
        return 'available'
    elif now < start:
        return 'upcoming'
    else:
        return 'ended'
    
    

@app.route('/')
def index():
    if 'admin_logged_in' in session:
        return redirect(url_for('admin_dashboard'))
    elif 'user_email' in session:
        return redirect(url_for('student_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        if email == 'admin':
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM admin WHERE username = ?', ('admin',))
            admin = cursor.fetchone()
            conn.close()
            
            if admin and check_password_hash(admin['password'], password):
                session['admin_logged_in'] = True
                session['username'] = 'admin'
                flash('Admin login successful', 'success')
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Invalid admin credentials', 'error')
        else:
            if not validate_email(email):
                flash('Invalid email format', 'error')
                return render_template('login.html')
            
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM allowed_emails WHERE email = ?', (email,))
            allowed = cursor.fetchone()
            conn.close()
            
            if allowed:
                session['user_email'] = email
                flash('Login successful', 'success')
                return redirect(url_for('student_dashboard'))
            else:
                flash('Email not authorized. Contact admin.', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('login'))

@app.route('/student')
@login_required
def student_dashboard():
    if 'admin_logged_in' in session:
        return redirect(url_for('admin_dashboard'))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tests ORDER BY start_time')
    tests = cursor.fetchall()
    conn.close()
    
    tests_with_status = []
    for test in tests:
        test_dict = dict(test)
        test_dict['status'] = get_test_status(test['start_time'], test['end_time'])
        tests_with_status.append(test_dict)
    
    tests_with_status.sort(key=lambda x: (
        0 if x['status'] == 'available' else 1 if x['status'] == 'upcoming' else 2,
        x['start_time']
    ))
    
    return render_template('student.html', 
                         email=session.get('user_email'),
                         tests=tests_with_status)

@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM allowed_emails ORDER BY email')
    emails = cursor.fetchall()
    
    cursor.execute('SELECT * FROM tests ORDER BY start_time')
    tests = cursor.fetchall()
    
    conn.close()
    
    tests_with_status = []
    active_count = 0
    for test in tests:
        test_dict = dict(test)
        status = get_test_status(test['start_time'], test['end_time'])
        test_dict['status'] = status
        if status == 'available':
            active_count += 1
        tests_with_status.append(test_dict)
    
    return render_template('admin.html',
                         emails=emails,
                         tests=tests_with_status,
                         total_students=len(emails),
                         total_tests=len(tests),
                         active_tests=active_count)

@app.route('/admin/add-email', methods=['POST'])
@admin_required
def add_email():
    email = request.form.get('email', '').strip().lower()
    
    if not validate_email(email):
        flash('Invalid email format', 'error')
        return redirect(url_for('admin_dashboard'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute('INSERT INTO allowed_emails (email) VALUES (?)', (email,))
        conn.commit()
        flash(f'Email {email} added successfully', 'success')
    except sqlite3.IntegrityError:
        flash(f'Email {email} already exists', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/upload-csv', methods=['POST'])
@admin_required
def upload_csv():
    if 'csv_file' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(url_for('admin_dashboard'))
    
    file = request.files['csv_file']
    
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('admin_dashboard'))
    
    if not file.filename.endswith('.csv'):
        flash('Only CSV files are allowed', 'error')
        return redirect(url_for('admin_dashboard'))
    
    try:
        content = file.read().decode('utf-8').splitlines()
        reader = csv.reader(content)
        
        rows = list(reader)
        if not rows:
            flash('CSV file is empty', 'error')
            return redirect(url_for('admin_dashboard'))
        
        first_row = rows[0][0].strip().lower() if rows[0] else ''
        has_header = first_row in ['email', 'emails']
        
        emails_to_add = []
        if has_header:
            emails_to_add = [row[0].strip().lower() for row in rows[1:] if row and row[0].strip()]
        else:
            emails_to_add = [row[0].strip().lower() for row in rows if row and row[0].strip()]
        
        valid_emails = [email for email in emails_to_add if validate_email(email)]
        
        conn = get_db()
        cursor = conn.cursor()
        
        added = 0
        skipped = 0
        
        for email in valid_emails:
            try:
                cursor.execute('INSERT INTO allowed_emails (email) VALUES (?)', (email,))
                conn.commit()
                added += 1
            except sqlite3.IntegrityError:
                skipped += 1
        
        conn.close()
        
        flash(f'CSV processed: {added} emails added, {skipped} duplicates skipped', 'success')
    
    except Exception as e:
        flash(f'Error processing CSV: {str(e)}', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete-email/<int:id>', methods=['POST'])
@admin_required
def delete_email(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM allowed_emails WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    
    flash('Email deleted successfully', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/create-test', methods=['POST'])
@admin_required
def create_test():
    test_name = request.form.get('test_name', '').strip()
    test_link = request.form.get('test_link', '').strip()
    start_time = request.form.get('start_time', '').strip()
    end_time = request.form.get('end_time', '').strip()
    
    if not all([test_name, test_link, start_time, end_time]):
        flash('All fields are required', 'error')
        return redirect(url_for('admin_dashboard'))
    
    try:
        start_dt = datetime.fromisoformat(start_time)
        end_dt = datetime.fromisoformat(end_time)
        
        if start_dt >= end_dt:
            flash('Start time must be before end time', 'error')
            return redirect(url_for('admin_dashboard'))
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO tests (test_name, test_link, start_time, end_time)
            VALUES (?, ?, ?, ?)
        ''', (test_name, test_link, start_time, end_time))
        conn.commit()
        conn.close()
        
        flash('Test created successfully', 'success')
    except Exception as e:
        flash(f'Error creating test: {str(e)}', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/update-test/<int:id>', methods=['POST'])
@admin_required
def update_test(id):
    test_name = request.form.get('test_name', '').strip()
    test_link = request.form.get('test_link', '').strip()
    start_time = request.form.get('start_time', '').strip()
    end_time = request.form.get('end_time', '').strip()
    
    if not all([test_name, test_link, start_time, end_time]):
        flash('All fields are required', 'error')
        return redirect(url_for('admin_dashboard'))
    
    try:
        start_dt = datetime.fromisoformat(start_time)
        end_dt = datetime.fromisoformat(end_time)
        
        if start_dt >= end_dt:
            flash('Start time must be before end time', 'error')
            return redirect(url_for('admin_dashboard'))
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE tests 
            SET test_name = ?, test_link = ?, start_time = ?, end_time = ?
            WHERE id = ?
        ''', (test_name, test_link, start_time, end_time, id))
        conn.commit()
        conn.close()
        
        flash('Test updated successfully', 'success')
    except Exception as e:
        flash(f'Error updating test: {str(e)}', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete-test/<int:id>', methods=['POST'])
@admin_required
def delete_test(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM tests WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    
    flash('Test deleted successfully', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/get-tests')
@admin_required
def get_tests():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tests ORDER BY start_time')
    tests = cursor.fetchall()
    conn.close()
    
    tests_list = []
    for test in tests:
        test_dict = dict(test)
        test_dict['status'] = get_test_status(test['start_time'], test['end_time'])
        tests_list.append(test_dict)
    
    return jsonify(tests_list)

@app.route('/admin/change-password', methods=['POST'])
@admin_required
def change_password():
    current_password = request.form.get('current_password', '').strip()
    new_password = request.form.get('new_password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()
    
    if not all([current_password, new_password, confirm_password]):
        flash('All password fields are required', 'error')
        return redirect(url_for('admin_dashboard'))
    
    if new_password != confirm_password:
        flash('New passwords do not match', 'error')
        return redirect(url_for('admin_dashboard'))
    
    if len(new_password) < 6:
        flash('Password must be at least 6 characters', 'error')
        return redirect(url_for('admin_dashboard'))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM admin WHERE username = ?', ('admin',))
    admin = cursor.fetchone()
    
    if not check_password_hash(admin['password'], current_password):
        flash('Current password is incorrect', 'error')
        conn.close()
        return redirect(url_for('admin_dashboard'))
    
    hashed_password = generate_password_hash(new_password)
    cursor.execute('UPDATE admin SET password = ? WHERE username = ?', (hashed_password, 'admin'))
    conn.commit()
    conn.close()
    
    flash('Password changed successfully', 'success')
    return redirect(url_for('admin_dashboard'))

@app.cli.command('init-db')
def init_db_command():
    init_db()
    print('Database initialized successfully')


init_db()


if __name__ == '__main__':
    init_db()
    app.run(debug=True)