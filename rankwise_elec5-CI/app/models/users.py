import os
import csv
import hashlib
from functools import wraps
from flask import session, redirect, url_for, flash

# Path to the users spreadsheet
USERS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'instance', 'users.csv')

# Path to the students directory
STUDENTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'instance', 'students')

# Path to the sections file
SECTIONS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'instance', 'sections.csv')

# Ensure the users file exists
def initialize_users_file():
    if not os.path.exists(USERS_FILE):
        os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
        with open(USERS_FILE, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['username', 'password_hash', 'role'])
            # Create default admin account
            writer.writerow(['admin', hash_password('admin'), 'admin'])

def reset_student_passwords_to_default():
    """Reset all student users' passwords to their default (student_id) value.
    This should be invoked on server startup to invalidate any temporary verification codes.
    """
    if not os.path.exists(USERS_FILE):
        initialize_users_file()
        return

    import csv
    from tempfile import NamedTemporaryFile
    import shutil

    temp_file = NamedTemporaryFile(mode='w', delete=False, newline='')
    try:
        with open(USERS_FILE, 'r', newline='') as csv_file, temp_file:
            reader = csv.DictReader(csv_file)
            fieldnames = reader.fieldnames or ['username', 'password_hash', 'role']
            writer = csv.DictWriter(temp_file, fieldnames=fieldnames)
            writer.writeheader()

            for row in reader:
                # For student rows, reset password_hash to hash(username)
                if row.get('role') == 'student' and row.get('username'):
                    row['password_hash'] = hash_password(row['username'])
                writer.writerow(row)

        shutil.move(temp_file.name, USERS_FILE)
    except Exception:
        # Best-effort reset; on failure leave file unchanged
        try:
            os.unlink(temp_file.name)
        except Exception:
            pass
            
# Ensure the students directory exists
def initialize_students_dir():
    if not os.path.exists(STUDENTS_DIR):
        os.makedirs(STUDENTS_DIR, exist_ok=True)
        
# Ensure the sections file exists
def initialize_sections_file():
    if not os.path.exists(SECTIONS_FILE):
        os.makedirs(os.path.dirname(SECTIONS_FILE), exist_ok=True)
        with open(SECTIONS_FILE, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['section_name', 'file_name', 'upload_date'])

# Hash password for security
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# User class to represent a user
class User:
    def __init__(self, username, role):
        self.username = username
        self.role = role
        
    def is_admin(self):
        return self.role == 'admin'
        
    def is_student(self):
        return self.role == 'student'

# Student class to represent a student
class Student:
    def __init__(self, student_id, fullname, is_irregular, email, grade_level=None, username=None, password_hash=None, section=None):
        self.student_id = student_id
        self.fullname = fullname
        self.is_irregular = is_irregular
        self.email = email
        self.grade_level = grade_level
        # Use student_id as username
        self.username = username or student_id
        self.password_hash = password_hash
        self.section = section
        
    def to_dict(self):
        return {
            'student_id': self.student_id,
            'fullname': self.fullname,
            'is_irregular': self.is_irregular,
            'email': self.email,
            'grade_level': self.grade_level,
            'username': self.username,
            'section': self.section
        }

# Section class to represent a class section
class Section:
    def __init__(self, name, file_name, upload_date):
        self.name = name
        self.file_name = file_name
        self.upload_date = upload_date
        self._students = None
        
    @property
    def students(self):
        # Lazy load students only when needed
        if self._students is None:
            self._students = []
            file_path = os.path.join(STUDENTS_DIR, self.file_name)
            if os.path.exists(file_path):
                with open(file_path, 'r', newline='') as file:
                    reader = csv.DictReader(file)
                    for row in reader:
                        try:
                            student = Student(
                                row.get('student_id', ''),
                                row.get('fullname', ''),
                                row.get('is_irregular', 'No'),
                                row.get('email', ''),
                                row.get('grade_level', ''),
                                row.get('username', ''),
                                None,
                                self.name
                            )
                            self._students.append(student)
                        except Exception as e:
                            print(f"Error loading student: {e}")
        return self._students
    
    @property
    def student_count(self):
        return len(self.students)

