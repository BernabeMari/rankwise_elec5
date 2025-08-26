# Flask Application Study Plan - RankWise

## Overview
This is a Flask-based form/quiz management system with authentication, user management, and assessment functionality. The application uses SQLAlchemy for database operations and CSV files for user management.

---

## Day 1: Foundation & Authentication Setup

### Focus: `app/__init__.py` and `app/auth.py`

#### Key Concepts to Memorize:

**1. Application Factory Pattern (`__init__.py`)**
```python
def create_app():
    app = Flask(__name__)
    # Configuration
    app.config['SECRET_KEY'] = 'your-secret-key'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///forms.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize extensions
    db.init_app(app)
    
    # Register blueprints
    from app.auth import auth
    app.register_blueprint(auth, url_prefix='/auth')
    
    from app.routes import main
    app.register_blueprint(main)
    
    return app
```

**2. Blueprint Registration Pattern**
- `auth` blueprint with `/auth` prefix
- `main` blueprint for core routes
- Context processors for global variables

**3. Authentication Flow (`auth.py`)**
```python
@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = authenticate_user(username, password)
        if user:
            session['user_id'] = user.username
            session['role'] = user.role
            return redirect(url_for('main.index'))
```

**4. Session Management**
- `session['user_id']` - stores logged-in user
- `session['role']` - stores user role (admin/student)
- `session.clear()` - logout functionality

**5. Admin-Only Routes Pattern**
```python
@auth.route('/admin/users', methods=['GET', 'POST'])
def manage_users():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('You must be an admin to access this page', 'danger')
        return redirect(url_for('main.index'))
```

#### Memorization Points:
- Flask app factory pattern
- Blueprint registration with URL prefixes
- Session-based authentication
- Role-based access control
- Flash message system

---

## Day 2: User Management & Data Models

### Focus: `app/models/users.py`

#### Key Concepts to Memorize:

**1. File Path Management**
```python
USERS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'instance', 'users.csv')
STUDENTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'instance', 'students')
SECTIONS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'instance', 'sections.csv')
```

**2. Password Hashing**
```python
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()
```

**3. User Classes**
```python
class User:
    def __init__(self, username, role):
        self.username = username
        self.role = role
        
    def is_admin(self):
        return self.role == 'admin'
        
    def is_student(self):
        return self.role == 'student'

class Student:
    def __init__(self, student_id, fullname, is_irregular, email, grade_level=None, username=None, password_hash=None, section=None):
        self.student_id = student_id
        self.fullname = fullname
        self.is_irregular = is_irregular
        self.email = email
        self.grade_level = grade_level
        self.username = username or student_id
        self.password_hash = password_hash
        self.section = section
```

**4. Authentication Logic**
```python
def authenticate_user(username, password):
    # Check admin/regular users first
    with open(USERS_FILE, 'r', newline='') as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row['username'] == username and row['password_hash'] == hash_password(password):
                return User(row['username'], row['role'])
    
    # Look through student sections
    sections = get_all_sections()
    for section in sections:
        for student in section.students:
            if student.student_id == username and hash_password(student.student_id) == hash_password(password):
                return User(student.student_id, 'student')
    
    return None
```

**5. Decorator Pattern for Authorization**
```python
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

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
```

#### Memorization Points:
- CSV-based user storage
- SHA-256 password hashing
- Class-based user representation
- Multi-level authentication (admin + student sections)
- Decorator-based authorization
- File initialization patterns

---

## Day 3: Database Models & Core Functionality

### Focus: `app/models/models.py` and `app/routes.py` (first half)

#### Key Concepts to Memorize:

