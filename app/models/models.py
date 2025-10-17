from app import db
from datetime import datetime
import json

class Form(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_visible = db.Column(db.Boolean, default=True)  # Toggle for form visibility
    questions = db.relationship('Question', backref='form', lazy=True, cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"Form('{self.title}')"

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    form_id = db.Column(db.Integer, db.ForeignKey('form.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20), nullable=False)  # 'multiple_choice', 'identification', 'coding'
    options = db.Column(db.Text, nullable=True)  # JSON string for multiple choice options
    sample_code = db.Column(db.Text, nullable=True)  # For coding questions
    expected_output = db.Column(db.Text, nullable=True)  # For coding questions
    correct_answer = db.Column(db.Text, nullable=True)  # For correct answer in multiple choice and identification
    order = db.Column(db.Integer, default=0)
    points = db.Column(db.Integer, default=1)  # Points value for the question
    
    # Add cascade delete to answers when a question is deleted
    answers = db.relationship('Answer', backref='question', lazy=True, cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"Question('{self.question_text[:20]}...')"
    
    def get_options(self):
        if self.options and self.question_type in ['multiple_choice', 'checkbox']:
            return json.loads(self.options)
        if self.question_type == 'true_false':
            return ['True', 'False']
        return []
    
    def set_options(self, options_list):
        if self.question_type in ['multiple_choice', 'checkbox']:
            self.options = json.dumps(options_list)
    
    def get_correct_answers(self):
        """Return list of correct answers for checkbox/enumeration, or single-item list for others."""
        if not self.correct_answer:
            return []
        if self.question_type in ['checkbox', 'enumeration']:
            try:
                data = json.loads(self.correct_answer)
                return data if isinstance(data, list) else []
            except Exception:
                return []
        return [self.correct_answer]

class Response(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    form_id = db.Column(db.Integer, db.ForeignKey('form.id'), nullable=False)
    submitted_by = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    answers = db.relationship('Answer', backref='response', lazy=True, cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"Response('{self.id}')"

class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    response_id = db.Column(db.Integer, db.ForeignKey('response.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    answer_text = db.Column(db.Text, nullable=True)
    is_correct = db.Column(db.Boolean, default=False)
    score_percentage = db.Column(db.Float, default=0)  # Percentage score for partial credit (0-100)
    feedback = db.Column(db.Text, nullable=True)  # To store AI feedback for coding questions
    
    def __repr__(self):
        return f"Answer('{self.answer_text[:20]}...')"

class Dataset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    filename = db.Column(db.String(255), nullable=False)  # Built-in filename
    file_path = db.Column(db.String(500), nullable=False)  # Path to built-in file
    file_size = db.Column(db.Integer, nullable=False)  # File size in bytes
    columns = db.Column(db.Text, nullable=True)  # JSON string of column names
    row_count = db.Column(db.Integer, default=0)  # Number of data rows
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)  # Whether dataset is available for AI context
    is_builtin = db.Column(db.Boolean, default=True)  # Whether this is a built-in dataset
    
    def __repr__(self):
        return f"Dataset('{self.name}')"
    
    def get_columns(self):
        """Return list of column names."""
        if self.columns:
            try:
                return json.loads(self.columns)
            except Exception:
                return []
        return []
    
    def set_columns(self, columns_list):
        """Set column names from a list."""
        self.columns = json.dumps(columns_list)
    
    def get_sample_data(self, limit=5):
        """Return sample data from the dataset for preview."""
        try:
            import pandas as pd
            df = pd.read_csv(self.file_path)
            return df.head(limit).to_dict('records')
        except Exception as e:
            print(f"Error reading dataset sample: {e}")
            return [] 