# Get user by username
def get_user(username):
    if not os.path.exists(USERS_FILE):
        initialize_users_file()
        
    with open(USERS_FILE, 'r', newline='') as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row['username'] == username:
                return User(row['username'], row['role'])
    return None

# Authenticate user
def authenticate_user(username, password):
    if not os.path.exists(USERS_FILE):
        initialize_users_file()
    
    # Check admin/regular users first
    with open(USERS_FILE, 'r', newline='') as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row['username'] == username and row['password_hash'] == hash_password(password):
                return User(row['username'], row['role'])
    
    # Look through all student sections for matching credentials
    sections = get_all_sections()
    for section in sections:
        for student in section.students:
            # For students, both username and password are the student ID
            if student.student_id == username and hash_password(student.student_id) == hash_password(password):
                # Register the user automatically if they're not in the users file
                if not get_user(username):
                    register_user(student.student_id, student.student_id, 'student')
                return User(student.student_id, 'student')
    
    return None

# Register a new user
def register_user(username, password, role='student'):
    if not os.path.exists(USERS_FILE):
        initialize_users_file()
    
    # Check if user already exists
    if get_user(username):
        return False
    
    # Append new user to the CSV
    with open(USERS_FILE, 'a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([username, hash_password(password), role])
    
    return True

# Get all sections
def get_all_sections():
    if not os.path.exists(SECTIONS_FILE):
        initialize_sections_file()
    
    sections = []
    try:
        with open(SECTIONS_FILE, 'r', newline='') as file:
            reader = csv.DictReader(file)
            for row in reader:
                section = Section(
                    row['section_name'],
                    row['file_name'],
                    row['upload_date']
                )
                sections.append(section)
    except Exception as e:
        print(f"Error reading sections file: {e}")
    
    return sections

# Get a specific section by name
def get_section(section_name):
    sections = get_all_sections()
    for section in sections:
        if section.name == section_name:
            return section
    return None

# Get all students from all sections
def get_all_students():
    students = []
    sections = get_all_sections()
    
    for section in sections:
        students.extend(section.students)
    
    return students

# Save a new section from uploaded Excel file
def save_section_from_excel(section_name, excel_file):
    # Ensure directories exist
    initialize_students_dir()
    initialize_sections_file()
    
    # Generate a unique filename
    import uuid
    from datetime import datetime
    import pandas as pd
    
    # Generate temporary Excel filename
    temp_excel = f"{uuid.uuid4()}.xlsx"
    temp_excel_path = os.path.join(STUDENTS_DIR, temp_excel)
    
    # Generate CSV filename for storage
    filename = f"{uuid.uuid4()}.csv"
    file_path = os.path.join(STUDENTS_DIR, filename)
    
    # Save the uploaded file temporarily
    excel_file.save(temp_excel_path)
    
    try:
        # Read Excel file with pandas
        df = pd.read_excel(temp_excel_path)
        
        # Normalize column names (case insensitive)
        df.columns = [col.lower().strip() for col in df.columns]
        
        # Check required fields
        required_fields = ['studentid', 'name', 'email', 'isregular', 'gradelevel']
        mapping = {
            'studentid': 'student_id',
            'name': 'fullname',
            'isregular': 'is_irregular',
            'gradelevel': 'grade_level'
        }
        
        # Validate required fields exist
        for field in required_fields:
            if field not in df.columns:
                os.remove(temp_excel_path)
                return False, f"Missing required column: {field}"
        
        # Extract and rename only the columns we need
        columns_to_extract = {}
        
        # Handle studentid -> student_id
        columns_to_extract['student_id'] = df['studentid']
        
        # Handle name -> fullname
        columns_to_extract['fullname'] = df['name']
        
        # Handle isRegular -> is_irregular (convert to Yes/No)
        # Convert boolean/numeric to Yes/No string
        # If True or 1, it's Regular (so is_irregular is "No")
        # If False or 0, it's Irregular (so is_irregular is "Yes")
        is_irregular = []
        for val in df['isregular']:
            if isinstance(val, bool):
                is_irregular.append("No" if val else "Yes")
            elif isinstance(val, (int, float)):
                is_irregular.append("No" if val else "Yes")
            elif isinstance(val, str):
                val_lower = val.lower()
                if val_lower in ['true', 'yes', '1', 'regular']:
                    is_irregular.append("No")
                else:
                    is_irregular.append("Yes")
            else:
                is_irregular.append("Yes")
        columns_to_extract['is_irregular'] = is_irregular
        
        # Handle email
        columns_to_extract['email'] = df['email']
        
        # Handle grade level
        columns_to_extract['grade_level'] = df['gradelevel']
        
        # Create new dataframe with only the columns we need
        new_df = pd.DataFrame(columns_to_extract)
        
        # Check for duplicate student IDs
        duplicate_students = []
        for student_id in new_df['student_id']:
            if student_id_exists(student_id):
                duplicate_students.append(student_id)
        
        if duplicate_students:
            # Clean up temporary files
            if os.path.exists(temp_excel_path):
                os.remove(temp_excel_path)
            if os.path.exists(file_path):
                os.remove(file_path)
            return False, f"Duplicate student IDs found: {', '.join(duplicate_students)}. Student IDs must be unique across all sections."
        
        # Save as CSV
        new_df.to_csv(file_path, index=False)
        
        # Clean up temporary Excel file
        os.remove(temp_excel_path)
        
    except Exception as e:
        # Clean up temporary files in case of error
        if os.path.exists(temp_excel_path):
            os.remove(temp_excel_path)
        if os.path.exists(file_path):
            os.remove(file_path)
        return False, f"Error processing Excel file: {e}"
    
    # Add to sections CSV
    with open(SECTIONS_FILE, 'a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([
            section_name, 
            filename, 
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ])
    
    # Register student users
    register_students_from_section(section_name)
    
    return True, "Section added successfully"