**1. SQLAlchemy Model Relationships**
```python
class Form(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    questions = db.relationship('Question', backref='form', lazy=True, cascade='all, delete-orphan')
    responses = db.relationship('Response', backref='form', lazy=True, cascade='all, delete-orphan')

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    form_id = db.Column(db.Integer, db.ForeignKey('form.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(50), nullable=False)
    order = db.Column(db.Integer, nullable=False)
    correct_answer = db.Column(db.Text)
    points = db.Column(db.Integer, default=1)
    options = db.relationship('QuestionOption', backref='question', lazy=True, cascade='all, delete-orphan')

class Response(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    form_id = db.Column(db.Integer, db.ForeignKey('form.id'), nullable=False)
    submitted_by = db.Column(db.String(100))
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    answers = db.relationship('Answer', backref='response', lazy=True, cascade='all, delete-orphan')
```

**2. Route Patterns**
```python
@main.route('/')
@login_required
def index():
    forms = Form.query.order_by(Form.created_at.desc()).all()
    user = get_user(session['user_id'])
    return render_template('index.html', forms=forms, user=user)

@main.route('/form/new', methods=['GET', 'POST'])
@admin_required
def new_form():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        
        if not title:
            flash('Title is required!', 'danger')
            return redirect(url_for('main.new_form'))
        
        form = Form(title=title, description=description)
        db.session.add(form)
        db.session.commit()
        
        return redirect(url_for('main.edit_form', form_id=form.id))
    
    return render_template('new_form.html')
```

**3. Form Processing Pattern**
```python
@main.route('/form/<int:form_id>/question/new', methods=['POST'])
@admin_required
def add_question(form_id):
    form = Form.query.get_or_404(form_id)
    
    question_text = request.form.get('question_text')
    question_type = request.form.get('question_type')
    correct_answer = request.form.get('correct_answer')
    points = request.form.get('points', 1)
    
    # Validation
    if not question_text or not question_type:
        flash('Question text and type are required!', 'danger')
        return redirect(url_for('main.edit_form', form_id=form_id))
    
    # Get highest order and add 1
    highest_order = db.session.query(db.func.max(Question.order)).filter_by(form_id=form_id).scalar() or 0
    new_order = highest_order + 1
    
    question = Question(
        form_id=form_id,
        question_text=question_text,
        question_type=question_type,
        order=new_order,
        correct_answer=correct_answer,
        points=points
    )
    
    db.session.add(question)
    db.session.commit()
```

#### Memorization Points:
- SQLAlchemy model relationships (one-to-many, cascade deletes)
- Route decorators and HTTP methods
- Form validation patterns
- Database session management
- Error handling with flash messages
- Order management for questions

---

## Day 4: Advanced Routes & Response Handling

### Focus: `app/routes.py` (second half) and Response Processing

#### Key Concepts to Memorize:

**1. Form Response Processing**
```python
@main.route('/form/<int:form_id>/submit', methods=['POST'])
@login_required
def submit_response(form_id):
    form = Form.query.get_or_404(form_id)
    
    # Check if user already submitted
    existing_response = Response.query.filter_by(
        form_id=form_id, 
        submitted_by=session['user_id']
    ).first()
    
    if existing_response:
        flash('You have already submitted a response for this form', 'warning')
        return redirect(url_for('main.view_form', form_id=form_id))
    
    # Create new response
    response = Response(
        form_id=form_id,
        submitted_by=session['user_id']
    )
    db.session.add(response)
    db.session.commit()
    
    # Process answers
    questions = Question.query.filter_by(form_id=form_id).order_by(Question.order).all()
    total_score = 0
    
    for question in questions:
        answer_text = request.form.get(f'answer_{question.id}')
        
        if answer_text:
            # Calculate score for this question
            score = 0
            if question.question_type == 'multiple_choice':
                if answer_text == question.correct_answer:
                    score = question.points
            elif question.question_type == 'text':
                # For text questions, always give points (manual review needed)
                score = question.points
            
            answer = Answer(
                response_id=response.id,
                question_id=question.id,
                answer_text=answer_text,
                score=score
            )
            db.session.add(answer)
            total_score += score
    
    response.total_score = total_score
    db.session.commit()
```

