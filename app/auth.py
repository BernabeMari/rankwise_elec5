from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
import random
import string
from app.models.users import (
    authenticate_user, register_user, get_user, initialize_users_file, 
    initialize_students_dir, initialize_sections_file, get_all_sections, 
    get_all_students, save_section_from_excel, hash_password
)

auth = Blueprint('auth', __name__)

# Dictionary to store student verification codes
student_verification_codes = {}

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Please enter both username and password', 'danger')
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
    
    # Ensure users file exists with default admin
    initialize_users_file()
    
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
    
    # Get student ID from request
    data = request.get_json()
    if not data or 'student_id' not in data:
        return jsonify({'success': False, 'error': 'Student ID is required'}), 400
    
    student_id = data['student_id']
    
    # Generate a random 6-digit verification code
    verification_code = ''.join(random.choices(string.digits, k=6))
    
    # Store the verification code in our dictionary
    student_verification_codes[student_id] = verification_code
    
    # Update the user's password to the verification code
    import csv
    import os
    from tempfile import NamedTemporaryFile
    import shutil
    from app.models.users import USERS_FILE
    
    if not os.path.exists(USERS_FILE):
        initialize_users_file()
    
    # Check if user exists
    user_exists = False
    temp_file = NamedTemporaryFile(mode='w', delete=False, newline='')
    
    try:
        with open(USERS_FILE, 'r', newline='') as csv_file, temp_file:
            reader = csv.DictReader(csv_file)
            fieldnames = reader.fieldnames
            
            writer = csv.DictWriter(temp_file, fieldnames=fieldnames)
            writer.writeheader()
            
            for row in reader:
                if row['username'] == student_id:
                    row['password_hash'] = hash_password(verification_code)
                    user_exists = True
                writer.writerow(row)
        
        # Replace the original file with the temporary file
        shutil.move(temp_file.name, USERS_FILE)
        
        # If user doesn't exist, create it
        if not user_exists:
            with open(USERS_FILE, 'a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow([student_id, hash_password(verification_code), 'student'])
        
        return jsonify({
            'success': True,
            'verification_code': verification_code,
            'message': 'Verification code generated successfully'
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
    
    generated_codes = []
    
    import csv
    import os
    from tempfile import NamedTemporaryFile
    import shutil
    from app.models.users import USERS_FILE
    
    if not os.path.exists(USERS_FILE):
        initialize_users_file()
    
    # Read all existing users
    existing_users = {}
    try:
        with open(USERS_FILE, 'r', newline='') as csv_file:
            reader = csv.DictReader(csv_file)
            fieldnames = reader.fieldnames
            
            for row in reader:
                existing_users[row['username']] = row
    
        # Create temporary file for writing updated users
        temp_file = NamedTemporaryFile(mode='w', delete=False, newline='')
        
        with temp_file:
            writer = csv.DictWriter(temp_file, fieldnames=fieldnames)
            writer.writeheader()
            
            # Process each student ID
            for student_id in student_ids:
                # Generate a 6-digit verification code
                verification_code = ''.join(random.choices(string.digits, k=6))
                
                # Store the verification code in our dictionary
                student_verification_codes[student_id] = verification_code
                
                # Add to the generated codes list
                generated_codes.append({
                    'student_id': student_id,
                    'verification_code': verification_code
                })
                
                # Update or add user in the CSV
                if student_id in existing_users:
                    existing_users[student_id]['password_hash'] = hash_password(verification_code)
                else:
                    existing_users[student_id] = {
                        'username': student_id,
                        'password_hash': hash_password(verification_code),
                        'role': 'student'
                    }
            
            # Write all users back to the file
            for username, user_data in existing_users.items():
                writer.writerow(user_data)
        
        # Replace the original file with the temporary file
        shutil.move(temp_file.name, USERS_FILE)
        
        return jsonify({
            'success': True,
            'codes': generated_codes,
            'message': f'Generated {len(generated_codes)} verification codes successfully'
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@auth.route('/remove-verification-codes', methods=['POST'])
def remove_verification_codes():
    # Admin check
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
    
    data = request.get_json()
    student_ids = data.get('student_ids', [])
    
    if not student_ids:
        return jsonify({'success': False, 'error': 'Student IDs are required'}), 400
    
    for student_id in student_ids:
        # Remove the verification code if it exists
        if student_id in student_verification_codes:
            del student_verification_codes[student_id]
    
    return jsonify({
        'success': True,
        'message': f'Removed verification codes for {len(student_ids)} students'
    })

@auth.route('/get-verification-codes', methods=['GET'])
def get_verification_codes():
    # Admin check
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
    
    codes = []
    
    for student_id, verification_code in student_verification_codes.items():
        codes.append({
            'student_id': student_id,
            'verification_code': verification_code
        })
    
    return jsonify({
        'success': True,
        'codes': codes
    }) 