# Check if student ID already exists across all sections
def student_id_exists(student_id):
    """Check if a student ID already exists in any section"""
    if not student_id:
        return False
    
    sections = get_all_sections()
    for section in sections:
        for student in section.students:
            if student.student_id == student_id:
                return True
    return False

# Register students from a section as users
def register_students_from_section(section_name):
    section = get_section(section_name)
    if not section:
        return False
    
    for student in section.students:
        # Skip if no student ID
        if not student.student_id:
            continue
        
        # Register user if not exists - use student ID as username
        if not get_user(student.student_id):
            register_user(student.student_id, student.student_id, 'student')
    
    return True

# Delete a section and all its students
def delete_section(section_name):
    """Delete a section and all its students"""
    try:
        # Find the section
        sections = get_all_sections()
        section_to_delete = None
        
        for section in sections:
            if section.name == section_name:
                section_to_delete = section
                break
        
        if not section_to_delete:
            return False, "Section not found"
        
        # Delete the CSV file
        file_path = os.path.join(STUDENTS_DIR, section_to_delete.file_name)
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Remove from sections CSV
        temp_file = os.path.join(os.path.dirname(SECTIONS_FILE), 'temp_sections.csv')
        
        with open(SECTIONS_FILE, 'r', newline='') as file, open(temp_file, 'w', newline='') as temp:
            reader = csv.DictReader(file)
            writer = csv.DictWriter(temp, fieldnames=reader.fieldnames)
            writer.writeheader()
            
            for row in reader:
                if row['section_name'] != section_name:
                    writer.writerow(row)
        
        # Replace the original file
        os.replace(temp_file, SECTIONS_FILE)
        
        return True, f"Section '{section_name}' deleted successfully"
        
    except Exception as e:
        return False, f"Error deleting section: {str(e)}"

# Delete a specific student from a section
def delete_student_from_section(section_name, student_id):
    """Delete a specific student from a section"""
    try:
        # Find the section
        section = get_section(section_name)
        if not section:
            return False, "Section not found"
        
        # Read the current CSV file
        file_path = os.path.join(STUDENTS_DIR, section.file_name)
        if not os.path.exists(file_path):
            return False, "Section file not found"
        
        temp_file = os.path.join(STUDENTS_DIR, f'temp_{section.file_name}')
        
        with open(file_path, 'r', newline='') as file, open(temp_file, 'w', newline='') as temp:
            reader = csv.DictReader(file)
            writer = csv.DictWriter(temp, fieldnames=reader.fieldnames)
            writer.writeheader()
            
            student_found = False
            for row in reader:
                if row['student_id'] != student_id:
                    writer.writerow(row)
                else:
                    student_found = True
            
            if not student_found:
                os.remove(temp_file)
                return False, "Student not found in section"
        
        # Replace the original file
        os.replace(temp_file, file_path)
        
        return True, f"Student '{student_id}' deleted from section '{section_name}'"
        
    except Exception as e:
        return False, f"Error deleting student: {str(e)}"

