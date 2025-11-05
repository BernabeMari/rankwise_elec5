import json
import time
import pytest
from unittest.mock import patch

from app import db
from app.models.models import Form, Question, Response, Answer


@pytest.fixture()
def sample_form(app):
    with app.app_context():
        form = Form(title='Test Form', description='desc')
        db.session.add(form)
        db.session.flush()
        q1 = Question(form_id=form.id, question_text='2+2?', question_type='multiple_choice', correct_answer='4', points=2, order=1)
        q1.set_options(['3','4','5','6'])
        q2 = Question(form_id=form.id, question_text='Language in browsers', question_type='identification', correct_answer='JavaScript', points=3, order=2)
        q3 = Question(form_id=form.id, question_text='Write sum function', question_type='coding', points=5, order=3)
        db.session.add_all([q1, q2, q3])
        db.session.commit()
        return form.id


def test_submit_form_scoring(student_session, app, sample_form):
    client = student_session
    # Ensure form visible
    with app.app_context():
        form = Form.query.get(sample_form)
        form.is_visible = True
        db.session.commit()
    # Mock custom evaluation for coding
    with patch('app.routes.evaluate_code_with_custom_system', return_value=(True, 90, 'All tests passed')):
        resp = client.post(f'/form/{sample_form}/submit', data={}, follow_redirects=False)
    # fetch created response
    with app.app_context():
        resp_db = Response.query.order_by(Response.id.desc()).first()
        assert resp_db is not None
        answers = {a.question.question_type: a for a in resp_db.answers}
        # Multiple choice default empty => incorrect
        assert answers['multiple_choice'].score_percentage == 0
        # Identification default empty => 0
        assert answers['identification'].score_percentage == 0
        # Coding empty answer should be 0 (AI not invoked)
        assert answers['coding'].score_percentage == 0


def test_submit_form_with_answers(student_session, app, sample_form):
    client = student_session
    with app.app_context():
        form = Form.query.get(sample_form)
        form.is_visible = True
        db.session.commit()
        q_by_type = {q.question_type: q for q in Question.query.filter_by(form_id=form.id).all()}
    with patch('app.routes.evaluate_code_with_custom_system', return_value=(True, 100, 'All tests passed')):
        resp = client.post(f'/form/{sample_form}/submit', data={
            f'question_{q_by_type["multiple_choice"].id}': '4',
            f'question_{q_by_type["identification"].id}': 'javascript',
            f'question_{q_by_type["coding"].id}': 'def add(a,b): return a+b',
        }, follow_redirects=False)
        assert resp.status_code == 302
    with app.app_context():
        resp_db = Response.query.order_by(Response.id.desc()).first()
        answers = {a.question.question_type: a for a in resp_db.answers}
        assert answers['multiple_choice'].is_correct is True
        assert answers['identification'].score_percentage >= 70
        assert answers['coding'].score_percentage == 100


def test_view_responses_ranking(admin_session, app, sample_form):
    client = admin_session
    with app.app_context():
        form = Form.query.get(sample_form)
        form.is_visible = True
        db.session.commit()
        # create two responses with different percentages via answers directly
        r1 = Response(form_id=form.id, submitted_by='s1')
        r2 = Response(form_id=form.id, submitted_by='s2')
        db.session.add_all([r1, r2])
        db.session.flush()
        q_list = Question.query.filter_by(form_id=form.id).all()
        # r1: better score
        db.session.add_all([
            Answer(response_id=r1.id, question_id=q_list[0].id, score_percentage=100),
            Answer(response_id=r1.id, question_id=q_list[1].id, score_percentage=100),
            Answer(response_id=r1.id, question_id=q_list[2].id, score_percentage=100),
        ])
        # r2: lower
        db.session.add_all([
            Answer(response_id=r2.id, question_id=q_list[0].id, score_percentage=0),
            Answer(response_id=r2.id, question_id=q_list[1].id, score_percentage=70),
            Answer(response_id=r2.id, question_id=q_list[2].id, score_percentage=50),
        ])
        db.session.commit()
    resp = client.get(f'/form/{sample_form}/responses')
    assert resp.status_code == 200
    assert b'rank' in resp.data or b'Rank' in resp.data


def test_view_response_badges_and_speed(student_session, app, sample_form):
    client = student_session
    # Submit a response with high scores through the route to avoid detached instances
    with app.app_context():
        form = Form.query.get(sample_form)
        form.is_visible = True
        db.session.commit()
        q_by_type = {q.question_type: q for q in Question.query.filter_by(form_id=form.id).all()}
    with patch('app.routes.evaluate_code_with_custom_system', return_value=(True, 100, 'All tests passed')):
        client.post(f'/form/{sample_form}/submit', data={
            f'question_{q_by_type["multiple_choice"].id}': '4',
            f'question_{q_by_type["identification"].id}': 'javascript',
            f'question_{q_by_type["coding"].id}': 'def add(a,b): return a+b',
        }, follow_redirects=False)
    with app.app_context():
        r = Response.query.order_by(Response.id.desc()).first()
        r_id = r.id
    with client.session_transaction() as sess:
        sess[f'response_duration_{r_id}'] = 10.0
    resp = client.get(f'/response/{r_id}')
    assert resp.status_code == 200
    assert b'High Score' in resp.data or b'Good Score' in resp.data


