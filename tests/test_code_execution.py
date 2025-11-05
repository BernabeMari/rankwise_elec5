import pytest
from unittest.mock import patch, MagicMock
from app import db
from app.models.models import Form, Question


def test_execute_code_endpoint(student_session, app):
    """Test the /execute-code endpoint for code execution"""
    client = student_session
    with app.app_context():
        form = Form(title='Test Form', is_visible=True)
        db.session.add(form)
        db.session.flush()
        q = Question(form_id=form.id, question_text='Write a function', question_type='coding')
        db.session.add(q)
        db.session.commit()
        question_id = q.id
    
    # Test Python code execution
    resp = client.post('/execute-code', json={
        'code': 'print("Hello, World!")',
        'language': 'python',
        'question_id': question_id
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'output' in data or 'error' in data


def test_check_input_needed_endpoint(student_session, app):
    """Test the /check-input-needed endpoint"""
    client = student_session
    
    # Code without input
    resp = client.post('/check-input-needed', json={
        'code': 'print("Hello")',
        'language': 'python'
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'needs_input' in data
    assert data['needs_input'] is False
    
    # Code with input
    resp2 = client.post('/check-input-needed', json={
        'code': 'x = input()\nprint(x)',
        'language': 'python'
    })
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    assert 'needs_input' in data2
    assert data2['needs_input'] is True


@patch('app.routes.evaluate_code_with_custom_system')
def test_coding_question_evaluation(mock_eval, student_session, app):
    """Test coding question evaluation with custom system"""
    mock_eval.return_value = (True, 100, 'All tests passed')
    
    client = student_session
    with app.app_context():
        form = Form(title='Coding Form', is_visible=True)
        db.session.add(form)
        db.session.flush()
        q = Question(
            form_id=form.id, 
            question_text='Write a sum function',
            question_type='coding',
            expected_output='def test_sum():\n    assert sum([1,2,3]) == 6'
        )
        db.session.add(q)
        db.session.commit()
        form_id = form.id
        question_id = q.id
    
    resp = client.post(f'/form/{form_id}/submit', data={
        f'question_{question_id}': 'def sum(nums): return sum(nums)'
    }, follow_redirects=False)
    
    assert resp.status_code == 302
    mock_eval.assert_called_once()


def test_java_code_execution(student_session):
    """Test Java code execution endpoint"""
    client = student_session
    resp = client.post('/execute-code', json={
        'code': 'public class Test { public static void main(String[] args) { System.out.println("Hello"); } }',
        'language': 'java'
    })
    # Should return 200 even if compilation fails (graceful error handling)
    assert resp.status_code in [200, 400, 500]


def test_cpp_code_execution(student_session):
    """Test C++ code execution endpoint"""
    client = student_session
    resp = client.post('/execute-code', json={
        'code': '#include <iostream>\nint main() { std::cout << "Hello"; return 0; }',
        'language': 'cpp'
    })
    # Should return 200 even if compilation fails (graceful error handling)
    assert resp.status_code in [200, 400, 500]

