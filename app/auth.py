from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
import random
import string
from app.models.users import (
    authenticate_user, register_user, get_user, initialize_users_file, 
    initialize_students_dir, initialize_sections_file, get_all_sections, 
    get_all_students, save_section_from_excel, hash_password, delete_section,
    delete_student_from_section, student_id_exists, move_student_to_section,
    get_all_section_names, add_single_student, get_student_by_id, get_user_by_email,
    update_student
)
from app.utils.email_utils import send_email

auth = Blueprint('auth', __name__)


def send_verification_email(student, verification_code):
    """
    Send the verification code to the student's email address.
    Returns (email_sent: bool, error_message: Optional[str])
    """
    if not student or not getattr(student, "email", None):
        return False, "Student email is missing. Please update the student's email address."

    subject = "Rankwise Verification Code"
    body = (
        f"Hello {student.fullname or student.student_id},\n\n"
        f"Your temporary verification code is: {verification_code}\n\n"
        "Use this code together with your student ID to log in to Rankwise. "
        "For security, please do not share this code with others.\n\n"
        "If you did not request this code, please contact your teacher.\n\n"
        "This is an automated message."
    )

    return send_email(student.email, subject, body)

def send_admin_verification_email(admin_email, admin_name, verification_code):
    """
    Send the verification code to the admin's email address.
    Returns (email_sent: bool, error_message: Optional[str])
    """
    if not admin_email:
        return False, "Admin email is missing."

    subject = "Rankwise Admin Account Verification"
    body = (
        f"Hello {admin_name},\n\n"
        f"Your verification code is: {verification_code}\n\n"
        "Please use this code to verify your admin account and create your password. "
        "For security, please do not share this code with others.\n\n"
        "If you did not request this code, please contact the system administrator.\n\n"
        "IMPORTANT (For Unverified Admins):\n"
        "If you received this message, please log in to RankWise by entering your email ONLY. "
        "Leave the password field blank, then click Login.\n\n"
        "This is an automated message."
    )

    return send_email(admin_email, subject, body)

@auth.route('/login', methods = ['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password', '').strip()
        
        # Check if it's an email (for unverified admin login)
        if '@' in username and not password:
            # Email-only login for unverified admins
            user = get_user_by_email(username)
            if user and user.role == 'admin' and not user.verified:
                # Store email in session for verification step
                session['pending_email'] = username
                return redirect(url_for('auth.verify_code'))
            else:
                flash('Invalid email or account already verified. Please use username and password.', 'danger')
                return redirect(url_for('auth.login'))
        
        # Regular login with username and password
        if not password:
            flash('Password is required for regular login', 'danger')
            return redirect(url_for('auth.login'))
        
        user = authenticate_user(username, password)
        if user:
            session['user_id'] = user.username
            session['role'] = user.role
            flash(f'Welcome, {username}!', 'success')
            return redirect(url_for('main.index'))
        else:
            flash('Invalid username or password', 'danger')
            return redirect(url_for('auth.login'))
    return render_template('login.html')

@auth.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'success')
    return redirect(url_for('auth.login'))

@auth.route('/admin/users', methods=['GET', 'POST'])
def manage_users():
    # Admin check
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('You must be an admin to access this page', 'danger')
        return redirect(url_for('main.index'))
    
    # Initialize the students directory and sections file if they don't exist
    initialize_students_dir()
    initialize_sections_file()
    
    # Handle CSV file upload
    if request.method == 'POST':
        # Check if section name is provided
        section_name = request.form.get('section_name')
        if not section_name:
            flash('Please provide a section name', 'danger')
            return redirect(url_for('auth.manage_users'))
        
        # Check if CSV file is provided
        if 'csv_file' not in request.files:
            flash('No file selected', 'danger')
            return redirect(url_for('auth.manage_users'))
        
        csv_file = request.files['csv_file']
        
        # Check if file is empty
        if csv_file.filename == '':
            flash('No file selected', 'danger')
            return redirect(url_for('auth.manage_users'))
        
        # Check file extension
        if not csv_file.filename.lower().endswith(('.xlsx', '.xls')):
            flash('Only Excel files (.xlsx, .xls) are allowed', 'danger')
            return redirect(url_for('auth.manage_users'))
        
        # Process the file
        success, message = save_section_from_excel(section_name, csv_file)
        if success:
            flash(message, 'success')
        else:
            flash(message, 'danger')
        
        return redirect(url_for('auth.manage_users'))
    
    # Get all sections and students
    sections = get_all_sections()
    active_section = request.args.get('section')
    
    # If a section is specified, get students only from that section
    if active_section:
        for section in sections:
            if section.name == active_section:
                students = section.students
                break
        else:
            students = []
    else:
        students = get_all_students()
    
    return render_template('manage_users.html', sections=sections, students=students, active_section=active_section)

