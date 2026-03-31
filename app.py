from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timezone
from functools import wraps
import csv
import os
import re
import psycopg2
import psycopg2.extras
import pytz

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
IST = pytz.timezone('Asia/Kolkata')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ── Template filters ──────────────────────────────────────────────────────────

@app.template_filter('format_datetime')
def format_datetime(value):
    if not value:
        return ''
    dt = datetime.fromisoformat(str(value))
    return dt.strftime('%b %d, %Y at %I:%M %p')

@app.template_filter('format_datetime_short')
def format_datetime_short(value):
    if not value:
        return ''
    dt = datetime.fromisoformat(str(value))
    return dt.strftime('%m/%d/%y %I:%M %p')

# ── Database helpers ──────────────────────────────────────────────────────────

DATABASE_URL = os.environ.get('DATABASE_URL')

# Render provides postgres:// but psycopg2 needs postgresql://
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS allowed_emails (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tests (
            id SERIAL PRIMARY KEY,
            test_name TEXT NOT NULL,
            test_link TEXT NOT NULL,
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('SELECT COUNT(*) FROM admin WHERE username = %s', ('admin',))
    if cursor.fetchone()['count'] == 0:
        hashed_password = generate_password_hash('admin123')
        cursor.execute(
            'INSERT INTO admin (username, password) VALUES (%s, %s)',
            ('admin', hashed_password)
        )

    conn.commit()
    cursor.close()
    conn.close()

# ── Auth decorators ───────────────────────────────────────────────────────────

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

# ── Utilities ─────────────────────────────────────────────────────────────────

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def get_test_status(start_time, end_time):
    now = datetime.now(IST)

    # psycopg2 returns datetime objects; handle both str and datetime
    if isinstance(start_time, str):
        start_time = datetime.fromisoformat(start_time)
    if isinstance(end_time, str):
        end_time = datetime.fromisoformat(end_time)

    if start_time.tzinfo is None:
        start_time = IST.localize(start_time)
    if end_time.tzinfo is None:
        end_time = IST.localize(end_time)

    if now >= start_time and now <= end_time:
        return 'available'
    elif now < start_time:
        return 'upcoming'
    else:
        return 'ended'

# ── Routes ────────────────────────────────────────────────────────────────────

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
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        if email == 'admin':
            conn   = get_db()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM admin WHERE username = %s', ('admin',))
            admin = cursor.fetchone()
            cursor.close()
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

            conn   = get_db()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM allowed_emails WHERE email = %s', (email,))
            allowed = cursor.fetchone()
            cursor.close()
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

    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tests ORDER BY start_time')
    tests = cursor.fetchall()
    cursor.close()
    conn.close()

    tests_with_status = []
    for test in tests:
        test_dict = dict(test)
        test_dict['status'] = get_test_status(test['start_time'], test['end_time'])
        tests_with_status.append(test_dict)

    tests_with_status.sort(key=lambda x: (
        0 if x['status'] == 'available' else 1 if x['status'] == 'upcoming' else 2,
        str(x['start_time'])
    ))

    return render_template('student.html',
                           email=session.get('user_email'),
                           tests=tests_with_status)

@app.route('/admin')
@admin_required
def admin_dashboard():
    conn   = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM allowed_emails ORDER BY email')
    emails = cursor.fetchall()

    cursor.execute('SELECT * FROM tests ORDER BY start_time')
    tests = cursor.fetchall()

    cursor.close()
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

    conn   = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO allowed_emails (email) VALUES (%s)', (email,))
        conn.commit()
        flash(f'Email {email} added successfully', 'success')
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        flash(f'Email {email} already exists', 'error')
    finally:
        cursor.close()
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
        reader  = csv.reader(content)
        rows    = list(reader)

        if not rows:
            flash('CSV file is empty', 'error')
            return redirect(url_for('admin_dashboard'))

        first_row  = rows[0][0].strip().lower() if rows[0] else ''
        has_header = first_row in ['email', 'emails']

        emails_to_add = [
            row[0].strip().lower()
            for row in (rows[1:] if has_header else rows)
            if row and row[0].strip()
        ]
        valid_emails = [e for e in emails_to_add if validate_email(e)]

        conn   = get_db()
        cursor = conn.cursor()
        added = skipped = 0

        for email in valid_emails:
            try:
                cursor.execute('INSERT INTO allowed_emails (email) VALUES (%s)', (email,))
                conn.commit()
                added += 1
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                skipped += 1

        cursor.close()
        conn.close()
        flash(f'CSV processed: {added} emails added, {skipped} duplicates skipped', 'success')

    except Exception as e:
        flash(f'Error processing CSV: {str(e)}', 'error')

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete-email/<int:id>', methods=['POST'])
@admin_required
def delete_email(id):
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM allowed_emails WHERE id = %s', (id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Email deleted successfully', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/create-test', methods=['POST'])
@admin_required
def create_test():
    test_name  = request.form.get('test_name', '').strip()
    test_link  = request.form.get('test_link', '').strip()
    start_time = request.form.get('start_time', '').strip()
    end_time   = request.form.get('end_time', '').strip()

    if not all([test_name, test_link, start_time, end_time]):
        flash('All fields are required', 'error')
        return redirect(url_for('admin_dashboard'))

    try:
        start_dt = datetime.fromisoformat(start_time)
        end_dt   = datetime.fromisoformat(end_time)

        if start_dt >= end_dt:
            flash('Start time must be before end time', 'error')
            return redirect(url_for('admin_dashboard'))

        conn   = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO tests (test_name, test_link, start_time, end_time)
            VALUES (%s, %s, %s, %s)
        ''', (test_name, test_link, start_time, end_time))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Test created successfully', 'success')

    except Exception as e:
        flash(f'Error creating test: {str(e)}', 'error')

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/update-test/<int:id>', methods=['POST'])
@admin_required
def update_test(id):
    test_name  = request.form.get('test_name', '').strip()
    test_link  = request.form.get('test_link', '').strip()
    start_time = request.form.get('start_time', '').strip()
    end_time   = request.form.get('end_time', '').strip()

    if not all([test_name, test_link, start_time, end_time]):
        flash('All fields are required', 'error')
        return redirect(url_for('admin_dashboard'))

    try:
        start_dt = datetime.fromisoformat(start_time)
        end_dt   = datetime.fromisoformat(end_time)

        if start_dt >= end_dt:
            flash('Start time must be before end time', 'error')
            return redirect(url_for('admin_dashboard'))

        conn   = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE tests
            SET test_name = %s, test_link = %s, start_time = %s, end_time = %s
            WHERE id = %s
        ''', (test_name, test_link, start_time, end_time, id))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Test updated successfully', 'success')

    except Exception as e:
        flash(f'Error updating test: {str(e)}', 'error')

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete-test/<int:id>', methods=['POST'])
@admin_required
def delete_test(id):
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM tests WHERE id = %s', (id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Test deleted successfully', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/get-tests')
@admin_required
def get_tests():
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tests ORDER BY start_time')
    tests = cursor.fetchall()
    cursor.close()
    conn.close()

    tests_list = []
    for test in tests:
        test_dict = dict(test)
        test_dict['status'] = get_test_status(test['start_time'], test['end_time'])
        # Convert datetime objects to ISO strings for JSON serialization
        test_dict['start_time'] = str(test_dict['start_time'])
        test_dict['end_time']   = str(test_dict['end_time'])
        test_dict['created_at'] = str(test_dict['created_at'])
        tests_list.append(test_dict)

    return jsonify(tests_list)

@app.route('/admin/change-password', methods=['POST'])
@admin_required
def change_password():
    current_password = request.form.get('current_password', '').strip()
    new_password     = request.form.get('new_password', '').strip()
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

    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM admin WHERE username = %s', ('admin',))
    admin = cursor.fetchone()

    if not check_password_hash(admin['password'], current_password):
        flash('Current password is incorrect', 'error')
        cursor.close()
        conn.close()
        return redirect(url_for('admin_dashboard'))

    hashed_password = generate_password_hash(new_password)
    cursor.execute(
        'UPDATE admin SET password = %s WHERE username = %s',
        (hashed_password, 'admin')
    )
    conn.commit()
    cursor.close()
    conn.close()
    flash('Password changed successfully', 'success')
    return redirect(url_for('admin_dashboard'))

# ── CLI & startup ─────────────────────────────────────────────────────────────

@app.cli.command('init-db')
def init_db_command():
    init_db()
    print('Database initialized successfully')

init_db()

if __name__ == '__main__':
    app.run(debug=True)
