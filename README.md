# Python Forms Application

A responsive web application similar to Google Forms, built with Python Flask and Bootstrap.

## Features

- Create forms with various question types:
  - Multiple Choice - Questions with multiple options
  - Identification - Short answer questions
  - Coding - Questions with sample code and expected output
- Responsive design that works across devices
- Form management (create, edit, delete)
- Response collection and viewing

## Setup Instructions

1. Clone the repository:
```
git clone https://github.com/yourusername/python-forms.git
cd python-forms
```

2. Create a virtual environment and activate it:
```
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:
```
pip install -r requirements.txt
```

4. Run the application:
```
python run.py
```

5. Open your browser and navigate to:
```
http://127.0.0.1:5000/
```

## Usage

1. **Creating a Form**:
   - Click "Create New Form" on the homepage
   - Enter a title and optional description
   - Click "Create Form"

2. **Adding Questions**:
   - On the form edit page, fill out the question form
   - Select the question type (Multiple Choice, Identification, or Coding)
   - For Multiple Choice: Add options using the "Add Option" button
   - For Coding: Add sample code and expected output
   - Click "Add Question"

3. **Viewing a Form**:
   - From the homepage, click "View" on any form
   - Or click "Preview Form" when editing a form

4. **Submitting Responses**:
   - Navigate to the form view page
   - Fill out the form questions
   - Click "Submit"

5. **Viewing Responses**:
   - From the homepage, click "Responses" on any form
   - Click "View" on any response to see details

## Technologies Used

- **Backend**: Python Flask
- **Database**: SQLite with SQLAlchemy ORM
- **Frontend**: HTML, CSS, JavaScript, Bootstrap 5
- **Icons**: Bootstrap Icons 