@auth.route('/generate-verification-code', methods=['POST'])
def generate_verification_code():
    # Admin check
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
    
    data = request.get_json()
    if not data or 'student_id' not in data:
        return jsonify({'success': False, 'error': 'Student ID is required'}), 400
    
    student_id = data['student_id']
    student = get_student_by_id(student_id)
    
    # Generate a random 6-digit verification code
    verification_code = ''.join(random.choices(string.digits, k=6))
    
    # Update the user's password to the verification code
    import csv
    import os
    from tempfile import NamedTemporaryFile
    import shutil
    from app.models.users import USERS_FILE
    
    if not os.path.exists(USERS_FILE):
        initialize_users_file()
    
    user_exists = False
    temp_file = NamedTemporaryFile(mode='w', delete=False, newline='')
    
    try:
        with open(USERS_FILE, 'r', newline='') as csv_file, temp_file:
            reader = csv.DictReader(csv_file)
            fieldnames = reader.fieldnames or ['username', 'password_hash', 'role', 'email', 'name', 'verification_code', 'verified']
            
            # Ensure all required columns exist
            required_fields = ['username', 'password_hash', 'role', 'email', 'name', 'verification_code', 'verified']
            for field in required_fields:
                if field not in fieldnames:
                    fieldnames.append(field)
            
            writer = csv.DictWriter(temp_file, fieldnames=fieldnames)
            writer.writeheader()
            
            for row in reader:
                if row['username'] == student_id:
                    row['password_hash'] = hash_password(verification_code)
                    user_exists = True
                # Ensure all fields exist in row
                for field in required_fields:
                    if field not in row:
                        row[field] = ''
                writer.writerow(row)
        
        shutil.move(temp_file.name, USERS_FILE)
        
        if not user_exists:
            # Use register_user to ensure proper column handling
            register_user(student_id, verification_code, 'student')
        
        email_sent, email_error = send_verification_email(student, verification_code)
        
        message = "Verification code generated."
        if email_sent:
            message += " Email sent to student."
        else:
            message += " Email could not be sent."
        
        return jsonify({
            'success': True,
            'email_sent': email_sent,
            'email_error': email_error,
            'message': message
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@auth.route('/generate-bulk-verification-codes', methods=['POST'])
def generate_bulk_verification_codes():
    # Admin check
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
    
    data = request.get_json()
    student_ids = data.get('student_ids', [])
    
    if not student_ids:
        return jsonify({'success': False, 'error': 'Student IDs are required'}), 400
    
    import csv
    import os
    from tempfile import NamedTemporaryFile
    import shutil
    from app.models.users import USERS_FILE
    
    if not os.path.exists(USERS_FILE):
        initialize_users_file()
    
    try:
        # Load existing users
        existing_users = {}
        required_fields = ['username', 'password_hash', 'role', 'email', 'name', 'verification_code', 'verified']
        
        with open(USERS_FILE, 'r', newline='') as csv_file:
            reader = csv.DictReader(csv_file)
            fieldnames = reader.fieldnames or required_fields
            
            # Ensure all required columns exist
            for field in required_fields:
                if field not in fieldnames:
                    fieldnames.append(field)
            
            for row in reader:
                # Ensure all fields exist in row
                for field in required_fields:
                    if field not in row:
                        row[field] = ''
                existing_users[row['username']] = row
        
        temp_file = NamedTemporaryFile(mode='w', delete=False, newline='')
        bulk_results = []
        
        with temp_file:
            writer = csv.DictWriter(temp_file, fieldnames=fieldnames)
            writer.writeheader()
            
            for student_id in student_ids:
                verification_code = ''.join(random.choices(string.digits, k=6))
                student = get_student_by_id(student_id)
                
                if student_id in existing_users:
                    existing_users[student_id]['password_hash'] = hash_password(verification_code)
                else:
                    existing_users[student_id] = {
                        'username': student_id,
                        'password_hash': hash_password(verification_code),
                        'role': 'student',
                        'email': '',
                        'name': '',
                        'verification_code': '',
                        'verified': 'False'
                    }
                
                email_sent, email_error = send_verification_email(student, verification_code)
                bulk_results.append({
                    'student_id': student_id,
                    'student_name': getattr(student, 'fullname', student_id),
                    'email_sent': email_sent,
                    'email_error': email_error
                })
            
            for user_data in existing_users.values():
                # Ensure all fields exist before writing
                for field in required_fields:
                    if field not in user_data:
                        user_data[field] = ''
                writer.writerow(user_data)
        
        shutil.move(temp_file.name, USERS_FILE)
        
        return jsonify({
            'success': True,
            'results': bulk_results,
            'message': f'Processed {len(bulk_results)} students.'
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@auth.route('/delete-section', methods=['POST'])
def delete_section_route():
    # Admin check
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
    
    data = request.get_json()
    section_name = data.get('section_name')
    
    if not section_name:
        return jsonify({'success': False, 'error': 'Section name is required'}), 400
    
    success, message = delete_section(section_name)
    
    return jsonify({
        'success': success,
        'message': message
    })

@auth.route('/move-student', methods=['POST'])
def move_student_route():
    # Admin check
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
    
    data = request.get_json()
    student_id = data.get('student_id')
    from_section = data.get('from_section')
    to_section = data.get('to_section')
    
    if not student_id or not from_section or not to_section:
        return jsonify({'success': False, 'error': 'Student ID, from section, and to section are required'}), 400
    
    if from_section == to_section:
        return jsonify({'success': False, 'error': 'Source and destination sections must be different'}), 400
    
    success, message = move_student_to_section(student_id, from_section, to_section)
    
    return jsonify({
        'success': success,
        'message': message
    })

@auth.route('/get-sections', methods=['GET'])
def get_sections_route():
    # Admin check
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
    
    sections = get_all_section_names()
    
    return jsonify({
        'success': True,
        'sections': sections
    })

@auth.route('/ensure-section', methods=['POST'])
def ensure_section():
    # Admin check
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
    
    data = request.get_json()
    section_name = data.get('section_name')
    
    if not section_name:
        return jsonify({'success': False, 'error': 'Section name is required'}), 400
    
    # Check if section already exists
    from app.models.users import get_section, SECTIONS_FILE, STUDENTS_DIR
    import csv
    import os
    from datetime import datetime
    import uuid
    
    existing_section = get_section(section_name)
    
    if existing_section:
        return jsonify({
            'success': True,
            'message': f'Section "{section_name}" already exists',
            'created': False
        })
    
    # Create new section with empty CSV file
    initialize_students_dir()
    initialize_sections_file()
    
    # Generate a unique filename for the section
    filename = f"{uuid.uuid4()}.csv"
    file_path = os.path.join(STUDENTS_DIR, filename)
    
    # Create empty CSV file with headers
    with open(file_path, 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['student_id', 'fullname', 'is_irregular', 'email', 'grade_level'])
    
    # Add to sections CSV
    with open(SECTIONS_FILE, 'a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([
            section_name,
            filename,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ])
    
    return jsonify({
        'success': True,
        'message': f'Section "{section_name}" created successfully',
        'created': True
    })

@auth.route('/add-single-student', methods=['POST'])
def add_single_student_route():
    # Admin check
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
    
    data = request.get_json()
    student_id = data.get('student_id')
    fullname = data.get('fullname')
    is_irregular = data.get('is_irregular', False)
    email = data.get('email', '')
    grade_level = data.get('grade_level', '')
    section_name = data.get('section_name')
    
    if not student_id or not fullname or not section_name:
        return jsonify({'success': False, 'error': 'Student ID, full name, and section are required'}), 400
    
    success, message = add_single_student(student_id, fullname, is_irregular, email, grade_level, section_name)
    
    return jsonify({
        'success': success,
        'message': message
    })

@auth.route('/update-student', methods=['POST'])
def update_student_route():
    # Admin check
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
    
    data = request.get_json()
    student_id = data.get('student_id')
    original_section_name = data.get('original_section_name')
    new_data = {
        'fullname': data.get('fullname'),
        'is_irregular': data.get('is_irregular', False),
        'email': data.get('email', ''),
        'grade_level': data.get('grade_level', ''),
        'section_name': data.get('section_name')
    }
    
    if not student_id or not original_section_name:
        return jsonify({'success': False, 'error': 'Student ID and original section name are required'}), 400
    
    if not new_data.get('fullname') or not new_data.get('section_name'):
        return jsonify({'success': False, 'error': 'Full name and section name are required'}), 400
    
    success, message = update_student(student_id, original_section_name, new_data)
    
    return jsonify({
        'success': success,
        'message': message
    })

@auth.route('/delete-student', methods=['POST'])
def delete_student_route():
    # Admin check
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
    
    data = request.get_json()
    section_name = data.get('section_name')
    student_id = data.get('student_id')
    
    if not section_name or not student_id:
        return jsonify({'success': False, 'error': 'Section name and student ID are required'}), 400
    
    success, message = delete_student_from_section(section_name, student_id)
    
    return jsonify({
        'success': success,
        'message': message
    })

@auth.route('/add-admin', methods=['POST'])
def add_admin():
    # Admin check
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
    
    data = request.get_json()
    name = data.get('name')
    email = data.get('email')
    
    if not name or not email:
        return jsonify({'success': False, 'error': 'Name and email are required'}), 400
    
    # Check if email already exists
    existing_user = get_user_by_email(email)
    if existing_user:
        return jsonify({'success': False, 'error': 'An account with this email already exists'}), 400
    
    # Generate username from email (use email as username for admins)
    username = email.lower()
    
    # Check if username already exists
    if get_user(username):
        return jsonify({'success': False, 'error': 'An account with this email already exists'}), 400
    
    # Generate verification code
    verification_code = ''.join(random.choices(string.digits, k=6))
    
    # Register admin with verification code
    success = register_user(
        username=username,
        password='',  # No password yet
        role='admin',
        email=email,
        name=name,
        verification_code=verification_code,
        verified='False'
    )
    
    if not success:
        return jsonify({'success': False, 'error': 'Failed to create admin account'}), 500
    
    # Send verification email
    email_sent, email_error = send_admin_verification_email(email, name, verification_code)
    
    if email_sent:
        return jsonify({
            'success': True,
            'message': f'Admin account created. Verification code sent to {email}.'
        })
    else:
        return jsonify({
            'success': True,
            'message': f'Admin account created, but email could not be sent: {email_error}'
        })

@auth.route('/verify-code', methods=['GET', 'POST'])
def verify_code():
    if request.method == 'POST':
        email = session.get('pending_email')
        if not email:
            flash('Session expired. Please log in again.', 'danger')
            return redirect(url_for('auth.login'))
        
        verification_code = request.form.get('verification_code')
        if not verification_code:
            flash('Please enter the verification code', 'danger')
            return render_template('verify_code.html', email=email)
        
        user = get_user_by_email(email)
        if not user or user.role != 'admin':
            flash('Invalid email', 'danger')
            session.pop('pending_email', None)
            return redirect(url_for('auth.login'))
        
        # Check verification code
        if user.verification_code == verification_code:
            # Code is correct, proceed to password creation
            session['pending_email'] = email
            session['verified'] = True
            return redirect(url_for('auth.create_password'))
        else:
            flash('Invalid verification code. Please try again.', 'danger')
            return render_template('verify_code.html', email=email)
    
    # GET request
    email = session.get('pending_email')
    if not email:
        flash('Please log in first', 'warning')
        return redirect(url_for('auth.login'))
    
    return render_template('verify_code.html', email=email)

@auth.route('/create-password', methods=['GET', 'POST'])
def create_password():
    if request.method == 'POST':
        email = session.get('pending_email')
        if not email or not session.get('verified'):
            flash('Please complete verification first', 'danger')
            return redirect(url_for('auth.login'))
        
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not password or not confirm_password:
            flash('Please fill in all fields', 'danger')
            return render_template('create_password.html', email=email)
        
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return render_template('create_password.html', email=email)
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long', 'danger')
            return render_template('create_password.html', email=email)
        
        # Update user password and mark as verified
        import csv
        import os
        from tempfile import NamedTemporaryFile
        import shutil
        from app.models.users import USERS_FILE
        
        user = get_user_by_email(email)
        if not user:
            flash('User not found', 'danger')
            session.clear()
            return redirect(url_for('auth.login'))
        
        temp_file = NamedTemporaryFile(mode='w', delete=False, newline='')
        
        try:
            with open(USERS_FILE, 'r', newline='') as csv_file, temp_file:
                reader = csv.DictReader(csv_file)
                fieldnames = reader.fieldnames or ['username', 'password_hash', 'role', 'email', 'name', 'verification_code', 'verified']
                
                # Ensure all columns exist
                if 'email' not in fieldnames:
                    fieldnames.extend(['email', 'name', 'verification_code', 'verified'])
                
                writer = csv.DictWriter(temp_file, fieldnames=fieldnames)
                writer.writeheader()
                
                for row in reader:
                    if row.get('email', '').lower() == email.lower():
                        row['password_hash'] = hash_password(password)
                        row['verification_code'] = ''
                        row['verified'] = 'True'
                    writer.writerow(row)
            
            shutil.move(temp_file.name, USERS_FILE)
            
            # Log in the user
            session['user_id'] = user.username
            session['role'] = user.role
            session.pop('pending_email', None)
            session.pop('verified', None)
            
            flash('Password created successfully! Welcome!', 'success')
            return redirect(url_for('main.index'))
        
        except Exception as e:
            flash(f'Error creating password: {str(e)}', 'danger')
            return render_template('create_password.html', email=email)
    
    # GET request
    email = session.get('pending_email')
    if not email or not session.get('verified'):
        flash('Please complete verification first', 'warning')
        return redirect(url_for('auth.login'))
    
    return render_template('create_password.html', email=email) 