# Move a student to a different section
def move_student_to_section(student_id, from_section_name, to_section_name):
    """Move a student from one section to another"""
    try:
        # Check if student exists in the source section
        from_section = get_section(from_section_name)
        if not from_section:
            return False, "Source section not found"
        
        # Check if destination section exists
        to_section = get_section(to_section_name)
        if not to_section:
            return False, "Destination section not found"
        
        # Find the student in the source section
        student_to_move = None
        for student in from_section.students:
            if student.student_id == student_id:
                student_to_move = student
                break
        
        if not student_to_move:
            return False, "Student not found in source section"
        
        # Check if student is irregular (only irregular students can be moved)
        if student_to_move.is_irregular != 'Yes':
            return False, "Only irregular students can be moved between sections"
        
        # Check if student ID already exists in destination section
        for student in to_section.students:
            if student.student_id == student_id:
                return False, "Student ID already exists in destination section"
        
        # Remove student from source section
        success, message = delete_student_from_section(from_section_name, student_id)
        if not success:
            return False, f"Error removing student from source section: {message}"
        
        # Add student to destination section
        file_path = os.path.join(STUDENTS_DIR, to_section.file_name)
        
        with open(file_path, 'a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([
                student_to_move.student_id,
                student_to_move.fullname,
                student_to_move.is_irregular,
                student_to_move.email,
                student_to_move.grade_level
            ])
        
        return True, f"Student '{student_id}' moved from '{from_section_name}' to '{to_section_name}' successfully"
        
    except Exception as e:
        return False, f"Error moving student: {str(e)}"

# Get all sections for dropdown
def get_all_section_names():
    """Get a list of all section names"""
    sections = get_all_sections()
    return [section.name for section in sections]

# Add a single student manually
def add_single_student(student_id, fullname, is_irregular, email, grade_level, section_name):
    """Add a single student to a specific section"""
    try:
        # Validate required fields
        if not student_id or not fullname or not section_name:
            return False, "Student ID, full name, and section are required"
        
        # Check if student ID already exists
        if student_id_exists(student_id):
            return False, f"Student ID '{student_id}' already exists in another section"
        
        # Check if section exists
        section = get_section(section_name)
        if not section:
            return False, f"Section '{section_name}' not found"
        
        # Check if student ID already exists in the target section
        for student in section.students:
            if student.student_id == student_id:
                return False, f"Student ID '{student_id}' already exists in section '{section_name}'"
        
        # Prepare student data
        student_data = {
            'student_id': student_id,
            'fullname': fullname,
            'is_irregular': 'Yes' if is_irregular else 'No',
            'email': email or '',
            'grade_level': grade_level or ''
        }
        
        # Add student to the section's CSV file
        file_path = os.path.join(STUDENTS_DIR, section.file_name)
        
        with open(file_path, 'a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([
                student_data['student_id'],
                student_data['fullname'],
                student_data['is_irregular'],
                student_data['email'],
                student_data['grade_level']
            ])
        
        # Register the student as a user
        register_user(student_id, student_id, 'student')
        
        return True, f"Student '{fullname}' (ID: {student_id}) added to section '{section_name}' successfully"
        
    except Exception as e:
        return False, f"Error adding student: {str(e)}"

# Decorator for requiring login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

# Decorator for requiring admin role
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page', 'warning')
            return redirect(url_for('auth.login'))
        
        user = get_user(session['user_id'])
        if not user or not user.is_admin():
            flash('You do not have permission to access this page', 'danger')
            return redirect(url_for('main.index'))
            
        return f(*args, **kwargs)
    return decorated_function 