**2. Score Calculation Logic**
```python
def calculate_score(question, answer_text):
    if question.question_type == 'multiple_choice':
        return question.points if answer_text == question.correct_answer else 0
    elif question.question_type == 'text':
        return question.points  # Manual review needed
    return 0
```

**3. Response Viewing Patterns**
```python
@main.route('/form/<int:form_id>/responses')
@admin_required
def view_responses(form_id):
    form = Form.query.get_or_404(form_id)
    responses = Response.query.filter_by(form_id=form_id).order_by(Response.submitted_at.desc()).all()
    
    # Calculate statistics
    total_responses = len(responses)
    if total_responses > 0:
        average_score = sum(r.total_score for r in responses) / total_responses
        highest_score = max(r.total_score for r in responses)
        lowest_score = min(r.total_score for r in responses)
    else:
        average_score = highest_score = lowest_score = 0
    
    return render_template('responses.html', 
                         form=form, 
                         responses=responses,
                         total_responses=total_responses,
                         average_score=average_score,
                         highest_score=highest_score,
                         lowest_score=lowest_score)
```

#### Memorization Points:
- Response submission validation
- Score calculation algorithms
- Database transaction management
- Statistical calculations
- Admin-only response viewing
- Duplicate submission prevention

---

## Day 5: Templates & Frontend Integration

### Focus: Template Structure and JavaScript Integration

#### Key Concepts to Memorize:

**1. Template Inheritance Pattern**
```html
<!-- base.html -->
<!DOCTYPE html>
<html>
<head>
    <title>{% block title %}{% endblock %}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/styles.css') }}">
</head>
<body>
    <nav>
        <!-- Navigation -->
    </nav>
    
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        {% block content %}{% endblock %}
    </div>
    
    <script src="{{ url_for('static', filename='js/ai-connector.js') }}"></script>
</body>
</html>
```

**2. Form Rendering Pattern**
```html
<!-- view_form.html -->
<form method="POST" action="{{ url_for('main.submit_response', form_id=form.id) }}">
    {% for question in questions %}
    <div class="question">
        <h4>{{ question.question_text }}</h4>
        <p>Points: {{ question.points }}</p>
        
        {% if question.question_type == 'multiple_choice' %}
            {% for option in question.options %}
            <div class="form-check">
                <input type="radio" name="answer_{{ question.id }}" value="{{ option.option_text }}" required>
                <label>{{ option.option_text }}</label>
            </div>
            {% endfor %}
        {% elif question.question_type == 'text' %}
            <textarea name="answer_{{ question.id }}" required></textarea>
        {% endif %}
    </div>
    {% endfor %}
    
    <button type="submit">Submit Response</button>
</form>
```

**3. JavaScript Integration**
```javascript
// ai-connector.js
function generateVerificationCode(studentId) {
    fetch('/auth/generate-verification-code', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ student_id: studentId })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert(`Verification code: ${data.verification_code}`);
        } else {
            alert('Error: ' + data.error);
        }
    });
}
```

#### Memorization Points:
- Jinja2 template syntax
- Flash message handling
- Form rendering with dynamic questions
- Static file serving
- AJAX integration patterns
- Bootstrap/CSS integration

---

## Day 6: Advanced Features & Integration

### Focus: Excel Import, Verification Codes, and AI Features

#### Key Concepts to Memorize:

**1. Excel File Processing**
```python
def save_section_from_excel(section_name, excel_file):
    import pandas as pd
    import uuid
    
    # Generate unique filename
    filename = f"{uuid.uuid4()}.csv"
    file_path = os.path.join(STUDENTS_DIR, filename)
    
    # Read Excel with pandas
    df = pd.read_excel(excel_file)
    df.columns = [col.lower().strip() for col in df.columns]
    
    # Validate required fields
    required_fields = ['studentid', 'name', 'email', 'isregular', 'gradelevel']
    for field in required_fields:
        if field not in df.columns:
            return False, f"Missing required column: {field}"
    
    # Process and save as CSV
    new_df = pd.DataFrame({
        'student_id': df['studentid'],
        'fullname': df['name'],
        'email': df['email'],
        'is_irregular': ['No' if val else 'Yes' for val in df['isregular']],
        'grade_level': df['gradelevel']
    })
    
    new_df.to_csv(file_path, index=False)
    
    # Add to sections CSV
    with open(SECTIONS_FILE, 'a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([section_name, filename, datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
    
    return True, "Section added successfully"
```