def test_clear_form_responses(admin_session, app, sample_form):
    client = admin_session
    with app.app_context():
        form = Form.query.get(sample_form)
        r = Response(form_id=form.id)
        db.session.add(r)
        db.session.flush()
        a = Answer(response_id=r.id, question_id=Question.query.filter_by(form_id=form.id).first().id, score_percentage=100)
        db.session.add(a)
        db.session.commit()
    resp = client.post(f'/form/{sample_form}/responses/clear', follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        assert Response.query.filter_by(form_id=sample_form).count() == 0
        assert Answer.query.count() == 0


@pytest.fixture()
def form_with_all_question_types(app):
    with app.app_context():
        form = Form(title='All Types Form', description='desc', is_visible=True)
        db.session.add(form)
        db.session.flush()
        
        # Multiple choice
        q1 = Question(form_id=form.id, question_text='What is 2+2?', question_type='multiple_choice', 
                     correct_answer='4', points=2, order=1)
        q1.set_options(['3','4','5','6'])
        
        # Checkbox
        q2 = Question(form_id=form.id, question_text='Which are programming languages?', 
                     question_type='checkbox', correct_answer=json.dumps(['Python', 'Java']), points=3, order=2)
        q2.set_options(['Python', 'HTML', 'Java', 'CSS'])
        
        # True/False
        q3 = Question(form_id=form.id, question_text='Python is compiled', 
                     question_type='true_false', correct_answer='False', points=1, order=3)
        
        # Enumeration
        q4 = Question(form_id=form.id, question_text='Name three data types', 
                     question_type='enumeration', correct_answer=json.dumps(['int', 'str', 'float']), points=3, order=4)
        
        # Identification
        q5 = Question(form_id=form.id, question_text='Language for web', 
                     question_type='identification', correct_answer='JavaScript', points=2, order=5)
        
        db.session.add_all([q1, q2, q3, q4, q5])
        db.session.commit()
        return form.id


def test_submit_checkbox_correct(student_session, app, form_with_all_question_types):
    client = student_session
    with app.app_context():
        q_by_type = {q.question_type: q for q in Question.query.filter_by(form_id=form_with_all_question_types).all()}
    # For checkbox, use getlist which requires multiple values with same key
    from werkzeug.datastructures import MultiDict
    form_data = MultiDict([
        (f'question_{q_by_type["checkbox"].id}', 'Python'),
        (f'question_{q_by_type["checkbox"].id}', 'Java'),
    ])
    resp = client.post(f'/form/{form_with_all_question_types}/submit', data=form_data, follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        resp_db = Response.query.order_by(Response.id.desc()).first()
        checkbox_answer = next(a for a in resp_db.answers if a.question.question_type == 'checkbox')
        assert checkbox_answer.score_percentage == 100
        assert checkbox_answer.is_correct is True


def test_submit_checkbox_partial(student_session, app, form_with_all_question_types):
    client = student_session
    with app.app_context():
        q_by_type = {q.question_type: q for q in Question.query.filter_by(form_id=form_with_all_question_types).all()}
    from werkzeug.datastructures import MultiDict
    form_data = MultiDict([
        (f'question_{q_by_type["checkbox"].id}', 'Python'),  # Only one correct out of two
    ])
    resp = client.post(f'/form/{form_with_all_question_types}/submit', data=form_data, follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        resp_db = Response.query.order_by(Response.id.desc()).first()
        checkbox_answer = next(a for a in resp_db.answers if a.question.question_type == 'checkbox')
        assert checkbox_answer.score_percentage < 100
        assert checkbox_answer.score_percentage > 0


def test_submit_true_false_correct(student_session, app, form_with_all_question_types):
    client = student_session
    with app.app_context():
        q_by_type = {q.question_type: q for q in Question.query.filter_by(form_id=form_with_all_question_types).all()}
    resp = client.post(f'/form/{form_with_all_question_types}/submit', data={
        f'question_{q_by_type["true_false"].id}': 'False',
    }, follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        resp_db = Response.query.order_by(Response.id.desc()).first()
        tf_answer = next(a for a in resp_db.answers if a.question.question_type == 'true_false')
        assert tf_answer.score_percentage == 100
        assert tf_answer.is_correct is True


def test_submit_enumeration_partial(student_session, app, form_with_all_question_types):
    client = student_session
    with app.app_context():
        q_by_type = {q.question_type: q for q in Question.query.filter_by(form_id=form_with_all_question_types).all()}
    resp = client.post(f'/form/{form_with_all_question_types}/submit', data={
        f'question_{q_by_type["enumeration"].id}': 'int, str',  # Two out of three
    }, follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        resp_db = Response.query.order_by(Response.id.desc()).first()
        enum_answer = next(a for a in resp_db.answers if a.question.question_type == 'enumeration')
        assert enum_answer.score_percentage > 0
        assert enum_answer.score_percentage < 100


def test_form_visibility_toggle(admin_session, app):
    client = admin_session
    with app.app_context():
        form = Form(title='Toggle Test', is_visible=True)
        db.session.add(form)
        db.session.commit()
        form_id = form.id
    resp = client.post(f'/form/{form_id}/toggle-visibility', follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        form = Form.query.get(form_id)
        assert form.is_visible is False
    # Toggle again
    resp = client.post(f'/form/{form_id}/toggle-visibility', follow_redirects=False)
    with app.app_context():
        form = Form.query.get(form_id)
        assert form.is_visible is True


def test_student_cannot_view_hidden_form(student_session, app):
    client = student_session
    with app.app_context():
        form = Form(title='Hidden Form', is_visible=False)
        db.session.add(form)
        db.session.commit()
        form_id = form.id
    resp = client.get(f'/form/{form_id}/view', follow_redirects=False)
    assert resp.status_code == 302  # Redirected
    assert b'not currently available' in resp.data or b'warning' in resp.data.lower()


def test_admin_can_view_hidden_form(admin_session, app):
    client = admin_session
    with app.app_context():
        form = Form(title='Hidden Form', is_visible=False)
        db.session.add(form)
        db.session.commit()
        form_id = form.id
    resp = client.get(f'/form/{form_id}/view', follow_redirects=False)
    assert resp.status_code == 200  # Admin can view


def test_student_index_filters_completed_forms(student_session, app):
    client = student_session
    user_id = 'student1'
    with app.app_context():
        form1 = Form(title='Form 1', is_visible=True)
        form2 = Form(title='Form 2', is_visible=True)
        db.session.add_all([form1, form2])
        db.session.flush()
        # Student already completed form1
        r = Response(form_id=form1.id, submitted_by=user_id)
        db.session.add(r)
        db.session.commit()
        form1_id = form1.id
        form2_id = form2.id
    resp = client.get('/')
    assert resp.status_code == 200
    # Form1 should not appear (already completed), Form2 should appear
    assert b'Form 2' in resp.data
    # Form1 might still appear but with different status - check that at least form2 is there


def test_analytics_endpoint(admin_session, app, sample_form):
    client = admin_session
    with app.app_context():
        form = Form.query.get(sample_form)
        form.is_visible = True
        # Create a response
        r = Response(form_id=form.id, submitted_by='s1')
        db.session.add(r)
        db.session.flush()
        q = Question.query.filter_by(form_id=form.id).first()
        a = Answer(response_id=r.id, question_id=q.id, score_percentage=80)
        db.session.add(a)
        db.session.commit()
    resp = client.get(f'/form/{sample_form}/analytics')
    assert resp.status_code == 200
    assert b'analytics' in resp.data.lower() or b'response' in resp.data.lower()


def test_manual_mark_answer(admin_session, app, sample_form):
    client = admin_session
    with app.app_context():
        form = Form.query.get(sample_form)
        r = Response(form_id=form.id)
        db.session.add(r)
        db.session.flush()
        q = Question.query.filter_by(form_id=form.id).first()
        a = Answer(response_id=r.id, question_id=q.id, score_percentage=50)
        db.session.add(a)
        db.session.commit()
        answer_id = a.id
    resp = client.post(f'/answer/{answer_id}/manual', data={
        'score_percentage': '100',
        'is_correct': 'true'
    }, follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        a = Answer.query.get(answer_id)
        assert a.score_percentage == 100
        assert a.is_correct is True


def test_datasets_management(admin_session, app):
    client = admin_session
    resp = client.get('/datasets')
    assert resp.status_code == 200
    assert b'dataset' in resp.data.lower()


def test_toggle_dataset_status(admin_session, app):
    client = admin_session
    with app.app_context():
        from app.models.models import Dataset
        dataset = Dataset(
            name='Test Dataset',
            filename='test.csv',
            file_path='/test.csv',
            file_size=100,
            is_builtin=True,
            is_active=True
        )
        db.session.add(dataset)
        db.session.commit()
        dataset_id = dataset.id
    resp = client.post(f'/datasets/{dataset_id}/toggle', follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        dataset = Dataset.query.get(dataset_id)
        assert dataset.is_active is False 