**2. Verification Code System**
```python
@auth.route('/generate-verification-code', methods=['POST'])
def generate_verification_code():
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
    
    data = request.get_json()
    student_id = data['student_id']
    
    # Generate 6-digit code
    verification_code = ''.join(random.choices(string.digits, k=6))
    student_verification_codes[student_id] = verification_code
    
    # Update user password
    update_user_password(student_id, verification_code)
    
    return jsonify({
        'success': True,
        'verification_code': verification_code
    })
```

**3. Bulk Operations**
```python
@auth.route('/generate-bulk-verification-codes', methods=['POST'])
def generate_bulk_verification_codes():
    data = request.get_json()
    student_ids = data.get('student_ids', [])
    
    generated_codes = []
    for student_id in student_ids:
        verification_code = ''.join(random.choices(string.digits, k=6))
        student_verification_codes[student_id] = verification_code
        update_user_password(student_id, verification_code)
        generated_codes.append({
            'student_id': student_id,
            'verification_code': verification_code
        })
    
    return jsonify({
        'success': True,
        'codes': generated_codes
    })
```

#### Memorization Points:
- Pandas Excel processing
- UUID generation for unique filenames
- Bulk operation patterns
- JSON API responses
- Error handling in file operations
- Verification code generation and storage

---

## Day 7: Testing & Deployment Preparation

### Focus: Database Setup, Requirements, and Configuration

#### Key Concepts to Memorize:

**1. Database Initialization**
```python
# create_db.py
from app import create_app, db
from app.models.models import Form, Question, Response, Answer, QuestionOption

app = create_app()
with app.app_context():
    db.create_all()
    print("Database tables created successfully!")
```

**2. Requirements Management**
```txt
Flask==2.3.3
Flask-SQLAlchemy==3.0.5
pandas==2.0.3
openpyxl==3.1.2
```

**3. Application Entry Point**
```python
# run.py
from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
```

**4. File Structure Understanding**
```
rankwise/
├── app/
│   ├── __init__.py          # App factory
│   ├── auth.py              # Authentication routes
│   ├── routes.py            # Main application routes
│   ├── models/
│   │   ├── models.py        # Database models
│   │   └── users.py         # User management
│   ├── static/              # CSS, JS, images
│   └── templates/           # HTML templates
├── instance/                # Database and data files
├── create_db.py            # Database initialization
├── requirements.txt        # Dependencies
└── run.py                 # Application entry point
```

#### Memorization Points:
- Database initialization patterns
- Dependency management
- Application entry points
- File organization structure
- Development vs production configuration
- Error handling and logging

---

## Study Tips:

1. **Start with Day 1** - Master the application factory and authentication flow
2. **Practice coding** - Try to recreate key functions from memory
3. **Understand relationships** - Focus on how different components interact
4. **Test the application** - Run it locally to see how everything works together
5. **Review daily** - Spend 15-30 minutes each day reviewing previous concepts

## Key Patterns to Remember:

- **Blueprint Pattern**: Organizing routes into modules
- **Factory Pattern**: Creating Flask app instances
- **Decorator Pattern**: Authentication and authorization
- **Session Management**: User state across requests
- **Database Relationships**: One-to-many, cascade operations
- **Form Processing**: Validation, submission, scoring
- **File Operations**: CSV/Excel processing, unique naming
- **API Design**: JSON responses, error handling

This study plan covers the complete Flask application architecture and should give you a solid understanding of how all the components work together! 